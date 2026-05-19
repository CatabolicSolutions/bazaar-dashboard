#!/usr/bin/env python3
"""Historical replay harness for brand-new 3-state rotation logic.

Uses clean market history only (no legacy WETH decision artifacts) and simulates a
simple three-state engine across ETH/USD history:
- USDC
- ETH
- BTC (placeholder path for future multi-asset extension; inactive if no BTC history)

Tonight's first shipped version focuses on ETH-vs-USDC rotation quality using the
new state-machine shape, while keeping the schema ready for BTC extension.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
ETH_PATH = ROOT / 'eth_scalper' / 'out_eth_market_chart_30d.json'
OUT_DIR = ROOT / 'eth_scalper' / 'out'
OUT_DIR.mkdir(parents=True, exist_ok=True)

DATASET_PATH = OUT_DIR / 'three_state_replay_dataset.json'
TRADES_PATH = OUT_DIR / 'three_state_replay_trades.json'
SUMMARY_PATH = OUT_DIR / 'three_state_replay_summary.json'

import os

INITIAL_USDC = 150.0
FEE_PCT = 0.05

LOOKBACK = int(os.getenv('LOOKBACK', '12'))
ENTRY_DISCOUNT_PCT = float(os.getenv('ENTRY_DISCOUNT_PCT', '0.60'))
REENTRY_RECOVER_PCT = float(os.getenv('REENTRY_RECOVER_PCT', '0.22'))
EXIT_EXTENSION_PCT = float(os.getenv('EXIT_EXTENSION_PCT', '0.45'))
STOP_PCT = float(os.getenv('STOP_PCT', '0.60'))
MAX_HOLD_BARS = int(os.getenv('MAX_HOLD_BARS', '6'))
COOLDOWN_BARS = int(os.getenv('COOLDOWN_BARS', '3'))


@dataclass
class Trade:
    entry_idx: int
    exit_idx: int
    entry_ts: int
    exit_ts: int
    entry_price: float
    exit_price: float
    units: float
    gross_pnl_usd: float
    net_pnl_usd: float
    net_pct: float
    hold_bars: int
    entry_reason: str
    exit_reason: str


class State:
    def __init__(self):
        self.side = 'USDC'
        self.usdc = INITIAL_USDC
        self.eth_units = 0.0
        self.entry_price: Optional[float] = None
        self.entry_idx: Optional[int] = None
        self.entry_ts: Optional[int] = None
        self.peak_price: Optional[float] = None
        self.last_exit_idx = -999999
        self.trades: list[Trade] = []


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_eth_history() -> list[dict]:
    obj = json.loads(ETH_PATH.read_text())
    prices = obj['prices']
    vols = obj.get('total_volumes', [])
    out = []
    for i, pair in enumerate(prices):
        ts, price = pair
        volume = vols[i][1] if i < len(vols) else 0.0
        out.append({'ts': int(ts), 'price': float(price), 'volume': float(volume)})
    return out


def pct(a: float, b: float) -> float:
    if not b:
        return 0.0
    return ((a - b) / b) * 100.0


def build_dataset(rows: list[dict]) -> list[dict]:
    out = []
    for i, row in enumerate(rows):
        start = max(0, i - (LOOKBACK - 1))
        win = rows[start:i + 1]
        prices = [r['price'] for r in win]
        vols = [r.get('volume', 0.0) for r in win]
        midpoint = sum(prices) / len(prices)
        window_low = min(prices)
        window_high = max(prices)
        prev = rows[i - 1]['price'] if i >= 1 else row['price']
        prev2 = rows[i - 2]['price'] if i >= 2 else prev
        last_change = pct(row['price'], prev)
        prev_change = pct(prev, prev2)
        reversal_strength = 0.0
        if prev_change < 0 < last_change:
            reversal_strength = abs(prev_change) + abs(last_change)
        distance_from_mid = pct(row['price'], midpoint)
        discount_from_high = pct(window_high, row['price'])
        bounce_from_low = pct(row['price'], window_low)
        volatility = pct(window_high, midpoint)
        avg_vol = (sum(vols) / len(vols)) if vols else 0.0
        volume_ratio = (row['volume'] / avg_vol) if avg_vol else 1.0
        reentry_score = max(0.0, (discount_from_high * 0.5) + (reversal_strength * 0.3) + (max(last_change, 0.0) * 0.2))
        out.append({
            **row,
            'midpoint': midpoint,
            'window_low': window_low,
            'window_high': window_high,
            'distance_from_mid_pct': distance_from_mid,
            'discount_from_high_pct': discount_from_high,
            'bounce_from_low_pct': bounce_from_low,
            'reversal_strength_pct': reversal_strength,
            'last_change_pct': last_change,
            'prev_change_pct': prev_change,
            'volatility_pct': volatility,
            'volume_ratio': volume_ratio,
            'reentry_score': reentry_score,
        })
    return out


def buy_fee_multiplier() -> float:
    return 1 - (FEE_PCT / 100.0)


def sell_fee_multiplier() -> float:
    return 1 - (FEE_PCT / 100.0)


def should_enter(row: dict, idx: int, state: State) -> tuple[bool, str]:
    if idx - state.last_exit_idx <= COOLDOWN_BARS:
        return False, 'cooldown'
    if row['price'] > row['midpoint']:
        return False, 'above_midpoint'
    if row['discount_from_high_pct'] < ENTRY_DISCOUNT_PCT:
        return False, 'discount_too_small'
    if row['bounce_from_low_pct'] < REENTRY_RECOVER_PCT:
        return False, 'bounce_too_small'
    if row['reversal_strength_pct'] <= 0:
        return False, 'no_reversal'
    if row['last_change_pct'] <= 0:
        return False, 'no_positive_turn'
    return True, 'discounted_reversal_reentry'


def should_exit(row: dict, idx: int, state: State) -> tuple[bool, str]:
    assert state.entry_price is not None
    assert state.entry_idx is not None
    change_pct = pct(row['price'], state.entry_price)
    hold_bars = idx - state.entry_idx
    peak_price = max(state.peak_price or row['price'], row['price'])
    peak_gain_pct = pct(peak_price, state.entry_price)
    retrace_from_peak_pct = pct(peak_price, row['price'])
    state.peak_price = peak_price

    if change_pct <= -STOP_PCT:
        return True, 'hard_stop'
    if hold_bars >= MAX_HOLD_BARS:
        return True, 'timeout'
    if peak_gain_pct >= EXIT_EXTENSION_PCT and retrace_from_peak_pct >= 0.12:
        return True, 'take_profit_retrace'
    if row['price'] >= row['midpoint'] and change_pct >= 0.20:
        return True, 'mean_reclaim_exit'
    return False, 'hold'


def run_replay(dataset: list[dict]) -> State:
    state = State()
    for idx, row in enumerate(dataset):
        if state.side == 'USDC':
            enter, reason = should_enter(row, idx, state)
            if not enter:
                continue
            units = (state.usdc / row['price']) * buy_fee_multiplier()
            state.eth_units = units
            state.usdc = 0.0
            state.side = 'ETH'
            state.entry_price = row['price']
            state.entry_idx = idx
            state.entry_ts = row['ts']
            state.peak_price = row['price']
        else:
            exit_now, reason = should_exit(row, idx, state)
            if not exit_now:
                continue
            gross_value = state.eth_units * row['price']
            net_value = gross_value * sell_fee_multiplier()
            gross_cost = state.eth_units * (state.entry_price or row['price'])
            gross_pnl = gross_value - gross_cost
            net_pnl = net_value - gross_cost
            net_pct = (net_pnl / gross_cost * 100.0) if gross_cost else 0.0
            trade = Trade(
                entry_idx=state.entry_idx,
                exit_idx=idx,
                entry_ts=state.entry_ts,
                exit_ts=row['ts'],
                entry_price=state.entry_price,
                exit_price=row['price'],
                units=state.eth_units,
                gross_pnl_usd=gross_pnl,
                net_pnl_usd=net_pnl,
                net_pct=net_pct,
                hold_bars=idx - state.entry_idx,
                entry_reason='discounted_reversal_reentry',
                exit_reason=reason,
            )
            state.trades.append(trade)
            state.usdc = net_value
            state.eth_units = 0.0
            state.side = 'USDC'
            state.entry_price = None
            state.entry_idx = None
            state.entry_ts = None
            state.peak_price = None
            state.last_exit_idx = idx
    return state


def summarize(dataset: list[dict], state: State) -> dict:
    trades = state.trades
    wins = [t for t in trades if t.net_pnl_usd > 0]
    losses = [t for t in trades if t.net_pnl_usd <= 0]
    timeout_exits = [t for t in trades if t.exit_reason == 'timeout']
    final_mark = dataset[-1]['price'] if dataset else None
    final_equity = state.usdc if state.side == 'USDC' else (state.eth_units * final_mark if final_mark else state.usdc)
    total_return_pct = ((final_equity - INITIAL_USDC) / INITIAL_USDC * 100.0) if final_equity is not None else None
    starting_eth_equiv = (INITIAL_USDC / dataset[0]['price']) if dataset else None
    ending_eth_equiv = (final_equity / final_mark) if (final_equity is not None and final_mark) else None
    eth_equiv_delta = (ending_eth_equiv - starting_eth_equiv) if (starting_eth_equiv is not None and ending_eth_equiv is not None) else None
    eth_equiv_return_pct = ((eth_equiv_delta / starting_eth_equiv) * 100.0) if (starting_eth_equiv and eth_equiv_delta is not None) else None
    return {
        'generated_at': now_iso(),
        'source': str(ETH_PATH.relative_to(ROOT)),
        'rows': len(dataset),
        'initial_usdc': INITIAL_USDC,
        'initial_eth_equiv_units': starting_eth_equiv,
        'final_side': state.side,
        'final_equity_usd': final_equity,
        'final_eth_equiv_units': ending_eth_equiv,
        'eth_equiv_delta_units': eth_equiv_delta,
        'eth_equiv_return_pct': eth_equiv_return_pct,
        'total_return_pct': total_return_pct,
        'trade_count': len(trades),
        'win_count': len(wins),
        'loss_count': len(losses),
        'win_rate': (len(wins) / len(trades)) if trades else None,
        'avg_net_pnl_usd': (sum(t.net_pnl_usd for t in trades) / len(trades)) if trades else None,
        'avg_net_pct': (sum(t.net_pct for t in trades) / len(trades)) if trades else None,
        'total_net_pnl_usd': sum(t.net_pnl_usd for t in trades) if trades else 0.0,
        'avg_hold_bars': (sum(t.hold_bars for t in trades) / len(trades)) if trades else None,
        'timeout_exit_count': len(timeout_exits),
        'exit_reason_counts': {
            key: sum(1 for t in trades if t.exit_reason == key)
            for key in sorted({t.exit_reason for t in trades})
        },
        'objective': {
            'primary': 'eth_equivalent_unit_accumulation',
            'starting_units': starting_eth_equiv,
            'ending_units': ending_eth_equiv,
            'delta_units': eth_equiv_delta,
            'return_pct': eth_equiv_return_pct,
        },
        'parameters': {
            'lookback': LOOKBACK,
            'entry_discount_pct': ENTRY_DISCOUNT_PCT,
            'reentry_recover_pct': REENTRY_RECOVER_PCT,
            'exit_extension_pct': EXIT_EXTENSION_PCT,
            'stop_pct': STOP_PCT,
            'max_hold_bars': MAX_HOLD_BARS,
            'cooldown_bars': COOLDOWN_BARS,
            'fee_pct_per_side': FEE_PCT,
        },
        'sample_trades': [asdict(t) for t in trades[:12]],
    }


def main() -> None:
    rows = load_eth_history()
    dataset = build_dataset(rows)
    state = run_replay(dataset)
    summary = summarize(dataset, state)

    DATASET_PATH.write_text(json.dumps(dataset, indent=2))
    TRADES_PATH.write_text(json.dumps([asdict(t) for t in state.trades], indent=2))
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
