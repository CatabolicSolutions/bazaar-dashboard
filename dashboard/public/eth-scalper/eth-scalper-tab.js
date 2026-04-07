/**
 * ETH Scalper Tab - Crypto Native Dashboard
 * Completely separate from Tradier stock trading interface
 */

class ETHScalperTab {
  constructor() {
    this.data = {
      status: 'loading',
      pnl: { today: 0, total: 0 },
      trades: [],
      positions: [],
      signals: [],
      wallet: { eth: 0, usdc: 0, gas: 0 },
      requests: { used: 0, limit: 900 }
    };
    this.refreshInterval = null;
  }

  init() {
    this.render();
    this.startAutoRefresh();
    this.fetchData();
  }

  destroy() {
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
    }
  }

  startAutoRefresh() {
    this.refreshInterval = setInterval(() => this.fetchData(), 5000); // 5 seconds
  }

  async fetchData() {
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

      this.render();
    } catch (err) {
      console.error('ETH Scalper fetch error:', err);
      this.data.status = 'error';
      this.render();
    }
  }

  async sendCommand(command) {
    try {
      const res = await fetch('/api/eth-scalper/command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command })
      });
      
      if (res.ok) {
        this.fetchData(); // Refresh immediately
      }
    } catch (err) {
      console.error('Command failed:', err);
      alert('Command failed: ' + err.message);
    }
  }

  render() {
    const container = document.getElementById('ethScalperContainer');
    if (!container) return;

    container.innerHTML = `
      <div class="eth-scalper-tab">
        ${this.renderHeader()}
        ${this.renderCards()}
        ${this.renderTradesTable()}
        ${this.renderSignalsLog()}
        ${this.renderWalletPanel()}
        ${this.renderControls()}
      </div>
    `;
  }

  renderHeader() {
    const statusClass = this.data.status === 'active' ? 'active' : 
                       this.data.status === 'paused' ? 'paused' : 'stopped';
    
    return `
      <div class="eth-header">
        <h1 class="eth-title">⚡ ETH SCALPER</h1>
        <p class="eth-subtitle">Live Monitoring & Execution</p>
        <div style="margin-top: 16px;">
          <span class="eth-status ${statusClass}">
            <span class="status-dot"></span>
            ${this.data.status.toUpperCase()}
          </span>
        </div>
      </div>
    `;
  }

  renderCards() {
    const pnlClass = this.data.pnl.today >= 0 ? 'positive' : 'negative';
    const pnlSign = this.data.pnl.today >= 0 ? '+' : '';
    
    return `
      <div class="eth-cards">
        <div class="eth-card">
          <div class="eth-card-header">
            <span class="eth-card-label">Today's P&L</span>
            <span class="eth-card-icon">💰</span>
          </div>
          <div class="eth-card-value ${pnlClass}">${pnlSign}$${this.data.pnl.today.toFixed(2)}</div>
          <div class="eth-card-subtext">Total: ${this.data.pnl.total >= 0 ? '+' : ''}$${this.data.pnl.total.toFixed(2)}</div>
        </div>

        <div class="eth-card">
          <div class="eth-card-header">
            <span class="eth-card-label">Open Positions</span>
            <span class="eth-card-icon">📊</span>
          </div>
          <div class="eth-card-value">${this.data.positions.length}</div>
          <div class="eth-card-subtext">Max: 2 positions</div>
        </div>

        <div class="eth-card">
          <div class="eth-card-header">
            <span class="eth-card-label">1inch Requests</span>
            <span class="eth-card-icon">🔄</span>
          </div>
          <div class="eth-card-value">${this.data.requests.used}</div>
          <div class="eth-card-subtext">Limit: ${this.data.requests.limit}/day</div>
        </div>
      </div>
    `;
  }

  renderTradesTable() {
    const trades = this.data.trades.slice(0, 10); // Last 10 trades
    
    if (trades.length === 0) {
      return `
        <div class="eth-section">
          <div class="eth-section-header">
            <h3 class="eth-section-title">Live Trades</h3>
          </div>
          <div class="eth-empty">
            <div class="eth-empty-icon">📈</div>
            <p>No trades yet. Waiting for signals...</p>
          </div>
        </div>
      `;
    }

    return `
      <div class="eth-section">
        <div class="eth-section-header">
          <h3 class="eth-section-title">Live Trades</h3>
        </div>
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
            ${trades.map(trade => this.renderTradeRow(trade)).join('')}
          </tbody>
        </table>
      </div>
    `;
  }

  renderTradeRow(trade) {
    const time = new Date(trade.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const pnlClass = trade.pnl_usd >= 0 ? 'positive' : 'negative';
    const pnlSign = trade.pnl_usd >= 0 ? '+' : '';
    const statusClass = trade.pnl_usd >= 0 ? 'win' : trade.pnl_usd < 0 ? 'loss' : 'pending';
    const statusEmoji = trade.pnl_usd >= 0 ? '✅' : trade.pnl_usd < 0 ? '❌' : '⏳';
    
    return `
      <tr>
        <td>${time}</td>
        <td>${trade.type || 'ETH→USDC'}</td>
        <td>$${trade.entry_price?.toFixed(2) || '--'}</td>
        <td>$${trade.exit_price?.toFixed(2) || '--'}</td>
        <td class="${pnlClass}">${pnlSign}$${trade.pnl_usd?.toFixed(2) || '0.00'}</td>
        <td><span class="trade-status ${statusClass}">${statusEmoji} ${trade.status || 'Closed'}</span></td>
      </tr>
    `;
  }

  renderSignalsLog() {
    const signals = this.data.signals.slice(0, 10); // Last 10 signals
    
    if (signals.length === 0) {
      return `
        <div class="eth-section">
          <div class="eth-section-header">
            <h3 class="eth-section-title">Signal Log</h3>
          </div>
          <div class="eth-empty">
            <div class="eth-empty-icon">📡</div>
            <p>No signals detected yet...</p>
          </div>
        </div>
      `;
    }

    return `
      <div class="eth-section">
        <div class="eth-section-header">
          <h3 class="eth-section-title">Signal Log (Last 10)</h3>
        </div>
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
            ${signals.map(signal => this.renderSignalRow(signal)).join('')}
          </tbody>
        </table>
      </div>
    `;
  }

  renderSignalRow(signal) {
    const time = new Date(signal.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const actionClass = signal.executed ? 'executed' : 'skipped';
    const actionText = signal.executed ? 'EXECUTED' : 'SKIPPED';
    
    return `
      <tr>
        <td>${time}</td>
        <td>${signal.type || 'Momentum'}</td>
        <td><span class="signal-score">${signal.score}/10</span></td>
        <td><span class="signal-badge ${actionClass}">${actionText}</span></td>
        <td>${signal.reason || (signal.executed ? 'Pending' : '-')}</td>
      </tr>
    `;
  }

  renderWalletPanel() {
    return `
      <div class="eth-section">
        <div class="eth-section-header">
          <h3 class="eth-section-title">Wallet & Gas</h3>
        </div>
        <div class="eth-wallet">
          <div class="wallet-item">
            <div class="wallet-icon eth">⟠</div>
            <div class="wallet-info">
              <div class="wallet-label">ETH Balance</div>
              <div class="wallet-value">${this.data.wallet.eth.toFixed(4)} ETH</div>
            </div>
          </div>
          <div class="wallet-item">
            <div class="wallet-icon usdc">💵</div>
            <div class="wallet-info">
              <div class="wallet-label">USDC Balance</div>
              <div class="wallet-value">$${this.data.wallet.usdc.toFixed(2)}</div>
            </div>
          </div>
          <div class="wallet-item">
            <div class="wallet-icon gas">⛽</div>
            <div class="wallet-info">
              <div class="wallet-label">Gas Price</div>
              <div class="wallet-value">${this.data.wallet.gas.toFixed(1)} gwei</div>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  renderControls() {
    const isActive = this.data.status === 'active';
    
    return `
      <div class="eth-controls">
        <button class="eth-btn danger" onclick="ethScalperTab.sendCommand('STOP')">
          🛑 STOP BOT
        </button>
        <button class="eth-btn primary" onclick="ethScalperTab.sendCommand('START')" ${isActive ? 'disabled' : ''}>
          ▶️ START BOT
        </button>
        <button class="eth-btn secondary" onclick="ethScalperTab.sendCommand('PAPER')">
          📝 PAPER MODE
        </button>
        <button class="eth-btn secondary" onclick="ethScalperTab.sendCommand('LIVE')">
          💰 LIVE MODE
        </button>
        <button class="eth-btn secondary" onclick="window.open('/logs/eth-scalper.log', '_blank')">
          📄 VIEW LOGS
        </button>
      </div>
    `;
  }
}

// Global instance
window.ethScalperTab = new ETHScalperTab();
