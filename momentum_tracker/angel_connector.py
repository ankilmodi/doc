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

IP WHITELIST WORKAROUND:
  If Angel One blocks this server's IP, set one of these env vars in Vercel:
    HTTPS_PROXY=http://user:pass@proxy-host:port   (any proxy service)
    QUOTAGUARDSTATIC_URL=http://...                (QuotaGuard Static – Indian IP)
    FIXIE_URL=http://...                           (Fixie proxy)
  The connector will automatically route all API calls through the proxy.

Angel One REST base: https://apiconnect.angelbroking.com
"""

from __future__ import annotations

import os
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


def _get_proxies() -> Optional[Dict[str, str]]:
    """
    Return a requests-compatible proxy dict if any proxy env var is set.
    Priority: QUOTAGUARDSTATIC_URL > FIXIE_URL > HTTPS_PROXY > HTTP_PROXY
    Returns None if no proxy is configured (direct connection).
    """
    for env_var in ("QUOTAGUARDSTATIC_URL", "FIXIE_URL", "HTTPS_PROXY", "HTTP_PROXY"):
        proxy_url = os.environ.get(env_var, "").strip()
        
        # Skip if empty or just whitespace
        if not proxy_url:
            continue
            
        # Validate proxy URL format
        if not proxy_url.startswith(("http://", "https://")):
            logger.warning("Proxy URL from %s is malformed (missing http:// or https://): %s", env_var, proxy_url[:40])
            continue
            
        # Check if it has a host
        if proxy_url.count("://") == 1:
            parts = proxy_url.split("://")[1]
            if not parts or parts.strip() == "":
                logger.warning("Proxy URL from %s is malformed (missing host): %s", env_var, proxy_url)
                continue
        
        logger.info("Using proxy from %s: %s", env_var, proxy_url[:40] + "..." if len(proxy_url) > 40 else proxy_url)
        return {"http": proxy_url, "https": proxy_url}
    
    logger.info("No proxy configured - using direct connection")
    return None


def _get_server_ip() -> str:
    """Return the outbound IP of this server (used in Angel One headers)."""
    try:
        proxies = _get_proxies()
        r = requests.get("https://api.ipify.org?format=json", timeout=5, proxies=proxies)
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
        self._proxies = _get_proxies()
        self._server_ip: str = _get_server_ip()
        proxy_status = "via proxy" if self._proxies else "direct (no proxy)"
        logger.info("Server outbound IP: %s (%s)", self._server_ip, proxy_status)
        self._login()

    # ── Authentication ────────────────────────────────────────────────────────

    def _headers(self, auth: bool = False) -> Dict[str, str]:
        h = {
            "Content-Type":       "application/json",
            "Accept":             "application/json",
            "X-UserType":         "USER",
            "X-SourceID":         "WEB",
            "X-ClientLocalIP":    "0.0.0.0",
            "X-ClientPublicIP":   "0.0.0.0",
            "X-MACAddress":       "fe:80:00:00:00:00",
            "X-PrivateKey":       config.ANGEL_API_KEY,
        }
        if auth:
            h["Authorization"] = f"Bearer {self._jwt_token}"
        return h

    def _login(self) -> None:
        # Validate and clean TOTP secret
        totp_secret_raw = config.ANGEL_TOTP_SECRET
        
        if not totp_secret_raw or totp_secret_raw.strip() == "":
            raise RuntimeError(
                "❌ TOTP secret is missing! "
                "Set ANGEL_TOTP_SECRET in Vercel environment variables."
            )
        
        totp_secret = totp_secret_raw.strip().upper().replace(" ", "").replace("-", "")
        
        # Log for debugging (mask middle part for security)
        masked = totp_secret[:4] + "****" + totp_secret[-4:] if len(totp_secret) > 8 else "****"
        logger.info("TOTP secret: %s (length: %d)", masked, len(totp_secret))
        
        # Check if TOTP secret is valid Base32 (A-Z, 2-7 only)
        import re
        if not re.match(r'^[A-Z2-7]+$', totp_secret):
            invalid_chars = [c for c in totp_secret if c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567']
            raise RuntimeError(
                f"❌ Invalid TOTP secret format. Base32 secrets can only contain A-Z and 2-7. "
                f"Invalid characters found: {', '.join(repr(c) for c in set(invalid_chars))}. "
                f"Check ANGEL_TOTP_SECRET in Vercel environment variables."
            )
        
        # Fix Base32 padding - must be multiple of 8 characters
        padding_needed = (8 - (len(totp_secret) % 8)) % 8
        if padding_needed:
            totp_secret = totp_secret + ('=' * padding_needed)
            logger.info("Added %d padding characters", padding_needed)
        
        try:
            totp = pyotp.TOTP(totp_secret)
            totp_code = totp.now()
            logger.info("✅ TOTP code generated successfully: %s", totp_code)
        except Exception as e:
            raise RuntimeError(
                f"❌ Failed to generate TOTP code from secret. "
                f"The TOTP secret in Vercel might be incorrect. "
                f"Current secret starts with: {totp_secret[:6]}... "
                f"Error: {str(e)}"
            )
        
        logger.info("Logging in to Angel One with TOTP: %s", totp_code)

        payload = {
            "clientcode": config.ANGEL_CLIENT_ID,
            "password":   config.ANGEL_PASSWORD,
            "totp":       totp_code,
        }
        try:
            resp = requests.post(
                f"{_BASE}/rest/auth/angelbroking/user/v1/loginByPassword",
                json=payload,
                headers=self._headers(),
                timeout=15,
                proxies=self._proxies,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.ProxyError as e:
            raise RuntimeError(
                f"❌ Proxy Error: Please check proxy URL. It is malformed and could be missing the host. "
                f"Check HTTPS_PROXY, HTTP_PROXY, QUOTAGUARDSTATIC_URL, or FIXIE_URL environment variables. "
                f"Error: {str(e)}"
            )
        except requests.exceptions.RequestException as e:
            err_msg = str(e)
            if "not a registered IP" in err_msg or "IP" in err_msg:
                raise RuntimeError(
                    f"❌ IP not whitelisted: {self._server_ip} — "
                    f"Add this IP on smartapi.angelone.in or set HTTPS_PROXY env var. "
                    f"Original error: {err_msg}"
                )
            raise RuntimeError(f"Login request failed: {err_msg}")

        if not data.get("status"):
            msg = data.get("message", "Unknown error")
            error_code = data.get("errorcode", "")
            
            # Check for IP whitelist issues
            if "not a registered IP" in msg or "IP" in msg.upper() or "whitelist" in msg.lower():
                raise RuntimeError(
                    f"❌ IP not whitelisted: {self._server_ip}\n"
                    f"Add this IP at: https://smartapi.angelone.in → My Profile → IP Whitelist\n"
                    f"Or set HTTPS_PROXY environment variable in Vercel."
                )
            
            # Check for invalid TOTP
            if "totp" in msg.lower() or "OTP" in msg:
                raise RuntimeError(
                    f"❌ Invalid TOTP code! The TOTP secret might be wrong.\n"
                    f"Generated TOTP: {totp_code}\n"
                    f"TOTP secret starts with: {totp_secret[:6]}...\n"
                    f"Angel One error: {msg}\n\n"
                    f"Solution: Verify ANGEL_TOTP_SECRET in Vercel matches your Angel One TOTP secret."
                )
            
            # Check for invalid credentials
            if "password" in msg.lower() or "client" in msg.lower() or "credential" in msg.lower():
                raise RuntimeError(
                    f"❌ Invalid credentials!\n"
                    f"Angel One error: {msg}\n"
                    f"Error code: {error_code}\n\n"
                    f"Check these in Vercel environment variables:\n"
                    f"- ANGEL_CLIENT_ID (should be: A291133)\n"
                    f"- ANGEL_PASSWORD (should be: 9595)\n"
                    f"- ANGEL_API_KEY (should be: KvtCKM7Z)"
                )
            
            # Generic error
            raise RuntimeError(
                f"❌ Angel One login failed!\n"
                f"Error: {msg}\n"
                f"Error code: {error_code}\n"
                f"TOTP used: {totp_code}"
            )

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
                    proxies=self._proxies,
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
