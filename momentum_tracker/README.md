# Momentum Signal Tracker

Intraday stock momentum signal scanner for **NIFTY 50 + NIFTY 500** using the
**Angel One SmartConnect API**.  Runs entirely in a plain Python runtime – no
database, no Docker, no extra services.

---

## Features

| Feature | Detail |
|---|---|
| Live data | Angel One SmartConnect REST API |
| Universe | NIFTY 50 + NIFTY 500 (penny stocks excluded) |
| Indicators | RSI-14, EMA-9/21, Momentum (ROC-10), Volume vs. 5-day avg |
| Signal types | BUY and SELL momentum signals |
| Breakout detection | Price ≥ 20-bar high with volume spike |
| Intervals | 1-min, 5-min, 15-min (configurable) |
| Refresh | Every 100 seconds (configurable) |
| Output | Console table + optional CSV file |
| Allocation | Score-weighted capital split across top signals |
| F&O marking | Each stock tagged YES/NO for F&O eligibility |

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run (continuous mode)

```bash
python main.py
```

### 3. One-shot dry run (single scan, then exit)

```bash
python main.py --dry-run
```

### 4. Save results to CSV as well

```bash
python main.py --save-csv
```

### 5. Use 1-minute candles

```bash
python main.py --interval ONE_MINUTE
```

### 6. Full options

```
usage: main.py [-h]
               [--interval {ONE_MINUTE,FIVE_MINUTE,FIFTEEN_MINUTE,THIRTY_MINUTE,ONE_HOUR,ONE_DAY}]
               [--save-csv]
               [--dry-run]
               [--top TOP]
               [--capital CAPITAL]
               [--log-level {DEBUG,INFO,WARNING,ERROR}]
```

---

## Project Structure

```
momentum_tracker/
├── main.py             # CLI entry point
├── config.py           # All tunable parameters (thresholds, credentials, etc.)
├── angel_connector.py  # Angel One SmartConnect wrapper (login, candles, LTP)
├── symbols.py          # NIFTY 50 / NIFTY 500 symbol master with token IDs
├── indicators.py       # Pure-Python RSI, EMA, Momentum, Volume ratio, Breakout
├── signals.py          # Signal detection, scoring, ranking, trade levels
├── scanner.py          # Scan loop orchestrator
├── formatter.py        # Console table and CSV output
├── requirements.txt
└── README.md
```

---

## Output Format

### Console table (sample)

```
==========================================================================================
  MOMENTUM SIGNAL TRACKER  |  Scan time: 2025-06-15 09:35:42 IST
  Interval: FIVE_MINUTE  |  Capital: $10,000 USD  (≈ ₹840,000)
==========================================================================================
Rank  Symbol        Signal  F&O  LTP        RSI     Momentum%  VolRatio  Breakout  Score  Entry      TG1        TG2        TG3        StopLoss   TrailStop
------------------------------------------------------------------------------------------
1     RELIANCE      BUY     YES  2885.50    62.4    3.21%      2.45x     YES       87.5   2885.50    2928.79    2974.07    3029.78    2856.64    2863.86
2     TATAMOTORS    BUY     YES  845.70     59.1    2.87%      1.92x     NO        74.2   845.70     858.39     871.37     888.00     837.24     839.33
...
```

### CSV columns

`scan_time, rank, symbol, signal, fno, ltp, rsi, ema_fast, ema_slow,
momentum_pct, volume_ratio, breakout, score, entry, tg1, tg2, tg3,
stop_loss, trailing_stop, alloc_inr, alloc_usd`

---

## Configuration (`config.py`)

| Parameter | Default | Description |
|---|---|---|
| `RSI_BUY_MIN / MAX` | 55 / 75 | RSI band for BUY signal |
| `RSI_SELL_MIN / MAX` | 25 / 45 | RSI band for SELL signal |
| `VOLUME_SPIKE_MULT` | 1.5 | Minimum volume-to-5-day-avg ratio |
| `MOMENTUM_BUY_MIN` | 2.0 % | Minimum ROC for BUY |
| `MOMENTUM_SELL_MAX` | −2.0 % | Maximum ROC for SELL |
| `STOP_LOSS_PCT` | 1.0 % | Distance from entry to stop-loss |
| `TRAILING_STOP_PCT` | 0.75 % | Trailing stop offset |
| `TG1 / TG2 / TG3 _PCT` | 1.5 / 3.0 / 5.0 % | Target levels |
| `MIN_PRICE` | ₹20 | Penny-stock filter |
| `REFRESH_SECONDS` | 100 | Scan loop interval |
| `TOP_N` | 10 | Max signals in output |
| `CAPITAL_USD` | 10 000 | Allocation capital |
| `USD_TO_INR` | 84.0 | Conversion rate (update daily) |

---

## Signal Conditions

### BUY
- RSI between 55 and 75
- Fast EMA (9) > Slow EMA (21)  → bullish trend
- Momentum ROC > +2 %
- Current volume ≥ 1.5 × 5-day average
- Price ≥ ₹20

### SELL
- RSI between 25 and 45
- Fast EMA (9) < Slow EMA (21)  → bearish trend
- Momentum ROC < −2 %
- Volume spike ≥ 1.5 ×
- Price ≥ ₹20

---

## Trade Levels

| Level | BUY formula | SELL formula |
|---|---|---|
| Entry | LTP | LTP |
| Stop-Loss | Entry × 0.99 | Entry × 1.01 |
| Trailing Stop | Entry × 0.9925 | Entry × 1.0075 |
| TG1 | Entry × 1.015 | Entry × 0.985 |
| TG2 | Entry × 1.030 | Entry × 0.970 |
| TG3 | Entry × 1.050 | Entry × 0.950 |

---

## Capital Allocation Logic

Stocks are ranked by composite score (0–100).  Capital is split
**proportionally to score**, so higher-conviction signals receive larger
allocations.  The suggestion is purely indicative – always verify available
margin, lot sizes, and circuit limits before placing orders.

---

## Constraints & Limitations

- Requires a valid Angel One SmartConnect API subscription.
- Historical candle data may be throttled; the 0.3 s per-symbol pause reduces
  the risk of hitting rate limits.
- Token IDs in `symbols.py` are refreshed from Angel One's master file at
  startup; they are not persisted to disk.
- The system holds no state between restarts; every run starts fresh.
- Market hours are IST; the scan window defaults to 09:30–15:25.

---

## Disclaimer

This tool is for **educational and informational purposes only**.  It does not
constitute financial advice.  Past signal performance does not guarantee future
results.  Always conduct your own due diligence before trading.
