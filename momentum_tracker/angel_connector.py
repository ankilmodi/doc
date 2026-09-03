"""
angel_connector.py – Thin wrapper around the SmartApi (Angel One) SDK.

Responsibilities:
  • Login with TOTP and obtain a JWT session.
  • Re-login automatically when the session expires.
  • Fetch live LTP quotes for a batch of tokens.
  • Fetch OHLCV candle history for indicator calculations.
  • Provide a clean interface so other modules never import smartapi directly.

Dependencies (pure Python + smartapi-python):
    pip install smartapi-python pyotp requests
"""

from __future__ import annotations

import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pyotp
from SmartApi import SmartConnect   # pip install smartapi-python

import config

logger = logging.getLogger(__name__)


class AngelConnector:
    """Manages the Angel One SmartConnect session and data fetching."""

    _EXCHANGE = "NSE"                         # we only track NSE equities
    _MAX_QUOTE_BATCH = 50                     # API limit per call

    def __init__(self) -> None:
        self._api: Optional[SmartConnect] = None
        self._auth_token: str = ""
        self._feed_token: str = ""
        self._session_expiry: datetime = datetime.min
        self._login()

    # ── Authentication ────────────────────────────────────────────────────────

    def _login(self) -> None:
        """Login to Angel One and cache the session tokens."""
        logger.info("Logging in to Angel One…")
        totp_code = pyotp.TOTP(config.ANGEL_TOTP_SECRET).now()

        api = SmartConnect(api_key=config.ANGEL_API_KEY)
        data = api.generateSession(
            clientCode=config.ANGEL_CLIENT_ID,
            password=config.ANGEL_PASSWORD,
            totp=totp_code,
        )

        if not data or data.get("status") is False:
            raise RuntimeError(f"Angel One login failed: {data}")

        self._api = api
        self._auth_token = data["data"]["jwtToken"]
        self._feed_token = data["data"]["feedToken"]
        # Sessions last ~1 day; refresh proactively after 20 h
        self._session_expiry = datetime.now() + timedelta(hours=20)
        logger.info("Angel One login successful.")

    def _ensure_session(self) -> None:
        """Re-login if the session is about to expire."""
        if datetime.now() >= self._session_expiry:
            logger.warning("Session expiring – re-logging in.")
            self._login()

    # ── Live quotes ───────────────────────────────────────────────────────────

    def get_ltp(self, symbol_tokens: List[str]) -> Dict[str, float]:
        """
        Return {token: ltp} for the supplied list of NSE token strings.
        Batches requests to stay within the API's per-call limit.
        """
        self._ensure_session()
        result: Dict[str, float] = {}

        for i in range(0, len(symbol_tokens), self._MAX_QUOTE_BATCH):
            batch = symbol_tokens[i : i + self._MAX_QUOTE_BATCH]
            exchange_tokens = {self._EXCHANGE: batch}
            try:
                resp = self._api.getMarketData("LTP", exchange_tokens)
                if resp and resp.get("status"):
                    for item in resp["data"].get("fetched", []):
                        token = str(item["symbolToken"])
                        ltp   = float(item["ltp"])
                        result[token] = ltp
            except Exception as exc:
                logger.error("getMarketData error (batch %d): %s", i, exc)
            time.sleep(0.2)   # polite rate-limiting

        return result

    # ── OHLCV candle history ──────────────────────────────────────────────────

    def get_candles(
        self,
        token: str,
        symbol: str,
        interval: str,
        n_candles: int = 50,
    ) -> List[Dict]:
        """
        Fetch the last *n_candles* OHLCV candles for one symbol.

        Returns a list of dicts:
            [{"timestamp": datetime, "open": f, "high": f,
              "low": f, "close": f, "volume": int}, …]
        """
        self._ensure_session()

        # Angel One requires explicit from/to timestamps
        to_dt   = datetime.now()
        # Fetch more days to cover weekends / holidays when requesting daily bars
        from_dt = to_dt - timedelta(days=max(7, n_candles // 78 + 2))

        params = {
            "exchange":    self._EXCHANGE,
            "symboltoken": token,
            "interval":    interval,
            "fromdate":    from_dt.strftime("%Y-%m-%d %H:%M"),
            "todate":      to_dt.strftime("%Y-%m-%d %H:%M"),
        }

        try:
            resp = self._api.getCandleData(params)
        except Exception as exc:
            logger.error("getCandleData error for %s: %s", symbol, exc)
            return []

        if not resp or not resp.get("status"):
            logger.warning("No candle data for %s: %s", symbol, resp)
            return []

        candles: List[Dict] = []
        for row in resp["data"]:
            # row format: [timestamp_str, open, high, low, close, volume]
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

        # Return only the most recent n_candles
        return candles[-n_candles:]

    # ── Bulk historical volumes (for 5-day avg volume) ────────────────────────

    def get_daily_volumes(self, token: str, symbol: str, days: int = 5) -> List[int]:
        """
        Return a list of the last *days* session-total volumes (oldest→newest),
        fetched via ONE_DAY candles.
        """
        self._ensure_session()
        to_dt   = datetime.now()
        from_dt = to_dt - timedelta(days=days + 5)   # buffer for holidays

        params = {
            "exchange":    self._EXCHANGE,
            "symboltoken": token,
            "interval":    "ONE_DAY",
            "fromdate":    from_dt.strftime("%Y-%m-%d %H:%M"),
            "todate":      to_dt.strftime("%Y-%m-%d %H:%M"),
        }

        try:
            resp = self._api.getCandleData(params)
        except Exception as exc:
            logger.error("get_daily_volumes error for %s: %s", symbol, exc)
            return []

        if not resp or not resp.get("status"):
            return []

        volumes = [int(row[5]) for row in resp["data"] if len(row) > 5]
        return volumes[-days:]   # last *days* sessions

    @property
    def feed_token(self) -> str:
        return self._feed_token
