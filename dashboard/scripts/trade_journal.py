#!/usr/bin/env python3
"""
Trade Journal - Auto-logs all trading activity
Tracks entries, exits, P&L, and generates analytics
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

# Add scripts directory to path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

JOURNAL_DIR = ROOT / 'journal'


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_journal_file() -> Path:
    """Get current month's journal file"""
    today = datetime.now(timezone.utc)
    filename = f"trades_{today.strftime('%Y-%m')}.json"
    return JOURNAL_DIR / filename


def load_journal() -> list[dict]:
    """Load all trades from current journal"""
    journal_file = get_journal_file()
    if journal_file.exists():
        try:
            return json.loads(journal_file.read_text())
        except:
            return []
    return []


def save_journal(trades: list[dict]):
    """Save trades to journal"""
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    journal_file = get_journal_file()
    journal_file.write_text(json.dumps(trades, indent=2))


def log_trade_entry(
    symbol: str,
    option_type: str,
    strike: float,
    expiration: str,
    entry_price: float,
    quantity: int,
    signal_source: str = 'manual',
    tags: list[str] = None,
    metadata: dict = None
) -> dict:
    """Log a new trade entry"""
    trades = load_journal()
    
    trade = {
        'trade_id': f"trade_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{symbol}",
        'status': 'open',
        'entry': {
            'timestamp': now_iso(),
            'symbol': symbol,
            'option_type': option_type,
            'strike': strike,
            'expiration': expiration,
            'price': entry_price,
            'quantity': quantity,
        },
        'exit': None,
        'pnl': None,
        'duration_minutes': None,
        'signal_source': signal_source,
        'tags': tags or [],
        'metadata': metadata or {},
    }
    
    trades.append(trade)
    save_journal(trades)
    
    return trade


def log_trade_exit(
    trade_id: str,
    exit_price: float,
    exit_reason: str = 'manual',
    exit_score: int = None,
    tags_to_add: list[str] = None
) -> dict:
    """Log a trade exit and calculate P&L"""
    trades = load_journal()
    
    for trade in trades:
        if trade['trade_id'] == trade_id:
            entry = trade['entry']
            entry_time = datetime.fromisoformat(entry['timestamp'])
            exit_time = datetime.now(timezone.utc)
            
            # Calculate P&L
            entry_value = entry['price'] * entry['quantity'] * 100
            exit_value = exit_price * entry['quantity'] * 100
            pnl = exit_value - entry_value
            pnl_percent = (pnl / entry_value * 100) if entry_value > 0 else 0
            
            # Calculate duration
            duration = exit_time - entry_time
            duration_minutes = duration.total_seconds() / 60
            
            # Update trade
            trade['status'] = 'closed'
            trade['exit'] = {
                'timestamp': now_iso(),
                'price': exit_price,
                'reason': exit_reason,
                'exit_score': exit_score,
            }
            trade['pnl'] = {
                'dollar': round(pnl, 2),
                'percent': round(pnl_percent, 2),
            }
            trade['duration_minutes'] = round(duration_minutes, 1)
            
            # Add tags
            if tags_to_add:
                trade['tags'].extend(tags_to_add)
            
            save_journal(trades)
            return trade
    
    return None


def calculate_analytics(trades: list[dict] = None, period: str = 'all') -> dict:
    """Calculate trading analytics"""
    if trades is None:
        trades = load_journal()
    
    # Filter by period
    now = datetime.now(timezone.utc)
    if period == 'today':
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        trades = [t for t in trades if datetime.fromisoformat(t['entry']['timestamp']) >= start]
    elif period == 'week':
        start = now - timedelta(days=7)
        trades = [t for t in trades if datetime.fromisoformat(t['entry']['timestamp']) >= start]
    elif period == 'month':
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        trades = [t for t in trades if datetime.fromisoformat(t['entry']['timestamp']) >= start]
    
    closed_trades = [t for t in trades if t['status'] == 'closed']
    
    if not closed_trades:
        return {
            'period': period,
            'total_trades': 0,
            'win_rate': 0,
            'avg_pnl': 0,
            'total_pnl': 0,
            'best_trade': None,
            'worst_trade': None,
        }
    
    # Basic stats
    total_trades = len(closed_trades)
    winning_trades = [t for t in closed_trades if t['pnl']['dollar'] > 0]
    losing_trades = [t for t in closed_trades if t['pnl']['dollar'] <= 0]
    
    win_rate = len(winning_trades) / total_trades * 100
    
    # P&L stats
    pnls = [t['pnl']['dollar'] for t in closed_trades]
    total_pnl = sum(pnls)
    avg_pnl = total_pnl / total_trades
    
    # Best/worst trades
    best_trade = max(closed_trades, key=lambda t: t['pnl']['dollar'])
    worst_trade = min(closed_trades, key=lambda t: t['pnl']['dollar'])
    
    # Max drawdown (consecutive losses)
    max_drawdown_streak = 0
    current_streak = 0
    for t in closed_trades:
        if t['pnl']['dollar'] < 0:
            current_streak += 1
            max_drawdown_streak = max(max_drawdown_streak, current_streak)
        else:
            current_streak = 0
    
    # P&L by hour
    pnl_by_hour = {}
    for t in closed_trades:
        hour = datetime.fromisoformat(t['entry']['timestamp']).hour
        if hour not in pnl_by_hour:
            pnl_by_hour[hour] = []
        pnl_by_hour[hour].append(t['pnl']['dollar'])
    
    pnl_by_hour_avg = {h: sum(v)/len(v) for h, v in pnl_by_hour.items()}
    
    # Duration stats
    durations = [t['duration_minutes'] for t in closed_trades if t['duration_minutes']]
    avg_duration = sum(durations) / len(durations) if durations else 0
    
    return {
        'period': period,
        'total_trades': total_trades,
        'winning_trades': len(winning_trades),
        'losing_trades': len(losing_trades),
        'win_rate': round(win_rate, 1),
        'avg_pnl': round(avg_pnl, 2),
        'total_pnl': round(total_pnl, 2),
        'best_trade': {
            'symbol': best_trade['entry']['symbol'],
            'pnl': best_trade['pnl']['dollar'],
            'date': best_trade['exit']['timestamp'],
        },
        'worst_trade': {
            'symbol': worst_trade['entry']['symbol'],
            'pnl': worst_trade['pnl']['dollar'],
            'date': worst_trade['exit']['timestamp'],
        },
        'max_drawdown_streak': max_drawdown_streak,
        'avg_duration_minutes': round(avg_duration, 1),
        'pnl_by_hour': pnl_by_hour_avg,
    }


def export_to_csv(output_path: str = None) -> str:
    """Export trades to CSV format"""
    trades = load_journal()
    
    if not output_path:
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        output_path = str(JOURNAL_DIR / f'trades_export_{today}.csv')
    
    import csv
    
    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'Trade ID', 'Status', 'Symbol', 'Option Type', 'Strike', 'Expiry',
            'Entry Time', 'Entry Price', 'Quantity',
            'Exit Time', 'Exit Price', 'Exit Reason',
            'P&L ($)', 'P&L (%)', 'Duration (min)',
            'Signal Source', 'Tags'
        ])
        
        for t in trades:
            entry = t['entry']
            exit_data = t.get('exit', {})
            pnl = t.get('pnl', {})
            
            writer.writerow([
                t['trade_id'],
                t['status'],
                entry['symbol'],
                entry['option_type'],
                entry['strike'],
                entry['expiration'],
                entry['timestamp'],
                entry['price'],
                entry['quantity'],
                exit_data.get('timestamp', ''),
                exit_data.get('price', ''),
                exit_data.get('reason', ''),
                pnl.get('dollar', '') if pnl else '',
                pnl.get('percent', '') if pnl else '',
                t.get('duration_minutes', ''),
                t.get('signal_source', ''),
                ', '.join(t.get('tags', []))
            ])
    
    return output_path


def get_all_trades() -> list[dict]:
    """Get all trades from all journal files"""
    all_trades = []
    
    if JOURNAL_DIR.exists():
        for journal_file in JOURNAL_DIR.glob('trades_*.json'):
            try:
                trades = json.loads(journal_file.read_text())
                all_trades.extend(trades)
            except:
                pass
    
    # Sort by entry time
    all_trades.sort(key=lambda t: t['entry']['timestamp'], reverse=True)
    return all_trades


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Trade Journal')
    parser.add_argument('--analytics', choices=['today', 'week', 'month', 'all'], help='Show analytics')
    parser.add_argument('--export-csv', action='store_true', help='Export to CSV')
    parser.add_argument('--list', action='store_true', help='List all trades')
    
    args = parser.parse_args()
    
    if args.analytics:
        result = calculate_analytics(period=args.analytics)
        print(json.dumps(result, indent=2))
    elif args.export_csv:
        path = export_to_csv()
        print(f'Exported to: {path}')
    elif args.list:
        trades = get_all_trades()
        print(json.dumps(trades, indent=2))
    else:
        parser.print_help()
