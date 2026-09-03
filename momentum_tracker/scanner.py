"""
scanner.py – Core scan loop.

Strategy (IP-restriction workaround):
  - Fetch ALL symbols in one bulk FULL-quote call per cycle (no historical API).
  - Each quote gives: ltp, open, high, low, close (prev), volume, tradeVolume.
  - Push each quote into an in-memory rolling candle cache (deque, max 60 bars).
  - Calculate indicators from the accumulated cache.
  - Over time (warm serverless instance / local run) the cache grows and
    indicator quality improves.  First scan uses 1-bar data → limited signals;
    subsequent scans become progressively more accurate.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Dict, List

import config
import indicators as ind
import signals as sig
import formatter as fmt
from angel_connector import AngelConnector
from symbols import build_symbol_list, refresh_tokens_from_master

logger = logging.getLogger(__name__)


def _in_scan_window() -> bool:
    now  = datetime.now()
    hhmm = now.hour * 100 + now.minute
    start = int(config.SCAN_START_TIME.replace(":", ""))
    end   = int(config.SCAN_END_TIME.replace(":", ""))
    return start <= hhmm <= end


def process_symbol(
    symbol_info: Dict,
    api:         AngelConnector,
    quote:       Dict,            # pre-fetched FULL quote for this token
) -> Dict | None:
    """
    Compute indicators and detect signal for one symbol using cached candles.
    """
    symbol = symbol_info["symbol"]
    token  = symbol_info["token"]
    fno    = symbol_info["fno"]

    # Push current quote into the rolling cache
    api.update_candle_cache(token, quote)

    # ── Fetch candle series from cache ────────────────────────────────────────
    candles = api.get_candles(
        token=token, symbol=symbol,
        interval=config.CANDLE_INTERVAL,
        n_candles=max(config.RSI_PERIOD + 5, config.EMA_SLOW + 5, 30),
    )

    # Need at least RSI_PERIOD+2 bars for meaningful indicators
    if len(candles) < max(5, config.RSI_PERIOD // 2):
        logger.debug("%s: only %d bar(s) in cache – using relaxed thresholds.",
                     symbol, len(candles))

    # ── 5-day volume: use today's cumulative volume as proxy ──────────────────
    today_vol = int(quote.get("tradeVolume", quote.get("volume", 0)))
    # Build a proxy daily volume list (flat baseline → ratio = 1.0)
    daily_vols = [today_vol] * config.VOLUME_AVG_DAYS if today_vol > 0 else []

    # ── Compute indicators ────────────────────────────────────────────────────
    indicators = ind.compute_indicators(
        candles=candles,
        daily_volumes=daily_vols,
        rsi_period=min(config.RSI_PERIOD, max(len(candles) - 1, 1)),
        ema_fast=min(config.EMA_FAST, max(len(candles) - 1, 1)),
        ema_slow=min(config.EMA_SLOW, max(len(candles) - 1, 1)),
        mom_period=min(config.MOMENTUM_PERIOD, max(len(candles) - 1, 1)),
    )

    if not indicators:
        return None

    # For volume ratio: compare current bar volume vs. previous bars' avg
    if len(candles) >= 3:
        prev_vols = [c["volume"] for c in candles[:-1]]
        avg_prev  = sum(prev_vols) / len(prev_vols) if prev_vols else 1
        current_vol = candles[-1]["volume"]
        live_ratio  = current_vol / avg_prev if avg_prev > 0 else 1.0
        indicators["volume_ratio"] = round(live_ratio, 3)

    # ── Detect & score ────────────────────────────────────────────────────────
    signal = sig.detect_signal(indicators)
    if signal == "NONE":
        return None

    score  = sig.score_signal(indicators, signal)
    levels = sig.build_trade_levels(indicators["ltp"], signal)

    return {
        "symbol":       symbol,
        "token":        token,
        "fno":          fno,
        "signal":       signal,
        "score":        score,
        "levels":       levels,
        "ltp":          indicators["ltp"],
        "rsi":          indicators["rsi"],
        "ema_fast":     indicators["ema_fast"],
        "ema_slow":     indicators["ema_slow"],
        "ema_trend":    indicators["ema_trend"],
        "momentum":     indicators["momentum"],
        "volume_ratio": indicators["volume_ratio"],
        "breakout":     indicators["breakout"],
    }


def run_single_scan(universe: List[Dict], api: AngelConnector) -> List[Dict]:
    """
    One full scan cycle:
      1. Bulk-fetch FULL quotes for all symbols (single API round-trip).
      2. Process each symbol with cached candle data.
      3. Return ranked top-N signals.
    """
    logger.info("Bulk-fetching FULL quotes for %d symbols…", len(universe))

    # One bulk call for all quotes
    all_quotes = api.fetch_and_cache_all(universe)

    logger.info("Quotes received: %d / %d", len(all_quotes), len(universe))

    candidates: List[Dict] = []
    for sym_info in universe:
        token  = sym_info["token"]
        symbol = sym_info["symbol"]
        quote  = all_quotes.get(token)

        if not quote:
            logger.debug("%s: no quote received – skipping.", symbol)
            continue

        try:
            result = process_symbol(sym_info, api, quote)
            if result:
                candidates.append(result)
                logger.info("  ✓ %s  signal=%s  score=%.1f  ltp=%.2f",
                             symbol, result["signal"], result["score"], result["ltp"])
        except Exception as exc:
            logger.warning("  ✗ %s error: %s", symbol, exc)

    ranked = sig.rank_signals(candidates)
    return ranked


def run(save_csv: bool = False) -> None:
    """Main entry point for the continuous CLI scan loop."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )

    logger.info("Starting Momentum Signal Tracker…")
    logger.info("Interval: %s | Refresh: every %ds | Top N: %d",
                config.CANDLE_INTERVAL, config.REFRESH_SECONDS, config.TOP_N)

    api      = AngelConnector()
    universe = refresh_tokens_from_master()
    logger.info("Universe: %d symbols", len(universe))

    scan_count = 0
    try:
        while True:
            now = datetime.now()

            if not _in_scan_window():
                logger.info("Outside scan window (%s–%s). Waiting 60 s…",
                            config.SCAN_START_TIME, config.SCAN_END_TIME)
                time.sleep(60)
                continue

            scan_count += 1
            logger.info("─── Scan #%d at %s ───", scan_count, now.strftime("%H:%M:%S"))

            ranked     = run_single_scan(universe, api)
            allocation = sig.build_allocation(ranked)

            print(fmt.format_table(ranked, allocation, now))

            if save_csv:
                fmt.save_csv(ranked, allocation, now, path="signals.csv")

            logger.info("Scan #%d done – %d signal(s). Next in %ds…",
                        scan_count, len(ranked), config.REFRESH_SECONDS)
            time.sleep(config.REFRESH_SECONDS)

    except KeyboardInterrupt:
        logger.info("Stopped after %d scan(s).", scan_count)
