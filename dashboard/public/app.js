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

function renderSimpleList(id, items, emptyText) {
  const wrap = document.getElementById(id);
  if (!items?.length) {
    wrap.innerHTML = `<div class="placeholder">${emptyText}</div>`;
    return;
  }
  wrap.innerHTML = items.map(item => `<div class="leader"><pre class="mono">${JSON.stringify(item, null, 2)}</pre></div>`).join('');
}

async function refresh() {
  const snapshot = await loadSnapshot();
  document.getElementById('updatedAt').textContent = `Snapshot: ${snapshot.updatedAt}`;
  renderHealth(snapshot.systemHealth || {});
  renderBoard(snapshot.tradier?.rawBoard || '');
  renderLeaders(snapshot.tradier?.leaders || []);
  renderSimpleList('positionsWrap', snapshot.activePositions?.positions, 'No active positions loaded.');
  renderSimpleList('queueWrap', snapshot.executionQueue?.queue, 'No queued actions loaded.');
}

document.getElementById('refreshBtn').addEventListener('click', refresh);
refresh().catch(err => {
  document.getElementById('serverState').textContent = 'ERROR';
  document.getElementById('serverState').className = 'status-pill bad';
  document.getElementById('boardPreview').textContent = err.message;
});
setInterval(() => {
  refresh().catch(() => {});
}, 30000);
