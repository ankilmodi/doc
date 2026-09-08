"""
api/index.py – FastAPI web server for the Momentum Signal Tracker.

Uses Market Quote FULL mode only (no historical API – avoids 403 from
non-Indian Vercel server IPs).

Python-based session management for simplified login.
"""

from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "momentum_tracker"))

from fastapi import FastAPI, Query, Body, Request, Cookie, Response, Form
from fastapi.responses import PlainTextResponse, JSONResponse, HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from itsdangerous import URLSafeTimedSerializer, BadSignature
import secrets

import config
import signals as sig
import formatter as fmt
from angel_connector import AngelConnector
from symbols import refresh_tokens_from_master
from scanner import run_single_scan
from order_service import OrderService, OrderRequest

# Setup Jinja2 templates
import os
templates_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
templates = Jinja2Templates(directory=templates_dir)

app = FastAPI(
    title="Momentum Signal Tracker",
    description="Intraday NIFTY 50/500 momentum signals via Angel One SmartConnect.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# ── Session Management (Python-based) ─────────────────────────────────────────
SECRET_KEY = os.getenv("SESSION_SECRET_KEY", secrets.token_hex(32))
serializer = URLSafeTimedSerializer(SECRET_KEY)
SESSION_MAX_AGE = 8 * 60 * 60  # 8 hours

# Store active sessions in memory (for serverless, use Redis/DB in production)
active_sessions = {}

def create_session(user_id: str) -> str:
    """Create a new session token"""
    session_token = serializer.dumps({"user_id": user_id, "created_at": datetime.now().isoformat()})
    active_sessions[session_token] = {
        "user_id": user_id,
        "created_at": datetime.now(),
        "expires_at": datetime.now() + timedelta(seconds=SESSION_MAX_AGE)
    }
    return session_token

def verify_session(session_token: Optional[str]) -> Optional[Dict]:
    """Verify session token and return session data"""
    if not session_token:
        return None
    
    if session_token not in active_sessions:
        return None
    
    session_data = active_sessions[session_token]
    if datetime.now() > session_data["expires_at"]:
        del active_sessions[session_token]
        return None
    
    return session_data

def delete_session(session_token: str):
    """Delete a session"""
    if session_token in active_sessions:
        del active_sessions[session_token]

# ── Module-level singletons (reused across warm Vercel invocations) ───────────
_api:      Optional[AngelConnector] = None
_universe: Optional[list]           = None
_order_service: Optional[OrderService] = None


def _get_api() -> AngelConnector:
    global _api
    if _api is None:
        _api = AngelConnector()
    return _api


def _get_universe() -> list:
    global _universe
    if _universe is None:
        _universe = refresh_tokens_from_master()
    return _universe


def _get_order_service() -> OrderService:
    global _order_service
    if _order_service is None:
        api = _get_api()
        _order_service = OrderService(api, trading_mode=config.TRADING_MODE)
    return _order_service


# ── Routes ────────────────────────────────────────────────────────────────────

_INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Momentum Signal Tracker</title>
  <style>
    :root {
      --bg:        #0d1117;
      --surface:   #161b22;
      --surface2:  #21262d;
      --border:    #30363d;
      --green:     #3fb950;
      --red:       #f85149;
      --yellow:    #d29922;
      --blue:      #58a6ff;
      --purple:    #bc8cff;
      --text:      #e6edf3;
      --muted:     #8b949e;
      --font:      'Segoe UI', system-ui, sans-serif;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      background: var(--bg);
      color: var(--text);
      font-family: var(--font);
      min-height: 100vh;
    }

    /* ── Header ── */
    header {
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: 14px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 12px;
      position: sticky;
      top: 0;
      z-index: 100;
    }
    .logo {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .logo-icon {
      width: 36px; height: 36px;
      background: linear-gradient(135deg, #58a6ff, #bc8cff);
      border-radius: 8px;
      display: flex; align-items: center; justify-content: center;
      font-size: 18px;
    }
    .logo h1 { font-size: 18px; font-weight: 700; letter-spacing: 0.3px; }
    .logo span { font-size: 12px; color: var(--muted); display: block; margin-top: 1px; }

    .header-right {
      display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
    }
    .status-pill {
      display: flex; align-items: center; gap: 6px;
      background: var(--surface2);
      border: 1px solid var(--border);
      border-radius: 20px;
      padding: 5px 12px;
      font-size: 13px;
    }
    .dot {
      width: 8px; height: 8px; border-radius: 50%;
      background: var(--muted);
      transition: background 0.3s;
    }
    .dot.live  { background: var(--green); box-shadow: 0 0 6px var(--green); animation: pulse 2s infinite; }
    .dot.error { background: var(--red); }
    @keyframes pulse {
      0%,100% { opacity: 1; } 50% { opacity: 0.4; }
    }

    #last-updated { font-size: 12px; color: var(--muted); }

    /* ── Controls bar ── */
    .controls {
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: 12px 24px;
      display: flex;
      align-items: center;
      gap: 14px;
      flex-wrap: wrap;
    }
    .ctrl-group { display: flex; align-items: center; gap: 8px; }
    .ctrl-group label { font-size: 13px; color: var(--muted); white-space: nowrap; }
    select, input[type=number] {
      background: var(--surface2);
      border: 1px solid var(--border);
      color: var(--text);
      border-radius: 6px;
      padding: 6px 10px;
      font-size: 13px;
      outline: none;
      transition: border-color 0.2s;
    }
    select:focus, input[type=number]:focus { border-color: var(--blue); }
    input[type=number] { width: 90px; }

    .btn {
      padding: 7px 16px;
      border-radius: 6px;
      border: none;
      cursor: pointer;
      font-size: 13px;
      font-weight: 600;
      transition: opacity 0.2s, transform 0.1s;
    }
    .btn:active { transform: scale(0.97); }
    .btn-primary  { background: var(--blue);   color: #000; }
    .btn-success  { background: var(--green);  color: #000; }
    .btn-outline  {
      background: transparent;
      border: 1px solid var(--border);
      color: var(--text);
    }
    .btn:disabled { opacity: 0.4; cursor: not-allowed; }

    .spacer { flex: 1; }

    /* ── Countdown bar ── */
    #countdown-bar {
      height: 3px;
      background: var(--border);
      position: relative;
      overflow: hidden;
    }
    #countdown-fill {
      height: 100%;
      background: linear-gradient(90deg, var(--blue), var(--purple));
      width: 100%;
      transition: width 1s linear;
    }

    /* ── Main layout ── */
    main { padding: 20px 24px; max-width: 1600px; margin: 0 auto; }

    /* ── Stats row ── */
    .stats-row {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 12px;
      margin-bottom: 20px;
    }
    .stat-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 14px 16px;
    }
    .stat-card .label { font-size: 12px; color: var(--muted); margin-bottom: 6px; }
    .stat-card .value { font-size: 24px; font-weight: 700; }
    .stat-card .sub   { font-size: 11px; color: var(--muted); margin-top: 3px; }
    .green { color: var(--green); }
    .red   { color: var(--red);   }
    .blue  { color: var(--blue);  }
    .yellow{ color: var(--yellow);}

    /* ── Table section ── */
    .section-header {
      display: flex; align-items: center; justify-content: space-between;
      margin-bottom: 12px; flex-wrap: wrap; gap: 8px;
    }
    .section-title { font-size: 15px; font-weight: 600; }
    .tag {
      font-size: 11px; padding: 2px 8px;
      border-radius: 12px; font-weight: 600;
    }
    .tag-buy  { background: rgba(63,185,80,0.15);  color: var(--green); border: 1px solid rgba(63,185,80,0.3); }
    .tag-sell { background: rgba(248,81,73,0.15);  color: var(--red);   border: 1px solid rgba(248,81,73,0.3); }
    .tag-fno  { background: rgba(188,140,255,0.15);color: var(--purple);border: 1px solid rgba(188,140,255,0.3); }
    .tag-bo   { background: rgba(210,153,34,0.15); color: var(--yellow);border: 1px solid rgba(210,153,34,0.3); }

    .table-wrap {
      overflow-x: auto;
      border-radius: 10px;
      border: 1px solid var(--border);
      margin-bottom: 24px;
    }
    table {
      width: 100%; border-collapse: collapse;
      font-size: 13px; white-space: nowrap;
    }
    thead tr {
      background: var(--surface2);
      border-bottom: 1px solid var(--border);
    }
    th {
      padding: 10px 14px;
      text-align: left;
      font-weight: 600;
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    tbody tr {
      border-bottom: 1px solid var(--border);
      transition: background 0.15s;
    }
    tbody tr:last-child { border-bottom: none; }
    tbody tr:hover { background: rgba(88,166,255,0.05); }
    td { padding: 11px 14px; }

    .rank-badge {
      width: 24px; height: 24px; border-radius: 50%;
      background: var(--surface2);
      border: 1px solid var(--border);
      display: inline-flex; align-items: center; justify-content: center;
      font-size: 11px; font-weight: 700; color: var(--muted);
    }
    .rank-badge.top { background: rgba(210,153,34,0.2); border-color: var(--yellow); color: var(--yellow); }

    .symbol-cell { font-weight: 700; font-size: 14px; }

    .bar-wrap {
      display: flex; align-items: center; gap: 8px;
    }
    .bar-bg {
      width: 60px; height: 6px; background: var(--surface2);
      border-radius: 3px; overflow: hidden; flex-shrink: 0;
    }
    .bar-fill {
      height: 100%; border-radius: 3px;
      background: linear-gradient(90deg, var(--blue), var(--purple));
    }

    /* ── Allocation section ── */
    .alloc-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
      gap: 12px;
      margin-bottom: 24px;
    }
    .alloc-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 14px 16px;
      position: relative;
      overflow: hidden;
    }
    .alloc-card::before {
      content: '';
      position: absolute; top: 0; left: 0;
      width: 4px; height: 100%;
    }
    .alloc-card.buy::before  { background: var(--green); }
    .alloc-card.sell::before { background: var(--red);   }
    .alloc-top {
      display: flex; justify-content: space-between; align-items: flex-start;
      margin-bottom: 10px;
    }
    .alloc-symbol { font-weight: 700; font-size: 15px; }
    .alloc-inr    { font-size: 14px; font-weight: 700; }
    .alloc-usd    { font-size: 11px; color: var(--muted); }
    .alloc-pct-bar {
      height: 4px; background: var(--surface2); border-radius: 2px; overflow: hidden;
    }
    .alloc-pct-fill {
      height: 100%; border-radius: 2px;
      background: linear-gradient(90deg, var(--green), var(--blue));
    }
    .alloc-pct-label {
      font-size: 11px; color: var(--muted); margin-top: 5px; text-align: right;
    }

    /* ── Empty / loading states ── */
    .empty-state {
      text-align: center; padding: 60px 20px;
      color: var(--muted);
    }
    .empty-state .icon { font-size: 48px; margin-bottom: 12px; }
    .empty-state p { font-size: 14px; }

    .spinner {
      width: 32px; height: 32px;
      border: 3px solid var(--border);
      border-top-color: var(--blue);
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
      margin: 0 auto 12px;
    }
    @keyframes spin { to { transform: rotate(360deg); } }

    /* ── Toast ── */
    #toast {
      position: fixed; bottom: 24px; right: 24px;
      background: var(--surface2);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px 18px;
      font-size: 13px;
      opacity: 0;
      transform: translateY(10px);
      transition: opacity 0.3s, transform 0.3s;
      z-index: 999;
      max-width: 320px;
    }
    #toast.show { opacity: 1; transform: translateY(0); }
    #toast.success { border-left: 3px solid var(--green); }
    #toast.error   { border-left: 3px solid var(--red);   }

    /* ── Footer ── */
    footer {
      text-align: center;
      padding: 20px;
      font-size: 12px;
      color: var(--muted);
      border-top: 1px solid var(--border);
    }

    @media (max-width: 600px) {
      header { padding: 12px 16px; }
      main   { padding: 14px 12px; }
      .controls { padding: 10px 12px; }
    }

    /* Order Management Styles */
    .tabs {
      display: flex;
      border-bottom: 1px solid var(--border);
      gap: 8px;
      margin-bottom: 16px;
    }

    .tab {
      padding: 10px 20px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      color: var(--muted);
      border-bottom: 2px solid transparent;
      transition: all 0.2s;
    }

    .tab:hover { color: var(--text); }
    .tab.active { color: var(--blue); border-bottom-color: var(--blue); }

    .tab-content { display: none; }
    .tab-content.active { display: block; }

    .btn-sm {
      padding: 4px 10px;
      font-size: 11px;
      border-radius: 4px;
      border: 1px solid var(--border);
      background: var(--surface2);
      color: var(--text);
      cursor: pointer;
      margin-right: 4px;
      transition: all 0.2s;
    }

    .btn-sm:hover {
      background: var(--surface);
      border-color: var(--blue);
    }

    .btn-danger {
      border-color: var(--red);
      color: var(--red);
    }

    .btn-danger:hover {
      background: rgba(248,81,73,0.1);
    }

    /* Modal Styles */
    .modal {
      display: none;
      position: fixed;
      z-index: 1000;
      left: 0;
      top: 0;
      width: 100%;
      height: 100%;
      background: rgba(0,0,0,0.7);
      align-items: center;
      justify-content: center;
    }

    .modal-content {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      max-width: 600px;
      width: 90%;
      max-height: 90vh;
      overflow-y: auto;
    }

    .modal-header {
      padding: 16px 20px;
      border-bottom: 1px solid var(--border);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .modal-header h2 {
      font-size: 18px;
      font-weight: 600;
    }

    .modal-close {
      font-size: 24px;
      cursor: pointer;
      color: var(--muted);
      line-height: 1;
    }

    .modal-close:hover {
      color: var(--text);
    }

    .modal-body {
      padding: 20px;
    }

    .modal-footer {
      padding: 16px 20px;
      border-top: 1px solid var(--border);
      display: flex;
      justify-content: flex-end;
      gap: 10px;
    }

    .form-group {
      margin-bottom: 16px;
    }

    .form-group label {
      display: block;
      font-size: 13px;
      color: var(--muted);
      margin-bottom: 6px;
    }

    .form-group input {
      width: 100%;
      padding: 8px 12px;
      background: var(--surface2);
      border: 1px solid var(--border);
      border-radius: 6px;
      color: var(--text);
      font-size: 14px;
    }

    .form-group input:focus {
      outline: none;
      border-color: var(--blue);
    }
  </style>
</head>
<body>

<!-- ── Header ── -->
<header>
  <div class="logo">
    <div class="logo-icon">📈</div>
    <div>
      <h1>Momentum Signal Tracker</h1>
      <span>NIFTY 50 &amp; NIFTY 500 · Angel One Live Feed</span>
    </div>
  </div>
  <div class="header-right">
    <div class="status-pill" style="background:rgba(255,193,7,0.1);border-color:rgba(255,193,7,0.3);margin-right:12px" title="Trading Mode">
      <div class="dot" style="background:var(--yellow)"></div>
      <span id="trading-mode-text" style="color:var(--yellow);font-weight:600">LIVE MODE</span>
    </div>
    <!-- ── Balance Widget ── -->
    <div id="balance-widget" style="display:none;background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:6px 14px;font-size:12px;gap:0;flex-direction:column">
      <div style="font-size:10px;color:var(--muted);margin-bottom:4px;letter-spacing:0.5px;text-transform:uppercase">💼 Account Balance</div>
      <div style="display:flex;gap:16px;flex-wrap:wrap;align-items:center">
        <span title="Available Cash to Trade">
          <span style="color:var(--muted);font-size:10px">Available</span><br>
          <strong id="balance-credit" style="color:var(--green);font-size:14px">—</strong>
        </span>
        <span title="Used Margin / Debits">
          <span style="color:var(--muted);font-size:10px">Used</span><br>
          <strong id="balance-used" style="color:var(--red);font-size:14px">—</strong>
        </span>
        <span title="Net Balance (Cash + Collateral)">
          <span style="color:var(--muted);font-size:10px">Net</span><br>
          <strong id="balance-net" style="color:var(--blue);font-size:14px">—</strong>
        </span>
        <span title="Today's Total P&L (Unrealised + Realised)">
          <span style="color:var(--muted);font-size:10px">Today P&amp;L</span><br>
          <strong id="balance-m2m" style="font-size:14px">—</strong>
        </span>
      </div>
    </div>
    <div class="status-pill">
      <div class="dot" id="status-dot"></div>
      <span id="status-text">Idle</span>
    </div>
    <span id="session-info" style="font-size:11px;color:var(--muted);margin-right:12px;display:none">
      Session: <span id="session-time"></span>
    </span>
    <button class="btn btn-outline" id="btn-login" onclick="showLoginModal()">🔐 Login</button>
    <button class="btn btn-outline" id="btn-logout" onclick="handleLogout()" style="display:none">🚪 Logout</button>
    <span id="last-updated">—</span>
  </div>
</header>

<!-- ── Countdown bar ── -->
<div id="countdown-bar"><div id="countdown-fill"></div></div>

<!-- ── Controls ── -->
<div class="controls" style="display:none">
  <div class="ctrl-group">
    <label>Interval</label>
    <select id="interval">
      <option value="ONE_MINUTE">1 Min</option>
      <option value="FIVE_MINUTE" selected>5 Min</option>
      <option value="FIFTEEN_MINUTE">15 Min</option>
      <option value="THIRTY_MINUTE">30 Min</option>
    </select>
  </div>
  <div class="ctrl-group">
    <label>Top N</label>
    <input type="number" id="top-n" value="10" min="1" max="50" />
  </div>
  <div class="ctrl-group">
    <label>Capital (USD)</label>
    <input type="number" id="capital" value="10000" min="100" step="500" />
  </div>
  <div class="spacer"></div>
  <button class="btn btn-outline" id="btn-refresh" onclick="refreshAllData()" title="Refresh Orders & Positions">🔄 Refresh Data</button>
  <button class="btn btn-outline" id="btn-csv" onclick="downloadCSV()" disabled>⬇ CSV</button>
  <button class="btn btn-primary"  id="btn-scan" onclick="startScan()">▶ Start Scan</button>
  <button class="btn btn-outline"  id="btn-stop" onclick="stopScan()" disabled>⏹ Stop</button>
</div>

<!-- ── Main ── -->
<main style="display:none">

  <!-- Stats row -->
  <div class="stats-row">
    <div class="stat-card">
      <div class="label">Total Signals</div>
      <div class="value blue" id="stat-total">—</div>
      <div class="sub">qualifying stocks</div>
    </div>
    <div class="stat-card">
      <div class="label">BUY Signals</div>
      <div class="value green" id="stat-buy">—</div>
      <div class="sub">momentum up</div>
    </div>
    <div class="stat-card">
      <div class="label">SELL Signals</div>
      <div class="value red" id="stat-sell">—</div>
      <div class="sub">momentum down</div>
    </div>
    <div class="stat-card">
      <div class="label">F&amp;O Eligible</div>
      <div class="value yellow" id="stat-fno">—</div>
      <div class="sub">in derivatives</div>
    </div>
    <div class="stat-card">
      <div class="label">Breakouts</div>
      <div class="value" style="color:var(--purple)" id="stat-bo">—</div>
      <div class="sub">high-vol breakout</div>
    </div>
    <div class="stat-card">
      <div class="label">Scan #</div>
      <div class="value" id="stat-scan">0</div>
      <div class="sub">cycles completed</div>
    </div>
  </div>

  <!-- Signals table -->
  <div class="section-header">
    <span class="section-title">📊 Live Signals</span>
    <span id="signal-count" style="font-size:12px;color:var(--muted)"></span>
  </div>
  <div class="table-wrap">
    <table id="signals-table">
      <thead>
        <tr>
          <th>#</th>
          <th>Symbol</th>
          <th>Signal</th>
          <th>F&amp;O</th>
          <th>LTP (₹)</th>
          <th>RSI</th>
          <th>Momentum %</th>
          <th>Vol Ratio</th>
          <th>Breakout</th>
          <th>Score</th>
          <th>Entry</th>
          <th>TG1</th>
          <th>TG2</th>
          <th>TG3</th>
          <th>Stop Loss</th>
          <th>Trail Stop</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody id="signals-body">
        <tr>
          <td colspan="16">
            <div class="empty-state">
              <div class="icon">🔍</div>
              <p>Press <strong>Start Scan</strong> to fetch live signals</p>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <!-- Allocation section -->
  <div class="section-header">
    <span class="section-title">💰 Capital Allocation</span>
    <span id="alloc-total" style="font-size:12px;color:var(--muted)"></span>
  </div>
  <div class="alloc-grid" id="alloc-grid">
    <div style="color:var(--muted);font-size:13px;padding:20px 0">
      Allocation will appear after the first scan.
    </div>
  </div>

  <!-- ═══════════════════════════════════════════════════════════════════ -->
  <!-- ORDER MANAGEMENT SECTION -->
  <!-- ═══════════════════════════════════════════════════════════════════ -->
  
  <div class="section-header" style="margin-top:32px">
    <span class="section-title">📋 My Orders & Positions</span>
  </div>

  <div class="tabs">
    <div class="tab active" onclick="showOrderTab('open-orders')">Open Orders</div>
    <div class="tab" onclick="showOrderTab('order-history')">Order History</div>
    <div class="tab" onclick="showOrderTab('positions')">Positions</div>
  </div>

  <!-- Open Orders Tab -->
  <div class="tab-content active" id="open-orders-tab">
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Order ID</th>
            <th>Symbol</th>
            <th>Side</th>
            <th>Type</th>
            <th>Qty</th>
            <th>Price</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody id="open-orders-body">
          <tr><td colspan="8" style="text-align:center;color:var(--muted);padding:20px">No open orders</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Order History Tab -->
  <div class="tab-content" id="order-history-tab">
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Order ID</th>
            <th>Symbol</th>
            <th>Side</th>
            <th>Type</th>
            <th>Qty</th>
            <th>Price</th>
            <th>Status</th>
            <th>Time</th>
          </tr>
        </thead>
        <tbody id="order-history-body">
          <tr><td colspan="8" style="text-align:center;color:var(--muted);padding:20px">No order history</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Positions Tab -->
  <div class="tab-content" id="positions-tab">
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Type</th>
            <th>Quantity</th>
            <th>Avg Price</th>
            <th>LTP</th>
            <th>P&L</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody id="positions-body">
          <tr><td colspan="7" style="text-align:center;color:var(--muted);padding:20px">No open positions</td></tr>
        </tbody>
      </table>
    </div>
  </div>

</main>

<footer>
  ⚠ For educational purposes only · Not financial advice · Data via Angel One SmartConnect
</footer>

<!-- Toast -->
<div id="toast"></div>

<!-- Angel One Login Modal -->
<div id="login-modal" class="modal" style="display:flex">
  <div class="modal-content" style="max-width:400px">
    <div class="modal-header">
      <h2>🔐 Angel One Login</h2>
      <span class="modal-close" onclick="closeLoginModal()">&times;</span>
    </div>
    <div class="modal-body">
      <form id="login-form" onsubmit="doLogin(); return false;">
        <div class="form-group">
          <label>Client ID</label>
          <input type="text" id="login-client-id" placeholder="Your Angel One Client ID" value="A291133" required autofocus>
        </div>
        <div class="form-group">
          <label>Password</label>
          <input type="password" id="login-password" placeholder="Your Trading Password" value="9595" required>
        </div>
        <div style="background:var(--surface2);padding:12px;border-radius:6px;font-size:12px;color:var(--muted);margin-top:12px">
          ℹ️ Using simplified login. API credentials are configured on the backend.
          <br><br>
          💡 <strong>Quick Login:</strong> Press <kbd style="background:var(--surface);padding:2px 6px;border-radius:3px;border:1px solid var(--border)">Enter</kbd> to login instantly
        </div>
      </form>
    </div>
    <div class="modal-footer">
      <button class="btn btn-primary" type="button" id="login-submit-btn">🚀 Login Now</button>
    </div>
  </div>
</div>

<script>
// ═══════════════════════════════════════════════════════════════════════
// SUPER SIMPLE LOGIN - NO COMPLEX CODE
// ═══════════════════════════════════════════════════════════════════════

let isLoggedIn = false;

// SIMPLE LOGIN FUNCTION
function doLogin() {
  console.log('LOGIN BUTTON CLICKED!');
  
  const btn = document.getElementById('login-submit-btn');
  btn.textContent = '⏳ Please wait...';
  btn.disabled = true;
  
  fetch('/auth/use-config-credentials', {
    method: 'POST',
    credentials: 'include'
  })
  .then(r => r.json())
  .then(d => {
    console.log('LOGIN RESPONSE:', d);
    if (d.status) {
      alert('✅ Login Success!');
      isLoggedIn = true;
      document.getElementById('login-modal').style.display = 'none';
      document.querySelector('main').style.display = 'block';
      document.querySelector('.controls').style.display = 'flex';
      document.getElementById('btn-logout').style.display = 'inline-block';
      fetchBalance();
    } else {
      alert('❌ Login Failed: ' + d.message);
      btn.textContent = '🚀 Login Now';
      btn.disabled = false;
    }
  })
  .catch(e => {
    console.error('LOGIN ERROR:', e);
    alert('❌ Error: ' + e.message);
    btn.textContent = '🚀 Login Now';
    btn.disabled = false;
  });
}

// ATTACH BUTTON CLICK - MULTIPLE WAYS TO ENSURE IT WORKS
window.addEventListener('load', function() {
  console.log('PAGE LOADED - ATTACHING LOGIN BUTTON');
  
  const btn = document.getElementById('login-submit-btn');
  if (btn) {
    // Method 1: onclick
    btn.onclick = function() {
      console.log('LOGIN BUTTON CLICKED VIA ONCLICK');
      doLogin();
      return false;
    };
    
    // Method 2: addEventListener
    btn.addEventListener('click', function(e) {
      e.preventDefault();
      console.log('LOGIN BUTTON CLICKED VIA ADDEVENTLISTENER');
      doLogin();
    });
    
    console.log('✅ LOGIN BUTTON READY');
  } else {
    console.error('❌ LOGIN BUTTON NOT FOUND!');
  }
});

// Check Python session on page load
async function checkPythonSession() {
  try {
    const res = await fetch(window.location.origin + '/auth/session', {
      credentials: 'include' // Include cookies
    });
    const data = await res.json();
    
    if (data.logged_in) {
      isLoggedIn = true;
      showSessionInfo(data.expires_in);
      return true;
    }
  } catch (err) {
    console.error('Session check failed:', err);
  }
  return false;
}

// Show session expiry info
function showSessionInfo(expiresIn) {
  const hours = Math.floor(expiresIn / 3600);
  const minutes = Math.floor((expiresIn % 3600) / 60);
  
  const sessionInfo = document.getElementById('session-info');
  const sessionTime = document.getElementById('session-time');
  if (sessionInfo && sessionTime) {
    sessionInfo.style.display = 'inline';
    sessionTime.textContent = `${hours}h ${minutes}m remaining`;
  }
}

// Fetch and display balance
async function fetchBalance() {
  try {
    const res = await fetch(window.location.origin + '/funds', { credentials: 'include' });
    const data = await res.json();
    if (data.status && data.data) {
      const d = data.data;
      const fmt = v => '₹' + Number(v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      const m2m = d.today_pnl || (d.m2munrealized || 0) + (d.m2mrealized || 0);

      document.getElementById('balance-credit').textContent = fmt(d.availablecash || 0);
      document.getElementById('balance-used').textContent   = fmt(d.utiliseddebits || 0);
      document.getElementById('balance-net').textContent    = fmt(d.net || 0);

      const m2mEl = document.getElementById('balance-m2m');
      m2mEl.textContent = (m2m >= 0 ? '+' : '') + fmt(m2m);
      m2mEl.style.color = m2m >= 0 ? 'var(--green)' : 'var(--red)';

      document.getElementById('balance-widget').style.display = 'flex';
    }
  } catch (err) {
    console.error('Balance fetch failed:', err);
  }
}

// Ensure content stays hidden until login
function enforceLoginProtection() {
  const mainEl = document.querySelector('main');
  const controlsEl = document.querySelector('.controls');
  const modalEl = document.getElementById('login-modal');
  const loginBtn = document.getElementById('btn-login');
  const logoutBtn = document.getElementById('btn-logout');
  
  if (!isLoggedIn) {
    if (mainEl) mainEl.style.display = 'none';
    if (controlsEl) controlsEl.style.display = 'none';
    if (modalEl) modalEl.style.display = 'flex';
    if (loginBtn) loginBtn.style.display = 'inline-block';
    if (logoutBtn) logoutBtn.style.display = 'none';
  } else {
    if (mainEl) mainEl.style.display = 'block';
    if (controlsEl) controlsEl.style.display = 'flex';
    if (modalEl) modalEl.style.display = 'none';
    if (loginBtn) loginBtn.style.display = 'none';
    if (logoutBtn) logoutBtn.style.display = 'inline-block';
  }
}

// Check session on load
checkPythonSession().then(sessionValid => {
  if (sessionValid) {
    console.log('Python session valid - user logged in');
    fetchBalance();
  }
  enforceLoginProtection();
});

// Call immediately
enforceLoginProtection();

// OLD FUNCTION REMOVED - NOW USING doLogin() ABOVE

function handleLogout() {
  console.log('Logout called');
  
  if (confirm('Are you sure you want to logout?')) {
    // Call Python logout endpoint
    fetch(window.location.origin + '/auth/logout', {
      method: 'POST',
      credentials: 'include'
    })
    .then(res => res.json())
    .then(data => {
      isLoggedIn = false;
      
      // Hide main content immediately
      enforceLoginProtection();
      
      // Stop any scanning
      if (window.scanInterval) {
        clearInterval(window.scanInterval);
        window.scanInterval = null;
      }
      if (window.countdownInterval) {
        clearInterval(window.countdownInterval);
        window.countdownInterval = null;
      }
      
      alert('✅ Logged out successfully! Python session destroyed.');
    })
    .catch(err => {
      console.error('Logout error:', err);
      // Force logout even if API fails
      isLoggedIn = false;
      enforceLoginProtection();
    });
  }
}

function closeLoginModal() {
  if (!isLoggedIn) {
    alert('Please login to continue');
    return;
  }
  document.getElementById('login-modal').style.display = 'none';
}

// Attach event listener when page loads
document.addEventListener('DOMContentLoaded', function() {
  // Enforce protection on load
  enforceLoginProtection();
  console.log('Page loaded - login protection enforced');
});

// Also enforce protection every 1 second as backup
setInterval(enforceLoginProtection, 1000);
</script>

<script>
  // Always use the same origin so it works on localhost, Vercel, or any custom domain.
  const API = window.location.origin;

  let scanInterval = null;
  let countdownInterval = null;
  let scanCount = 0;
  let refreshSecs = 100;
  let remaining = 100;
  let lastData = null;

  // ═══════════════════════════════════════════════════════════════════════
  // LOGIN MANAGEMENT
  // ═══════════════════════════════════════════════════════════════════════

  function showLoginModal() {
    document.getElementById('login-modal').style.display = 'flex';
    // Hide main content
    document.querySelector('main').style.display = 'none';
    document.querySelector('.controls').style.display = 'none';
  }

  function hideLoginModal() {
    document.getElementById('login-modal').style.display = 'none';
    document.querySelector('main').style.display = 'block';
    document.querySelector('.controls').style.display = 'flex';
  }

  async function submitLogin() {
    console.log('submitLogin called');
    
    const clientId = document.getElementById('login-client-id').value;
    const password = document.getElementById('login-password').value;

    console.log('Client ID:', clientId);
    console.log('Password:', password ? '***' : 'empty');

    if (!clientId || !password) {
      toast('Please fill Client ID and Password', 'error');
      return;
    }

    // Verify credentials match config
    if (clientId !== 'A291133' || password !== '9595') {
      toast('Invalid Client ID or Password', 'error');
      return;
    }

    // Show loading
    const loginBtn = document.getElementById('login-submit-btn');
    if (loginBtn) {
      loginBtn.textContent = 'Logging in...';
      loginBtn.disabled = true;
    }

    // Use config credentials for actual login
    try {
      console.log('Calling backend...');
      const res = await fetch(`${API}/auth/use-config-credentials`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      const data = await res.json();
      console.log('Backend response:', data);

      if (data.status) {
        isLoggedIn = true;
        toast('Login successful!', 'success');
        hideLoginModal();
        fetchBalance();
        const headerBtn = document.getElementById('btn-login');
        if (headerBtn) {
          headerBtn.textContent = '✅ Logged In';
          headerBtn.disabled = true;
        }
        
        // Clear form
        const form = document.getElementById('login-form');
        if (form) form.reset();
      } else {
        toast('Login failed: ' + (data.message || 'Backend connection error'), 'error');
        if (loginBtn) {
          loginBtn.textContent = 'Login';
          loginBtn.disabled = false;
        }
      }
    } catch (err) {
      console.error('[submitLogin] Error:', err);
      toast('Login failed: ' + err.message, 'error');
      if (loginBtn) {
        loginBtn.textContent = 'Login';
        loginBtn.disabled = false;
      }
    }
  }

  // ═══════════════════════════════════════════════════════════════════════

  // ── Toast ────────────────────────────────────────────────────────────────
  function toast(msg, type = 'success') {
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.className = `show ${type}`;
    clearTimeout(el._t);
    el._t = setTimeout(() => { el.className = ''; }, 3500);
  }

  // ── Status dot ───────────────────────────────────────────────────────────
  function setStatus(state, text) {
    const dot  = document.getElementById('status-dot');
    const span = document.getElementById('status-text');
    dot.className = 'dot ' + state;
    span.textContent = text;
  }

  // ── Countdown bar ────────────────────────────────────────────────────────
  function startCountdown() {
    remaining = refreshSecs;
    clearInterval(countdownInterval);
    countdownInterval = setInterval(() => {
      remaining = Math.max(0, remaining - 1);
      const pct = (remaining / refreshSecs) * 100;
      document.getElementById('countdown-fill').style.width = pct + '%';
    }, 1000);
  }

  // ── Fetch scan ───────────────────────────────────────────────────────────
  async function fetchScan() {
    const interval = document.getElementById('interval').value;
    const top      = document.getElementById('top-n').value;
    const capital  = document.getElementById('capital').value;

    setStatus('live', 'Scanning…');

    try {
      const res = await fetch(
        `${API}/scan?interval=${interval}&top=${top}&capital=${capital}`,
        { cache: 'no-store' }
      );
      if (!res.ok) {
        // Try to parse server-side error detail
        let detail = `HTTP ${res.status}`;
        try {
          const errBody = await res.json();
          detail = errBody.detail || errBody.error || detail;
        } catch (_) {}
        throw new Error(detail);
      }
      const data = await res.json();
      lastData = data;
      scanCount++;
      renderData(data);
      setStatus('live', 'Live');
      document.getElementById('last-updated').textContent =
        'Updated: ' + new Date().toLocaleTimeString('en-IN');
      document.getElementById('stat-scan').textContent = scanCount;
      document.getElementById('btn-csv').disabled = false;
      startCountdown();
    } catch (err) {
      setStatus('error', 'Error');
      toast('Scan failed: ' + err.message, 'error');
      console.error('[fetchScan]', err);
    }
  }

  // ── Render table ─────────────────────────────────────────────────────────
  function renderData(data) {
    const results = data.results || [];
    const body    = document.getElementById('signals-body');

    // Stats
    const buys     = results.filter(r => r.signal === 'BUY').length;
    const sells    = results.filter(r => r.signal === 'SELL').length;
    const fnos     = results.filter(r => r.fno).length;
    const bos      = results.filter(r => r.breakout).length;
    document.getElementById('stat-total').textContent = results.length;
    document.getElementById('stat-buy').textContent   = buys;
    document.getElementById('stat-sell').textContent  = sells;
    document.getElementById('stat-fno').textContent   = fnos;
    document.getElementById('stat-bo').textContent    = bos;
    document.getElementById('signal-count').textContent =
      `${results.length} signal(s) · ${data.interval} · ${data.scan_time?.slice(0,19)?.replace('T',' ')} IST`;

    if (results.length === 0) {
      body.innerHTML = `<tr><td colspan="16">
        <div class="empty-state">
          <div class="icon">😶</div>
          <p>No qualifying signals in this cycle. Market may be outside scan window.</p>
        </div></td></tr>`;
      renderAllocation([]);
      return;
    }

    body.innerHTML = results.map((r, i) => {
      const isBuy  = r.signal === 'BUY';
      const scoreW = Math.min(r.score, 100);
      return `
      <tr>
        <td><span class="rank-badge ${i < 3 ? 'top' : ''}">${r.rank}</span></td>
        <td class="symbol-cell">
          ${r.symbol}
          ${r.fno      ? '<span class="tag tag-fno" style="margin-left:4px">F&O</span>' : ''}
          ${r.breakout ? '<span class="tag tag-bo"  style="margin-left:2px">BO</span>'  : ''}
        </td>
        <td><span class="tag ${isBuy ? 'tag-buy' : 'tag-sell'}">${r.signal}</span></td>
        <td style="color:${r.fno ? 'var(--purple)' : 'var(--muted)'}">${r.fno ? 'YES' : 'NO'}</td>
        <td><strong>₹${fmt(r.ltp)}</strong></td>
        <td style="color:${rsiColor(r.rsi)}">${r.rsi != null ? r.rsi.toFixed(1) : '—'}</td>
        <td style="color:${r.momentum_pct >= 0 ? 'var(--green)' : 'var(--red)'}">
          ${r.momentum_pct != null ? (r.momentum_pct >= 0 ? '+' : '') + r.momentum_pct.toFixed(2) + '%' : '—'}
        </td>
        <td>
          <div class="bar-wrap">
            <div class="bar-bg"><div class="bar-fill" style="width:${Math.min((r.volume_ratio||0)/3*100,100)}%"></div></div>
            ${r.volume_ratio != null ? r.volume_ratio.toFixed(2) + 'x' : '—'}
          </div>
        </td>
        <td style="color:${r.breakout ? 'var(--yellow)' : 'var(--muted)'}">
          ${r.breakout ? '✓ YES' : 'NO'}
        </td>
        <td>
          <div class="bar-wrap">
            <div class="bar-bg"><div class="bar-fill" style="width:${scoreW}%"></div></div>
            <strong>${r.score?.toFixed(1)}</strong>
          </div>
        </td>
        <td>₹${fmt(r.entry)}</td>
        <td style="color:${isBuy?'var(--green)':'var(--red)'}">₹${fmt(r.tg1)}</td>
        <td style="color:${isBuy?'var(--green)':'var(--red)'}">₹${fmt(r.tg2)}</td>
        <td style="color:${isBuy?'var(--green)':'var(--red)'}">₹${fmt(r.tg3)}</td>
        <td style="color:var(--red)">₹${fmt(r.stop_loss)}</td>
        <td style="color:var(--yellow)">₹${fmt(r.trailing_stop)}</td>
        <td>
          <button class="btn-sm" onclick="placeQuickOrder('${r.symbol}', '${r.symboltoken || ''}', '${isBuy ? 'BUY' : 'SELL'}', 'MARKET', ${r.ltp}, ${r.entry}, ${r.stop_loss}, ${r.tg1})" style="background:${isBuy?'rgba(63,185,80,0.1)':'rgba(248,81,73,0.1)'};color:${isBuy?'var(--green)':'var(--red)'};border-color:${isBuy?'var(--green)':'var(--red)'}">
            ${isBuy ? '🟢 BUY' : '🔴 SELL'}
          </button>
        </td>
      </tr>`;
    }).join('');

    renderAllocation(results);
  }

  function rsiColor(v) {
    if (v == null) return 'var(--muted)';
    if (v >= 70)   return 'var(--red)';
    if (v >= 55)   return 'var(--green)';
    if (v <= 30)   return 'var(--red)';
    return 'var(--muted)';
  }

  function fmt(v) {
    if (v == null) return '—';
    return Number(v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  // ── Render allocation ────────────────────────────────────────────────────
  function renderAllocation(results) {
    const grid    = document.getElementById('alloc-grid');
    const capital = parseFloat(document.getElementById('capital').value) || 10000;
    const usdInr  = 84;
    const totalInr = capital * usdInr;

    if (!results.length) {
      grid.innerHTML = '<div style="color:var(--muted);font-size:13px;padding:20px 0">No signals to allocate.</div>';
      document.getElementById('alloc-total').textContent = '';
      return;
    }

    document.getElementById('alloc-total').textContent =
      `Total: ${capital.toLocaleString()} USD · ₹${totalInr.toLocaleString('en-IN')}`;

    grid.innerHTML = results.map(r => {
      const inr  = r.alloc_inr || 0;
      const usd  = r.alloc_usd || 0;
      const pct  = totalInr > 0 ? (inr / totalInr * 100) : 0;
      const isBuy = r.signal === 'BUY';
      return `
      <div class="alloc-card ${isBuy ? 'buy' : 'sell'}">
        <div class="alloc-top">
          <div>
            <div class="alloc-symbol">${r.symbol}</div>
            <div style="margin-top:3px">
              <span class="tag ${isBuy ? 'tag-buy' : 'tag-sell'}">${r.signal}</span>
              ${r.fno ? '<span class="tag tag-fno" style="margin-left:4px">F&O</span>' : ''}
            </div>
          </div>
          <div style="text-align:right">
            <div class="alloc-inr">₹${Math.round(inr).toLocaleString('en-IN')}</div>
            <div class="alloc-usd">${usd.toFixed(2)}</div>
          </div>
        </div>
        <div class="alloc-pct-bar">
          <div class="alloc-pct-fill" style="width:${pct}%"></div>
        </div>
        <div class="alloc-pct-label">${pct.toFixed(1)}% of capital · Score ${r.score?.toFixed(1)}</div>
      </div>`;
    }).join('');
  }

  // ── Start / Stop ─────────────────────────────────────────────────────────
  function startScan() {
    refreshSecs = 100;
    fetchScan();
    scanInterval = setInterval(fetchScan, refreshSecs * 1000);
    document.getElementById('btn-scan').disabled = true;
    document.getElementById('btn-stop').disabled = false;
    toast('Scan started — refreshes every 100 s', 'success');
  }

  function stopScan() {
    if (scanInterval) clearInterval(scanInterval);
    clearInterval(countdownInterval);
    scanInterval = null;
    document.getElementById('btn-scan').disabled = false;
    document.getElementById('btn-stop').disabled = true;
    document.getElementById('countdown-fill').style.width = '100%';
    toast('Scan stopped', 'success');
  }

  // ── Refresh All Data ──────────────────────────────────────────────────────
  async function refreshAllData() {
    const btn = document.getElementById('btn-refresh');
    btn.disabled = true;
    btn.textContent = '⏳ Refreshing...';
    
    try {
      // Refresh based on active tab
      const activeTab = document.querySelector('.tab-content.active');
      if (activeTab) {
        if (activeTab.id === 'open-orders-tab') {
          await fetchOpenOrders();
        } else if (activeTab.id === 'order-history-tab') {
          await fetchOrderHistory();
        } else if (activeTab.id === 'positions-tab') {
          await fetchPositions();
        }
      }
      toast('Data refreshed successfully', 'success');
    } catch (err) {
      toast('Refresh failed: ' + err.message, 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = '🔄 Refresh Data';
    }
  }

  // ── Update Session Timer ──────────────────────────────────────────────────
  function updateSessionTimer() {
    const loginTime = localStorage.getItem('angel_login_time');
    const sessionExpiry = localStorage.getItem('angel_session_expiry');
    
    if (!loginTime || !sessionExpiry) return;
    
    const now = new Date().getTime();
    const expiry = parseInt(sessionExpiry);
    const remaining = expiry - now;
    
    if (remaining <= 0) {
      document.getElementById('session-info').style.display = 'none';
      return;
    }
    
    const hours = Math.floor(remaining / (1000 * 60 * 60));
    const minutes = Math.floor((remaining % (1000 * 60 * 60)) / (1000 * 60));
    
    const sessionInfo = document.getElementById('session-info');
    const sessionTime = document.getElementById('session-time');
    sessionInfo.style.display = 'inline';
    sessionTime.textContent = `${hours}h ${minutes}m remaining`;
  }

  // ── CSV download ─────────────────────────────────────────────────────────
  async function downloadCSV() {
    const interval = document.getElementById('interval').value;
    const top      = document.getElementById('top-n').value;
    const capital  = document.getElementById('capital').value;
    const url = `${API}/scan/csv?interval=${interval}&top=${top}&capital=${capital}`;
    window.open(url, '_blank');
    toast('CSV download started', 'success');
  }

  // ═══════════════════════════════════════════════════════════════════════
  // ORDER MANAGEMENT FUNCTIONS
  // ═══════════════════════════════════════════════════════════════════════

  let tradingMode = 'PAPER';

  // ── Show Order Tab ────────────────────────────────────────────────────
  function showOrderTab(tabName) {
    // Hide all tabs
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    
    // Show selected tab
    event.target.classList.add('active');
    document.getElementById(`${tabName}-tab`).classList.add('active');
    
    // Refresh data for the selected tab
    if (tabName === 'open-orders') {
      fetchOpenOrders();
    } else if (tabName === 'order-history') {
      fetchOrderHistory();
    } else if (tabName === 'positions') {
      fetchPositions();
    }
  }

  // ── Quick Order from Signal ───────────────────────────────────────────
  async function placeQuickOrder(symbol, symboltoken, side, ordertype, ltp, entry, stopLoss, target) {
    // Confirmation dialog with details
    const confirmMsg = `
📊 Order Confirmation

Symbol: ${symbol}
Side: ${side}
Type: ${ordertype}
LTP: ₹${ltp}
Entry: ₹${entry}
Stop Loss: ₹${stopLoss}
Target: ₹${target}

Place this order?`;

    if (!confirm(confirmMsg)) {
      return;
    }

    // Show loading
    toast('⏳ Placing order...', 'success');

    const orderData = {
      symbol: symbol,
      symboltoken: symboltoken,
      transactiontype: side,
      ordertype: ordertype,
      producttype: 'INTRADAY',
      quantity: 1,
      stop_loss: stopLoss,
      target: target
    };

    try {
      const res = await fetch(`${API}/orders/place`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(orderData)
      });
      const data = await res.json();

      if (data.status) {
        toast(`✅ Order placed successfully! ID: ${data.data?.orderid || 'Success'}`, 'success');
        // Auto refresh orders and positions
        setTimeout(() => {
          fetchOpenOrders();
          fetchPositions();
        }, 1000);
      } else {
        toast(`❌ Order failed: ${data.message}`, 'error');
      }
    } catch (err) {
      console.error('[placeQuickOrder]', err);
      toast('❌ Order placement failed: ' + err.message, 'error');
    }
  }

  // ── Fetch Open Orders ─────────────────────────────────────────────────
  async function fetchOpenOrders() {
    try {
      const res = await fetch(`${API}/orders/open`);
      const data = await res.json();

      if (data.status) {
        renderOpenOrders(data.data || []);
      }
    } catch (err) {
      console.error('[fetchOpenOrders]', err);
    }
  }

  // ── Render Open Orders ────────────────────────────────────────────────
  function renderOpenOrders(orders) {
    const tbody = document.getElementById('open-orders-body');
    if (!tbody) return;

    if (orders.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--muted);padding:20px">No open orders</td></tr>';
      return;
    }

    tbody.innerHTML = orders.map(o => `
      <tr>
        <td style="font-family:monospace;font-size:11px">${o.order_id}</td>
        <td><strong>${o.symbol}</strong></td>
        <td><span class="tag ${o.transactiontype === 'BUY' ? 'tag-buy' : 'tag-sell'}">${o.transactiontype}</span></td>
        <td>${o.ordertype}</td>
        <td>${o.quantity}</td>
        <td>₹${o.price?.toFixed(2) || '—'}</td>
        <td><span class="tag tag-bo">${o.status}</span></td>
        <td>
          <button class="btn-sm btn-danger" onclick="cancelOrder('${o.order_id}')">Cancel</button>
        </td>
      </tr>
    `).join('');
  }

  // ── Cancel Order ──────────────────────────────────────────────────────
  async function cancelOrder(orderId) {
    if (!confirm(`Cancel order ${orderId}?`)) return;

    try {
      const res = await fetch(`${API}/orders/cancel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ order_id: orderId, variety: 'NORMAL' })
      });
      const data = await res.json();

      if (data.status) {
        toast('Order cancelled', 'success');
        fetchOpenOrders();
      } else {
        toast('Cancel failed: ' + data.message, 'error');
      }
    } catch (err) {
      console.error('[cancelOrder]', err);
      toast('Cancel failed', 'error');
    }
  }

  // ── Fetch Order History ───────────────────────────────────────────────
  async function fetchOrderHistory() {
    try {
      const res = await fetch(`${API}/orders/history`);
      const data = await res.json();

      if (data.status) {
        renderOrderHistory(data.data || []);
      }
    } catch (err) {
      console.error('[fetchOrderHistory]', err);
    }
  }

  // ── Render Order History ──────────────────────────────────────────────
  function renderOrderHistory(orders) {
    const tbody = document.getElementById('order-history-body');
    if (!tbody) return;

    if (orders.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--muted);padding:20px">No order history</td></tr>';
      return;
    }

    tbody.innerHTML = orders.slice(0, 20).map(o => `
      <tr>
        <td style="font-family:monospace;font-size:11px">${o.order_id}</td>
        <td><strong>${o.symbol}</strong></td>
        <td><span class="tag ${o.transactiontype === 'BUY' ? 'tag-buy' : 'tag-sell'}">${o.transactiontype}</span></td>
        <td>${o.ordertype}</td>
        <td>${o.quantity}</td>
        <td>₹${o.price?.toFixed(2) || '—'}</td>
        <td><span class="tag ${o.status === 'complete' ? 'tag-buy' : 'tag-sell'}">${o.status}</span></td>
        <td style="font-size:11px;color:var(--muted)">${formatTime(o.updated_at)}</td>
      </tr>
    `).join('');
  }

  // ── Fetch Positions ───────────────────────────────────────────────────
  async function fetchPositions() {
    try {
      const res = await fetch(`${API}/positions`);
      const data = await res.json();

      if (data.status) {
        renderPositions(data.data || []);
      }
    } catch (err) {
      console.error('[fetchPositions]', err);
    }
  }

  // ── Render Positions ──────────────────────────────────────────────────
  function renderPositions(positions) {
    const tbody = document.getElementById('positions-body');
    if (!tbody) return;

    if (positions.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--muted);padding:20px">No open positions</td></tr>';
      return;
    }

    tbody.innerHTML = positions.map(p => {
      const pnlColor = p.pnl >= 0 ? 'green' : 'red';
      const pnlSign = p.pnl >= 0 ? '+' : '';
      return `
      <tr>
        <td><strong>${p.symbol}</strong></td>
        <td>${p.quantity > 0 ? 'LONG' : 'SHORT'}</td>
        <td>${Math.abs(p.quantity)}</td>
        <td>₹${p.buy_avg_price?.toFixed(2) || '—'}</td>
        <td>₹${p.ltp?.toFixed(2) || '—'}</td>
        <td style="color:var(--${pnlColor})"><strong>${pnlSign}₹${Math.abs(p.pnl || 0).toFixed(2)}</strong></td>
        <td>
          <button class="btn-sm btn-danger" onclick="exitPosition('${p.symbol}', '${p.symboltoken}', ${p.quantity}, '${p.producttype}')">Exit</button>
        </td>
      </tr>
    `;
    }).join('');
  }

  // ── Exit Position ─────────────────────────────────────────────────────
  async function exitPosition(symbol, symboltoken, quantity, producttype) {
    if (!confirm(`Exit position in ${symbol}?`)) return;

    const orderData = {
      symbol: symbol,
      symboltoken: symboltoken,
      transactiontype: quantity > 0 ? 'SELL' : 'BUY',
      ordertype: 'MARKET',
      producttype: producttype,
      quantity: Math.abs(quantity)
    };

    try {
      const res = await fetch(`${API}/orders/place`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(orderData)
      });
      const data = await res.json();

      if (data.status) {
        toast(`Position exited: ${symbol}`, 'success');
        fetchPositions();
        fetchOpenOrders();
      } else {
        toast(`Exit failed: ${data.message}`, 'error');
      }
    } catch (err) {
      console.error('[exitPosition]', err);
      toast('Exit failed', 'error');
    }
  }

  // ── Format Time ───────────────────────────────────────────────────────
  function formatTime(isoString) {
    if (!isoString) return '—';
    try {
      const date = new Date(isoString);
      return date.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
    } catch {
      return '—';
    }
  }

  // ── Auto-refresh orders/positions every 10 seconds ────────────────────
  setInterval(() => {
    const activeTab = document.querySelector('.tab-content.active');
    if (activeTab && activeTab.id === 'open-orders-tab') {
      fetchOpenOrders();
    } else if (activeTab && activeTab.id === 'positions-tab') {
      fetchPositions();
    }
  }, 10000);

  // ── Auto-refresh balance every 60 seconds ────────────────────────────
  setInterval(() => { if (isLoggedIn) fetchBalance(); }, 60000);

</script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def root(request: Request, session_token: Optional[str] = Cookie(None)):
    """Serve the main page."""
    return HTMLResponse(content=_INDEX_HTML)


@app.get("/logout")
async def logout(session_token: Optional[str] = Cookie(None)):
    """Logout - destroy session and redirect to login"""
    if session_token:
        delete_session(session_token)
    
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("session_token")
    return response


@app.get("/health")
def health():
    """Quick connectivity and login check."""
    try:
        api = _get_api()
        return JSONResponse({
            "status":     "ok",
            "server_ip":  api._server_ip,
            "session":    "active" if api._jwt_token else "none",
            "time_ist":   datetime.now().isoformat(),
        })
    except Exception as exc:
        return JSONResponse({"status": "error", "detail": str(exc)}, status_code=500)


@app.get("/debug")
def debug_scan(
    interval: str = Query("FIVE_MINUTE"),
    n:        int = Query(5),
):
    """
    Return raw indicator values for the first N symbols so we can see
    exactly what's failing the signal filter.
    """
    import indicators as ind
    import signals as sig
    from angel_connector import _CANDLE_CACHE

    api      = _get_api()
    universe = _get_universe()[:n]
    now      = datetime.now()

    all_quotes = api.fetch_and_cache_all(universe)
    out = []

    for sym_info in universe:
        token  = sym_info["token"]
        symbol = sym_info["symbol"]
        quote  = all_quotes.get(token, {})

        api.update_candle_cache(token, quote)

        import threading
        from angel_connector import _CACHE_LOCK
        with _CACHE_LOCK:
            from angel_connector import _CANDLE_CACHE
            candles = list(_CANDLE_CACHE.get(token, []))

        n_bars = len(candles)
        ltp    = float(quote.get("ltp", 0))
        open_p = float(quote.get("open", ltp))
        vol    = int(quote.get("tradeVolume", quote.get("volume", 0)))

        # Compute raw indicators
        rsi_val  = None
        ema_f    = None
        ema_s    = None
        mom_val  = None
        if candles:
            closes = [c["close"] for c in candles]
            rp = min(14, max(len(candles)-1, 2))
            ef = min(9,  max(len(candles)-1, 2))
            es = min(21, max(len(candles)-1, 2))
            mp = min(10, max(len(candles)-1, 2))
            from indicators import rsi_current, ema_current, momentum_current
            rsi_val = rsi_current(candles, rp)
            ema_f   = ema_current(candles, ef)
            ema_s   = ema_current(candles, es)
            mom_val = momentum_current(candles, mp)

        # Detect signal
        ind_dict = {
            "rsi": rsi_val, "ema_trend": None, "momentum": mom_val,
            "volume_ratio": None, "ltp": ltp, "open": open_p,
        }
        if ema_f and ema_s:
            ind_dict["ema_trend"] = "bullish" if ema_f > ema_s else "bearish"

        signal = sig.detect_signal(ind_dict)

        out.append({
            "symbol":      symbol,
            "token":       token,
            "n_bars":      n_bars,
            "ltp":         ltp,
            "open":        open_p,
            "volume":      vol,
            "rsi":         round(rsi_val, 2) if rsi_val is not None else None,
            "ema_fast":    round(ema_f,   2) if ema_f   is not None else None,
            "ema_slow":    round(ema_s,   2) if ema_s   is not None else None,
            "momentum":    round(mom_val, 3) if mom_val is not None else None,
            "ema_trend":   ind_dict["ema_trend"],
            "signal":      signal,
            "quote_keys":  list(quote.keys()) if quote else [],
        })

    return JSONResponse({"time": now.isoformat(), "symbols": out})


@app.get("/scan")
def scan_json(
    interval: str  = Query("FIVE_MINUTE"),
    top:      int  = Query(10),
    capital:  float= Query(10000),
    warm:     int  = Query(2, description="Extra warm-up passes to populate candle cache (0-5)"),
):
    config.CANDLE_INTERVAL = interval
    config.TOP_N           = top
    config.CAPITAL_USD     = capital

    api      = _get_api()
    universe = _get_universe()
    now      = datetime.now()

    # Warm up the candle cache with extra passes so cold-start instances
    # accumulate enough bars for meaningful indicator calculation.
    warm_passes = max(0, min(int(warm), 5))
    for _ in range(warm_passes):
        try:
            all_q = api.fetch_and_cache_all(universe)
            for sym_info in universe:
                q = all_q.get(sym_info["token"])
                if q:
                    api.update_candle_cache(sym_info["token"], q)
        except Exception:
            break

    try:
        ranked = run_single_scan(universe, api)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)

    alloc   = sig.build_allocation(ranked)
    payload = []

    for i, stock in enumerate(ranked, 1):
        lvl = stock.get("levels", {})
        payload.append({
            "rank":          i,
            "symbol":        stock["symbol"],
            "signal":        stock["signal"],
            "fno":           stock["fno"],
            "ltp":           stock["ltp"],
            "rsi":           stock.get("rsi"),
            "ema_fast":      stock.get("ema_fast"),
            "ema_slow":      stock.get("ema_slow"),
            "ema_trend":     stock.get("ema_trend"),
            "momentum_pct":  stock.get("momentum"),
            "volume_ratio":  stock.get("volume_ratio"),
            "breakout":      stock.get("breakout"),
            "score":         stock["score"],
            "entry":         lvl.get("entry"),
            "tg1":           lvl.get("tg1"),
            "tg2":           lvl.get("tg2"),
            "tg3":           lvl.get("tg3"),
            "stop_loss":     lvl.get("stop_loss"),
            "trailing_stop": lvl.get("trailing_stop"),
            "alloc_inr":     alloc.get(stock["symbol"]),
            "alloc_usd":     round(alloc.get(stock["symbol"], 0) / config.USD_TO_INR, 2),
        })

    return JSONResponse({
        "scan_time":   now.isoformat(),
        "interval":    interval,
        "warm_passes": warm_passes,
        "count":       len(ranked),
        "results":     payload,
        "note":        "No signals found – market may be closed or cache is cold. Try ?warm=3 for more warm-up passes." if not ranked else None,
    })


@app.get("/scan/table", response_class=PlainTextResponse)
def scan_table(
    interval: str  = Query("FIVE_MINUTE"),
    top:      int  = Query(10),
    capital:  float= Query(10000),
    warm:     int  = Query(2, description="Extra warm-up passes (0-5)"),
):
    config.CANDLE_INTERVAL = interval
    config.TOP_N           = top
    config.CAPITAL_USD     = capital

    api      = _get_api()
    universe = _get_universe()
    now      = datetime.now()

    warm_passes = max(0, min(int(warm), 5))
    for _ in range(warm_passes):
        try:
            all_q = api.fetch_and_cache_all(universe)
            for sym_info in universe:
                q = all_q.get(sym_info["token"])
                if q:
                    api.update_candle_cache(sym_info["token"], q)
        except Exception:
            break

    ranked   = run_single_scan(universe, api)
    alloc    = sig.build_allocation(ranked)
    return fmt.format_table(ranked, alloc, now)


@app.get("/scan/csv")
def scan_csv(
    interval: str  = Query("FIVE_MINUTE"),
    top:      int  = Query(10),
    capital:  float= Query(10000),
    warm:     int  = Query(2, description="Extra warm-up passes (0-5)"),
):
    config.CANDLE_INTERVAL = interval
    config.TOP_N           = top
    config.CAPITAL_USD     = capital

    api      = _get_api()
    universe = _get_universe()
    now      = datetime.now()

    warm_passes = max(0, min(int(warm), 5))
    for _ in range(warm_passes):
        try:
            all_q = api.fetch_and_cache_all(universe)
            for sym_info in universe:
                q = all_q.get(sym_info["token"])
                if q:
                    api.update_candle_cache(sym_info["token"], q)
        except Exception:
            break

    ranked   = run_single_scan(universe, api)
    alloc    = sig.build_allocation(ranked)
    csv_data = fmt.to_csv(ranked, alloc, now)
    filename = f"signals_{now.strftime('%Y%m%d_%H%M%S')}.csv"

    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ──────────────────────────────────────────────────────────────────────────────
# AUTHENTICATION ENDPOINTS (Python Session-Based)
# ──────────────────────────────────────────────────────────────────────────────

@app.post("/auth/login")
def user_login(
    credentials: Dict[str, str] = Body(...),
    response: Response = None
):
    """
    Simple login with Client ID and Password.
    Validates against config.py credentials and creates Python session.
    """
    try:
        client_id = credentials.get("client_id", "").strip()
        password = credentials.get("password", "").strip()
        
        # Validate credentials
        if client_id != config.ANGEL_CLIENT_ID or password != config.ANGEL_PASSWORD:
            return JSONResponse({
                "status": False,
                "message": "Invalid Client ID or Password"
            }, status_code=401)
        
        # Create session
        session_token = create_session(client_id)
        
        # Set session cookie
        response = JSONResponse({
            "status": True,
            "message": "Login successful",
            "session_expires_in": SESSION_MAX_AGE
        })
        response.set_cookie(
            key="session_token",
            value=session_token,
            max_age=SESSION_MAX_AGE,
            httponly=True,
            samesite="lax"
        )
        
        return response
        
    except Exception as e:
        return JSONResponse({
            "status": False,
            "message": str(e)
        }, status_code=500)
        config.ANGEL_PASSWORD = credentials.get("password")
        config.ANGEL_API_KEY = credentials.get("api_key")
        config.ANGEL_TOTP_SECRET = credentials.get("totp_secret")
        
        # Force re-login with new credentials
        global _api
        _api = None
        
        # Try to get API (will trigger login)
        api = _get_api()
        
        return JSONResponse({
            "status": True,
            "message": "Login successful",
            "data": {
                "client_id": credentials.get("client_id"),
            }
        })
        
    except Exception as exc:
        logger.error(f"Login error: {exc}")
        return JSONResponse({
            "status": False,
            "message": f"Login failed: {str(exc)}",
        }, status_code=401)


@app.post("/auth/use-config-credentials")
def use_config_credentials(response: Response = None):
    """
    Quick login using credentials from config.py.
    Creates Python session cookie.
    """
    try:
        # Force re-login with config credentials
        global _api
        _api = None
        
        # Try to get API (will trigger login with config credentials)
        api = _get_api()
        
        # Create session
        session_token = create_session(config.ANGEL_CLIENT_ID)
        
        # Set session cookie
        response = JSONResponse({
            "status": True,
            "message": "Login successful",
            "data": {
                "client_id": config.ANGEL_CLIENT_ID,
            }
        })
        response.set_cookie(
            key="session_token",
            value=session_token,
            max_age=SESSION_MAX_AGE,
            httponly=True,
            samesite="lax"
        )
        
        return response
        
    except Exception as exc:
        return JSONResponse({
            "status": False,
            "message": f"Login failed: {str(exc)}",
        }, status_code=401)


@app.post("/auth/logout")
def logout(
    response: Response = None,
    session_token: Optional[str] = Cookie(None)
):
    """Logout and destroy session"""
    if session_token:
        delete_session(session_token)
    
    response = JSONResponse({
        "status": True,
        "message": "Logged out successfully"
    })
    response.delete_cookie("session_token")
    return response


@app.get("/auth/session")
def check_session(session_token: Optional[str] = Cookie(None)):
    """Check if session is valid"""
    session_data = verify_session(session_token)
    
    if session_data:
        remaining = int((session_data["expires_at"] - datetime.now()).total_seconds())
        return JSONResponse({
            "status": True,
            "logged_in": True,
            "user_id": session_data["user_id"],
            "expires_in": remaining
        })
    else:
        return JSONResponse({
            "status": True,
            "logged_in": False
        })


# ──────────────────────────────────────────────────────────────────────────────
# ORDER MANAGEMENT ENDPOINTS
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/trading/mode")
def get_trading_mode():
    """Get current trading mode (PAPER or LIVE)."""
    return JSONResponse({
        "trading_mode": config.TRADING_MODE,
        "paper_capital": config.PAPER_TRADING_CAPITAL,
    })


@app.post("/trading/mode")
def set_trading_mode(mode: Dict[str, str] = Body(...)):
    """Set trading mode to PAPER or LIVE."""
    new_mode = mode.get("mode", "PAPER").upper()
    if new_mode not in ("PAPER", "LIVE"):
        return JSONResponse({"status": False, "message": "Invalid mode. Use PAPER or LIVE"}, status_code=400)
    
    config.TRADING_MODE = new_mode
    order_service = _get_order_service()
    order_service.set_trading_mode(new_mode)
    
    logger.info(f"Trading mode set to {new_mode}")
    return JSONResponse({
        "status": True,
        "message": f"Trading mode set to {new_mode}",
        "trading_mode": new_mode,
    })


@app.post("/orders/place")
def place_order(order_data: Dict[str, Any] = Body(...)):
    """
    Place an order.
    
    Request body:
    {
        "symbol": "RELIANCE",
        "symboltoken": "2885",
        "exchange": "NSE",
        "transactiontype": "BUY",
        "ordertype": "MARKET",
        "producttype": "INTRADAY",
        "quantity": 10,
        "price": null,  // Required for LIMIT orders
        "triggerprice": null,  // Required for STOPLOSS orders
        "stop_loss": 490.0,  // Optional
        "target": 520.0  // Optional
    }
    """
    try:
        order_req = OrderRequest(
            symbol=order_data.get("symbol"),
            symboltoken=order_data.get("symboltoken"),
            exchange=order_data.get("exchange", "NSE"),
            transactiontype=order_data.get("transactiontype", "BUY"),
            ordertype=order_data.get("ordertype", "MARKET"),
            producttype=order_data.get("producttype", "INTRADAY"),
            quantity=int(order_data.get("quantity", 1)),
            price=float(order_data["price"]) if order_data.get("price") is not None else None,
            triggerprice=float(order_data["triggerprice"]) if order_data.get("triggerprice") is not None else None,
            duration=order_data.get("duration", "DAY"),
            variety=order_data.get("variety", "NORMAL"),
            stop_loss=float(order_data["stop_loss"]) if order_data.get("stop_loss") is not None else None,
            target=float(order_data["target"]) if order_data.get("target") is not None else None,
        )
        
        # Get current LTP for this symbol
        api = _get_api()
        ltp_data = api.get_ltp([order_req.symboltoken])
        current_ltp = ltp_data.get(order_req.symboltoken, 0.0)
        
        # Place order
        order_service = _get_order_service()
        result = order_service.place_order(order_req, current_ltp)
        
        return JSONResponse(result)
        
    except Exception as exc:
        logger.error(f"Order placement error: {exc}")
        return JSONResponse({
            "status": False,
            "message": f"Order placement failed: {str(exc)}",
        }, status_code=500)


@app.post("/orders/modify")
def modify_order(modify_data: Dict[str, Any] = Body(...)):
    """
    Modify an existing order.
    
    Request body:
    {
        "order_id": "PAPER1001",
        "variety": "NORMAL",
        "ordertype": "LIMIT",
        "quantity": 15,  // Optional
        "price": 505.0   // Optional
    }
    """
    try:
        order_service = _get_order_service()
        result = order_service.modify_order(
            order_id=modify_data["order_id"],
            variety=modify_data.get("variety", "NORMAL"),
            ordertype=modify_data.get("ordertype", "LIMIT"),
            quantity=int(modify_data["quantity"]) if modify_data.get("quantity") is not None else None,
            price=float(modify_data["price"]) if modify_data.get("price") is not None else None,
        )
        return JSONResponse(result)
    except Exception as exc:
        logger.error(f"Order modification error: {exc}")
        return JSONResponse({"status": False, "message": str(exc)}, status_code=500)


@app.post("/orders/cancel")
def cancel_order(cancel_data: Dict[str, Any] = Body(...)):
    """
    Cancel an order.
    
    Request body:
    {
        "order_id": "PAPER1001",
        "variety": "NORMAL"
    }
    """
    try:
        order_service = _get_order_service()
        result = order_service.cancel_order(
            order_id=cancel_data["order_id"],
            variety=cancel_data.get("variety", "NORMAL"),
        )
        return JSONResponse(result)
    except Exception as exc:
        logger.error(f"Order cancellation error: {exc}")
        return JSONResponse({"status": False, "message": str(exc)}, status_code=500)


@app.get("/orders")
def get_orders():
    """Get all orders."""
    try:
        order_service = _get_order_service()
        orders = order_service.get_order_book()
        return JSONResponse({
            "status": True,
            "data": orders,
            "count": len(orders),
        })
    except Exception as exc:
        logger.error(f"Get orders error: {exc}")
        return JSONResponse({"status": False, "message": str(exc)}, status_code=500)


@app.get("/orders/open")
def get_open_orders():
    """Get open/pending orders."""
    try:
        order_service = _get_order_service()
        orders = order_service.get_order_book()
        open_orders = [o for o in orders if o.get("status") in ("open", "pending", "trigger pending")]
        return JSONResponse({
            "status": True,
            "data": open_orders,
            "count": len(open_orders),
        })
    except Exception as exc:
        logger.error(f"Get open orders error: {exc}")
        return JSONResponse({"status": False, "message": str(exc)}, status_code=500)


@app.get("/orders/history")
def get_order_history():
    """Get order history (completed/cancelled)."""
    try:
        order_service = _get_order_service()
        orders = order_service.get_order_book()
        history = [o for o in orders if o.get("status") in ("complete", "cancelled", "rejected")]
        return JSONResponse({
            "status": True,
            "data": sorted(history, key=lambda x: x.get("updated_at", ""), reverse=True),
            "count": len(history),
        })
    except Exception as exc:
        logger.error(f"Get order history error: {exc}")
        return JSONResponse({"status": False, "message": str(exc)}, status_code=500)


@app.get("/positions")
def get_positions():
    """Get current positions."""
    try:
        order_service = _get_order_service()
        positions = order_service.get_positions()
        
        # Update LTPs for P&L calculation
        if positions and config.TRADING_MODE == "PAPER":
            api = _get_api()
            tokens = [p.get("symboltoken") for p in positions if p.get("symboltoken")]
            if tokens:
                ltp_data = api.get_ltp(tokens)
                for pos in positions:
                    token = pos.get("symboltoken")
                    if token in ltp_data:
                        pos["ltp"] = ltp_data[token]
                        # Recalculate P&L
                        if pos["quantity"] > 0:
                            pos["pnl"] = (pos["ltp"] - pos["buy_avg_price"]) * pos["quantity"]
                        elif pos["quantity"] < 0:
                            pos["pnl"] = (pos["sell_avg_price"] - pos["ltp"]) * abs(pos["quantity"])
        
        return JSONResponse({
            "status": True,
            "data": positions,
            "count": len(positions),
        })
    except Exception as exc:
        logger.error(f"Get positions error: {exc}")
        return JSONResponse({"status": False, "message": str(exc)}, status_code=500)


@app.get("/trades")
def get_trades():
    """Get trade book (executed trades)."""
    try:
        order_service = _get_order_service()
        trades = order_service.get_trade_book()
        return JSONResponse({
            "status": True,
            "data": trades,
            "count": len(trades),
        })
    except Exception as exc:
        logger.error(f"Get trades error: {exc}")
        return JSONResponse({"status": False, "message": str(exc)}, status_code=500)


@app.get("/funds")
def get_funds():
    """Get REAL funds from Angel One account (always live, ignores trading mode)."""
    try:
        api = _get_api()

        def safe_float(v):
            try: return round(float(v), 2)
            except: return 0.0

        # Always call the real Angel One RMS endpoint for actual balance
        import requests as _req
        resp = _req.get(
            "https://apiconnect.angelbroking.com/rest/secure/angelbroking/user/v1/getRMS",
            headers={
                "Content-Type":     "application/json",
                "Accept":           "application/json",
                "X-UserType":       "USER",
                "X-SourceID":       "WEB",
                "X-ClientLocalIP":  api._server_ip,
                "X-ClientPublicIP": api._server_ip,
                "X-MACAddress":     "fe:80:00:00:00:00",
                "X-PrivateKey":     config.ANGEL_API_KEY,
                "Authorization":    f"Bearer {api._jwt_token}",
            },
            timeout=10,
        )
        resp.raise_for_status()
        result = resp.json()
        raw = result.get("data", {}) if result.get("status") else {}

        m2m_unrealized = safe_float(raw.get("m2munrealized", raw.get("m2mUnrealized", 0)))
        m2m_realized   = safe_float(raw.get("m2mrealized",   raw.get("m2mRealized",   0)))

        return JSONResponse({
            "status": True,
            "trading_mode": config.TRADING_MODE,
            "data": {
                "availablecash":  safe_float(raw.get("availablecash",  raw.get("net", 0))),
                "net":            safe_float(raw.get("net",            raw.get("availablecash", 0))),
                "utiliseddebits": safe_float(raw.get("utiliseddebits", 0)),
                "collateral":     safe_float(raw.get("collateral",     0)),
                "m2munrealized":  m2m_unrealized,
                "m2mrealized":    m2m_realized,
                "today_pnl":      round(m2m_unrealized + m2m_realized, 2),
            },
        })
    except Exception as exc:
        logger.error(f"Get funds error: {exc}")
        return JSONResponse({"status": False, "message": str(exc)}, status_code=500)


@app.post("/orders/calculate-quantity")
def calculate_quantity(calc_data: Dict[str, Any] = Body(...)):
    """
    Calculate recommended quantity based on risk management.
    
    Request body:
    {
        "capital": 100000,
        "risk_pct": 1.0,
        "entry_price": 500.0,
        "stop_loss_price": 490.0
    }
    """
    try:
        order_service = _get_order_service()
        quantity = order_service.calculate_position_size(
            capital=float(calc_data["capital"]),
            risk_pct=float(calc_data.get("risk_pct", 1.0)),
            entry_price=float(calc_data["entry_price"]),
            stop_loss_price=float(calc_data["stop_loss_price"]),
        )
        
        risk_per_share = abs(float(calc_data["entry_price"]) - float(calc_data["stop_loss_price"]))
        total_risk = risk_per_share * quantity
        position_value = float(calc_data["entry_price"]) * quantity
        
        return JSONResponse({
            "status": True,
            "data": {
                "recommended_quantity": quantity,
                "risk_per_share": round(risk_per_share, 2),
                "total_risk": round(total_risk, 2),
                "position_value": round(position_value, 2),
                "risk_pct": round((total_risk / float(calc_data["capital"])) * 100, 2),
            }
        })
    except Exception as exc:
        logger.error(f"Calculate quantity error: {exc}")
        return JSONResponse({"status": False, "message": str(exc)}, status_code=500)


@app.get("/trading/stats")
def get_trading_stats():
    """Get trading statistics."""
    try:
        order_service = _get_order_service()
        
        positions = order_service.get_positions()
        funds = order_service.get_rms_limits()
        orders = order_service.get_order_book()
        
        open_positions = len(positions)
        open_orders = len([o for o in orders if o.get("status") in ("open", "pending", "trigger pending")])
        completed_orders = len([o for o in orders if o.get("status") == "complete"])
        
        # Calculate today's P&L
        todays_pnl = sum(p.get("pnl", 0) for p in positions)
        
        return JSONResponse({
            "status": True,
            "data": {
                "available_funds": funds.get("availablecash", 0),
                "used_margin": funds.get("utiliseddebits", 0),
                "open_positions": open_positions,
                "todays_pnl": round(todays_pnl, 2),
                "open_orders": open_orders,
                "completed_orders": completed_orders,
                "trading_mode": config.TRADING_MODE,
            }
        })
    except Exception as exc:
        logger.error(f"Get trading stats error: {exc}")
        return JSONResponse({"status": False, "message": str(exc)}, status_code=500)
