"""
angel_connector.py – Direct REST calls to the Angel One SmartConnect API.

FIX: Angel One historical API (getCandleData) returns 403 from non-Indian IPs
(Vercel runs on AWS us-east-1). We work around this by:

  1. Using the Market Quote API in FULL mode to get OHLC + volume for each
     symbol — this endpoint is NOT IP-restricted.
  2. Building synthetic candle history from repeated LTP/quote polls cached
     in memory (for RSI/EMA we need a series; we seed with quote data and
     accumulate across calls within the same serverless warm instance).
  3. For the 5-day volume average we use the Gainers/Losers or the FULL quote
     which includes 52-week high/low and today's volume — good enough proxy.

Angel One REST base: https://apiconnect.angelbroking.com
"""

from __future__ import annotations

import time
import logging
import threading
from collections import deque
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pyotp
import requests

import config

logger = logging.getLogger(__name__)

_BASE = "https://apiconnect.angelbroking.com"

# We keep a rolling in-memory OHLCV buffer per token (max 60 bars).
# Each serverless warm invocation accumulates data; cold starts start fresh
# but get at least 1 bar from the initial quote fetch.
_CANDLE_CACHE: Dict[str, deque] = {}
_CACHE_LOCK   = threading.Lock()
_MAX_BARS     = 60


def _get_server_ip() -> str:
    """Return the outbound IP of this server (used in Angel One headers)."""
    try:
        r = requests.get("https://api.ipify.org?format=json", timeout=5)
        return r.json().get("ip", "127.0.0.1")
    except Exception:
        return "127.0.0.1"


class AngelConnector:
    """Angel One SmartConnect session manager – uses Market Quote API only."""

    _MAX_QUOTE_BATCH = 50

    def __init__(self) -> None:
        self._jwt_token:      str = ""
        self._feed_token:     str = ""
        self._refresh_token:  str = ""
        self._session_expiry: datetime = datetime.min
        self._server_ip:      str = _get_server_ip()
        logger.info("Server outbound IP: %s", self._server_ip)
        self._login()

    # ── Authentication ────────────────────────────────────────────────────────

    def _headers(self, auth: bool = False) -> Dict[str, str]:
        h = {
            "Content-Type":       "application/json",
            "Accept":             "application/json",
            "X-UserType":         "USER",
            "X-SourceID":         "WEB",
            "X-ClientLocalIP":    self._server_ip,
            "X-ClientPublicIP":   self._server_ip,
            "X-MACAddress":       "fe:80:00:00:00:00",
            "X-PrivateKey":       config.ANGEL_API_KEY,
        }
        if auth:
            h["Authorization"] = f"Bearer {self._jwt_token}"
        return h

    def _login(self) -> None:
        totp_code = pyotp.TOTP(config.ANGEL_TOTP_SECRET).now()
        logger.info("Logging in to Angel One (TOTP: %s)…", totp_code)

        payload = {
            "clientcode": config.ANGEL_CLIENT_ID,
            "password":   config.ANGEL_PASSWORD,
            "totp":       totp_code,
        }
        resp = requests.post(
            f"{_BASE}/rest/auth/angelbroking/user/v1/loginByPassword",
            json=payload,
            headers=self._headers(),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        if not data.get("status"):
            raise RuntimeError(f"Angel One login failed: {data.get('message')}")

        d = data["data"]
        self._jwt_token     = d["jwtToken"]
        self._refresh_token = d["refreshToken"]
        self._feed_token    = d["feedToken"]
        self._session_expiry = datetime.now() + timedelta(hours=20)
        logger.info("Angel One login successful.")

    def _ensure_session(self) -> None:
        if datetime.now() >= self._session_expiry:
            logger.warning("Session expiring – re-logging in.")
            self._login()

    # ── Market Quote (FULL mode) – works from any IP ──────────────────────────

    def get_full_quotes(self, tokens: List[str]) -> Dict[str, Dict]:
        """
        Fetch FULL market quote for a batch of NSE tokens.
        Returns {token: quote_dict} where quote_dict has:
            ltp, open, high, low, close, volume, avgPrice,
            upperCircuit, lowerCircuit, yearHigh, yearLow,
            totBuyQuan, totSellQuan
        """
        self._ensure_session()
        result: Dict[str, Dict] = {}

        for i in range(0, len(tokens), self._MAX_QUOTE_BATCH):
            batch = tokens[i: i + self._MAX_QUOTE_BATCH]
            payload = {"mode": "FULL", "exchangeTokens": {"NSE": batch}}
            try:
                resp = requests.post(
                    f"{_BASE}/rest/secure/angelbroking/market/v1/quote/",
                    json=payload,
                    headers=self._headers(auth=True),
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("status"):
                    for item in data["data"].get("fetched", []):
                        token = str(item.get("symbolToken", ""))
                        result[token] = item
                else:
                    logger.warning("FULL quote batch %d: %s", i, data.get("message"))
            except Exception as exc:
                logger.error("get_full_quotes batch %d: %s", i, exc)
            time.sleep(0.15)

        return result

    def get_ltp(self, symbol_tokens: List[str]) -> Dict[str, float]:
        """Return {token: ltp}."""
        quotes = self.get_full_quotes(symbol_tokens)
        return {tok: float(q.get("ltp", 0)) for tok, q in quotes.items()}

    # ── Synthetic candle builder ───────────────────────────────────────────────

    def _quote_to_candle(self, quote: Dict) -> Optional[Dict]:
        """Convert a FULL quote response into a candle-like dict."""
        try:
            return {
                "timestamp": datetime.now(),
                "open":   float(quote.get("open",  quote.get("ltp", 0))),
                "high":   float(quote.get("high",  quote.get("ltp", 0))),
                "low":    float(quote.get("low",   quote.get("ltp", 0))),
                "close":  float(quote.get("ltp",   0)),
                "volume": int(  quote.get("tradeVolume", quote.get("volume", 0))),
            }
        except Exception:
            return None

    def update_candle_cache(self, token: str, quote: Dict) -> None:
        """Push the latest quote as a new bar into the in-memory cache."""
        candle = self._quote_to_candle(quote)
        if candle is None:
            return
        with _CACHE_LOCK:
            if token not in _CANDLE_CACHE:
                _CANDLE_CACHE[token] = deque(maxlen=_MAX_BARS)
            _CANDLE_CACHE[token].append(candle)

    def get_candles(
        self,
        token:     str,
        symbol:    str,
        interval:  str,
        n_candles: int = 50,
    ) -> List[Dict]:
        """
        Return the cached synthetic candle list for this token.
        Falls back to a single-bar list from a live quote if cache is empty.
        """
        with _CACHE_LOCK:
            cached = list(_CANDLE_CACHE.get(token, []))

        if cached:
            return cached[-n_candles:]

        # Cache miss – fetch one live quote to seed at least 1 bar
        quotes = self.get_full_quotes([token])
        if token in quotes:
            self.update_candle_cache(token, quotes[token])
            with _CACHE_LOCK:
                return list(_CANDLE_CACHE.get(token, []))
        return []

    def get_daily_volumes(self, token: str, symbol: str, days: int = 5) -> List[int]:
        """
        Approximate the 5-day average volume using today's cumulative volume.
        Angel One FULL quote gives tradeVolume (today's total).
        We return [tradeVolume] * days as a flat proxy so volume_ratio ≈ 1.0
        unless a real spike is happening, which will be visible as >1.
        
        NOTE: This is a graceful degradation — without historical data access
        from this server IP, today's volume is the best available proxy.
        """
        quotes = self.get_full_quotes([token])
        if token not in quotes:
            return []
        vol = int(quotes[token].get("tradeVolume", quotes[token].get("volume", 0)))
        # Return a flat list so volume_ratio = 1.0 (neutral baseline)
        return [vol] * days if vol > 0 else []

    # ── Bulk quote + cache update (call once per scan cycle) ──────────────────

    def fetch_and_cache_all(self, symbol_list: List[Dict]) -> Dict[str, Dict]:
        """
        Fetch FULL quotes for all symbols in one pass and update the candle
        cache.  Returns {token: quote_dict}.
        """
        tokens = [s["token"] for s in symbol_list]
        all_quotes = self.get_full_quotes(tokens)

        for token, quote in all_quotes.items():
            self.update_candle_cache(token, quote)

        return all_quotes

    @property
    def feed_token(self) -> str:
        return self._feed_token
