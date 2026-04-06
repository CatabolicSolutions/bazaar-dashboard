#!/usr/bin/env python3
"""
Position management API for dashboard
Fetches live position data and handles position closing
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add scripts directory to path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

from tradier_account import positions as get_tradier_positions, balances
from tradier_broker_interface import TradierBrokerInterface
from tradier_execution import occ_option_symbol


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_live_positions() -> dict:
    """Fetch current positions from Tradier with live P&L"""
    try:
        # Get positions from Tradier
        tradier_positions = get_tradier_positions()
        
        # Get account balances for buying power
        account_balances = balances()
        
        positions_data = {
            'updated_at': now_iso(),
            'positions': [],
            'account_summary': {
                'option_buying_power': account_balances.get('balances', {}).get('margin', {}).get('option_buying_power', 0),
                'total_cash': account_balances.get('balances', {}).get('total_cash', 0),
            }
        }
        
        # Parse Tradier positions
        if tradier_positions and 'positions' in tradier_positions:
            if tradier_positions['positions'] == 'null':
                positions_data['positions'] = []
            elif isinstance(tradier_positions['positions'], dict):
                position_list = tradier_positions['positions'].get('position', [])
                if not isinstance(position_list, list):
                    position_list = [position_list]
                
                for pos in position_list:
                    position_data = {
                        'symbol': pos.get('symbol', ''),
                        'description': pos.get('description', ''),
                        'quantity': int(pos.get('quantity', 0)),
                        'entry_price': float(pos.get('cost_basis', 0)) / int(pos.get('quantity', 1)) if int(pos.get('quantity', 1)) > 0 else 0,
                        'current_price': float(pos.get('last_price', 0)),
                        'market_value': float(pos.get('market_value', 0)),
                        'cost_basis': float(pos.get('cost_basis', 0)),
                        'pnl_dollar': float(pos.get('gain_loss', 0)),
                        'pnl_percent': float(pos.get('gain_loss_percent', 0)) * 100,
                        'option_type': 'call' if 'Call' in pos.get('description', '') else 'put',
                        'strike': _extract_strike(pos.get('description', '')),
                        'expiration': _extract_expiration(pos.get('description', '')),
                        'days_to_expiry': _calculate_dte(_extract_expiration(pos.get('description', ''))),
                    }
                    positions_data['positions'].append(position_data)
        
        return {'ok': True, 'data': positions_data}
        
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def _extract_strike(description: str) -> float:
    """Extract strike price from option description"""
    try:
        # Description format: "SPY Mar 31 2026 $400.00 Put"
        parts = description.split('$')
        if len(parts) > 1:
            strike_str = parts[1].split()[0]
            return float(strike_str.replace(',', ''))
    except:
        pass
    return 0.0


def _extract_expiration(description: str) -> str:
    """Extract expiration date from option description"""
    try:
        # Description format: "SPY Mar 31 2026 $400.00 Put"
        import re
        match = re.search(r'(\w{3})\s+(\d{1,2})\s+(\d{4})', description)
        if match:
            month_str, day, year = match.groups()
            months = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                     'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}
            month = months.get(month_str, 1)
            return f"{year}-{month:02d}-{int(day):02d}"
    except:
        pass
    return ''


def _calculate_dte(expiration: str) -> int:
    """Calculate days to expiry"""
    try:
        from datetime import datetime
        exp_date = datetime.strptime(expiration, '%Y-%m-%d')
        today = datetime.now()
        delta = exp_date - today
        return max(0, delta.days)
    except:
        return 0


def close_position(symbol: str, quantity: int, option_type: str, strike: float, expiration: str) -> dict:
    """Close a position by selling to close"""
    try:
        broker = TradierBrokerInterface()
        
        # Build option symbol
        option_symbol = occ_option_symbol(symbol, expiration, option_type, strike)
        
        # Build sell order
        payload = {
            'class': 'option',
            'symbol': symbol.upper(),
            'option_symbol': option_symbol,
            'side': 'sell_to_close',
            'quantity': quantity,
            'type': 'market',  # Market order for quick close
            'duration': 'day',
            'tag': f'alfred-close-{now_iso()}',
        }
        
        # Preview first
        preview = broker.preview_order(payload)
        
        # Place order
        result = broker.place_order(payload)
        
        return {
            'ok': True,
            'preview': preview,
            'order': result,
            'message': f'Position close order placed for {symbol} {quantity} contracts'
        }
        
    except Exception as e:
        return {'ok': False, 'error': str(e)}


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Position management API')
    parser.add_argument('--get-positions', action='store_true', help='Get live positions')
    parser.add_argument('--close', action='store_true', help='Close a position')
    parser.add_argument('--symbol', help='Symbol to close')
    parser.add_argument('--quantity', type=int, help='Quantity to close')
    parser.add_argument('--option-type', choices=['call', 'put'], help='Option type')
    parser.add_argument('--strike', type=float, help='Strike price')
    parser.add_argument('--expiration', help='Expiration date (YYYY-MM-DD)')
    
    args = parser.parse_args()
    
    if args.get_positions:
        result = get_live_positions()
        print(json.dumps(result, indent=2))
    elif args.close:
        if not all([args.symbol, args.quantity, args.option_type, args.strike, args.expiration]):
            print(json.dumps({'ok': False, 'error': 'Missing required parameters for close'}))
            sys.exit(1)
        result = close_position(args.symbol, args.quantity, args.option_type, args.strike, args.expiration)
        print(json.dumps(result, indent=2))
    else:
        parser.print_help()
