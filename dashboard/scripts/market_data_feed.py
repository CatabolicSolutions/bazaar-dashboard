#!/usr/bin/env python3
"""
Live market data feed for dashboard scanner
Fetches real-time quotes and calculates opportunity scores
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

import requests

API_BASE = os.getenv('TRADIER_BASE_URL', 'https://api.tradier.com/v1')
API_TOKEN = os.getenv('TRADIER_API_KEY')
HEADERS = {
    'Authorization': f'Bearer {API_TOKEN}',
    'Accept': 'application/json',
} if API_TOKEN else {}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_quotes(symbols: list[str]) -> dict[str, Any]:
    """Get real-time quotes for symbols"""
    if not API_TOKEN or not symbols:
        return {}
    
    try:
        url = f'{API_BASE}/markets/quotes'
        params = {'symbols': ','.join(symbols), 'greeks': 'true'}
        r = requests.get(url, headers=HEADERS, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        
        quotes = {}
        if 'quotes' in data:
            quote_list = data['quotes'].get('quote', [])
            if not isinstance(quote_list, list):
                quote_list = [quote_list]
            
            for q in quote_list:
                symbol = q.get('symbol')
                if symbol:
                    # Safely convert values with None handling
                    def safe_float(val, default=0.0):
                        try:
                            return float(val) if val is not None else default
                        except (ValueError, TypeError):
                            return default
                    
                    def safe_int(val, default=0):
                        try:
                            return int(val) if val is not None else default
                        except (ValueError, TypeError):
                            return default
                    
                    greeks = q.get('greeks', {}) or {}
                    
                    quotes[symbol] = {
                        'last': safe_float(q.get('last')),
                        'bid': safe_float(q.get('bid')),
                        'ask': safe_float(q.get('ask')),
                        'volume': safe_int(q.get('volume')),
                        'open_interest': safe_int(q.get('open_interest')),
                        'iv': safe_float(greeks.get('mid_iv')) * 100 if greeks else 0,
                        'delta': safe_float(greeks.get('delta')) if greeks else 0,
                        'theta': safe_float(greeks.get('theta')) if greeks else 0,
                        'change': safe_float(q.get('change')),
                        'change_percent': safe_float(q.get('change_percentage')),
                    }
        return quotes
    except Exception as e:
        return {'error': str(e)}


def get_option_chains(symbol: str) -> dict:
    """Get option chain for a symbol"""
    if not API_TOKEN:
        return {}
    
    try:
        # First get expirations
        url = f'{API_BASE}/markets/options/expirations'
        params = {'symbol': symbol, 'includeAllRoots': 'true'}
        r = requests.get(url, headers=HEADERS, params=params, timeout=30)
        r.raise_for_status()
        exp_data = r.json()
        
        expirations = exp_data.get('expirations', {}).get('date', [])
        if not expirations:
            return {}
        
        # Get chain for first expiration
        chain_url = f'{API_BASE}/markets/options/chains'
        chain_params = {'symbol': symbol, 'expiration': expirations[0], 'greeks': 'true'}
        r = requests.get(chain_url, headers=HEADERS, params=chain_params, timeout=30)
        r.raise_for_status()
        
        return r.json()
    except Exception as e:
        return {'error': str(e)}


def calculate_opportunity_score(leader: dict, quote: dict) -> dict:
    """Calculate opportunity score based on various factors"""
    score = 0
    factors = []
    
    # Handle missing quote
    if not quote:
        return {
            'score': 0,
            'max_score': 100,
            'temperature': 'cold',
            'factors': ['No live data'],
            'metrics': {}
        }
    
    # Price momentum (recent change)
    change_pct = quote.get('change_percent', 0) or 0
    if abs(change_pct) > 5:
        score += 20
        factors.append('High momentum')
    elif abs(change_pct) > 2:
        score += 10
        factors.append('Moderate momentum')
    
    # Volume vs open interest
    volume = quote.get('volume', 0) or 0
    oi = quote.get('open_interest', 0) or 0
    if oi > 0 and volume > oi * 0.5:
        score += 15
        factors.append('High volume')
    
    # IV level
    iv = quote.get('iv', 0) or 0
    if iv > 30:
        score += 10
        factors.append('Elevated IV')
    elif iv < 15:
        score += 5
        factors.append('Low IV')
    
    # Bid-ask spread (liquidity)
    bid = quote.get('bid', 0) or 0
    ask = quote.get('ask', 0) or 0
    spread_pct = None
    if bid > 0 and ask > 0:
        spread_pct = (ask - bid) / ((ask + bid) / 2) * 100
        if spread_pct < 5:
            score += 15
            factors.append('Tight spread')
        elif spread_pct < 10:
            score += 5
            factors.append('Moderate spread')
    
    # Delta alignment (for directional trades)
    delta = abs(quote.get('delta', 0) or 0)
    if 0.10 <= delta <= 0.20:
        score += 10
        factors.append('Good delta range')
    
    # Determine temperature
    if score >= 50:
        temperature = 'hot'
    elif score >= 30:
        temperature = 'warm'
    elif score >= 15:
        temperature = 'cool'
    else:
        temperature = 'cold'
    
    return {
        'score': score,
        'max_score': 100,
        'temperature': temperature,
        'factors': factors,
        'metrics': {
            'change_percent': change_pct,
            'volume_vs_oi': volume / oi if oi > 0 else 0,
            'iv': iv,
            'spread_pct': spread_pct,
            'delta': delta,
        }
    }


def get_live_scanner_data() -> dict:
    """Get enhanced scanner data with live market data"""
    # Read current leaders from board
    board_path = ROOT / 'out' / 'tradier_leaders_board.txt'
    if not board_path.exists():
        return {'ok': False, 'error': 'Board not found'}
    
    board_text = board_path.read_text()
    
    # Parse option symbols from board
    import re
    option_symbols = []
    leaders_info = []
    
    current_section = None
    
    for line in board_text.split('\n'):
        line = line.strip()
        if line.startswith('Directional'):
            current_section = 'directional'
            continue
        elif line.startswith('Premium'):
            current_section = 'premium'
            continue
        elif line.startswith('VIX:'):
            continue
        elif line.startswith('Run Notes'):
            break
        
        # Parse leader line
        match = re.match(r'^(\d+)\.\s+(\w+)\s+(CALL|PUT)\s+\|\s+Underlying\s+([\d.]+)\s+\|\s+Strike\s+([\d.]+)\s+\|\s+Exp\s+(\S+)', line)
        if match:
            num, symbol, opt_type, underlying, strike, exp = match.groups()
            
            # Build option symbol for quote lookup
            from tradier_execution import occ_option_symbol
            try:
                option_symbol = occ_option_symbol(symbol, exp, opt_type.lower(), float(strike))
                option_symbols.append(option_symbol)
                leaders_info.append({
                    'number': num,
                    'symbol': symbol,
                    'option_type': opt_type,
                    'underlying': float(underlying) if underlying else 0,
                    'strike': float(strike) if strike else 0,
                    'expiration': exp,
                    'section': current_section,
                    'option_symbol': option_symbol,
                })
            except Exception as e:
                print(f"Error building symbol for {symbol}: {e}", file=sys.stderr)
    
    # Get live quotes for options
    quotes = get_quotes(option_symbols)
    
    if 'error' in quotes:
        return {'ok': False, 'error': quotes['error']}
    
    # Enhance leaders with live data
    enhanced_leaders = []
    
    for leader_info in leaders_info:
        option_symbol = leader_info['option_symbol']
        quote = quotes.get(option_symbol, {})
        
        # Calculate opportunity score
        opportunity = calculate_opportunity_score(leader_info, quote)
        
        enhanced_leaders.append({
            **leader_info,
            'quote': quote,
            'opportunity': opportunity,
        })
    
    return {
        'ok': True,
        'data': {
            'updated_at': now_iso(),
            'leaders': enhanced_leaders,
            'count': len(enhanced_leaders),
        }
    }


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Live market data feed')
    parser.add_argument('--scanner', action='store_true', help='Get enhanced scanner data')
    parser.add_argument('--quotes', help='Get quotes for symbols (comma-separated)')
    
    args = parser.parse_args()
    
    if args.scanner:
        result = get_live_scanner_data()
        print(json.dumps(result, indent=2))
    elif args.quotes:
        symbols = args.quotes.split(',')
        result = get_quotes(symbols)
        print(json.dumps(result, indent=2))
    else:
        parser.print_help()
