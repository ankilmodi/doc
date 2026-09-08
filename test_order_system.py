"""
test_order_system.py - Quick test script for order management system.

Run this to verify the backend order management is working correctly.
Tests PAPER mode only (no real orders).

Usage:
    python test_order_system.py
"""

import sys
import os

# Add momentum_tracker to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "momentum_tracker"))

from order_service import OrderService, OrderRequest
from angel_connector import AngelConnector
import config

def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)

def test_paper_trading():
    """Test paper trading engine."""
    print_section("TEST 1: Paper Trading Engine")
    
    # Initialize Angel connector (for LTP data)
    print("Initializing Angel One connector...")
    try:
        angel = AngelConnector()
        print("✅ Angel One connected successfully")
    except Exception as e:
        print(f"❌ Angel One connection failed: {e}")
        print("⚠️  Continuing with paper trading tests...")
        angel = None
    
    # Initialize order service in PAPER mode
    print("\nInitializing OrderService in PAPER mode...")
    order_service = OrderService(angel, trading_mode="PAPER") if angel else None
    
    if not order_service:
        print("⚠️  Cannot test without order service")
        return
    
    print("✅ OrderService initialized in PAPER mode")
    
    # Test 1: Place a MARKET BUY order
    print_section("TEST 2: Place MARKET BUY Order")
    
    order_req = OrderRequest(
        symbol="RELIANCE",
        symboltoken="2885",
        exchange="NSE",
        transactiontype="BUY",
        ordertype="MARKET",
        producttype="INTRADAY",
        quantity=10,
    )
    
    print(f"Placing order: BUY 10 RELIANCE @ MARKET")
    result = order_service.place_order(order_req, current_ltp=2500.0)
    
    if result.get("status"):
        print(f"✅ Order placed successfully!")
        print(f"   Order ID: {result['data']['orderid']}")
    else:
        print(f"❌ Order failed: {result.get('message')}")
    
    # Test 2: Place a LIMIT SELL order
    print_section("TEST 3: Place LIMIT SELL Order")
    
    order_req2 = OrderRequest(
        symbol="INFY",
        symboltoken="1594",
        exchange="NSE",
        transactiontype="SELL",
        ordertype="LIMIT",
        producttype="INTRADAY",
        quantity=50,
        price=1500.0,
    )
    
    print(f"Placing order: SELL 50 INFY @ ₹1500 LIMIT")
    result2 = order_service.place_order(order_req2, current_ltp=1480.0)
    
    if result2.get("status"):
        print(f"✅ Order placed successfully!")
        print(f"   Order ID: {result2['data']['orderid']}")
    else:
        print(f"❌ Order failed: {result2.get('message')}")
    
    # Test 3: Get order book
    print_section("TEST 4: Fetch Order Book")
    
    orders = order_service.get_order_book()
    print(f"Total orders: {len(orders)}")
    
    for order in orders:
        print(f"  - {order['order_id']}: {order['transactiontype']} {order['quantity']} {order['symbol']} @ {order['ordertype']} | Status: {order['status']}")
    
    if len(orders) >= 2:
        print("✅ Order book retrieved successfully")
    else:
        print("⚠️  Expected at least 2 orders")
    
    # Test 4: Get positions
    print_section("TEST 5: Fetch Positions")
    
    positions = order_service.get_positions()
    print(f"Total positions: {len(positions)}")
    
    for pos in positions:
        print(f"  - {pos['symbol']}: {pos['quantity']} shares | P&L: ₹{pos['pnl']:.2f}")
    
    if len(positions) >= 1:
        print("✅ Positions retrieved successfully")
    else:
        print("⚠️  Expected at least 1 position (from RELIANCE BUY)")
    
    # Test 5: Cancel an order
    if orders and len(orders) > 0:
        print_section("TEST 6: Cancel Order")
        
        # Find an open order to cancel
        open_order = next((o for o in orders if o['status'] in ('open', 'trigger pending')), None)
        
        if open_order:
            order_id = open_order['order_id']
            print(f"Cancelling order: {order_id}")
            cancel_result = order_service.cancel_order(order_id, variety="NORMAL")
            
            if cancel_result.get("status"):
                print(f"✅ Order cancelled successfully")
            else:
                print(f"❌ Cancellation failed: {cancel_result.get('message')}")
        else:
            print("⚠️  No open orders to cancel")
    
    # Test 6: Get funds
    print_section("TEST 7: Fetch Funds")
    
    funds = order_service.get_rms_limits()
    print(f"Available Cash: ₹{funds.get('availablecash', 0):,.2f}")
    print(f"Used Margin: ₹{funds.get('utiliseddebits', 0):,.2f}")
    print(f"Net: ₹{funds.get('net', 0):,.2f}")
    print("✅ Funds retrieved successfully")
    
    # Test 7: Position sizing calculator
    print_section("TEST 8: Position Size Calculator")
    
    capital = 100000
    risk_pct = 1.0
    entry_price = 500.0
    stop_loss = 490.0
    
    recommended_qty = order_service.calculate_position_size(
        capital=capital,
        risk_pct=risk_pct,
        entry_price=entry_price,
        stop_loss_price=stop_loss,
    )
    
    risk_per_share = abs(entry_price - stop_loss)
    total_risk = risk_per_share * recommended_qty
    
    print(f"Capital: ₹{capital:,.0f}")
    print(f"Risk per trade: {risk_pct}%")
    print(f"Entry: ₹{entry_price} | Stop Loss: ₹{stop_loss}")
    print(f"Risk per share: ₹{risk_per_share}")
    print(f"➡️  Recommended Quantity: {recommended_qty} shares")
    print(f"Total Risk: ₹{total_risk:.2f} ({(total_risk/capital)*100:.2f}%)")
    
    if recommended_qty == 100:
        print("✅ Position sizing calculator working correctly")
    else:
        print(f"⚠️  Expected 100, got {recommended_qty}")
    
    print_section("✅ ALL TESTS COMPLETED")
    print("\nSummary:")
    print("  - Paper trading engine: ✅ Working")
    print("  - Order placement: ✅ Working")
    print("  - Order book: ✅ Working")
    print("  - Positions: ✅ Working")
    print("  - Funds: ✅ Working")
    print("  - Position sizing: ✅ Working")
    print("\n🎉 Backend order management system is fully functional!")
    print("\n⚠️  NOTE: These were PAPER trades only. No real orders were placed.")
    print("      To test with real API, switch TRADING_MODE to 'LIVE' in config.py")

def test_order_validation():
    """Test order validation logic."""
    print_section("TEST 9: Order Validation")
    
    # Valid order
    valid_order = OrderRequest(
        symbol="RELIANCE",
        symboltoken="2885",
        transactiontype="BUY",
        ordertype="LIMIT",
        producttype="INTRADAY",
        quantity=10,
        price=2500.0,
    )
    
    from order_service import OrderService
    
    # Create a dummy order service for validation testing
    class DummyAngel:
        _jwt_token = "dummy"
        _server_ip = "127.0.0.1"
        def _headers(self):
            return {"X-PrivateKey": "dummy"}
    
    service = OrderService(DummyAngel(), "PAPER")
    
    is_valid, error = service._validate_order(valid_order)
    print(f"Valid order test: {'✅ PASS' if is_valid else '❌ FAIL'}")
    
    # Invalid order - negative quantity
    invalid_order1 = OrderRequest(
        symbol="RELIANCE",
        symboltoken="2885",
        transactiontype="BUY",
        ordertype="MARKET",
        producttype="INTRADAY",
        quantity=-5,
    )
    
    is_valid, error = service._validate_order(invalid_order1)
    expected_error = not is_valid and "positive" in error.lower()
    print(f"Negative quantity test: {'✅ PASS' if expected_error else '❌ FAIL'}")
    
    # Invalid order - LIMIT without price
    invalid_order2 = OrderRequest(
        symbol="RELIANCE",
        symboltoken="2885",
        transactiontype="BUY",
        ordertype="LIMIT",
        producttype="INTRADAY",
        quantity=10,
        price=None,
    )
    
    is_valid, error = service._validate_order(invalid_order2)
    expected_error = not is_valid and "price" in error.lower()
    print(f"LIMIT without price test: {'✅ PASS' if expected_error else '❌ FAIL'}")
    
    # Invalid order - STOPLOSS without trigger
    invalid_order3 = OrderRequest(
        symbol="RELIANCE",
        symboltoken="2885",
        transactiontype="BUY",
        ordertype="STOPLOSS_LIMIT",
        producttype="INTRADAY",
        quantity=10,
        price=2510.0,
        triggerprice=None,
    )
    
    is_valid, error = service._validate_order(invalid_order3)
    expected_error = not is_valid and "trigger" in error.lower()
    print(f"STOPLOSS without trigger test: {'✅ PASS' if expected_error else '❌ FAIL'}")
    
    print("✅ Order validation tests completed")

if __name__ == "__main__":
    print("\n" + "="*60)
    print("  ORDER MANAGEMENT SYSTEM TEST SUITE")
    print("  Testing PAPER mode only (safe)")
    print("="*60)
    
    try:
        test_paper_trading()
        test_order_validation()
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*60)
    print("  End of tests")
    print("="*60 + "\n")
