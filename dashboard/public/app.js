// BAZAAR Trading Terminal - Professional Dashboard
// Real-time data, live charts, and autonomous agent monitoring

const state = {
  ethPrice: 0,
  priceHistory: [],
  maxHistory: 100,
  positions: [],
  trades: [],
  signals: [],
  wallet: { eth: 0, usdc: 0, gas: 0 },
  pnl: { today: 0, total: 0 },
  agents: { ethScalper: 'running', tradier: 'waiting' },
  lastUpdate: null
};

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  initChart();
  startDataPolling();
  updateClock();
  setInterval(updateClock, 1000);
});

// Chart Setup
let chartCanvas, chartCtx;

function initChart() {
  chartCanvas = document.getElementById('price-chart');
  if (!chartCanvas) return;
  
  const container = chartCanvas.parentElement;
  chartCanvas.width = container.clientWidth - 32;
  chartCanvas.height = container.clientHeight - 32;
  chartCtx = chartCanvas.getContext('2d');
  
  drawChart();
}

function drawChart() {
  if (!chartCtx || state.priceHistory.length < 2) return;
  
  const width = chartCanvas.width;
  const height = chartCanvas.height;
  const padding = 20;
  
  // Clear
  chartCtx.clearRect(0, 0, width, height);
  
  // Calculate scales
  const prices = state.priceHistory.map(p => p.price);
  const minPrice = Math.min(...prices) * 0.999;
  const maxPrice = Math.max(...prices) * 1.001;
  const priceRange = maxPrice - minPrice;
  
  // Draw grid
  chartCtx.strokeStyle = '#1e293b';
  chartCtx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = padding + (height - 2 * padding) * i / 4;
    chartCtx.beginPath();
    chartCtx.moveTo(padding, y);
    chartCtx.lineTo(width - padding, y);
    chartCtx.stroke();
  }
  
  // Draw price line
  chartCtx.strokeStyle = '#3b82f6';
  chartCtx.lineWidth = 2;
  chartCtx.beginPath();
  
  state.priceHistory.forEach((point, i) => {
    const x = padding + (width - 2 * padding) * i / (state.priceHistory.length - 1);
    const y = height - padding - (point.price - minPrice) / priceRange * (height - 2 * padding);
    
    if (i === 0) {
      chartCtx.moveTo(x, y);
    } else {
      chartCtx.lineTo(x, y);
    }
  });
  
  chartCtx.stroke();
  
  // Draw gradient fill
  chartCtx.lineTo(width - padding, height - padding);
  chartCtx.lineTo(padding, height - padding);
  chartCtx.closePath();
  
  const gradient = chartCtx.createLinearGradient(0, padding, 0, height - padding);
  gradient.addColorStop(0, 'rgba(59, 130, 246, 0.3)');
  gradient.addColorStop(1, 'rgba(59, 130, 246, 0)');
  chartCtx.fillStyle = gradient;
  chartCtx.fill();
  
  // Draw current price dot
  if (state.priceHistory.length > 0) {
    const lastPoint = state.priceHistory[state.priceHistory.length - 1];
    const x = width - padding;
    const y = height - padding - (lastPoint.price - minPrice) / priceRange * (height - 2 * padding);
    
    chartCtx.fillStyle = '#3b82f6';
    chartCtx.beginPath();
    chartCtx.arc(x, y, 4, 0, Math.PI * 2);
    chartCtx.fill();
    
    // Glow effect
    chartCtx.shadowColor = '#3b82f6';
    chartCtx.shadowBlur = 10;
    chartCtx.beginPath();
    chartCtx.arc(x, y, 6, 0, Math.PI * 2);
    chartCtx.fill();
    chartCtx.shadowBlur = 0;
  }
}

// Data Polling
function startDataPolling() {
  fetchData();
  setInterval(fetchData, 3000);
}

async function fetchData() {
  try {
    const [statusRes, walletRes, tradesRes, signalsRes] = await Promise.all([
      fetch('/api/eth-scalper/status').catch(() => null),
      fetch('/api/eth-scalper/wallet').catch(() => null),
      fetch('/api/eth-scalper/trades').catch(() => null),
      fetch('/api/eth-scalper/signals').catch(() => null)
    ]);
    
    if (statusRes?.ok) {
      const data = await statusRes.json();
      state.ethPrice = calculateEthPrice(data);
      state.pnl = data.pnl || { today: 0, total: 0 };
      state.agents.ethScalper = data.status;
      
      // Update price history
      state.priceHistory.push({ price: state.ethPrice, time: Date.now() });
      if (state.priceHistory.length > state.maxHistory) {
        state.priceHistory.shift();
      }
      
      updateTicker(data);
      updatePositions(data);
      updatePnL(data);
      updateRisk(data);
      updateAgents(data);
      updateTradingPanel(data);
    }
    
    if (walletRes?.ok) {
      const data = await walletRes.json();
      state.wallet = data;
      updateWallet(data);
    }
    
    if (tradesRes?.ok) {
      const data = await tradesRes.json();
      state.trades = data.trades || [];
      updateTrades(data.trades);
    }
    
    if (signalsRes?.ok) {
      const data = await signalsRes.json();
      state.signals = data.signals || [];
      updateSignals(data.signals);
    }
    
    drawChart();
    state.lastUpdate = new Date();
    
  } catch (err) {
    console.error('Data fetch error:', err);
  }
}

function calculateEthPrice(data) {
  const totalUsd = data.wallet?.estimated_total_usd || 0;
  const usdc = data.wallet?.usdc || 0;
  const eth = data.wallet?.eth || 0;
  
  if (eth > 0 && totalUsd > usdc) {
    const price = (totalUsd - usdc) / eth;
    if (price >= 1000 && price <= 10000) return price;
  }
  return 2500;
}

// UI Updates
function updateTicker(data) {
  const priceEl = document.getElementById('ticker-eth-price');
  const changeEl = document.getElementById('ticker-eth-change');
  const usdcEl = document.getElementById('ticker-usdc-balance');
  const pnlEl = document.getElementById('ticker-pnl');
  const posEl = document.getElementById('ticker-positions');
  
  if (priceEl) priceEl.textContent = `$${state.ethPrice.toFixed(2)}`;
  
  if (changeEl && state.priceHistory.length >= 2) {
    const prevPrice = state.priceHistory[state.priceHistory.length - 2]?.price || state.ethPrice;
    const change = ((state.ethPrice - prevPrice) / prevPrice) * 100;
    changeEl.textContent = `${change >= 0 ? '+' : ''}${change.toFixed(2)}%`;
    changeEl.className = `ticker-change ${change >= 0 ? 'positive' : 'negative'}`;
  }
  
  if (usdcEl) usdcEl.textContent = `$${state.wallet.usdc.toFixed(2)}`;
  if (pnlEl) {
    const pnl = state.pnl.today;
    pnlEl.textContent = `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`;
    pnlEl.style.color = pnl >= 0 ? '#00d084' : '#ff4d4d';
  }
  if (posEl) posEl.textContent = data.open_positions || 0;
}

function updatePositions(data) {
  const list = document.getElementById('positions-list');
  const count = document.getElementById('positions-count');
  
  if (count) count.textContent = data.open_positions || 0;
  
  if (!list) return;
  
  if (!data.open_positions || data.open_positions === 0) {
    list.innerHTML = '<div class="empty-state">No open positions</div>';
    return;
  }
  
  // Mock position for display
  list.innerHTML = `
    <div class="position-item">
      <div>
        <span class="position-direction long">LONG</span>
        <span style="margin-left:8px;color:#94a3b8">ETH</span>
      </div>
      <div class="position-details">
        <span style="color:#f0f4f8">$${state.ethPrice.toFixed(2)}</span>
        <span class="position-pnl positive">+$0.00</span>
      </div>
    </div>
  `;
}

function updatePnL(data) {
  const todayEl = document.getElementById('pnl-today');
  const totalEl = document.getElementById('pnl-total');
  const winRateEl = document.getElementById('win-rate');
  const countEl = document.getElementById('trade-count');
  
  if (todayEl) {
    const pnl = state.pnl.today;
    todayEl.textContent = `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`;
    todayEl.className = `pnl-value ${pnl >= 0 ? 'positive' : 'negative'}`;
  }
  
  if (totalEl) {
    const total = state.pnl.total;
    totalEl.textContent = `${total >= 0 ? '+' : ''}$${total.toFixed(2)}`;
  }
  
  if (winRateEl) winRateEl.textContent = '0%';
  if (countEl) countEl.textContent = data.daily_trades || 0;
}

function updateRisk(data) {
  const totalCapital = state.wallet.eth * state.ethPrice + state.wallet.usdc;
  const positionValue = (data.open_positions || 0) * 50;
  const exposurePct = totalCapital > 0 ? (positionValue / totalCapital) * 100 : 0;
  
  const dailyLoss = Math.abs(Math.min(0, state.pnl.today));
  const lossPct = (dailyLoss / 15) * 100;
  
  const heatPct = ((data.open_positions || 0) / 2) * 100;
  
  // Update exposure
  const expFill = document.getElementById('exposure-fill');
  const expVal = document.getElementById('exposure-value');
  if (expFill) {
    expFill.style.width = `${Math.min(exposurePct, 100)}%`;
    expFill.className = `gauge-fill ${exposurePct > 80 ? 'high' : exposurePct > 50 ? 'medium' : 'low'}`;
  }
  if (expVal) expVal.textContent = `${exposurePct.toFixed(0)}%`;
  
  // Update loss
  const lossFill = document.getElementById('loss-fill');
  const lossVal = document.getElementById('loss-value');
  if (lossFill) {
    lossFill.style.width = `${Math.min(lossPct, 100)}%`;
    lossFill.className = `gauge-fill ${lossPct > 80 ? 'high' : lossPct > 50 ? 'medium' : 'low'}`;
  }
  if (lossVal) lossVal.textContent = `$${dailyLoss.toFixed(0)}/$15`;
  
  // Update heat
  const heatFill = document.getElementById('heat-fill');
  const heatVal = document.getElementById('heat-value');
  if (heatFill) {
    heatFill.style.width = `${heatPct}%`;
    heatFill.className = `gauge-fill ${heatPct >= 100 ? 'high' : heatPct > 50 ? 'medium' : 'low'}`;
  }
  if (heatVal) heatVal.textContent = `${data.open_positions || 0}/2`;
  
  // Update badge
  const badge = document.getElementById('risk-badge');
  if (badge) {
    const maxRisk = Math.max(exposurePct, lossPct, heatPct);
    if (maxRisk >= 80) {
      badge.textContent = 'ELEVATED';
      badge.className = 'badge danger';
    } else if (maxRisk >= 50) {
      badge.textContent = 'MODERATE';
      badge.className = 'badge warning';
    } else {
      badge.textContent = 'SAFE';
      badge.className = 'badge safe';
    }
  }
}

function updateAgents(data) {
  const ethStatus = document.getElementById('eth-agent-status');
  const ethDot = document.getElementById('eth-agent-dot');
  const tradierStatus = document.getElementById('tradier-agent-status');
  const tradierDot = document.getElementById('tradier-agent-dot');
  const systemStatus = document.getElementById('system-status');
  const systemText = document.getElementById('system-status-text');
  
  if (ethStatus && ethDot) {
    const isRunning = data.status === 'running';
    ethStatus.textContent = isRunning ? 'Running' : 'Paused';
    ethDot.className = `status-dot ${isRunning ? 'active' : ''}`;
  }
  
  if (tradierStatus && tradierDot) {
    tradierStatus.textContent = 'Waiting';
    tradierDot.className = 'status-dot waiting';
  }
  
  if (systemStatus && systemText) {
    const isLive = data.mode === 'live';
    systemStatus.className = `status-dot ${isLive ? 'active' : ''}`;
    systemText.textContent = isLive ? 'LIVE' : 'PAPER';
  }
}

function updateTradingPanel(data) {
  const capitalEl = document.getElementById('available-capital');
  const gasEl = document.getElementById('gas-price');
  const apiEl = document.getElementById('api-calls');
  
  if (capitalEl) capitalEl.textContent = `$${(data.available_capital || 0).toFixed(2)}`;
  if (gasEl) gasEl.textContent = `${state.wallet.gas.toFixed(1)} gwei`;
  if (apiEl) apiEl.textContent = `${data.requests?.used || 0}/${data.requests?.limit || 900}`;
}

function updateWallet(data) {
  const walletEl = document.getElementById('wallet-address');
  if (walletEl && data.address) {
    walletEl.textContent = `${data.address.slice(0, 6)}...${data.address.slice(-4)}`;
  }
}

function updateTrades(trades) {
  const list = document.getElementById('orders-list');
  if (!list) return;
  
  if (!trades || trades.length === 0) {
    list.innerHTML = '<div class="empty-state">No recent orders</div>';
    return;
  }
  
  list.innerHTML = trades.slice(0, 5).map(trade => `
    <div class="order-item">
      <span>${trade.direction === 'long' ? 'BUY' : 'SELL'} ETH</span>
      <span style="color:${trade.pnl_usd >= 0 ? '#00d084' : '#ff4d4d'}">${trade.pnl_usd >= 0 ? '+' : ''}$${trade.pnl_usd?.toFixed(2) || '0.00'}</span>
    </div>
  `).join('');
}

function updateSignals(signals) {
  const list = document.getElementById('signals-list');
  if (!list) return;
  
  if (!signals || signals.length === 0) {
    list.innerHTML = '<div class="empty-state">No active signals</div>';
    return;
  }
  
  list.innerHTML = signals.slice(0, 5).map(signal => `
    <div class="signal-item">
      <span class="signal-direction ${signal.direction === 'up' ? 'up' : 'down'}">${signal.direction === 'up' ? '▲' : '▼'} ${signal.direction.toUpperCase()}</span>
      <span style="color:#94a3b8">$${signal.price?.toFixed(2)}</span>
      <span class="signal-score">${signal.score}/10</span>
    </div>
  `).join('');
}

function updateClock() {
  const el = document.getElementById('last-update');
  if (el && state.lastUpdate) {
    el.textContent = state.lastUpdate.toLocaleTimeString();
  }
}

// Trade Actions
async function executeBuy() {
  const btn = document.getElementById('buy-btn');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="btn-label">EXECUTING...</span>';
  }
  
  try {
    const res = await fetch('/api/eth-scalper/command', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: 'BUY' })
    });
    
    if (res.ok) {
      showToast('Buy order sent', 'success');
    } else {
      showToast('Order failed', 'error');
    }
  } catch (err) {
    showToast('Network error', 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<span class="btn-label">BUY ETH</span><span class="btn-sublabel">Market Order</span>';
    }
  }
}

async function executeSell() {
  const btn = document.getElementById('sell-btn');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="btn-label">EXECUTING...</span>';
  }
  
  try {
    const res = await fetch('/api/eth-scalper/command', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: 'SELL' })
    });
    
    if (res.ok) {
      showToast('Sell order sent', 'success');
    } else {
      showToast('Order failed', 'error');
    }
  } catch (err) {
    showToast('Network error', 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<span class="btn-label">SELL ETH</span><span class="btn-sublabel">Market Order</span>';
    }
  }
}

function showToast(message, type) {
  const toast = document.createElement('div');
  toast.style.cssText = `
    position: fixed;
    bottom: 80px;
    right: 20px;
    padding: 12px 20px;
    background: ${type === 'success' ? '#00d084' : '#ff4d4d'};
    color: white;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 600;
    z-index: 1000;
    animation: slideIn 0.3s ease;
  `;
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 3000);
}

// Handle window resize
window.addEventListener('resize', () => {
  initChart();
  drawChart();
});
