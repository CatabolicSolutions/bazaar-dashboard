const API_BASE = '';
const POLL_INTERVAL = 5000;

const el = {
  asof: document.getElementById('asof'),
  headlineDecision: document.getElementById('headline-decision'),
  headlineReason: document.getElementById('headline-reason'),
  headlineTradier: document.getElementById('headline-tradier'),
  headlineTradierSub: document.getElementById('headline-tradier-sub'),
  headlineBloc: document.getElementById('headline-bloc'),
  headlineBlocSub: document.getElementById('headline-bloc-sub'),
  headlineExposure: document.getElementById('headline-exposure'),
  headlineExposureSub: document.getElementById('headline-exposure-sub'),
  directiveTitle: document.getElementById('directive-title'),
  directiveBadge: document.getElementById('directive-badge'),
  directiveCopy: document.getElementById('directive-copy'),
  miniTradierCapital: document.getElementById('mini-tradier-capital'),
  miniBlocCapital: document.getElementById('mini-bloc-capital'),
  miniReality: document.getElementById('mini-reality'),
  readinessList: document.getElementById('readiness-list'),
  nextActions: document.getElementById('next-actions'),
  positionsList: document.getElementById('positions-list'),
  activityList: document.getElementById('activity-list')
};

function fmtMoney(v, digits = 2) {
  const n = Number(v);
  if (!Number.isFinite(n)) return '--';
  return `$${n.toFixed(digits)}`;
}

function safe(v, fallback = '--') {
  return v == null || v === '' ? fallback : String(v);
}

function renderError(message) {
  if (el.directiveTitle) el.directiveTitle.textContent = 'Client render error';
  if (el.directiveCopy) el.directiveCopy.textContent = safe(message);
}

function renderHQ(payload) {
  const live = (payload && payload.live) || {};
  const wallet = live.wallet || {};
  const positions = Array.isArray(live.positions) ? live.positions : [];
  const holdingAsset = safe(live.holding_asset, 'Inventory');
  const holdingUnits = live.holding_units;
  const invested = Number(live.invested_capital_usd || 0);
  const deployable = Number(live.deployable_capital_usd || 0);
  const activePositions = Number(live.active_positions || (positions.length || 0));
  const status = safe(live.compounding_state, 'unknown');

  el.asof.textContent = `Updated ${new Date().toLocaleString()} • HQv6`;
  el.headlineDecision.textContent = status === 'holding_active_inventory' ? 'Monitor compounding hold' : 'Monitor live state';
  el.headlineReason.textContent = status === 'holding_active_inventory'
    ? `Holding ${holdingAsset}${holdingUnits != null ? ` (${holdingUnits})` : ''} as active compounding inventory.`
    : 'Waiting for live system truth.';

  el.headlineTradier.textContent = 'Tradier readiness';
  el.headlineTradierSub.textContent = 'Separate execution path';

  el.headlineBloc.textContent = status === 'holding_active_inventory' ? 'Holding active inventory' : 'Bloc runtime';
  el.headlineBlocSub.textContent = status === 'holding_active_inventory'
    ? `${holdingAsset} • ${fmtMoney(invested)} invested`
    : `${fmtMoney(deployable)} deployable`;

  el.headlineExposure.textContent = `${activePositions || 0} ${(activePositions || 0) === 1 ? 'position' : 'positions'}`;
  el.headlineExposureSub.textContent = status === 'holding_active_inventory'
    ? 'Active compounding inventory requires supervision'
    : 'No active risk detected';

  el.directiveTitle.textContent = status === 'holding_active_inventory' ? 'Monitor compounding hold' : 'Stand by';
  el.directiveBadge.textContent = status === 'holding_active_inventory' ? 'ACTIVE HOLD' : 'MONITORING';
  el.directiveBadge.className = `decision-badge ${status === 'holding_active_inventory' ? 'badge-amber' : 'badge-amber'}`;
  el.directiveCopy.textContent = status === 'holding_active_inventory'
    ? `Deployed capital is in ${holdingAsset}. Focus on recycle and exit quality, not fresh entry.`
    : 'Pulling live system truth.';

  el.miniTradierCapital.textContent = '--';
  el.miniBlocCapital.textContent = status === 'holding_active_inventory'
    ? `${fmtMoney(invested)} in ${holdingAsset}`
    : `${fmtMoney(deployable)}`;
  el.miniReality.textContent = `ETH ${fmtMoney(wallet.eth_price_usd || wallet.eth_price || NaN)} | Wallet ${safe(wallet.address)}`;

  el.readinessList.innerHTML = `
    <div class="ops-item">
      <div class="ops-item-head">
        <div class="ops-name">Bloc</div>
        <div class="decision-badge badge-amber">LIVE</div>
      </div>
      <div class="ops-summary">${status === 'holding_active_inventory' ? `Holding ${holdingAsset} for managed recycle.` : 'Runtime connected.'}</div>
      <div class="kv">
        <div><span>State</span>${safe(status)}</div>
        <div><span>Holding</span>${holdingAsset}${holdingUnits != null ? ` ${holdingUnits}` : ''}</div>
        <div><span>Invested</span>${fmtMoney(invested)}</div>
        <div><span>Deployable</span>${fmtMoney(deployable)}</div>
      </div>
      <div class="blocker"><strong>Operator focus:</strong> ${status === 'holding_active_inventory' ? 'Supervise exit and recycle conditions.' : 'Await live setup or funded state.'}</div>
    </div>
  `;

  el.nextActions.innerHTML = `
    <div class="next-action"><div class="num">1</div><div class="action-copy"><strong>Supervise active hold</strong>Track ${holdingAsset} exposure and recycle path.</div></div>
    <div class="next-action"><div class="num">2</div><div class="action-copy"><strong>Verify mark and units</strong>Confirm ${holdingUnits != null ? holdingUnits : '--'} units and ${fmtMoney(invested)} invested.</div></div>
    <div class="next-action"><div class="num">3</div><div class="action-copy"><strong>Do not force new entry</strong>Compounding capital is deployed, not missing.</div></div>
  `;

  if (positions.length) {
    el.positionsList.innerHTML = positions.map((pos) => `
      <div class="position-row">
        <div class="position-top">
          <div>${safe(pos.asset, holdingAsset)} HOLD</div>
          <div>${fmtMoney(invested)}</div>
        </div>
        <div class="meta-row">
          <span>Units: ${safe(pos.units, holdingUnits)}</span>
          <span>Status: ${safe(pos.status, status)}</span>
          <span>Source: ${safe(pos.source)}</span>
        </div>
      </div>
    `).join('');
  } else {
    el.positionsList.innerHTML = `
      <div class="position-row">
        <div class="position-top">
          <div>${holdingAsset} HOLD</div>
          <div>${fmtMoney(invested)}</div>
        </div>
        <div class="meta-row">
          <span>Units: ${holdingUnits != null ? holdingUnits : '--'}</span>
          <span>Status: ${status}</span>
          <span>Source: wallet truth</span>
        </div>
      </div>
    `;
  }

  const events = Array.isArray(payload.events) ? payload.events : [];
  el.activityList.innerHTML = events.length
    ? events.map((row) => `
      <div class="activity-row">
        <div class="activity-top"><div>${safe(row.title)}</div><div>${safe(row.created_at)}</div></div>
        <div class="meta-row"><span>${safe(row.event_type)}</span><span>${safe(row.severity)}</span></div>
      </div>
    `).join('')
    : '<div class="activity-empty">No recent HQ events available.</div>';
}

async function pollData() {
  try {
    const payload = await fetch(`${API_BASE}/api/hq/status`).then(r => r.json());
    renderHQ(payload);
  } catch (err) {
    console.error('War Room HQ poll failed:', err);
    renderError(err && err.message ? err.message : String(err));
  }
}

pollData();
setInterval(pollData, POLL_INTERVAL);
