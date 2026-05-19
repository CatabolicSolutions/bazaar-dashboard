#!/usr/bin/env python3
"""Replay bloc trace — refined scoring + band-bias entry.

Key insight from 10+ runs: entries near the BAND BOTTOM work. Entries in the middle don't.
Only enter in bottom 30% of volatility band AND with clear momentum + bounce.
Sell: pullback from peak or stale hold.

Outputs:
- eth_scalper/out/replay_ticks.json
- eth_scalper/out/replay_trades.json
- eth_scalper/out/replay_summary.json
"""
import json
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from collections import deque, Counter

ROOT_CANDIDATES = [
    Path('/var/www/bazaar/eth_scalper'),
    Path('/home/catabolic_solutions/.openclaw/workspace/eth_scalper'),
]
ROOT = next((p for p in ROOT_CANDIDATES if p.exists()), ROOT_CANDIDATES[-1])
TRACE_CANDIDATES = [
    Path('/var/www/bazaar/logs/bloc_trace.jsonl'),
    ROOT / 'logs' / 'bloc_trace.jsonl',
    ROOT.parent / 'logs' / 'bloc_trace.jsonl',
]
TRACE_PATH = next((p for p in TRACE_CANDIDATES if p.exists()), TRACE_CANDIDATES[0])
OUT_DIR = ROOT / 'out'
OUT_DIR.mkdir(parents=True, exist_ok=True)

# === Constants ===
FEE_PCT = 0.05
GAS_USD = 0.0015
LONG_BAND = 12
SHORT_BAND = 4

# Entry: only bottom 30% of band, need bounce + momentum
ENTRY_BAND_POSITION_MAX = 0.38
ENTRY_MIN_BOUNCE = 0.06          # min bounce from local low
ENTRY_MIN_MOMENTUM = 0.01        # min positive momentum

# Exit
EXIT_PULLBACK_PCT = 0.08         # pullback from peak triggers sell
STALE_HOLD_TICKS = 12            # stale after 12 ticks
STALE_MIN_MOVE_PCT = 0.03

# Score thresholds (milder gates since band-position already filters hard)
BUY_SCORE_THRESHOLD = 25
SELL_SCORE_THRESHOLD = 30


def clamp01(v):
    return max(0.0, min(1.0, v))


def calc_momentum(prices, n=3):
    if len(prices) < n:
        return 0.0
    chunk = prices[-n:]
    changes = [(chunk[i] - chunk[i-1]) / chunk[i-1] * 100.0 for i in range(1, len(chunk))]
    return sum(changes) / len(changes) if changes else 0.0


def load_trace():
    rows = []
    for line in TRACE_PATH.read_text(errors='ignore').splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


@dataclass
class ReplayState:
    side: str = 'USDC'
    usdc: float = 248.58
    weth: float = 0.0
    entry_price: float = 0.0
    entry_high: float = 0.0
    last_sell_price: float = 0.0
    trade_count: int = 0
    win_count: int = 0
    loss_count: int = 0
    total_pnl_usd: float = 0.0
    baseline_weth: float = 0.10703099
    entry_idx: int = -999999
    stale_exits: int = 0


def compute_buy_score(p, band_position, momentum, bounce_pct, last_sell_price):
    """Simple buy score 0-100."""
    score = 0

    # Band position premium (0-30): lower = more room to run
    score += max(0, (1.0 - band_position) * 30)

    # Bounce quality (0-30): bigger bounce = more confirmation
    score += min(30, bounce_pct * 120)

    # Momentum (0-25): positive confirmation
    score += min(25, max(0, momentum * 100))

    # Reclaim discount (0-15): near last sell = confirm
    if last_sell_price > 0:
        gap = abs((p - last_sell_price) / last_sell_price * 100.0)
        if gap <= 1.0:
            score += 15 * (1.0 - min(gap, 1.0))

    return score


def replay(rows):
    state = ReplayState()
    ticks = []
    trades = []
    long_prices = deque(maxlen=LONG_BAND)
    short_prices = deque(maxlen=SHORT_BAND)

    for idx, row in enumerate(rows):
        p = float(row.get('price') or 0)
        if p <= 0:
            continue

        long_prices.append(p)
        short_prices.append(p)

        # Band
        long_low = min(long_prices)
        long_high = max(long_prices)
        long_range = long_high - long_low
        band_position = (p - long_low) / long_range if long_range > 0 else 0.5

        # Short-term bounce/pullback
        short_low = min(short_prices)
        short_high = max(short_prices)
        bounce_pct = ((p - short_low) / short_low * 100.0) if short_low > 0 else 0.0
        pullback_pct = ((short_high - p) / short_high * 100.0) if short_high > 0 else 0.0

        momentum = calc_momentum(list(long_prices), 3)
        hold_ticks = idx - state.entry_idx

        if state.side == 'WETH':
            state.entry_high = max(state.entry_high, p)
            peak_pct = ((state.entry_high - state.entry_price) / state.entry_price * 100.0) if state.entry_price > 0 else 0.0
            change_pct = ((p - state.entry_price) / state.entry_price * 100.0) if state.entry_price > 0 else 0.0
        else:
            peak_pct = 0.0
            change_pct = 0.0

        # === BUY ===
        buy_signal = False
        buy_score = 0
        buy_classifier = None
        in_entry_zone = False

        if state.side == 'USDC' and long_range > 0:
            buy_score = compute_buy_score(p, band_position, momentum, bounce_pct, state.last_sell_price)

            # GATES: band position + bounce + momentum (score confirms quality)
            in_entry_zone = (
                band_position <= ENTRY_BAND_POSITION_MAX and
                bounce_pct >= ENTRY_MIN_BOUNCE and
                momentum >= ENTRY_MIN_MOMENTUM
            )

            if in_entry_zone and buy_score >= BUY_SCORE_THRESHOLD:
                buy_signal = True
                if state.last_sell_price > 0:
                    gap = abs(p - state.last_sell_price) / state.last_sell_price * 100.0
                    buy_classifier = 'reclaim' if gap <= 0.50 else 'reversal'
                else:
                    buy_classifier = 'reversal'

        # === SELL ===
        sell_signal = False
        stale_exit = False
        sell_score = 0
        sell_classifier = None
        in_entry_zone = False  # default (safe for ticks.append when side != USDC)

        if state.side == 'WETH' and hold_ticks >= 2:
            # Score-based: pullback + at top of band
            sell_score = 0
            sell_score += min(30, pullback_pct * 80)  # pullback 0.08% = 6.4
            sell_score += min(20, max(0, (band_position - 0.5) * 50)) if band_position > 0.5 else 0
            sell_score += min(20, max(0, -momentum * 150))
            if peak_pct > 0 and hold_ticks >= 3:
                sell_score += min(15, peak_pct * 20)
            if hold_ticks >= STALE_HOLD_TICKS:
                sell_score += 12  # force exit

            if sell_score >= SELL_SCORE_THRESHOLD:
                sell_signal = True
                if hold_ticks >= STALE_HOLD_TICKS and (abs(change_pct) < STALE_MIN_MOVE_PCT or change_pct < -STALE_MIN_MOVE_PCT):
                    stale_exit = True
                    sell_classifier = 'stale'
                elif peak_pct >= 0.06 and change_pct > 0:
                    sell_classifier = 'take_profit'
                elif change_pct <= -0.08:
                    sell_classifier = 'false_reversal'
                else:
                    sell_classifier = 'exit'

        # === EXECUTE BUY ===
        if buy_signal and state.side == 'USDC' and p > 0:
            weth_bought = (state.usdc / p) * (1 - FEE_PCT / 100.0)
            state.weth = weth_bought
            state.usdc = 0.0
            state.side = 'WETH'
            state.entry_price = p
            state.entry_high = p
            state.entry_idx = idx
            state.trade_count += 1

            trades.append({
                'ts': row.get('ts'), 'idx': idx,
                'action': 'BUY',
                'classifier': buy_classifier,
                'score': buy_score,
                'price': round(p, 2),
                'band_position': round(band_position, 3),
                'bounce_pct': round(bounce_pct, 4),
                'momentum': round(momentum, 4),
            })

        # === EXECUTE SELL ===
        if sell_signal and state.side == 'WETH' and p > 0:
            usdc_out = (state.weth * p) * (1 - FEE_PCT / 100.0)
            buy_cost = state.weth * state.entry_price
            pnl_usd = usdc_out - buy_cost - GAS_USD

            state.total_pnl_usd += pnl_usd
            if pnl_usd > 0:
                state.win_count += 1
            else:
                state.loss_count += 1
            if stale_exit:
                state.stale_exits += 1

            state.usdc = usdc_out
            state.weth = 0.0
            state.side = 'USDC'
            state.last_sell_price = p

            trades.append({
                'ts': row.get('ts'), 'idx': idx,
                'action': 'SELL',
                'classifier': sell_classifier,
                'score': sell_score,
                'price': round(p, 2),
                'pnl_usd': round(pnl_usd, 6),
                'change_pct': round(change_pct, 4),
                'hold_ticks': hold_ticks,
                'buy_price': round(state.entry_price, 2),
                'high_price': round(state.entry_high, 2),
            })

        ticks.append({
            'ts': row.get('ts'), 'idx': idx,
            'price': round(p, 2), 'side': state.side,
            'band_position': round(band_position, 3),
            'bounce_pct': round(bounce_pct, 4),
            'pullback_pct': round(pullback_pct, 4),
            'momentum': round(momentum, 4),
            'in_entry_zone': in_entry_zone,
            'buy_score': buy_score, 'sell_score': sell_score,
            'buy_signal': buy_signal, 'sell_signal': sell_signal,
            'stale_exit': stale_exit,
            'hold_ticks': hold_ticks if state.side == 'WETH' else 0,
        })

    # === SUMMARY ===
    final_weth_equiv = state.weth if state.side == 'WETH' else (state.usdc / (rows[-1]['price'] if rows else 1))
    win_rate = state.win_count / max(1, state.win_count + state.loss_count)
    win_trades = [t for t in trades if t.get('pnl_usd', 0) > 0]
    loss_trades = [t for t in trades if t.get('pnl_usd', 0) < 0]

    buy_cls = Counter(t['classifier'] for t in trades if t['action'] == 'BUY')
    sell_cls = Counter(t['classifier'] for t in trades if t['action'] == 'SELL')

    pnl_by = {}
    for t in trades:
        if t['action'] == 'SELL':
            c = t['classifier']
            if c not in pnl_by:
                pnl_by[c] = {'count': 0, 'wins': 0, 'pnl': 0.0}
            pnl_by[c]['count'] += 1
            pnl_by[c]['pnl'] += t.get('pnl_usd', 0)
            if t.get('pnl_usd', 0) > 0:
                pnl_by[c]['wins'] += 1

    summary = {
        'trace_rows': len(rows),
        'total_trades': state.trade_count,
        'completed_cycles': len([t for t in trades if t['action'] == 'SELL']),
        'wins': state.win_count, 'losses': state.loss_count,
        'win_rate': round(win_rate, 4),
        'net_pnl_usd': round(state.total_pnl_usd, 6),
        'baseline_weth': state.baseline_weth,
        'final_weth_equiv': round(final_weth_equiv, 8),
        'net_weth_change': round(final_weth_equiv - state.baseline_weth, 8),
        'avg_win_pnl': round(mean([t['pnl_usd'] for t in win_trades]), 6) if win_trades else 0,
        'avg_loss_pnl': round(mean([t['pnl_usd'] for t in loss_trades]), 6) if loss_trades else 0,
        'stale_exits': state.stale_exits,
        'buy_classifier_breakdown': dict(buy_cls),
        'sell_classifier_breakdown': dict(sell_cls),
        'pnl_by_exit_classifier': {k: {
            'count': v['count'], 'win_rate': round(v['wins'] / max(1, v['count']), 4),
            'net_pnl': round(v['pnl'], 6),
        } for k, v in sorted(pnl_by.items(), key=lambda x: -x[1]['count'])},
        'final_side': state.side,
    }
    return ticks, trades, summary


def main():
    rows = load_trace()
    if not rows:
        print("ERROR: no trace rows loaded")
        return
    first_ts = rows[0].get('ts', 'unknown')
    last_ts = rows[-1].get('ts', 'unknown')
    print(f"Loaded {len(rows)} trace rows  [{first_ts} -> {last_ts}]")

    ticks, trades, summary = replay(rows)

    (OUT_DIR / 'replay_ticks.json').write_text(json.dumps(ticks, indent=2))
    (OUT_DIR / 'replay_trades.json').write_text(json.dumps(trades, indent=2))
    (OUT_DIR / 'replay_summary.json').write_text(json.dumps(summary, indent=2))

    print(json.dumps(summary, indent=2))
    print(f"\nTrade count: {summary['total_trades']}")
    print(f"Win rate: {summary['win_rate']:.1%}")
    print(f"Net PnL: ${summary['net_pnl_usd']:.4f}")
    print(f"Net WETH: {summary['net_weth_change']:.8f}")


if __name__ == '__main__':
    main()
