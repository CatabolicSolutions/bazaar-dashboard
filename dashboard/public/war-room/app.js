// WAR ROOM — Real‑time Command Center
// Polls status endpoints every 5 seconds, updates UI.

// Config
const API_BASE = ''; // same origin
const POLL_INTERVAL = 5000;

// State
let state = {
    account: { usdc: 168, weth: 85 },
    pnlToday: 0,
    tradier: { bp: 150, positions: 0, orders: 0, health: 'green' },
    bloc: { usdc: 168, weth: 85, positions: 1, health: 'green' },
    hq: { engine_truth_board: { tradier: {}, bloc: {} } },
    positions: [],
    activity: []
};

// DOM elements
const el = {
    clock: document.getElementById('clock'),
    accountUsdc: document.getElementById('account-usdc'),
    accountWeth: document.getElementById('account-weth'),
    pnlToday: document.getElementById('pnl-today'),
    tradierHealth: document.getElementById('tradier-health'),
    tradierBp: document.getElementById('tradier-bp'),
    tradierPositions: document.getElementById('tradier-positions'),
    tradierOrders: document.getElementById('tradier-orders'),
    blocHealth: document.getElementById('bloc-health'),
    blocUsdc: document.getElementById('bloc-usdc'),
    blocWeth: document.getElementById('bloc-weth'),
    blocPositions: document.getElementById('bloc-positions'),
    positionsContainer: document.getElementById('positions-container'),
    activityTableBody: document.getElementById('activity-table-body'),
    truthTradierFunded: document.getElementById('truth-tradier-funded'),
    truthTradierPathReady: document.getElementById('truth-tradier-path-ready'),
    truthTradierEdgeProven: document.getElementById('truth-tradier-edge-proven'),
    truthTradierStatus: document.getElementById('truth-tradier-status'),
    truthTradierCapital: document.getElementById('truth-tradier-capital'),
    truthTradierStage: document.getElementById('truth-tradier-stage'),
    truthTradierAttempt: document.getElementById('truth-tradier-attempt'),
    truthTradierBlocker: document.getElementById('truth-tradier-blocker'),
    truthBlocFunded: document.getElementById('truth-bloc-funded'),
    truthBlocPathReady: document.getElementById('truth-bloc-path-ready'),
    truthBlocEdgeProven: document.getElementById('truth-bloc-edge-proven'),
    truthBlocStatus: document.getElementById('truth-bloc-status'),
    truthBlocCapital: document.getElementById('truth-bloc-capital'),
    truthBlocAttempt: document.getElementById('truth-bloc-attempt'),
    truthBlocRejection: document.getElementById('truth-bloc-rejection'),
    truthBlocSize: document.getElementById('truth-bloc-size'),
    truthBlocEdge: document.getElementById('truth-bloc-edge'),
    truthBlocFriction: document.getElementById('truth-bloc-friction'),
    btnPauseBloc: document.getElementById('btn-pause-bloc'),
    btnPauseTradier: document.getElementById('btn-pause-tradier'),
    btnCloseAll: document.getElementById('btn-close-all'),
    tradierOrder: document.getElementById('tradier-order'),
    ethPrice: document.getElementById('eth-price'),
    lastMomentum: document.getElementById('last-momentum')
};

// Update clock every second
function updateClock() {
    const now = new Date();
    const time = now.toLocaleTimeString('en-US', { hour12: false });
    el.clock.textContent = time;
}
setInterval(updateClock, 1000);
updateClock();

// Format currency
function formatCurrency(amount) {
    if (typeof amount !== 'number') return '$0.00';
    return '$' + amount.toFixed(2);
}

// Render account summary
function renderAccount() {
    el.accountUsdc.textContent = formatCurrency(state.account.usdc) + ' USDC';
    el.accountWeth.textContent = formatCurrency(state.account.weth) + ' WETH';
    el.pnlToday.textContent = (state.pnlToday >= 0 ? '+' : '') + formatCurrency(state.pnlToday);
}

// Render Tradier panel
function renderTradier() {
    el.tradierBp.textContent = formatCurrency(state.tradier.bp);
    el.tradierPositions.textContent = state.tradier.positions;
    el.tradierOrders.textContent = state.tradier.orders;
    el.tradierHealth.className = 'health-dot ' + (state.tradier.health === 'green' ? '' : 'red');
}

// Render Bloc panel
function renderBloc() {
    el.blocUsdc.textContent = formatCurrency(state.bloc.usdc);
    el.blocWeth.textContent = formatCurrency(state.bloc.weth);
    el.blocPositions.textContent = state.bloc.positions;
    el.blocHealth.className = 'health-dot ' + (state.bloc.health === 'green' ? '' : 'red');
}

// Render positions
function renderPositions() {
    if (state.positions.length === 0) {
        el.positionsContainer.innerHTML = '<div style="color: var(--text-dim); text-align: center; padding: 32px;">No active positions</div>';
        return;
    }
    let html = '';
    state.positions.forEach(pos => {
        const pnlColor = pos.pnl >= 0 ? 'var(--green)' : 'var(--red)';
        html += `
            <div class="position-card">
                <div class="position-header">
                    <span class="position-symbol">${pos.symbol} ${pos.side}</span>
                    <span class="position-side">${pos.side}</span>
                </div>
                <div class="position-details">
                    <div class="detail-item">
                        <span class="detail-label">Entry</span>
                        <span class="detail-value">${formatCurrency(pos.entry)}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">P&L</span>
                        <span class="detail-value" style="color: ${pnlColor};">${pos.pnl >= 0 ? '+' : ''}${formatCurrency(pos.pnl)}</span>
                    </div>
                </div>
                <div class="position-actions">
                    <button class="btn-close" data-symbol="${pos.symbol}" data-side="${pos.side}">Close</button>
                </div>
            </div>
        `;
    });
    el.positionsContainer.innerHTML = html;
    // Attach close button handlers
    document.querySelectorAll('.btn-close').forEach(btn => {
        btn.addEventListener('click', function() {
            const symbol = this.dataset.symbol;
            const side = this.dataset.side;
            if (confirm(`Close ${symbol} ${pos.side} position?`)) {
                // Call close endpoint
                fetch(`${API_BASE}/api/close`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ symbol, side })
                }).then(res => res.json()).then(data => {
                    console.log('Close response:', data);
                    pollData(); // Refresh
                }).catch(err => console.error('Close failed:', err));
            }
        });
    });
}

// Render activity table
function renderActivity() {
    let html = '';
    state.activity.forEach(row => {
        html += `
            <tr>
                <td>${row.time}</td>
                <td>${row.system}</td>
                <td>${row.symbol}</td>
                <td>${row.side}</td>
                <td>${row.pnl === null ? '--' : (row.pnl >= 0 ? '+' : '') + formatCurrency(row.pnl)}</td>
            </tr>
        `;
    });
    el.activityTableBody.innerHTML = html;
}

// Poll data from backend
async function pollData() {
    try {
        const [tradierRes, blocRes, positionsRes, activityRes, sieRes, snapshotRes] = await Promise.all([
            fetch(`${API_BASE}/api/tradier/status`).then(r => r.json()),
            fetch(`${API_BASE}/api/bloc/status`).then(r => r.json()),
            fetch(`${API_BASE}/api/positions`).then(r => r.json()),
            fetch(`${API_BASE}/api/activity`).then(r => r.json()),
            fetch(`${API_BASE}/api/sie/status`).then(r => r.json()),
            fetch(`${API_BASE}/snapshot.json`).then(r => r.json())
        ]);
        // Merge into state
        if (tradierRes.bp !== undefined) state.tradier.bp = tradierRes.bp;
        if (tradierRes.positions !== undefined) state.tradier.positions = tradierRes.positions;
        if (tradierRes.orders !== undefined) state.tradier.orders = tradierRes.orders;
        if (tradierRes.health !== undefined) state.tradier.health = tradierRes.health;
        
        if (blocRes.usdc !== undefined) state.bloc.usdc = blocRes.usdc;
        if (blocRes.weth !== undefined) state.bloc.weth = blocRes.weth;
        if (blocRes.positions !== undefined) state.bloc.positions = blocRes.positions;
        if (blocRes.health !== undefined) state.bloc.health = blocRes.health;
        
        // SIE status (reality banner)
        if (sieRes && sieRes.order_id !== undefined) {
            el.tradierOrder.textContent = `${sieRes.order_id} (NVDA PUT)`;
            el.ethPrice.textContent = `$${sieRes.eth_price ? sieRes.eth_price.toFixed(2) : '--'}`;
            el.lastMomentum.textContent = `${sieRes.momentum ? (sieRes.momentum * 100).toFixed(3) : '--'}%`;
        }

        // Account summary (for now combine bloc balances)
        state.account.usdc = state.bloc.usdc;
        state.account.weth = state.bloc.weth;
        
        if (positionsRes.positions) state.positions = positionsRes.positions;
        if (activityRes.activity) state.activity = activityRes.activity;
        if (snapshotRes.hq) state.hq = snapshotRes.hq;
        
        renderAll();
    } catch (err) {
        console.error('Poll error:', err);
        // Set health to red
        el.tradierHealth.className = 'health-dot red';
        el.blocHealth.className = 'health-dot red';
    }
}

// Initial render
function renderTruthBoard() {
    const tradier = (state.hq.engine_truth_board || {}).tradier || {};
    const bloc = (state.hq.engine_truth_board || {}).bloc || {};
    el.truthTradierFunded.textContent = String(tradier.funded ?? '--');
    el.truthTradierPathReady.textContent = String(tradier.path_ready ?? '--');
    el.truthTradierEdgeProven.textContent = String(tradier.edge_proven ?? '--');
    el.truthTradierStatus.textContent = tradier.status_label ?? '--';
    el.truthTradierCapital.textContent = tradier.available_capital_usd ?? '--';
    el.truthTradierStage.textContent = tradier.last_lifecycle_stage ?? '--';
    el.truthTradierAttempt.textContent = tradier.last_attempt_status ?? '--';
    el.truthTradierBlocker.textContent = tradier.top_blocker ?? '--';
    el.truthBlocFunded.textContent = String(bloc.funded ?? '--');
    el.truthBlocPathReady.textContent = String(bloc.path_ready ?? '--');
    el.truthBlocEdgeProven.textContent = String(bloc.edge_proven ?? '--');
    el.truthBlocStatus.textContent = bloc.status_label ?? '--';
    el.truthBlocCapital.textContent = bloc.available_capital_usd ?? '--';
    el.truthBlocAttempt.textContent = bloc.last_attempt_status ?? '--';
    el.truthBlocRejection.textContent = bloc.last_rejection_reason ?? '--';
    el.truthBlocSize.textContent = bloc.last_meaningful_attempt_size_usd ?? '--';
    el.truthBlocEdge.textContent = bloc.last_gross_edge_pct ?? '--';
    el.truthBlocFriction.textContent = bloc.last_estimated_friction_pct ?? '--';
}

function renderAll() {
    renderTruthBoard();
    renderAccount();
    renderTradier();
    renderBloc();
    renderPositions();
    renderActivity();
}

// Button actions
el.btnPauseBloc.addEventListener('click', () => {
    fetch(`${API_BASE}/api/command`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: 'pause_bloc' })
    }).then(res => res.json()).then(data => {
        console.log('Pause Bloc:', data);
        alert('Bloc paused');
    }).catch(err => console.error('Command failed:', err));
});

el.btnPauseTradier.addEventListener('click', () => {
    fetch(`${API_BASE}/api/command`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: 'pause_tradier' })
    }).then(res => res.json()).then(data => {
        console.log('Pause Tradier:', data);
        alert('Tradier paused');
    }).catch(err => console.error('Command failed:', err));
});

el.btnCloseAll.addEventListener('click', () => {
    if (confirm('Emergency close ALL positions? This cannot be undone.')) {
        fetch(`${API_BASE}/api/command`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command: 'close_all' })
        }).then(res => res.json()).then(data => {
            console.log('Close all:', data);
            alert('Emergency close initiated');
        }).catch(err => console.error('Command failed:', err));
    }
});

// Start polling
setInterval(pollData, POLL_INTERVAL);
pollData();

// Initial render
renderAll();