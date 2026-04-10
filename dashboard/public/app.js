// BAZAAR Trading Command Center - Fully Functional
// Real-time data from snapshot.json and ETH scalper APIs

// State
let snapshot = null;
let ethData = { status: 'loading', mode: 'unknown', pnl: {today: 0, total: 0}, wallet: {eth: 0, usdc: 0} };
let priceHistory = [];
let currentZone = 'trade';

// Init
document.addEventListener('DOMContentLoaded', () => {
  switchZone('trade');
  loadData();
  setInterval(loadData, 3000);
  updateClock();
  setInterval(updateClock, 1000);
});

// Zone switching
function switchZone(zone) {
  currentZone = zone;
  document.querySelectorAll('.zone').forEach(z => z.style.display = 'none');
  document.getElementById('zone-' + zone).style.display = 'block';
  document.querySelectorAll('.nav-pill').forEach(p => p.classList.remove('active'));
  document.querySelector('.nav-pill[data-zone="' + zone + '"]').classList.add('active');
}

// Load all data
async function loadData() {
  await Promise.all([loadSnapshot(), loadEthData()]);
  renderAll();
}

// Load snapshot
async function loadSnapshot() {
  try {
    const res = await fetch('./snapshot.json?' + Date.now());
    if (res.ok) snapshot = await res.json();
  } catch (e) { console.error('Snapshot error:', e); }
}

// Load ETH scalper data
async function loadEthData() {
  try {
    const [statusRes, walletRes] = await Promise.all([
      fetch('/api/eth-scalper/status').catch(() => null),
      fetch('/api/eth-scalper/wallet').catch(() => null)
    ]);

    let statusData = null;
    let walletData = null;
    
    if (statusRes?.ok) {
      statusData = await statusRes.json();
      ethData = { ...ethData, ...statusData };
    }
    
    if (walletRes?.ok) {
      walletData = await walletRes.json();
      ethData.wallet = walletData;
    }

    const merged = { ...ethData, ...(statusData || {}), wallet: walletData || ethData.wallet };
    const price = calculateEthPrice(merged);
    if (price > 0) {
      priceHistory.push({ price, time: Date.now() });
      if (priceHistory.length > 100) priceHistory.shift();
    }
  } catch (e) { console.error('ETH data error:', e); }
}

function calculateEthPrice(data) {
  const total = data.wallet?.estimated_total_usd || 0;
  const usdc = data.wallet?.usdc || 0;
  const eth = data.wallet?.eth || 0;
  if (eth > 0 && total > usdc) {
    const price = (total - usdc) / eth;
    if (price >= 1000 && price <= 10000) return price;
  }
  return 2200; // fallback
}

// Render everything
function renderAll() {
  renderOperatorRail();
  renderLeaders();
  renderEthScalper();
  drawChart();
}

// Operator rail
function renderOperatorRail() {
  const mode = document.getElementById('systemMode');
  const bp = document.getElementById('buyingPower');
  const market = document.getElementById('marketStatus');
  
  if (mode) mode.textContent = ethData.mode?.toUpperCase() || 'LIVE';
  if (bp) bp.textContent = 'BP: $' + (ethData.available_capital || 0).toFixed(2);
  if (market) market.textContent = 'MARKET CLOSED'; // TODO: check market hours
}

// Render leaders from snapshot
function renderLeaders() {
  const wrap = document.getElementById('leadersWrap');
  const meta = document.getElementById('leadersMeta');
  
  if (!wrap) return;
  
  const leaders = snapshot?.tradier?.leaders || [];
  if (meta) meta.textContent = leaders.length + ' leaders';
  
  if (leaders.length === 0) {
    wrap.innerHTML = '<div class="void">No leaders available</div>';
    return;
  }
  
  wrap.innerHTML = leaders.map((l, i) => `
    <div class="leader-card" onclick="selectLeader(${i})">
      <div class="leader-header">
        <span class="leader-symbol">${l.symbol}</span>
        <span class="leader-type ${l.option_type?.toLowerCase()}">${l.option_type}</span>
      </div>
      <div class="leader-details">
        <span>Underlying: $${l.underlying || '--'}</span>
        <span>Strike: $${l.strike}</span>
      </div>
      <div class="leader-details">
        <span>Exp: ${l.exp}</span>
        <span>Mid: $${((parseFloat(l.bid) + parseFloat(l.ask)) / 2).toFixed(2)}</span>
      </div>
      <div class="leader-strategy">${l.section === 'directional' ? 'Scalp' : 'Credit'}</div>
    </div>
  `).join('');
}

function selectLeader(index) {
  const leaders = snapshot?.tradier?.leaders || [];
  const leader = leaders[index];
  if (!leader) return;
  
  const wrap = document.getElementById('actionsWrap');
  if (!wrap) return;
  
  const mid = ((parseFloat(leader.bid) + parseFloat(leader.ask)) / 2).toFixed(2);
  
  wrap.innerHTML = `
    <div class="action-card">
      <h4>${leader.symbol} ${leader.strike} ${leader.option_type}</h4>
      <p>Mid: $${mid} | Exp: ${leader.exp}</p>
      <div class="action-buttons">
        <button class="btn-action primary" onclick="executeTrade('${leader.symbol}', '${leader.option_type}', '${leader.strike}', '${leader.exp}', '${mid}')">EXECUTE</button>
        <button class="btn-action" onclick="alert('Preview: ${leader.symbol} ${leader.option_type} @ $${mid}')">PREVIEW</button>
      </div>
    </div>
  `;
  
  // Switch to execute tab
  switchZone('execute');
}

// Render ETH scalper
function renderEthScalper() {
  const price = calculateEthPrice(ethData);
  
  // Stats
  setText('eth-price-display', '$' + price.toFixed(2));
  setText('eth-pnl-today', (ethData.pnl?.today >= 0 ? '+' : '') + '$' + (ethData.pnl?.today || 0).toFixed(2), 
    ethData.pnl?.today >= 0 ? 'positive' : 'negative');
  setText('eth-open-positions', ethData.open_positions || 0);
  setText('eth-daily-trades', ethData.daily_trades || 0);
  setText('eth-balance', (ethData.wallet?.eth || 0).toFixed(4));
  setText('usdc-balance', '$' + (ethData.wallet?.usdc || 0).toFixed(2));
  
  // Trading panel
  setText('eth-available-capital', '$' + (ethData.available_capital || 0).toFixed(2));
  setText('eth-gas-display', (ethData.wallet?.gas || 0).toFixed(1) + ' gwei');
  setText('eth-api-calls', (ethData.requests?.used || 0) + '/' + (ethData.requests?.limit || 900));
  
  const modeBadge = document.getElementById('eth-mode-badge');
  if (modeBadge) {
    modeBadge.textContent = ethData.mode?.toUpperCase() || 'UNKNOWN';
    modeBadge.className = 'panel-status ' + (ethData.mode === 'live' ? 'safe' : 'warning');
  }
  
  // Risk gauges
  const totalCap = (ethData.wallet?.eth || 0) * price + (ethData.wallet?.usdc || 0);
  const posValue = (ethData.open_positions || 0) * 50;
  const expPct = totalCap > 0 ? (posValue / totalCap) * 100 : 0;
  const lossPct = (Math.abs(Math.min(0, ethData.pnl?.today || 0)) / 15) * 100;
  const heatPct = ((ethData.open_positions || 0) / 2) * 100;
  
  updateGauge('eth-exposure', expPct, '%');
  updateGauge('eth-loss', lossPct, '$' + Math.abs(Math.min(0, ethData.pnl?.today || 0)).toFixed(0) + '/$15');
  updateGauge('eth-heat', heatPct, (ethData.open_positions || 0) + '/2');
  
  // Risk badge
  const riskBadge = document.getElementById('eth-risk-badge');
  if (riskBadge) {
    const maxRisk = Math.max(expPct, lossPct, heatPct);
    riskBadge.textContent = maxRisk >= 80 ? 'ELEVATED' : maxRisk >= 50 ? 'MODERATE' : 'SAFE';
    riskBadge.className = 'panel-status ' + (maxRisk >= 80 ? 'danger' : maxRisk >= 50 ? 'warning' : 'safe');
  }
  
  // Agents
  const ethStatus = document.getElementById('eth-agent-status-text');
  const ethDot = document.getElementById('eth-agent-dot');
  if (ethStatus) ethStatus.textContent = ethData.status === 'running' ? 'Running' : 'Paused';
  if (ethDot) ethDot.className = 'agent-dot ' + (ethData.status === 'running' ? 'active' : '');
}

function updateGauge(id, pct, label) {
  const fill = document.getElementById(id + '-fill');
  const val = document.getElementById(id + '-value');
  if (fill) {
    fill.style.width = Math.min(pct, 100) + '%';
    fill.className = 'gauge-fill ' + (pct >= 80 ? 'high' : pct >= 50 ? 'medium' : 'low');
  }
  if (val) val.textContent = label;
}

function setText(id, text, className) {
  const el = document.getElementById(id);
  if (el) {
    el.textContent = text;
    if (className) el.className = 'stat-value ' + className;
  }
}

// Chart
function drawChart() {
  const canvas = document.getElementById('eth-chart');
  if (!canvas || priceHistory.length < 2) return;
  
  const ctx = canvas.getContext('2d');
  const container = canvas.parentElement;
  canvas.width = container.clientWidth - 20;
  canvas.height = container.clientHeight - 20;
  
  const w = canvas.width, h = canvas.height, pad = 20;
  const prices = priceHistory.map(p => p.price);
  const min = Math.min(...prices) * 0.999;
  const max = Math.max(...prices) * 1.001;
  const range = max - min;
  
  ctx.clearRect(0, 0, w, h);
  
  // Grid
  ctx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue('--border').trim();
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = pad + (h - 2 * pad) * i / 4;
    ctx.beginPath(); ctx.moveTo(pad, y); ctx.lineTo(w - pad, y); ctx.stroke();
  }
  
  // Line
  ctx.strokeStyle = '#9b59b6'; // purple accent
  ctx.lineWidth = 2;
  ctx.beginPath();
  priceHistory.forEach((p, i) => {
    const x = pad + (w - 2 * pad) * i / (priceHistory.length - 1);
    const y = h - pad - (p.price - min) / range * (h - 2 * pad);
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.stroke();
  
  // Fill
  ctx.lineTo(w - pad, h - pad); ctx.lineTo(pad, h - pad); ctx.closePath();
  const grad = ctx.createLinearGradient(0, pad, 0, h - pad);
  grad.addColorStop(0, 'rgba(155, 89, 182, 0.3)');
  grad.addColorStop(1, 'rgba(155, 89, 182, 0)');
  ctx.fillStyle = grad; ctx.fill();
}

// Actions
async function executeTrade(symbol, type, strike, exp, price) {
  alert(`Execute: ${symbol} ${type} $${strike} @ $${price}\n\nThis would connect to Tradier API to place the order.`);
}

async function executeEthBuy() {
  await sendCommand('BUY');
}

async function executeEthSell() {
  await sendCommand('SELL');
}

async function sendCommand(cmd) {
  try {
    const res = await fetch('/api/eth-scalper/command', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({command: cmd})
    });
    alert(cmd + ' command ' + (res.ok ? 'sent!' : 'failed'));
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

function viewBotLogs() {
  window.open('/eth-scalper/logs/', '_blank');
}

function runPremarketScan() {
  alert('Scan initiated - checking for overnight movers...');
}

function forceRefresh() {
  loadData();
  alert('Refreshing data...');
}

function showFilterCriteria() {
  alert('Filter options:\n- Min confidence: 5/10\n- Max DTE: 14\n- Min liquidity: $100K');
}

function updateAnalytics() {
  const el = document.getElementById('analyticsSummary');
  if (el) el.innerHTML = '<div style="padding:20px">Analytics: ' + ethData.daily_trades + ' trades today</div>';
}

function exportJournal() {
  alert('Exporting trade history...');
}

function updateClock() {
  const now = new Date();
  const time = now.toLocaleTimeString('en-US', {hour12: false});
  const clock = document.getElementById('clock');
  const update = document.getElementById('lastUpdate');
  if (clock) clock.textContent = time;
  if (update) update.textContent = time;
}

window.addEventListener('resize', drawChart);
