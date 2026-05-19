#!/usr/bin/env python3
"""Replay harness aligned to the current bloc rotation architecture in the workspace.

This mirrors the decision shape implied by the available ETH/BTC components:
- multi-asset universe (ETH/BTC)
- midpoint / reversal / pullback signal structure
- all-in single-inventory posture that can bind to ETH or BTC
- accumulation-first scoring in base-inventory equivalent units

This is a harness-side correction toward ETH<->BTC rotation using the actual available
multi-asset signal architecture in `eth_scalper/`, while staying honest that the old
`live_main_vps.py` loop is still WETH<->USDC-specific.
"""
from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[2]
ETH_PATH = ROOT / 'eth_scalper' / 'out_eth_market_chart_30d.json'
BTC_PATH = ROOT / 'eth_scalper' / 'out_btc_market_chart_30d.json'
OUT_DIR = ROOT / 'eth_scalper' / 'out'
OUT_DIR.mkdir(parents=True, exist_ok=True)
SUMMARY_PATH = OUT_DIR / 'live_bloc_replay_summary.json'
TRADES_PATH = OUT_DIR / 'live_bloc_replay_trades.json'
TRACE_PATH = OUT_DIR / 'live_bloc_replay_trace.json'

# Mirrors live_main_vps.py defaults where possible
INITIAL_USDC = float(os.getenv('INITIAL_USDC', '150'))
FEE_FACTOR = 1 - 0.0005
EMA_12_ALPHA = 2 / (12 + 1)
EMA_50_ALPHA = 2 / (50 + 1)
DEQUE_MAX = int(os.getenv('DEQUE_MAX', '30'))
VOL_MULTIPLIER = float(os.getenv('VOL_MULTIPLIER', '1.10'))
VOL_FLOOR = float(os.getenv('VOL_FLOOR', '0.12'))
VOL_CAP = float(os.getenv('VOL_CAP', '3.00'))
PAIR_SPREAD_TRIGGER_PCT = float(os.getenv('PAIR_SPREAD_TRIGGER_PCT', '0.18'))
PAIR_REVERSAL_TRIGGER_PCT = float(os.getenv('PAIR_REVERSAL_TRIGGER_PCT', '0.08'))
PAIR_ROTATE_MIN_EDGE_PCT = float(os.getenv('PAIR_ROTATE_MIN_EDGE_PCT', '0.02'))
PAIR_ROTATE_EXIT_EDGE_PCT = float(os.getenv('PAIR_ROTATE_EXIT_EDGE_PCT', '0.01'))
PAIR_ENTRY_MIN_RELATIVE_STRENGTH_PCT = float(os.getenv('PAIR_ENTRY_MIN_RELATIVE_STRENGTH_PCT', '0.20'))
PAIR_ROTATION_COMMIT_PCT = float(os.getenv('PAIR_ROTATION_COMMIT_PCT', '0.08'))
PAIR_ROTATION_HOLD_BARS = int(os.getenv('PAIR_ROTATION_HOLD_BARS', '3'))
PAIR_USDC_EXIT_EDGE_PCT = float(os.getenv('PAIR_USDC_EXIT_EDGE_PCT', '0.18'))
PAIR_CHURN_GUARD_BARS = int(os.getenv('PAIR_CHURN_GUARD_BARS', '4'))
ROTATE_SIGNAL_LOOKBACK_BARS = int(os.getenv('ROTATE_SIGNAL_LOOKBACK_BARS', '12'))
ROTATE_SIGNAL_MOM_BARS = int(os.getenv('ROTATE_SIGNAL_MOM_BARS', '3'))
ROTATE_SIGNAL_MIN_EDGE_PCT = float(os.getenv('ROTATE_SIGNAL_MIN_EDGE_PCT', '0.12'))
ROTATE_SIGNAL_MIN_DEV_PCT = float(os.getenv('ROTATE_SIGNAL_MIN_DEV_PCT', '0.08'))
ROTATE_SIGNAL_MIN_SPREAD_MOVE_PCT = float(os.getenv('ROTATE_SIGNAL_MIN_SPREAD_MOVE_PCT', '0.03'))
ROTATE_SIGNAL_PERSIST_BARS = int(os.getenv('ROTATE_SIGNAL_PERSIST_BARS', '2'))
ROTATE_POST_HOLD_BARS = int(os.getenv('ROTATE_POST_HOLD_BARS', '6'))
ARM_WAIT_SUPPRESS_DURING_ROTATE = os.getenv('ARM_WAIT_SUPPRESS_DURING_ROTATE', 'true').lower() == 'true'
ARM_WAIT_MIN_ROTATE_EDGE_PCT = float(os.getenv('ARM_WAIT_MIN_ROTATE_EDGE_PCT', '0.18'))
REGIME_VOL_CHAOS_PCT = float(os.getenv('REGIME_VOL_CHAOS_PCT', '6.0'))
REGIME_VOL_CALM_PCT = float(os.getenv('REGIME_VOL_CALM_PCT', '1.5'))
VOL_FILTER = float(os.getenv('VOL_FILTER', '0.3'))
STOP_LOSS = float(os.getenv('STOP_LOSS', '0.75'))
MIN_WETH_ACCUMULATION_PCT = float(os.getenv('MIN_WETH_ACCUMULATION_PCT', '0.12'))
SELL_EXTENSION_MIN_PCT = float(os.getenv('SELL_EXTENSION_MIN_PCT', '0.15'))
SELL_RETRACE_TRIGGER_PCT = float(os.getenv('SELL_RETRACE_TRIGGER_PCT', '0.03'))
SELL_MIN_EXTENSION_EXIT_PCT = float(os.getenv('SELL_MIN_EXTENSION_EXIT_PCT', '0.75'))
SELL_ROLLOVER_RETRACE_PCT = float(os.getenv('SELL_ROLLOVER_RETRACE_PCT', '0.10'))
SELL_EXTENDED_PROFIT_EXIT_PCT = float(os.getenv('SELL_EXTENDED_PROFIT_EXIT_PCT', '0.85'))
MOMENTUM_HOLD_MIN_TICK_PCT = float(os.getenv('MOMENTUM_HOLD_MIN_TICK_PCT', '0.035'))
MOMENTUM_NEG_TICK_PCT = float(os.getenv('MOMENTUM_NEG_TICK_PCT', '-0.015'))
MOMENTUM_FADE_RATIO = float(os.getenv('MOMENTUM_FADE_RATIO', '0.55'))
REENTRY_RECOVER_ABOVE_SELL_PCT = float(os.getenv('REENTRY_RECOVER_ABOVE_SELL_PCT', '0.30'))
REENTRY_SCORE_THRESHOLD = float(os.getenv('REENTRY_SCORE_THRESHOLD', '0.42'))
REENTRY_SCORE_ARM_THRESHOLD = float(os.getenv('REENTRY_SCORE_ARM_THRESHOLD', '0.34'))
REENTRY_PARITY_BAND_PCT = float(os.getenv('REENTRY_PARITY_BAND_PCT', '0.06'))
REENTRY_FORCE_AFTER_BARS = int(os.getenv('REENTRY_FORCE_AFTER_BARS', '180'))
REENTRY_START_DISCOUNT_PCT = float(os.getenv('REENTRY_START_DISCOUNT_PCT', '0.10'))
REENTRY_END_PREMIUM_PCT = float(os.getenv('REENTRY_END_PREMIUM_PCT', '0.03'))
DEEP_REENTRY_DISCOUNT_PCT = float(os.getenv('DEEP_REENTRY_DISCOUNT_PCT', '1.0'))
DEEP_REENTRY_MIN_WETH_GAIN_PCT = float(os.getenv('DEEP_REENTRY_MIN_WETH_GAIN_PCT', '0.02'))
MISSED_REENTRY_RECOVERY_PCT = float(os.getenv('MISSED_REENTRY_RECOVERY_PCT', '0.55'))
REENTRY_REANALYZE_AFTER_BARS = int(os.getenv('REENTRY_REANALYZE_AFTER_BARS', '120'))
REENTRY_REANALYZE_VOL_MULTIPLIER = float(os.getenv('REENTRY_REANALYZE_VOL_MULTIPLIER', '0.55'))
REENTRY_REANALYZE_MAX_PREMIUM_PCT = float(os.getenv('REENTRY_REANALYZE_MAX_PREMIUM_PCT', '0.75'))
TWO_CYCLE_WETH_BONUS_WEIGHT = float(os.getenv('TWO_CYCLE_WETH_BONUS_WEIGHT', '0.25'))
COOLDOWN_BARS = int(os.getenv('COOLDOWN_BARS', '3'))


@dataclass
class Trade:
    idx: int
    ts: int
    action: str
    side_before: str
    side_after: str
    price: float
    entry_class: str | None
    hold_state: str | None
    weth_equiv_before: float
    weth_equiv_after: float
    net_unit_delta: float
    trigger: float
    reentry_score: float
    two_cycle_edge_pct: float
    weth_edge_pct: float


def clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def load_series(path: Path, symbol: str) -> list[dict]:
    obj = json.loads(path.read_text())
    return [{'ts': int(ts), 'symbol': symbol, 'price': float(px)} for ts, px in obj['prices']]


def align_rows() -> list[dict]:
    eth = load_series(ETH_PATH, 'ETH')
    btc = load_series(BTC_PATH, 'BTC')
    n = min(len(eth), len(btc))
    rows = []
    for i in range(n):
        rows.append({
            'ts': eth[i]['ts'],
            'ETH': eth[i]['price'],
            'BTC': btc[i]['price'],
        })
    return rows


def units_after_swap(source_units: float, source_price: float, target_price: float) -> float:
    if source_units <= 0 or source_price <= 0 or target_price <= 0:
        return 0.0
    usdc_value = source_units * source_price * FEE_FACTOR
    return (usdc_value / target_price) * FEE_FACTOR


def total_usd(side: str, units: float, current_price: float, usdc: float) -> float:
    return usdc if side == 'USDC' else (units * current_price)


def main() -> None:
    rows = align_rows()
    ema12 = {symbol: rows[0][symbol] for symbol in ('ETH', 'BTC')}
    ema50 = {symbol: rows[0][symbol] for symbol in ('ETH', 'BTC')}
    side = 'USDC'
    holding_symbol = None
    usdc = INITIAL_USDC
    units = 0.0
    entry_price = None
    last_sell_price = {'ETH': 0.0, 'BTC': 0.0}
    sell_peak_price = 0.0
    last_flip_idx = -999999
    last_entry_idx = -999999
    last_rotation_idx = -999999
    post_rotate_hold_until = -999999
    deep_reentry_seen = False
    deep_reentry_low = 0.0
    dq = deque(maxlen=DEQUE_MAX)
    trades: list[Trade] = []
    trace = []
    rotate_signal_state = {'signal': 'NONE', 'streak': 0}

    for idx, row in enumerate(rows):
        if idx == 0:
            dq.append({'ETH': rows[0]['ETH'], 'BTC': rows[0]['BTC'], 'spread_pct': ((rows[0]['ETH']/rows[0]['BTC'])-1)*100.0, 'tick_change_pct': 0.0, 'anchor_distance_pct': 0.0})
            continue

        for symbol in ('ETH', 'BTC'):
            p = row[symbol]
            ema12[symbol] = p * EMA_12_ALPHA + ema12[symbol] * (1 - EMA_12_ALPHA)
            ema50[symbol] = p * EMA_50_ALPHA + ema50[symbol] * (1 - EMA_50_ALPHA)
        spread_now = (row['ETH'] / row['BTC']) if row['BTC'] > 0 else 0.0
        spread_prev = (rows[idx-1]['ETH'] / rows[idx-1]['BTC']) if rows[idx-1]['BTC'] > 0 else spread_now
        tick_change_pct = ((spread_now - spread_prev) / spread_prev) * 100.0 if spread_prev else 0.0
        anchor_distance_pct = abs((spread_now - (ema12['ETH'] / ema12['BTC'])) / (ema12['ETH'] / ema12['BTC'])) * 100 if ema12['BTC'] else 0.0
        dq.append({'ETH': row['ETH'], 'BTC': row['BTC'], 'spread_pct': spread_now, 'tick_change_pct': tick_change_pct, 'anchor_distance_pct': anchor_distance_pct})
        avg_vol = sum(x['anchor_distance_pct'] for x in dq) / len(dq) if dq else 0.0
        recent_ticks = [x['tick_change_pct'] for x in list(dq)[-5:]]
        spread_lookback = [x['spread_pct'] for x in list(dq)[-ROTATE_SIGNAL_LOOKBACK_BARS:]]
        momentum_peak = max(recent_ticks) if recent_ticks else 0.0
        momentum_now = recent_ticks[-1] if recent_ticks else 0.0
        prev_momentum = recent_ticks[-2] if len(recent_ticks) >= 2 else momentum_now

        current_price = row[holding_symbol] if holding_symbol else row['ETH']
        spread_anchor = (sum(spread_lookback) / len(spread_lookback)) if spread_lookback else spread_now
        spread_dev_pct = ((spread_now - spread_anchor) / spread_anchor * 100.0) if spread_anchor else 0.0
        mom_ref_idx = max(0, idx - ROTATE_SIGNAL_MOM_BARS)
        eth_mom_pct = ((row['ETH'] - rows[mom_ref_idx]['ETH']) / rows[mom_ref_idx]['ETH'] * 100.0) if rows[mom_ref_idx]['ETH'] else 0.0
        btc_mom_pct = ((row['BTC'] - rows[mom_ref_idx]['BTC']) / rows[mom_ref_idx]['BTC'] * 100.0) if rows[mom_ref_idx]['BTC'] else 0.0
        rotate_signal = 'NONE'
        rotate_edge_pct = 0.0
        if spread_dev_pct >= ROTATE_SIGNAL_MIN_DEV_PCT and tick_change_pct >= ROTATE_SIGNAL_MIN_SPREAD_MOVE_PCT and (btc_mom_pct - eth_mom_pct) >= ROTATE_SIGNAL_MIN_EDGE_PCT:
            rotate_signal = 'ROTATE_TO_BTC'
            rotate_edge_pct = btc_mom_pct - eth_mom_pct
        elif spread_dev_pct <= -ROTATE_SIGNAL_MIN_DEV_PCT and tick_change_pct <= -ROTATE_SIGNAL_MIN_SPREAD_MOVE_PCT and (eth_mom_pct - btc_mom_pct) >= ROTATE_SIGNAL_MIN_EDGE_PCT:
            rotate_signal = 'ROTATE_TO_ETH'
            rotate_edge_pct = eth_mom_pct - btc_mom_pct
        if rotate_signal == rotate_signal_state['signal'] and rotate_signal != 'NONE':
            rotate_signal_state['streak'] += 1
        elif rotate_signal != 'NONE':
            rotate_signal_state = {'signal': rotate_signal, 'streak': 1}
        else:
            rotate_signal_state = {'signal': 'NONE', 'streak': 0}
        if side != 'USDC':
            sell_peak_price = max(sell_peak_price or 0.0, current_price)
        else:
            sell_peak_price = 0.0
        peak_price = sell_peak_price or current_price
        extension_from_entry_pct = ((peak_price - entry_price) / entry_price * 100.0) if entry_price else 0.0
        retrace_from_peak_pct = ((peak_price - current_price) / peak_price * 100.0) if peak_price else 0.0
        extension_hold = side != 'USDC' and extension_from_entry_pct >= SELL_EXTENSION_MIN_PCT and retrace_from_peak_pct < SELL_RETRACE_TRIGGER_PCT
        regime_factor = 1.15 if avg_vol >= REGIME_VOL_CHAOS_PCT else (0.95 if avg_vol <= REGIME_VOL_CALM_PCT else 1.0)
        trigger = max(VOL_FLOOR, min(VOL_CAP, round(avg_vol * VOL_MULTIPLIER * regime_factor, 2)))
        cooldown_ok = (idx - last_flip_idx) >= COOLDOWN_BARS

        symbol_metrics = {}
        for symbol in ('ETH', 'BTC'):
            sp = row[symbol]
            exit_price = ema12[symbol] * (1 + trigger / 100.0)
            entry_target = ema12[symbol] * (1 - trigger / 100.0)
            stop_price = ema50[symbol] * (1 - STOP_LOSS / 100.0)
            symbol_metrics[symbol] = {'price': sp, 'exit_price': exit_price, 'entry_target': entry_target, 'stop_price': stop_price}
        active = symbol_metrics[holding_symbol] if holding_symbol else symbol_metrics['ETH']
        exit_price = active['exit_price']
        entry_target = active['entry_target']
        stop_price = active['stop_price']
        momentum_hold = side != 'USDC' and current_price >= exit_price and momentum_peak >= MOMENTUM_HOLD_MIN_TICK_PCT and momentum_now > max(MOMENTUM_NEG_TICK_PCT, momentum_peak * MOMENTUM_FADE_RATIO)
        continuation_hold = side != 'USDC' and ((current_price >= exit_price and (momentum_hold or extension_hold)) or (extension_from_entry_pct >= SELL_MIN_EXTENSION_EXIT_PCT and retrace_from_peak_pct < SELL_ROLLOVER_RETRACE_PCT and momentum_now > MOMENTUM_NEG_TICK_PCT))
        rollover_ready = side != 'USDC' and extension_from_entry_pct >= SELL_MIN_EXTENSION_EXIT_PCT and (retrace_from_peak_pct >= SELL_ROLLOVER_RETRACE_PCT or momentum_now <= MOMENTUM_NEG_TICK_PCT or (momentum_peak > 0 and momentum_now <= momentum_peak * MOMENTUM_FADE_RATIO))
        extended_profit_rollover_exit = side != 'USDC' and extension_from_entry_pct >= SELL_EXTENDED_PROFIT_EXIT_PCT and rollover_ready
        hold_state = 'continuation' if continuation_hold else ('rollover' if rollover_ready else ('armed' if side != 'USDC' and current_price >= exit_price else 'hold'))
        move_ok = anchor_distance_pct >= avg_vol * VOL_FILTER if avg_vol > 0 else True

        current_eth_equiv = units * (row[holding_symbol] / row['ETH']) if side != 'USDC' and holding_symbol else (usdc / row['ETH'] if row['ETH'] > 0 else 0.0)
        candidate = {}
        for symbol in ('ETH', 'BTC'):
            target_price = row[symbol]
            if side == 'USDC':
                projected_units = (usdc / target_price) * FEE_FACTOR if target_price > 0 else 0.0
            else:
                projected_units = units_after_swap(units, row[holding_symbol], target_price)
            projected_eth_equiv = projected_units if symbol == 'ETH' else ((projected_units * target_price) / row['ETH'] if row['ETH'] > 0 else 0.0)
            projected_delta_pct = (((projected_eth_equiv - current_eth_equiv) / current_eth_equiv) * 100.0) if current_eth_equiv > 0 else 0.0
            candidate[symbol] = {'projected_units': projected_units, 'projected_eth_equiv': projected_eth_equiv, 'edge_pct': projected_delta_pct}
        ranked_symbols = sorted(candidate.keys(), key=lambda s: candidate[s]['edge_pct'], reverse=True)
        best_symbol = ranked_symbols[0]
        second_symbol = ranked_symbols[1]
        best_edge_pct = candidate[best_symbol]['edge_pct']
        second_edge_pct = candidate[second_symbol]['edge_pct']
        relative_strength_pct = best_edge_pct - second_edge_pct
        weth_edge_pct = candidate[best_symbol]['edge_pct']
        weth_ok = weth_edge_pct >= MIN_WETH_ACCUMULATION_PCT
        if side == 'USDC' and last_sell_price[best_symbol] > 0 and row[best_symbol] <= last_sell_price[best_symbol] * (1 - DEEP_REENTRY_DISCOUNT_PCT / 100.0):
            deep_reentry_seen = True
            deep_reentry_low = min(deep_reentry_low or row[best_symbol], row[best_symbol])
        elif side != 'USDC':
            deep_reentry_seen = False
            deep_reentry_low = 0.0

        parity_anchor = last_sell_price[best_symbol] if last_sell_price[best_symbol] > 0 else ema12[best_symbol]
        time_since_flip = max(0, idx - last_flip_idx)
        decay_progress = min(1.0, time_since_flip / REENTRY_FORCE_AFTER_BARS) if REENTRY_FORCE_AFTER_BARS > 0 else 1.0
        target_reentry_pct = REENTRY_START_DISCOUNT_PCT + (REENTRY_END_PREMIUM_PCT - REENTRY_START_DISCOUNT_PCT) * decay_progress
        reentry_premium_pct = ((row[best_symbol] - parity_anchor) / parity_anchor * 100.0) if parity_anchor else 999.0
        reanalyze_active = side == 'USDC' and time_since_flip >= REENTRY_REANALYZE_AFTER_BARS
        volatility_reentry_pct = min(REENTRY_REANALYZE_MAX_PREMIUM_PCT, max(REENTRY_END_PREMIUM_PCT, avg_vol * REENTRY_REANALYZE_VOL_MULTIPLIER))
        if side == 'USDC':
            two_cycle_units = candidate[best_symbol]['projected_units']
            two_cycle_edge_pct = candidate[best_symbol]['edge_pct']
        else:
            alt_symbol = 'BTC' if holding_symbol == 'ETH' else 'ETH'
            two_cycle_units = units_after_swap(units_after_swap(units, row[holding_symbol], row[alt_symbol]), row[alt_symbol], row[holding_symbol])
            two_cycle_edge_pct = (((two_cycle_units - units) / units) * 100.0) if units > 0 else 0.0

        recent_prices = [x[best_symbol] for x in list(dq)[-12:]]
        local_low = min(recent_prices) if recent_prices else row[best_symbol]
        local_high = max(recent_prices) if recent_prices else row[best_symbol]
        pullback_from_high_pct = (((local_high - row[best_symbol]) / local_high) * 100.0) if local_high else 0.0
        bounce_from_low_pct = (((row[best_symbol] - local_low) / local_low) * 100.0) if local_low else 0.0
        wave_quality = clamp01((pullback_from_high_pct / max(0.2, avg_vol)) * 0.55 + (bounce_from_low_pct / max(0.2, avg_vol)) * 0.45)
        trend_drift = clamp01((((row[best_symbol] - ema12[best_symbol]) / ema12[best_symbol] * 100.0) + avg_vol) / max(0.5, avg_vol * 2)) if ema12[best_symbol] else 0.0
        spread_move_score = clamp01(abs(tick_change_pct) / max(PAIR_SPREAD_TRIGGER_PCT, 0.01))
        reversal_score = clamp01(abs(momentum_now - prev_momentum) / max(PAIR_REVERSAL_TRIGGER_PCT, 0.01))
        edge_score = clamp01((weth_edge_pct + 0.12) / 0.35)
        two_cycle_score = clamp01((two_cycle_edge_pct + 0.18) / 0.55)
        reentry_score = clamp01(wave_quality * 0.22 + edge_score * 0.18 + two_cycle_score * 0.20 + trend_drift * 0.12 + spread_move_score * 0.16 + reversal_score * 0.12)
        recovery_mode = side == 'USDC' and last_sell_price[best_symbol] > 0 and row[best_symbol] >= last_sell_price[best_symbol] and reanalyze_active

        entry_class = 'chase'
        pair_entry_ok = (abs(tick_change_pct) >= PAIR_SPREAD_TRIGGER_PCT or abs(momentum_now - prev_momentum) >= PAIR_REVERSAL_TRIGGER_PCT) and relative_strength_pct >= PAIR_ENTRY_MIN_RELATIVE_STRENGTH_PCT
        arm_wait_allowed = not (ARM_WAIT_SUPPRESS_DURING_ROTATE and rotate_signal != 'NONE' and rotate_edge_pct < ARM_WAIT_MIN_ROTATE_EDGE_PCT)
        if side == 'USDC' and row[best_symbol] <= symbol_metrics[best_symbol]['entry_target'] and (weth_ok or candidate[best_symbol]['edge_pct'] >= PAIR_ROTATE_MIN_EDGE_PCT):
            entry_class = 'ideal_dip'
        elif side == 'USDC' and recovery_mode and reentry_premium_pct <= REENTRY_RECOVER_ABOVE_SELL_PCT and two_cycle_edge_pct >= -0.05 and reentry_score >= REENTRY_SCORE_THRESHOLD:
            entry_class = 'fair_recovery'
        elif side == 'USDC' and pair_entry_ok and reentry_score >= REENTRY_SCORE_ARM_THRESHOLD and arm_wait_allowed:
            entry_class = 'arm_wait'

        discounted_entry_signal = side == 'USDC' and row[best_symbol] <= symbol_metrics[best_symbol]['entry_target'] and (move_ok or pair_entry_ok) and (weth_ok or candidate[best_symbol]['edge_pct'] >= PAIR_ROTATE_MIN_EDGE_PCT)
        reentry_signal = side == 'USDC' and cooldown_ok and (entry_class == 'ideal_dip' or (pair_entry_ok and candidate[best_symbol]['edge_pct'] >= PAIR_ROTATE_MIN_EDGE_PCT and arm_wait_allowed))
        force_reentry_signal = side == 'USDC' and cooldown_ok and entry_class in ('fair_recovery','arm_wait') and time_since_flip >= max(2, REENTRY_FORCE_AFTER_BARS // 20)
        volatility_reentry_signal = side == 'USDC' and cooldown_ok and entry_class in ('fair_recovery','arm_wait') and (recovery_mode or pair_entry_ok)
        missed_recovery_signal = side == 'USDC' and deep_reentry_seen and deep_reentry_low > 0 and row[best_symbol] <= deep_reentry_low * (1 + MISSED_REENTRY_RECOVERY_PCT / 100.0) and row[best_symbol] < last_sell_price[best_symbol] and cooldown_ok
        rotate_symbol = 'BTC' if holding_symbol == 'ETH' else 'ETH'
        rotation_edge_ok = side != 'USDC' and candidate[rotate_symbol]['edge_pct'] >= PAIR_ROTATE_MIN_EDGE_PCT
        relative_exit_ok = side != 'USDC' and candidate[rotate_symbol]['edge_pct'] > candidate[holding_symbol]['edge_pct'] + PAIR_ROTATE_EXIT_EDGE_PCT
        rotate_signal_matches_position = side != 'USDC' and ((rotate_signal == 'ROTATE_TO_BTC' and holding_symbol == 'ETH') or (rotate_signal == 'ROTATE_TO_ETH' and holding_symbol == 'BTC'))
        rotation_commit_ok = side != 'USDC' and rotate_signal_matches_position and rotate_signal_state['streak'] >= ROTATE_SIGNAL_PERSIST_BARS and rotate_edge_pct >= PAIR_ROTATION_COMMIT_PCT and (idx - last_entry_idx) >= PAIR_ROTATION_HOLD_BARS
        churn_guard_active = side != 'USDC' and (idx - last_flip_idx) < PAIR_CHURN_GUARD_BARS
        post_rotate_hold_active = side != 'USDC' and idx < post_rotate_hold_until
        usdc_exit_ok = side != 'USDC' and not post_rotate_hold_active and (current_price <= stop_price or (((current_price >= exit_price and rollover_ready) or extended_profit_rollover_exit) and candidate[rotate_symbol]['edge_pct'] < PAIR_USDC_EXIT_EDGE_PCT))
        sell_signal = side != 'USDC' and cooldown_ok and not churn_guard_active and usdc_exit_ok and not rotation_commit_ok
        buy_signal = side == 'USDC' and (discounted_entry_signal or reentry_signal or force_reentry_signal or missed_recovery_signal or volatility_reentry_signal) and cooldown_ok
        stop_signal = False

        trace.append({
            'idx': idx,
            'ts': row['ts'],
            'price': current_price,
            'eth_price': row['ETH'],
            'btc_price': row['BTC'],
            'side': side,
            'holding_symbol': holding_symbol,
            'best_symbol': best_symbol,
            'ema12': dict(ema12),
            'ema50': dict(ema50),
            'trigger': trigger,
            'entry_target': entry_target,
            'exit_price': exit_price,
            'stop_price': stop_price,
            'pair_entry_ok': pair_entry_ok,
            'rotation_edge_ok': rotation_edge_ok,
            'relative_exit_ok': relative_exit_ok,
            'relative_strength_pct': relative_strength_pct,
            'rotation_commit_ok': rotation_commit_ok,
            'usdc_exit_ok': usdc_exit_ok,
            'churn_guard_active': churn_guard_active,
            'rotate_signal': rotate_signal,
            'rotate_edge_pct': rotate_edge_pct,
            'rotate_signal_streak': rotate_signal_state['streak'],
            'spread_dev_pct': spread_dev_pct,
            'eth_mom_pct': eth_mom_pct,
            'btc_mom_pct': btc_mom_pct,
            'arm_wait_allowed': arm_wait_allowed,
            'post_rotate_hold_active': post_rotate_hold_active,
            'weth_edge_pct': weth_edge_pct,
            'two_cycle_edge_pct': two_cycle_edge_pct,
            'reentry_score': reentry_score,
            'entry_class': entry_class,
            'hold_state': hold_state,
            'discounted_entry_signal': discounted_entry_signal,
            'reentry_signal': reentry_signal,
            'force_reentry_signal': force_reentry_signal,
            'volatility_reentry_signal': volatility_reentry_signal,
            'missed_recovery_signal': missed_recovery_signal,
            'sell_signal': sell_signal,
            'stop_signal': stop_signal,
        })

        if sell_signal or rotation_commit_ok:
            before_units = current_eth_equiv
            side_before = holding_symbol or side
            if rotation_commit_ok:
                target_symbol = rotate_symbol
                new_units = units_after_swap(units, row[holding_symbol], row[target_symbol])
                after_units = new_units if target_symbol == 'ETH' else ((new_units * row[target_symbol]) / row['ETH'] if row['ETH'] > 0 else 0.0)
                units = new_units
                last_sell_price[holding_symbol] = row[holding_symbol]
                holding_symbol = target_symbol
                side = target_symbol
                entry_price = row[target_symbol]
                sell_peak_price = row[target_symbol]
                last_flip_idx = idx
                last_rotation_idx = idx
                last_entry_idx = idx
                post_rotate_hold_until = idx + ROTATE_POST_HOLD_BARS
                trades.append(Trade(idx, row['ts'], 'ROTATE', side_before, side, row[target_symbol], None, hold_state, before_units, after_units, after_units - before_units, trigger, reentry_score, two_cycle_edge_pct, weth_edge_pct))
            else:
                usdc = units * row[holding_symbol] * FEE_FACTOR
                units = 0.0
                last_sell_price[holding_symbol] = row[holding_symbol]
                side = 'USDC'
                holding_symbol = None
                last_flip_idx = idx
                entry_price = None
                after_units = usdc / row['ETH'] if row['ETH'] > 0 else 0.0
                trades.append(Trade(idx, row['ts'], 'SELL', side_before, side, current_price, None, hold_state, before_units, after_units, after_units - before_units, trigger, reentry_score, two_cycle_edge_pct, weth_edge_pct))
            continue

        if buy_signal:
            before_units = current_eth_equiv
            units = (usdc / row[best_symbol]) * FEE_FACTOR
            usdc = 0.0
            side_before = side
            side = best_symbol
            holding_symbol = best_symbol
            last_flip_idx = idx
            last_entry_idx = idx
            entry_price = row[best_symbol]
            sell_peak_price = row[best_symbol]
            deep_reentry_seen = False
            deep_reentry_low = 0.0
            after_units = units if best_symbol == 'ETH' else ((units * row[best_symbol]) / row['ETH'] if row['ETH'] > 0 else 0.0)
            trades.append(Trade(idx, row['ts'], 'BUY', side_before, side, row[best_symbol], entry_class, hold_state, before_units, after_units, after_units - before_units, trigger, reentry_score, two_cycle_edge_pct, weth_edge_pct))

    final_ref_price = rows[-1]['ETH']
    initial_units = INITIAL_USDC / rows[0]['ETH']
    final_units = units * (rows[-1][holding_symbol] / final_ref_price) if side != 'USDC' and holding_symbol else (usdc / final_ref_price if final_ref_price > 0 else 0.0)
    summary = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'source': str(ETH_PATH.relative_to(ROOT)),
        'objective': 'eth_equivalent_units_from_eth_btc_rotation',
        'rows': len(rows),
        'initial_usdc': INITIAL_USDC,
        'initial_eth_equiv_units': initial_units,
        'final_side': side,
        'final_holding_symbol': holding_symbol,
        'final_eth_equiv_units': final_units,
        'eth_equiv_delta_units': final_units - initial_units,
        'eth_equiv_return_pct': ((final_units - initial_units) / initial_units * 100.0) if initial_units > 0 else None,
        'trade_count': len(trades),
        'buy_count': sum(1 for t in trades if t.action == 'BUY'),
        'rotate_count': sum(1 for t in trades if t.action == 'ROTATE'),
        'sell_count': sum(1 for t in trades if t.action == 'SELL'),
        'stop_count': sum(1 for t in trades if t.action == 'STOP'),
        'avg_trade_unit_delta': (sum(t.net_unit_delta for t in trades) / len(trades)) if trades else None,
        'entry_class_counts': {k: sum(1 for t in trades if t.entry_class == k) for k in sorted({t.entry_class for t in trades if t.entry_class})},
        'hold_state_exit_counts': {k: sum(1 for t in trades if t.hold_state == k) for k in sorted({t.hold_state for t in trades if t.hold_state})},
        'parameters': {
            'VOL_MULTIPLIER': VOL_MULTIPLIER,
            'VOL_FLOOR': VOL_FLOOR,
            'VOL_CAP': VOL_CAP,
            'STOP_LOSS': STOP_LOSS,
            'MIN_WETH_ACCUMULATION_PCT': MIN_WETH_ACCUMULATION_PCT,
            'REENTRY_RECOVER_ABOVE_SELL_PCT': REENTRY_RECOVER_ABOVE_SELL_PCT,
            'REENTRY_SCORE_THRESHOLD': REENTRY_SCORE_THRESHOLD,
            'REENTRY_SCORE_ARM_THRESHOLD': REENTRY_SCORE_ARM_THRESHOLD,
            'REENTRY_REANALYZE_VOL_MULTIPLIER': REENTRY_REANALYZE_VOL_MULTIPLIER,
            'TWO_CYCLE_WETH_BONUS_WEIGHT': TWO_CYCLE_WETH_BONUS_WEIGHT,
            'COOLDOWN_BARS': COOLDOWN_BARS,
            'PAIR_ENTRY_MIN_RELATIVE_STRENGTH_PCT': PAIR_ENTRY_MIN_RELATIVE_STRENGTH_PCT,
            'PAIR_ROTATION_COMMIT_PCT': PAIR_ROTATION_COMMIT_PCT,
            'PAIR_ROTATION_HOLD_BARS': PAIR_ROTATION_HOLD_BARS,
            'PAIR_USDC_EXIT_EDGE_PCT': PAIR_USDC_EXIT_EDGE_PCT,
            'PAIR_CHURN_GUARD_BARS': PAIR_CHURN_GUARD_BARS,
            'ROTATE_SIGNAL_LOOKBACK_BARS': ROTATE_SIGNAL_LOOKBACK_BARS,
            'ROTATE_SIGNAL_MOM_BARS': ROTATE_SIGNAL_MOM_BARS,
            'ROTATE_SIGNAL_MIN_EDGE_PCT': ROTATE_SIGNAL_MIN_EDGE_PCT,
            'ROTATE_SIGNAL_MIN_DEV_PCT': ROTATE_SIGNAL_MIN_DEV_PCT,
            'ROTATE_SIGNAL_MIN_SPREAD_MOVE_PCT': ROTATE_SIGNAL_MIN_SPREAD_MOVE_PCT,
            'ROTATE_SIGNAL_PERSIST_BARS': ROTATE_SIGNAL_PERSIST_BARS,
            'ROTATE_POST_HOLD_BARS': ROTATE_POST_HOLD_BARS,
            'ARM_WAIT_SUPPRESS_DURING_ROTATE': ARM_WAIT_SUPPRESS_DURING_ROTATE,
            'ARM_WAIT_MIN_ROTATE_EDGE_PCT': ARM_WAIT_MIN_ROTATE_EDGE_PCT,
        },
        'sample_trades': [asdict(t) for t in trades[:20]],
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2))
    TRADES_PATH.write_text(json.dumps([asdict(t) for t in trades], indent=2))
    TRACE_PATH.write_text(json.dumps(trace, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
