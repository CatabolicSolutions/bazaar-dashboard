#!/usr/bin/env python3
"""
Exit Predictor Engine
Monitors open positions and generates HOLD/WATCH/EXIT signals
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

# Add scripts directory to path
ROOT = Path('/home/catabolic_solutions/.openclaw/workspace')
sys.path.insert(0, str(ROOT / 'scripts'))

from position_manager import get_live_positions
from tradier_state_store import load_state


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ExitPredictor:
    def __init__(self):
        self.position_history = {}  # Track changes over time
        self.history_file = ROOT / 'dashboard' / 'state' / 'position_history.json'
        self.load_history()
    
    def load_history(self):
        """Load position history from file"""
        if self.history_file.exists():
            try:
                self.position_history = json.loads(self.history_file.read_text())
            except:
                self.position_history = {}
    
    def save_history(self):
        """Save position history to file"""
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        self.history_file.write_text(json.dumps(self.position_history, indent=2))
    
    def calculate_exit_score(self, position: dict, live_data: dict) -> dict:
        """
        Calculate exit score (0-100) based on:
        - Delta divergence (0-40 points)
        - Theta acceleration (0-30 points)
        - Price level breach (0-30 points)
        """
        score = 0
        reasons = []
        
        # Get position identifier
        position_key = f"{position.get('symbol')}_{position.get('contract', '').replace(' ', '_')}"
        
        # Track history
        if position_key not in self.position_history:
            self.position_history[position_key] = {
                'entry_delta': live_data.get('delta', 0),
                'entry_time': now_iso(),
                'snapshots': []
            }
        
        history = self.position_history[position_key]
        entry_delta = history.get('entry_delta', live_data.get('delta', 0))
        current_delta = live_data.get('delta', 0)
        
        # ===== DELTA DIVERGENCE (0-40 points) =====
        if entry_delta != 0:
            delta_change_pct = abs((current_delta - entry_delta) / entry_delta) * 100
        else:
            delta_change_pct = 0
        
        # Delta moved >20% against position = EXIT (40 points)
        if delta_change_pct > 20:
            score += 40
            reasons.append(f"Delta moved {delta_change_pct:.1f}% against position")
        # Delta moved 10-20% against = WATCH (20 points)
        elif delta_change_pct > 10:
            score += 20
            reasons.append(f"Delta moved {delta_change_pct:.1f}% - monitor closely")
        # Delta moved 5-10% = mild concern (10 points)
        elif delta_change_pct > 5:
            score += 10
        
        # ===== THETA ACCELERATION (0-30 points) =====
        current_theta = abs(live_data.get('theta', 0))
        
        # Expected theta decay for 0DTE/1DTE is roughly 50-100% of value per day
        # If theta is burning >2x expected, that's a problem
        position_value = live_data.get('last', 0) * 100  # Per contract
        expected_daily_theta = position_value * 0.5  # Assume 50% daily decay
        
        if expected_daily_theta > 0 and current_theta > 0:
            theta_ratio = current_theta / expected_daily_theta
            
            if theta_ratio > 2.0:
                score += 30
                reasons.append(f"Theta burn {theta_ratio:.1f}x expected - accelerating decay")
            elif theta_ratio > 1.5:
                score += 15
                reasons.append(f"Theta burn elevated ({theta_ratio:.1f}x)")
        
        # ===== PRICE LEVEL BREACH (0-30 points) =====
        underlying = live_data.get('underlying', 0)
        strike = self._extract_strike(position.get('contract', ''))
        
        if underlying > 0 and strike > 0:
            # Calculate distance to strike as %
            distance_pct = abs(underlying - strike) / strike * 100
            
            # Price within 1% of strike = danger zone for ATM options
            if distance_pct < 1.0:
                score += 30
                reasons.append(f"Price ${underlying:.2f} within 1% of strike ${strike:.2f}")
            # Price within 2% = watch zone
            elif distance_pct < 2.0:
                score += 15
                reasons.append(f"Price approaching strike ({distance_pct:.1f}% away)")
        
        # Store snapshot
        history['snapshots'].append({
            'timestamp': now_iso(),
            'delta': current_delta,
            'theta': current_theta,
            'underlying': underlying,
            'score': score
        })
        
        # Keep only last 20 snapshots
        history['snapshots'] = history['snapshots'][-20:]
        
        # Determine signal
        if score >= 70:
            signal = 'EXIT'
            color = 'red'
        elif score >= 40:
            signal = 'WATCH'
            color = 'yellow'
        else:
            signal = 'HOLD'
            color = 'green'
        
        return {
            'score': score,
            'max_score': 100,
            'signal': signal,
            'color': color,
            'reasons': reasons,
            'metrics': {
                'delta_change_pct': delta_change_pct,
                'current_delta': current_delta,
                'entry_delta': entry_delta,
                'current_theta': current_theta,
                'underlying': underlying,
                'strike': strike,
            },
            'position_key': position_key,
            'updated_at': now_iso()
        }
    
    def _extract_strike(self, contract: str) -> float:
        """Extract strike from contract string"""
        try:
            parts = contract.split()
            if len(parts) >= 3:
                return float(parts[1])
        except:
            pass
        return 0.0
    
    def analyze_all_positions(self) -> dict:
        """Analyze all open positions and generate exit signals"""
        # Get live positions
        positions_result = get_live_positions()
        
        if not positions_result.get('ok'):
            return {'ok': False, 'error': positions_result.get('error', 'Failed to fetch positions')}
        
        live_data = positions_result.get('data', {})
        positions = live_data.get('positions', [])
        
        # Also get positions from execution state
        state = load_state()
        execution_positions = state.get('positions', [])
        
        # Merge position data
        all_positions = []
        
        # Add live positions from Tradier
        for pos in positions:
            all_positions.append({
                'symbol': pos.get('symbol', ''),
                'contract': pos.get('description', ''),
                'quantity': pos.get('quantity', 0),
                'entry_price': pos.get('entry_price', 0),
                'current_price': pos.get('current_price', 0),
                'live_data': pos
            })
        
        # Add execution state positions if not already included
        for pos in execution_positions:
            if pos.get('current_status') == 'open':
                exists = any(p.get('symbol') == pos.get('symbol') and 
                           p.get('contract') == pos.get('contract') for p in all_positions)
                if not exists:
                    all_positions.append({
                        'symbol': pos.get('symbol', ''),
                        'contract': pos.get('contract', ''),
                        'quantity': pos.get('qty', 0),
                        'entry_price': float(pos.get('entry_price', 0)),
                        'current_price': float(pos.get('entry_price', 0)),
                        'live_data': {}
                    })
        
        # Analyze each position
        analysis_results = []
        exit_count = 0
        watch_count = 0
        hold_count = 0
        
        for position in all_positions:
            # Use live data if available, otherwise empty
            live = position.get('live_data', {})
            
            analysis = self.calculate_exit_score(position, live)
            
            analysis_results.append({
                'position': position,
                'analysis': analysis
            })
            
            if analysis['signal'] == 'EXIT':
                exit_count += 1
            elif analysis['signal'] == 'WATCH':
                watch_count += 1
            else:
                hold_count += 1
        
        # Save history
        self.save_history()
        
        return {
            'ok': True,
            'data': {
                'updated_at': now_iso(),
                'positions_analyzed': len(analysis_results),
                'summary': {
                    'exit': exit_count,
                    'watch': watch_count,
                    'hold': hold_count
                },
                'results': analysis_results
            }
        }


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Exit Predictor Engine')
    parser.add_argument('--analyze', action='store_true', help='Analyze all positions')
    
    args = parser.parse_args()
    
    if args.analyze:
        predictor = ExitPredictor()
        result = predictor.analyze_all_positions()
        print(json.dumps(result, indent=2))
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
