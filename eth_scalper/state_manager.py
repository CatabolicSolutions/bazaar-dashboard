"""State manager - bridges scalper bot and dashboard"""
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from config.settings import HOLD_TIME_MAX_SECONDS

ROOT = Path(__file__).parent
STATE_DIR = ROOT / 'state'
LOGS_DIR = ROOT / 'logs'
DUST_WETH_EPSILON = 1e-12
MIN_TRADABLE_WETH_UNITS = 1e-6

# Ensure directories exist
STATE_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

class StateManager:
    """Manages state files for dashboard integration"""
    
    def __init__(self):
        self.bot_state_file = STATE_DIR / 'bot_state.json'
        self.positions_file = STATE_DIR / 'positions.json'
        self.persisted_positions_file = STATE_DIR / 'persisted_positions.json'
        self.trades_log = LOGS_DIR / 'trades.jsonl'
        self.signals_log = LOGS_DIR / 'signals.jsonl'
    
    def update_bot_state(self, status: str, pnl_today: float, pnl_total: float, 
                         requests_used: int, daily_trades: int, open_positions: int,
                         available_capital: float, mode: str = 'live', live_inventory: Optional[Dict] = None,
                         reconciled_positions: Optional[List[Dict]] = None, quarantined_summary: Optional[Dict] = None):
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
            'live_inventory': live_inventory or {},
            'reconciled_positions': reconciled_positions or [],
            'quarantined_summary': quarantined_summary or {'count': 0, 'ids': []},
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
        seen_ids = set()
        for pos in positions:
            if getattr(pos, 'id', None) in seen_ids:
                continue
            seen_ids.add(getattr(pos, 'id', None))
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

    def persist_live_position(self, position):
        """Persist durable tracked metadata for live executions."""
        current = []
        if self.persisted_positions_file.exists():
            try:
                current = json.loads(self.persisted_positions_file.read_text()).get('positions', [])
            except Exception:
                current = []
        current = [p for p in current if p.get('id') != position.id]
        lot_units = None
        try:
            executed_to_amount = getattr(position, 'executed_to_amount_units', None)
            if executed_to_amount is not None:
                lot_units = float(executed_to_amount)
            else:
                signal_price = float(position.signal.get('price')) if getattr(position, 'signal', None) else None
                if signal_price and signal_price > 0:
                    lot_units = float(position.size_usd) / signal_price
        except Exception:
            lot_units = None
        bound_symbol = getattr(position, 'bound_symbol', None) or getattr(position, 'asset_symbol', None) or position.signal.get('symbol', 'ETH') if getattr(position, 'signal', None) else 'ETH'
        binding_asset = getattr(position, 'binding_asset', None) or ('CBBTC' if bound_symbol == 'BTC' else 'WETH')
        binding_units = getattr(position, 'binding_units', None)
        if binding_units is None:
            binding_units = lot_units
        current.append({
            'id': position.id,
            'source': getattr(position, 'source', None) or 'autonomous_entry',
            'asset': binding_asset,
            'entry_price': position.entry_price,
            'target_price': position.target_price,
            'stop_price': position.stop_price,
            'max_hold_seconds': getattr(position, 'max_hold_seconds', HOLD_TIME_MAX_SECONDS),
            'size_usd': position.size_usd,
            'lot_units': lot_units,
            'status': position.status.value,
            'entry_time': position.entry_time,
            'tx_hash': position.tx_hash,
            'paper': position.paper,
            'resumable_after_restart': bool(getattr(position, 'resumable_after_restart', False)),
            'binding_asset': binding_asset,
            'binding_units': binding_units,
            'binding_method': 'tx_confirmed_lot_units',
            'entry_derivation': 'tracked_live_execution',
            'target_derivation': 'tracked_live_execution',
            'stop_derivation': 'tracked_live_execution',
            'max_hold_derivation': 'config',
            'updated_at': datetime.now(timezone.utc).isoformat()
        })
        self.persisted_positions_file.write_text(json.dumps({'positions': current, 'updated_at': datetime.now(timezone.utc).isoformat()}, indent=2))

    def mark_position_closed(self, position, exit_price: float, exit_time: float, pnl_usd: float, pnl_pct: float, reason: str):
        """Durably update a persisted tracked lot to closed state after live exit."""
        current = []
        if self.persisted_positions_file.exists():
            try:
                current = json.loads(self.persisted_positions_file.read_text()).get('positions', [])
            except Exception:
                current = []
        updated = []
        for item in current:
            if item.get('id') != position.id:
                updated.append(item)
                continue
            closed_item = dict(item)
            closed_item.update({
                'status': 'closed',
                'exit_tx_hash': getattr(position, 'exit_tx_hash', None),
                'exit_price': exit_price,
                'exit_time': exit_time,
                'pnl_usd': pnl_usd,
                'pnl_pct': pnl_pct,
                'close_reason': reason,
                'resumable_after_restart': False,
                'allocation_state': 'closed',
                'linked_to_wallet_inventory': False,
                'updated_at': datetime.now(timezone.utc).isoformat(),
            })
            updated.append(closed_item)
        self.persisted_positions_file.write_text(json.dumps({'positions': updated, 'updated_at': datetime.now(timezone.utc).isoformat()}, indent=2))

    def load_persisted_positions(self) -> List[Dict]:
        if not self.persisted_positions_file.exists():
            return []
        try:
            return json.loads(self.persisted_positions_file.read_text()).get('positions', [])
        except Exception:
            return []
    
    def update_wallet(self, wallet: Dict):
        """Persist live wallet balances for dashboard/state consumers."""
        wallet_file = STATE_DIR / 'wallet.json'
        state = dict(wallet or {})
        state['updated_at'] = datetime.now(timezone.utc).isoformat()
        wallet_file.write_text(json.dumps(state, indent=2))

    def summarize_quarantined_positions(self, reconciled_positions: List[Dict]) -> Dict:
        quarantined = [p for p in (reconciled_positions or []) if p.get('allocation_state') == 'quarantined']
        return {
            'count': len(quarantined),
            'ids': [p.get('id') for p in quarantined if p.get('id')],
        }

    def build_reconciled_positions(self, wallet: Dict, tracked_positions: Optional[List] = None) -> List[Dict]:
        """Reconstruct visible live position objects without inventing non-derivable metadata."""
        tracked_positions = tracked_positions or []
        persisted_positions = self.load_persisted_positions()
        if tracked_positions:
            reconciled = []
            for pos in tracked_positions:
                reconciled.append({
                    'source': 'tracked_trade_manager_state',
                    'asset': 'WETH' if getattr(pos, 'direction', None) == 'long' else 'UNKNOWN',
                    'entry_price': getattr(pos, 'entry_price', None),
                    'target_price': getattr(pos, 'target_price', None),
                    'stop_price': getattr(pos, 'stop_price', None),
                    'max_hold_seconds': HOLD_TIME_MAX_SECONDS,
                    'size_usd': getattr(pos, 'size_usd', None),
                    'status': getattr(getattr(pos, 'status', None), 'value', None),
                    'tx_hash': getattr(pos, 'tx_hash', None),
                    'entry_derivation': 'tracked',
                    'target_derivation': 'tracked',
                    'stop_derivation': 'tracked',
                    'max_hold_derivation': 'config',
                })
            return reconciled

        weth_balance = float((wallet or {}).get('weth') or 0.0)
        cbbtc_balance = float((wallet or {}).get('cbbtc') or 0.0)
        if weth_balance <= DUST_WETH_EPSILON:
            weth_balance = 0.0
        if cbbtc_balance <= DUST_WETH_EPSILON:
            cbbtc_balance = 0.0
        if (weth_balance > 0 or cbbtc_balance > 0) and persisted_positions:
            remaining_by_asset = {
                'WETH': weth_balance,
                'CBBTC': cbbtc_balance,
            }
            reconciled = []
            for pos in persisted_positions:
                lot_units = pos.get('lot_units')
                if lot_units is None:
                    lot_units = 0.0
                lot_units = float(lot_units)
                enriched = dict(pos)
                enriched['lot_units'] = lot_units
                if enriched.get('status') == 'closed':
                    enriched['allocated_units'] = 0.0
                    enriched['linked_to_wallet_inventory'] = False
                    enriched['allocation_state'] = 'closed'
                    enriched['resumable_after_restart'] = False
                    reconciled.append(enriched)
                    continue
                binding_asset = enriched.get('binding_asset') or enriched.get('asset') or 'WETH'
                remaining = remaining_by_asset.get(binding_asset, 0.0)
                asset_min_units = MIN_TRADABLE_WETH_UNITS if binding_asset == 'WETH' else 1e-8
                if enriched.get('source') == 'inventory_reconciliation' and remaining < asset_min_units:
                    enriched['allocated_units'] = 0.0
                    enriched['linked_to_wallet_inventory'] = False
                    enriched['allocation_state'] = 'closed'
                    enriched['status'] = 'closed'
                    enriched['resumable_after_restart'] = False
                    reconciled.append(enriched)
                    continue
                if lot_units <= 0:
                    enriched['allocated_units'] = 0.0
                    enriched['linked_to_wallet_inventory'] = False
                    enriched['status'] = 'quarantined_zero_unit_tracked_lot'
                    enriched['allocation_state'] = 'quarantined'
                    enriched['quarantine_reason'] = 'pre_fix_zero_unit_lot'
                    reconciled.append(enriched)
                    continue
                allocated_units = min(remaining, lot_units) if remaining > 0 else 0.0
                remaining = max(0.0, remaining - allocated_units)
                remaining_by_asset[binding_asset] = remaining
                enriched['allocated_units'] = allocated_units
                enriched['linked_to_wallet_inventory'] = allocated_units > 0
                enriched['allocation_state'] = 'allocated' if allocated_units > 0 else 'unallocated'
                enriched['resumable_after_restart'] = bool(enriched.get('resumable_after_restart')) and allocated_units > 0
                reconciled.append(enriched)
            for asset, remaining in remaining_by_asset.items():
                asset_min_units = MIN_TRADABLE_WETH_UNITS if asset == 'WETH' else 1e-8
                if remaining >= asset_min_units:
                    reconciled.append({
                        'source': 'inventory_reconciliation',
                        'asset': asset,
                        'lot_units': remaining,
                        'allocated_units': remaining,
                        'binding_asset': asset,
                        'binding_units': remaining,
                        'entry_price': None,
                        'target_price': None,
                        'stop_price': None,
                        'max_hold_seconds': None,
                        'status': 'legacy_unallocated_inventory',
                        'tx_hash': None,
                        'linked_to_wallet_inventory': True,
                        'entry_derivation': 'UNVERIFIED',
                        'target_derivation': 'UNVERIFIED',
                        'stop_derivation': 'UNVERIFIED',
                        'max_hold_derivation': 'UNVERIFIED',
                        'notes': f'Unallocated legacy {asset} inventory not linked to a tracked execution lot.'
                    })
            return reconciled
        if weth_balance >= MIN_TRADABLE_WETH_UNITS or cbbtc_balance >= 1e-8:
            single_asset = 'WETH' if weth_balance >= MIN_TRADABLE_WETH_UNITS else 'CBBTC'
            single_units = weth_balance if single_asset == 'WETH' else cbbtc_balance
            return [{
                'id': f'reconciled_live_inventory_{single_asset.lower()}',
                'source': 'inventory_reconciliation',
                'asset': single_asset,
                'lot_units': single_units,
                'allocated_units': single_units,
                'binding_asset': single_asset,
                'binding_units': single_units,
                'entry_price': None,
                'target_price': None,
                'stop_price': None,
                'max_hold_seconds': HOLD_TIME_MAX_SECONDS,
                'status': 'legacy_unallocated_inventory',
                'allocation_state': 'allocated',
                'resumable_after_restart': True,
                'tx_hash': None,
                'linked_to_wallet_inventory': True,
                'entry_derivation': 'UNVERIFIED',
                'target_derivation': 'UNVERIFIED',
                'stop_derivation': 'UNVERIFIED',
                'max_hold_derivation': 'config',
                'notes': f'Derived from nonzero on-chain {single_asset} inventory with no active or persisted tracked lots. Treat as managed live inventory for compounding.'
            }]
        return []

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
