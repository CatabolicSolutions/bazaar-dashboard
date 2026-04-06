#!/usr/bin/env python3
"""
Portfolio Heatmap - Risk Visualization
Shows portfolio risk at a glance with color-coded P&L
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Add scripts directory to path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

from position_manager import get_live_positions


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def calculate_portfolio_heatmap() -> dict:
    """Calculate portfolio heatmap data"""
    # Get live positions
    positions_result = get_live_positions()
    
    if not positions_result.get('ok'):
        return {'ok': False, 'error': positions_result.get('error', 'Failed to fetch positions')}
    
    data = positions_result.get('data', {})
    positions = data.get('positions', [])
    
    if not positions:
        return {
            'ok': True,
            'data': {
                'updated_at': now_iso(),
                'positions': [],
                'total_value': 0,
                'total_pnl': 0,
                'risk_metrics': {},
                'concentration': {},
                'alerts': []
            }
        }
    
    # Calculate position metrics
    total_value = 0
    total_cost = 0
    total_pnl = 0
    
    # Greeks aggregation
    total_delta = 0
    total_theta = 0
    total_vega = 0
    
    # Symbol concentration
    symbol_values = {}
    
    heatmap_positions = []
    
    for pos in positions:
        # Position value and P&L
        market_value = pos.get('market_value', 0)
        cost_basis = pos.get('cost_basis', 0)
        pnl = pos.get('pnl_dollar', 0)
        pnl_percent = pos.get('pnl_percent', 0)
        
        total_value += market_value
        total_cost += cost_basis
        total_pnl += pnl
        
        # Greeks
        delta = pos.get('delta', 0) * pos.get('quantity', 0)
        theta = pos.get('theta', 0) * pos.get('quantity', 0)
        vega = pos.get('vega', 0) * pos.get('quantity', 0) if 'vega' in pos else 0
        
        total_delta += delta
        total_theta += theta
        total_vega += vega
        
        # Symbol concentration
        symbol = pos.get('symbol', 'Unknown')
        if symbol not in symbol_values:
            symbol_values[symbol] = 0
        symbol_values[symbol] += market_value
        
        # Parse description for display
        description = pos.get('description', '')
        # Format: "SPY Apr 4 2026 $400.00 Put"
        parts = description.split()
        if len(parts) >= 6:
            display_symbol = parts[0]
            expiry = f"{parts[1]} {parts[2]}"
            strike = parts[4].replace('$', '').replace(',', '')
            option_type = parts[5].lower()
        else:
            display_symbol = symbol
            expiry = 'Unknown'
            strike = '0'
            option_type = 'unknown'
        
        # Calculate DTE
        dte = pos.get('days_to_expiry', 0)
        
        heatmap_positions.append({
            'symbol': display_symbol,
            'option_type': option_type,
            'strike': strike,
            'expiry': expiry,
            'dte': dte,
            'quantity': pos.get('quantity', 0),
            'market_value': market_value,
            'cost_basis': cost_basis,
            'pnl_dollar': pnl,
            'pnl_percent': pnl_percent,
            'delta': delta,
            'theta': theta,
            'vega': vega,
            'last_price': pos.get('current_price', 0),
        })
    
    # Calculate concentration percentages
    concentration = {}
    for symbol, value in symbol_values.items():
        pct = (value / total_value * 100) if total_value > 0 else 0
        concentration[symbol] = {
            'value': value,
            'percent': round(pct, 1)
        }
    
    # Sort positions by absolute P&L (largest moves first)
    heatmap_positions.sort(key=lambda p: abs(p['pnl_dollar']), reverse=True)
    
    # Risk metrics
    risk_metrics = {
        'total_delta': round(total_delta, 2),
        'total_theta': round(total_theta, 2),
        'total_vega': round(total_vega, 2),
        'max_loss_scenario': round(total_cost, 2),  # If all go to zero
        'portfolio_beta': round(total_delta / total_value, 2) if total_value > 0 else 0,
    }
    
    # Concentration alerts
    alerts = []
    
    # Check for >20% in single symbol
    for symbol, data in concentration.items():
        if data['percent'] > 20:
            alerts.append({
                'type': 'concentration',
                'severity': 'warning',
                'message': f'{symbol} is {data["percent"]}% of portfolio (max 20%)'
            })
    
    # Check for extreme directional bias
    if abs(total_delta) > 50:
        direction = 'bullish' if total_delta > 0 else 'bearish'
        alerts.append({
            'type': 'directional_bias',
            'severity': 'warning',
            'message': f'Portfolio is highly {direction} (delta: {total_delta:.1f})'
        })
    
    # Check for high theta burn
    if total_theta < -100:  # Losing more than $100/day to time decay
        alerts.append({
            'type': 'theta_burn',
            'severity': 'info',
            'message': f'High theta burn: ${total_theta:.2f}/day'
        })
    
    return {
        'ok': True,
        'data': {
            'updated_at': now_iso(),
            'positions': heatmap_positions,
            'position_count': len(heatmap_positions),
            'total_value': round(total_value, 2),
            'total_cost': round(total_cost, 2),
            'total_pnl': round(total_pnl, 2),
            'total_pnl_percent': round((total_pnl / total_cost * 100), 2) if total_cost > 0 else 0,
            'risk_metrics': risk_metrics,
            'concentration': concentration,
            'alerts': alerts
        }
    }


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Portfolio Heatmap')
    parser.add_argument('--heatmap', action='store_true', help='Generate heatmap')
    
    args = parser.parse_args()
    
    if args.heatmap:
        result = calculate_portfolio_heatmap()
        print(json.dumps(result, indent=2))
    else:
        parser.print_help()
