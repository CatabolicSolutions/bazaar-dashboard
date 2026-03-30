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

function getLeaderState(leader) {
  if (!leader) return { queued: false, watched: false, queueItem: null, watchItem: null };
  const positions = currentSnapshot?.activePositions?.positions || [];
  const queue = currentSnapshot?.executionQueue?.queue || [];
  const instrument = leaderInstrument(leader);

  const queueItem = queue.find(item => item.symbol === leader.symbol && item.instrument === instrument) || null;
  const watchItem = positions.find(item => item.symbol === leader.symbol && item.instrument === instrument && item.status === 'watch') || null;

  return {
    queued: Boolean(queueItem),
    watched: Boolean(watchItem),
    queueItem,
    watchItem,
  };
}

function getSelectedLeaderFeedback(leader) {
  const payload = currentSnapshot?.tradier?.actionFeedback || {};
  const feedback = payload.feedback;
  if (!leader || !feedback) return null;
  const instrument = leaderInstrument(leader);
  if (feedback.symbol !== leader.symbol || feedback.instrument !== instrument) return null;
  return {
    updatedAt: payload.updatedAt,
    ...feedback,
  };
}

function statusBadge(label, kind = 'neutral') {
  return `<span class="status-chip ${kind}">${escapeHtml(label)}</span>`;
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

  wrap.innerHTML = leaders.map((leader, index) => {
    const state = getLeaderState(leader);
    const feedback = getSelectedLeaderFeedback(leader);
    const stateBadges = [
      leader.fallback ? '<span class="pill warn-pill">Fallback Expiry</span>' : `<span class="pill neutral-pill">${escapeHtml(leader.label || 'Primary')}</span>`,
      state.queued ? statusBadge('Queued', 'queued') : '',
      state.watched ? statusBadge('Watching', 'watch') : '',
      feedback ? statusBadge('Recent action', 'recent') : '',
    ].filter(Boolean).join('');

    return `
      <button class="leader-row ${index === selectedLeaderIndex ? 'selected' : ''}" data-index="${index}">
        <div class="leader-row-top">
          <div>
            <div class="section">${escapeHtml(formatSection(leader.section))}</div>
            <div class="headline">${escapeHtml(leaderDisplayName(leader))}</div>
          </div>
          <div class="badge-stack">${stateBadges}</div>
        </div>
        <div class="leader-row-grid">
          <div><span class="label">Underlying</span><span class="value">${escapeHtml(leader.underlying)}</span></div>
          <div><span class="label">Delta</span><span class="value">${escapeHtml(leader.delta)}</span></div>
          <div><span class="label">Bid / Ask</span><span class="value">${escapeHtml(leader.bid)} / ${escapeHtml(leader.ask)}</span></div>
          <div><span class="label">Confidence</span><span class="value">${escapeHtml(leader.confidence)}</span></div>
        </div>
      </button>
    `;
  }).join('');

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

  const state = getLeaderState(leader);
  const feedback = getSelectedLeaderFeedback(leader);
  const stateSummary = [
    state.queued ? statusBadge('Already queued', 'queued') : statusBadge('Not queued', 'neutral'),
    state.watched ? statusBadge('On watch list', 'watch') : statusBadge('Not watched', 'neutral'),
    feedback ? statusBadge('Recent action recorded', 'recent') : '',
  ].filter(Boolean).join('');

  meta.textContent = `${formatSection(leader.section)} · ${leader.symbol || '—'} · ${leader.exp || '—'}`;
  wrap.className = 'detail-wrap';
  wrap.innerHTML = `
    <div class="detail-state-row">
      <div>
        <div class="label">Local Action State</div>
        <div class="badge-stack">${stateSummary}</div>
      </div>
    </div>
    ${feedback ? `
      <div class="detail-feedback-row">
        <div class="label">Recent Action Result</div>
        <div class="feedback-title">${escapeHtml(feedback.result)}</div>
        <div class="feedback-body">${escapeHtml(feedback.stateChange)}</div>
        <div class="muted small">${escapeHtml(feedback.action)} · ${escapeHtml(feedback.updatedAt || 'unknown time')}</div>
      </div>
    ` : ''}
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
      ${detailField('Queue Status', state.queued ? 'Queued in local execution queue' : 'Not queued locally')}
      ${detailField('Watch Status', state.watched ? 'Tracked in local watch state' : 'Not watched locally')}
      ${state.queueItem ? detailField('Queued Trigger', state.queueItem.trigger || '—', true) : ''}
      ${state.watchItem ? detailField('Watch Invalidation', state.watchItem.invalidation || '—', true) : ''}
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

function inferActions(leader) {
  if (!leader) return [];

  const state = getLeaderState(leader);

  return [
    {
      key: 'queue_selected_leader',
      title: 'Add to execution queue',
      detail: state.queued
        ? 'Selected ticket is already represented in local execution queue state.'
        : 'Write this selected Tradier ticket into local execution queue state.',
      disabled: state.queued,
      cta: state.queued ? 'Already queued' : 'Queue Selected Ticket',
      stateLabel: state.queued ? 'Visible state: queued' : 'Visible state: not queued',
      stateKind: state.queued ? 'queued' : 'neutral',
    },
    {
      key: 'watch_selected_leader',
      title: 'Add to watch list',
      detail: state.watched
        ? 'Selected ticket is already represented in local active_positions state as watch.'
        : 'Write this selected Tradier ticket into local watch state for operator tracking.',
      disabled: state.watched,
      cta: state.watched ? 'Already watching' : 'Watch Selected Ticket',
      stateLabel: state.watched ? 'Visible state: watching' : 'Visible state: not watched',
      stateKind: state.watched ? 'watch' : 'neutral',
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

  const feedbackText = data.feedback?.stateChange || `${data.action} saved at ${data.updatedAt}`;
  status.textContent = feedbackText;
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

  const state = getLeaderState(leader);
  const feedback = getSelectedLeaderFeedback(leader);
  const actions = inferActions(leader);
  const actionStateSummary = [
    state.queued ? statusBadge('Queued in local state', 'queued') : statusBadge('Queue pending', 'neutral'),
    state.watched ? statusBadge('Watching in local state', 'watch') : statusBadge('Watch pending', 'neutral'),
    feedback ? statusBadge('Recent action feedback live', 'recent') : '',
  ].filter(Boolean).join('');

  wrap.className = 'actions-wrap';
  wrap.innerHTML = `
    <div class="action-summary">
      <div class="action-summary-title">Selected Ticket</div>
      <div class="action-summary-value">${escapeHtml(leaderDisplayName(leader))}</div>
      <div class="badge-stack">${actionStateSummary}</div>
      <div class="muted small">Real local actions only. No remote execution or workflow expansion.</div>
    </div>
    ${feedback ? `
      <div class="action-feedback-box">
        <div class="label">What Just Happened</div>
        <div class="feedback-title">${escapeHtml(feedback.result)}</div>
        <div class="feedback-body">${escapeHtml(feedback.stateChange)}</div>
        <div class="muted small">${escapeHtml(feedback.action)} · ${escapeHtml(feedback.updatedAt || 'unknown time')}</div>
      </div>
    ` : ''}
    <div class="action-list">
      ${actions.map(action => `
        <div class="action-item">
          <div class="action-item-top">
            <div class="action-title">${escapeHtml(action.title)}</div>
            ${statusBadge(action.stateLabel, action.stateKind)}
          </div>
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
