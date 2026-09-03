"""
angel_connector.py – Direct REST calls to the Angel One SmartConnect API.

Replaces the smartapi-python SDK entirely so there are zero C-extension
or undeclared dependencies.  Everything is plain requests + pyotp.

Angel One REST base: https://apiconnect.angelbroking.com
Docs: https://smartapi.angelbroking.com/docs
"""

from __future__ import annotations

import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pyotp
import requests

import config

logger = logging.getLogger(__name__)

_BASE = "https://apiconnect.angelbroking.com"

# ── Header templates ──────────────────────────────────────────────────────────
_COMMON_HEADERS = {
    "Content-Type":  "application/json",
    "Accept":        "application/json",
    "X-UserType":    "USER",
    "X-SourceID":    "WEB",
    "X-ClientLocalIP": "127.0.0.1",
    "X-ClientPublicIP": "127.0.0.1",
    "X-MACAddress":  "00:00:00:00:00:00",
    "X-PrivateKey":  config.ANGEL_API_KEY,
}


class AngelConnector:
    """Manages Angel One SmartConnect session and data fetching via REST."""

    _MAX_QUOTE_BATCH = 50

    def __init__(self) -> None:
        self._jwt_token:   str = ""
        self._feed_token:  str = ""
        self._refresh_token: str = ""
        self._session_expiry: datetime = datetime.min
        self._login()

    # ── Authentication ────────────────────────────────────────────────────────

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
            headers=_COMMON_HEADERS,
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

    def _auth_headers(self) -> Dict[str, str]:
        return {**_COMMON_HEADERS, "Authorization": f"Bearer {self._jwt_token}"}

    # ── Live LTP quotes ───────────────────────────────────────────────────────

    def get_ltp(self, symbol_tokens: List[str]) -> Dict[str, float]:
        """Return {token: ltp} for a list of NSE token strings."""
        self._ensure_session()
        result: Dict[str, float] = {}

        for i in range(0, len(symbol_tokens), self._MAX_QUOTE_BATCH):
            batch = symbol_tokens[i: i + self._MAX_QUOTE_BATCH]
            payload = {"mode": "LTP", "exchangeTokens": {"NSE": batch}}
            try:
                resp = requests.post(
                    f"{_BASE}/rest/secure/angelbroking/market/v1/quote/",
                    json=payload,
                    headers=self._auth_headers(),
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("status"):
                    for item in data["data"].get("fetched", []):
                        result[str(item["symbolToken"])] = float(item["ltp"])
            except Exception as exc:
                logger.error("get_ltp batch %d error: %s", i, exc)
            time.sleep(0.2)

        return result

    # ── OHLCV candle history ──────────────────────────────────────────────────

    def get_candles(
        self,
        token:     str,
        symbol:    str,
        interval:  str,
        n_candles: int = 50,
    ) -> List[Dict]:
        self._ensure_session()

        to_dt   = datetime.now()
        from_dt = to_dt - timedelta(days=max(7, n_candles // 78 + 2))

        payload = {
            "exchange":    "NSE",
            "symboltoken": token,
            "interval":    interval,
            "fromdate":    from_dt.strftime("%Y-%m-%d %H:%M"),
            "todate":      to_dt.strftime("%Y-%m-%d %H:%M"),
        }

        try:
            resp = requests.post(
                f"{_BASE}/rest/secure/angelbroking/historical/v1/getCandleData",
                json=payload,
                headers=self._auth_headers(),
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.error("get_candles %s error: %s", symbol, exc)
            return []

        if not data.get("status"):
            logger.warning("No candle data for %s: %s", symbol, data.get("message"))
            return []

        candles: List[Dict] = []
        for row in data.get("data", []):
            try:
                ts = datetime.strptime(row[0][:19], "%Y-%m-%dT%H:%M:%S")
                candles.append({
                    "timestamp": ts,
                    "open":   float(row[1]),
                    "high":   float(row[2]),
                    "low":    float(row[3]),
                    "close":  float(row[4]),
                    "volume": int(row[5]),
                })
            except (IndexError, ValueError) as exc:
                logger.debug("Skipping malformed candle row %s: %s", row, exc)

        return candles[-n_candles:]

    # ── Daily volumes for 5-day avg ───────────────────────────────────────────

    def get_daily_volumes(self, token: str, symbol: str, days: int = 5) -> List[int]:
        self._ensure_session()

        to_dt   = datetime.now()
        from_dt = to_dt - timedelta(days=days + 5)

        payload = {
            "exchange":    "NSE",
            "symboltoken": token,
            "interval":    "ONE_DAY",
            "fromdate":    from_dt.strftime("%Y-%m-%d %H:%M"),
            "todate":      to_dt.strftime("%Y-%m-%d %H:%M"),
        }

        try:
            resp = requests.post(
                f"{_BASE}/rest/secure/angelbroking/historical/v1/getCandleData",
                json=payload,
                headers=self._auth_headers(),
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.error("get_daily_volumes %s error: %s", symbol, exc)
            return []

        if not data.get("status"):
            return []

        volumes = [int(row[5]) for row in data.get("data", []) if len(row) > 5]
        return volumes[-days:]

    @property
    def feed_token(self) -> str:
        return self._feed_token
