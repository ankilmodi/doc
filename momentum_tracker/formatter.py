"""
formatter.py – Output formatting utilities.

Produces:
  • A rich tabular view printed to stdout (pure Python, no tabulate).
  • A CSV string / file dump on request.
  • An allocation summary block.
"""

from __future__ import annotations
import csv
import io
import os
from datetime import datetime
from typing import Dict, List

import config


# ── Column definitions ────────────────────────────────────────────────────────
_COLS = [
    ("Rank",           5),
    ("Symbol",        12),
    ("Signal",         6),
    ("F&O",            4),
    ("LTP",           10),
    ("RSI",            7),
    ("Momentum%",     11),
    ("VolRatio",       9),
    ("Breakout",       9),
    ("Score",          7),
    ("Entry",         10),
    ("TG1",           10),
    ("TG2",           10),
    ("TG3",           10),
    ("StopLoss",      10),
    ("TrailStop",     10),
]


def _row(values: List[str]) -> str:
    parts = []
    for val, (_, width) in zip(values, _COLS):
        parts.append(str(val).ljust(width))
    return " ".join(parts)


def _header() -> str:
    return _row([c[0] for c in _COLS])


def _separator() -> str:
    return "-" * sum(w + 1 for _, w in _COLS)


def format_table(ranked: List[Dict], allocation: Dict[str, float], scan_time: datetime) -> str:
    """
    Return the full console output as a string.
    """
    lines: List[str] = []
    lines.append("")
    lines.append("=" * 90)
    lines.append(f"  MOMENTUM SIGNAL TRACKER  |  Scan time: {scan_time.strftime('%Y-%m-%d %H:%M:%S IST')}")
    lines.append(f"  Interval: {config.CANDLE_INTERVAL}  |  Capital: ${config.CAPITAL_USD:,} USD  "
                 f"(≈ ₹{config.CAPITAL_USD * config.USD_TO_INR:,.0f})")
    lines.append("=" * 90)

    if not ranked:
        lines.append("  ⚠  No qualifying signals found in this scan cycle.")
        lines.append("=" * 90)
        return "\n".join(lines)

    lines.append(_header())
    lines.append(_separator())

    for i, stock in enumerate(ranked, 1):
        lvl = stock.get("levels", {})
        row_vals = [
            str(i),
            stock.get("symbol", ""),
            stock.get("signal", ""),
            "YES" if stock.get("fno") else "NO",
            f"{stock.get('ltp', 0):.2f}",
            f"{stock.get('rsi', 0):.1f}" if stock.get("rsi") is not None else "N/A",
            f"{stock.get('momentum', 0):.2f}%" if stock.get("momentum") is not None else "N/A",
            f"{stock.get('volume_ratio', 0):.2f}x" if stock.get("volume_ratio") is not None else "N/A",
            "YES" if stock.get("breakout") else "NO",
            f"{stock.get('score', 0):.1f}",
            f"{lvl.get('entry', 0):.2f}",
            f"{lvl.get('tg1', 0):.2f}",
            f"{lvl.get('tg2', 0):.2f}",
            f"{lvl.get('tg3', 0):.2f}",
            f"{lvl.get('stop_loss', 0):.2f}",
            f"{lvl.get('trailing_stop', 0):.2f}",
        ]
        lines.append(_row(row_vals))

    lines.append(_separator())

    # ── Allocation block ───────────────────────────────────────────────────
    lines.append("")
    lines.append("  CAPITAL ALLOCATION SUGGESTION  (score-weighted, proportional)")
    lines.append("  " + "-" * 70)
    total_inr = config.CAPITAL_USD * config.USD_TO_INR
    lines.append(f"  {'Symbol':<14} {'Alloc (INR)':>14}  {'Alloc (USD)':>12}  {'%':>6}  Signal")
    lines.append("  " + "-" * 70)
    for stock in ranked:
        sym  = stock["symbol"]
        inr  = allocation.get(sym, 0)
        usd  = inr / config.USD_TO_INR
        pct  = inr / total_inr * 100 if total_inr else 0
        sig  = stock.get("signal", "")
        lines.append(f"  {sym:<14} {inr:>14,.2f}  {usd:>12,.2f}  {pct:>5.1f}%  {sig}")
    lines.append("  " + "-" * 70)
    lines.append(f"  {'TOTAL':<14} {total_inr:>14,.2f}  {config.CAPITAL_USD:>12,.2f}")
    lines.append("")
    lines.append("  ⚠  Allocation is indicative only. Verify lot sizes and margins before trading.")
    lines.append("=" * 90)

    return "\n".join(lines)


def to_csv(ranked: List[Dict], allocation: Dict[str, float], scan_time: datetime) -> str:
    """Return a CSV string for all ranked stocks."""
    buf = io.StringIO()
    writer = csv.writer(buf)

    writer.writerow([
        "scan_time", "rank", "symbol", "signal", "fno",
        "ltp", "rsi", "ema_fast", "ema_slow", "momentum_pct",
        "volume_ratio", "breakout", "score",
        "entry", "tg1", "tg2", "tg3", "stop_loss", "trailing_stop",
        "alloc_inr", "alloc_usd",
    ])

    ts_str = scan_time.strftime("%Y-%m-%d %H:%M:%S")
    for i, stock in enumerate(ranked, 1):
        lvl   = stock.get("levels", {})
        inr   = allocation.get(stock["symbol"], 0)
        writer.writerow([
            ts_str, i,
            stock.get("symbol"),
            stock.get("signal"),
            "YES" if stock.get("fno") else "NO",
            f"{stock.get('ltp', 0):.2f}",
            f"{stock.get('rsi', 0):.2f}"          if stock.get("rsi")          is not None else "",
            f"{stock.get('ema_fast', 0):.2f}"      if stock.get("ema_fast")     is not None else "",
            f"{stock.get('ema_slow', 0):.2f}"      if stock.get("ema_slow")     is not None else "",
            f"{stock.get('momentum', 0):.2f}"      if stock.get("momentum")     is not None else "",
            f"{stock.get('volume_ratio', 0):.2f}"  if stock.get("volume_ratio") is not None else "",
            "YES" if stock.get("breakout") else "NO",
            f"{stock.get('score', 0):.2f}",
            f"{lvl.get('entry', 0):.2f}",
            f"{lvl.get('tg1', 0):.2f}",
            f"{lvl.get('tg2', 0):.2f}",
            f"{lvl.get('tg3', 0):.2f}",
            f"{lvl.get('stop_loss', 0):.2f}",
            f"{lvl.get('trailing_stop', 0):.2f}",
            f"{inr:.2f}",
            f"{inr / config.USD_TO_INR:.2f}",
        ])

    return buf.getvalue()


def save_csv(ranked: List[Dict], allocation: Dict[str, float],
             scan_time: datetime, path: str = "signals.csv") -> None:
    """Append (or create) the CSV file with the latest scan results."""
    content = to_csv(ranked, allocation, scan_time)
    file_exists = os.path.isfile(path)
    mode = "a" if file_exists else "w"
    with open(path, mode, newline="", encoding="utf-8") as f:
        if file_exists:
            # Skip the header row when appending
            lines = content.splitlines()
            f.write("\n".join(lines[1:]) + "\n")
        else:
            f.write(content)
