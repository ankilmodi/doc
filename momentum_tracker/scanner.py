"""
scanner.py – Core scan loop.

Orchestrates:
  1. Fetch candle data and daily volume history for each symbol.
  2. Compute technical indicators.
  3. Detect and score signals.
  4. Rank, format, and print/save results.
  5. Sleep 100 seconds and repeat.

Runs until Ctrl-C.
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
    """Return True only during the configured scan window (IST)."""
    now  = datetime.now()
    hhmm = now.hour * 100 + now.minute  # e.g. 930 for 09:30

    start = int(config.SCAN_START_TIME.replace(":", ""))
    end   = int(config.SCAN_END_TIME.replace(":", ""))
    return start <= hhmm <= end


def process_symbol(
    symbol_info: Dict,
    api: AngelConnector,
) -> Dict | None:
    """
    Fetch data, calculate indicators, detect signal for one symbol.
    Returns a result dict or None if no qualifying signal.
    """
    symbol = symbol_info["symbol"]
    token  = symbol_info["token"]
    fno    = symbol_info["fno"]

    # ── 1. Fetch candle data ─────────────────────────────────────────────────
    candles = api.get_candles(
        token    = token,
        symbol   = symbol,
        interval = config.CANDLE_INTERVAL,
        n_candles = max(
            config.RSI_PERIOD + 5,
            config.EMA_SLOW   + 5,
            config.MOMENTUM_PERIOD + 5,
            30,
        ),
    )

    if len(candles) < config.RSI_PERIOD + 2:
        logger.debug("%s: insufficient candles (%d) – skipping.", symbol, len(candles))
        return None

    # ── 2. Fetch 5-day average volume ────────────────────────────────────────
    daily_vols = api.get_daily_volumes(token, symbol, days=config.VOLUME_AVG_DAYS)

    # ── 3. Compute indicators ────────────────────────────────────────────────
    indicators = ind.compute_indicators(
        candles       = candles,
        daily_volumes = daily_vols,
        rsi_period    = config.RSI_PERIOD,
        ema_fast      = config.EMA_FAST,
        ema_slow      = config.EMA_SLOW,
        mom_period    = config.MOMENTUM_PERIOD,
    )

    if not indicators:
        return None

    # ── 4. Detect and score signal ───────────────────────────────────────────
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
    Iterate over the universe, collect qualifying signals, rank them.
    Returns the top-N ranked list.
    """
    candidates: List[Dict] = []
    total = len(universe)

    for i, sym_info in enumerate(universe, 1):
        symbol = sym_info["symbol"]
        logger.info("[%d/%d] Processing %s…", i, total, symbol)
        try:
            result = process_symbol(sym_info, api)
            if result:
                candidates.append(result)
                logger.info("  ✓ %s  signal=%s  score=%.1f",
                             symbol, result["signal"], result["score"])
        except Exception as exc:
            logger.warning("  ✗ %s error: %s", symbol, exc)

        # Small pause to avoid hammering the API
        time.sleep(0.3)

    ranked = sig.rank_signals(candidates)
    return ranked


def run(save_csv: bool = False) -> None:
    """
    Main entry point.  Runs indefinitely until Ctrl-C.
    """
    logging.basicConfig(
        level  = logging.INFO,
        format = "%(asctime)s  %(levelname)-8s %(message)s",
        datefmt= "%H:%M:%S",
    )

    logger.info("Starting Momentum Signal Tracker…")
    logger.info("Interval: %s | Refresh: every %ds | Top N: %d",
                config.CANDLE_INTERVAL, config.REFRESH_SECONDS, config.TOP_N)

    # ── Init API connection ───────────────────────────────────────────────────
    api = AngelConnector()

    # ── Load and refresh the symbol universe ─────────────────────────────────
    logger.info("Loading symbol universe (refreshing tokens from Angel One master)…")
    universe = refresh_tokens_from_master()
    logger.info("Universe size: %d symbols", len(universe))

    scan_count = 0

    try:
        while True:
            now = datetime.now()

            if not _in_scan_window():
                logger.info(
                    "Outside scan window (%s – %s IST).  Next check in 60 s…",
                    config.SCAN_START_TIME, config.SCAN_END_TIME,
                )
                time.sleep(60)
                continue

            scan_count += 1
            logger.info("─── Scan #%d  at %s ───", scan_count, now.strftime("%H:%M:%S"))

            ranked     = run_single_scan(universe, api)
            allocation = sig.build_allocation(ranked)

            # Print to console
            table = fmt.format_table(ranked, allocation, now)
            print(table)

            # Optionally save to CSV
            if save_csv:
                fmt.save_csv(ranked, allocation, now, path="signals.csv")
                logger.info("Results saved to signals.csv")

            logger.info("Scan #%d complete – %d qualifying signal(s). "
                        "Next scan in %ds…",
                        scan_count, len(ranked), config.REFRESH_SECONDS)
            time.sleep(config.REFRESH_SECONDS)

    except KeyboardInterrupt:
        logger.info("Stopped by user after %d scan(s).", scan_count)
