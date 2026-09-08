"""
api/index.py – FastAPI web server for the Momentum Signal Tracker.

Uses Market Quote FULL mode only (no historical API – avoids 403 from
non-Indian Vercel server IPs).
"""

from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "momentum_tracker"))

from fastapi import FastAPI, Query, Body
from fastapi.responses import PlainTextResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from typing import Optional, Dict, Any

import config
import signals as sig
import formatter as fmt
from angel_connector import AngelConnector
from symbols import refresh_tokens_from_master
from scanner import run_single_scan
from order_service import OrderService, OrderRequest

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
_order_service: Optional[OrderService] = None


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


def _get_order_service() -> OrderService:
    global _order_service
    if _order_service is None:
        api = _get_api()
        _order_service = OrderService(api, trading_mode=config.TRADING_MODE)
    return _order_service


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


# ──────────────────────────────────────────────────────────────────────────────
# AUTHENTICATION ENDPOINT
# ──────────────────────────────────────────────────────────────────────────────

@app.post("/auth/login")
def user_login(credentials: Dict[str, str] = Body(...)):
    """
    User login with their own Angel One credentials.
    
    Request body:
    {
        "client_id": "A123456",
        "password": "password",
        "api_key": "api_key",
        "totp_secret": "TOTP_SECRET"
    }
    """
    try:
        # Temporarily update config with user credentials
        config.ANGEL_CLIENT_ID = credentials.get("client_id")
        config.ANGEL_PASSWORD = credentials.get("password")
        config.ANGEL_API_KEY = credentials.get("api_key")
        config.ANGEL_TOTP_SECRET = credentials.get("totp_secret")
        
        # Force re-login with new credentials
        global _api
        _api = None
        
        # Try to get API (will trigger login)
        api = _get_api()
        
        return JSONResponse({
            "status": True,
            "message": "Login successful",
            "data": {
                "client_id": credentials.get("client_id"),
            }
        })
        
    except Exception as exc:
        logger.error(f"Login error: {exc}")
        return JSONResponse({
            "status": False,
            "message": f"Login failed: {str(exc)}",
        }, status_code=401)


@app.post("/auth/use-config-credentials")
def use_config_credentials():
    """
    Use credentials from config.py (your credentials).
    """
    try:
        # Force re-login with config credentials
        global _api
        _api = None
        
        # Try to get API (will trigger login with config credentials)
        api = _get_api()
        
        return JSONResponse({
            "status": True,
            "message": "Login successful with config credentials",
            "data": {
                "client_id": config.ANGEL_CLIENT_ID,
            }
        })
        
    except Exception as exc:
        logger.error(f"Config login error: {exc}")
        return JSONResponse({
            "status": False,
            "message": f"Login failed: {str(exc)}",
        }, status_code=401)


# ──────────────────────────────────────────────────────────────────────────────
# ORDER MANAGEMENT ENDPOINTS
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/trading/mode")
def get_trading_mode():
    """Get current trading mode (PAPER or LIVE)."""
    return JSONResponse({
        "trading_mode": config.TRADING_MODE,
        "paper_capital": config.PAPER_TRADING_CAPITAL,
    })


@app.post("/trading/mode")
def set_trading_mode(mode: Dict[str, str] = Body(...)):
    """Set trading mode to PAPER or LIVE."""
    new_mode = mode.get("mode", "PAPER").upper()
    if new_mode not in ("PAPER", "LIVE"):
        return JSONResponse({"status": False, "message": "Invalid mode. Use PAPER or LIVE"}, status_code=400)
    
    config.TRADING_MODE = new_mode
    order_service = _get_order_service()
    order_service.set_trading_mode(new_mode)
    
    logger.info(f"Trading mode set to {new_mode}")
    return JSONResponse({
        "status": True,
        "message": f"Trading mode set to {new_mode}",
        "trading_mode": new_mode,
    })


@app.post("/orders/place")
def place_order(order_data: Dict[str, Any] = Body(...)):
    """
    Place an order.
    
    Request body:
    {
        "symbol": "RELIANCE",
        "symboltoken": "2885",
        "exchange": "NSE",
        "transactiontype": "BUY",
        "ordertype": "MARKET",
        "producttype": "INTRADAY",
        "quantity": 10,
        "price": null,  // Required for LIMIT orders
        "triggerprice": null,  // Required for STOPLOSS orders
        "stop_loss": 490.0,  // Optional
        "target": 520.0  // Optional
    }
    """
    try:
        order_req = OrderRequest(
            symbol=order_data.get("symbol"),
            symboltoken=order_data.get("symboltoken"),
            exchange=order_data.get("exchange", "NSE"),
            transactiontype=order_data.get("transactiontype", "BUY"),
            ordertype=order_data.get("ordertype", "MARKET"),
            producttype=order_data.get("producttype", "INTRADAY"),
            quantity=int(order_data.get("quantity", 1)),
            price=float(order_data["price"]) if order_data.get("price") is not None else None,
            triggerprice=float(order_data["triggerprice"]) if order_data.get("triggerprice") is not None else None,
            duration=order_data.get("duration", "DAY"),
            variety=order_data.get("variety", "NORMAL"),
            stop_loss=float(order_data["stop_loss"]) if order_data.get("stop_loss") is not None else None,
            target=float(order_data["target"]) if order_data.get("target") is not None else None,
        )
        
        # Get current LTP for this symbol
        api = _get_api()
        ltp_data = api.get_ltp([order_req.symboltoken])
        current_ltp = ltp_data.get(order_req.symboltoken, 0.0)
        
        # Place order
        order_service = _get_order_service()
        result = order_service.place_order(order_req, current_ltp)
        
        return JSONResponse(result)
        
    except Exception as exc:
        logger.error(f"Order placement error: {exc}")
        return JSONResponse({
            "status": False,
            "message": f"Order placement failed: {str(exc)}",
        }, status_code=500)


@app.post("/orders/modify")
def modify_order(modify_data: Dict[str, Any] = Body(...)):
    """
    Modify an existing order.
    
    Request body:
    {
        "order_id": "PAPER1001",
        "variety": "NORMAL",
        "ordertype": "LIMIT",
        "quantity": 15,  // Optional
        "price": 505.0   // Optional
    }
    """
    try:
        order_service = _get_order_service()
        result = order_service.modify_order(
            order_id=modify_data["order_id"],
            variety=modify_data.get("variety", "NORMAL"),
            ordertype=modify_data.get("ordertype", "LIMIT"),
            quantity=int(modify_data["quantity"]) if modify_data.get("quantity") is not None else None,
            price=float(modify_data["price"]) if modify_data.get("price") is not None else None,
        )
        return JSONResponse(result)
    except Exception as exc:
        logger.error(f"Order modification error: {exc}")
        return JSONResponse({"status": False, "message": str(exc)}, status_code=500)


@app.post("/orders/cancel")
def cancel_order(cancel_data: Dict[str, Any] = Body(...)):
    """
    Cancel an order.
    
    Request body:
    {
        "order_id": "PAPER1001",
        "variety": "NORMAL"
    }
    """
    try:
        order_service = _get_order_service()
        result = order_service.cancel_order(
            order_id=cancel_data["order_id"],
            variety=cancel_data.get("variety", "NORMAL"),
        )
        return JSONResponse(result)
    except Exception as exc:
        logger.error(f"Order cancellation error: {exc}")
        return JSONResponse({"status": False, "message": str(exc)}, status_code=500)


@app.get("/orders")
def get_orders():
    """Get all orders."""
    try:
        order_service = _get_order_service()
        orders = order_service.get_order_book()
        return JSONResponse({
            "status": True,
            "data": orders,
            "count": len(orders),
        })
    except Exception as exc:
        logger.error(f"Get orders error: {exc}")
        return JSONResponse({"status": False, "message": str(exc)}, status_code=500)


@app.get("/orders/open")
def get_open_orders():
    """Get open/pending orders."""
    try:
        order_service = _get_order_service()
        orders = order_service.get_order_book()
        open_orders = [o for o in orders if o.get("status") in ("open", "pending", "trigger pending")]
        return JSONResponse({
            "status": True,
            "data": open_orders,
            "count": len(open_orders),
        })
    except Exception as exc:
        logger.error(f"Get open orders error: {exc}")
        return JSONResponse({"status": False, "message": str(exc)}, status_code=500)


@app.get("/orders/history")
def get_order_history():
    """Get order history (completed/cancelled)."""
    try:
        order_service = _get_order_service()
        orders = order_service.get_order_book()
        history = [o for o in orders if o.get("status") in ("complete", "cancelled", "rejected")]
        return JSONResponse({
            "status": True,
            "data": sorted(history, key=lambda x: x.get("updated_at", ""), reverse=True),
            "count": len(history),
        })
    except Exception as exc:
        logger.error(f"Get order history error: {exc}")
        return JSONResponse({"status": False, "message": str(exc)}, status_code=500)


@app.get("/positions")
def get_positions():
    """Get current positions."""
    try:
        order_service = _get_order_service()
        positions = order_service.get_positions()
        
        # Update LTPs for P&L calculation
        if positions and config.TRADING_MODE == "PAPER":
            api = _get_api()
            tokens = [p.get("symboltoken") for p in positions if p.get("symboltoken")]
            if tokens:
                ltp_data = api.get_ltp(tokens)
                for pos in positions:
                    token = pos.get("symboltoken")
                    if token in ltp_data:
                        pos["ltp"] = ltp_data[token]
                        # Recalculate P&L
                        if pos["quantity"] > 0:
                            pos["pnl"] = (pos["ltp"] - pos["buy_avg_price"]) * pos["quantity"]
                        elif pos["quantity"] < 0:
                            pos["pnl"] = (pos["sell_avg_price"] - pos["ltp"]) * abs(pos["quantity"])
        
        return JSONResponse({
            "status": True,
            "data": positions,
            "count": len(positions),
        })
    except Exception as exc:
        logger.error(f"Get positions error: {exc}")
        return JSONResponse({"status": False, "message": str(exc)}, status_code=500)


@app.get("/trades")
def get_trades():
    """Get trade book (executed trades)."""
    try:
        order_service = _get_order_service()
        trades = order_service.get_trade_book()
        return JSONResponse({
            "status": True,
            "data": trades,
            "count": len(trades),
        })
    except Exception as exc:
        logger.error(f"Get trades error: {exc}")
        return JSONResponse({"status": False, "message": str(exc)}, status_code=500)


@app.get("/funds")
def get_funds():
    """Get available funds and margin info."""
    try:
        order_service = _get_order_service()
        funds = order_service.get_rms_limits()
        
        return JSONResponse({
            "status": True,
            "data": funds,
            "trading_mode": config.TRADING_MODE,
        })
    except Exception as exc:
        logger.error(f"Get funds error: {exc}")
        return JSONResponse({"status": False, "message": str(exc)}, status_code=500)


@app.post("/orders/calculate-quantity")
def calculate_quantity(calc_data: Dict[str, Any] = Body(...)):
    """
    Calculate recommended quantity based on risk management.
    
    Request body:
    {
        "capital": 100000,
        "risk_pct": 1.0,
        "entry_price": 500.0,
        "stop_loss_price": 490.0
    }
    """
    try:
        order_service = _get_order_service()
        quantity = order_service.calculate_position_size(
            capital=float(calc_data["capital"]),
            risk_pct=float(calc_data.get("risk_pct", 1.0)),
            entry_price=float(calc_data["entry_price"]),
            stop_loss_price=float(calc_data["stop_loss_price"]),
        )
        
        risk_per_share = abs(float(calc_data["entry_price"]) - float(calc_data["stop_loss_price"]))
        total_risk = risk_per_share * quantity
        position_value = float(calc_data["entry_price"]) * quantity
        
        return JSONResponse({
            "status": True,
            "data": {
                "recommended_quantity": quantity,
                "risk_per_share": round(risk_per_share, 2),
                "total_risk": round(total_risk, 2),
                "position_value": round(position_value, 2),
                "risk_pct": round((total_risk / float(calc_data["capital"])) * 100, 2),
            }
        })
    except Exception as exc:
        logger.error(f"Calculate quantity error: {exc}")
        return JSONResponse({"status": False, "message": str(exc)}, status_code=500)


@app.get("/trading/stats")
def get_trading_stats():
    """Get trading statistics."""
    try:
        order_service = _get_order_service()
        
        positions = order_service.get_positions()
        funds = order_service.get_rms_limits()
        orders = order_service.get_order_book()
        
        open_positions = len(positions)
        open_orders = len([o for o in orders if o.get("status") in ("open", "pending", "trigger pending")])
        completed_orders = len([o for o in orders if o.get("status") == "complete"])
        
        # Calculate today's P&L
        todays_pnl = sum(p.get("pnl", 0) for p in positions)
        
        return JSONResponse({
            "status": True,
            "data": {
                "available_funds": funds.get("availablecash", 0),
                "used_margin": funds.get("utiliseddebits", 0),
                "open_positions": open_positions,
                "todays_pnl": round(todays_pnl, 2),
                "open_orders": open_orders,
                "completed_orders": completed_orders,
                "trading_mode": config.TRADING_MODE,
            }
        })
    except Exception as exc:
        logger.error(f"Get trading stats error: {exc}")
        return JSONResponse({"status": False, "message": str(exc)}, status_code=500)
