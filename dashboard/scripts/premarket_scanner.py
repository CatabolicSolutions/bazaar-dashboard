#!/usr/bin/env python3
"""
Pre-Market Gap Scanner
Identifies overnight gap opportunities before market open
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Add scripts directory to path
ROOT = Path('/home/catabolic_solutions/.openclaw/workspace')
sys.path.insert(0, str(ROOT / 'scripts'))

import requests

API_BASE = os.getenv('TRADIER_BASE_URL', 'https://api.tradier.com/v1')
API_TOKEN = os.getenv('TRADIER_API_KEY')
HEADERS = {
    'Authorization': f'Bearer {API_TOKEN}',
    'Accept': 'application/json',
} if API_TOKEN else {}

# Focus on liquid options underlyings
WATCHLIST = [
    'SPY', 'QQQ', 'IWM',  # ETFs
    'AAPL', 'MSFT', 'AMZN', 'GOOGL', 'META',  # Big tech
    'TSLA', 'NVDA', 'AMD', 'NFLX',  # High volatility
    'JPM', 'BAC', 'GS',  # Financials
    'XLE', 'XLF', 'XLK', 'XLI',  # Sectors
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_quotes(symbols: list[str]) -> dict[str, Any]:
    """Get quotes for symbols"""
    if not API_TOKEN or not symbols:
        return {}
    
    try:
        url = f'{API_BASE}/markets/quotes'
        params = {'symbols': ','.join(symbols)}
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
                    quotes[symbol] = {
                        'last': float(q.get('last', 0) or 0),
                        'open': float(q.get('open', 0) or 0),
                        'prevclose': float(q.get('prevclose', 0) or 0),
                        'volume': int(q.get('volume', 0) or 0),
                        'average_volume': int(q.get('average_volume', 0) or 0),
                    }
        return quotes
    except Exception as e:
        return {'error': str(e)}


def calculate_gap(quote: dict) -> dict:
    """Calculate gap percentage and metrics"""
    last = quote.get('last', 0)
    prevclose = quote.get('prevclose', 0)
    
    if prevclose <= 0:
        return None
    
    gap_pct = ((last - prevclose) / prevclose) * 100
    
    # Relative volume
    volume = quote.get('volume', 0)
    avg_volume = quote.get('average_volume', 1)
    relative_volume = volume / avg_volume if avg_volume > 0 else 0
    
    # Gap direction
    if gap_pct >= 3:
        direction = 'gap_up'
        significance = 'high' if gap_pct >= 5 else 'medium'
    elif gap_pct <= -3:
        direction = 'gap_down'
        significance = 'high' if gap_pct <= -5 else 'medium'
    elif abs(gap_pct) >= 1:
        direction = 'gap_up' if gap_pct > 0 else 'gap_down'
        significance = 'low'
    else:
        direction = 'flat'
        significance = 'none'
    
    return {
        'gap_percent': round(gap_pct, 2),
        'direction': direction,
        'significance': significance,
        'relative_volume': round(relative_volume, 2),
        'last_price': last,
        'prev_close': prevclose,
    }


def scan_gaps() -> dict:
    """Scan for pre-market gaps"""
    quotes = get_quotes(WATCHLIST)
    
    if 'error' in quotes:
        return {'ok': False, 'error': quotes['error']}
    
    gaps = []
    
    for symbol, quote in quotes.items():
        gap_data = calculate_gap(quote)
        if gap_data and gap_data['significance'] in ('high', 'medium'):
            gaps.append({
                'symbol': symbol,
                **gap_data
            })
    
    # Sort by absolute gap size (largest moves first)
    gaps.sort(key=lambda x: abs(x['gap_percent']), reverse=True)
    
    # Categorize
    high_priority = [g for g in gaps if g['significance'] == 'high']
    medium_priority = [g for g in gaps if g['significance'] == 'medium']
    
    return {
        'ok': True,
        'data': {
            'scanned_at': now_iso(),
            'market_status': 'pre-market',
            'total_scanned': len(WATCHLIST),
            'gaps_found': len(gaps),
            'high_priority': high_priority,
            'medium_priority': medium_priority,
            'all_gaps': gaps
        }
    }


def generate_option_plays(gap: dict) -> list[dict]:
    """Generate potential option plays for a gap"""
    plays = []
    symbol = gap['symbol']
    direction = gap['direction']
    
    # For gap up: consider call credit spreads or put buys for reversal
    # For gap down: consider put credit spreads or call buys for reversal
    
    if direction == 'gap_up':
        plays.append({
            'strategy': 'put_credit_spread',
            'direction': 'bullish',
            'rationale': f'Gap up {gap["gap_percent"]}% - sell premium on pullback',
            'risk': 'medium'
        })
        plays.append({
            'strategy': 'long_put',
            'direction': 'bearish_reversal',
            'rationale': 'Fade the gap if overextended',
            'risk': 'high'
        })
    elif direction == 'gap_down':
        plays.append({
            'strategy': 'call_credit_spread',
            'direction': 'bearish',
            'rationale': f'Gap down {gap["gap_percent"]}% - sell premium on bounce',
            'risk': 'medium'
        })
        plays.append({
            'strategy': 'long_call',
            'direction': 'bullish_reversal',
            'rationale': 'Buy the dip if oversold',
            'risk': 'high'
        })
    
    return plays


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Pre-market gap scanner')
    parser.add_argument('--scan', action='store_true', help='Run gap scan')
    parser.add_argument('--output', help='Output file for results')
    
    args = parser.parse_args()
    
    if args.scan:
        result = scan_gaps()
        
        # Add option plays to each gap
        if result.get('ok'):
            for gap in result['data']['all_gaps']:
                gap['option_plays'] = generate_option_plays(gap)
        
        output = json.dumps(result, indent=2)
        
        if args.output:
            Path(args.output).write_text(output)
            print(f'Results saved to: {args.output}')
        else:
            print(output)
    else:
        parser.print_help()
