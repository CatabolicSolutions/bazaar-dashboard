"""Risk management - daily limits, position tracking, cooldowns"""
import time
from typing import Dict, Optional

DUST_WETH_EPSILON = 1e-12

from config.settings import (
    MAX_POSITION_USD, MAX_DAILY_LOSS_USD, INITIAL_CAPITAL_USD, MAX_DAILY_TRADES
)

class RiskManager:
    def __init__(self):
        self.daily_pnl = 0  # Reset daily
        self.daily_trades = 0
        self.open_positions = {}  # token_pair -> position
        self.last_trade_time = 0
        self.cooldown_seconds = 60  # Minimum time between trades
        self.trade_history = []
        self.max_history = 100
        self.day_start = time.time()
    
    def can_trade(self, signal: Dict) -> tuple[bool, str]:
        """
        Check if we can execute a trade
        Returns (can_trade, reason)
        """
        # Check daily loss limit
        if self.daily_pnl <= -MAX_DAILY_LOSS_USD:
            return False, f"Daily loss limit reached: ${self.daily_pnl:.2f}"
        
        # Check cooldown
        now = time.time()
        time_since_last = now - self.last_trade_time
        if time_since_last < self.cooldown_seconds:
            return False, f"Cooldown active: {self.cooldown_seconds - time_since_last:.0f}s remaining"

        if self.daily_trades >= MAX_DAILY_TRADES:
            return False, f"Max daily trades ({MAX_DAILY_TRADES}) reached"
        
        # Check if we have open position in this pair
        pair = self._get_pair_key(signal)
        try:
            from wallet_monitor import wallet_monitor
            wallet = wallet_monitor.get_all_balances()
            wallet_weth = float(wallet.get('weth') or 0.0)
            wallet_cbbtc = float(wallet.get('cbbtc') or 0.0)
            eth_price = float(wallet.get('eth_price_usd') or 0.0)
            btc_price = float(wallet.get('cbbtc_price_usd', wallet.get('btc_price_usd', 0.0)) or 0.0)
        except Exception:
            wallet = {}
            wallet_weth = 0.0
            wallet_cbbtc = 0.0
            eth_price = 0.0
            btc_price = 0.0
        has_live_inventory = wallet_weth > DUST_WETH_EPSILON or wallet_cbbtc > 1e-8
        if pair in self.open_positions and not has_live_inventory:
            self.open_positions.pop(pair, None)
        if pair in self.open_positions:
            return False, f"Open position exists: {pair}"
        
        # Check capital availability
        used_capital = sum(p.get('size_usd', p.get('size', 0)) for p in self.open_positions.values())
        try:
            available = max(0.0, float(wallet.get('usdc') or 0.0) - used_capital)
            invested = max(0.0, (wallet_weth * eth_price) + (wallet_cbbtc * btc_price))
        except Exception:
            available = INITIAL_CAPITAL_USD - used_capital
            invested = 0.0
        
        if available <= 0 and (invested > 0 or has_live_inventory):
            if invested > 0:
                return False, f"Capital deployed in active inventory: ${invested:.2f} invested"
            return False, "Capital deployed in active inventory"
        if available <= 0:
            return False, f"Insufficient capital: ${available:.2f} available"
        
        return True, "OK"
    
    def record_trade(self, signal: Dict, size_usd: float, paper: bool = True) -> Dict:
        """Record a trade"""
        now = time.time()
        
        position = {
            'timestamp': now,
            'signal': signal,
            'size_usd': size_usd,
            'paper': paper,
            'entry_price': signal['price'],
            'pair': self._get_pair_key(signal)
        }
        
        self.open_positions[position['pair']] = position
        self.last_trade_time = now
        self.daily_trades += 1
        
        self.trade_history.append({
            'type': 'entry',
            'timestamp': now,
            'position': position,
            'paper': paper
        })
        
        return position
    
    def close_position(self, pair: str, exit_price: float, paper: bool = True) -> Optional[Dict]:
        """Close a position and record P&L"""
        if pair not in self.open_positions:
            return None
        
        position = self.open_positions.pop(pair)
        
        # Calculate P&L
        direction = position['signal']['direction']
        entry = position['entry_price']
        
        if direction == 'up':
            # Long position - profit if price went up
            pnl_pct = ((exit_price - entry) / entry) * 100
        else:
            # Short position - profit if price went down
            pnl_pct = ((entry - exit_price) / entry) * 100
        
        pnl_usd = (pnl_pct / 100) * position['size_usd']
        
        self.daily_pnl += pnl_usd
        
        result = {
            'timestamp': time.time(),
            'position': position,
            'exit_price': exit_price,
            'pnl_usd': pnl_usd,
            'pnl_pct': pnl_pct,
            'paper': paper
        }
        
        self.trade_history.append({
            'type': 'exit',
            'timestamp': time.time(),
            'result': result
        })
        
        # Trim history
        if len(self.trade_history) > self.max_history:
            self.trade_history = self.trade_history[-self.max_history:]
        
        return result
    
    def _get_pair_key(self, signal: Dict) -> str:
        """Get unique key for a trading pair"""
        direction = signal['direction']
        symbol = signal.get('symbol', 'ETH')
        return f"{symbol}-USDC-{direction}"
    
    def reset_daily_stats(self):
        """Reset daily statistics (call at day start)"""
        self.daily_pnl = 0
        self.daily_trades = 0
        self.day_start = time.time()
    
    def get_status(self) -> Dict:
        """Get current risk status"""
        used_capital = sum(p.get('size_usd', p.get('size', 0)) for p in self.open_positions.values())
        
        invested_capital = 0.0
        try:
            from wallet_monitor import wallet_monitor
            wallet = wallet_monitor.get_all_balances()
            available_capital = max(0.0, float(wallet.get('usdc') or 0.0) - used_capital)
            invested_capital = max(
                0.0,
                (float(wallet.get('weth') or 0.0) * float(wallet.get('eth_price_usd') or 0.0)) +
                (float(wallet.get('cbbtc') or 0.0) * float(wallet.get('cbbtc_price_usd', wallet.get('btc_price_usd', 0.0)) or 0.0))
            )
        except Exception:
            available_capital = INITIAL_CAPITAL_USD - used_capital

        return {
            'daily_pnl': self.daily_pnl,
            'daily_trades': self.daily_trades,
            'open_positions': len(self.open_positions),
            'used_capital': used_capital,
            'available_capital': available_capital,
            'invested_capital': invested_capital,
            'daily_loss_limit': MAX_DAILY_LOSS_USD,
            'remaining_loss_allowance': MAX_DAILY_LOSS_USD + self.daily_pnl if self.daily_pnl < 0 else MAX_DAILY_LOSS_USD,
            'cooldown_active': time.time() - self.last_trade_time < self.cooldown_seconds
        }

# Global instance
risk_manager = RiskManager()
