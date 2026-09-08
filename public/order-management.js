/**
 * order-management.js
 * 
 * Angel One Order Management UI Module
 * Handles order placement, positions, and order book display.
 * 
 * To use: Include this script in index.html and call initOrderManagement()
 */

const OrderManagement = (() => {
  const API = window.location.origin;
  let tradingMode = 'PAPER';
  let refreshInterval = null;
  
  // ────────────────────────────────────────────────────────────────────────
  // INITIALIZATION
  // ────────────────────────────────────────────────────────────────────────
  
  function init() {
    fetchTradingMode();
    setupEventListeners();
    createOrderModal();
    createConfirmModal();
    refreshOrderData();
    
    // Auto-refresh every 10 seconds
    refreshInterval = setInterval(refreshOrderData, 10000);
  }
  
  function setupEventListeners() {
    // Trading mode toggle
    const modeToggle = document.getElementById('trading-mode-toggle');
    if (modeToggle) {
      modeToggle.addEventListener('change', handleModeToggle);
    }
  }
  
  // ────────────────────────────────────────────────────────────────────────
  // TRADING MODE
  // ────────────────────────────────────────────────────────────────────────
  
  async function fetchTradingMode() {
    try {
      const res = await fetch(`${API}/trading/mode`);
      const data = await res.json();
      tradingMode = data.trading_mode;
      updateModeUI(tradingMode);
    } catch (err) {
      console.error('[fetchTradingMode]', err);
    }
  }
  
  async function handleModeToggle(e) {
    const newMode = e.target.checked ? 'LIVE' : 'PAPER';
    
    if (newMode === 'LIVE') {
      const confirmed = confirm(
        '⚠️ WARNING: Switching to LIVE mode will place REAL orders with real money.\n\n' +
        'Are you sure you want to continue?'
      );
      if (!confirmed) {
        e.target.checked = false;
        return;
      }
    }
    
    try {
      const res = await fetch(`${API}/trading/mode`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: newMode })
      });
      const data = await res.json();
      
      if (data.status) {
        tradingMode = newMode;
        updateModeUI(newMode);
        toast(`Trading mode: ${newMode}`, newMode === 'LIVE' ? 'error' : 'success');
      } else {
        toast('Failed to change mode: ' + data.message, 'error');
        e.target.checked = tradingMode === 'LIVE';
      }
    } catch (err) {
      console.error('[handleModeToggle]', err);
      toast('Mode change failed', 'error');
      e.target.checked = tradingMode === 'LIVE';
    }
  }
  
  function updateModeUI(mode) {
    const badge = document.getElementById('trading-mode-badge');
    const toggle = document.getElementById('trading-mode-toggle');
    
    if (badge) {
      badge.textContent = mode;
      badge.className = `tag ${mode === 'LIVE' ? 'tag-sell' : 'tag-fno'}`;
    }
    
    if (toggle) {
      toggle.checked = mode === 'LIVE';
    }
    
    // Update all order buttons
    document.querySelectorAll('.order-btn').forEach(btn => {
      if (mode === 'LIVE') {
        btn.classList.add('live-mode');
      } else {
        btn.classList.remove('live-mode');
      }
    });
  }
  
  // ────────────────────────────────────────────────────────────────────────
  // ORDER PLACEMENT
  // ────────────────────────────────────────────────────────────────────────
  
  function openOrderModal(signalData, orderType) {
    const modal = document.getElementById('order-modal');
    const form = document.getElementById('order-form');
    
    // Populate form
    document.getElementById('order-symbol').value = signalData.symbol;
    document.getElementById('order-symboltoken').value = signalData.symboltoken || '';
    document.getElementById('order-ltp').textContent = `₹${signalData.ltp?.toFixed(2) || '0.00'}`;
    
    // Set transaction type
    const isBuy = orderType.startsWith('BUY') || signalData.signal === 'BUY';
    document.getElementById('order-transaction').value = isBuy ? 'BUY' : 'SELL';
    
    // Set order type
    if (orderType.includes('MARKET')) {
      document.getElementById('order-type').value = 'MARKET';
    } else if (orderType.includes('LIMIT')) {
      document.getElementById('order-type').value = 'LIMIT';
      document.getElementById('order-price').value = signalData.entry || signalData.ltp;
    }
    
    // Set stop-loss and target if available
    if (signalData.stop_loss) {
      document.getElementById('order-sl').value = signalData.stop_loss;
    }
    if (signalData.tg1) {
      document.getElementById('order-target').value = signalData.tg1;
    }
    
    // Calculate quantity
    calculateQuantity();
    
    // Show modal
    modal.style.display = 'flex';
  }
  
  async function calculateQuantity() {
    const capital = parseFloat(document.getElementById('order-capital').value) || 100000;
    const riskPct = parseFloat(document.getElementById('order-risk-pct').value) || 1.0;
    const entryPrice = parseFloat(document.getElementById('order-price').value) || 
                      parseFloat(document.getElementById('order-ltp').textContent.replace('₹', '')) || 0;
    const slPrice = parseFloat(document.getElementById('order-sl').value) || 0;
    
    if (!entryPrice || !slPrice) {
      return;
    }
    
    try {
      const res = await fetch(`${API}/orders/calculate-quantity`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          capital,
          risk_pct: riskPct,
          entry_price: entryPrice,
          stop_loss_price: slPrice
        })
      });
      const data = await res.json();
      
      if (data.status) {
        document.getElementById('order-quantity').value = data.data.recommended_quantity;
        document.getElementById('order-calc-info').innerHTML = `
          Risk: ₹${data.data.total_risk} (${data.data.risk_pct}%) | 
          Position Value: ₹${data.data.position_value.toLocaleString('en-IN')}
        `;
      }
    } catch (err) {
      console.error('[calculateQuantity]', err);
    }
  }
  
  async function submitOrder() {
    const orderData = {
      symbol: document.getElementById('order-symbol').value,
      symboltoken: document.getElementById('order-symboltoken').value,
      exchange: 'NSE',
      transactiontype: document.getElementById('order-transaction').value,
      ordertype: document.getElementById('order-type').value,
      producttype: document.getElementById('order-product').value,
      quantity: parseInt(document.getElementById('order-quantity').value),
      price: parseFloat(document.getElementById('order-price').value) || null,
      triggerprice: parseFloat(document.getElementById('order-trigger').value) || null,
      stop_loss: parseFloat(document.getElementById('order-sl').value) || null,
      target: parseFloat(document.getElementById('order-target').value) || null,
    };
    
    // Validation
    if (!orderData.symbol || !orderData.symboltoken) {
      toast('Missing symbol or token', 'error');
      return;
    }
    
    if (orderData.quantity <= 0) {
      toast('Quantity must be positive', 'error');
      return;
    }
    
    // Show confirmation for LIVE orders
    if (tradingMode === 'LIVE') {
      const confirmed = await showConfirmModal(orderData);
      if (!confirmed) return;
    }
    
    try {
      const res = await fetch(`${API}/orders/place`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(orderData)
      });
      const data = await res.json();
      
      if (data.status) {
        toast(`Order placed: ${data.data?.orderid || 'success'}`, 'success');
        closeOrderModal();
        refreshOrderData();
      } else {
        toast(`Order failed: ${data.message}`, 'error');
      }
    } catch (err) {
      console.error('[submitOrder]', err);
      toast('Order placement failed', 'error');
    }
  }
  
  // ────────────────────────────────────────────────────────────────────────
  // ORDER BOOK / POSITIONS
  // ────────────────────────────────────────────────────────────────────────
  
  async function refreshOrderData() {
    await Promise.all([
      fetchTradingStats(),
      fetchOpenOrders(),
      fetchPositions(),
      fetchOrderHistory()
    ]);
  }
  
  async function fetchTradingStats() {
    try {
      const res = await fetch(`${API}/trading/stats`);
      const data = await res.json();
      
      if (data.status) {
        const stats = data.data;
        updateElement('stat-funds', `₹${stats.available_funds?.toLocaleString('en-IN') || '0'}`);
        updateElement('stat-margin', `₹${stats.used_margin?.toLocaleString('en-IN') || '0'}`);
        updateElement('stat-positions', stats.open_positions || 0);
        updateElement('stat-pnl', `₹${stats.todays_pnl?.toLocaleString('en-IN') || '0'}`, 
                     stats.todays_pnl >= 0 ? 'green' : 'red');
      }
    } catch (err) {
      console.error('[fetchTradingStats]', err);
    }
  }
  
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
  
  // ────────────────────────────────────────────────────────────────────────
  // RENDERING
  // ────────────────────────────────────────────────────────────────────────
  
  function renderOpenOrders(orders) {
    const tbody = document.getElementById('open-orders-body');
    if (!tbody) return;
    
    if (orders.length === 0) {
      tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--muted)">No open orders</td></tr>';
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
        <td>₹${o.triggerprice?.toFixed(2) || '—'}</td>
        <td><span class="tag tag-bo">${o.status}</span></td>
        <td>
          <button class="btn-sm" onclick="OrderManagement.modifyOrder('${o.order_id}')">Modify</button>
          <button class="btn-sm btn-danger" onclick="OrderManagement.cancelOrder('${o.order_id}')">Cancel</button>
        </td>
      </tr>
    `).join('');
  }
  
  function renderPositions(positions) {
    const tbody = document.getElementById('positions-body');
    if (!tbody) return;
    
    if (positions.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--muted)">No open positions</td></tr>';
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
        <td>${p.producttype}</td>
        <td>
          <button class="btn-sm btn-danger" onclick="OrderManagement.exitPosition('${p.symbol}', ${p.ltp})">Exit</button>
        </td>
      </tr>
    `};
    }).join('');
  }
  
  function renderOrderHistory(orders) {
    const tbody = document.getElementById('order-history-body');
    if (!tbody) return;
    
    if (orders.length === 0) {
      tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--muted)">No order history</td></tr>';
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
        <td>₹${o.average_price?.toFixed(2) || '—'}</td>
        <td><span class="tag ${o.status === 'complete' ? 'tag-buy' : 'tag-sell'}">${o.status}</span></td>
        <td style="font-size:11px;color:var(--muted)">${formatTime(o.updated_at)}</td>
      </tr>
    `).join('');
  }
  
  // ────────────────────────────────────────────────────────────────────────
  // ORDER ACTIONS
  // ────────────────────────────────────────────────────────────────────────
  
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
        refreshOrderData();
      } else {
        toast('Cancel failed: ' + data.message, 'error');
      }
    } catch (err) {
      console.error('[cancelOrder]', err);
      toast('Cancel failed', 'error');
    }
  }
  
  async function exitPosition(symbol, ltp) {
    if (!confirm(`Exit position in ${symbol} at market price (≈₹${ltp})?`)) return;
    
    // Find position to determine quantity and side
    const posRes = await fetch(`${API}/positions`);
    const posData = await posRes.json();
    const position = posData.data.find(p => p.symbol === symbol);
    
    if (!position) {
      toast('Position not found', 'error');
      return;
    }
    
    const orderData = {
      symbol,
      symboltoken: position.symboltoken,
      exchange: 'NSE',
      transactiontype: position.quantity > 0 ? 'SELL' : 'BUY',
      ordertype: 'MARKET',
      producttype: position.producttype,
      quantity: Math.abs(position.quantity),
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
        refreshOrderData();
      } else {
        toast(`Exit failed: ${data.message}`, 'error');
      }
    } catch (err) {
      console.error('[exitPosition]', err);
      toast('Exit failed', 'error');
    }
  }
  
  // ────────────────────────────────────────────────────────────────────────
  // MODAL MANAGEMENT
  // ────────────────────────────────────────────────────────────────────────
  
  function createOrderModal() {
    // Modal HTML will be injected via the main HTML file
    // This function just sets up event listeners
    const modal = document.getElementById('order-modal');
    if (!modal) return;
    
    // Close handlers
    document.getElementById('order-modal-close')?.addEventListener('click', closeOrderModal);
    document.getElementById('order-cancel-btn')?.addEventListener('click', closeOrderModal);
    document.getElementById('order-submit-btn')?.addEventListener('click', submitOrder);
    
    // Calculate quantity on change
    document.getElementById('order-price')?.addEventListener('input', calculateQuantity);
    document.getElementById('order-sl')?.addEventListener('input', calculateQuantity);
    document.getElementById('order-risk-pct')?.addEventListener('input', calculateQuantity);
    
    // Order type change
    document.getElementById('order-type')?.addEventListener('change', (e) => {
      const priceField = document.getElementById('order-price');
      const triggerField = document.getElementById('order-trigger');
      
      if (e.target.value === 'MARKET') {
        priceField.disabled = true;
        triggerField.disabled = true;
      } else if (e.target.value === 'LIMIT') {
        priceField.disabled = false;
        triggerField.disabled = true;
      } else { // STOPLOSS_*
        priceField.disabled = false;
        triggerField.disabled = false;
      }
    });
  }
  
  function closeOrderModal() {
    document.getElementById('order-modal').style.display = 'none';
  }
  
  function createConfirmModal() {
    // Confirmation modal for LIVE orders
  }
  
  async function showConfirmModal(orderData) {
    return new Promise((resolve) => {
      const orderValue = (orderData.price || 0) * orderData.quantity;
      const confirmed = confirm(
        '═══════════════════════════════\n' +
        '   ⚠️  CONFIRM REAL ORDER  ⚠️\n' +
        '═══════════════════════════════\n\n' +
        `Symbol: ${orderData.symbol}\n` +
        `Action: ${orderData.transactiontype}\n` +
        `Order Type: ${orderData.ordertype}\n` +
        `Quantity: ${orderData.quantity}\n` +
        `Price: ₹${orderData.price?.toFixed(2) || 'MARKET'}\n` +
        `Stop Loss: ₹${orderData.stop_loss?.toFixed(2) || '—'}\n` +
        `Target: ₹${orderData.target?.toFixed(2) || '—'}\n` +
        `Estimated Value: ₹${orderValue.toLocaleString('en-IN')}\n\n` +
        '⚠️ This will place a REAL order with real money!\n\n' +
        'Do you want to proceed?'
      );
      resolve(confirmed);
    });
  }
  
  // ────────────────────────────────────────────────────────────────────────
  // UTILITIES
  // ────────────────────────────────────────────────────────────────────────
  
  function updateElement(id, value, colorClass) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = value;
    if (colorClass) {
      el.className = colorClass;
    }
  }
  
  function formatTime(isoString) {
    if (!isoString) return '—';
    try {
      const date = new Date(isoString);
      return date.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
    } catch {
      return '—';
    }
  }
  
  function toast(msg, type = 'success') {
    const el = document.getElementById('toast');
    if (!el) return;
    el.textContent = msg;
    el.className = `show ${type}`;
    clearTimeout(el._t);
    el._t = setTimeout(() => { el.className = ''; }, 3500);
  }
  
  // ────────────────────────────────────────────────────────────────────────
  // PUBLIC API
  // ────────────────────────────────────────────────────────────────────────
  
  return {
    init,
    openOrderModal,
    cancelOrder,
    exitPosition,
    refreshOrderData,
  };
})();

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => OrderManagement.init());
} else {
  OrderManagement.init();
}
