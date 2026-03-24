async function loadSnapshot() {
  const res = await fetch('./snapshot.json?ts=' + Date.now());
  if (!res.ok) throw new Error('Failed to load snapshot');
  return res.json();
}

function renderHealth(health) {
  const wrap = document.getElementById('healthGrid');
  const items = [
    ['Tradier API Key', health.tradierApiKeyLoaded ? 'Loaded' : 'Missing', health.tradierApiKeyLoaded ? 'good' : 'bad'],
    ['Board Artifact', health.tradierBoardPresent ? 'Present' : 'Missing', health.tradierBoardPresent ? 'good' : 'bad'],
    ['Board Updated', health.tradierBoardUpdatedAt || 'N/A', 'muted'],
    ['Latest Commit', health.latestCommit || 'N/A', 'muted'],
  ];
  wrap.innerHTML = items.map(([label, value, klass]) => `
    <div class="health-item">
      <div class="label">${label}</div>
      <div class="value ${klass}">${value}</div>
    </div>
  `).join('');
}

function renderBoard(raw) {
  document.getElementById('boardPreview').textContent = raw || 'No board available.';
}

function renderLeaders(leaders) {
  const wrap = document.getElementById('leadersWrap');
  if (!leaders?.length) {
    wrap.innerHTML = '<div class="placeholder">No leaders parsed yet.</div>';
    return;
  }
  wrap.innerHTML = leaders.map(leader => `
    <div class="leader">
      <div class="section">${leader.section}</div>
      <div class="headline">${leader.headline}</div>
      <ul>${leader.details.map(d => `<li>${d}</li>`).join('')}</ul>
    </div>
  `).join('');
}

function positionTemplate(position = {}) {
  return {
    symbol: position.symbol || '',
    instrument: position.instrument || '',
    entry: position.entry || '',
    current: position.current || '',
    size: position.size || '',
    invalidation: position.invalidation || '',
    targets: position.targets || '',
    notes: position.notes || '',
    status: position.status || 'open',
  };
}

function queueTemplate(item = {}) {
  return {
    symbol: item.symbol || '',
    instrument: item.instrument || '',
    side: item.side || '',
    trigger: item.trigger || '',
    thesis: item.thesis || '',
    priority: item.priority || 'normal',
    status: item.status || 'queued',
    notes: item.notes || '',
  };
}

function collectPositions() {
  return Array.from(document.querySelectorAll('.position-card')).map(card => ({
    symbol: card.querySelector('[name="symbol"]').value,
    instrument: card.querySelector('[name="instrument"]').value,
    entry: card.querySelector('[name="entry"]').value,
    current: card.querySelector('[name="current"]').value,
    size: card.querySelector('[name="size"]').value,
    invalidation: card.querySelector('[name="invalidation"]').value,
    targets: card.querySelector('[name="targets"]').value,
    notes: card.querySelector('[name="notes"]').value,
    status: card.querySelector('[name="status"]').value,
  }));
}

function collectQueue() {
  return Array.from(document.querySelectorAll('.queue-card')).map(card => ({
    symbol: card.querySelector('[name="symbol"]').value,
    instrument: card.querySelector('[name="instrument"]').value,
    side: card.querySelector('[name="side"]').value,
    trigger: card.querySelector('[name="trigger"]').value,
    thesis: card.querySelector('[name="thesis"]').value,
    priority: card.querySelector('[name="priority"]').value,
    status: card.querySelector('[name="status"]').value,
    notes: card.querySelector('[name="notes"]').value,
  }));
}

function makePositionCard(position = {}) {
  const p = positionTemplate(position);
  return `
    <div class="position-card">
      <div class="position-grid">
        <input name="symbol" placeholder="Symbol" value="${p.symbol}">
        <input name="instrument" placeholder="Instrument" value="${p.instrument}">
        <input name="entry" placeholder="Entry" value="${p.entry}">
        <input name="current" placeholder="Current" value="${p.current}">
        <input name="size" placeholder="Size" value="${p.size}">
        <select name="status">
          <option value="open" ${p.status === 'open' ? 'selected' : ''}>open</option>
          <option value="watch" ${p.status === 'watch' ? 'selected' : ''}>watch</option>
          <option value="closed" ${p.status === 'closed' ? 'selected' : ''}>closed</option>
        </select>
        <textarea name="invalidation" placeholder="Invalidation">${p.invalidation}</textarea>
        <textarea name="targets" placeholder="Targets">${p.targets}</textarea>
        <textarea name="notes" placeholder="Notes">${p.notes}</textarea>
      </div>
      <div class="position-actions">
        <div class="muted small">Editable position state</div>
        <button class="link-btn remove-position-btn">Remove</button>
      </div>
    </div>
  `;
}

function makeQueueCard(item = {}) {
  const q = queueTemplate(item);
  return `
    <div class="queue-card">
      <div class="queue-grid">
        <input name="symbol" placeholder="Symbol" value="${q.symbol}">
        <input name="instrument" placeholder="Instrument" value="${q.instrument}">
        <input name="side" placeholder="Side" value="${q.side}">
        <input name="trigger" placeholder="Trigger" value="${q.trigger}">
        <select name="priority">
          <option value="low" ${q.priority === 'low' ? 'selected' : ''}>low</option>
          <option value="normal" ${q.priority === 'normal' ? 'selected' : ''}>normal</option>
          <option value="high" ${q.priority === 'high' ? 'selected' : ''}>high</option>
        </select>
        <select name="status">
          <option value="queued" ${q.status === 'queued' ? 'selected' : ''}>queued</option>
          <option value="approved" ${q.status === 'approved' ? 'selected' : ''}>approved</option>
          <option value="entered" ${q.status === 'entered' ? 'selected' : ''}>entered</option>
          <option value="closed" ${q.status === 'closed' ? 'selected' : ''}>closed</option>
        </select>
        <textarea name="thesis" placeholder="Thesis">${q.thesis}</textarea>
        <textarea name="notes" placeholder="Notes">${q.notes}</textarea>
      </div>
      <div class="position-actions">
        <div class="muted small">Editable execution queue item</div>
        <button class="link-btn remove-queue-btn">Remove</button>
      </div>
    </div>
  `;
}

function bindPositionActions() {
  document.querySelectorAll('.remove-position-btn').forEach(btn => {
    btn.onclick = () => btn.closest('.position-card').remove();
  });
}

function bindQueueActions() {
  document.querySelectorAll('.remove-queue-btn').forEach(btn => {
    btn.onclick = () => btn.closest('.queue-card').remove();
  });
}

function renderPositions(state) {
  const wrap = document.getElementById('positionsWrap');
  const positions = state?.positions || [];
  const cards = positions.length ? positions.map(makePositionCard).join('') : makePositionCard();
  wrap.innerHTML = cards + '<button id="addPositionBtn" class="link-btn">Add Position</button>';
  bindPositionActions();
  document.getElementById('addPositionBtn').onclick = () => {
    document.getElementById('addPositionBtn').insertAdjacentHTML('beforebegin', makePositionCard());
    bindPositionActions();
  };
  document.getElementById('positionsStatus').textContent = state?.updatedAt ? `Last saved: ${state.updatedAt}` : 'Unsaved draft';
}

function renderQueue(state) {
  const wrap = document.getElementById('queueWrap');
  const queue = state?.queue || [];
  const cards = queue.length ? queue.map(makeQueueCard).join('') : makeQueueCard();
  wrap.innerHTML = cards + '<button id="addQueueBtn" class="link-btn">Add Queue Item</button>';
  bindQueueActions();
  document.getElementById('addQueueBtn').onclick = () => {
    document.getElementById('addQueueBtn').insertAdjacentHTML('beforebegin', makeQueueCard());
    bindQueueActions();
  };
  document.getElementById('queueStatus').textContent = state?.updatedAt ? `Last saved: ${state.updatedAt}` : 'Unsaved draft';
}

async function savePositions() {
  const payload = { positions: collectPositions() };
  const res = await fetch('/api/positions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  const status = document.getElementById('positionsStatus');
  if (!res.ok || !data.ok) {
    status.textContent = `Save failed: ${data.error || 'unknown error'}`;
    return;
  }
  status.textContent = `Saved ${data.count} position(s) at ${data.updatedAt}`;
  await refresh();
}

async function saveQueue() {
  const payload = { queue: collectQueue() };
  const res = await fetch('/api/queue', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  const status = document.getElementById('queueStatus');
  if (!res.ok || !data.ok) {
    status.textContent = `Save failed: ${data.error || 'unknown error'}`;
    return;
  }
  status.textContent = `Saved ${data.count} queue item(s) at ${data.updatedAt}`;
  await refresh();
}

async function refresh() {
  const snapshot = await loadSnapshot();
  document.getElementById('updatedAt').textContent = `Snapshot: ${snapshot.updatedAt}`;
  renderHealth(snapshot.systemHealth || {});
  renderBoard(snapshot.tradier?.rawBoard || '');
  renderLeaders(snapshot.tradier?.leaders || []);
  renderPositions(snapshot.activePositions || {});
  renderQueue(snapshot.executionQueue || {});
}

document.getElementById('refreshBtn').addEventListener('click', refresh);
document.getElementById('savePositionsBtn').addEventListener('click', savePositions);
document.getElementById('saveQueueBtn').addEventListener('click', saveQueue);
refresh().catch(err => {
  document.getElementById('serverState').textContent = 'ERROR';
  document.getElementById('serverState').className = 'status-pill bad';
  document.getElementById('boardPreview').textContent = err.message;
});
setInterval(() => {
  refresh().catch(() => {});
}, 30000);
