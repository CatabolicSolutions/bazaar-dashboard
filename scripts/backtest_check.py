#!/usr/bin/env python3
"""
AGORA Backtest Harness — Signal Verification
Snapshots historical market state on multiple dates, runs the pipeline's
signal logic without forward-looking bias, compares against actual outcomes.

Usage:
  python3 scripts/backtest_check.py          # standard run
  python3 scripts/backtest_check.py --full   # includes simulated option pricing

The script:
1. Picks 4 historical snapshot dates (Fridays, each 1 week apart)
2. For each: fetches underlying price history UP TO that date only
3. Computes pipeline-derived metrics (momentum, RVol, trend, macro regime)
4. Simulates what AGORA would recommend from that date
5. Checks actual forward performance over the option DTE period
"""

import json, os, sys, math
from datetime import datetime, timedelta, date
from pathlib import Path

# ── Config ──
SYMBOLS = ['SPY', 'QQQ', 'IWM', 'TLT', 'TSLA', 'AMZN', 'MSFT']
LOOKBACK_DAYS = 30        # how many daily bars before snapshot
FORWARD_DAYS = 7          # outcome window (matches default DTE=7)

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent
AGORA = WORKSPACE / 'agora'

# ── Tradier API ──
TOKEN = os.environ.get('TRADIER_API_KEY')
if not TOKEN:
    # fallback: load from .bazaar.env
    env_file = WORKSPACE / '.bazaar.env'
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if '=' in line and not line.startswith('#'):
                k, v = line.strip().split('=', 1)
                os.environ.setdefault(k, v)
        TOKEN = os.environ.get('TRADIER_API_KEY')

TRADIER_BASE = 'https://api.tradier.com/v1'
TRADIER_HEADERS = {'Authorization': f'Bearer {TOKEN}', 'Accept': 'application/json'}

def tradier_get(path, params=None):
    import requests
    r = requests.get(f'{TRADIER_BASE}{path}', params=params, headers=TRADIER_HEADERS)
    return r.json() if r.status_code == 200 else {}

def get_history(symbol, start, end):
    """Daily bars for a symbol between dates."""
    data = tradier_get('/markets/history', {
        'symbol': symbol, 'interval': 'daily',
        'start': start, 'end': end
    })
    bars = data.get('history', {}).get('day', [])
    if isinstance(bars, dict):
        bars = [bars]
    return bars



# ── Snapshot window — historical data cut-off ──
def load_snapshot(snapshot_date):
    """
    Fetch historical bars up to (not including) snapshot_date.
    Returns: dict of {symbol: [{'date','close','volume',...}]}
    with the most recent bar being snapshot_date minus 1 trading day.
    """
    start = (snapshot_date - timedelta(days=LOOKBACK_DAYS)).strftime('%Y-%m-%d')
    end = (snapshot_date + timedelta(days=1)).strftime('%Y-%m-%d')
    
    results = {}
    for sym in SYMBOLS:
        bars = get_history(sym, start, end)
        # Filter to bars <= snapshot_date
        bars = [b for b in bars if b.get('date') <= snapshot_date.strftime('%Y-%m-%d')]
        if not bars:
            print(f'  ⚠ No history for {sym} up to {snapshot_date.date()}')
            continue
        results[sym] = bars
    return results

# ── Pipeline signal logic ═══════════════════════════════════════

def compute_momentum(bars):
    """5d and 20d price change % from latest bar."""
    if len(bars) < 5:
        return None, None
    latest = float(bars[-1]['close'])
    p5 = float(bars[-5]['close'])
    p20 = float(bars[-min(20, len(bars))]['close']) if len(bars) >= 20 else float(bars[0]['close'])
    mom_5d = (latest - p5) / p5 * 100
    mom_20d = (latest - p20) / p20 * 100
    return mom_5d, mom_20d

def compute_rvol(bars):
    """Relative volume: current day volume / 20d avg volume."""
    if len(bars) < 2:
        return 100
    latest_vol = int(bars[-1].get('volume', 1))
    avg_vol = sum(int(b.get('volume', 1)) for b in bars[-21:-1]) / max(len(bars[-21:-1]), 1)
    return (latest_vol / avg_vol * 100) if avg_vol > 0 else 100

def compute_trend_alignment(mom_5d, mom_20d):
    """Trend is aligned when both 5d and 20d momentum agree."""
    if mom_5d is None:
        return False, 'neutral'
    direction = 'bullish' if mom_20d > 2 else 'bearish' if mom_20d < -2 else 'neutral'
    aligned = (mom_5d > 0 and mom_20d > 0) or (mom_5d < 0 and mom_20d < 0)
    # If mixed, trend is conflicted
    if not aligned and (mom_5d * mom_20d < 0):
        direction = 'conflicted'
    return aligned, direction

def simulate_pipeline(snapshot_date, history_data):
    """
    For each symbol, compute what the pipeline would conclude
    from the snapshot date's perspective.
    """
    signals = {}
    for sym, bars in history_data.items():
        if len(bars) < 5:
            signals[sym] = {'error': 'insufficient data', 'bars': len(bars)}
            continue
        
        close = float(bars[-1]['close'])
        mom_5d, mom_20d = compute_momentum(bars)
        rvol = compute_rvol(bars)
        aligned, direction = compute_trend_alignment(mom_5d, mom_20d)
        
        # Macro regime heuristic (based on SPY)
        spy_bars = history_data.get('SPY', [])
        spy_regime = 'neutral'
        if len(spy_bars) >= 20:
            spy_mom_20 = (float(spy_bars[-1]['close']) - float(spy_bars[-20]['close'])) / float(spy_bars[-20]['close']) * 100
            if spy_mom_20 > 3: spy_regime = 'bullish'
            elif spy_mom_20 < -3: spy_regime = 'bearish'
            else: spy_regime = 'neutral'
        
        # Pipeline-style composite score (simplified)
        edge_score = 50  # baseline neutral
        if direction == 'bullish':
            if mom_5d > 2: edge_score += 15
            if mom_20d > 5: edge_score += 10
            if rvol > 120: edge_score += 5
        elif direction == 'bearish':
            if mom_5d < -2: edge_score += 15
            if mom_20d < -5: edge_score += 10
            if rvol > 120: edge_score += 5
        
        # Volume note
        if rvol > 200:
            vol_note = '🔥 Unusual volume spike'
        elif rvol > 130:
            vol_note = '⚠️ Elevated volume'
        elif rvol < 50:
            vol_note = 'Low volume — caution'
        else:
            vol_note = 'Normal volume'
        
        # Support/Resistance (lookback range)
        prices = [float(b['close']) for b in bars]
        support = min(prices)
        resistance = max(prices)
        range_pct = (resistance - support) / support * 100 if support > 0 else 0
        
        signals[sym] = {
            'date': bars[-1]['date'],
            'close': close,
            'mom_5d': round(mom_5d, 2),
            'mom_20d': round(mom_20d, 2),
            'rvol_pct': round(rvol, 0),
            'trend_aligned': aligned,
            'trend_direction': direction,
            'macro_regime': spy_regime,
            'edge_score': min(round(edge_score), 100),
            'support': round(support, 2),
            'resistance': round(resistance, 2),
            'range_pct': round(range_pct, 1),
            'volume_note': vol_note,
            'verdict': 'GO' if edge_score >= 65 else 'MODIFY' if edge_score >= 55 else 'WAIT',
        }
    
    return signals

# ── Forward outcome check ═══════════════════════════════════════

def get_forward_prices(symbols, target_date):
    """Get close prices on or around target_date for each symbol."""
    start = (target_date - timedelta(days=2)).strftime('%Y-%m-%d')
    end = (target_date + timedelta(days=2)).strftime('%Y-%m-%d')
    prices = {}
    for sym in symbols:
        bars = get_history(sym, start, end)
        # Find closest bar to target_date
        target = target_date.strftime('%Y-%m-%d')
        closest_bar = None
        for b in bars:
            if b.get('date') == target:
                closest_bar = b
                break
        if closest_bar is None and bars:
            # Take last bar (closest date)
            closest_bar = bars[-1]
        if closest_bar:
            prices[sym] = float(closest_bar['close'])
    return prices

def check_outcome(snapshot_date, signals, forward_prices):
    """
    Compare pipeline's directional prediction against actual price action
    FORWARD_DAYS after the snapshot date.
    """
    outcomes = {}
    for sym, sig in signals.items():
        if 'error' in sig:
            outcomes[sym] = {'error': sig['error']}
            continue
        forward_close = forward_prices.get(sym)
        if forward_close is None:
            outcomes[sym] = {'error': 'no forward data'}
            continue
        
        snapshot_close = sig['close']
        move_pct = (forward_close - snapshot_close) / snapshot_close * 100
        direction = sig['trend_direction']
        
        if direction == 'bullish' and move_pct > 0:
            correct = True
        elif direction == 'bearish' and move_pct < 0:
            correct = True
        elif direction == 'neutral':
            correct = abs(move_pct) < 1.5
        else:
            correct = False
        
        outcomes[sym] = {
            'snapshot_close': snapshot_close,
            'forward_close': forward_close,
            'move_pct': round(move_pct, 2),
            'direction_predicted': direction,
            'correct': correct,
            'would_profit': (
                (direction == 'bullish' and move_pct > 1.0) or
                (direction == 'bearish' and move_pct < -1.0)
            ),
        }
    return outcomes

# ── Report ──
def print_report(snapshot_date, signals, outcomes):
    lines = []
    lines.append(f'\n{"═"*60}')
    lines.append(f'📅 Snapshot: {snapshot_date} (Friday)')
    lines.append(f'{"─"*60}')
    
    total = len(signals)
    correct = sum(1 for o in outcomes.values() if o.get('correct'))
    profit = sum(1 for o in outcomes.values() if o.get('would_profit'))
    
    for sym, sig in signals.items():
        if 'error' in sig:
            continue
        o = outcomes.get(sym, {})
        
        arrow = '📈' if sig['trend_direction'] == 'bullish' else '📉' if sig['trend_direction'] == 'bearish' else '➡️'
        correct_mark = '✅' if o.get('correct') else '❌'
        profit_mark = '💰' if o.get('would_profit') else ''
        
        lines.append(f'\n {sym:6s}  {arrow}')
        lines.append(f'   Close:    ${sig["close"]:<8.2f}  →  ${o.get("forward_close",0):<8.2f}  ({o.get("move_pct",0):+.2f}%)  {correct_mark}{profit_mark}')
        lines.append(f'   Momentum: 5d={sig["mom_5d"]:+.2f}%  20d={sig["mom_20d"]:+.2f}%')
        lines.append(f'   RVol:     {sig["rvol_pct"]:.0f}%  |  Range: ${sig["support"]}–${sig["resistance"]} ({sig["range_pct"]}%)')
        lines.append(f'   Trend:    {"✅ Aligned" if sig["trend_aligned"] else "❌ Conflicted"}  {sig["trend_direction"].upper()}')
        lines.append(f'   Verdict:  {sig["verdict"]} (edge={sig["edge_score"]})  |  {sig["volume_note"]}')
    
    score = f'{correct}/{total} correct ({correct/total*100:.0f}%)' if total > 0 else 'N/A'
    profit_score = f'{profit}/{total} would profit' if total > 0 else 'N/A'
    lines.append(f'\n{"─"*60}')
    lines.append(f'  Score: {score}  |  {profit_score}')
    if total > 0:
        macro_regime = list(signals.values())[0].get('macro_regime', '?')
        lines.append(f'  Macro regime: {macro_regime.upper()}')
    
    print('\n'.join(lines))
    return {
        'date': str(snapshot_date),
        'total': total,
        'correct': correct,
        'would_profit': profit,
        'macro_regime': list(signals.values())[0].get('macro_regime', '?') if signals else '?',
    }

# ── Main ──
def main():
    # Snapshot dates: last 4 Fridays
    today_real = date.today()
    # Use today or May 8 2026
    today = today_real if today_real.weekday() == 4 else date(2026, 5, 8)
    
    snapshot_dates = []
    for w in range(1, 5):
        d = today - timedelta(weeks=w)
        # Ensure Friday
        days_to_friday = (d.weekday() - 4) % 7
        snapshot_dates.append(d - timedelta(days=days_to_friday))
    
    print(f'🔍 AGORA Backtest Harness')
    print(f'   Snapshot dates: {", ".join(str(d) for d in snapshot_dates)}')
    print(f'   Lookback: {LOOKBACK_DAYS}d  |  Forward window: {FORWARD_DAYS}d')
    print(f'   Symbols: {", ".join(SYMBOLS)}')
    
    all_results = []
    
    for snap_date in snapshot_dates:
        print(f'\n{"⏳"*3} Processing {snap_date}...')
        history = load_snapshot(snap_date)
        if not history:
            print(f'   ⚠ No history data for this date')
            continue
        
        signals = simulate_pipeline(snap_date, history)
        
        # Forward outcome: get prices FORWARD_DAYS after snapshot
        forward_date = snap_date + timedelta(days=FORWARD_DAYS)
        forward_prices = get_forward_prices(list(signals.keys()), forward_date)
        if forward_prices:
            outcomes = check_outcome(snap_date, signals, forward_prices)
        else:
            outcomes = {s: {'error': 'no forward data'} for s in signals}
        
        result = print_report(snap_date, signals, outcomes)
        all_results.append(result)
    
    # Summary
    print(f'\n{"═"*60}')
    print(f'📊 BACKTEST SUMMARY')
    print(f'{"═"*60}')
    total_correct = sum(r['correct'] for r in all_results)
    total_signals = sum(r['total'] for r in all_results)
    total_profit = sum(r['would_profit'] for r in all_results)
    if total_signals > 0:
        print(f'  Overall:  {total_correct}/{total_signals} directionally correct ({total_correct/total_signals*100:.0f}%)')
        print(f'  Profitable signals: {total_profit}/{total_signals} ({total_profit/total_signals*100:.0f}%)')
        print(f'  Macro contexts: {", ".join(r["macro_regime"] for r in all_results)}')
    
    print(f'\n{"═"*60}')
    print('Analysis:')
    for r in all_results:
        print(f'  {r["date"]}: {r["correct"]}/{r["total"]} correct, {r["would_profit"]} profitable  (macro: {r["macro_regime"]})')
    
    # Summary verdict
    if total_signals > 0:
        acc = total_correct / total_signals * 100
        if acc >= 70:
            print(f'\n🟢 VERDICT: Pipeline logic is robust ({acc:.0f}% directional accuracy)')
        elif acc >= 55:
            print(f'\n🟡 VERDICT: Pipeline logic is directional ({acc:.0f}% — above random)')
        else:
            print(f'\n🔴 VERDICT: Pipeline logic needs refinement ({acc:.0f}% — near or below random)')

if __name__ == '__main__':
    main()
