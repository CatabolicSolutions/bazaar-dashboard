const API_BASE = '';
const POLL_INTERVAL = 5000;

const state = {
    tradier: { bp: 0, positions: 0, orders: 0, health: 'red' },
    bloc: { usdc: 0, weth: 0, positions: 0, health: 'red' },
    hq: { engine_truth_board: { tradier: {}, bloc: {} } },
    hqLive: null,
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
    const board = state.hq?.engine_truth_board || { tradier: {}, bloc: {} };
    const live = state.hqLive?.live || {};
    return {
        ...board,
        tradier: { ...(board.tradier || {}), ...(state.tradier || {}) },
        bloc: {
            ...(board.bloc || {}),
            ...(state.bloc || {}),
            ...(live ? {
                compounding_state: live.compounding_state,
                holding_asset: live.holding_asset,
                holding_units: live.holding_units,
                invested_capital_usd: live.invested_capital_usd,
                available_capital_usd: live.deployable_capital_usd,
                status_label: live.compounding_state,
                positions: live.active_positions,
            } : {})
        }
    };
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
    const b = { ...(truth().bloc || {}), ...(state.bloc || {}) };
    const activePositions = Array.isArray(state.positions) ? state.positions.length : 0;
    const effectivePositions = b.compounding_state === 'holding_active_inventory' && activePositions === 0 ? 1 : activePositions;

    if (b.compounding_state === 'holding_active_inventory') {
        return {
            title: 'Monitor compounding hold',
            badge: 'Active Hold',
            badgeClass: 'badge-amber',
            copy: `Bloc is holding ${b.holding_asset || 'inventory'}${b.holding_units ? ` (${b.holding_units})` : ''} with ${fmtMoney(b.invested_capital_usd, 2)} invested. Next best action is exit supervision and recycle discipline, not new entry.`
        };
    }

    if (effectivePositions > 0) {
        return {
            title: 'Manage live risk',
            badge: 'Live Risk',
            badgeClass: 'badge-red',
            copy: `There ${effectivePositions === 1 ? 'is' : 'are'} ${effectivePositions} active ${effectivePositions === 1 ? 'position' : 'positions'} on the board. Monitor exits, unrealized P&L, and forced-close readiness before looking for fresh entries.`
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

    if (b.path_ready) {
        return {
            title: 'Assess live Bloc state',
            badge: 'Monitoring',
            badgeClass: 'badge-amber',
            copy: 'Bloc runtime is online. Wait for either deployable capital or an active compounding inventory state worth supervising.'
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

    if (b.compounding_state === 'holding_active_inventory') {
        actions.push({
            title: 'Supervise the active compounding hold',
            copy: `Track ${b.holding_asset || 'inventory'} exposure, exit conditions, and recycle path. Do not allow fresh ETH entry logic to masquerade as available capital.`
        });
        actions.push({
            title: 'Verify mark and exit readiness',
            copy: `Confirm units, marked value, and executable unwind path for ${b.holding_asset || 'the held asset'} so HQ reflects real operator choices.`
        });
    }

    if (t.top_blocker) {
        actions.push({
            title: 'Fix Tradier sizing mismatch',
            copy: `Last attempt failed because ${t.top_blocker}. Lower ticket notional so the next live candidate can clear buying power.`
        });
    }

    if (b.funded && !b.edge_proven && b.compounding_state !== 'holding_active_inventory') {
        actions.push({
            title: 'Do not force a Bloc trade',
            copy: 'Keep Bloc in no-trade mode until a contract survives probability, friction, and clarity checks.'
        });
    }

    if ((state.positions || []).length === 0 && b.compounding_state !== 'holding_active_inventory') {
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
    if (state.hqLive && state.hqLive.live && state.hqLive.live.compounding_state === 'holding_active_inventory') {
        el.asof.textContent = `Updated ${new Date().toLocaleString()} • HQv5`;
        el.headlineDecision.textContent = 'Monitor compounding hold';
        el.headlineReason.textContent = `Holding ${state.hqLive.live.holding_asset} (${state.hqLive.live.holding_units}) as active compounding inventory.`;
        el.headlineBloc.textContent = 'Holding active inventory';
        el.headlineBlocSub.textContent = `${state.hqLive.live.holding_asset} • ${fmtMoney(state.hqLive.live.invested_capital_usd, 2)} invested`;
        el.headlineExposure.textContent = `${state.hqLive.live.active_positions || 1} position`;
        el.headlineExposureSub.textContent = 'Active compounding inventory requires supervision';
        el.directiveTitle.textContent = 'Monitor compounding hold';
        el.directiveBadge.textContent = 'Active Hold';
        el.directiveBadge.className = 'decision-badge badge-amber';
        el.directiveCopy.textContent = `Deployed capital is in ${state.hqLive.live.holding_asset}. Focus on recycle and exit quality.`;
        el.miniBlocCapital.textContent = `${fmtMoney(state.hqLive.live.invested_capital_usd, 2)} in ${state.hqLive.live.holding_asset}`;
    }
    const liveB = { ...(state.bloc || {}), ...((state.hqLive && state.hqLive.live) ? {
        holding_asset: state.hqLive.live.holding_asset,
        holding_units: state.hqLive.live.holding_units,
        invested_capital_usd: state.hqLive.live.invested_capital_usd,
        compounding_state: state.hqLive.live.compounding_state,
    } : {}) };
    const liveHolding = liveB.holding_asset || b.holding_asset;
    const liveInvested = typeof liveB.invested_capital_usd === 'number' ? liveB.invested_capital_usd : b.invested_capital_usd;
    const directive = computeDirective();
    const activePositions = Array.isArray(state.positions) ? state.positions.length : 0;

    el.asof.textContent = `Updated ${new Date().toLocaleString()} • HQv5`;
    el.headlineDecision.textContent = directive.title;
    el.headlineReason.textContent = directive.copy;

    el.headlineTradier.textContent = `${readinessScore(t)}/3 ready`;
    el.headlineTradierSub.textContent = `${titleCase(t.status_label)} • ${fmtMoney(t.available_capital_usd)}`;

    const blocHolding = liveB.compounding_state === 'holding_active_inventory' || b.compounding_state === 'holding_active_inventory' || !!liveHolding;
    el.headlineBloc.textContent = blocHolding ? 'Holding active inventory' : `${readinessScore(b)}/3 ready`;
    const blocCapitalLine = blocHolding
        ? `${liveHolding || 'Inventory'} • ${fmtMoney(liveInvested, 2)} invested`
        : `${titleCase(b.status_label)} • ${fmtMoney(b.available_capital_usd, 2)}`;
    el.headlineBlocSub.textContent = blocCapitalLine;

    const effectivePositions = blocHolding && activePositions === 0 ? 1 : activePositions;
    el.headlineExposure.textContent = `${effectivePositions} ${effectivePositions === 1 ? 'position' : 'positions'}`;
    el.headlineExposureSub.textContent = effectivePositions > 0
        ? (b.compounding_state === 'holding_active_inventory' ? 'Active compounding inventory requires supervision' : 'Live risk requires supervision')
        : 'No active risk detected';

    el.directiveTitle.textContent = directive.title;
    el.directiveBadge.textContent = directive.badge;
    el.directiveBadge.className = `decision-badge ${directive.badgeClass}`;
    el.directiveCopy.textContent = directive.copy;

    el.miniTradierCapital.textContent = fmtMoney(t.available_capital_usd);
    el.miniBlocCapital.textContent = blocHolding
        ? `${fmtMoney(liveInvested, 2)} in ${liveHolding || 'inventory'}`
        : fmtMoney(b.available_capital_usd, 2);
    const eth = typeof state.sie.eth_price === 'number' ? `$${state.sie.eth_price.toFixed(2)}` : '--';
    const mom = typeof state.sie.momentum === 'number' ? `${(state.sie.momentum * 100).toFixed(2)}%` : '--';
    el.miniReality.textContent = `ETH ${eth} | Mom ${mom}`;
}

function renderReadiness() {
    const blocData = { ...(truth().bloc || {}), ...(state.bloc || {}) };
    const systems = [
        { key: 'Tradier', data: truth().tradier || {}, capital: state.tradier.bp },
        { key: 'Bloc', data: blocData, capital: state.bloc.usdc }
    ];

    el.readinessList.innerHTML = systems.map(({ key, data, capital }) => `
        <div class="ops-item">
            <div class="ops-item-head">
                <div class="ops-name">${key}</div>
                <div class="decision-badge ${data.edge_proven ? 'badge-green' : (data.path_ready ? 'badge-amber' : 'badge-red')}">${readinessScore(data)}/3 ready</div>
            </div>
            <div class="ops-summary">${data.compounding_state === 'holding_active_inventory' ? `Holding ${data.holding_asset || 'inventory'} for managed recycle.` : `${titleCase(data.status_label)}. ${data.edge_proven ? 'System has proven edge.' : 'Not yet cleared for confident scaling.'}`}</div>
            <div class="kv">
                <div><span>Funded</span>${fmtBool(data.funded)}</div>
                <div><span>Path ready</span>${fmtBool(data.path_ready)}</div>
                <div><span>Edge proven</span>${fmtBool(data.edge_proven)}</div>
                <div><span>Capital</span>${fmtMoney((data.compounding_state === 'holding_active_inventory' ? data.invested_capital_usd : data.available_capital_usd) ?? capital, 2)}</div>
                <div><span>Last stage</span>${titleCase(data.last_lifecycle_stage)}</div>
                <div><span>Last attempt</span>${titleCase(data.last_attempt_status)}</div>
                <div><span>Holding</span>${data.holding_asset ? `${data.holding_asset} ${data.holding_units}` : '--'}</div>
            </div>
            <div class="blocker"><strong>Top blocker:</strong> ${data.compounding_state === 'holding_active_inventory' ? 'Monitoring active compounding inventory for recycle/exit' : (data.top_blocker || data.last_rejection_reason || 'None currently surfaced')}</div>
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
    const hqLivePositions = Array.isArray(state.hqLive?.live?.positions) ? state.hqLive.live.positions : [];
    const positions = hqLivePositions.length ? hqLivePositions : (Array.isArray(state.positions) ? state.positions : []);
    if (!positions.length) {
        const bloc = { ...(truth().bloc || {}), ...(state.bloc || {}) };
        if ((bloc.compounding_state === 'holding_active_inventory' || bloc.holding_asset) && bloc.holding_asset) {
            el.positionsList.innerHTML = `<div class="position-row"><div class="position-top"><div>${bloc.holding_asset} HOLD</div><div>${fmtMoney(bloc.invested_capital_usd, 2)}</div></div><div class="meta-row"><span>Units: ${bloc.holding_units ?? '--'}</span><span>Status: Holding active inventory</span><span>Action: Monitor for recycle</span></div></div>`;
            return;
        }
        el.positionsList.innerHTML = '<div class="positions-empty">No active positions. That is good if edge is absent, bad if the engine should be live and is silently stalled.</div>';
        return;
    }

    el.positionsList.innerHTML = positions.map((pos) => {
        const symbol = pos.symbol || pos.asset || '--';
        const side = pos.side || 'Hold';
        const pnl = typeof pos.pnl === 'number' ? `${pos.pnl >= 0 ? '+' : ''}${fmtMoney(pos.pnl)}` : (typeof pos.size_usd === 'number' ? fmtMoney(pos.size_usd) : '--');
        const entry = pos.entry ?? pos.entry_price;
        const size = pos.size ?? pos.units ?? '--';
        return `
            <div class="position-row">
                <div class="position-top">
                    <div>${symbol} ${side}</div>
                    <div class="${typeof pos.pnl === 'number' ? (pos.pnl >= 0 ? 'good' : 'bad') : ''}">${pnl}</div>
                </div>
                <div class="meta-row">
                    <span>Entry: ${typeof entry === 'number' ? fmtMoney(entry) : '--'}</span>
                    <span>Size: ${size}</span>
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

function wireControls() {
    if (el.btnPauseBloc) {
        el.btnPauseBloc.addEventListener('click', () => sendCommand('pause_bloc', 'Bloc paused'));
    }
    if (el.btnPauseTradier) {
        el.btnPauseTradier.addEventListener('click', () => sendCommand('pause_tradier', 'Tradier paused'));
    }
    if (el.btnCloseAll) {
        el.btnCloseAll.addEventListener('click', () => {
            if (confirm('Emergency close ALL positions?')) sendCommand('close_all', 'Emergency close initiated');
        });
    }
}

async function pollData() {
    try {
        const hqRes = await fetch(`${API_BASE}/api/hq/status`).then(r => r.json()).catch(() => ({}));
        if (hqRes.live) {
            state.hqLive = hqRes;
            state.bloc = {
                ...state.bloc,
                compounding_state: hqRes.live.compounding_state,
                holding_asset: hqRes.live.holding_asset,
                holding_units: hqRes.live.holding_units,
                invested_capital_usd: hqRes.live.invested_capital_usd,
                available_capital_usd: hqRes.live.deployable_capital_usd,
                positions: hqRes.live.active_positions,
            };
            state.positions = hqRes.live.positions || [];
        }

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
        if (!state.positions.length) state.positions = positionsRes.positions || [];
        state.activity = activityRes.activity || [];
        state.sie = sieRes || {};
        if (snapshotRes.hq) state.hq = snapshotRes.hq;

        renderAll();
    } catch (err) {
        console.error('Poll error:', err);
        if (el.directiveTitle) el.directiveTitle.textContent = 'Client render error';
        if (el.directiveCopy) el.directiveCopy.textContent = String(err && err.message ? err.message : err);
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

wireControls();
renderAll();
pollData();
setInterval(pollData, POLL_INTERVAL);
