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

function bindPositionActions() {
  document.querySelectorAll('.remove-position-btn').forEach(btn => {
    btn.onclick = () => {
      btn.closest('.position-card').remove();
    };
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

function renderSimpleList(id, items, emptyText) {
  const wrap = document.getElementById(id);
  if (!items?.length) {
    wrap.innerHTML = `<div class="placeholder">${emptyText}</div>`;
    return;
  }
  wrap.innerHTML = items.map(item => `<div class="leader"><pre class="mono">${JSON.stringify(item, null, 2)}</pre></div>`).join('');
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

async function refresh() {
  const snapshot = await loadSnapshot();
  document.getElementById('updatedAt').textContent = `Snapshot: ${snapshot.updatedAt}`;
  renderHealth(snapshot.systemHealth || {});
  renderBoard(snapshot.tradier?.rawBoard || '');
  renderLeaders(snapshot.tradier?.leaders || []);
  renderPositions(snapshot.activePositions || {});
  renderSimpleList('queueWrap', snapshot.executionQueue?.queue, 'No queued actions loaded.');
}

document.getElementById('refreshBtn').addEventListener('click', refresh);
document.getElementById('savePositionsBtn').addEventListener('click', savePositions);
refresh().catch(err => {
  document.getElementById('serverState').textContent = 'ERROR';
  document.getElementById('serverState').className = 'status-pill bad';
  document.getElementById('boardPreview').textContent = err.message;
});
setInterval(() => {
  refresh().catch(() => {});
}, 30000);
