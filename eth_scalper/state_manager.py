"""State manager - bridges scalper bot and dashboard"""
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

ROOT = Path(__file__).parent
STATE_DIR = ROOT / 'state'
LOGS_DIR = ROOT / 'logs'

# Ensure directories exist
STATE_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

class StateManager:
    """Manages state files for dashboard integration"""
    
    def __init__(self):
        self.bot_state_file = STATE_DIR / 'bot_state.json'
        self.positions_file = STATE_DIR / 'positions.json'
        self.trades_log = LOGS_DIR / 'trades.jsonl'
        self.signals_log = LOGS_DIR / 'signals.jsonl'
    
    def update_bot_state(self, status: str, pnl_today: float, pnl_total: float, 
                         requests_used: int, daily_trades: int, open_positions: int,
                         available_capital: float, mode: str = 'live'):
        """Update bot status for dashboard"""
        state = {
            'status': status,
            'mode': mode,
            'pnl': {
                'today': round(pnl_today, 2),
                'total': round(pnl_total, 2)
            },
            'requests': {
                'used': requests_used,
                'limit': 900
            },
            'daily_trades': daily_trades,
            'open_positions': open_positions,
            'available_capital': round(available_capital, 2),
            'updated_at': datetime.now(timezone.utc).isoformat()
        }
        self.bot_state_file.write_text(json.dumps(state, indent=2))
    
    def log_trade(self, position, exit_price: float, pnl_usd: float, pnl_pct: float, 
                  gas_cost: float, reason: str):
        """Log a completed trade"""
        entry = {
            'type': 'trade',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'data': {
                'id': position.id,
                'direction': position.direction,
                'entry_price': position.entry_price,
                'exit_price': exit_price,
                'size_usd': position.size_usd,
                'pnl_usd': round(pnl_usd, 2),
                'pnl_pct': round(pnl_pct, 2),
                'gas_cost_usd': round(gas_cost, 2),
                'reason': reason,
                'paper': position.paper,
                'tx_hash': position.tx_hash,
                'exit_tx_hash': position.exit_tx_hash
            }
        }
        with open(self.trades_log, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    
    def log_signal(self, signal: Dict, executed: bool, reason: str = ''):
        """Log a signal (whether executed or not)"""
        entry = {
            'type': 'signal',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'data': {
                'direction': signal.get('direction'),
                'price': signal.get('price'),
                'change_60s_pct': signal.get('change_60s_pct'),
                'gas_gwei': signal.get('gas_gwei'),
                'score': signal.get('score'),
                'executed': executed,
                'reason': reason
            }
        }
        with open(self.signals_log, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    
    def update_positions(self, positions: List):
        """Update open positions"""
        state = {
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'positions': []
        }
        for pos in positions:
            state['positions'].append({
                'id': pos.id,
                'direction': pos.direction,
                'entry_price': pos.entry_price,
                'target_price': pos.target_price,
                'stop_price': pos.stop_price,
                'size_usd': pos.size_usd,
                'size': pos.size_usd,
                'status': pos.status.value,
                'entry_time': pos.entry_time,
                'tx_hash': pos.tx_hash,
                'paper': pos.paper
            })
        self.positions_file.write_text(json.dumps(state, indent=2))
    
    def read_command(self) -> Optional[str]:
        """Read command from dashboard"""
        cmd_file = STATE_DIR / 'command.txt'
        if cmd_file.exists():
            command = cmd_file.read_text().strip()
            cmd_file.unlink()  # Clear after reading
            return command
        return None

# Global instance
state_manager = StateManager()
