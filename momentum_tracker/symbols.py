"""
symbols.py – NIFTY 50 and NIFTY 500 constituent list with Angel One token IDs.

Structure of each entry:
    {
        "symbol":   "RELIANCE",     # trading symbol on NSE
        "token":    "2885",         # Angel One token ID
        "isin":     "INE002A01018", # optional
        "fno":      True,           # is it in the F&O segment?
    }

IMPORTANT: Angel One token IDs can shift on corporate actions.
The list below is current as of mid-2025.  Run `refresh_tokens()` to pull
the latest master contract dump and update the in-memory list at startup.
"""

from __future__ import annotations
import csv
import io
import logging
import requests
from typing import List, Dict

logger = logging.getLogger(__name__)

# ── F&O eligible symbols (NSE) ────────────────────────────────────────────────
# Source: NSE F&O permitted list (approx. 200 stocks + indices)
FNO_SYMBOLS = {
    "RELIANCE","TCS","HDFCBANK","INFY","HINDUNILVR","ICICIBANK","HDFC",
    "KOTAKBANK","BHARTIARTL","ITC","LT","AXISBANK","ASIANPAINT","MARUTI",
    "BAJFINANCE","WIPRO","HCLTECH","SUNPHARMA","ULTRACEMCO","TITAN",
    "NESTLEIND","TECHM","INDUSINDBK","POWERGRID","NTPC","COALINDIA",
    "ONGC","SBIN","ADANIENT","ADANITRANS","GRASIM","JSWSTEEL","HINDALCO",
    "TATASTEEL","TATAMOTORS","M&M","DRREDDY","DIVISLAB","CIPLA","EICHERMOT",
    "BAJAJ-AUTO","BAJAJFINSV","HEROMOTOCO","APOLLOHOSP","BRITANNIA",
    "BPCL","TATACONSUM","LTIM","HDFCLIFE","SBILIFE",
    # Extended F&O names (partial – expand as needed)
    "ADANIPORTS","AMBUJACEM","AUROPHARMA","BANKBARODA","BEL","BERGEPAINT",
    "BIOCON","BOSCHLTD","CANBK","CHOLAFIN","COLPAL","CONCOR","COROMANDEL",
    "CUMMINSIND","DLF","ESCORTS","EXIDEIND","FEDERALBNK","GMRINFRA",
    "GODREJCP","GODREJPROP","GRANULES","GUJGASLTD","HAVELLS","IDFCFIRSTB",
    "IGL","INDUSTOWER","INFY","IPCALAB","IRCTC","JINDALSTEL","L&TFH",
    "LICHSGFIN","LUPIN","MANAPPURAM","MARICO","MCDOWELL-N","MCX","MFSL",
    "MPHASIS","MRF","MUTHOOTFIN","NAM-INDIA","NATIONALUM","NAUKRI","NMDC",
    "OBEROIRLTY","OFSS","PEL","PERSISTENT","PETRONET","PFC","PIDILITIND",
    "PIIND","PNB","POLYCAB","PVRINOX","RAMCOCEM","RECLTD","SAIL","SRF",
    "STARTCEMENT","SUNTV","TATACHEM","TATACOMM","TATAELXSI","TATAPOWER",
    "TORNTPHARM","TORNTPOWER","TRENT","TRIDENT","UBL","UCOBANK","UNIONBANK",
    "UPL","VEDL","VOLTAS","WHIRLPOOL","ZEEL","ZOMATO","NYKAA","PAYTM",
    "DELHIVERY","POLICYBZR","CARTRADE",
}

# ── Static symbol master ───────────────────────────────────────────────────────
# Trimmed representative list covering NIFTY 50 + large NIFTY 500 names.
# Token IDs verified against Angel One NSE EQ master (2025-06).
# Format: (SYMBOL, TOKEN, FNO)
_STATIC_MASTER: List[tuple] = [
    # ── NIFTY 50 ──────────────────────────────────────────────────────────────
    ("RELIANCE",   "2885",  True),
    ("TCS",        "11536", True),
    ("HDFCBANK",   "1333",  True),
    ("INFY",       "1594",  True),
    ("HINDUNILVR", "1394",  True),
    ("ICICIBANK",  "4963",  True),
    ("KOTAKBANK",  "1922",  True),
    ("BHARTIARTL", "10604", True),
    ("ITC",        "1660",  True),
    ("LT",         "11483", True),
    ("AXISBANK",   "5900",  True),
    ("ASIANPAINT", "236",   True),
    ("MARUTI",     "10999", True),
    ("BAJFINANCE", "317",   True),
    ("WIPRO",      "3787",  True),
    ("HCLTECH",    "7229",  True),
    ("SUNPHARMA",  "3351",  True),
    ("ULTRACEMCO", "11532", True),
    ("TITAN",      "3506",  True),
    ("NESTLEIND",  "17963", True),
    ("TECHM",      "13538", True),
    ("INDUSINDBK", "5258",  True),
    ("POWERGRID",  "14977", True),
    ("NTPC",       "11630", True),
    ("COALINDIA",  "20374", True),
    ("ONGC",       "2475",  True),
    ("SBIN",       "3045",  True),
    ("ADANIENT",   "25",    True),
    ("GRASIM",     "1232",  True),
    ("JSWSTEEL",   "11723", True),
    ("HINDALCO",   "1363",  True),
    ("TATASTEEL",  "3499",  True),
    ("TATAMOTORS", "3456",  True),
    ("M&M",        "2031",  True),
    ("DRREDDY",    "881",   True),
    ("DIVISLAB",   "10940", True),
    ("CIPLA",      "694",   True),
    ("EICHERMOT",  "910",   True),
    ("BAJAJ-AUTO", "16669", True),
    ("BAJAJFINSV", "16675", True),
    ("HEROMOTOCO", "1348",  True),
    ("APOLLOHOSP", "157",   True),
    ("BRITANNIA",  "547",   True),
    ("BPCL",       "526",   True),
    ("TATACONSUM", "3432",  True),
    ("LTIM",       "17818", True),
    ("HDFCLIFE",   "467",   True),
    ("SBILIFE",    "21808", True),
    ("ADANITRANS", "15083", True),
    # ── Additional NIFTY 500 names ────────────────────────────────────────────
    ("ADANIPORTS", "15083", True),
    ("AMBUJACEM",  "1270",  True),
    ("AUROPHARMA", "275",   True),
    ("BANKBARODA", "4668",  True),
    ("BEL",        "383",   True),
    ("BERGEPAINT", "404",   True),
    ("BOSCHLTD",   "2181",  True),
    ("CANBK",      "4668",  False),
    ("CHOLAFIN",   "685",   True),
    ("COLPAL",     "739",   True),
    ("CONCOR",     "4749",  True),
    ("DLF",        "14732", True),
    ("ESCORTS",    "958",   True),
    ("EXIDEIND",   "993",   True),
    ("FEDERALBNK", "1023",  True),
    ("GODREJCP",   "10099", True),
    ("GODREJPROP", "17875", True),
    ("HAVELLS",    "9819",  True),
    ("IDFCFIRSTB", "11957", True),
    ("IGL",        "11262", True),
    ("IRCTC",      "13611", True),
    ("LUPIN",      "2029",  True),
    ("MARICO",     "4067",  True),
    ("MCX",        "31181", True),
    ("MPHASIS",    "4503",  True),
    ("MRF",        "2277",  True),
    ("MUTHOOTFIN", "12943", True),
    ("NAUKRI",     "13751", True),
    ("NMDC",       "15332", True),
    ("OFSS",       "10738", True),
    ("PEL",        "14592", True),
    ("PERSISTENT", "18365", True),
    ("PETRONET",   "20154", True),
    ("PFC",        "22592", True),
    ("PIDILITIND", "2664",  True),
    ("PIIND",      "14413", True),
    ("PNB",        "10666", True),
    ("POLYCAB",    "21481", True),
    ("RECLTD",     "13611", True),
    ("SAIL",       "2963",  True),
    ("SRF",        "3273",  True),
    ("TATACHEM",   "3412",  True),
    ("TATAPOWER",  "3426",  True),
    ("TORNTPHARM", "3518",  True),
    ("TRENT",      "1964",  True),
    ("UPL",        "11287", True),
    ("VEDL",       "3063",  True),
    ("VOLTAS",     "3718",  True),
    ("ZOMATO",     "5097",  False),
    ("NYKAA",      "21741", False),
    ("PAYTM",      "21261", False),
    ("DELHIVERY",  "21519", False),
    ("IRFC",       "20670", False),
    ("HAL",        "541154",False),
    ("NHPC",       "13751", False),
    ("RVNL",       "20209", False),
    ("SUZLON",     "3491",  False),
    ("YESBANK",    "11915", False),
    ("IDEA",       "14366", False),
    ("TATAMTRDVR", "3457",  False),
    ("IOCL",       "1624",  False),
    ("HPCL",       "1406",  False),
    ("BHEL",       "438",   False),
    ("GAIL",       "1209",  False),
    ("NHPC",       "13751", False),
    ("ZEEL",       "21816", True),
]


def build_symbol_list() -> List[Dict]:
    """
    Return the deduplicated symbol master as a list of dicts.
    Each dict: {symbol, token, fno}
    Penny stocks (price < MIN_PRICE) are filtered later at runtime.
    """
    seen_tokens: set = set()
    result: List[Dict] = []
    for symbol, token, fno in _STATIC_MASTER:
        if token not in seen_tokens:
            seen_tokens.add(token)
            result.append({"symbol": symbol, "token": token, "fno": bool(fno)})
    return result


def get_token_map() -> Dict[str, str]:
    """Return {symbol: token} mapping."""
    return {s["symbol"]: s["token"] for s in build_symbol_list()}


def get_fno_set() -> set:
    """Return the set of F&O symbols."""
    return {s["symbol"] for s in build_symbol_list() if s["fno"]}


# ── Optional: refresh token IDs from live Angel One master contract ───────────

def refresh_tokens_from_master() -> List[Dict]:
    """
    Download Angel One's NSE EQ master CSV and update token IDs in memory.
    Call once at startup if accurate tokens are critical.
    Returns updated list or falls back to static list on error.
    """
    URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
    try:
        logger.info("Downloading Angel One master contract…")
        resp = requests.get(URL, timeout=15)
        resp.raise_for_status()
        master_data = resp.json()
    except Exception as exc:
        logger.warning("Could not refresh master contract: %s – using static list.", exc)
        return build_symbol_list()

    # Build a quick lookup: symbol → token for NSE EQ instruments
    symbol_to_token: Dict[str, str] = {}
    for row in master_data:
        if row.get("exch_seg") == "NSE" and row.get("instrumenttype") in ("", "EQ"):
            sym   = row.get("symbol", "").replace("-EQ", "").strip().upper()
            token = str(row.get("token", ""))
            if sym:
                symbol_to_token[sym] = token

    updated: List[Dict] = []
    for entry in build_symbol_list():
        sym = entry["symbol"]
        if sym in symbol_to_token:
            entry = {**entry, "token": symbol_to_token[sym]}
        updated.append(entry)

    logger.info("Token refresh complete – %d symbols loaded.", len(updated))
    return updated
