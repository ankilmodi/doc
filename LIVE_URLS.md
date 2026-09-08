# 🌐 Live URLs - Momentum Signal Tracker

## Main Application
**🔗 https://momentum-signal-tracker.vercel.app/**

Everything is handled on one page!

---

## ✅ Working API Endpoints

### Scanner APIs (Existing - Working)
```
✅ https://momentum-signal-tracker.vercel.app/health
✅ https://momentum-signal-tracker.vercel.app/scan
✅ https://momentum-signal-tracker.vercel.app/scan?interval=FIVE_MINUTE&top=10
✅ https://momentum-signal-tracker.vercel.app/scan/table
✅ https://momentum-signal-tracker.vercel.app/scan/csv
```

### Order Management APIs (NEW - Working)
```
✅ https://momentum-signal-tracker.vercel.app/trading/mode
✅ https://momentum-signal-tracker.vercel.app/trading/stats
✅ https://momentum-signal-tracker.vercel.app/orders
✅ https://momentum-signal-tracker.vercel.app/orders/open
✅ https://momentum-signal-tracker.vercel.app/orders/history
✅ https://momentum-signal-tracker.vercel.app/positions
✅ https://momentum-signal-tracker.vercel.app/trades
✅ https://momentum-signal-tracker.vercel.app/funds
```

### POST Endpoints (Use Postman/curl)
```
POST https://momentum-signal-tracker.vercel.app/orders/place
POST https://momentum-signal-tracker.vercel.app/orders/modify
POST https://momentum-signal-tracker.vercel.app/orders/cancel
POST https://momentum-signal-tracker.vercel.app/orders/calculate-quantity
POST https://momentum-signal-tracker.vercel.app/trading/mode
```

---

## 🧪 Quick Tests

### 1. Check Health
```bash
curl https://momentum-signal-tracker.vercel.app/health
```

### 2. Get Trading Mode
```bash
curl https://momentum-signal-tracker.vercel.app/trading/mode
```
**Response:** `{"trading_mode":"PAPER","paper_capital":1000000.0}`

### 3. Get Live Signals
```bash
curl "https://momentum-signal-tracker.vercel.app/scan?interval=FIVE_MINUTE&top=10"
```

### 4. Place Test Order (PAPER Mode)
```bash
curl -X POST https://momentum-signal-tracker.vercel.app/orders/place \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "RELIANCE",
    "symboltoken": "2885",
    "transactiontype": "BUY",
    "ordertype": "MARKET",
    "producttype": "INTRADAY",
    "quantity": 10
  }'
```

### 5. Check Orders
```bash
curl https://momentum-signal-tracker.vercel.app/orders
```

### 6. Check Positions
```bash
curl https://momentum-signal-tracker.vercel.app/positions
```

---

## 📊 Current Status

- **Main Page:** ✅ https://momentum-signal-tracker.vercel.app/
- **Trading Mode:** PAPER (Safe Testing)
- **Available Funds:** ₹10,00,000
- **Backend:** ✅ All APIs Working
- **Frontend:** ⚠️ Needs UI Integration

---

## 📝 Frontend Integration Status

**Files Deployed:**
- ✅ `order-management.js` - Available at `/order-management.js`
- ✅ `order-ui-additions.html` - UI template available

**Action Needed:**
Integrate the order management UI into `index.html` by following:
`ORDER_MANAGEMENT_INTEGRATION_GUIDE.md`

---

## 🔗 Access Static Files

```
https://momentum-signal-tracker.vercel.app/order-management.js
https://momentum-signal-tracker.vercel.app/order-ui-additions.html
```

---

## ✅ Everything Working!

Your application is live with:
- ✅ Signal Scanner
- ✅ Order Management Backend
- ✅ Paper Trading Engine
- ✅ All 13 Order APIs

**All on one page:** https://momentum-signal-tracker.vercel.app/
