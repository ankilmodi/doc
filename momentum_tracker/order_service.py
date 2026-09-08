"""
order_service.py – Angel One order management service.

Handles order placement, modification, cancellation, and position tracking.
Supports both PAPER (testing) and LIVE (real) trading modes.
"""

from __future__ import annotations

import logging
import json
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from dataclasses import dataclass, asdict

import requests

logger = logging.getLogger(__name__)


@dataclass
class OrderRequest:
    """Order placement request."""
    symbol: str
    symboltoken: str
    exchange: str = "NSE"
    transactiontype: str = "BUY"  # BUY | SELL
    ordertype: str = "MARKET"      # MARKET | LIMIT | STOPLOSS_LIMIT | STOPLOSS_MARKET
    producttype: str = "INTRADAY"  # INTRADAY | DELIVERY | MARGIN
    quantity: int = 1
    price: Optional[float] = None
    triggerprice: Optional[float] = None
    duration: str = "DAY"
    variety: str = "NORMAL"
    
    # Additional fields for internal tracking
    stop_loss: Optional[float] = None
    target: Optional[float] = None


class PaperTradingEngine:
    """Simple in-memory paper trading simulator."""
    
    def __init__(self):
        self.orders = {}
        self.positions = {}
        self.trades = []
        self.order_counter = 1000
        self.available_funds = 1_000_000.0  # ₹10 lakh default
        self.used_margin = 0.0
        
    def place_order(self, order_req: OrderRequest, current_ltp: float) -> Dict:
        """Simulate order placement."""
        self.order_counter += 1
        order_id = f"PAPER{self.order_counter}"
        
        # Determine execution
        if order_req.ordertype == "MARKET":
            status = "complete"
            exec_price = current_ltp
            filled_qty = order_req.quantity
        elif order_req.ordertype == "LIMIT":
            # Check if immediately executable
            if order_req.transactiontype == "BUY" and current_ltp <= order_req.price:
                status = "complete"
                exec_price = current_ltp
                filled_qty = order_req.quantity
            elif order_req.transactiontype == "SELL" and current_ltp >= order_req.price:
                status = "complete"
                exec_price = current_ltp
                filled_qty = order_req.quantity
            else:
                status = "open"
                exec_price = order_req.price
                filled_qty = 0
        else:  # Stop-loss orders
            status = "trigger pending"
            exec_price = None
            filled_qty = 0
        
        order = {
            "order_id": order_id,
            "symbol": order_req.symbol,
            "symboltoken": order_req.symboltoken,
            "exchange": order_req.exchange,
            "transactiontype": order_req.transactiontype,
            "ordertype": order_req.ordertype,
            "producttype": order_req.producttype,
            "quantity": order_req.quantity,
            "price": order_req.price,
            "triggerprice": order_req.triggerprice,
            "status": status,
            "filled_quantity": filled_qty,
            "average_price": exec_price,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "stop_loss": order_req.stop_loss,
            "target": order_req.target,
        }
        
        self.orders[order_id] = order
        
        # Update position if executed
        if status == "complete":
            self._update_position(order_req, exec_price, filled_qty)
        
        logger.info(f"[PAPER] Order placed: {order_id} | {order_req.transactiontype} {order_req.quantity} {order_req.symbol} @ {exec_price} | Status: {status}")
        
        return {
            "status": True,
            "message": "Paper order placed successfully",
            "data": {"orderid": order_id, "script": order_req.symbol}
        }
    
    def _update_position(self, order_req: OrderRequest, price: float, quantity: int):
        """Update position based on executed order."""
        symbol = order_req.symbol
        
        if symbol not in self.positions:
            self.positions[symbol] = {
                "symbol": symbol,
                "symboltoken": order_req.symboltoken,
                "exchange": order_req.exchange,
                "producttype": order_req.producttype,
                "quantity": 0,
                "buy_avg_price": 0.0,
                "sell_avg_price": 0.0,
                "ltp": price,
                "pnl": 0.0,
                "buy_quantity": 0,
                "sell_quantity": 0,
            }
        
        pos = self.positions[symbol]
        
        if order_req.transactiontype == "BUY":
            new_buy_qty = pos["buy_quantity"] + quantity
            pos["buy_avg_price"] = (
                (pos["buy_avg_price"] * pos["buy_quantity"] + price * quantity) / new_buy_qty
                if new_buy_qty > 0 else 0
            )
            pos["buy_quantity"] = new_buy_qty
            pos["quantity"] += quantity
        else:  # SELL
            new_sell_qty = pos["sell_quantity"] + quantity
            pos["sell_avg_price"] = (
                (pos["sell_avg_price"] * pos["sell_quantity"] + price * quantity) / new_sell_qty
                if new_sell_qty > 0 else 0
            )
            pos["sell_quantity"] = new_sell_qty
            pos["quantity"] -= quantity
        
        pos["ltp"] = price
        self._calculate_pnl(symbol)
    
    def _calculate_pnl(self, symbol: str):
        """Calculate P&L for a position."""
        pos = self.positions.get(symbol)
        if not pos:
            return
        
        if pos["quantity"] > 0:
            # Long position
            pos["pnl"] = (pos["ltp"] - pos["buy_avg_price"]) * pos["quantity"]
        elif pos["quantity"] < 0:
            # Short position
            pos["pnl"] = (pos["sell_avg_price"] - pos["ltp"]) * abs(pos["quantity"])
        else:
            pos["pnl"] = 0.0
    
    def modify_order(self, order_id: str, new_price: Optional[float] = None, new_qty: Optional[int] = None) -> Dict:
        """Modify an order."""
        if order_id not in self.orders:
            return {"status": False, "message": "Order not found"}
        
        order = self.orders[order_id]
        if order["status"] not in ("open", "trigger pending"):
            return {"status": False, "message": f"Cannot modify order in {order['status']} status"}
        
        if new_price is not None:
            order["price"] = new_price
        if new_qty is not None:
            order["quantity"] = new_qty
        
        order["status"] = "modified"
        order["updated_at"] = datetime.now().isoformat()
        
        logger.info(f"[PAPER] Order modified: {order_id}")
        return {"status": True, "message": "Paper order modified", "data": {"orderid": order_id}}
    
    def cancel_order(self, order_id: str) -> Dict:
        """Cancel an order."""
        if order_id not in self.orders:
            return {"status": False, "message": "Order not found"}
        
        order = self.orders[order_id]
        if order["status"] not in ("open", "trigger pending"):
            return {"status": False, "message": f"Cannot cancel order in {order['status']} status"}
        
        order["status"] = "cancelled"
        order["updated_at"] = datetime.now().isoformat()
        
        logger.info(f"[PAPER] Order cancelled: {order_id}")
        return {"status": True, "message": "Paper order cancelled", "data": {"orderid": order_id}}
    
    def get_orders(self) -> List[Dict]:
        """Get all orders."""
        return list(self.orders.values())
    
    def get_open_orders(self) -> List[Dict]:
        """Get open orders."""
        return [o for o in self.orders.values() if o["status"] in ("open", "pending", "trigger pending")]
    
    def get_order_history(self) -> List[Dict]:
        """Get completed/cancelled orders."""
        return [o for o in self.orders.values() if o["status"] in ("complete", "cancelled", "rejected")]
    
    def get_positions(self) -> List[Dict]:
        """Get all open positions."""
        return [p for p in self.positions.values() if p["quantity"] != 0]
    
    def get_funds(self) -> Dict:
        """Get fund details."""
        return {
            "availablecash": self.available_funds - self.used_margin,
            "utiliseddebits": self.used_margin,
            "net": self.available_funds,
        }
    
    def update_ltp(self, symbol: str, ltp: float):
        """Update LTP for position P&L calculation."""
        if symbol in self.positions:
            self.positions[symbol]["ltp"] = ltp
            self._calculate_pnl(symbol)


# Global paper trading engine
_paper_engine = PaperTradingEngine()


class OrderService:
    """
    Order management service for Angel One.
    Supports both PAPER and LIVE trading modes.
    """
    
    def __init__(self, angel_connector, trading_mode: str = "PAPER"):
        """
        Initialize order service.
        
        Args:
            angel_connector: AngelConnector instance with active session
            trading_mode: "PAPER" or "LIVE"
        """
        self.angel = angel_connector
        self.trading_mode = trading_mode.upper()
        self.base_url = "https://apiconnect.angelbroking.com"
        
        logger.info(f"OrderService initialized in {self.trading_mode} mode")
    
    def set_trading_mode(self, mode: str):
        """Switch between PAPER and LIVE modes."""
        self.trading_mode = mode.upper()
        logger.info(f"Trading mode set to {self.trading_mode}")
    
    def _headers(self) -> Dict[str, str]:
        """Get headers for API requests."""
        return {
            "Authorization": f"Bearer {self.angel._jwt_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            "X-ClientLocalIP": self.angel._server_ip,
            "X-ClientPublicIP": self.angel._server_ip,
            "X-MACAddress": "fe:80:00:00:00:00",
            "X-PrivateKey": self.angel._headers()["X-PrivateKey"],
        }
    
    def place_order(self, order_req: OrderRequest, current_ltp: float) -> Dict:
        """
        Place an order.
        
        Args:
            order_req: Order request object
            current_ltp: Current last traded price (for paper trading)
        
        Returns:
            Response dict with status, message, and data
        """
        # Validate order
        is_valid, error_msg = self._validate_order(order_req)
        if not is_valid:
            return {"status": False, "message": error_msg, "errorcode": "INVALID_ORDER"}
        
        # Paper mode
        if self.trading_mode == "PAPER":
            return _paper_engine.place_order(order_req, current_ltp)
        
        # LIVE mode - call Angel One API
        try:
            payload = {
                "variety": order_req.variety,
                "tradingsymbol": order_req.symbol,
                "symboltoken": order_req.symboltoken,
                "transactiontype": order_req.transactiontype,
                "exchange": order_req.exchange,
                "ordertype": order_req.ordertype,
                "producttype": order_req.producttype,
                "duration": order_req.duration,
                "quantity": str(order_req.quantity),
            }
            
            if order_req.price is not None:
                payload["price"] = f"{order_req.price:.2f}"
            
            if order_req.triggerprice is not None:
                payload["triggerprice"] = f"{order_req.triggerprice:.2f}"
            
            resp = requests.post(
                f"{self.base_url}/rest/secure/angelbroking/order/v1/placeOrder",
                json=payload,
                headers=self._headers(),
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            
            logger.info(f"[LIVE] Order placed: {order_req.transactiontype} {order_req.quantity} {order_req.symbol} | Response: {data}")
            
            return data
            
        except Exception as exc:
            logger.error(f"[LIVE] Order placement failed: {exc}")
            return {
                "status": False,
                "message": f"Order placement failed: {str(exc)}",
                "errorcode": "API_ERROR",
            }
    
    def modify_order(self, order_id: str, variety: str, ordertype: str, 
                    quantity: Optional[int] = None, price: Optional[float] = None) -> Dict:
        """Modify an existing order."""
        if self.trading_mode == "PAPER":
            return _paper_engine.modify_order(order_id, price, quantity)
        
        try:
            payload = {
                "variety": variety,
                "orderid": order_id,
                "ordertype": ordertype,
            }
            if quantity is not None:
                payload["quantity"] = str(quantity)
            if price is not None:
                payload["price"] = f"{price:.2f}"
            
            resp = requests.post(
                f"{self.base_url}/rest/secure/angelbroking/order/v1/modifyOrder",
                json=payload,
                headers=self._headers(),
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.error(f"[LIVE] Order modification failed: {exc}")
            return {"status": False, "message": str(exc)}
    
    def cancel_order(self, order_id: str, variety: str) -> Dict:
        """Cancel an order."""
        if self.trading_mode == "PAPER":
            return _paper_engine.cancel_order(order_id)
        
        try:
            payload = {"variety": variety, "orderid": order_id}
            resp = requests.post(
                f"{self.base_url}/rest/secure/angelbroking/order/v1/cancelOrder",
                json=payload,
                headers=self._headers(),
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.error(f"[LIVE] Order cancellation failed: {exc}")
            return {"status": False, "message": str(exc)}
    
    def get_order_book(self) -> List[Dict]:
        """Get all orders."""
        if self.trading_mode == "PAPER":
            return _paper_engine.get_orders()
        
        try:
            resp = requests.get(
                f"{self.base_url}/rest/secure/angelbroking/order/v1/getOrderBook",
                headers=self._headers(),
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", []) if data.get("status") else []
        except Exception as exc:
            logger.error(f"[LIVE] Get order book failed: {exc}")
            return []
    
    def get_positions(self) -> List[Dict]:
        """Get positions."""
        if self.trading_mode == "PAPER":
            return _paper_engine.get_positions()
        
        try:
            resp = requests.get(
                f"{self.base_url}/rest/secure/angelbroking/order/v1/getPosition",
                headers=self._headers(),
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", []) if data.get("status") else []
        except Exception as exc:
            logger.error(f"[LIVE] Get positions failed: {exc}")
            return []
    
    def get_trade_book(self) -> List[Dict]:
        """Get executed trades."""
        if self.trading_mode == "PAPER":
            return []  # Not implemented in paper trading
        
        try:
            resp = requests.get(
                f"{self.base_url}/rest/secure/angelbroking/order/v1/getTradeBook",
                headers=self._headers(),
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", []) if data.get("status") else []
        except Exception as exc:
            logger.error(f"[LIVE] Get trade book failed: {exc}")
            return []
    
    def get_rms_limits(self) -> Dict:
        """Get available funds and margin info."""
        if self.trading_mode == "PAPER":
            return _paper_engine.get_funds()
        
        try:
            resp = requests.get(
                f"{self.base_url}/rest/secure/angelbroking/user/v1/getRMS",
                headers=self._headers(),
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", {}) if data.get("status") else {}
        except Exception as exc:
            logger.error(f"[LIVE] Get RMS limits failed: {exc}")
            return {}
    
    def _validate_order(self, order_req: OrderRequest) -> Tuple[bool, Optional[str]]:
        """Validate order parameters."""
        if order_req.quantity <= 0:
            return False, "Quantity must be positive"
        
        if order_req.ordertype == "LIMIT" and order_req.price is None:
            return False, "LIMIT orders require a price"
        
        if order_req.ordertype in ("STOPLOSS_LIMIT", "STOPLOSS_MARKET"):
            if order_req.triggerprice is None:
                return False, "STOPLOSS orders require a trigger price"
        
        if order_req.ordertype == "STOPLOSS_LIMIT":
            if order_req.price is None:
                return False, "STOPLOSS_LIMIT orders require both price and trigger price"
            
            if order_req.transactiontype == "BUY" and order_req.price < order_req.triggerprice:
                return False, "For BUY stop-loss, price must be >= trigger price"
            elif order_req.transactiontype == "SELL" and order_req.price > order_req.triggerprice:
                return False, "For SELL stop-loss, price must be <= trigger price"
        
        return True, None
    
    def calculate_position_size(self, capital: float, risk_pct: float, 
                               entry_price: float, stop_loss_price: float) -> int:
        """
        Calculate recommended position size based on risk management.
        
        Args:
            capital: Total capital
            risk_pct: Risk percentage per trade (e.g., 1.0 for 1%)
            entry_price: Entry price per share
            stop_loss_price: Stop loss price per share
        
        Returns:
            Recommended quantity
        """
        if entry_price <= 0 or stop_loss_price <= 0:
            return 0
        
        risk_per_share = abs(entry_price - stop_loss_price)
        if risk_per_share == 0:
            return 0
        
        max_risk_amount = capital * (risk_pct / 100)
        quantity = int(max_risk_amount / risk_per_share)
        
        return max(1, quantity)
