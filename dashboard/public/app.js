let currentSnapshot = null;
let selectedLeaderIndex = 0;

async function loadSnapshot() {
  const res = await fetch('./snapshot.json?ts=' + Date.now());
  if (!res.ok) throw new Error('Failed to load snapshot');
  return res.json();
}

function escapeHtml(value) {
  return String(value ?? '—')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function formatSection(section) {
  return section === 'premium' ? 'Premium / Credit' : 'Directional / Scalping';
}

function leaderDisplayName(leader) {
  return `${leader.symbol || '—'} ${leader.option_type || ''} ${leader.strike || ''} ${leader.exp || ''}`.trim();
}

function leaderInstrument(leader) {
  return `${leader.exp || ''} ${leader.strike || ''} ${leader.option_type || ''}`.trim();
}

function getSelectedLeader() {
  return currentSnapshot?.tradier?.leaders?.[selectedLeaderIndex] || null;
}

function renderOverview(snapshot) {
  const health = snapshot.systemHealth || {};
  const tradier = snapshot.tradier || {};
  const overview = tradier.overview || {};
  const items = [
    ['Board Status', health.tradierBoardPresent ? 'Present' : 'Missing', health.tradierBoardPresent ? 'good' : 'bad'],
    ['Board Updated', health.tradierBoardUpdatedAt || 'N/A', 'muted'],
    ['Leaders Parsed', overview.leaderCount ?? tradier.leaders?.length ?? 0, 'accent'],
    ['Directional', overview.directionalCount ?? 0, 'muted'],
    ['Premium', overview.premiumCount ?? 0, 'muted'],
    ['Fallback Leaders', overview.fallbackCount ?? 0, overview.fallbackCount ? 'warn' : 'good'],
    ['VIX', overview.vix ?? 'N/A', 'muted'],
    ['Latest Commit', health.latestCommit || 'N/A', 'muted'],
  ];

  document.getElementById('overviewGrid').innerHTML = items.map(([label, value, klass]) => `
    <div class="overview-item">
      <div class="label">${escapeHtml(label)}</div>
      <div class="value ${klass}">${escapeHtml(value)}</div>
    </div>
  `).join('');
}

function renderLeaders(leaders) {
  const wrap = document.getElementById('leadersWrap');
  if (!leaders?.length) {
    wrap.innerHTML = '<div class="placeholder">No Tradier leaders parsed yet.</div>';
    renderDetail(null);
    renderActions(null);
    return;
  }

  if (selectedLeaderIndex >= leaders.length) {
    selectedLeaderIndex = 0;
  }

  wrap.innerHTML = leaders.map((leader, index) => `
    <button class="leader-row ${index === selectedLeaderIndex ? 'selected' : ''}" data-index="${index}">
      <div class="leader-row-top">
        <div>
          <div class="section">${escapeHtml(formatSection(leader.section))}</div>
          <div class="headline">${escapeHtml(leaderDisplayName(leader))}</div>
        </div>
        <div class="pill ${leader.fallback ? 'warn-pill' : 'neutral-pill'}">${leader.fallback ? 'Fallback Expiry' : escapeHtml(leader.label || 'Primary')}</div>
      </div>
      <div class="leader-row-grid">
        <div><span class="label">Underlying</span><span class="value">${escapeHtml(leader.underlying)}</span></div>
        <div><span class="label">Delta</span><span class="value">${escapeHtml(leader.delta)}</span></div>
        <div><span class="label">Bid / Ask</span><span class="value">${escapeHtml(leader.bid)} / ${escapeHtml(leader.ask)}</span></div>
        <div><span class="label">Confidence</span><span class="value">${escapeHtml(leader.confidence)}</span></div>
      </div>
    </button>
  `).join('');

  wrap.querySelectorAll('.leader-row').forEach(button => {
    button.addEventListener('click', () => {
      selectedLeaderIndex = Number(button.dataset.index);
      renderTradierSlice();
    });
  });

  renderDetail(leaders[selectedLeaderIndex]);
  renderActions(leaders[selectedLeaderIndex]);
}

function detailField(label, value, wide = false) {
  return `
    <div class="detail-field ${wide ? 'wide' : ''}">
      <div class="label">${escapeHtml(label)}</div>
      <div class="value">${escapeHtml(value)}</div>
    </div>
  `;
}

function renderDetail(leader) {
  const wrap = document.getElementById('detailWrap');
  const meta = document.getElementById('selectedMeta');
  if (!leader) {
    meta.textContent = 'No leader selected';
    wrap.className = 'detail-wrap placeholder';
    wrap.textContent = 'Select a Tradier leader to inspect ticket detail.';
    return;
  }

  meta.textContent = `${formatSection(leader.section)} · ${leader.symbol || '—'} · ${leader.exp || '—'}`;
  wrap.className = 'detail-wrap';
  wrap.innerHTML = `
    <div class="detail-grid">
      ${detailField('Symbol', leader.symbol)}
      ${detailField('Option Type', leader.option_type)}
      ${detailField('Strike', leader.strike)}
      ${detailField('Expiry', leader.exp)}
      ${detailField('DTE Label', leader.label)}
      ${detailField('Underlying', leader.underlying)}
      ${detailField('Delta', leader.delta)}
      ${detailField('Bid / Ask', `${leader.bid || '—'} / ${leader.ask || '—'}`)}
      ${detailField('Section', formatSection(leader.section))}
      ${detailField('Fallback Expiry', leader.fallback ? 'Yes' : 'No')}
      ${detailField('Thesis', leader.thesis, true)}
      ${detailField('Entry', leader.entry, true)}
      ${detailField('Invalidation', leader.invalidation, true)}
      ${detailField('Targets', leader.targets, true)}
      ${detailField('Risk', leader.risk, true)}
      ${detailField('Confidence', leader.confidence, true)}
      ${leader.note ? detailField('Note', leader.note, true) : ''}
      ${detailField('Source Headline', leader.headline, true)}
    </div>
  `;
}

function itemExists(list = [], predicate) {
  return list.some(predicate);
}

function inferActions(leader) {
  if (!leader) return [];

  const positions = currentSnapshot?.activePositions?.positions || [];
  const queue = currentSnapshot?.executionQueue?.queue || [];
  const instrument = leaderInstrument(leader);

  const queued = itemExists(queue, item => item.symbol === leader.symbol && item.instrument === instrument);
  const watched = itemExists(positions, item => item.symbol === leader.symbol && item.instrument === instrument && item.status === 'watch');

  return [
    {
      key: 'queue_selected_leader',
      title: 'Add to execution queue',
      detail: queued
        ? 'Selected ticket is already represented in local execution queue state.'
        : 'Write this selected Tradier ticket into local execution queue state.',
      disabled: queued,
      cta: queued ? 'Already queued' : 'Queue Selected Ticket',
    },
    {
      key: 'watch_selected_leader',
      title: 'Add to watch list',
      detail: watched
        ? 'Selected ticket is already represented in local active_positions state as watch.'
        : 'Write this selected Tradier ticket into local watch state for operator tracking.',
      disabled: watched,
      cta: watched ? 'Already watching' : 'Watch Selected Ticket',
    },
  ];
}

async function runSelectedAction(actionKey) {
  const leader = getSelectedLeader();
  const status = document.getElementById('actionStatus');
  if (!leader || !status) return;

  status.textContent = 'Submitting local action…';
  status.className = 'action-status muted small';

  const res = await fetch('/api/actions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: actionKey, leader }),
  });
  const data = await res.json();

  if (!res.ok || !data.ok) {
    status.textContent = `Action failed: ${data.error || 'unknown error'}`;
    status.className = 'action-status bad small';
    return;
  }

  status.textContent = `${data.action} saved at ${data.updatedAt}`;
  status.className = 'action-status good small';
  await refresh();
}

function bindActionButtons() {
  document.querySelectorAll('[data-action-key]').forEach(button => {
    button.addEventListener('click', () => runSelectedAction(button.dataset.actionKey).catch(err => {
      const status = document.getElementById('actionStatus');
      if (status) {
        status.textContent = err.message;
        status.className = 'action-status bad small';
      }
    }));
  });
}

function renderActions(leader) {
  const wrap = document.getElementById('actionsWrap');
  if (!leader) {
    wrap.className = 'actions-wrap placeholder';
    wrap.textContent = 'Select a Tradier leader to view local next actions.';
    return;
  }

  const actions = inferActions(leader);
  wrap.className = 'actions-wrap';
  wrap.innerHTML = `
    <div class="action-summary">
      <div class="action-summary-title">Selected Ticket</div>
      <div class="action-summary-value">${escapeHtml(leaderDisplayName(leader))}</div>
      <div class="muted small">Real local actions only. No remote execution or workflow expansion.</div>
    </div>
    <div class="action-list">
      ${actions.map(action => `
        <div class="action-item">
          <div class="action-title">${escapeHtml(action.title)}</div>
          <div class="action-detail">${escapeHtml(action.detail)}</div>
          <button class="action-btn" data-action-key="${escapeHtml(action.key)}" ${action.disabled ? 'disabled' : ''}>${escapeHtml(action.cta)}</button>
        </div>
      `).join('')}
    </div>
    <div id="actionStatus" class="action-status muted small">Selected-item actions write only to current local dashboard state files.</div>
  `;
  bindActionButtons();
}

function renderTradierSlice() {
  if (!currentSnapshot) return;
  renderOverview(currentSnapshot);
  renderLeaders(currentSnapshot.tradier?.leaders || []);
}

async function refresh() {
  currentSnapshot = await loadSnapshot();
  document.getElementById('updatedAt').textContent = `Snapshot: ${currentSnapshot.updatedAt}`;
  renderTradierSlice();
}

document.getElementById('refreshBtn').addEventListener('click', refresh);
refresh().catch(err => {
  document.getElementById('serverState').textContent = 'ERROR';
  document.getElementById('serverState').className = 'status-pill bad';
  document.getElementById('detailWrap').className = 'detail-wrap placeholder';
  document.getElementById('detailWrap').textContent = err.message;
});
setInterval(() => {
  refresh().catch(() => {});
}, 30000);
