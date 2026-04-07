/**
 * ETH Scalper Tab - GitHub Dark Theme
 * Clean, minimal crypto trading interface
 */

class EthScalperTab {
  constructor() {
    this.container = document.getElementById('ethScalperContainer');
    this.refreshInterval = null;
    this.data = {
      status: 'loading',
      pnl: { today: 0, total: 0 },
      trades: [],
      positions: [],
      signals: [],
      wallet: { eth: 0, usdc: 0, gas: 0 },
      requests: { used: 0, limit: 900 }
    };
  }

  async init() {
    if (!this.container) return;
    this.render();
    await this.loadData();
    this.startPolling();
  }

  destroy() {
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
    }
  }

  startPolling() {
    this.refreshInterval = setInterval(() => this.loadData(), 5000);
  }

  async loadData() {
    try {
      const [statusRes, tradesRes, positionsRes, signalsRes, walletRes] = await Promise.all([
        fetch('/api/eth-scalper/status').catch(() => null),
        fetch('/api/eth-scalper/trades').catch(() => null),
        fetch('/api/eth-scalper/positions').catch(() => null),
        fetch('/api/eth-scalper/signals').catch(() => null),
        fetch('/api/eth-scalper/wallet').catch(() => null)
      ]);

      if (statusRes?.ok) {
        const status = await statusRes.json();
        this.data.status = status.status || 'unknown';
        this.data.pnl = status.pnl || { today: 0, total: 0 };
        this.data.requests = status.requests || { used: 0, limit: 900 };
      }

      if (tradesRes?.ok) {
        const trades = await tradesRes.json();
        this.data.trades = trades.trades || [];
      }

      if (positionsRes?.ok) {
        const positions = await positionsRes.json();
        this.data.positions = positions.positions || [];
      }

      if (signalsRes?.ok) {
        const signals = await signalsRes.json();
        this.data.signals = signals.signals || [];
      }

      if (walletRes?.ok) {
        const wallet = await walletRes.json();
        this.data.wallet = wallet;
      }

      this.updateUI();
    } catch (err) {
      console.error('ETH Scalper load error:', err);
    }
  }

  render() {
    if (!this.container) return;

    this.container.innerHTML = `
      <div class="eth-scalper-tab">
        <header class="eth-header">
          <h2>ETH Scalper</h2>
          <span id="eth-status-badge" class="status-badge loading">Loading...</span>
        </header>

        <div class="eth-grid">
          <div class="eth-card pnl-card">
            <h3>Today's P&L</h3>
            <div id="eth-pnl-value" class="pnl-value">$0.00</div>
            <div id="eth-pnl-subtext" class="pnl-subtext">Total: $0.00</div>
          </div>

          <div class="eth-card positions-card">
            <h3>Open Positions</h3>
            <div id="eth-positions-count" class="positions-count">0</div>
            <div class="positions-detail">Max: 2 positions</div>
          </div>

          <div class="eth-card status-card">
            <h3>API Status</h3>
            <div class="status-item">
              <span class="status-label">1inch Requests</span>
              <span id="eth-requests-value" class="status-value">0/900</span>
            </div>
            <div class="status-item">
              <span class="status-label">Daily Trades</span>
              <span id="eth-trades-value" class="status-value">0/20</span>
            </div>
          </div>
        </div>

        <div class="eth-card trades-section">
          <h3>Live Trades</h3>
          <div id="eth-trades-table">
            <div class="eth-empty">
              <div class="eth-empty-icon">📈</div>
              <p>No trades yet. Waiting for signals...</p>
            </div>
          </div>
        </div>

        <div class="eth-card signals-section">
          <h3>Signal Log</h3>
          <div id="eth-signals-log">
            <div class="eth-empty">
              <div class="eth-empty-icon">📡</div>
              <p>No signals detected yet...</p>
            </div>
          </div>
        </div>

        <div class="eth-card wallet-section">
          <h3>Wallet & Gas</h3>
          <div class="wallet-grid">
            <div class="wallet-item">
              <div class="wallet-icon eth">⟠</div>
              <div class="wallet-info">
                <div class="wallet-label">ETH Balance</div>
                <div id="eth-balance" class="wallet-value">0.0000 ETH</div>
              </div>
            </div>
            <div class="wallet-item">
              <div class="wallet-icon usdc">💵</div>
              <div class="wallet-info">
                <div class="wallet-label">USDC Balance</div>
                <div id="usdc-balance" class="wallet-value">$0.00</div>
              </div>
            </div>
            <div class="wallet-item">
              <div class="wallet-icon gas">⛽</div>
              <div class="wallet-info">
                <div class="wallet-label">Gas Price</div>
                <div id="gas-price" class="wallet-value">0.0 gwei</div>
              </div>
            </div>
          </div>
        </div>

        <div class="eth-controls">
          <button class="eth-btn danger" onclick="ethScalperTab.sendCommand('STOP')">
            🛑 STOP BOT
          </button>
          <button class="eth-btn primary" onclick="ethScalperTab.sendCommand('START')">
            ▶️ START BOT
          </button>
          <button class="eth-btn secondary" onclick="ethScalperTab.toggleMode()">
            📝 PAPER MODE
          </button>
          <button class="eth-btn secondary" onclick="ethScalperTab.viewLogs()">
            📄 VIEW LOGS
          </button>
        </div>
      </div>
    `;
  }

  updateUI() {
    // Update status badge
    const statusBadge = document.getElementById('eth-status-badge');
    if (statusBadge) {
      statusBadge.className = `status-badge ${this.data.status}`;
      statusBadge.textContent = this.data.status.toUpperCase();
    }

    // Update P&L
    const pnlValue = document.getElementById('eth-pnl-value');
    const pnlSubtext = document.getElementById('eth-pnl-subtext');
    if (pnlValue) {
      const pnlClass = this.data.pnl.today >= 0 ? 'eth-profit' : 'eth-loss';
      const pnlSign = this.data.pnl.today >= 0 ? '+' : '';
      pnlValue.className = `pnl-value ${pnlClass}`;
      pnlValue.textContent = `${pnlSign}$${this.data.pnl.today.toFixed(2)}`;
    }
    if (pnlSubtext) {
      const totalSign = this.data.pnl.total >= 0 ? '+' : '';
      pnlSubtext.textContent = `Total: ${totalSign}$${this.data.pnl.total.toFixed(2)}`;
    }

    // Update positions
    const positionsCount = document.getElementById('eth-positions-count');
    if (positionsCount) {
      positionsCount.textContent = this.data.positions.length;
    }

    // Update API status
    const requestsValue = document.getElementById('eth-requests-value');
    if (requestsValue) {
      requestsValue.textContent = `${this.data.requests.used}/${this.data.requests.limit}`;
    }

    // Update wallet
    const ethBalance = document.getElementById('eth-balance');
    const usdcBalance = document.getElementById('usdc-balance');
    const gasPrice = document.getElementById('gas-price');

    if (ethBalance) ethBalance.textContent = `${this.data.wallet.eth.toFixed(4)} ETH`;
    if (usdcBalance) usdcBalance.textContent = `$${this.data.wallet.usdc.toFixed(2)}`;
    if (gasPrice) gasPrice.textContent = `${this.data.wallet.gas.toFixed(1)} gwei`;

    // Update trades table
    this.updateTradesTable();

    // Update signals log
    this.updateSignalsLog();
  }

  updateTradesTable() {
    const container = document.getElementById('eth-trades-table');
    if (!container) return;

    if (this.data.trades.length === 0) {
      container.innerHTML = `
        <div class="eth-empty">
          <div class="eth-empty-icon">📈</div>
          <p>No trades yet. Waiting for signals...</p>
        </div>
      `;
      return;
    }

    const trades = this.data.trades.slice(0, 10);
    container.innerHTML = `
      <table class="eth-table">
        <thead>
          <tr>
            <th>Time</th>
            <th>Type</th>
            <th>Entry</th>
            <th>Exit</th>
            <th>P&L</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          ${trades.map(t => this.renderTradeRow(t)).join('')}
        </tbody>
      </table>
    `;
  }

  renderTradeRow(trade) {
    const time = new Date(trade.timestamp || Date.now()).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const pnlClass = (trade.pnl_usd || 0) >= 0 ? 'eth-profit' : 'eth-loss';
    const pnlSign = (trade.pnl_usd || 0) >= 0 ? '+' : '';
    const badgeClass = (trade.pnl_usd || 0) >= 0 ? 'win' : (trade.pnl_usd || 0) < 0 ? 'loss' : 'pending';
    const emoji = (trade.pnl_usd || 0) >= 0 ? '✅' : (trade.pnl_usd || 0) < 0 ? '❌' : '⏳';

    return `
      <tr>
        <td>${time}</td>
        <td>${trade.type || 'ETH→USDC'}</td>
        <td>$${(trade.entry_price || 0).toFixed(2)}</td>
        <td>$${(trade.exit_price || 0).toFixed(2)}</td>
        <td class="${pnlClass}">${pnlSign}$${(trade.pnl_usd || 0).toFixed(2)}</td>
        <td><span class="trade-badge ${badgeClass}">${emoji}</span></td>
      </tr>
    `;
  }

  updateSignalsLog() {
    const container = document.getElementById('eth-signals-log');
    if (!container) return;

    if (this.data.signals.length === 0) {
      container.innerHTML = `
        <div class="eth-empty">
          <div class="eth-empty-icon">📡</div>
          <p>No signals detected yet...</p>
        </div>
      `;
      return;
    }

    const signals = this.data.signals.slice(0, 10);
    container.innerHTML = `
      <table class="eth-table">
        <thead>
          <tr>
            <th>Time</th>
            <th>Signal</th>
            <th>Score</th>
            <th>Action</th>
            <th>Result</th>
          </tr>
        </thead>
        <tbody>
          ${signals.map(s => this.renderSignalRow(s)).join('')}
        </tbody>
      </table>
    `;
  }

  renderSignalRow(signal) {
    const time = new Date(signal.timestamp || Date.now()).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const badgeClass = signal.executed ? 'executed' : 'skipped';
    const badgeText = signal.executed ? 'EXECUTED' : 'SKIPPED';

    return `
      <tr>
        <td>${time}</td>
        <td>${signal.type || 'Momentum'}</td>
        <td><span class="signal-score">${signal.score || 0}/10</span></td>
        <td><span class="signal-badge ${badgeClass}">${badgeText}</span></td>
        <td>${signal.reason || '-'}</td>
      </tr>
    `;
  }

  async sendCommand(command) {
    try {
      const res = await fetch('/api/eth-scalper/command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command })
      });

      if (res.ok) {
        // Refresh immediately
        setTimeout(() => this.loadData(), 500);
      }
    } catch (err) {
      console.error('Command failed:', err);
    }
  }

  toggleMode() {
    // Toggle between paper and live mode
    const newMode = this.data.status === 'paper' ? 'LIVE' : 'PAPER';
    this.sendCommand(newMode);
  }

  viewLogs() {
    // Fetch and display logs
    fetch('/eth-scalper/logs/')
      .then(res => res.text())
      .then(logs => {
        // Create a modal to show logs
        const modal = document.createElement('div');
        modal.style.cssText = `
          position: fixed;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
          background: rgba(0,0,0,0.8);
          z-index: 10000;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 20px;
        `;
        modal.innerHTML = `
          <div style="
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 12px;
            width: 90%;
            max-width: 1200px;
            height: 80%;
            display: flex;
            flex-direction: column;
            overflow: hidden;
          ">
            <div style="
              display: flex;
              justify-content: space-between;
              align-items: center;
              padding: 16px 20px;
              border-bottom: 1px solid #30363d;
            ">
              <h3 style="margin: 0; color: #e6edf3;">ETH Scalper Logs</h3>
              <button onclick="this.closest('.modal').remove()" style="
                background: transparent;
                border: none;
                color: #7d8590;
                font-size: 20px;
                cursor: pointer;
              ">✕</button>
            </div>
            <pre style="
              flex: 1;
              margin: 0;
              padding: 20px;
              overflow: auto;
              color: #e6edf3;
              font-family: 'SF Mono', Monaco, monospace;
              font-size: 12px;
              line-height: 1.5;
              background: #0d1117;
            ">${logs.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</pre>
          </div>
        `;
        modal.className = 'modal';
        document.body.appendChild(modal);
        
        // Close on background click
        modal.addEventListener('click', (e) => {
          if (e.target === modal) modal.remove();
        });
      })
      .catch(err => {
        alert('Failed to load logs: ' + err.message);
      });
  }
}

// Global instance
window.ethScalperTab = new EthScalperTab();
