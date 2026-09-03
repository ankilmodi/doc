"""
api/index.py – FastAPI web server for the Momentum Signal Tracker.
Deployed as a Vercel Python serverless function.

Endpoints:
  GET /          → health check + instructions
  GET /scan      → run one full scan and return JSON results
  GET /scan/csv  → run one scan and return CSV
  GET /scan/table → run one scan and return plain-text table
"""

from __future__ import annotations
import sys
import os

# Make sure the momentum_tracker package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "momentum_tracker"))

from fastapi import FastAPI, Query
from fastapi.responses import PlainTextResponse, JSONResponse
from datetime import datetime
from typing import Optional

import config
import signals as sig
import formatter as fmt
from angel_connector import AngelConnector
from symbols import refresh_tokens_from_master
from scanner import run_single_scan

app = FastAPI(
    title="Momentum Signal Tracker",
    description="Intraday NIFTY 50/500 momentum signals via Angel One SmartConnect.",
    version="1.0.0",
)

# ── Cached API connection (reused across warm invocations) ────────────────────
_api: Optional[AngelConnector] = None
_universe = None


def _get_api() -> AngelConnector:
    global _api
    if _api is None:
        _api = AngelConnector()
    return _api


def _get_universe():
    global _universe
    if _universe is None:
        _universe = refresh_tokens_from_master()
    return _universe


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=PlainTextResponse)
def root():
    return (
        "Momentum Signal Tracker – Live\n"
        "================================\n\n"
        "Endpoints:\n"
        "  GET /scan          → JSON results\n"
        "  GET /scan/table    → plain-text table\n"
        "  GET /scan/csv      → CSV download\n\n"
        "Query params (all optional):\n"
        "  interval  ONE_MINUTE | FIVE_MINUTE | FIFTEEN_MINUTE  (default: FIVE_MINUTE)\n"
        "  top       number of stocks in output  (default: 10)\n"
        "  capital   capital in USD              (default: 10000)\n"
    )


@app.get("/scan")
def scan_json(
    interval: str = Query("FIVE_MINUTE", description="Candle interval"),
    top: int      = Query(10,            description="Max stocks in output"),
    capital: float= Query(10000,         description="Capital in USD"),
):
    config.CANDLE_INTERVAL = interval
    config.TOP_N           = top
    config.CAPITAL_USD     = capital

    api      = _get_api()
    universe = _get_universe()
    now      = datetime.now()
    ranked   = run_single_scan(universe, api)
    alloc    = sig.build_allocation(ranked)

    payload = []
    for i, stock in enumerate(ranked, 1):
        lvl = stock.get("levels", {})
        payload.append({
            "rank":           i,
            "symbol":         stock["symbol"],
            "signal":         stock["signal"],
            "fno":            stock["fno"],
            "ltp":            stock["ltp"],
            "rsi":            stock.get("rsi"),
            "ema_fast":       stock.get("ema_fast"),
            "ema_slow":       stock.get("ema_slow"),
            "ema_trend":      stock.get("ema_trend"),
            "momentum_pct":   stock.get("momentum"),
            "volume_ratio":   stock.get("volume_ratio"),
            "breakout":       stock.get("breakout"),
            "score":          stock["score"],
            "entry":          lvl.get("entry"),
            "tg1":            lvl.get("tg1"),
            "tg2":            lvl.get("tg2"),
            "tg3":            lvl.get("tg3"),
            "stop_loss":      lvl.get("stop_loss"),
            "trailing_stop":  lvl.get("trailing_stop"),
            "alloc_inr":      alloc.get(stock["symbol"]),
            "alloc_usd":      round(alloc.get(stock["symbol"], 0) / config.USD_TO_INR, 2),
        })

    return JSONResponse({
        "scan_time": now.isoformat(),
        "interval":  interval,
        "count":     len(ranked),
        "results":   payload,
    })


@app.get("/scan/table", response_class=PlainTextResponse)
def scan_table(
    interval: str  = Query("FIVE_MINUTE"),
    top: int       = Query(10),
    capital: float = Query(10000),
):
    config.CANDLE_INTERVAL = interval
    config.TOP_N           = top
    config.CAPITAL_USD     = capital

    api      = _get_api()
    universe = _get_universe()
    now      = datetime.now()
    ranked   = run_single_scan(universe, api)
    alloc    = sig.build_allocation(ranked)
    return fmt.format_table(ranked, alloc, now)


@app.get("/scan/csv")
def scan_csv(
    interval: str  = Query("FIVE_MINUTE"),
    top: int       = Query(10),
    capital: float = Query(10000),
):
    from fastapi.responses import Response
    config.CANDLE_INTERVAL = interval
    config.TOP_N           = top
    config.CAPITAL_USD     = capital

    api      = _get_api()
    universe = _get_universe()
    now      = datetime.now()
    ranked   = run_single_scan(universe, api)
    alloc    = sig.build_allocation(ranked)
    csv_data = fmt.to_csv(ranked, alloc, now)

    filename = f"signals_{now.strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
