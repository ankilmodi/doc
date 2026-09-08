# Angel One Order Management - Integration Guide

## 🎯 Overview

This guide explains how to integrate the complete Angel One order management system into your Momentum Signal Tracker application.

## ✅ Completed Backend Implementation

The following backend components are **already implemented and ready to use**:

### 1. **order_service.py**
- `OrderRequest` dataclass for order parameters
- `PaperTradingEngine` for safe testing without real money
- `OrderService` class with methods for:
  - `place_order()` - Place market/limit/stop-loss orders
  - `modify_order()` - Modify existing orders
  - `cancel_order()` - Cancel orders
  - `get_order_book()` - Fetch all orders
  - `get_positions()` - Fetch current positions
  - `get_trade_book()` - Fetch executed trades
  - `get_rms_limits()` - Fetch funds and margin info
  - `calculate_position_size()` - Risk-based quantity calculator

### 2. **config.py** (Enhanced)
Added order management settings:
```python
TRADING_MODE = "PAPER"  # PAPER or LIVE
PAPER_TRADING_CAPITAL = 1_000_000.0
DEFAULT_RISK_PER_TRADE_PCT = 1.0
MAX_POSITION_SIZE_PCT = 20.0
MAX_OPEN_POSITIONS = 5
```

### 3. **api/index.py** (Enhanced)
Added 13 new API endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/trading/mode` | GET | Get current trading mode |
| `/trading/mode` | POST | Switch PAPER/LIVE mode |
| `/orders/place` | POST | Place order |
| `/orders/modify` | POST | Modify order |
| `/orders/cancel` | POST | Cancel order |
| `/orders` | GET | Get all orders |
| `/orders/open` | GET | Get open orders |
| `/orders/history` | GET | Get order history |
| `/positions` | GET | Get positions with P&L |
| `/trades` | GET | Get trade book |
| `/funds` | GET | Get available funds |
| `/orders/calculate-quantity` | POST | Calculate recommended quantity |
| `/trading/stats` | GET | Get dashboard statistics |

## 📁 Files Created

```
momentum_tracker/
├── order_service.py          ✅ NEW - Core order management logic
└── config.py                 ✅ UPDATED - Added order settings

api/
└── index.py                  ✅ UPDATED - Added order endpoints

public/
├── order-management.js       ✅ NEW - Frontend order management module
└── order-ui-additions.html   ✅ NEW - UI components to add

.env.example                  ✅ NEW - Credential template
.gitignore                    ✅ UPDATED - Security protection
```

## 🔧 Frontend Integration Steps

### Step 1: Add Order Management JavaScript

Add this line **before `</body>`** in `public/index.html`:

```html
<script src="order-management.js"></script>
```

### Step 2: Add CSS Styles

Open `public/order-ui-additions.html` and copy the styles from **Section 1** into your `<style>` section in `index.html`.

### Step 3: Add Trading Mode Toggle to Header

In your header's `.header-right` div, add:

```html
<div class="status-pill">
  <span>Mode:</span>
  <span class="tag tag-fno" id="trading-mode-badge">PAPER</span>
  <label class="toggle-switch">
    <input type="checkbox" id="trading-mode-toggle">
    <span class="toggle-slider"></span>
  </label>
</div>
```

### Step 4: Add Trading Dashboard Stats

After your existing stats row, add:

```html
<div class="section-header" style="margin-top:24px">
  <span class="section-title">💼 Trading Dashboard</span>
</div>
<div class="stats-row">
  <div class="stat-card">
    <div class="label">Available Funds</div>
    <div class="value blue" id="stat-funds">—</div>
    <div class="sub">available cash</div>
  </div>
  <div class="stat-card">
    <div class="label">Used Margin</div>
    <div class="value yellow" id="stat-margin">—</div>
    <div class="sub">margin utilized</div>
  </div>
  <div class="stat-card">
    <div class="label">Open Positions</div>
    <div class="value" style="color:var(--purple)" id="stat-positions">—</div>
    <div class="sub">active positions</div>
  </div>
  <div class="stat-card">
    <div class="label">Today's P&L</div>
    <div class="value" id="stat-pnl">—</div>
    <div class="sub">profit & loss</div>
  </div>
</div>
```

### Step 5: Add Order Buttons to Signals Table

In your signals table `<thead>`, add a new column:

```html
<th>Actions</th>
```

In your `renderData()` function, add this as the last `<td>` in each row:

```javascript
<td>
  <button class="order-btn" onclick='OrderManagement.openOrderModal(${JSON.stringify(r)}, "MARKET")'>
    ${isBuy ? '🟢 BUY' : '🔴 SELL'} MKT
  </button>
  <button class="order-btn" onclick='OrderManagement.openOrderModal(${JSON.stringify(r)}, "LIMIT")'>
    ${isBuy ? 'BUY' : 'SELL'} LMT
  </button>
</td>
```

### Step 6: Add Order Management Section

After your signals table and allocation section, add the complete order management UI from **Section 5** of `order-ui-additions.html`.

### Step 7: Add Order Modal

Before `</body>`, add the order modal from **Section 6** of `order-ui-additions.html`.

## 🧪 Testing

### Test in PAPER Mode (Safe - No Real Orders)

1. **Start your backend:**
   ```powershell
   cd C:\xampp\htdocs\doc
   python -m uvicorn api.index:app --reload --port 8000
   ```

2. **Open the application:**
   ```
   http://localhost:8000/public/index.html
   ```

3. **Verify PAPER mode:**
   - Check that the toggle shows "PAPER"
   - The badge should be purple/blue, NOT red

4. **Test order placement:**
   - Click "Start Scan" to generate signals
   - Click "BUY MKT" on any signal
   - Fill in quantity
   - Click "Place Order"
   - Check "Open Orders" or "Order History" tab

5. **Test position tracking:**
   - Place a BUY order
   - Go to "Positions" tab
   - Verify P&L updates

6. **Test order cancellation:**
   - Place a LIMIT order (won't execute immediately)
   - Go to "Open Orders" tab
   - Click "Cancel"

7. **Test position exit:**
   - Have an open position
   - Go to "Positions" tab
   - Click "Exit"

### Test Risk Calculator

1. Open order modal
2. Set entry price: 500
3. Set stop-loss: 490
4. Set risk %: 1.0
5. Set capital: 100,000
6. Verify recommended quantity = 100

## ⚠️ Before Going LIVE

1. **Verify credentials in config.py:**
   ```python
   ANGEL_API_KEY = "your_real_key"
   ANGEL_CLIENT_ID = "your_client_id"
   ANGEL_PASSWORD = "your_password"
   ANGEL_TOTP_SECRET = "your_totp_secret"
   ```

2. **Create `.env` file (DO NOT commit):**
   ```bash
   cp .env.example .env
   # Edit .env with real credentials
   ```

3. **Test with SMALL quantities first**

4. **Enable LIVE mode:**
   - Toggle the switch in the UI
   - OR set in config: `TRADING_MODE = "LIVE"`

5. **Confirm every order** - The system will show a confirmation dialog for LIVE orders

## 🔐 Security Checklist

- ✅ API credentials are on backend only
- ✅ `.env` is in `.gitignore`
- ✅ No credentials exposed in browser
- ✅ Paper mode for safe testing
- ✅ Confirmation required for LIVE orders
- ✅ Order validation before placement

## 📊 API Usage Examples

### Place Order via API

```bash
curl -X POST http://localhost:8000/orders/place \
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

### Get Positions

```bash
curl http://localhost:8000/positions
```

### Get Trading Stats

```bash
curl http://localhost:8000/trading/stats
```

### Switch to LIVE Mode

```bash
curl -X POST http://localhost:8000/trading/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "LIVE"}'
```

## 🐛 Troubleshooting

### Orders not appearing
- Check browser console for errors
- Verify API endpoint is running
- Check trading mode (PAPER vs LIVE)

### "Order validation failed"
- Verify all required fields are filled
- Check LIMIT orders have price
- Check STOPLOSS orders have trigger price

### Positions not updating
- Check WebSocket/polling is active
- Verify symbol tokens are correct
- Check Angel One session is active

### "Angel One login failed"
- Verify credentials in config.py
- Check TOTP secret is correct
- Ensure IP is whitelisted (if applicable)

## 📚 Features Implemented

### ✅ Feature 1-3: Order Actions
- [x] BUY MARKET, BUY LIMIT, BUY + SL buttons
- [x] SELL MARKET, SELL LIMIT, SELL + SL buttons
- [x] Order modal with all parameters

### ✅ Feature 4-5: Stop Loss & Limit Orders
- [x] Buy Limit with correct price validation
- [x] Stop Loss orders with trigger price
- [x] Risk/reward calculation

### ✅ Feature 6: Position/Order Listing
- [x] Open Orders tab
- [x] Order History tab
- [x] Positions tab with P&L
- [x] Modify/Cancel/Exit actions

### ✅ Feature 7: Angel One Sync
- [x] Real-time order fetching
- [x] Position P&L updates
- [x] Auto-refresh every 10 seconds
- [x] Error handling for all APIs

### ✅ Feature 8: Signal-to-Order Workflow
- [x] BUY/SELL buttons on each signal
- [x] Pre-populated entry/target/stop-loss
- [x] One-click order placement

### ✅ Feature 9: Risk Management
- [x] Capital input
- [x] Risk per trade %
- [x] Automatic quantity calculator
- [x] Position size validator

### ✅ Feature 10: Safety Confirmation
- [x] Confirmation dialog for LIVE orders
- [x] Shows all order details
- [x] No auto-execution on signals

### ✅ Feature 11: Dashboard
- [x] Available Funds
- [x] Used Margin
- [x] Open Positions count
- [x] Today's P&L

### ✅ Feature 12-14: Backend Architecture
- [x] Dedicated OrderService class
- [x] Secure credential management
- [x] PAPER/LIVE mode switching
- [x] Comprehensive logging (no credentials logged)

## 🚀 Next Steps

1. Follow the integration steps above to add the UI
2. Test thoroughly in PAPER mode
3. Verify all order types work correctly
4. Test risk calculator with different scenarios
5. Only after thorough testing, switch to LIVE mode with small quantities

## 📞 Support

If you encounter issues:
1. Check browser console for JavaScript errors
2. Check Python console for backend errors
3. Verify all files are in correct locations
4. Ensure FastAPI server is running
5. Test API endpoints directly with curl

---

**⚠️ IMPORTANT DISCLAIMER:**
This system places real orders with real money when in LIVE mode. Always test thoroughly in PAPER mode first. Never risk more than you can afford to lose. The developers are not responsible for any trading losses.
