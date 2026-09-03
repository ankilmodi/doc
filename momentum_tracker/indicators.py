"""
indicators.py – Pure-Python technical indicator calculations.

No numpy / pandas required.  All functions operate on plain Python lists
of OHLCV dicts (as returned by AngelConnector.get_candles).

Each candle dict structure:
    {"timestamp": datetime, "open": float, "high": float,
     "low": float, "close": float, "volume": int}
"""

from __future__ import annotations
from typing import List, Dict, Optional


# ── Helper: extract close prices ─────────────────────────────────────────────

def _closes(candles: List[Dict]) -> List[float]:
    return [c["close"] for c in candles]

def _volumes(candles: List[Dict]) -> List[int]:
    return [c["volume"] for c in candles]


# ── EMA ───────────────────────────────────────────────────────────────────────

def ema(values: List[float], period: int) -> List[float]:
    """
    Exponential Moving Average.
    Returns a list of the same length as *values*; the first (period-1)
    elements are None (insufficient data).
    """
    if len(values) < period:
        return [None] * len(values)

    k = 2.0 / (period + 1)
    result: List[Optional[float]] = [None] * (period - 1)

    # Seed with a simple average of the first *period* values
    seed = sum(values[:period]) / period
    result.append(seed)

    for v in values[period:]:
        result.append(v * k + result[-1] * (1 - k))

    return result


def ema_current(candles: List[Dict], period: int) -> Optional[float]:
    """Return the latest EMA value, or None if insufficient data."""
    vals = ema(_closes(candles), period)
    for v in reversed(vals):
        if v is not None:
            return v
    return None


# ── RSI ───────────────────────────────────────────────────────────────────────

def rsi(values: List[float], period: int = 14) -> List[Optional[float]]:
    """
    Wilder's RSI.
    Returns a list of the same length; first *period* elements are None.
    """
    n = len(values)
    if n <= period:
        return [None] * n

    gains, losses = [], []
    for i in range(1, n):
        diff = values[i] - values[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    result: List[Optional[float]] = [None] * (period + 1)

    def _rsi_from_avg(ag: float, al: float) -> float:
        if al == 0:
            return 100.0
        rs = ag / al
        return 100 - 100 / (1 + rs)

    result.append(_rsi_from_avg(avg_gain, avg_loss))

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        result.append(_rsi_from_avg(avg_gain, avg_loss))

    return result


def rsi_current(candles: List[Dict], period: int = 14) -> Optional[float]:
    """Return the latest RSI, or None."""
    vals = rsi(_closes(candles), period)
    for v in reversed(vals):
        if v is not None:
            return v
    return None


# ── Momentum (Rate of Change) ─────────────────────────────────────────────────

def momentum_roc(values: List[float], period: int = 10) -> List[Optional[float]]:
    """
    Percentage Rate of Change:   (close - close[n]) / close[n] * 100
    Returns same-length list; first *period* elements are None.
    """
    result: List[Optional[float]] = [None] * period
    for i in range(period, len(values)):
        prev = values[i - period]
        if prev == 0:
            result.append(0.0)
        else:
            result.append((values[i] - prev) / prev * 100.0)
    return result


def momentum_current(candles: List[Dict], period: int = 10) -> Optional[float]:
    """Return the latest momentum % value."""
    vals = momentum_roc(_closes(candles), period)
    for v in reversed(vals):
        if v is not None:
            return v
    return None


# ── Volume ratio vs. 5-day average ───────────────────────────────────────────

def volume_ratio(current_volume: int, historical_daily_volumes: List[int]) -> Optional[float]:
    """
    current_volume        : today's cumulative volume (or latest bar's volume)
    historical_daily_volumes : list of N previous session total volumes

    Returns current / avg(historical) or None if list is empty.
    """
    if not historical_daily_volumes:
        return None
    avg = sum(historical_daily_volumes) / len(historical_daily_volumes)
    if avg == 0:
        return None
    return current_volume / avg


# ── Breakout detection ────────────────────────────────────────────────────────

def is_breakout(candles: List[Dict], lookback: int = 20) -> bool:
    """
    True if the latest close is >= the highest high of the previous
    *lookback* candles (classic horizontal-resistance breakout).
    Volume spike is checked separately via volume_ratio.
    """
    if len(candles) < lookback + 1:
        return False
    recent  = candles[-(lookback + 1):-1]   # previous candles (exclude current)
    current = candles[-1]
    prev_high = max(c["high"] for c in recent)
    return current["close"] >= prev_high


# ── Aggregate indicator snapshot ──────────────────────────────────────────────

def compute_indicators(
    candles:        List[Dict],
    daily_volumes:  List[int],
    rsi_period:     int = 14,
    ema_fast:       int = 9,
    ema_slow:       int = 21,
    mom_period:     int = 10,
) -> Dict:
    """
    Compute all indicators for one symbol and return a flat dict.

    Returns:
        {
            "rsi":          float | None,
            "ema_fast":     float | None,
            "ema_slow":     float | None,
            "ema_trend":    "bullish" | "bearish" | "neutral" | None,
            "momentum":     float | None,
            "volume_ratio": float | None,
            "breakout":     bool,
            "ltp":          float,
            "high":         float,
            "low":          float,
            "open":         float,
        }
    """
    if not candles:
        return {}

    last = candles[-1]
    ltp  = last["close"]

    r         = rsi_current(candles, rsi_period)
    ef        = ema_current(candles, ema_fast)
    es        = ema_current(candles, ema_slow)
    mom       = momentum_current(candles, mom_period)
    vol_ratio = volume_ratio(last["volume"], daily_volumes)
    breakout  = is_breakout(candles)

    # EMA trend
    if ef is not None and es is not None:
        if ef > es:
            trend = "bullish"
        elif ef < es:
            trend = "bearish"
        else:
            trend = "neutral"
    else:
        trend = None

    return {
        "rsi":          r,
        "ema_fast":     ef,
        "ema_slow":     es,
        "ema_trend":    trend,
        "momentum":     mom,
        "volume_ratio": vol_ratio,
        "breakout":     breakout,
        "ltp":          ltp,
        "high":         last["high"],
        "low":          last["low"],
        "open":         last["open"],
    }
