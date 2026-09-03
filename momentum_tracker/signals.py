"""
signals.py – Signal detection, scoring, and ranking logic.

A stock qualifies for a BUY signal when ALL of:
  1. RSI is between RSI_BUY_MIN and RSI_BUY_MAX  (momentum but not overbought)
  2. EMA trend is bullish  (fast EMA > slow EMA)
  3. Momentum (ROC) > MOMENTUM_BUY_MIN  (positive rate-of-change)
  4. Volume ratio >= VOLUME_SPIKE_MULT   (above-average volume)
  5. Price >= MIN_PRICE                  (no penny stocks)

A stock qualifies for a SELL / SHORT signal when ALL of:
  1. RSI is between RSI_SELL_MIN and RSI_SELL_MAX  (weak, not oversold)
  2. EMA trend is bearish
  3. Momentum < MOMENTUM_SELL_MAX         (negative ROC)
  4. Volume ratio >= VOLUME_SPIKE_MULT    (distribution with volume)
  5. Price >= MIN_PRICE

Breakout stocks get an extra +15 points in the score.

Scoring model (0-100):
  - RSI component      : 0-25 pts  (closer to ideal band mid = more)
  - Momentum component : 0-25 pts  (higher |momentum| = more)
  - Volume ratio       : 0-25 pts  (capped at 3× avg)
  - EMA separation     : 0-15 pts  (|fast-slow|/slow * 100, capped at 2 %)
  - Breakout bonus     : 0-15 pts
"""

from __future__ import annotations
from typing import Dict, List, Optional, Tuple
import config


SignalType = str   # "BUY" | "SELL" | "NONE"


def _score_rsi(rsi: float, signal: SignalType) -> float:
    """Return 0-25 RSI score."""
    if signal == "BUY":
        mid = (config.RSI_BUY_MIN + config.RSI_BUY_MAX) / 2
        distance = abs(rsi - mid)
        half_range = (config.RSI_BUY_MAX - config.RSI_BUY_MIN) / 2
        return max(0, 25 * (1 - distance / half_range))
    elif signal == "SELL":
        mid = (config.RSI_SELL_MIN + config.RSI_SELL_MAX) / 2
        distance = abs(rsi - mid)
        half_range = (config.RSI_SELL_MAX - config.RSI_SELL_MIN) / 2
        return max(0, 25 * (1 - distance / half_range))
    return 0.0


def _score_momentum(mom: float, signal: SignalType) -> float:
    """Return 0-25 momentum score."""
    cap = 10.0   # cap at 10 % ROC for full marks
    if signal == "BUY":
        val = max(0, min(mom, cap))
    elif signal == "SELL":
        val = max(0, min(-mom, cap))
    else:
        return 0.0
    return 25 * val / cap


def _score_volume(vol_ratio: float) -> float:
    """Return 0-25 volume score."""
    capped = min(vol_ratio, 3.0)   # 3× avg = full marks
    return 25 * (capped - 1.0) / 2.0  # starts earning above 1×


def _score_ema(ema_fast: float, ema_slow: float, signal: SignalType) -> float:
    """Return 0-15 EMA separation score."""
    if ema_slow == 0:
        return 0.0
    sep_pct = abs(ema_fast - ema_slow) / ema_slow * 100
    capped = min(sep_pct, 2.0)
    score = 15 * capped / 2.0
    # Only award if direction matches signal
    if signal == "BUY"  and ema_fast < ema_slow:
        return 0.0
    if signal == "SELL" and ema_fast > ema_slow:
        return 0.0
    return score


def detect_signal(ind: Dict) -> SignalType:
    """
    Evaluate indicator dict and return "BUY", "SELL", or "NONE".
    """
    rsi        = ind.get("rsi")
    ema_trend  = ind.get("ema_trend")
    mom        = ind.get("momentum")
    vol_ratio  = ind.get("volume_ratio")
    ltp        = ind.get("ltp", 0)

    # All values must be available
    if any(v is None for v in [rsi, ema_trend, mom, vol_ratio]):
        return "NONE"

    # Penny-stock filter
    if ltp < config.MIN_PRICE:
        return "NONE"

    # Volume must be a spike
    if vol_ratio < config.VOLUME_SPIKE_MULT:
        return "NONE"

    # BUY conditions
    if (
        config.RSI_BUY_MIN <= rsi <= config.RSI_BUY_MAX
        and ema_trend == "bullish"
        and mom >= config.MOMENTUM_BUY_MIN
    ):
        return "BUY"

    # SELL conditions
    if (
        config.RSI_SELL_MIN <= rsi <= config.RSI_SELL_MAX
        and ema_trend == "bearish"
        and mom <= config.MOMENTUM_SELL_MAX
    ):
        return "SELL"

    return "NONE"


def score_signal(ind: Dict, signal: SignalType) -> float:
    """Return 0-100 composite score for a qualifying signal."""
    if signal == "NONE":
        return 0.0

    rsi       = ind.get("rsi", 0) or 0
    mom       = ind.get("momentum", 0) or 0
    vol_ratio = ind.get("volume_ratio", 1) or 1
    ef        = ind.get("ema_fast", 0) or 0
    es        = ind.get("ema_slow", 0) or 0
    breakout  = ind.get("breakout", False)

    s  = _score_rsi(rsi, signal)
    s += _score_momentum(mom, signal)
    s += _score_volume(vol_ratio)
    s += _score_ema(ef, es, signal)
    if breakout:
        s += 15.0

    return round(min(s, 100.0), 2)


def build_trade_levels(ltp: float, signal: SignalType) -> Dict[str, float]:
    """
    Calculate entry / exit / TG1-TG3 / stop-loss / trailing-stop.

    For BUY  : targets are above entry; stop-loss is below.
    For SELL : targets are below entry; stop-loss is above.
    """
    sl_pct   = config.STOP_LOSS_PCT   / 100
    ts_pct   = config.TRAILING_STOP_PCT / 100
    tg1_pct  = config.TG1_PCT / 100
    tg2_pct  = config.TG2_PCT / 100
    tg3_pct  = config.TG3_PCT / 100

    r = lambda v: round(v, 2)

    if signal == "BUY":
        entry = r(ltp)
        return {
            "entry":          entry,
            "exit":           r(entry * (1 - sl_pct)),   # initial exit = stop-loss
            "stop_loss":      r(entry * (1 - sl_pct)),
            "trailing_stop":  r(entry * (1 - ts_pct)),   # will trail LTP
            "tg1":            r(entry * (1 + tg1_pct)),
            "tg2":            r(entry * (1 + tg2_pct)),
            "tg3":            r(entry * (1 + tg3_pct)),
        }
    elif signal == "SELL":
        entry = r(ltp)
        return {
            "entry":          entry,
            "exit":           r(entry * (1 + sl_pct)),
            "stop_loss":      r(entry * (1 + sl_pct)),
            "trailing_stop":  r(entry * (1 + ts_pct)),
            "tg1":            r(entry * (1 - tg1_pct)),
            "tg2":            r(entry * (1 - tg2_pct)),
            "tg3":            r(entry * (1 - tg3_pct)),
        }
    return {}


def rank_signals(candidates: List[Dict]) -> List[Dict]:
    """
    Sort by score descending, return top N.
    Each candidate dict must have a "score" key.
    """
    sorted_list = sorted(candidates, key=lambda x: x.get("score", 0), reverse=True)
    return sorted_list[: config.TOP_N]


def build_allocation(ranked: List[Dict]) -> Dict[str, float]:
    """
    Proportional capital allocation based on signal score.
    Capital is config.CAPITAL_USD converted to INR.
    Returns {symbol: allocated_inr}.
    """
    total_capital_inr = config.CAPITAL_USD * config.USD_TO_INR
    total_score = sum(s["score"] for s in ranked) or 1
    return {
        s["symbol"]: round(s["score"] / total_score * total_capital_inr, 2)
        for s in ranked
    }
