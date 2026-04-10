// THE BAZAAR - Trading Command Center
// Full-featured dashboard with Tradier leaders, ETH scalper, and autonomous agents

// ═══════════════════════════════════════════════════════════════
// STATE MANAGEMENT
// ═══════════════════════════════════════════════════════════════

let currentSnapshot = null;
let selectedLeaderIndex = 0;
let selectedLeaderKey = null;
let lastActionStatus = null;
let currentUiMode = 'loading';
let currentLoadError = null;
let currentZone = 'trade';

// ETH Scalper State
let ethScalperData = {
  status: 'loading',
  mode: 'unknown',
  pnl: { today: 0, total: 0 },
  trades: [],
  positions: [],
  signals: [],
  wallet: { eth: 0, usdc: 0, gas: 0, address: '' },
  requests: { used: 0, limit: 900 },
  daily_trades: 0,
  open_positions: 0,
  available_capital: 0
};

let priceHistory = [];
let maxHistory = 100;

// ═══════════════════════════════════════════════════════════════
// INITIALIZATION
// ═══════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
  // Set initial zone
  document.querySelectorAll('.zone').forEach(z => z.style.display = 'none');
  switchZone('trade');
  
  // Start data polling
  fetchSnapshot();
  setInterval(fetchSnapshot, 5000);
  
  // Start ETH scalper polling
  fetchEthScalperData();
  setInterval(fetchEthScalperData, 3000);
  
  // Clock
  updateClock();
  setInterval(updateClock, 1000);
  
  // Refresh button
  const refreshBtn = document.getElementById('refreshBtn');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', () => {
      fetchSnapshot();
      fetchEthScalperData();
    });
  }
});

// ═══════════════════════════════════════════════════════════════
// ZONE NAVIGATION
// ═══════════════════════════════════════════════════════════════

function switchZone(zoneName) {
  currentZone = zoneName;
  
  // Hide all zones
  document.querySelectorAll('.zone').forEach(z => {
    z.classList.remove('active');
    z.style.display = 'none';
  });
  
  // Show selected zone
  const targetZone = document.getElementById('zone-' + zoneName);
  if (targetZone) {
    targetZone.style.display = 'block';
    setTimeout(() => targetZone.classList.add('active'), 10);
  }
  
  // Update nav
  document.querySelectorAll('.nav-pill').forEach(p => {
    p.classList.remove('active');
    if (p.dataset.zone === zoneName) {
      p.classList.add('active');
    }
  });
  
  // Zone-specific refresh
  if (zoneName === 'journal') {
    updateAnalytics();
  }
}

// ═══════════════════════════════════════════════════════════════
// SNAPSHOT & TRADIER DATA
// ═══════════════════════════════════════════════════════════════

async function fetchSnapshot() {
  try {
    const response = await fetch('./snapshot.json?' + Date.now());
    if (!response.ok) throw new Error('Failed to fetch snapshot');
    
    currentSnapshot = await response.json();
    currentUiMode = 'ready';
    currentLoadError = null;
    
    renderDashboard();
  } catch (err) {
    console.error('Snapshot error:', err);
    currentUiMode = 'error';
    currentLoadError = err.message;
  }
}

function renderDashboard() {
  if (!currentSnapshot) return;
  
  // Update operator rail
  updateOperatorRail();
  
  // Update command layer
  renderCommandLayer();
  
  // Update leaders
  renderLeaders();
  
  // Update scan status
  renderScanStatus();
  
  // Update overview
  renderOverview();
}

function updateOperatorRail() {
  const modeEl = document.getElementById('systemMode');
  const bpEl = document.getElementById('buyingPower');
  const marketEl = document.getElementById('marketStatus');
  
  if (modeEl) modeEl.textContent = currentSnapshot?.account?.mode || 'LIVE';
  if (bpEl) bpEl.textContent = 'BP: $' + (currentSnapshot?.account?.buying_power || '0');
  if (marketEl) marketEl.textContent = currentSnapshot?.market?.status || 'CLOSED';
}

function renderCommandLayer() {
  const wrap = document.getElementById('commandLayerWrap');
  const stateEl = document.getElementById('commandState');
  
  if (!wrap || !currentSnapshot?.command_layer) return;
  
  const layer = currentSnapshot.command_layer;
  stateEl.textContent = layer.state || '--';
  
  wrap.innerHTML = `
    <div class="command-summary">
      <div class="command-item">
        <span class="label">Bias:</span>
        <span class="value ${layer.bias}">${layer.bias || 'neutral'}</span>
      </div>
      <div class="command-item">
        <span class="label">Confidence:</span>
        <span class="value">${layer.confidence || 0}/10</span>
      </div>
      <div class="command-item">
        <span class="label">Next Action:</span>
        <span class="value">${layer.next_action || 'wait'}</span>
      </div>
    </div>
  `;
}

function renderLeaders() {
  const wrap = document.getElementById('leadersWrap');
  const metaEl = document.getElementById('leadersMeta');
  
  if (!wrap || !currentSnapshot?.leaders) return;
  
  const leaders = currentSnapshot.leaders;
  metaEl.textContent = `${leaders.length} leaders`;
  
  if (leaders.length === 0) {
    wrap.innerHTML = '<div class="void">No leaders available</div>';
    return;
  }
  
  wrap.innerHTML = leaders.map((leader, i) => `
    <div class="leader-card ${selectedLeaderIndex === i ? 'selected' : ''}" onclick="selectLeader(${i})">
      <div class="leader-header">
        <span class="leader-symbol">${leader.symbol}</span>
        <span class="leader-type ${leader.option_type}">${leader.option_type}</span>
      </div>
      <div class="leader-details">
        <span>Strike: $${leader.strike}</span>
        <span>Exp: ${leader.expiration}</span>
        <span>Mid: $${leader.mid_price?.toFixed(2)}</span>
      </div>
      <div class="leader-strategy">${leader.strategy}</div>
    </div>
  `).join('');
}

function selectLeader(index) {
  selectedLeaderIndex = index;
  renderLeaders();
  
  const leader = currentSnapshot?.leaders?.[index];
  if (leader) {
    selectedLeaderKey = leader.candidate_id;
    renderActions(leader);
  }
}

function renderActions(leader) {
  const wrap = document.getElementById('actionsWrap');
  if (!wrap) return;
  
  wrap.innerHTML = `
    <div class="action-card">
      <h4>${leader.symbol} ${leader.strike} ${leader.option_type.toUpperCase()}</h4>
      <p>Mid: $${leader.mid_price?.toFixed(2)} | Exp: ${leader.expiration}</p>
      <div class="action-buttons">
        <button class="btn-action primary" onclick="executeTradierTrade('${leader.candidate_id}')">EXECUTE</button>
        <button class="btn-action" onclick="previewTrade('${leader.candidate_id}')">PREVIEW</button>
      </div>
    </div>
  `;
}

function renderScanStatus() {
  const statusEl = document.getElementById('scanStatus');
  const lastScanEl = document.getElementById('lastScanTime');
  const freshnessEl = document.getElementById('dataFreshness');
  
  if (!currentSnapshot?.scan) return;
  
  const scan = currentSnapshot.scan;
  statusEl.textContent = scan.status || 'Unknown';
  lastScanEl.textContent = scan.last_scan || '--';
  freshnessEl.textContent = scan.freshness || '--';
}

function renderOverview() {
  const grid = document.getElementById('overviewGrid');
  if (!grid || !currentSnapshot?.overview) return;
  
  const ov = currentSnapshot.overview;
  grid.innerHTML = `
    <div class="metric">
      <span class="metric-label">VIX</span>
      <span class="metric-value">${ov.vix || '--'}</span>
    </div>
    <div class="metric">
      <span class="metric-label">SPY</span>
      <span class="metric-value ${ov.spy_change >= 0 ? 'up' : 'down'}">${ov.spy || '--'}</span>
    </div>
    <div class="metric">
      <span class="metric-label">QQQ</span>
      <span class="metric-value ${ov.qqq_change >= 0 ? 'up' : 'down'}">${ov.qqq || '--'}</span>
    </div>
  `;
}

// ═══════════════════════════════════════════════════════════════
// ETH SCALPER DATA
// ═══════════════════════════════════════════════════════════════

async function fetchEthScalperData() {
  try {
    const [statusRes, walletRes, tradesRes, positionsRes, signalsRes] = await Promise.all([
      fetch('/api/eth-scalper/status').catch(() => null),
      fetch('/api/eth-scalper/wallet').catch(() => null),
      fetch('/api/eth-scalper/trades').catch(() => null),
      fetch('/api/eth-scalper/positions').catch(() => null),
      fetch('/api/eth-scalper/signals').catch(() => null)
    ]);
    
    if (statusRes?.ok) {
      const data = await statusRes.json();
      ethScalperData = { ...ethScalperData, ...data };
      
      // Update price history
      const ethPrice = calculateEthPrice(data);
      if (ethPrice > 0) {
        priceHistory.push({ price: ethPrice, time: Date.now() });
        if (priceHistory.length > maxHistory) priceHistory.shift();
      }
    }
    
    if (walletRes?.ok) {
      ethScalperData.wallet = await walletRes.json();
    }
    
    if (tradesRes?.ok) {
      const data = await tradesRes.json();
      ethScalperData.trades = data.trades || [];
    }
    
    if (positionsRes?.ok) {
      const data = await positionsRes.json();
      ethScalperData.positions = data.positions || [];
    }
    
    if (signalsRes?.ok) {
      const data = await signalsRes.json();
      ethScalperData.signals = data.signals || [];
    }
    
    renderEthScalper();
    drawChart();
    
  } catch (err) {
    console.error('ETH scalper fetch error:', err);
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
  return 0;
}

function renderEthScalper() {
  const ethPrice = calculateEthPrice(ethScalperData);
  
  // Stats
  const priceEl = document.getElementById('eth-price-display');
  const pnlEl = document.getElementById('eth-pnl-today');
  const posEl = document.getElementById('eth-open-positions');
  const tradesEl = document.getElementById('eth-daily-trades');
  const ethBalEl = document.getElementById('eth-balance');
  const usdcBalEl = document.getElementById('usdc-balance');
  
  if (priceEl) priceEl.textContent = ethPrice > 0 ? `$${ethPrice.toFixed(2)}` : '--';
  if (pnlEl) {
    const pnl = ethScalperData.pnl?.today || 0;
    pnlEl.textContent = `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`;
    pnlEl.className = `stat-value ${pnl >= 0 ? 'positive' : 'negative'}`;
  }
  if (posEl) posEl.textContent = ethScalperData.open_positions || 0;
  if (tradesEl) tradesEl.textContent = ethScalperData.daily_trades || 0;
  if (ethBalEl) ethBalEl.textContent = ethScalperData.wallet?.eth?.toFixed(4) || '0';
  if (usdcBalEl) usdcBalEl.textContent = `$${ethScalperData.wallet?.usdc?.toFixed(2) || '0'}`;
  
  // Trading panel
  const capitalEl = document.getElementById('eth-available-capital');
  const gasEl = document.getElementById('eth-gas-display');
  const apiEl = document.getElementById('eth-api-calls');
  const modeBadge = document.getElementById('eth-mode-badge');
  
  if (capitalEl) capitalEl.textContent = `$${(ethScalperData.available_capital || 0).toFixed(2)}`;
  if (gasEl) gasEl.textContent = `${(ethScalperData.wallet?.gas || 0).toFixed(1)} gwei`;
  if (apiEl) apiEl.textContent = `${ethScalperData.requests?.used || 0}/${ethScalperData.requests?.limit || 900}`;
  if (modeBadge) {
    modeBadge.textContent = ethScalperData.mode?.toUpperCase() || 'UNKNOWN';
    modeBadge.className = `panel-status ${ethScalperData.mode === 'live' ? 'safe' : 'warning'}`;
  }
  
  // Risk gauges
  updateRiskGauges(ethPrice);
  
  // Agents
  const ethStatusEl = document.getElementById('eth-agent-status-text');
  const ethDot = document.getElementById('eth-agent-dot');
  
  if (ethStatusEl) ethStatusEl.textContent = ethScalperData.status === 'running' ? 'Running' : 'Paused';
  if (ethDot) ethDot.className = `agent-dot ${ethScalperData.status === 'running' ? 'active' : ''}`;
  
  // Lists
  renderPositionsList();
  renderSignalsList();
  renderTradesList();
}

function updateRiskGauges(ethPrice) {
  const totalCapital = (ethScalperData.wallet?.eth || 0) * ethPrice + (ethScalperData.wallet?.usdc || 0);
  const positionValue = (ethScalperData.open_positions || 0) * 50;
  const exposurePct = totalCapital > 0 ? (positionValue / totalCapital) * 100 : 0;
  
  const dailyLoss = Math.abs(Math.min(0, ethScalperData.pnl?.today || 0));
  const lossPct = (dailyLoss / 15) * 100;
  
  const heatPct = ((ethScalperData.open_positions || 0) / 2) * 100;
  
  // Update DOM
  const expFill = document.getElementById('eth-exposure-fill');
  const expVal = document.getElementById('eth-exposure-value');
  if (expFill) {
    expFill.style.width = `${Math.min(exposurePct, 100)}%`;
    expFill.className = `gauge-fill ${exposurePct > 80 ? 'high' : exposurePct > 50 ? 'medium' : 'low'}`;
  }
  if (expVal) expVal.textContent = `${exposurePct.toFixed(0)}%`;
  
  const lossFill = document.getElementById('eth-loss-fill');
  const lossVal = document.getElementById('eth-loss-value');
  if (lossFill) {
    lossFill.style.width = `${Math.min(lossPct, 100)}%`;
    lossFill.className = `gauge-fill ${lossPct > 80 ? 'high' : lossPct > 50 ? 'medium' : 'low'}`;
  }
  if (lossVal) lossVal.textContent = `$${dailyLoss.toFixed(0)}/$15`;
  
  const heatFill = document.getElementById('eth-heat-fill');
  const heatVal = document.getElementById('eth-heat-value');
  if (heatFill) {
    heatFill.style.width = `${heatPct}%`;
    heatFill.className = `gauge-fill ${heatPct >= 100 ? 'high' : heatPct > 50 ? 'medium' : 'low'}`;
  }
  if (heatVal) heatVal.textContent = `${ethScalperData.open_positions || 0}/2`;
  
  // Badge
  const badge = document.getElementById('eth-risk-badge');
  if (badge) {
    const maxRisk = Math.max(exposurePct, lossPct, heatPct);
    if (maxRisk >= 80) {
      badge.textContent = 'ELEVATED';
      badge.className = 'panel-status danger';
    } else if (maxRisk >= 50) {
      badge.textContent = 'MODERATE';
      badge.className = 'panel-status warning';
    } else {
      badge.textContent = 'SAFE';
      badge.className = 'panel-status safe';
    }
  }
}

function renderPositionsList() {
  const list = document.getElementById('eth-positions-list');
  const count = document.getElementById('eth-positions-count');
  
  if (count) count.textContent = ethScalperData.positions?.length || 0;
  if (!list) return;
  
  if (!ethScalperData.positions || ethScalperData.positions.length === 0) {
    list.innerHTML = '<div class="void">No open positions</div>';
    return;
  }
  
  list.innerHTML = ethScalperData.positions.map(pos => `
    <div class="position-item">
      <span>${pos.direction === 'long' ? 'LONG' : 'SHORT'} ETH</span>
      <span style="color: ${pos.pnl_usd >= 0 ? 'var(--good)' : 'var(--bad)'}">${pos.pnl_usd >= 0 ? '+' : ''}$${pos.pnl_usd?.toFixed(2) || '0.00'}</span>
    </div>
  `).join('');
}

function renderSignalsList() {
  const list = document.getElementById('eth-signals-list');
  if (!list) return;
  
  if (!ethScalperData.signals || ethScalperData.signals.length === 0) {
    list.innerHTML = '<div class="void">No active signals</div>';
    return;
  }
  
  list.innerHTML = ethScalperData.signals.slice(0, 5).map(sig => `
    <div class="signal-item">
      <span style="color: ${sig.direction === 'up' ? 'var(--good)' : 'var(--bad)'}">${sig.direction === 'up' ? '▲' : '▼'} ${sig.direction.toUpperCase()}</span>
      <span>$${sig.price?.toFixed(2)}</span>
      <span style="color: var(--text-secondary)">${sig.score}/10</span>
    </div>
  `).join('');
}

function renderTradesList() {
  const list = document.getElementById('eth-trades-list');
  if (!list) return;
  
  if (!ethScalperData.trades || ethScalperData.trades.length === 0) {
    list.innerHTML = '<div class="void">No recent trades</div>';
    return;
  }
  
  list.innerHTML = ethScalperData.trades.slice(0, 5).map(trade => `
    <div class="trade-item">
      <span>${trade.direction === 'long' ? 'BUY' : 'SELL'} ETH</span>
      <span style="color: ${trade.pnl_usd >= 0 ? 'var(--good)' : 'var(--bad)'}">${trade.pnl_usd >= 0 ? '+' : ''}$${trade.pnl_usd?.toFixed(2) || '0.00'}</span>
    </div>
  `).join('');
}

// ═══════════════════════════════════════════════════════════════
// CHART
// ═══════════════════════════════════════════════════════════════

function drawChart() {
  const canvas = document.getElementById('eth-chart');
  if (!canvas || priceHistory.length < 2) return;
  
  const ctx = canvas.getContext('2d');
  const container = canvas.parentElement;
  canvas.width = container.clientWidth - 20;
  canvas.height = container.clientHeight - 20;
  
  const width = canvas.width;
  const height = canvas.height;
  const padding = 20;
  
  // Clear
  ctx.clearRect(0, 0, width, height);
  
  // Calculate scales
  const prices = priceHistory.map(p => p.price);
  const minPrice = Math.min(...prices) * 0.999;
  const maxPrice = Math.max(...prices) * 1.001;
  const priceRange = maxPrice - minPrice;
  
  // Draw grid
  ctx.strokeStyle = 'var(--border)';
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = padding + (height - 2 * padding) * i / 4;
    ctx.beginPath();
    ctx.moveTo(padding, y);
    ctx.lineTo(width - padding, y);
    ctx.stroke();
  }
  
  // Draw price line
  ctx.strokeStyle = 'var(--accent)';
  ctx.lineWidth = 2;
  ctx.beginPath();
  
  priceHistory.forEach((point, i) => {
    const x = padding + (width - 2 * padding) * i / (priceHistory.length - 1);
    const y = height - padding - (point.price - minPrice) / priceRange * (height - 2 * padding);
    
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  
  ctx.stroke();
  
  // Draw gradient fill
  ctx.lineTo(width - padding, height - padding);
  ctx.lineTo(padding, height - padding);
  ctx.closePath();
  
  const gradient = ctx.createLinearGradient(0, padding, 0, height - padding);
  gradient.addColorStop(0, 'rgba(201, 162, 39, 0.3)');
  gradient.addColorStop(1, 'rgba(201, 162, 39, 0)');
  ctx.fillStyle = gradient;
  ctx.fill();
}

// ═══════════════════════════════════════════════════════════════
// ACTIONS
// ═══════════════════════════════════════════════════════════════

async function executeEthBuy() {
  await sendBotCommand('BUY');
}

async function executeEthSell() {
  await sendBotCommand('SELL');
}

async function sendBotCommand(command) {
  try {
    const res = await fetch('/api/eth-scalper/command', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command })
    });
    
    if (res.ok) {
      showToast(`${command} command sent`, 'success');
    } else {
      showToast('Command failed', 'error');
    }
  } catch (err) {
    showToast('Network error', 'error');
  }
}

function viewBotLogs() {
  window.open('/eth-scalper/logs/', '_blank');
}

async function executeTradierTrade(candidateId) {
  showToast('Trade execution not yet implemented', 'warning');
}

function previewTrade(candidateId) {
  showToast('Preview not yet implemented', 'warning');
}

function runPremarketScan() {
  showToast('Scan initiated', 'info');
}

function forceRefresh() {
  fetchSnapshot();
  showToast('Refreshing...', 'info');
}

function showFilterCriteria() {
  showToast('Filters not yet implemented', 'warning');
}

function updateAnalytics() {
  const summary = document.getElementById('analyticsSummary');
  if (summary) summary.innerHTML = 'Analytics loading...';
}

function exportJournal() {
  showToast('Export not yet implemented', 'warning');
}

// ═══════════════════════════════════════════════════════════════
// UTILITIES
// ═══════════════════════════════════════════════════════════════

function updateClock() {
  const clock = document.getElementById('clock');
  const update = document.getElementById('lastUpdate');
  const now = new Date();
  const timeStr = now.toLocaleTimeString('en-US', { hour12: false });
  
  if (clock) clock.textContent = timeStr;
  if (update) update.textContent = timeStr;
}

function showToast(message, type = 'info') {
  const toast = document.createElement('div');
  toast.style.cssText = `
    position: fixed;
    bottom: 20px;
    right: 20px;
    padding: 12px 20px;
    background: ${type === 'success' ? 'var(--good)' : type === 'error' ? 'var(--bad)' : type === 'warning' ? 'var(--warn)' : 'var(--info)'};
    color: white;
    border-radius: var(--radius-md);
    font-size: 12px;
    font-weight: 700;
    z-index: 1000;
    animation: slideIn 0.3s ease;
  `;
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 3000);
}

// Handle resize
window.addEventListener('resize', drawChart);
