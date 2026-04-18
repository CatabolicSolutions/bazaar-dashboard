const API_BASE = '';
const POLL_INTERVAL = 5000;

const state = {
    tradier: { bp: 0, positions: 0, orders: 0, health: 'red' },
    bloc: { usdc: 0, weth: 0, positions: 0, health: 'red' },
    hq: { engine_truth_board: { tradier: {}, bloc: {} } },
    positions: [],
    activity: [],
    sie: {}
};

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
    activityList: document.getElementById('activity-list'),
    btnPauseBloc: document.getElementById('btn-pause-bloc'),
    btnPauseTradier: document.getElementById('btn-pause-tradier'),
    btnCloseAll: document.getElementById('btn-close-all')
};

function fmtMoney(v, digits = 2) {
    if (typeof v !== 'number' || Number.isNaN(v)) return '--';
    return `$${v.toFixed(digits)}`;
}

function fmtBool(v) {
    if (v === true) return 'Yes';
    if (v === false) return 'No';
    return '--';
}

function cleanLabel(v) {
    if (!v) return '--';
    return String(v).replaceAll('_', ' ');
}

function titleCase(v) {
    const s = cleanLabel(v);
    return s === '--' ? s : s.replace(/\b\w/g, c => c.toUpperCase());
}

function truth() {
    return state.hq?.engine_truth_board || { tradier: {}, bloc: {} };
}

function readinessScore(path) {
    if (!path) return 0;
    let score = 0;
    if (path.funded) score += 1;
    if (path.path_ready) score += 1;
    if (path.edge_proven) score += 1;
    return score;
}

function computeDirective() {
    const t = truth().tradier || {};
    const b = truth().bloc || {};
    const activePositions = Array.isArray(state.positions) ? state.positions.length : 0;

    if (activePositions > 0) {
        return {
            title: 'Manage live risk',
            badge: 'Live Risk',
            badgeClass: 'badge-red',
            copy: `There ${activePositions === 1 ? 'is' : 'are'} ${activePositions} active ${activePositions === 1 ? 'position' : 'positions'} on the board. Monitor exits, unrealized P&L, and forced-close readiness before looking for fresh entries.`
        };
    }

    if (t.path_ready && t.funded && !t.edge_proven) {
        return {
            title: 'Tradier operational, edge not yet validated',
            badge: 'Await Edge',
            badgeClass: 'badge-amber',
            copy: t.top_blocker
                ? `Tradier is structurally ready, but the last execution failed on a hard constraint: ${t.top_blocker}. Fix sizing and only take the next setup if notional fits buying power.`
                : 'Tradier is structurally ready. Next step is disciplined selection and sizing, not more scaffolding.'
        };
    }

    if (b.path_ready && b.funded && !b.edge_proven) {
        return {
            title: 'Bloc funded, but no proven edge',
            badge: 'No Trade',
            badgeClass: 'badge-amber',
            copy: 'Bloc has capital and plumbing, but the edge filter is not yet earning trust. Prioritize contract selection quality, fair-value anchoring, and friction-aware execution checks.'
        };
    }

    return {
        title: 'Monitor and refine',
        badge: 'Monitoring',
        badgeClass: 'badge-amber',
        copy: 'No urgent live action is required. Keep the stack honest, surface blockers clearly, and improve the highest-return path.'
    };
}

function buildNextActions() {
    const t = truth().tradier || {};
    const b = truth().bloc || {};
    const actions = [];

    if (t.top_blocker) {
        actions.push({
            title: 'Fix Tradier sizing mismatch',
            copy: `Last attempt failed because ${t.top_blocker}. Lower ticket notional so the next live candidate can clear buying power.`
        });
    }

    if (b.funded && !b.edge_proven) {
        actions.push({
            title: 'Do not force a Bloc trade',
            copy: 'Keep Bloc in no-trade mode until a contract survives probability, friction, and clarity checks.'
        });
    }

    if ((state.positions || []).length === 0) {
        actions.push({
            title: 'Use dashboard for go or no-go, not decoration',
            copy: 'Focus on capital, blockers, readiness, and next action. Ignore vanity metrics unless they change a decision.'
        });
    }

    actions.push({
        title: 'Review latest activity for false progress',
        copy: 'Look for repeated rejects, stale statuses, or any workflow that appears alive but is not actually producing tradable opportunities.'
    });

    return actions.slice(0, 4);
}

function renderHeadline() {
    const t = truth().tradier || {};
    const b = truth().bloc || {};
    const directive = computeDirective();
    const activePositions = Array.isArray(state.positions) ? state.positions.length : 0;

    el.asof.textContent = `Updated ${new Date().toLocaleString()}`;
    el.headlineDecision.textContent = directive.title;
    el.headlineReason.textContent = directive.copy;

    el.headlineTradier.textContent = `${readinessScore(t)}/3 ready`;
    el.headlineTradierSub.textContent = `${titleCase(t.status_label)} • ${fmtMoney(t.available_capital_usd)}`;

    el.headlineBloc.textContent = `${readinessScore(b)}/3 ready`;
    el.headlineBlocSub.textContent = `${titleCase(b.status_label)} • ${fmtMoney(b.available_capital_usd, 2)}`;

    el.headlineExposure.textContent = `${activePositions} ${activePositions === 1 ? 'position' : 'positions'}`;
    el.headlineExposureSub.textContent = activePositions > 0 ? 'Live risk requires supervision' : 'No active risk detected';

    el.directiveTitle.textContent = directive.title;
    el.directiveBadge.textContent = directive.badge;
    el.directiveBadge.className = `decision-badge ${directive.badgeClass}`;
    el.directiveCopy.textContent = directive.copy;

    el.miniTradierCapital.textContent = fmtMoney(t.available_capital_usd);
    el.miniBlocCapital.textContent = fmtMoney(b.available_capital_usd, 2);
    const eth = typeof state.sie.eth_price === 'number' ? `$${state.sie.eth_price.toFixed(2)}` : '--';
    const mom = typeof state.sie.momentum === 'number' ? `${(state.sie.momentum * 100).toFixed(2)}%` : '--';
    el.miniReality.textContent = `ETH ${eth} | Mom ${mom}`;
}

function renderReadiness() {
    const systems = [
        { key: 'Tradier', data: truth().tradier || {}, capital: state.tradier.bp },
        { key: 'Bloc', data: truth().bloc || {}, capital: state.bloc.usdc }
    ];

    el.readinessList.innerHTML = systems.map(({ key, data, capital }) => `
        <div class="ops-item">
            <div class="ops-item-head">
                <div class="ops-name">${key}</div>
                <div class="decision-badge ${data.edge_proven ? 'badge-green' : (data.path_ready ? 'badge-amber' : 'badge-red')}">${readinessScore(data)}/3 ready</div>
            </div>
            <div class="ops-summary">${titleCase(data.status_label)}. ${data.edge_proven ? 'System has proven edge.' : 'Not yet cleared for confident scaling.'}</div>
            <div class="kv">
                <div><span>Funded</span>${fmtBool(data.funded)}</div>
                <div><span>Path ready</span>${fmtBool(data.path_ready)}</div>
                <div><span>Edge proven</span>${fmtBool(data.edge_proven)}</div>
                <div><span>Capital</span>${fmtMoney(data.available_capital_usd ?? capital, 2)}</div>
                <div><span>Last stage</span>${titleCase(data.last_lifecycle_stage)}</div>
                <div><span>Last attempt</span>${titleCase(data.last_attempt_status)}</div>
            </div>
            <div class="blocker"><strong>Top blocker:</strong> ${data.top_blocker || data.last_rejection_reason || 'None currently surfaced'}</div>
        </div>
    `).join('');
}

function renderNextActions() {
    const actions = buildNextActions();
    el.nextActions.innerHTML = actions.map((item, idx) => `
        <div class="next-action">
            <div class="num">${idx + 1}</div>
            <div class="action-copy"><strong>${item.title}</strong>${item.copy}</div>
        </div>
    `).join('');
}

function renderPositions() {
    const positions = Array.isArray(state.positions) ? state.positions : [];
    if (!positions.length) {
        el.positionsList.innerHTML = '<div class="positions-empty">No active positions. That is good if edge is absent, bad if the engine should be live and is silently stalled.</div>';
        return;
    }

    el.positionsList.innerHTML = positions.map((pos) => {
        const pnl = typeof pos.pnl === 'number' ? `${pos.pnl >= 0 ? '+' : ''}${fmtMoney(pos.pnl)}` : '--';
        return `
            <div class="position-row">
                <div class="position-top">
                    <div>${pos.symbol || '--'} ${pos.side || ''}</div>
                    <div class="${typeof pos.pnl === 'number' ? (pos.pnl >= 0 ? 'good' : 'bad') : ''}">${pnl}</div>
                </div>
                <div class="meta-row">
                    <span>Entry: ${fmtMoney(pos.entry)}</span>
                    <span>Size: ${pos.size ?? '--'}</span>
                    <span>Status: ${titleCase(pos.status)}</span>
                </div>
            </div>
        `;
    }).join('');
}

function renderActivity() {
    const activity = Array.isArray(state.activity) ? state.activity : [];
    if (!activity.length) {
        el.activityList.innerHTML = '<div class="activity-empty">No recent activity available.</div>';
        return;
    }

    el.activityList.innerHTML = activity.slice(0, 8).map((row) => `
        <div class="activity-row">
            <div class="activity-top">
                <div>${row.system || '--'} • ${row.symbol || '--'}</div>
                <div>${row.time || '--'}</div>
            </div>
            <div class="meta-row">
                <span>Side: ${row.side || '--'}</span>
                <span>P&L: ${row.pnl == null ? '--' : `${row.pnl >= 0 ? '+' : ''}${fmtMoney(row.pnl)}`}</span>
            </div>
        </div>
    `).join('');
}

function renderAll() {
    renderHeadline();
    renderReadiness();
    renderNextActions();
    renderPositions();
    renderActivity();
}

async function pollData() {
    try {
        const [tradierRes, blocRes, positionsRes, activityRes, sieRes, snapshotRes] = await Promise.all([
            fetch(`${API_BASE}/api/tradier/status`).then(r => r.json()).catch(() => ({})),
            fetch(`${API_BASE}/api/bloc/status`).then(r => r.json()).catch(() => ({})),
            fetch(`${API_BASE}/api/positions`).then(r => r.json()).catch(() => ({})),
            fetch(`${API_BASE}/api/activity`).then(r => r.json()).catch(() => ({})),
            fetch(`${API_BASE}/api/sie/status`).then(r => r.json()).catch(() => ({})),
            fetch(`${API_BASE}/snapshot.json`).then(r => r.json()).catch(() => ({}))
        ]);

        state.tradier = { ...state.tradier, ...tradierRes };
        state.bloc = { ...state.bloc, ...blocRes };
        state.positions = positionsRes.positions || [];
        state.activity = activityRes.activity || [];
        state.sie = sieRes || {};
        if (snapshotRes.hq) state.hq = snapshotRes.hq;

        renderAll();
    } catch (err) {
        console.error('Poll error:', err);
    }
}

function sendCommand(command, successText) {
    fetch(`${API_BASE}/api/command`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command })
    }).then(r => r.json())
      .then(() => alert(successText))
      .catch(err => {
          console.error('Command failed:', err);
          alert('Command failed');
      });
}

el.btnPauseBloc.addEventListener('click', () => sendCommand('pause_bloc', 'Bloc paused'));
el.btnPauseTradier.addEventListener('click', () => sendCommand('pause_tradier', 'Tradier paused'));
el.btnCloseAll.addEventListener('click', () => {
    if (confirm('Emergency close ALL positions?')) sendCommand('close_all', 'Emergency close initiated');
});

renderAll();
pollData();
setInterval(pollData, POLL_INTERVAL);
