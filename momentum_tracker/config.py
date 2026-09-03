"""
config.py – Central configuration for the momentum signal tracker.
All tunable parameters live here; no secrets are hard-coded in other modules.
"""

# ── Angel One API credentials ────────────────────────────────────────────────
ANGEL_API_KEY    = "KvtCKM7Z"
ANGEL_CLIENT_ID  = "A291133"
ANGEL_PASSWORD   = "9595"
ANGEL_TOTP_SECRET = "KIZ25VVZPQ2M2GQMVA6SWCRPUOO76DSS"

# ── Scan timing ──────────────────────────────────────────────────────────────
MARKET_OPEN_TIME  = "09:15"          # IST – exchange opens
SCAN_START_TIME   = "09:30"          # IST – earliest scan window
SCAN_END_TIME     = "15:25"          # IST – latest scan window
REFRESH_SECONDS   = 100              # seconds between each full scan cycle

# ── Candle intervals supported ───────────────────────────────────────────────
# Values accepted by Angel One historical API: ONE_MINUTE, FIVE_MINUTE,
# FIFTEEN_MINUTE, THIRTY_MINUTE, ONE_HOUR, ONE_DAY
CANDLE_INTERVAL   = "FIVE_MINUTE"    # default working interval

# ── Indicator parameters ─────────────────────────────────────────────────────
RSI_PERIOD        = 14
EMA_FAST          = 9
EMA_SLOW          = 21
MOMENTUM_PERIOD   = 10               # n-bar rate-of-change
VOLUME_AVG_DAYS   = 5                # how many past sessions for avg volume

# ── Signal thresholds ────────────────────────────────────────────────────────
RSI_BUY_MIN       = 55               # RSI must be above this for a buy signal
RSI_BUY_MAX       = 75               # RSI must be below this (avoid overbought)
RSI_SELL_MIN      = 25               # RSI must be below this for a sell signal
RSI_SELL_MAX      = 45

VOLUME_SPIKE_MULT = 1.5              # current volume >= 1.5× 5-day avg to qualify
BREAKOUT_MULT     = 1.0              # price >= previous high to flag as breakout

MOMENTUM_BUY_MIN  = 2.0             # % momentum (ROC) threshold for buy
MOMENTUM_SELL_MAX = -2.0            # % momentum threshold for sell

MIN_PRICE         = 20.0             # exclude stocks below this price (penny filter)
MIN_MARKET_CAP_CR = 500             # rough proxy; enforced via universe list

# ── Ranking & output ─────────────────────────────────────────────────────────
TOP_N             = 10               # max stocks in output list
CAPITAL_USD       = 10_000           # allocation capital in USD
USD_TO_INR        = 84.0             # approximate conversion; update as needed

# ── Risk / target levels (as % of entry price) ───────────────────────────────
STOP_LOSS_PCT     = 1.0              # 1 % below entry
TRAILING_STOP_PCT = 0.75             # trailing stop tightens to 0.75 % of LTP
TG1_PCT           = 1.5
TG2_PCT           = 3.0
TG3_PCT           = 5.0
