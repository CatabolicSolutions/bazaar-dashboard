// Real‑time display of open positions, P&L, system health
// Poll /api/tradier/status and /api/bloc/status

function fetchTradierStatus() {
    fetch('/api/tradier/status')
        .then(response => response.json())
        .then(data => {
            console.log('Tradier status:', data);
            updateTradierWidget(data);
        })
        .catch(err => console.error('Failed to fetch Tradier status:', err));
}

function fetchBlocStatus() {
    fetch('/api/bloc/status')
        .then(response => response.json())
        .then(data => {
            console.log('Bloc status:', data);
            updateBlocWidget(data);
        })
        .catch(err => console.error('Failed to fetch Bloc status:', err));
}

function updateTradierWidget(data) {
    const container = document.getElementById('tradier-status');
    if (!container) return;
    let html = '<h3>Tradier</h3>';
    if (data.open_positions) {
        html += `<p>Open positions: ${data.open_positions.length}</p>`;
        data.open_positions.forEach(pos => {
            html += `<div>${pos.symbol} ${pos.side} ${pos.quantity} @ ${pos.price}</div>`;
        });
    } else {
        html += `<p>No open positions</p>`;
    }
    container.innerHTML = html;
}

function updateBlocWidget(data) {
    const container = document.getElementById('bloc-status');
    if (!container) return;
    let html = '<h3>Bloc</h3>';
    if (data.open_positions) {
        html += `<p>Open positions: ${data.open_positions.length}</p>`;
        data.open_positions.forEach(pos => {
            html += `<div>${pos.symbol} ${pos.side} ${pos.quantity} @ ${pos.price}</div>`;
        });
    } else {
        html += `<p>No open positions</p>`;
    }
    container.innerHTML = html;
}

// Poll every 30 seconds
setInterval(fetchTradierStatus, 30000);
setInterval(fetchBlocStatus, 30000);

// Initial fetch
fetchTradierStatus();
fetchBlocStatus();