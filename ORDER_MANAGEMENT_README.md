# Angel One Order Management System

## 🎯 Overview

Complete order management system for your Momentum Signal Tracker with Angel One SmartAPI integration.

### ✨ Key Features

- ✅ **PAPER/LIVE Trading Modes** - Test safely before going live
- ✅ **Order Placement** - Market, Limit, Stop-Loss orders
- ✅ **Position Tracking** - Real-time P&L monitoring
- ✅ **Risk Management** - Automated position sizing
- ✅ **Order Book** - Complete order history and status
- ✅ **Safety Features** - Confirmation dialogs, validation
- ✅ **Secure** - All credentials stay on backend

## 📁 Project Structure

```
C:\xampp\htdocs\doc\
│
├── momentum_tracker/
│   ├── order_service.py              ✅ Core order management
│   ├── angel_connector.py            ✅ Angel One API (existing)
│   ├── config.py                     ✅ Configuration (enhanced)
│   ├── scanner.py                    ✅ Signal detection (existing)
│   └── ...
│
├── api/
│   └── index.py                      ✅ FastAPI endpoints (enhanced)
│
├── public/
│   ├── index.html                    ⚠️  Needs integration
│   ├── order-management.js           ✅ Frontend module (NEW)
│   └── order-ui-additions.html       ✅ UI components (NEW)
│
├── .env.example                      ✅ Credential template
├── .gitignore                        ✅ Security
├── ORDER_MANAGEMENT_INTEGRATION_GUIDE.md  📖 Integration steps
├── ORDER_MANAGEMENT_README.md        📖 This file
└── test_order_system.py              🧪 Test script
```

## 🚀 Quick Start

### 1. Test Backend (Paper Mode)

```powershell
cd C:\xampp\htdocs\doc
python test_order_system.py
```

Expected output:
```
✅ Paper trading engine: Working
✅ Order placement: Working
✅ Order book: Working
✅ Positions: Working
✅ Funds: Working
✅ Position sizing: Working
```

### 2. Start the Server

```powershell
cd C:\xampp\htdocs\doc
python -m uvicorn api.index:app --reload --port 8000
```

### 3. Test API Endpoints

```bash
# Get trading mode
curl http://localhost:8000/trading/mode

# Get trading stats
curl http://localhost:8000/trading/stats

# Place a paper order
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

# Get positions
curl http://localhost:8000/positions

# Get orders
curl http://localhost:8000/orders
```

### 4. Integrate Frontend

Follow the steps in `ORDER_MANAGEMENT_INTEGRATION_GUIDE.md` to add the UI to your `index.html`.

## 📊 API Endpoints

### Trading Mode

```
GET  /trading/mode          Get current mode (PAPER/LIVE)
POST /trading/mode          Switch mode {"mode": "PAPER"}
```

### Orders

```
POST /orders/place          Place order
POST /orders/modify         Modify order
POST /orders/cancel         Cancel order
GET  /orders                Get all orders
GET  /orders/open           Get open orders only
GET  /orders/history        Get completed/cancelled orders
```

### Positions & Trades

```
GET  /positions             Get current positions with P&L
GET  /trades                Get trade book (executed trades)
```

### Risk & Funds

```
GET  /funds                 Get available funds & margin
POST /orders/calculate-quantity  Calculate position size
GET  /trading/stats         Get dashboard statistics
```

## 🎨 Frontend Components

### 1. Trading Mode Toggle
- Switch between PAPER (test) and LIVE (real)
- Visual indicator (blue/purple for PAPER, red for LIVE)
- Confirmation dialog when switching to LIVE

### 2. Trading Dashboard
- **Available Funds** - Cash available for trading
- **Used Margin** - Margin currently utilized
- **Open Positions** - Number of active positions
- **Today's P&L** - Profit/Loss for the day

### 3. Order Buttons on Signals
Each signal row has:
- **BUY/SELL MKT** - Market order button
- **BUY/SELL LMT** - Limit order button

### 4. Order Modal
Complete order form with:
- Symbol & current LTP
- Transaction type (BUY/SELL)
- Order type (MARKET/LIMIT/STOPLOSS)
- Product type (INTRADAY/DELIVERY/MARGIN)
- Quantity
- Price & Trigger price
- Stop-Loss & Target
- Risk management calculator

### 5. Order Management Tabs

**Open Orders Tab:**
- Order ID, Symbol, Side, Type, Qty, Price, Trigger, Status
- Actions: Modify, Cancel

**Order History Tab:**
- Completed and cancelled orders
- Execution details
- Timestamp

**Positions Tab:**
- Symbol, Type (LONG/SHORT), Quantity
- Average Price, LTP, P&L
- Actions: Exit position

## 🔐 Security Features

1. **Backend-Only Credentials**
   - API keys never sent to frontend
   - All authentication on server

2. **Environment Variables**
   - Use `.env` file (not committed)
   - Template provided in `.env.example`

3. **Order Validation**
   - All orders validated before placement
   - Logical checks (price, trigger, quantity)

4. **Confirmation Dialogs**
   - LIVE mode switch requires confirmation
   - Every LIVE order requires explicit confirmation

5. **Paper Mode Default**
   - System starts in PAPER mode
   - Must explicitly switch to LIVE

## 💡 Usage Examples

### Example 1: Place Market Order from Signal

1. Click "Start Scan"
2. Wait for signals to appear
3. Click "🟢 BUY MKT" on a BUY signal
4. Modal opens with pre-filled data
5. Adjust quantity if needed
6. Click "Place Order"
7. Order appears in "Open Orders" or executes immediately

### Example 2: Place Limit Order with Stop-Loss

1. Click "BUY LMT" on a signal
2. Modal opens
3. Set:
   - Limit Price: ₹500
   - Quantity: 100
   - Stop-Loss: ₹490
   - Target: ₹520
4. System calculates recommended quantity based on risk
5. Click "Place Order"
6. Order goes to "Open Orders"

### Example 3: Monitor Position P&L

1. Go to "Positions" tab
2. See all open positions
3. P&L updates automatically every 10 seconds
4. Click "Exit" to close position at market

### Example 4: Calculate Position Size

1. Open order modal
2. Set Capital: ₹100,000
3. Set Risk %: 1.0
4. Set Entry: ₹500
5. Set Stop-Loss: ₹490
6. System shows:
   - Recommended Quantity: 100
   - Risk per share: ₹10
   - Total Risk: ₹1,000 (1%)
   - Position Value: ₹50,000

## 🧪 Testing Workflow

### Phase 1: Backend Testing (PAPER Mode)

```powershell
# Run test script
python test_order_system.py

# Expected: All tests pass ✅
```

### Phase 2: API Testing (PAPER Mode)

```powershell
# Start server
python -m uvicorn api.index:app --reload --port 8000

# Test with curl (see API endpoints above)
```

### Phase 3: Frontend Testing (PAPER Mode)

1. Integrate UI (follow integration guide)
2. Open `http://localhost:8000/public/index.html`
3. Verify PAPER mode is active
4. Test all order types
5. Test position tracking
6. Test order cancellation
7. Test position exit

### Phase 4: LIVE Testing (Real Money)

⚠️ **WARNING: Only proceed after thorough PAPER testing**

1. Verify all credentials are correct
2. Start with VERY SMALL quantities
3. Toggle to LIVE mode (confirm dialog)
4. Place ONE test order
5. Verify order appears in Angel One app
6. Verify order executes correctly
7. Gradually increase usage

## 📋 Checklist Before Going LIVE

- [ ] Tested all order types in PAPER mode
- [ ] Tested order modification
- [ ] Tested order cancellation
- [ ] Tested position exit
- [ ] Verified risk calculator works correctly
- [ ] Tested with different symbols
- [ ] Verified P&L calculation is accurate
- [ ] Checked order validation catches errors
- [ ] Confirmed credentials are correct
- [ ] Backed up current working code
- [ ] Set up stop-loss for all positions
- [ ] Started with small quantities

## 🐛 Troubleshooting

### "Angel One login failed"
- Check credentials in `config.py`
- Verify TOTP secret is correct
- Check if 2FA is enabled in Angel One
- Ensure API key is active

### "Order validation failed"
- Check all required fields are filled
- LIMIT orders need price
- STOPLOSS orders need trigger price
- Quantity must be positive

### "Positions not updating"
- Check auto-refresh is enabled
- Verify symbol tokens are correct
- Check Angel One session is active
- Look for errors in browser console

### Frontend not loading
- Check `order-management.js` is included
- Verify API server is running
- Check browser console for errors
- Ensure CORS is enabled

## 📚 Additional Resources

- **Integration Guide:** `ORDER_MANAGEMENT_INTEGRATION_GUIDE.md`
- **Test Script:** `test_order_system.py`
- **UI Components:** `order-ui-additions.html`
- **Angel One API Docs:** https://smartapi.angelbroking.com/docs

## ⚠️ Important Disclaimers

1. **Trading Risk**
   - Trading involves substantial risk
   - Only risk capital you can afford to lose
   - Past performance does not guarantee future results

2. **Software Disclaimer**
   - This is educational software
   - Not financial advice
   - Use at your own risk
   - Developers not responsible for trading losses

3. **Testing**
   - Always test in PAPER mode first
   - Start with small quantities in LIVE mode
   - Never deploy untested code to production

4. **Security**
   - Never commit credentials to version control
   - Use strong passwords
   - Rotate API keys regularly
   - Monitor for unauthorized access

## 🎉 What's Included

### Backend (Python)
- ✅ Order placement service
- ✅ Paper trading simulator
- ✅ Position tracking
- ✅ Risk management calculator
- ✅ Order validation
- ✅ 13 REST API endpoints
- ✅ Secure credential management

### Frontend (JavaScript)
- ✅ Trading mode toggle
- ✅ Order buttons on signals
- ✅ Order placement modal
- ✅ Position tracking UI
- ✅ Order book display
- ✅ Risk calculator
- ✅ Real-time updates
- ✅ Confirmation dialogs

### Documentation
- ✅ Integration guide
- ✅ API documentation
- ✅ Testing guide
- ✅ Security best practices
- ✅ Troubleshooting guide

## 🚀 Next Steps

1. **Now:** Test backend with `python test_order_system.py`
2. **Next:** Integrate frontend UI
3. **Then:** Test thoroughly in PAPER mode
4. **Finally:** Go LIVE with small quantities

## 📞 Support

If you need help:
1. Check the troubleshooting section
2. Review the integration guide
3. Run the test script to identify issues
4. Check browser console for frontend errors
5. Check Python console for backend errors

---

**Built with:** Python, FastAPI, Angel One SmartAPI, Vanilla JavaScript

**License:** For educational and personal use only

**Version:** 1.0.0

**Last Updated:** September 7, 2026
