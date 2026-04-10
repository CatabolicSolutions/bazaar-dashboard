/**
 * ETH Scalper Tab - Enhanced Trading Interface
 * Real-time trading with manual execution controls
 */

class EthScalperTab {
  constructor() {
    this.container = document.getElementById('ethScalperContainer');
    this.refreshInterval = null;
    this.data = {
      status: 'loading',
      mode: 'unknown',
      pnl: { today: 0, total: 0 },
      trades: [],
      positions: [],
      signals: [],
      wallet: { eth: 0, usdc: 0, gas: 0, address: '' },
      requests: { used: 0, limit: 900 },
      daily_trades: 0,
      open_positions: 0,
      available_capital: 0
    };
    this.lastUpdate = null;
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
    this.refreshInterval = setInterval(() => this.loadData(), 3000); // Poll every 3s
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
        this.data.mode = status.mode || 'unknown';
        this.data.pnl = status.pnl || { today: 0, total: 0 };
        this.data.requests = status.requests || { used: 0, limit: 900 };
        this.data.daily_trades = status.daily_trades || 0;
        this.data.open_positions = status.open_positions || 0;
        this.data.available_capital = status.available_capital || 0;
        this.lastUpdate = status.updated_at;
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
        <!-- HEADER -->
        <header class="eth-header">
          <div class="eth-title">
            <h2>⟠ ETH Scalper</h2>
            <span id="eth-mode-badge" class="mode-badge">Loading...</span>
          </div>
          <div class="eth-status">
            <span id="eth-status-indicator" class="status-indicator"></span>
            <span id="eth-status-text">Connecting...</span>
          </div>
        </header>

        <!-- PRIMARY ACTION BAR -->
        <div class="eth-action-bar">
          <button id="eth-buy-btn" class="eth-btn-buy" onclick="ethScalperTab.confirmBuy()">
            <span class="btn-icon">🚀</span>
            <span class="btn-text">BUY ETH NOW</span>
            <span class="btn-sub">Execute 0.02 ETH swap</span>
          </button>
          
          <div class="eth-quick-stats">
            <div class="quick-stat">
              <span class="stat-label">ETH Price</span>
              <span id="eth-price-display" class="stat-value">--</span>
            </div>
            <div class="quick-stat">
              <span class="stat-label">Gas</span>
              <span id="eth-gas-display" class="stat-value">-- gwei</span>
            </div>
            <div class="quick-stat">
              <span class="stat-label">Daily Trades</span>
              <span id="eth-trades-display" class="stat-value">--</span>
            </div>
          </div>
        </div>

        <!-- MAIN GRID -->
        <div class="eth-grid">
          <!-- P&L CARD -->
          <div class="eth-card pnl-card">
            <div class="card-header">
              <h3>💰 P&L</h3>
              <span class="card-badge" id="pnl-badge">Today</span>
            </div>
            <div id="eth-pnl-value" class="pnl-value">$0.00</div>
            <div class="pnl-breakdown">
              <div class="pnl-row">
                <span>Total</span>
                <span id="eth-pnl-total">$0.00</span>
              </div>
              <div class="pnl-row">
                <span>Available</span>
                <span id="eth-available">$0.00</span>
              </div>
            </div>
          </div>

          <!-- POSITIONS CARD -->
          <div class="eth-card positions-card">
            <div class="card-header">
              <h3>🎯 Positions</h3>
              <span class="card-badge live" id="positions-badge">0 Open</span>
            </div>
            <div id="eth-positions-list" class="positions-list">
              <div class="empty-state">No open positions</div>
            </div>
          </div>

          <!-- WALLET CARD -->
          <div class="eth-card wallet-card">
            <div class="card-header">
              <h3>💳 Wallet</h3>
              <span class="card-badge" id="wallet-address">--</span>
            </div>
            <div class="wallet-balances">
              <div class="balance-item">
                <span class="balance-icon">⟠</span>
                <div class="balance-info">
                  <span class="balance-label">ETH</span>
                  <span id="eth-balance" class="balance-value">0.0000</span>
                </div>
              </div>
              <div class="balance-item">
                <span class="balance-icon">💵</span>
                <div class="balance-info">
                  <span class="balance-label">USDC</span>
                  <span id="usdc-balance" class="balance-value">$0.00</span>
                </div>
              </div>
              <div class="balance-item">
                <span class="balance-icon">⛽</span>
                <div class="balance-info">
                  <span class="balance-label">Gas</span>
                  <span id="gas-price" class="balance-value">-- gwei</span>
                </div>
              </div>
            </div>
          </div>

          <!-- API STATUS CARD -->
          <div class="eth-card api-card">
            <div class="card-header">
              <h3>🔌 API</h3>
              <span class="card-badge" id="api-status">Active</span>
            </div>
            <div class="api-stats">
              <div class="api-stat">
                <span class="api-label">1inch Calls</span>
                <div class="api-bar">
                  <div id="api-bar-fill" class="api-bar-fill" style="width: 0%"></div>
                </div>
                <span id="api-calls" class="api-value">0/900</span>
              </div>
              <div class="api-stat">
                <span class="api-label">Last Update</span>
                <span id="last-update" class="api-value">--</span>
              </div>
            </div>
          </div>
        </div>

        <!-- AUTONOMOUS STATUS DASHBOARD -->
        <div class="eth-autonomous-status">
          <div class="eth-card autonomous-card">
            <div class="card-header">
              <h3>🤖 Autonomous Agents</h3>
              <span class="card-badge live">LIVE</span>
            </div>
            <div class="autonomous-grid">
              <div class="agent-status">
                <div class="agent-icon">⟠</div>
                <div class="agent-info">
                  <span class="agent-name">ETH Scalper</span>
                  <span id="eth-agent-status" class="agent-state">Checking...</span>
                </div>
                <div id="eth-agent-dot" class="agent-dot"></div>
              </div>
              <div class="agent-status">
                <div class="agent-icon">📈</div>
                <div class="agent-info">
                  <span class="agent-name">Tradier Bot</span>
                  <span id="tradier-agent-status" class="agent-state">Checking...</span>
                </div>
                <div id="tradier-agent-dot" class="agent-dot"></div>
              </div>
            </div>
          </div>
        </div>

        <!-- RISK GAUGE -->
        <div class="eth-risk-section">
          <div class="eth-card risk-card">
            <div class="card-header">
              <h3>⚠️ Risk Monitor</h3>
              <span id="risk-badge" class="card-badge">SAFE</span>
            </div>
            <div class="risk-gauges">
              <div class="risk-gauge">
                <span class="gauge-label">Exposure</span>
                <div class="gauge-bar">
                  <div id="exposure-fill" class="gauge-fill" style="width: 0%"></div>
                </div>
                <span id="exposure-value" class="gauge-value">0%</span>
              </div>
              <div class="risk-gauge">
                <span class="gauge-label">Daily Loss</span>
                <div class="gauge-bar">
                  <div id="daily-loss-fill" class="gauge-fill" style="width: 0%"></div>
                </div>
                <span id="daily-loss-value" class="gauge-value">$0/$15</span>
              </div>
              <div class="risk-gauge">
                <span class="gauge-label">Position Heat</span>
                <div class="gauge-bar">
                  <div id="heat-fill" class="gauge-fill" style="width: 0%"></div>
                </div>
                <span id="heat-value" class="gauge-value">0/2</span>
              </div>
            </div>
          </div>
        </div>

        <!-- ACTIVITY SECTIONS -->
        <div class="eth-activity">
          <!-- TRADES -->
          <div class="eth-card activity-card">
            <div class="card-header">
              <h3>📈 Recent Trades</h3>
              <span class="card-badge">Last 10</span>
            </div>
            <div id="eth-trades-table" class="activity-table">
              <div class="empty-state">
                <div class="empty-icon">📊</div>
                <p>No trades executed yet</p>
                <p class="empty-sub">Click "BUY ETH NOW" to make your first trade</p>
              </div>
            </div>
          </div>

          <!-- SIGNALS -->
          <div class="eth-card activity-card">
            <div class="card-header">
              <h3>📡 Signal Log</h3>
              <span class="card-badge">Last 10</span>
            </div>
            <div id="eth-signals-log" class="activity-table">
              <div class="empty-state">
                <div class="empty-icon">📡</div>
                <p>No signals detected</p>
                <p class="empty-sub">Bot is monitoring for momentum...</p>
              </div>
            </div>
          </div>
        </div>

        <!-- CONTROLS -->
        <div class="eth-controls">
          <button class="eth-btn secondary" onclick="ethScalperTab.sendCommand('PAUSE')">
            ⏸️ Pause
          </button>
          <button class="eth-btn secondary" onclick="ethScalperTab.sendCommand('RESUME')">
            ▶️ Resume
          </button>
          <button class="eth-btn secondary" onclick="ethScalperTab.viewLogs()">
            📄 Logs
          </button>
          <button class="eth-btn danger" onclick="ethScalperTab.sendCommand('STOP')">
            🛑 Stop Bot
          </button>
        </div>
      </div>
    `;
  }

  updateUI() {
    // Mode badge
    const modeBadge = document.getElementById('eth-mode-badge');
    if (modeBadge) {
      const modeText = this.data.mode.toUpperCase();
      modeBadge.className = `mode-badge ${this.data.mode}`;
      modeBadge.textContent = modeText;
    }

    // P&L PULSE - Visual heartbeat based on performance
    const pnlValue = document.getElementById('eth-pnl-value');
    if (pnlValue) {
      const pnl = this.data.pnl.today;
      const pnlClass = pnl >= 0 ? 'positive' : 'negative';
      const pnlSign = pnl >= 0 ? '+' : '';
      pnlValue.className = `pnl-value ${pnlClass}`;
      pnlValue.textContent = `${pnlSign}$${pnl.toFixed(2)}`;
      
      // Add pulse animation based on magnitude
      const intensity = Math.min(Math.abs(pnl) / 50, 1); // Max pulse at $50
      if (intensity > 0.1) {
        pnlValue.style.animation = `pulse ${1 - intensity * 0.5}s ease-in-out infinite`;
        pnlValue.style.textShadow = pnl >= 0 
          ? `0 0 ${intensity * 20}px rgba(34, 197, 94, ${intensity})`
          : `0 0 ${intensity * 20}px rgba(239, 68, 68, ${intensity})`;
      } else {
        pnlValue.style.animation = 'none';
        pnlValue.style.textShadow = 'none';
      }
    }

    // Status indicator
    const statusIndicator = document.getElementById('eth-status-indicator');
    const statusText = document.getElementById('eth-status-text');
    if (statusIndicator && statusText) {
      const isRunning = this.data.status === 'running';
      statusIndicator.className = `status-indicator ${isRunning ? 'active' : 'inactive'}`;
      statusText.textContent = isRunning ? 'RUNNING' : this.data.status.toUpperCase();
    }

    // Quick stats
    const priceDisplay = document.getElementById('eth-price-display');
    const gasDisplay = document.getElementById('eth-gas-display');
    const tradesDisplay = document.getElementById('eth-trades-display');
    
    if (priceDisplay) {
      // Calculate ETH price from wallet data
      // estimated_total_usd = (ETH * price) + USDC
      // So: price = (estimated_total_usd - USDC) / ETH
      const totalUsd = this.data.wallet.estimated_total_usd || 0;
      const usdc = this.data.wallet.usdc || 0;
      const eth = this.data.wallet.eth || 0;
      let ethUsd = 2500; // Default fallback
      
      if (eth > 0 && totalUsd > usdc) {
        ethUsd = (totalUsd - usdc) / eth;
      }
      
      // Sanity check - ETH should be between $1000 and $10000
      if (ethUsd < 1000 || ethUsd > 10000) {
        ethUsd = 2500; // Fallback to reasonable estimate
      }
      
      priceDisplay.textContent = `$${ethUsd.toFixed(2)}`;
    }
    if (gasDisplay) gasDisplay.textContent = `${this.data.wallet.gas.toFixed(1)} gwei`;
    if (tradesDisplay) tradesDisplay.textContent = this.data.daily_trades;

    // P&L Total and Available (already handled above with pulse effect)
    const pnlTotal = document.getElementById('eth-pnl-total');
    const pnlAvailable = document.getElementById('eth-available');
    const pnlBadge = document.getElementById('pnl-badge');
    
    if (pnlTotal) {
      const totalSign = this.data.pnl.total >= 0 ? '+' : '';
      pnlTotal.textContent = `${totalSign}$${this.data.pnl.total.toFixed(2)}`;
    }
    if (pnlAvailable) pnlAvailable.textContent = `$${this.data.available_capital.toFixed(2)}`;
    if (pnlBadge) pnlBadge.textContent = `Today (${this.data.daily_trades} trades)`;

    // Positions
    const positionsList = document.getElementById('eth-positions-list');
    const positionsBadge = document.getElementById('positions-badge');
    
    if (positionsBadge) {
      positionsBadge.textContent = `${this.data.open_positions} Open`;
      positionsBadge.className = `card-badge ${this.data.open_positions > 0 ? 'live' : ''}`;
    }
    
    if (positionsList) {
      if (this.data.positions.length === 0) {
        positionsList.innerHTML = '<div class="empty-state">No open positions</div>';
      } else {
        positionsList.innerHTML = this.data.positions.map(p => this.renderPosition(p)).join('');
      }
    }

    // Wallet
    const ethBalance = document.getElementById('eth-balance');
    const usdcBalance = document.getElementById('usdc-balance');
    const gasPrice = document.getElementById('gas-price');
    const walletAddress = document.getElementById('wallet-address');
    
    if (ethBalance) ethBalance.textContent = this.data.wallet.eth.toFixed(4);
    if (usdcBalance) usdcBalance.textContent = `$${this.data.wallet.usdc.toFixed(2)}`;
    if (gasPrice) gasPrice.textContent = `${this.data.wallet.gas.toFixed(1)} gwei`;
    if (walletAddress && this.data.wallet.address) {
      walletAddress.textContent = `${this.data.wallet.address.slice(0, 6)}...${this.data.wallet.address.slice(-4)}`;
    }

    // API stats
    const apiBarFill = document.getElementById('api-bar-fill');
    const apiCalls = document.getElementById('api-calls');
    const lastUpdate = document.getElementById('last-update');
    
    if (apiBarFill) {
      const pct = (this.data.requests.used / this.data.requests.limit) * 100;
      apiBarFill.style.width = `${Math.min(pct, 100)}%`;
    }
    if (apiCalls) apiCalls.textContent = `${this.data.requests.used}/${this.data.requests.limit}`;
    if (lastUpdate && this.lastUpdate) {
      const date = new Date(this.lastUpdate);
      lastUpdate.textContent = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }

    // AUTONOMOUS STATUS DASHBOARD
    const ethAgentStatus = document.getElementById('eth-agent-status');
    const ethAgentDot = document.getElementById('eth-agent-dot');
    if (ethAgentStatus && ethAgentDot) {
      const isRunning = this.data.status === 'running';
      ethAgentStatus.textContent = isRunning ? 'RUNNING' : 'PAUSED';
      ethAgentDot.className = `agent-dot ${isRunning ? 'active' : 'inactive'}`;
    }
    
    // Fetch Tradier agent status
    this.updateTradierStatus();

    // RISK GAUGE
    this.updateRiskGauge();

    // Tables
    this.updateTradesTable();
    this.updateSignalsLog();
  }

  renderPosition(pos) {
    const directionEmoji = pos.direction === 'long' ? '📈' : '📉';
    const targetPct = ((pos.target_price / pos.entry_price) - 1) * 100;
    const stopPct = ((1 - pos.stop_price / pos.entry_price)) * 100;
    
    return `
      <div class="position-item">
        <div class="position-header">
          <span class="position-direction">${directionEmoji} ${pos.direction.toUpperCase()}</span>
          <span class="position-status ${pos.status}">${pos.status.toUpperCase()}</span>
        </div>
        <div class="position-details">
          <div class="position-row">
            <span>Entry: $${pos.entry_price.toFixed(2)}</span>
            <span>Size: $${pos.size_usd.toFixed(2)}</span>
          </div>
          <div class="position-row targets">
            <span class="target">🎯 +${targetPct.toFixed(2)}%</span>
            <span class="stop">🛑 -${stopPct.toFixed(2)}%</span>
          </div>
        </div>
        ${pos.tx_hash ? `<a href="https://etherscan.io/tx/${pos.tx_hash}" target="_blank" class="tx-link">View Tx ↗</a>` : ''}
      </div>
    `;
  }

  updateTradesTable() {
    const container = document.getElementById('eth-trades-table');
    if (!container) return;

    if (this.data.trades.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">📊</div>
          <p>No trades executed yet</p>
          <p class="empty-sub">Click "BUY ETH NOW" to make your first trade</p>
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
            <th>Dir</th>
            <th>Entry</th>
            <th>Exit</th>
            <th>P&L</th>
            <th>Tx</th>
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
    const pnlClass = (trade.pnl_usd || 0) >= 0 ? 'positive' : 'negative';
    const pnlSign = (trade.pnl_usd || 0) >= 0 ? '+' : '';
    const directionEmoji = trade.direction === 'long' ? '📈' : '📉';
    const txLink = trade.tx_hash ? `<a href="https://etherscan.io/tx/${trade.tx_hash}" target="_blank">↗</a>` : '-';

    return `
      <tr>
        <td>${time}</td>
        <td>${directionEmoji}</td>
        <td>$${(trade.entry_price || 0).toFixed(2)}</td>
        <td>$${(trade.exit_price || 0).toFixed(2)}</td>
        <td class="${pnlClass}">${pnlSign}$${(trade.pnl_usd || 0).toFixed(2)}</td>
        <td>${txLink}</td>
      </tr>
    `;
  }

  updateSignalsLog() {
    const container = document.getElementById('eth-signals-log');
    if (!container) return;

    if (this.data.signals.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">📡</div>
          <p>No signals detected</p>
          <p class="empty-sub">Bot is monitoring for momentum...</p>
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
            <th>Dir</th>
            <th>Price</th>
            <th>Score</th>
            <th>Action</th>
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
    const directionEmoji = signal.direction === 'up' ? '📈' : '📉';
    const badgeClass = signal.executed ? 'executed' : 'skipped';
    const badgeText = signal.executed ? 'TRADED' : 'SKIPPED';

    return `
      <tr>
        <td>${time}</td>
        <td>${directionEmoji}</td>
        <td>$${(signal.price || 0).toFixed(2)}</td>
        <td>${signal.score || 0}/10</td>
        <td><span class="signal-badge ${badgeClass}">${badgeText}</span></td>
      </tr>
    `;
  }

  async updateTradierStatus() {
    try {
      const response = await fetch('/api/tradier/status').catch(() => null);
      const tradierAgentStatus = document.getElementById('tradier-agent-status');
      const tradierAgentDot = document.getElementById('tradier-agent-dot');
      
      if (tradierAgentStatus && tradierAgentDot) {
        if (response?.ok) {
          const data = await response.json();
          const isRunning = data.status === 'running';
          tradierAgentStatus.textContent = isRunning ? 'RUNNING' : 'WAITING';
          tradierAgentDot.className = `agent-dot ${isRunning ? 'active' : 'waiting'}`;
        } else {
          tradierAgentStatus.textContent = 'STANDBY';
          tradierAgentDot.className = 'agent-dot standby';
        }
      }
    } catch (e) {
      // Silent fail - will retry next poll
    }
  }

  updateRiskGauge() {
    // Calculate exposure (position size / total capital)
    const totalCapital = this.data.wallet.eth * 2500 + this.data.wallet.usdc; // Approximate
    const positionValue = this.data.open_positions * 50; // Approx $50 per position
    const exposurePct = totalCapital > 0 ? (positionValue / totalCapital) * 100 : 0;
    
    // Daily loss (approximate from P&L)
    const dailyLoss = Math.abs(Math.min(0, this.data.pnl.today));
    const maxDailyLoss = 15;
    const lossPct = (dailyLoss / maxDailyLoss) * 100;
    
    // Position heat
    const maxPositions = 2;
    const heatPct = (this.data.open_positions / maxPositions) * 100;
    
    // Update exposure gauge
    const exposureFill = document.getElementById('exposure-fill');
    const exposureValue = document.getElementById('exposure-value');
    if (exposureFill && exposureValue) {
      exposureFill.style.width = `${Math.min(exposurePct, 100)}%`;
      exposureFill.className = `gauge-fill ${exposurePct > 80 ? 'high' : exposurePct > 50 ? 'medium' : 'low'}`;
      exposureValue.textContent = `${exposurePct.toFixed(0)}%`;
    }
    
    // Update daily loss gauge
    const lossFill = document.getElementById('daily-loss-fill');
    const lossValue = document.getElementById('daily-loss-value');
    if (lossFill && lossValue) {
      lossFill.style.width = `${Math.min(lossPct, 100)}%`;
      lossFill.className = `gauge-fill ${lossPct > 80 ? 'high' : lossPct > 50 ? 'medium' : 'low'}`;
      lossValue.textContent = `$${dailyLoss.toFixed(0)}/$${maxDailyLoss}`;
    }
    
    // Update heat gauge
    const heatFill = document.getElementById('heat-fill');
    const heatValue = document.getElementById('heat-value');
    if (heatFill && heatValue) {
      heatFill.style.width = `${heatPct}%`;
      heatFill.className = `gauge-fill ${heatPct >= 100 ? 'high' : heatPct > 50 ? 'medium' : 'low'}`;
      heatValue.textContent = `${this.data.open_positions}/${maxPositions}`;
    }
    
    // Update overall risk badge
    const riskBadge = document.getElementById('risk-badge');
    if (riskBadge) {
      const overallRisk = Math.max(exposurePct, lossPct, heatPct);
      if (overallRisk >= 80) {
        riskBadge.textContent = 'ELEVATED';
        riskBadge.className = 'card-badge danger';
      } else if (overallRisk >= 50) {
        riskBadge.textContent = 'MODERATE';
        riskBadge.className = 'card-badge warning';
      } else {
        riskBadge.textContent = 'SAFE';
        riskBadge.className = 'card-badge safe';
      }
    }
  }

  confirmBuy() {
    const modal = document.createElement('div');
    modal.className = 'eth-modal';
    modal.innerHTML = `
      <div class="eth-modal-content">
        <div class="eth-modal-header">
          <h3>🚀 Confirm Purchase</h3>
          <button class="close-btn" onclick="this.closest('.eth-modal').remove()">×</button>
        </div>
        <div class="eth-modal-body">
          <div class="confirm-details">
            <div class="confirm-row">
              <span>Action:</span>
              <strong>Buy 0.02 ETH</strong>
            </div>
            <div class="confirm-row">
              <span>Approximate Value:</span>
              <strong>~$50 USD</strong>
            </div>
            <div class="confirm-row">
              <span>Gas Estimate:</span>
              <strong>$2-5</strong>
            </div>
            <div class="confirm-row">
              <span>Mode:</span>
              <strong>${this.data.mode.toUpperCase()}</strong>
            </div>
          </div>
          <p class="confirm-warning">
            ${this.data.mode === 'live' 
              ? '⚠️ This will execute a REAL transaction on Ethereum mainnet.' 
              : '📝 This is a paper trade - no real money will be spent.'}
          </p>
        </div>
        <div class="eth-modal-footer">
          <button class="eth-btn secondary" onclick="this.closest('.eth-modal').remove()">Cancel</button>
          <button class="eth-btn primary" onclick="ethScalperTab.executeBuy(); this.closest('.eth-modal').remove()">
            ${this.data.mode === 'live' ? '💰 EXECUTE LIVE TRADE' : '📝 EXECUTE PAPER TRADE'}
          </button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
  }

  async executeBuy() {
    const btn = document.getElementById('eth-buy-btn');
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span class="btn-icon">⏳</span><span class="btn-text">EXECUTING...</span>';
    }

    try {
      const res = await fetch('/api/eth-scalper/command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: 'BUY' })
      });

      if (res.ok) {
        this.showToast('✅ Buy order sent to bot', 'success');
        setTimeout(() => this.loadData(), 1000);
      } else {
        this.showToast('❌ Failed to send buy order', 'error');
      }
    } catch (err) {
      console.error('Buy failed:', err);
      this.showToast('❌ Network error', 'error');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<span class="btn-icon">🚀</span><span class="btn-text">BUY ETH NOW</span><span class="btn-sub">Execute 0.02 ETH swap</span>';
      }
    }
  }

  showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `eth-toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
  }

  async sendCommand(command) {
    try {
      const res = await fetch('/api/eth-scalper/command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command })
      });

      if (res.ok) {
        this.showToast(`✅ Command sent: ${command}`, 'success');
        setTimeout(() => this.loadData(), 500);
      } else {
        this.showToast('❌ Command failed', 'error');
      }
    } catch (err) {
      console.error('Command failed:', err);
      this.showToast('❌ Network error', 'error');
    }
  }

  viewLogs() {
    window.open('/eth-scalper/logs/', '_blank');
  }
}

// Global instance
window.ethScalperTab = new EthScalperTab();
