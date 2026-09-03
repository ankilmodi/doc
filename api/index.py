"""
api/index.py – FastAPI web server for the Momentum Signal Tracker.

Uses Market Quote FULL mode only (no historical API – avoids 403 from
non-Indian Vercel server IPs).
"""

from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "momentum_tracker"))

from fastapi import FastAPI, Query
from fastapi.responses import PlainTextResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Module-level singletons (reused across warm Vercel invocations) ───────────
_api:      Optional[AngelConnector] = None
_universe: Optional[list]           = None


def _get_api() -> AngelConnector:
    global _api
    if _api is None:
        _api = AngelConnector()
    return _api


def _get_universe() -> list:
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
        "  GET /scan/csv      → CSV download\n"
        "  GET /health        → API connectivity check\n\n"
        "Query params:\n"
        "  interval  ONE_MINUTE | FIVE_MINUTE | FIFTEEN_MINUTE  (default: FIVE_MINUTE)\n"
        "  top       max stocks in output  (default: 10)\n"
        "  capital   capital in USD        (default: 10000)\n"
    )


@app.get("/health")
def health():
    """Quick connectivity and login check."""
    try:
        api = _get_api()
        return JSONResponse({
            "status":     "ok",
            "server_ip":  api._server_ip,
            "session":    "active" if api._jwt_token else "none",
            "time_ist":   datetime.now().isoformat(),
        })
    except Exception as exc:
        return JSONResponse({"status": "error", "detail": str(exc)}, status_code=500)


@app.get("/debug")
def debug_scan(
    interval: str = Query("FIVE_MINUTE"),
    n:        int = Query(5),
):
    """
    Return raw indicator values for the first N symbols so we can see
    exactly what's failing the signal filter.
    """
    import indicators as ind
    import signals as sig
    from angel_connector import _CANDLE_CACHE

    api      = _get_api()
    universe = _get_universe()[:n]
    now      = datetime.now()

    all_quotes = api.fetch_and_cache_all(universe)
    out = []

    for sym_info in universe:
        token  = sym_info["token"]
        symbol = sym_info["symbol"]
        quote  = all_quotes.get(token, {})

        api.update_candle_cache(token, quote)

        import threading
        from angel_connector import _CACHE_LOCK
        with _CACHE_LOCK:
            from angel_connector import _CANDLE_CACHE
            candles = list(_CANDLE_CACHE.get(token, []))

        n_bars = len(candles)
        ltp    = float(quote.get("ltp", 0))
        open_p = float(quote.get("open", ltp))
        vol    = int(quote.get("tradeVolume", quote.get("volume", 0)))

        # Compute raw indicators
        rsi_val  = None
        ema_f    = None
        ema_s    = None
        mom_val  = None
        if candles:
            closes = [c["close"] for c in candles]
            rp = min(14, max(len(candles)-1, 2))
            ef = min(9,  max(len(candles)-1, 2))
            es = min(21, max(len(candles)-1, 2))
            mp = min(10, max(len(candles)-1, 2))
            from indicators import rsi_current, ema_current, momentum_current
            rsi_val = rsi_current(candles, rp)
            ema_f   = ema_current(candles, ef)
            ema_s   = ema_current(candles, es)
            mom_val = momentum_current(candles, mp)

        # Detect signal
        ind_dict = {
            "rsi": rsi_val, "ema_trend": None, "momentum": mom_val,
            "volume_ratio": None, "ltp": ltp, "open": open_p,
        }
        if ema_f and ema_s:
            ind_dict["ema_trend"] = "bullish" if ema_f > ema_s else "bearish"

        signal = sig.detect_signal(ind_dict)

        out.append({
            "symbol":      symbol,
            "token":       token,
            "n_bars":      n_bars,
            "ltp":         ltp,
            "open":        open_p,
            "volume":      vol,
            "rsi":         round(rsi_val, 2) if rsi_val is not None else None,
            "ema_fast":    round(ema_f,   2) if ema_f   is not None else None,
            "ema_slow":    round(ema_s,   2) if ema_s   is not None else None,
            "momentum":    round(mom_val, 3) if mom_val is not None else None,
            "ema_trend":   ind_dict["ema_trend"],
            "signal":      signal,
            "quote_keys":  list(quote.keys()) if quote else [],
        })

    return JSONResponse({"time": now.isoformat(), "symbols": out})


@app.get("/scan")
def scan_json(
    interval: str  = Query("FIVE_MINUTE"),
    top:      int  = Query(10),
    capital:  float= Query(10000),
    warm:     int  = Query(2, description="Extra warm-up passes to populate candle cache (0-5)"),
):
    config.CANDLE_INTERVAL = interval
    config.TOP_N           = top
    config.CAPITAL_USD     = capital

    api      = _get_api()
    universe = _get_universe()
    now      = datetime.now()

    # Warm up the candle cache with extra passes so cold-start instances
    # accumulate enough bars for meaningful indicator calculation.
    warm_passes = max(0, min(int(warm), 5))
    for _ in range(warm_passes):
        try:
            all_q = api.fetch_and_cache_all(universe)
            for sym_info in universe:
                q = all_q.get(sym_info["token"])
                if q:
                    api.update_candle_cache(sym_info["token"], q)
        except Exception:
            break

    try:
        ranked = run_single_scan(universe, api)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)

    alloc   = sig.build_allocation(ranked)
    payload = []

    for i, stock in enumerate(ranked, 1):
        lvl = stock.get("levels", {})
        payload.append({
            "rank":          i,
            "symbol":        stock["symbol"],
            "signal":        stock["signal"],
            "fno":           stock["fno"],
            "ltp":           stock["ltp"],
            "rsi":           stock.get("rsi"),
            "ema_fast":      stock.get("ema_fast"),
            "ema_slow":      stock.get("ema_slow"),
            "ema_trend":     stock.get("ema_trend"),
            "momentum_pct":  stock.get("momentum"),
            "volume_ratio":  stock.get("volume_ratio"),
            "breakout":      stock.get("breakout"),
            "score":         stock["score"],
            "entry":         lvl.get("entry"),
            "tg1":           lvl.get("tg1"),
            "tg2":           lvl.get("tg2"),
            "tg3":           lvl.get("tg3"),
            "stop_loss":     lvl.get("stop_loss"),
            "trailing_stop": lvl.get("trailing_stop"),
            "alloc_inr":     alloc.get(stock["symbol"]),
            "alloc_usd":     round(alloc.get(stock["symbol"], 0) / config.USD_TO_INR, 2),
        })

    return JSONResponse({
        "scan_time":   now.isoformat(),
        "interval":    interval,
        "warm_passes": warm_passes,
        "count":       len(ranked),
        "results":     payload,
        "note":        "No signals found – market may be closed or cache is cold. Try ?warm=3 for more warm-up passes." if not ranked else None,
    })


@app.get("/scan/table", response_class=PlainTextResponse)
def scan_table(
    interval: str  = Query("FIVE_MINUTE"),
    top:      int  = Query(10),
    capital:  float= Query(10000),
    warm:     int  = Query(2, description="Extra warm-up passes (0-5)"),
):
    config.CANDLE_INTERVAL = interval
    config.TOP_N           = top
    config.CAPITAL_USD     = capital

    api      = _get_api()
    universe = _get_universe()
    now      = datetime.now()

    warm_passes = max(0, min(int(warm), 5))
    for _ in range(warm_passes):
        try:
            all_q = api.fetch_and_cache_all(universe)
            for sym_info in universe:
                q = all_q.get(sym_info["token"])
                if q:
                    api.update_candle_cache(sym_info["token"], q)
        except Exception:
            break

    ranked   = run_single_scan(universe, api)
    alloc    = sig.build_allocation(ranked)
    return fmt.format_table(ranked, alloc, now)


@app.get("/scan/csv")
def scan_csv(
    interval: str  = Query("FIVE_MINUTE"),
    top:      int  = Query(10),
    capital:  float= Query(10000),
    warm:     int  = Query(2, description="Extra warm-up passes (0-5)"),
):
    config.CANDLE_INTERVAL = interval
    config.TOP_N           = top
    config.CAPITAL_USD     = capital

    api      = _get_api()
    universe = _get_universe()
    now      = datetime.now()

    warm_passes = max(0, min(int(warm), 5))
    for _ in range(warm_passes):
        try:
            all_q = api.fetch_and_cache_all(universe)
            for sym_info in universe:
                q = all_q.get(sym_info["token"])
                if q:
                    api.update_candle_cache(sym_info["token"], q)
        except Exception:
            break

    ranked   = run_single_scan(universe, api)
    alloc    = sig.build_allocation(ranked)
    csv_data = fmt.to_csv(ranked, alloc, now)
    filename = f"signals_{now.strftime('%Y%m%d_%H%M%S')}.csv"

    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
