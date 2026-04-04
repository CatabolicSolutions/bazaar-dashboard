// ═══════════════════════════════════════════════════════════════
// THE BAZAAR - Trading Command Center
// Zone-based navigation with operator-first layout
// ═══════════════════════════════════════════════════════════════

// Polyfill for crypto.randomUUID for non-secure contexts (HTTP)
if (typeof crypto !== 'undefined' && !crypto.randomUUID) {
  crypto.randomUUID = function() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
      const r = Math.random() * 16 | 0;
      const v = c === 'x' ? r : (r & 0x3 | 0x8);
      return v.toString(16);
    });
  };
}

// ═══════════════════════════════════════════════════════════════
// STATE MANAGEMENT
// ═══════════════════════════════════════════════════════════════

let currentSnapshot = null;
let selectedLeaderIndex = 0;
let selectedLeaderKey = null;
let lastActionStatus = null;
let currentUiMode = 'loading';
let currentLoadError = null;
let currentZone = 'market';

// ═══════════════════════════════════════════════════════════════
// ZONE NAVIGATION
// ═══════════════════════════════════════════════════════════════

function switchZone(zoneName) {
  // Update state
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
    // Small delay for animation
    setTimeout(() => targetZone.classList.add('active'), 10);
  }
  
  // Update nav pills
  document.querySelectorAll('.nav-pill').forEach(p => {
    p.classList.remove('active');
    if (p.dataset.zone === zoneName) {
      p.classList.add('active');
    }
  });
  
  // Zone-specific refresh
  if (zoneName === 'positions') {
    fetchPositions();
    fetchHeatmap();
  } else if (zoneName === 'journal') {
    updateAnalytics();
  }
}

// Initialize zones on load
document.addEventListener('DOMContentLoaded', () => {
  // Set initial zone
  document.querySelectorAll('.zone').forEach(z => z.style.display = 'none');
  switchZone('market');
  
  // Start data refresh
  refresh();
  setInterval(refresh, 30000);
});

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

function leaderKey(leader) {
  if (!leader) return null;
  return [leader.symbol || '', leader.exp || '', leader.strike || '', leader.option_type || '', leader.section || ''].join('|');
}

function getSnapshotAgeMinutes(snapshot) {
  const updatedAt = snapshot?.systemHealth?.tradierBoardUpdatedAt;
  if (!updatedAt) return null;
  const ms = Date.now() - new Date(updatedAt).getTime();
  if (!Number.isFinite(ms)) return null;
  return ms / 60000;
}

function describeSnapshotHealth(snapshot) {
  if (!snapshot) {
    return { tone: 'warn', text: 'Snapshot not loaded yet.' };
  }
  const boardPresent = snapshot?.systemHealth?.tradierBoardPresent;
  const ageMinutes = getSnapshotAgeMinutes(snapshot);
  if (!boardPresent) {
    return { tone: 'bad', text: 'Tradier board artifact is missing. Dashboard is running without current board data.' };
  }
  if (ageMinutes !== null && ageMinutes > 120) {
    return { tone: 'warn', text: `Tradier board artifact looks stale (${Math.round(ageMinutes)} min old). Verify local refresh path.` };
  }
  return { tone: 'good', text: 'Tradier board artifact is available.' };
}

function syncSelectedLeader(leaders = []) {
  if (!leaders.length) {
    selectedLeaderIndex = 0;
    selectedLeaderKey = null;
    return { leader: null, missingPreviousSelection: false };
  }

  if (selectedLeaderKey) {
    const matchedIndex = leaders.findIndex(leader => leaderKey(leader) === selectedLeaderKey);
    if (matchedIndex >= 0) {
      selectedLeaderIndex = matchedIndex;
      return { leader: leaders[matchedIndex], missingPreviousSelection: false };
    }
    const fallbackLeader = leaders[0];
    selectedLeaderIndex = 0;
    selectedLeaderKey = leaderKey(fallbackLeader);
    return { leader: fallbackLeader, missingPreviousSelection: true };
  }

  if (selectedLeaderIndex >= leaders.length) {
    selectedLeaderIndex = 0;
  }

  const leader = leaders[selectedLeaderIndex];
  selectedLeaderKey = leaderKey(leader);
  return { leader, missingPreviousSelection: false };
}

function setSelectedLeader(index, leaders) {
  selectedLeaderIndex = index;
  selectedLeaderKey = leaderKey(leaders[index]);
  renderTradierSlice();
}

function getSelectedLeader() {
  return syncSelectedLeader(currentSnapshot?.tradier?.leaders || []).leader;
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
  const kindMap = {
    neutral: 'badge',
    queued: 'badge accent',
    watch: 'badge info',
    recent: 'badge warn',
    good: 'badge good',
    bad: 'badge bad'
  };
  const badgeClass = kindMap[kind] || 'badge';
  return `<span class="${badgeClass}">${escapeHtml(label)}</span>`;
}

function stateBanner(text, tone = 'neutral') {
  return `<div class="state-banner ${tone}">${escapeHtml(text)}</div>`;
}

function summaryField(label, value, kind = '') {
  return `
    <div class="summary-field ${kind}">
      <div class="label">${escapeHtml(label)}</div>
      <div class="value">${escapeHtml(value)}</div>
    </div>
  `;
}

function renderSummaryStrip(leader, stateMeta = null) {
  const wrap = document.getElementById('summaryStripWrap');
  if (!leader) {
    wrap.className = 'summary-strip-wrap placeholder';
    if (stateMeta?.kind === 'loading') {
      wrap.innerHTML = stateBanner('Loading selected-item operator summary…', 'loading');
      return;
    }
    if (stateMeta?.kind === 'error') {
      wrap.innerHTML = stateBanner(stateMeta.message || 'Unable to load selected-item summary.', 'bad');
      return;
    }
    if (stateMeta?.kind === 'empty') {
      wrap.innerHTML = stateBanner('No operator summary is available because no Tradier leaders are present.', 'warn');
      return;
    }
    wrap.textContent = 'Select a Tradier leader to view operator summary.';
    return;
  }

  const state = getLeaderState(leader);
  const feedback = getSelectedLeaderFeedback(leader);
  const latestAction = feedback?.action || 'No local action yet';
  const latestStateChange = feedback?.stateChange || 'No recent selected-item state change recorded.';
  const localTrigger = state.queueItem?.trigger || leader.entry || '—';
  const localInvalidation = state.watchItem?.invalidation || leader.invalidation || '—';

  wrap.className = 'summary-strip-wrap';
  wrap.innerHTML = `
    ${stateMeta?.kind === 'selection-reset' ? stateBanner('Operator summary was re-anchored to the current selected leader after refresh.', 'warn') : ''}
    <div class="summary-strip-head">
      <div>
        <div class="summary-title">${escapeHtml(leaderDisplayName(leader))}</div>
        <div class="muted small">${escapeHtml(formatSection(leader.section))} · ${escapeHtml(leaderKey(leader))}</div>
      </div>
      <div class="badge-stack">
        ${state.queued ? statusBadge('Queued: yes', 'queued') : statusBadge('Queued: no', 'neutral')}
        ${state.watched ? statusBadge('Watched: yes', 'watch') : statusBadge('Watched: no', 'neutral')}
        ${feedback ? statusBadge('Recent feedback', 'recent') : ''}
      </div>
    </div>
    <div class="summary-strip-grid">
      ${summaryField('Selected Leader', leaderDisplayName(leader), 'wide')}
      ${summaryField('Queued', state.queued ? 'Yes' : 'No')}
      ${summaryField('Watched', state.watched ? 'Yes' : 'No')}
      ${summaryField('Latest Local Action', latestAction)}
      ${summaryField('Local Trigger', localTrigger, 'wide')}
      ${summaryField('Local Invalidation', localInvalidation, 'wide')}
      ${summaryField('Latest State Change', latestStateChange, 'wide strong')}
    </div>
  `;
}

function renderOverview(snapshot) {
  const health = snapshot.systemHealth || {};
  const tradier = snapshot.tradier || {};
  const overview = tradier.overview || {};
  const healthSummary = describeSnapshotHealth(snapshot);
  
  const items = [
    { label: 'Board', value: health.tradierBoardPresent ? '✓ Live' : '✗ Missing', class: health.tradierBoardPresent ? 'positive' : 'negative' },
    { label: 'Leaders', value: overview.leaderCount ?? tradier.leaders?.length ?? 0, class: 'accent' },
    { label: 'Directional', value: overview.directionalCount ?? 0, class: '' },
    { label: 'Premium', value: overview.premiumCount ?? 0, class: '' },
    { label: 'VIX', value: overview.vix ?? '—', class: '' },
    { label: 'Updated', value: health.tradierBoardUpdatedAt ? new Date(health.tradierBoardUpdatedAt).toLocaleTimeString() : '—', class: 'text-muted' },
  ];

  const grid = document.getElementById('overviewGrid');
  if (!grid) return;
  
  grid.innerHTML = items.map(item => `
    <div class="metric-item">
      <div class="metric-label">${escapeHtml(item.label)}</div>
      <div class="metric-value ${item.class}">${escapeHtml(String(item.value))}</div>
    </div>
  `).join('');
  
  // Update timestamp
  const updatedAt = document.getElementById('updatedAt');
  if (updatedAt) {
    updatedAt.textContent = new Date().toLocaleTimeString();
  }
  
  // Update scan status
  renderScanStatus(snapshot);
}

let refreshStatusData = null;

function renderScanStatus(snapshot) {
  const health = snapshot?.systemHealth || {};
  const scanStatusEl = document.getElementById('scanStatus');
  const lastScanEl = document.getElementById('lastScanTime');
  const freshnessEl = document.getElementById('dataFreshness');
  const apiStatusEl = document.getElementById('apiStatus');
  const refreshResultEl = document.getElementById('refreshResult');
  const refreshStageEl = document.getElementById('refreshStage');
  const refreshMessageEl = document.getElementById('refreshMessage');
  
  if (!scanStatusEl || !lastScanEl || !freshnessEl || !apiStatusEl) return;
  
  const boardUpdated = health.tradierBoardUpdatedAt;
  const apiKeyLoaded = health.tradierApiKeyLoaded;
  
  // Calculate freshness
  let freshness = 'Unknown';
  let freshnessClass = '';
  if (boardUpdated) {
    const minutesAgo = (Date.now() - new Date(boardUpdated).getTime()) / 60000;
    if (minutesAgo < 30) {
      freshness = 'Fresh';
      freshnessClass = 'fresh';
    } else if (minutesAgo < 120) {
      freshness = `${Math.round(minutesAgo)}m old`;
      freshnessClass = 'stale';
    } else {
      freshness = `${Math.round(minutesAgo / 60)}h old`;
      freshnessClass = 'stale';
    }
  }
  
  // Update elements
  scanStatusEl.textContent = apiKeyLoaded ? (boardUpdated ? 'Active' : 'No Data') : 'API Error';
  scanStatusEl.className = `panel-status ${apiKeyLoaded ? (boardUpdated ? 'fresh' : 'stale') : 'error'}`;
  
  lastScanEl.textContent = boardUpdated ? new Date(boardUpdated).toLocaleTimeString() : 'Never';
  freshnessEl.textContent = freshness;
  freshnessEl.className = `status-value ${freshnessClass}`;
  apiStatusEl.textContent = apiKeyLoaded ? 'Connected' : 'Disconnected';
  apiStatusEl.className = `status-value ${apiKeyLoaded ? 'fresh' : 'error'}`;

  if (refreshResultEl && refreshStageEl && refreshMessageEl) {
    refreshResultEl.textContent = refreshStatusData ? (refreshStatusData.ok ? 'Success' : 'Failure') : '--';
    refreshResultEl.className = `status-value ${refreshStatusData ? (refreshStatusData.ok ? 'fresh' : 'error') : ''}`;
    refreshStageEl.textContent = refreshStatusData?.stage || '--';
    refreshMessageEl.textContent = refreshStatusData?.message || '--';
    refreshMessageEl.title = refreshStatusData?.message || '';
  }
}

async function fetchRefreshStatus() {
  try {
    const res = await fetch('/api/refresh-status');
    if (!res.ok) return null;
    const data = await res.json();
    if (data.ok) {
      refreshStatusData = data.data;
      return data.data;
    }
  } catch (err) {
    console.error('Failed to fetch refresh status:', err);
  }
  return null;
}

function renderNoTradeState() {
  const health = currentSnapshot?.systemHealth || {};
  const boardUpdated = health.tradierBoardUpdatedAt;
  const apiKeyLoaded = health.tradierApiKeyLoaded;
  
  let freshnessText = 'Unknown';
  let freshnessIcon = '⏱️';
  if (boardUpdated) {
    const minutesAgo = (Date.now() - new Date(boardUpdated).getTime()) / 60000;
    if (minutesAgo < 30) {
      freshnessText = 'Data is fresh';
      freshnessIcon = '✓';
    } else {
      freshnessText = `Last scan: ${Math.round(minutesAgo)} minutes ago`;
      freshnessIcon = '⏱️';
    }
  }
  
  const reasons = [
    'Confidence threshold not met (minimum 6/10 required)',
    'Bid-ask spreads too wide for clean entry',
    'Volume/OI below liquidity thresholds',
    'Delta profile outside optimal range (0.10-0.80)',
    'Risk/reward ratio not acceptable',
    'VIX regime suggesting caution'
  ];
  
  const refreshResult = refreshStatusData ? (refreshStatusData.ok ? 'Success' : 'Failure') : '--';
  const refreshStage = refreshStatusData?.stage || '--';
  const refreshMessage = refreshStatusData?.message || '--';

  return `
    <div class="no-trade-state">
      <div class="no-trade-icon">🛡️</div>
      <div class="no-trade-title">No Trade Signal</div>
      <div class="no-trade-subtitle">The system is actively screening. No candidates passed filters.</div>
      
      <div class="status-grid telemetry-grid" style="margin: var(--space-md) 0;">
        <div class="status-item">
          <span class="status-label">System Status</span>
          <span class="status-value ${apiKeyLoaded ? 'fresh' : 'error'}">${apiKeyLoaded ? 'Active' : 'Error'}</span>
        </div>
        <div class="status-item">
          <span class="status-label">Data Freshness</span>
          <span class="status-value ${boardUpdated ? 'fresh' : 'error'}">${freshnessText}</span>
        </div>
        <div class="status-item">
          <span class="status-label">Screening</span>
          <span class="status-value">Strict Filters</span>
        </div>
        <div class="status-item">
          <span class="status-label">Last Refresh Result</span>
          <span class="status-value ${refreshStatusData ? (refreshStatusData.ok ? 'fresh' : 'error') : ''}">${refreshResult}</span>
        </div>
        <div class="status-item">
          <span class="status-label">Refresh Stage</span>
          <span class="status-value">${escapeHtml(refreshStage)}</span>
        </div>
        <div class="status-item">
          <span class="status-label">Refresh Message</span>
          <span class="status-value" title="${escapeHtml(refreshMessage)}">${escapeHtml(refreshMessage)}</span>
        </div>
      </div>
      
      <div class="no-trade-reasons">
        <div style="font-size: 10px; text-transform: uppercase; letter-spacing: 0.1em; color: var(--text-tertiary); margin-bottom: var(--space-sm);">Common Rejection Reasons</div>
        <ul style="list-style: none; padding: 0; margin: 0;">
          ${reasons.map(r => `<li>• ${r}</li>`).join('')}
        </ul>
      </div>
      
      <div class="status-actions" style="justify-content: center; margin-top: var(--space-md);">
        <button class="btn-action" onclick="forceRefresh()">↻ Force Refresh</button>
        <button class="btn-action" onclick="showFilterCriteria()">⚙ View Filters</button>
      </div>
    </div>
  `;
}

function forceRefresh() {
  const btn = document.querySelector('button[onclick="forceRefresh()"]');
  if (btn) {
    btn.textContent = '⟳ Refreshing...';
    btn.disabled = true;
  }
  refresh().then(() => {
    if (btn) {
      btn.textContent = '↻ Force Refresh';
      btn.disabled = false;
    }
  }).catch(() => {
    if (btn) {
      btn.textContent = '✗ Failed';
      btn.disabled = false;
      setTimeout(() => { btn.textContent = '↻ Force Refresh'; }, 2000);
    }
  });
}

function showFilterCriteria() {
  alert(`Bazaar Filter Criteria:

DIRECTIONAL/SCALPING:
• Delta: 0.35 - 0.80
• DTE: 7-14 days
• Bid-ask spread: < 10%
• Volume: > 1000 contracts
• Confidence: ≥ 6/10

PREMIUM/CREDIT:
• Delta: 0.10 - 0.18
• DTE: 7-14 days
• OTM only
• Spread width: acceptable risk
• Confidence: ≥ 6/10

Standing down when no setups meet criteria is valid discipline.`);
}

// Global for live scanner data
let liveScannerData = null;

// Quick execute from scanner row
async function quickExecuteFromScanner(index) {
  const leader = currentSnapshot?.tradier?.leaders?.[index];
  if (!leader) {
    alert('Leader not found');
    return;
  }
  
  if (!confirm(`Quick execute: ${leaderDisplayName(leader)}?\n\nThis will create a preview for immediate execution.`)) {
    return;
  }
  
  // Set as selected leader
  setSelectedLeader(index, currentSnapshot.tradier.leaders);
  
  // Trigger execute preview
  await runExecutePreview(leader);
}

// Quick queue from scanner row
async function quickQueueFromScanner(index) {
  const leader = currentSnapshot?.tradier?.leaders?.[index];
  if (!leader) {
    alert('Leader not found');
    return;
  }
  
  try {
    const res = await fetch('/api/actions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'queue_selected_leader', leader }),
    });
    
    const data = await res.json();
    if (data.ok) {
      alert(`Added to queue: ${leaderDisplayName(leader)}`);
      await refresh();
    } else {
      alert(`Failed: ${data.error}`);
    }
  } catch (err) {
    alert(`Error: ${err.message}`);
  }
}

async function fetchLiveScanner() {
  try {
    const res = await fetch('/api/live-scanner');
    if (res.ok) {
      const data = await res.json();
      if (data.ok) {
        liveScannerData = data.data;
        return data.data;
      }
    }
  } catch (err) {
    console.error('Failed to fetch live scanner:', err);
  }
  return null;
}

function getLeaderLiveData(leader) {
  // Get live data for a leader if available
  if (!liveScannerData?.leaders) return null;
  
  // Match by symbol, strike, and expiration
  const leaderKey = `${leader.symbol}-${leader.strike}-${leader.exp}`;
  for (const live of liveScannerData.leaders) {
    const liveKey = `${live.symbol}-${live.strike}-${live.expiration}`;
    if (leaderKey === liveKey) {
      return live;
    }
  }
  return null;
}

function renderLeaders(leaders) {
  const wrap = document.getElementById('leadersWrap');
  if (!wrap) return;
  
  if (currentUiMode === 'loading') {
    wrap.innerHTML = '<div class="void">Loading Tradier snapshot...</div>';
    return;
  }
  if (currentUiMode === 'error') {
    wrap.innerHTML = `<div class="void">Error: ${escapeHtml(currentLoadError || 'Snapshot load failed')}</div>`;
    return;
  }
  if (!leaders?.length) {
    wrap.innerHTML = renderNoTradeState();
    return;
  }

  const { leader: selectedLeader, missingPreviousSelection } = syncSelectedLeader(leaders);

  const selectionBanner = missingPreviousSelection ? '<div class="banner warn">Previous selection no longer available. Anchored to current leader.</div>' : '';

  wrap.innerHTML = selectionBanner + leaders.map((leader, index) => {
    const state = getLeaderState(leader);
    const feedback = getSelectedLeaderFeedback(leader);
    
    // Get live data for this leader
    const liveData = getLeaderLiveData(leader);
    const opportunity = liveData?.opportunity;
    const quote = liveData?.quote;
    
    // Build badges
    const stateBadges = [
      leader.fallback ? '<span class="badge warn">Fallback</span>' : `<span class="badge">${escapeHtml(leader.label || 'Primary')}</span>`,
      state.queued ? statusBadge('Queued', 'queued') : '',
      state.watched ? statusBadge('Watching', 'watch') : '',
      feedback ? statusBadge('Recent', 'recent') : '',
    ].filter(Boolean).join('');
    
    // Opportunity badge
    let opportunityBadge = '';
    if (opportunity) {
      const tempColors = {
        'hot': 'badge bad',
        'warm': 'badge warn', 
        'cool': 'badge info',
        'cold': 'badge'
      };
      const tempClass = tempColors[opportunity.temperature] || 'badge';
      opportunityBadge = `<span class="${tempClass}">${opportunity.temperature.toUpperCase()}</span>`;
    }
    
    // Live price indicator
    let livePriceInfo = '';
    if (quote?.last && typeof quote.last === 'number') {
      const change = quote.change || 0;
      const changePercent = quote.change_percent || 0;
      const changeClass = change >= 0 ? 'text-positive' : 'text-negative';
      const changeSign = change >= 0 ? '+' : '';
      livePriceInfo = `<span class="${changeClass}">$${quote.last.toFixed(2)} (${changeSign}${changePercent.toFixed(1)}%)</span>`;
    }
    
    // IV badge
    let ivBadge = '';
    if (quote?.iv && typeof quote.iv === 'number') {
      ivBadge = `<span class="badge info">IV ${quote.iv.toFixed(1)}%</span>`;
    }

    return `
      <button class="leader-row ${leaderKey(leader) === leaderKey(selectedLeader) ? 'selected' : ''} ${opportunity?.temperature === 'hot' ? 'leader-hot' : ''}" data-index="${index}">
        <div class="leader-row-top">
          <div>
            <div class="section">${escapeHtml(formatSection(leader.section))} ${opportunityBadge}</div>
            <div class="headline">${escapeHtml(leaderDisplayName(leader))} ${livePriceInfo}</div>
          </div>
          <div class="badge-stack">${stateBadges} ${ivBadge}</div>
        </div>
        <div class="leader-row-grid">
          <div><span class="label">Underlying</span><span class="value">${escapeHtml(leader.underlying)}</span></div>
          <div><span class="label">Delta</span><span class="value">${escapeHtml(leader.delta)} ${quote?.delta && typeof quote.delta === 'number' ? `<span class="live-metric">(${quote.delta.toFixed(2)})</span>` : ''}</span></div>
          <div><span class="label">Bid / Ask</span><span class="value">${escapeHtml(leader.bid)} / ${escapeHtml(leader.ask)} ${quote?.bid && typeof quote.bid === 'number' ? `<span class="live-metric">[$${quote.bid.toFixed(2)}/${quote?.ask && typeof quote.ask === 'number' ? '$' + quote.ask.toFixed(2) : '--'}]</span>` : ''}</span></div>
          <div><span class="label">Confidence</span><span class="value">${escapeHtml(leader.confidence)}</span></div>
        </div>
        ${opportunity?.factors?.length ? `
          <div class="opportunity-factors">
            ${opportunity.factors.map(f => `<span class="factor-badge">${escapeHtml(f)}</span>`).join('')}
          </div>
        ` : ''}
        <div class="leader-actions">
          <button class="quick-execute-btn" onclick="event.stopPropagation(); quickExecuteFromScanner(${index})">
            ⚡ Quick Execute
          </button>
          <button class="queue-btn" onclick="event.stopPropagation(); quickQueueFromScanner(${index})">
            + Queue
          </button>
        </div>
      </button>
    `;
  }).join('');

  wrap.querySelectorAll('.leader-row').forEach(button => {
    button.addEventListener('click', () => {
      setSelectedLeader(Number(button.dataset.index), leaders);
    });
  });

  const selectionMeta = missingPreviousSelection ? { kind: 'selection-reset' } : null;
  renderSummaryStrip(selectedLeader, selectionMeta);
  renderDetail(selectedLeader, selectionMeta);
  renderActions(selectedLeader, selectionMeta);
}

function detailField(label, value, wide = false) {
  return `
    <div class="detail-field ${wide ? 'wide' : ''}">
      <div class="label">${escapeHtml(label)}</div>
      <div class="value">${escapeHtml(value)}</div>
    </div>
  `;
}

function renderQualificationCard(leader) {
  // Parse confidence score (e.g., "7/10" -> 7)
  const confidenceMatch = leader.confidence?.match(/(\d+)\/10/);
  const confidenceScore = confidenceMatch ? parseInt(confidenceMatch[1]) : 5;
  const confidencePercent = confidenceScore * 10;
  
  // Determine confidence color
  let confidenceColor = 'warn';
  if (confidenceScore >= 8) confidenceColor = 'good';
  else if (confidenceScore >= 6) confidenceColor = 'accent';
  else if (confidenceScore < 5) confidenceColor = 'bad';
  
  // Build qualification reasons
  const reasons = [];
  
  // Section-based qualification
  if (leader.section === 'directional') {
    reasons.push('Near-ATM delta (0.35-0.80) for directional exposure');
    reasons.push('7-14 DTE for optimal gamma/theta balance');
    reasons.push('Tight bid-ask spread for clean entry/exit');
  } else {
    reasons.push('OTM delta (~0.14) for defined-risk premium');
    reasons.push('Spread structure limits max loss');
    reasons.push('Time decay working in your favor');
  }
  
  // Add liquidity reason if available
  if (leader.bid && leader.ask) {
    const bid = parseFloat(leader.bid);
    const ask = parseFloat(leader.ask);
    if (bid > 0 && ask > 0) {
      const spreadPct = ((ask - bid) / ((ask + bid) / 2)) * 100;
      if (spreadPct < 5) reasons.push('Tight bid-ask spread (' + spreadPct.toFixed(1) + '%)');
    }
  }
  
  // Add fallback note if applicable
  if (leader.fallback) {
    reasons.push('⚠ Fallback expiry - confidence adjusted');
  }
  
  // Risk factors
  const risks = [];
  risks.push('Momentum confirmation required - do not blind enter');
  risks.push('Hard stop discipline essential');
  if (leader.section === 'directional') {
    risks.push('Directional risk - wrong way move = loss');
  } else {
    risks.push('Assignment risk if ITM at expiry');
  }
  if (leader.fallback) {
    risks.push('Non-optimal DTE may affect Greeks');
  }
  
  return `
    <div class="qualification-card">
      <div class="qualification-header">
        <div class="qualification-title">Trade Qualification</div>
        <div class="confidence-badge ${confidenceColor}">${confidenceScore}/10</div>
      </div>
      
      <div class="confidence-bar">
        <div class="confidence-fill ${confidenceColor}" style="width: ${confidencePercent}%"></div>
      </div>
      
      <div class="qualification-section">
        <div class="section-title">✓ Why This Passed Filters</div>
        <ul class="qualification-list">
          ${reasons.map(r => `<li>${escapeHtml(r)}</li>`).join('')}
        </ul>
      </div>
      
      <div class="qualification-section">
        <div class="section-title">⚠ Key Risk Factors</div>
        <ul class="risk-list">
          ${risks.map(r => `<li>${escapeHtml(r)}</li>`).join('')}
        </ul>
      </div>
      
      <div class="setup-thesis">
        <div class="section-title">Setup Thesis</div>
        <div class="thesis-text">${escapeHtml(leader.thesis || 'Best candidate in current delta/liquidity band')}</div>
      </div>
    </div>
  `;
}

function renderDetail(leader, stateMeta = null) {
  const wrap = document.getElementById('detailWrap');
  const meta = document.getElementById('selectedMeta');
  if (!leader) {
    meta.textContent = 'No leader selected';
    wrap.className = 'detail-wrap placeholder';
    if (stateMeta?.kind === 'loading') {
      wrap.innerHTML = stateBanner('Loading selected Tradier item…', 'loading');
      return;
    }
    if (stateMeta?.kind === 'error') {
      wrap.innerHTML = stateBanner(stateMeta.message || 'Unable to load selected item detail.', 'bad');
      return;
    }
    if (stateMeta?.kind === 'empty') {
      wrap.innerHTML = stateBanner('No selected-item detail is available because no Tradier leaders were parsed.', 'warn');
      return;
    }
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
  const staleNote = describeSnapshotHealth(currentSnapshot);

  meta.textContent = `${formatSection(leader.section)} · ${leader.symbol || '—'} · ${leader.exp || '—'}`;
  wrap.className = 'detail-wrap';
  
  // Build qualification card
  const qualificationCard = renderQualificationCard(leader);
  
  wrap.innerHTML = `
    ${stateMeta?.kind === 'selection-reset' ? stateBanner('Selected detail was re-anchored because the previous leader disappeared after refresh.', 'warn') : ''}
    ${staleNote.tone !== 'good' ? stateBanner(staleNote.text, staleNote.tone) : ''}
    ${qualificationCard}
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
      ${detailField('Selected Key', leaderKey(leader), true)}
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

// Global state for execution preview
let executionPreview = null;

function inferActions(leader) {
  if (!leader) return [];

  const state = getLeaderState(leader);

  return [
    {
      key: 'execute_preview',
      title: 'Execute Now',
      detail: 'Preview and execute this trade immediately via Tradier.',
      disabled: false,
      cta: 'Execute Now',
      stateLabel: 'Live execution',
      stateKind: 'execute',
      primary: true,
    },
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

  // Handle execution preview specially
  if (actionKey === 'execute_preview') {
    return runExecutePreview(leader);
  }
  
  // Handle execution confirmation
  if (actionKey === 'execute_confirm') {
    return runExecuteConfirm();
  }

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

  lastActionStatus = {
    leaderKey: leaderKey(leader),
    message: data.feedback?.stateChange || `${data.action} saved at ${data.updatedAt}`,
    updatedAt: data.updatedAt,
  };

  status.textContent = lastActionStatus.message;
  status.className = 'action-status good small';
  await refresh();
}

async function runExecutePreview(leader) {
  const status = document.getElementById('actionStatus');
  if (!status) return;

  status.textContent = 'Creating order preview via Tradier…';
  status.className = 'action-status loading small';

  try {
    const res = await fetch('/api/actions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'execute_preview', leader }),
    });
    const data = await res.json();

    if (!res.ok || !data.ok) {
      status.textContent = `Preview failed: ${data.error || 'unknown error'}`;
      status.className = 'action-status bad small';
      executionPreview = null;
      return;
    }

    executionPreview = data;
    
    // Show preview in actions panel
    renderExecutionPreview(data);
    
    status.textContent = 'Preview ready - review and confirm below';
    status.className = 'action-status good small';
    
  } catch (err) {
    status.textContent = `Preview error: ${err.message}`;
    status.className = 'action-status bad small';
    executionPreview = null;
  }
}

function renderExecutionPreview(data) {
  const wrap = document.getElementById('actionsWrap');
  const preview = data.preview || {};
  const broker = data.broker_response || {};
  const risk = data.risk_decision || {};
  
  const previewHtml = `
    <div class="execution-preview-box">
      <div class="preview-title">⚠️ Order Preview - Review Before Confirming</div>
      <div class="preview-details">
        <div><strong>Intent ID:</strong> ${escapeHtml(data.intent_id || 'N/A')}</div>
        <div><strong>Risk Check:</strong> ${risk.allowed ? '✅ Allowed' : '❌ Blocked'}</div>
        ${risk.reasons?.length ? `<div><strong>Risk Notes:</strong> ${escapeHtml(risk.reasons.join(', '))}</div>` : ''}
        <hr/>
        <div><strong>Estimated Cost:</strong> $${escapeHtml(String(preview.estimated_cost || 'N/A'))}</div>
        <div><strong>Fees:</strong> $${escapeHtml(String(preview.fees || 'N/A'))}</div>
        <div><strong>Buying Power Effect:</strong> $${escapeHtml(String(preview.buying_power_effect || 'N/A'))}</div>
        ${preview.warnings?.length ? `<div class="preview-warnings">⚠️ ${escapeHtml(preview.warnings.join(', '))}</div>` : ''}
        ${broker.order?.status ? `<div><strong>Broker Status:</strong> ${escapeHtml(broker.order.status)}</div>` : ''}
      </div>
      <div class="preview-actions">
        <button class="action-btn execute-confirm" data-action-key="execute_confirm">✅ Confirm & Execute</button>
        <button class="action-btn execute-cancel" onclick="cancelExecutionPreview()">❌ Cancel</button>
      </div>
    </div>
  `;
  
  // Insert preview after action list
  const actionList = wrap.querySelector('.action-list');
  if (actionList) {
    // Remove any existing preview
    const existing = wrap.querySelector('.execution-preview-box');
    if (existing) existing.remove();
    
    actionList.insertAdjacentHTML('afterend', previewHtml);
    bindActionButtons();
  }
}

function cancelExecutionPreview() {
  executionPreview = null;
  const preview = document.querySelector('.execution-preview-box');
  if (preview) preview.remove();
  
  const status = document.getElementById('actionStatus');
  if (status) {
    status.textContent = 'Execution cancelled';
    status.className = 'action-status muted small';
  }
  
  // Re-render to clear preview
  renderActions(getSelectedLeader());
}

async function runExecuteConfirm() {
  const status = document.getElementById('actionStatus');
  if (!status || !executionPreview) return;
  
  const intentId = executionPreview.intent_id;
  if (!intentId) {
    status.textContent = 'Error: No intent ID for confirmation';
    status.className = 'action-status bad small';
    return;
  }

  status.textContent = 'Placing order via Tradier…';
  status.className = 'action-status loading small';

  try {
    const res = await fetch('/api/actions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'execute_confirm', intent_id: intentId }),
    });
    const data = await res.json();

    if (!res.ok || !data.ok) {
      status.textContent = `Execution failed: ${data.error || 'unknown error'}`;
      status.className = 'action-status bad small';
      return;
    }

    executionPreview = null;
    
    lastActionStatus = {
      leaderKey: leaderKey(getSelectedLeader()),
      message: `Order placed: ${data.order?.broker_order_id || 'N/A'}`,
      updatedAt: new Date().toISOString(),
    };

    status.textContent = `✅ Order executed: ${data.order?.broker_order_id || 'N/A'}`;
    status.className = 'action-status good small';
    
    // Clear preview and refresh
    await refresh();
    
  } catch (err) {
    status.textContent = `Execution error: ${err.message}`;
    status.className = 'action-status bad small';
  }
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

function renderActions(leader, stateMeta = null) {
  const wrap = document.getElementById('actionsWrap');
  if (!leader) {
    wrap.className = 'actions-wrap placeholder';
    if (stateMeta?.kind === 'loading') {
      wrap.innerHTML = stateBanner('Loading selected-item action state…', 'loading');
      return;
    }
    if (stateMeta?.kind === 'error') {
      wrap.innerHTML = stateBanner(stateMeta.message || 'Unable to load selected-item actions.', 'bad');
      return;
    }
    if (stateMeta?.kind === 'empty') {
      wrap.innerHTML = stateBanner('No selected-item actions are available because no Tradier leaders are present.', 'warn');
      return;
    }
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

  const coherentStatus = lastActionStatus && lastActionStatus.leaderKey === leaderKey(leader)
    ? `${lastActionStatus.message} · coherent after refresh`
    : 'Selected-item actions write only to current local dashboard state files.';

  wrap.className = 'actions-wrap';
  wrap.innerHTML = `
    ${stateMeta?.kind === 'selection-reset' ? stateBanner('Actions were re-anchored to a new selected leader after refresh.', 'warn') : ''}
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
    <div id="actionStatus" class="action-status ${(lastActionStatus && lastActionStatus.leaderKey === leaderKey(leader)) ? 'good' : 'muted'} small">${escapeHtml(coherentStatus)}</div>
  `;
  bindActionButtons();
}

// Global variable for live position data
let livePositionData = null;
let exitPredictorData = null;
let alertConfig = {
  soundEnabled: true,
  browserNotifications: true,
  alertedPositions: new Set() // Track which positions we've already alerted on
};

// Request browser notification permission
function requestNotificationPermission() {
  if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission();
  }
}

// Play alert sound
function playAlertSound() {
  if (!alertConfig.soundEnabled) return;
  
  // Create oscillator for beep sound
  try {
    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();
    
    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);
    
    oscillator.frequency.value = 800;
    oscillator.type = 'sine';
    
    gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
    gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.5);
    
    oscillator.start(audioContext.currentTime);
    oscillator.stop(audioContext.currentTime + 0.5);
  } catch (e) {
    console.error('Failed to play alert sound:', e);
  }
}

// Send browser notification
function sendBrowserNotification(title, body) {
  if (!alertConfig.browserNotifications) return;
  if (!('Notification' in window)) return;
  if (Notification.permission !== 'granted') return;
  
  try {
    new Notification(title, {
      body: body,
      icon: '🚨',
      tag: 'exit-alert',
      requireInteraction: true
    });
  } catch (e) {
    console.error('Failed to send notification:', e);
  }
}

// Check for new EXIT signals and alert
function checkExitAlerts(positions) {
  if (!exitPredictorData?.results) return;
  
  exitPredictorData.results.forEach(result => {
    const pos = result.position;
    const analysis = result.analysis;
    const positionKey = `${pos.symbol}_${pos.contract}`;
    
    // Only alert on EXIT signals we haven't alerted on yet
    if (analysis.signal === 'EXIT' && !alertConfig.alertedPositions.has(positionKey)) {
      alertConfig.alertedPositions.add(positionKey);
      
      // Play sound
      playAlertSound();
      
      // Send browser notification
      const reason = analysis.reasons?.[0] || 'Exit signal triggered';
      sendBrowserNotification(
        '🚨 EXIT ALERT: ' + pos.symbol,
        `${pos.contract} - Score: ${analysis.score}/100 - ${reason}`
      );
      
      // Add to alert log
      addAlertToLog({
        timestamp: new Date().toISOString(),
        symbol: pos.symbol,
        contract: pos.contract,
        score: analysis.score,
        reason: reason,
        type: 'EXIT'
      });
    }
  });
}

// Alert log
let alertLog = [];

function addAlertToLog(alert) {
  alertLog.unshift(alert);
  // Keep only last 20 alerts
  alertLog = alertLog.slice(0, 20);
  renderAlertLog();
}

function renderAlertLog() {
  const logContainer = document.getElementById('alertLog');
  if (!logContainer) return;
  
  if (alertLog.length === 0) {
    logContainer.innerHTML = '<div class="void">No alerts</div>';
    return;
  }
  
  logContainer.innerHTML = alertLog.map(alert => `
    <div class="alert-item">
      <span class="alert-time">${new Date(alert.timestamp).toLocaleTimeString()}</span>
      <span class="alert-message">${escapeHtml(alert.symbol)} ${escapeHtml(alert.contract)}</span>
      <span class="badge ${alert.type === 'EXIT' ? 'bad' : alert.type === 'WATCH' ? 'warn' : 'info'}">${alert.type}</span>
    </div>
  `).join('');
}

// Toggle sound
function toggleAlertSound() {
  alertConfig.soundEnabled = !alertConfig.soundEnabled;
  localStorage.setItem('alertSoundEnabled', alertConfig.soundEnabled);
  updateAlertControls();
}

// Toggle browser notifications
function toggleBrowserNotifications() {
  alertConfig.browserNotifications = !alertConfig.browserNotifications;
  localStorage.setItem('browserNotificationsEnabled', alertConfig.browserNotifications);
  
  if (alertConfig.browserNotifications && 'Notification' in window && Notification.permission === 'default') {
    requestNotificationPermission();
  }
  
  updateAlertControls();
}

// Update alert control UI
function updateAlertControls() {
  const soundBtn = document.getElementById('toggleSound');
  const notifBtn = document.getElementById('toggleNotifications');
  
  if (soundBtn) {
    soundBtn.textContent = alertConfig.soundEnabled ? '🔊 Sound On' : '🔇 Sound Off';
    soundBtn.className = alertConfig.soundEnabled ? 'alert-control active' : 'alert-control';
  }
  
  if (notifBtn) {
    notifBtn.textContent = alertConfig.browserNotifications ? '🔔 Notifications On' : '🔕 Notifications Off';
    notifBtn.className = alertConfig.browserNotifications ? 'alert-control active' : 'alert-control';
  }
}

// Load alert config from localStorage
function loadAlertConfig() {
  const soundEnabled = localStorage.getItem('alertSoundEnabled');
  const notifEnabled = localStorage.getItem('browserNotificationsEnabled');
  
  if (soundEnabled !== null) {
    alertConfig.soundEnabled = soundEnabled === 'true';
  }
  if (notifEnabled !== null) {
    alertConfig.browserNotifications = notifEnabled === 'true';
  }
  
  // Request notification permission on load
  requestNotificationPermission();
}

// Fetch exit predictor analysis
async function fetchExitPredictor() {
  try {
    const res = await fetch('/api/exit-predictor');
    if (res.ok) {
      const data = await res.json();
      if (data.ok) {
        exitPredictorData = data.data;
        return data.data;
      }
    }
  } catch (err) {
    console.error('Failed to fetch exit predictor:', err);
  }
  return null;
}

// Get exit analysis for a position
function getPositionExitAnalysis(symbol, instrument) {
  if (!exitPredictorData?.results) return null;
  
  for (const result of exitPredictorData.results) {
    const pos = result.position;
    const posInstrument = pos.contract?.split(' ', 1)[1] || pos.contract;
    if (pos.symbol === symbol && posInstrument === instrument) {
      return result.analysis;
    }
  }
  return null;
}

async function fetchLivePositions() {
  try {
    const res = await fetch('/api/live-positions');
    if (res.ok) {
      const data = await res.json();
      if (data.ok) {
        livePositionData = data.data;
        return data.data;
      }
    }
  } catch (err) {
    console.error('Failed to fetch live positions:', err);
  }
  return null;
}

function calculatePnL(entry, current, size) {
  const entryVal = parseFloat(entry) || 0;
  const currentVal = parseFloat(current) || 0;
  const qty = parseInt(size) || 0;
  const pnl = (currentVal - entryVal) * qty * 100; // Options are 100 shares
  const pnlPct = entryVal > 0 ? ((currentVal - entryVal) / entryVal) * 100 : 0;
  return { pnl, pnlPct };
}

function formatPnL(pnl, pnlPct) {
  const safePnl = typeof pnl === 'number' ? pnl : 0;
  const safePnlPct = typeof pnlPct === 'number' ? pnlPct : 0;
  const sign = safePnl >= 0 ? '+' : '';
  const colorClass = safePnl >= 0 ? 'good' : 'bad';
  return `<span class="${colorClass}">${sign}$${safePnl.toFixed(2)} (${sign}${safePnlPct.toFixed(1)}%)</span>`;
}

async function closePosition(symbol, instrument, size) {
  if (!confirm(`Close position: ${symbol} ${instrument}?\n\nThis will place a market order to sell ${size} contract(s).`)) {
    return;
  }
  
  // Parse instrument to get option details
  // Format: "395 PUT 2026-03-31" or "400 CALL 2026-04-17"
  const parts = instrument.split(' ');
  if (parts.length < 3) {
    alert('Could not parse position details');
    return;
  }
  
  const strike = parts[0];
  const optionType = parts[1].toLowerCase();
  const expiration = parts[2];
  
  try {
    const res = await fetch('/api/close-position', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        symbol,
        quantity: parseInt(size),
        option_type: optionType,
        strike: parseFloat(strike),
        expiration
      })
    });
    
    const data = await res.json();
    if (data.ok) {
      alert(`Position close order placed!\nOrder ID: ${data.order?.order?.id || 'N/A'}`);
      await refresh();
    } else {
      alert(`Failed to close position: ${data.error}`);
    }
  } catch (err) {
    alert(`Error: ${err.message}`);
  }
}

function renderPositions(positions) {
  const wrap = document.getElementById('positionsWrap');
  if (!wrap) return;
  
  // Use live data if available, fall back to snapshot data
  const livePositions = livePositionData?.positions || [];
  const snapshotPositions = positions || [];
  const executionPositions = currentSnapshot?.tradierExecution?.positions || [];
  
  // Build position map with live data taking precedence
  const positionMap = new Map();
  
  // Add snapshot positions first
  snapshotPositions.forEach(pos => {
    if (pos.status === 'open') {
      positionMap.set(pos.position_id, pos);
    }
  });
  
  // Add execution positions
  executionPositions.forEach(ep => {
    if (ep.current_status === 'open') {
      const instrument = ep.contract?.split(' ', 1)[1] || ep.contract;
      positionMap.set(ep.position_id, {
        symbol: ep.symbol,
        instrument: instrument,
        entry: String(ep.entry_price),
        current: String(ep.entry_price),
        size: String(ep.qty),
        status: 'open',
        position_id: ep.position_id,
        notes: ep.notes || '',
      });
    }
  });
  
  // Merge live data (has real-time prices)
  livePositions.forEach(lp => {
    const key = lp.description; // Use description as key since IDs may differ
    // Find matching position by symbol and instrument
    for (const [pid, pos] of positionMap) {
      if (pos.symbol === lp.symbol && pos.instrument.includes(String(lp.strike))) {
        positionMap.set(pid, {
          ...pos,
          current: String(lp.current_price),
          live_price: lp.current_price,
          market_value: lp.market_value,
          pnl_dollar: lp.pnl_dollar,
          pnl_percent: lp.pnl_percent,
          days_to_expiry: lp.days_to_expiry,
          option_type: lp.option_type,
          strike: lp.strike,
          expiration: lp.expiration,
        });
        break;
      }
    }
  });
  
  const openPositions = Array.from(positionMap.values());
  
  if (openPositions.length === 0) {
    wrap.innerHTML = '<div class="void">No open positions</div>';
    return;
  }
  
  // Calculate total P&L
  let totalPnL = 0;
  openPositions.forEach(pos => {
    if (pos.pnl_dollar !== undefined) {
      totalPnL += pos.pnl_dollar;
    } else {
      const { pnl } = calculatePnL(pos.entry, pos.current, pos.size);
      totalPnL += pnl;
    }
  });
  
  wrap.innerHTML = openPositions.map(pos => {
    const pnl = pos.pnl_dollar !== undefined ? pos.pnl_dollar : calculatePnL(pos.entry, pos.current, pos.size).pnl;
    const pnlClass = pnl >= 0 ? 'positive' : 'negative';
    return `
      <div class="position-row">
        <span class="pos-symbol">${escapeHtml(pos.symbol)}</span>
        <span class="pos-details">${escapeHtml(pos.instrument)} × ${escapeHtml(pos.size)}</span>
        <span class="pos-pnl ${pnlClass}">${formatPnL(pnl)}</span>
      </div>
    `;
  }).join('');
}

function renderTradierSlice() {
  if (!currentSnapshot && currentUiMode !== 'loading') return;
  if (currentSnapshot) {
    renderOverview(currentSnapshot);
    renderPositions(currentSnapshot?.activePositions?.positions || []);
  }
  renderLeaders(currentSnapshot?.tradier?.leaders || []);
}

async function refresh() {
  currentUiMode = 'loading';
  currentLoadError = null;
  renderTradierSlice();
  try {
    currentSnapshot = await loadSnapshot();
    await fetchRefreshStatus();
    currentUiMode = 'ready';
    syncSelectedLeader(currentSnapshot?.tradier?.leaders || []);
    const updatedAtEl = document.getElementById('updatedAt');
    if (updatedAtEl) updatedAtEl.textContent = `Snapshot: ${currentSnapshot.updatedAt}`;
    renderTradierSlice();
  } catch (err) {
    currentUiMode = 'error';
    currentLoadError = err.message;
    const updatedAtEl = document.getElementById('updatedAt');
    if (updatedAtEl) updatedAtEl.textContent = 'Snapshot unavailable';
    renderTradierSlice();
    throw err;
  }
}

// Load alert configuration
loadAlertConfig();
updateAlertControls();

// Trade Journal globals
let journalData = null;
let analyticsData = null;
let premarketData = null;

// Pre-market scanner
async function runPremarketScan() {
  const resultsDiv = document.getElementById('premarketResults');
  const timeDiv = document.getElementById('premarketTime');
  
  resultsDiv.innerHTML = '<div class="premarket-loading">Scanning for gaps...</div>';
  
  try {
    const res = await fetch('/api/premarket');
    const data = await res.json();
    
    if (data.ok) {
      premarketData = data.data;
      if (timeDiv) timeDiv.textContent = 'Last scan: ' + new Date().toLocaleTimeString();
      renderPremarketResults(data.data);
    } else {
      resultsDiv.innerHTML = `<div class="premarket-error">Scan failed: ${data.error}</div>`;
    }
  } catch (err) {
    resultsDiv.innerHTML = `<div class="premarket-error">Error: ${err.message}</div>`;
  }
}

function renderPremarketResults(data) {
  const container = document.getElementById('premarketResults');
  
  if (data.gaps_found === 0) {
    container.innerHTML = '<div class="premarket-empty">No significant gaps found (>3%)</div>';
    return;
  }
  
  const highPriority = data.high_priority || [];
  const mediumPriority = data.medium_priority || [];
  
  container.innerHTML = `
    <div class="premarket-summary">
      <span class="premarket-count">${data.gaps_found} gaps found</span>
      <span class="premarket-high">${highPriority.length} high priority</span>
    </div>
    
    ${highPriority.length > 0 ? `
      <div class="premarket-section">
        <div class="premarket-section-title">🔥 High Priority (>5%)</div>
        ${highPriority.map(gap => renderGapCard(gap)).join('')}
      </div>
    ` : ''}
    
    ${mediumPriority.length > 0 ? `
      <div class="premarket-section">
        <div class="premarket-section-title">📊 Medium Priority (3-5%)</div>
        ${mediumPriority.map(gap => renderGapCard(gap)).join('')}
      </div>
    ` : ''}
  `;
}

function renderGapCard(gap) {
  const isUp = gap.direction === 'gap_up';
  const directionEmoji = isUp ? '🚀' : '🔻';
  const directionClass = isUp ? 'gap-up' : 'gap-down';
  const volumeClass = gap.relative_volume > 2 ? 'high-volume' : '';
  
  return `
    <div class="gap-card ${directionClass}">
      <div class="gap-header">
        <span class="gap-symbol">${escapeHtml(gap.symbol)} ${directionEmoji}</span>
        <span class="gap-percent ${directionClass}">${isUp ? '+' : ''}${gap.gap_percent}%</span>
      </div>
      <div class="gap-details">
        <span>Last: $${typeof gap.last_price === 'number' ? gap.last_price.toFixed(2) : '--'}</span>
        <span>Prev: $${typeof gap.prev_close === 'number' ? gap.prev_close.toFixed(2) : '--'}</span>
        <span class="gap-volume ${volumeClass}">Vol: ${typeof gap.relative_volume === 'number' ? gap.relative_volume.toFixed(1) : '--'}x avg</span>
      </div>
      ${gap.option_plays ? `
        <div class="gap-plays">
          ${gap.option_plays.map(play => `
            <div class="gap-play ${play.direction}">
              <span class="play-strategy">${escapeHtml(play.strategy)}</span>
              <span class="play-risk">${escapeHtml(play.risk)} risk</span>
            </div>
          `).join('')}
        </div>
      ` : ''}
      <button class="queue-gap-btn" onclick="queueGap('${escapeHtml(gap.symbol)}', '${gap.direction}')">
        + Add to Watchlist
      </button>
    </div>
  `;
}

async function queueGap(symbol, direction) {
  // Add to execution queue for market open
  try {
    const leader = {
      symbol: symbol,
      option_type: direction === 'gap_up' ? 'PUT' : 'CALL',
      headline: `Pre-market ${direction} play`,
      entry: 'Gap fade',
      thesis: `Fade the ${direction.replace('_', ' ')} at market open`
    };
    
    const res = await fetch('/api/queue', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(leader)
    });
    
    if (res.ok) {
      alert(`${symbol} added to execution queue for market open`);
    }
  } catch (err) {
    alert('Failed to queue: ' + err.message);
  }
}

// Fetch journal entries
async function fetchJournal() {
  try {
    const res = await fetch('/api/journal');
    if (res.ok) {
      const data = await res.json();
      if (data.ok) {
        journalData = data.trades;
        return data.trades;
      }
    }
  } catch (err) {
    console.error('Failed to fetch journal:', err);
  }
  return null;
}

// Fetch analytics
async function fetchAnalytics(period = 'all') {
  try {
    const res = await fetch(`/api/analytics?period=${period}`);
    if (res.ok) {
      const data = await res.json();
      if (data.ok) {
        analyticsData = data.analytics;
        return data.analytics;
      }
    }
  } catch (err) {
    console.error('Failed to fetch analytics:', err);
  }
  return null;
}

// Update analytics display
async function updateAnalytics() {
  const period = document.getElementById('analyticsPeriod')?.value || 'all';
  const analytics = await fetchAnalytics(period);
  
  const container = document.getElementById('analyticsSummary');
  if (!container || !analytics) return;
  
  if (analytics.total_trades === 0) {
    container.innerHTML = '<div class="analytics-empty">No trades yet. Execute a trade to see analytics.</div>';
    return;
  }
  
  const winRateClass = analytics.win_rate >= 50 ? 'good' : 'bad';
  const pnlClass = analytics.total_pnl >= 0 ? 'good' : 'bad';
  
  container.innerHTML = `
    <div class="analytics-grid">
      <div class="analytics-item">
        <div class="analytics-value">${analytics.total_trades}</div>
        <div class="analytics-label">Total Trades</div>
      </div>
      <div class="analytics-item">
        <div class="analytics-value ${winRateClass}">${analytics.win_rate}%</div>
        <div class="analytics-label">Win Rate</div>
      </div>
      <div class="analytics-item">
        <div class="analytics-value ${pnlClass}">$${typeof analytics.total_pnl === 'number' ? analytics.total_pnl.toFixed(2) : '0.00'}</div>
        <div class="analytics-label">Total P&L</div>
      </div>
      <div class="analytics-item">
        <div class="analytics-value">$${typeof analytics.avg_pnl === 'number' ? analytics.avg_pnl.toFixed(2) : '0.00'}</div>
        <div class="analytics-label">Avg P&L</div>
      </div>
      <div class="analytics-item">
        <div class="analytics-value">${analytics.max_drawdown_streak}</div>
        <div class="analytics-label">Max Loss Streak</div>
      </div>
      <div class="analytics-item">
        <div class="analytics-value">${typeof analytics.avg_duration_minutes === 'number' ? analytics.avg_duration_minutes.toFixed(0) : '--'}m</div>
        <div class="analytics-label">Avg Duration</div>
      </div>
    </div>
    ${analytics.best_trade && typeof analytics.best_trade.pnl === 'number' ? `
      <div class="trade-extremes">
        <div class="extreme best">
          <span class="extreme-label">Best Trade</span>
          <span class="extreme-value good">+$${analytics.best_trade.pnl.toFixed(2)}</span>
          <span class="extreme-symbol">${analytics.best_trade.symbol}</span>
        </div>
        <div class="extreme worst">
          <span class="extreme-label">Worst Trade</span>
          <span class="extreme-value bad">$${analytics.worst_trade && typeof analytics.worst_trade.pnl === 'number' ? analytics.worst_trade.pnl.toFixed(2) : '0.00'}</span>
          <span class="extreme-symbol">${analytics.worst_trade?.symbol || '--'}</span>
        </div>
      </div>
    ` : ''}
  `;
  
  // Also update journal entries
  renderJournalEntries();
}

// Render journal entries
function renderJournalEntries() {
  const container = document.getElementById('journalEntries');
  if (!container || !journalData) return;
  
  if (journalData.length === 0) {
    container.innerHTML = '<div class="journal-empty">No trades recorded yet.</div>';
    return;
  }
  
  // Show last 10 trades
  const recentTrades = journalData.slice(0, 10);
  
  container.innerHTML = `
    <div class="journal-list">
      ${recentTrades.map(trade => {
        const entry = trade.entry;
        const exit = trade.exit;
        const isWin = trade.pnl && trade.pnl.dollar > 0;
        const pnlClass = isWin ? 'good' : trade.pnl ? 'bad' : 'muted';
        const pnlText = trade.pnl && typeof trade.pnl.dollar === 'number' ? `${isWin ? '+' : ''}$${trade.pnl.dollar.toFixed(2)}` : 'Open';
        
        return `
          <div class="journal-item ${trade.status}">
            <div class="journal-main">
              <span class="journal-symbol">${escapeHtml(entry.symbol)}</span>
              <span class="journal-contract">${escapeHtml(entry.option_type)} ${entry.strike} ${entry.expiration}</span>
              <span class="journal-pnl ${pnlClass}">${pnlText}</span>
            </div>
            <div class="journal-details">
              <span>Entry: $${entry.price} × ${entry.quantity}</span>
              ${exit ? `<span>Exit: $${exit.price} (${exit.reason})</span>` : '<span>Open position</span>'}
              ${trade.duration_minutes && typeof trade.duration_minutes === 'number' ? `<span>Duration: ${trade.duration_minutes.toFixed(0)}m</span>` : ''}
            </div>
            ${trade.tags.length > 0 ? `
              <div class="journal-tags">
                ${trade.tags.map(tag => `<span class="journal-tag">${escapeHtml(tag)}</span>`).join('')}
              </div>
            ` : ''}
          </div>
        `;
      }).join('')}
    </div>
  `;
}

// Export journal to CSV
async function exportJournal() {
  try {
    const res = await fetch('/api/journal/export', { method: 'POST' });
    if (res.ok) {
      const data = await res.json();
      if (data.ok) {
        alert(`Journal exported to: ${data.path}`);
      } else {
        alert('Export failed: ' + data.error);
      }
    }
  } catch (err) {
    alert('Export error: ' + err.message);
  }
}

document.getElementById('refreshBtn').addEventListener('click', refresh);
refresh().catch(err => {
  const serverState = document.getElementById('serverState');
  if (serverState) {
    serverState.textContent = 'ERROR';
    serverState.className = 'status-pill bad';
  }
  const detailWrap = document.getElementById('detailWrap');
  if (detailWrap) {
    detailWrap.className = 'detail-wrap placeholder';
    detailWrap.textContent = err.message;
  }
});

// Auto-refresh every 30 seconds for general snapshot
setInterval(() => {
  refresh().catch(() => {});
}, 30000);

// Auto-refresh positions every 5 seconds for real-time P&L
setInterval(() => {
  fetchLivePositions().then(() => {
    if (currentSnapshot) {
      renderPositions(currentSnapshot?.activePositions?.positions || []);
    }
  }).catch(() => {});
}, 5000);

// Auto-refresh scanner every 10 seconds for live market data
setInterval(() => {
  fetchLiveScanner().then(() => {
    if (currentSnapshot) {
      renderLeaders(currentSnapshot?.tradier?.leaders || []);
    }
  }).catch(() => {});
}, 10000);

// Auto-refresh exit predictor every 30 seconds
setInterval(() => {
  fetchExitPredictor().then(() => {
    if (currentSnapshot) {
      renderPositions(currentSnapshot?.activePositions?.positions || []);
      // Check for new EXIT alerts
      checkExitAlerts(currentSnapshot?.activePositions?.positions || []);
    }
  }).catch(() => {});
}, 30000);

// Load journal on init
fetchJournal().then(() => {
  updateAnalytics();
});

// Portfolio Heatmap globals
let heatmapData = null;

// Fetch portfolio heatmap
async function fetchHeatmap() {
  try {
    const res = await fetch('/api/heatmap');
    if (res.ok) {
      const data = await res.json();
      if (data.ok) {
        heatmapData = data.data;
        renderHeatmap(data.data);
        renderRiskMetrics(data.data);
        return data.data;
      }
    }
  } catch (err) {
    console.error('Failed to fetch heatmap:', err);
  }
  return null;
}

function renderHeatmap(data) {
  const container = document.getElementById('heatmapContainer');
  if (!container) return;
  
  if (!data.positions || data.positions.length === 0) {
    container.innerHTML = '<div class="heatmap-empty">No positions to display</div>';
    return;
  }
  
  // Calculate cell sizes based on position value relative to total
  const totalValue = data.total_value;
  
  container.innerHTML = `
    <div class="heatmap-grid">
      ${data.positions.map(pos => {
        // Size based on market value
        const sizePercent = totalValue > 0 ? (pos.market_value / totalValue) * 100 : 0;
        const minSize = 15; // Minimum size percentage
        const cellSize = Math.max(minSize, sizePercent);
        
        // Color based on P&L
        const pnlPercent = pos.pnl_percent || 0;
        let colorClass = 'heatmap-neutral';
        let intensity = 0;
        
        if (pnlPercent > 0) {
          // Green for winners, intensity based on % gain
          colorClass = 'heatmap-green';
          intensity = Math.min(100, Math.abs(pnlPercent) * 5); // Scale up for visibility
        } else if (pnlPercent < 0) {
          // Red for losers
          colorClass = 'heatmap-red';
          intensity = Math.min(100, Math.abs(pnlPercent) * 5);
        }
        
        // Format display
        const pnlSign = pnlPercent >= 0 ? '+' : '';
        
        return `
          <div class="heatmap-cell ${colorClass}" 
               style="flex: 0 0 ${cellSize}%; --intensity: ${intensity}%"
               title="${pos.symbol} ${pos.option_type} $${pos.strike} - P&L: ${pnlSign}${typeof pnlPercent === 'number' ? pnlPercent.toFixed(1) : '--'}%">
            <div class="heatmap-cell-content">
              <div class="heatmap-symbol">${escapeHtml(pos.symbol)}</div>
              <div class="heatmap-details">
                <span class="heatmap-strike">$${escapeHtml(pos.strike)}</span>
                <span class="heatmap-dte">${pos.dte}DTE</span>
              </div>
              <div class="heatmap-pnl ${pnlPercent >= 0 ? 'good' : 'bad'}">${pnlSign}${typeof pnlPercent === 'number' ? pnlPercent.toFixed(1) : '--'}%</div>
            </div>
          </div>
        `;
      }).join('')}
    </div>
  `;
}

function renderRiskMetrics(data) {
  const container = document.getElementById('riskMetrics');
  if (!container) return;
  
  const metrics = data.risk_metrics || {};
  const alerts = data.alerts || [];
  
  // Determine delta bias
  const delta = metrics.total_delta || 0;
  let deltaBias = 'Neutral';
  let deltaClass = 'neutral';
  if (delta > 10) {
    deltaBias = 'Bullish 📈';
    deltaClass = 'bullish';
  } else if (delta < -10) {
    deltaBias = 'Bearish 📉';
    deltaClass = 'bearish';
  }
  
  // Theta interpretation
  const theta = metrics.total_theta || 0;
  const thetaClass = theta < -50 ? 'bad' : theta < 0 ? 'warning' : 'good';
  
  container.innerHTML = `
    <div class="risk-metrics-grid">
      <div class="risk-metric">
        <span class="risk-label">Total Delta</span>
        <span class="risk-value ${deltaClass}">${typeof delta === 'number' ? delta.toFixed(1) : '--'} (${deltaBias})</span>
      </div>
      <div class="risk-metric">
        <span class="risk-label">Daily Theta</span>
        <span class="risk-value ${thetaClass}">$${typeof theta === 'number' ? theta.toFixed(2) : '--'}/day</span>
      </div>
      <div class="risk-metric">
        <span class="risk-label">Total Vega</span>
        <span class="risk-value">${metrics.total_vega?.toFixed(1) || 0}</span>
      </div>
      <div class="risk-metric">
        <span class="risk-label">Max Loss</span>
        <span class="risk-value bad">-$${metrics.max_loss_scenario?.toFixed(2) || 0}</span>
      </div>
    </div>
    
    ${alerts.length > 0 ? `
      <div class="risk-alerts">
        <div class="risk-alerts-title">⚠️ Risk Alerts</div>
        ${alerts.map(alert => `
          <div class="risk-alert ${alert.severity}">
            <span class="alert-icon">${alert.severity === 'warning' ? '⚠️' : 'ℹ️'}</span>
            <span class="alert-message">${escapeHtml(alert.message)}</span>
          </div>
        `).join('')}
      </div>
    ` : ''}
    
    ${Object.keys(data.concentration || {}).length > 0 ? `
      <div class="concentration-section">
        <div class="concentration-title">Portfolio Concentration</div>
        <div class="concentration-bars">
          ${Object.entries(data.concentration).map(([symbol, data]) => `
            <div class="concentration-item">
              <span class="concentration-symbol">${escapeHtml(symbol)}</span>
              <div class="concentration-bar">
                <div class="concentration-fill ${data.percent > 20 ? 'high' : ''}" style="width: ${Math.min(100, data.percent)}%"></div>
              </div>
              <span class="concentration-percent ${data.percent > 20 ? 'high' : ''}">${data.percent}%</span>
            </div>
          `).join('')}
        </div>
      </div>
    ` : ''}
  `;
}

// Load heatmap on init
fetchHeatmap();

// Auto-refresh heatmap every 30 seconds
setInterval(() => {
  fetchHeatmap().catch(() => {});
}, 30000);

// Crypto Trading Module
let cryptoInitialized = false;
let cryptoWalletAddress = null;

async function initCryptoWallet() {
  const btn = document.getElementById('cryptoInitBtn');
  btn.textContent = 'Initializing...';
  btn.disabled = true;
  
  try {
    const res = await fetch('/api/crypto/init', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'init' })
    });
    
    const data = await res.json();
    if (data.ok) {
      cryptoInitialized = true;
      cryptoWalletAddress = data.address;
      renderCryptoWallet(data);
      document.getElementById('cryptoEmergencyBtn').style.display = 'inline-block';
      btn.style.display = 'none';
      fetchCryptoPairs();
    } else {
      alert('Failed to initialize: ' + data.error);
      btn.textContent = '🔐 Initialize Wallet';
      btn.disabled = false;
    }
  } catch (err) {
    alert('Error: ' + err.message);
    btn.textContent = '🔐 Initialize Wallet';
    btn.disabled = false;
  }
}

function renderCryptoWallet(data) {
  const container = document.getElementById('cryptoWalletInfo');
  
  container.innerHTML = `
    <div class="crypto-wallet-header">
      <div class="crypto-section-title">💳 Wallet</div>
      <div class="crypto-wallet-address">${escapeHtml(data.address)}</div>
    </div>
    <div class="crypto-balance">
      <div class="crypto-balance-item">
        <div class="crypto-balance-value">${data.eth_balance?.toFixed(4) || 0}</div>
        <div class="crypto-balance-label">ETH</div>
      </div>
      ${Object.entries(data.tokens || {}).map(([token, balance]) => `
        <div class="crypto-balance-item">
          <div class="crypto-balance-value">${balance?.toFixed(2) || 0}</div>
          <div class="crypto-balance-label">${escapeHtml(token)}</div>
        </div>
      `).join('')}
    </div>
    <div class="crypto-status ${data.emergency_stop ? 'bad' : 'good'}">
      ${data.emergency_stop ? '🛑 Emergency Stop Active' : '✅ Trading Active'}
    </div>
  `;
}

async function fetchCryptoPairs() {
  try {
    const res = await fetch('/api/crypto/pairs');
    const data = await res.json();
    
    if (data.ok) {
      const container = document.getElementById('cryptoPairsList');
      container.innerHTML = data.pairs.map(pair => `
        <div class="crypto-pair-row">
          <span class="crypto-pair-name">${escapeHtml(pair.pair)}</span>
          <span class="crypto-pair-price">${pair.quote?.toFixed(6) || 'N/A'}</span>
        </div>
      `).join('');
    }
  } catch (err) {
    console.error('Failed to fetch crypto pairs:', err);
  }
}

async function toggleCryptoEmergencyStop() {
  try {
    const res = await fetch('/api/crypto/emergency', { method: 'POST' });
    const data = await res.json();
    
    if (data.ok) {
      alert(data.stopped ? '🛑 Emergency Stop Activated' : '✅ Trading Resumed');
      // Refresh wallet info
      const walletRes = await fetch('/api/crypto/wallet');
      const walletData = await walletRes.json();
      if (walletData.ok) renderCryptoWallet(walletData);
    }
  } catch (err) {
    alert('Error: ' + err.message);
  }
}

// Auto-refresh crypto data every 30 seconds if initialized
setInterval(() => {
  if (cryptoInitialized) {
    fetch('/api/crypto/wallet')
      .then(r => r.json())
      .then(data => { if (data.ok) renderCryptoWallet(data); })
      .catch(() => {});
  }
}, 30000);
