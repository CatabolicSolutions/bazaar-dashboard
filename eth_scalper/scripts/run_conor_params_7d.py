#!/usr/bin/env python3
"""Clean 7-day replay with Conor's parameter set. No contamination, no assumptions."""
import json, os, sys
from collections import deque
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ETH_PATH = ROOT / 'eth_scalper' / 'out_eth_market_chart_30d.json'
BTC_PATH = ROOT / 'eth_scalper' / 'out_btc_market_chart_30d.json'
OUT_DIR = ROOT / 'eth_scalper' / 'out'
OUT_DIR.mkdir(parents=True, exist_ok=True)

# === CONOR'S EXACT PARAMETERS (single candidate, no assumptions) ===
def _env_float(key: str, default: float) -> float:
    v = os.environ.get(key)
    if v is not None:
        if v.lower() in ('true', 'false'):
            return 1.0 if v.lower() == 'true' else 0.0
        return float(v)
    return default

def _env_int(key: str, default: int) -> int:
    v = os.environ.get(key)
    if v is not None:
        if v.lower() in ('true', 'false'):
            return 1 if v.lower() == 'true' else 0
        return int(v)
    return default

def _env_bool(key: str, default: bool) -> bool:
    v = os.environ.get(key)
    if v is not None:
        return v.lower() == 'true'
    return default

# Load params from env vars with defaults = Conor's 9:30AM set
PARAMS = {
    'INITIAL_USDC': _env_float('INITIAL_USDC', 150),
    'FEE_FACTOR': _env_float('FEE_FACTOR', 1 - 0.0005),
    'EMA_12_ALPHA': _env_float('EMA_12_ALPHA', 2/(12+1)),
    'EMA_50_ALPHA': _env_float('EMA_50_ALPHA', 2/(50+1)),
    'DEQUE_MAX': _env_int('DEQUE_MAX', 30),
    'VOL_MULTIPLIER': _env_float('VOL_MULTIPLIER', 0.72),
    'VOL_FLOOR': _env_float('VOL_FLOOR', 0.12),
    'VOL_CAP': _env_float('VOL_CAP', 3.0),
    'STOP_LOSS': _env_float('STOP_LOSS', 1.30),
    'COOLDOWN_BARS': _env_int('COOLDOWN_BARS', 1),
    'PAIR_SPREAD_TRIGGER_PCT': _env_float('PAIR_SPREAD_TRIGGER_PCT', 0.18),
    'PAIR_REVERSAL_TRIGGER_PCT': _env_float('PAIR_REVERSAL_TRIGGER_PCT', 0.08),
    'PAIR_ROTATE_MIN_EDGE_PCT': _env_float('PAIR_ROTATE_MIN_EDGE_PCT', 0.02),
    'PAIR_ROTATE_EXIT_EDGE_PCT': _env_float('PAIR_ROTATE_EXIT_EDGE_PCT', 0.01),
    'PAIR_ENTRY_MIN_RELATIVE_STRENGTH_PCT': _env_float('PAIR_ENTRY_MIN_RELATIVE_STRENGTH_PCT', 0.00),
    'PAIR_ROTATION_COMMIT_PCT': _env_float('PAIR_ROTATION_COMMIT_PCT', 0.02),
    'PAIR_ROTATION_HOLD_BARS': _env_int('PAIR_ROTATION_HOLD_BARS', 2),
    'PAIR_USDC_EXIT_EDGE_PCT': _env_float('PAIR_USDC_EXIT_EDGE_PCT', 0.06),
    'PAIR_CHURN_GUARD_BARS': _env_int('PAIR_CHURN_GUARD_BARS', 2),
    'ROTATE_SIGNAL_LOOKBACK_BARS': _env_int('ROTATE_SIGNAL_LOOKBACK_BARS', 12),
    'ROTATE_SIGNAL_MOM_BARS': _env_int('ROTATE_SIGNAL_MOM_BARS', 3),
    'ROTATE_SIGNAL_MIN_EDGE_PCT': _env_float('ROTATE_SIGNAL_MIN_EDGE_PCT', 0.06),
    'ROTATE_SIGNAL_MIN_DEV_PCT': _env_float('ROTATE_SIGNAL_MIN_DEV_PCT', 0.03),
    'ROTATE_SIGNAL_MIN_SPREAD_MOVE_PCT': _env_float('ROTATE_SIGNAL_MIN_SPREAD_MOVE_PCT', 0.01),
    'ROTATE_SIGNAL_PERSIST_BARS': _env_int('ROTATE_SIGNAL_PERSIST_BARS', 2),
    'ROTATE_POST_HOLD_BARS': _env_int('ROTATE_POST_HOLD_BARS', 8),
    'ARM_WAIT_SUPPRESS_DURING_ROTATE': _env_bool('ARM_WAIT_SUPPRESS_DURING_ROTATE', True),
    'ARM_WAIT_MIN_ROTATE_EDGE_PCT': _env_float('ARM_WAIT_MIN_ROTATE_EDGE_PCT', 0.18),
    'REGIME_VOL_CHAOS_PCT': _env_float('REGIME_VOL_CHAOS_PCT', 6.0),
    'REGIME_VOL_CALM_PCT': _env_float('REGIME_VOL_CALM_PCT', 1.5),
    'VOL_FILTER': _env_float('VOL_FILTER', 0.3),
    'MIN_WETH_ACCUMULATION_PCT': _env_float('MIN_WETH_ACCUMULATION_PCT', -0.01),
    'SELL_EXTENSION_MIN_PCT': _env_float('SELL_EXTENSION_MIN_PCT', 0.15),
    'SELL_RETRACE_TRIGGER_PCT': _env_float('SELL_RETRACE_TRIGGER_PCT', 0.03),
    'SELL_MIN_EXTENSION_EXIT_PCT': _env_float('SELL_MIN_EXTENSION_EXIT_PCT', 0.75),
    'SELL_ROLLOVER_RETRACE_PCT': _env_float('SELL_ROLLOVER_RETRACE_PCT', 0.10),
    'SELL_EXTENDED_PROFIT_EXIT_PCT': _env_float('SELL_EXTENDED_PROFIT_EXIT_PCT', 0.85),
    'MOMENTUM_HOLD_MIN_TICK_PCT': _env_float('MOMENTUM_HOLD_MIN_TICK_PCT', 0.035),
    'MOMENTUM_NEG_TICK_PCT': _env_float('MOMENTUM_NEG_TICK_PCT', -0.015),
    'MOMENTUM_FADE_RATIO': _env_float('MOMENTUM_FADE_RATIO', 0.55),
    'REENTRY_RECOVER_ABOVE_SELL_PCT': _env_float('REENTRY_RECOVER_ABOVE_SELL_PCT', 0.30),
    'REENTRY_SCORE_THRESHOLD': _env_float('REENTRY_SCORE_THRESHOLD', 0.08),
    'REENTRY_SCORE_ARM_THRESHOLD': _env_float('REENTRY_SCORE_ARM_THRESHOLD', 0.03),
    'REENTRY_PARITY_BAND_PCT': _env_float('REENTRY_PARITY_BAND_PCT', 0.06),
    'REENTRY_FORCE_AFTER_BARS': _env_int('REENTRY_FORCE_AFTER_BARS', 180),
    'REENTRY_START_DISCOUNT_PCT': _env_float('REENTRY_START_DISCOUNT_PCT', 0.10),
    'REENTRY_END_PREMIUM_PCT': _env_float('REENTRY_END_PREMIUM_PCT', 0.03),
    'DEEP_REENTRY_DISCOUNT_PCT': _env_float('DEEP_REENTRY_DISCOUNT_PCT', 1.0),
    'DEEP_REENTRY_MIN_WETH_GAIN_PCT': _env_float('DEEP_REENTRY_MIN_WETH_GAIN_PCT', 0.02),
    'MISSED_REENTRY_RECOVERY_PCT': _env_float('MISSED_REENTRY_RECOVERY_PCT', 0.55),
    'REENTRY_REANALYZE_AFTER_BARS': _env_int('REENTRY_REANALYZE_AFTER_BARS', 120),
    'REENTRY_REANALYZE_VOL_MULTIPLIER': _env_float('REENTRY_REANALYZE_VOL_MULTIPLIER', 0.55),
    'REENTRY_REANALYZE_MAX_PREMIUM_PCT': _env_float('REENTRY_REANALYZE_MAX_PREMIUM_PCT', 0.75),
    'TWO_CYCLE_WETH_BONUS_WEIGHT': _env_float('TWO_CYCLE_WETH_BONUS_WEIGHT', 0.25),
}

def clamp01(v): return max(0.0, min(1.0, v))

@dataclass
class Trade:
    idx: int; ts: int; action: str; side_before: str; side_after: str
    price: float; entry_class: str | None; hold_state: str | None
    weth_equiv_before: float; weth_equiv_after: float; net_unit_delta: float
    trigger: float; reentry_score: float; two_cycle_edge_pct: float; weth_edge_pct: float

def load_series(path, symbol):
    obj = json.loads(path.read_text())
    return [{'ts': int(ts), 'symbol': symbol, 'price': float(px)} for ts, px in obj['prices']]

def units_after_swap(src_units, src_price, tgt_price, fee=PARAMS['FEE_FACTOR']):
    if src_units <= 0 or src_price <= 0 or tgt_price <= 0: return 0.0
    return (src_units * src_price * fee / tgt_price) * fee

def main():
    P = PARAMS
    eth_raw = load_series(ETH_PATH, 'ETH')
    btc_raw = load_series(BTC_PATH, 'BTC')
    n = min(len(eth_raw), len(btc_raw))
    all_rows = []
    for i in range(n):
        all_rows.append({'ts': eth_raw[i]['ts'], 'ETH': eth_raw[i]['price'], 'BTC': btc_raw[i]['price']})

    # ** 7-DAY SPLIT ** - last 7 days only, no lookback contamination
    # Use a warmup buffer at the start for EMA initialization, exclude from results
    last_ts = all_rows[-1]['ts']
    cutoff = last_ts - 7 * 24 * 3600 * 1000
    warmup_bars = 60  # ~60 bars of warmup for EMAs
    seven_day_start = next(i for i, r in enumerate(all_rows) if r['ts'] >= cutoff) - warmup_bars
    seven_day_start = max(0, seven_day_start)
    rows = all_rows[seven_day_start:]
    
    # Track where the actual 7-day window begins (index within rows)
    trade_start_idx = next(i for i, r in enumerate(rows) if r['ts'] >= cutoff)

    ema12 = {'ETH': rows[0]['ETH'], 'BTC': rows[0]['BTC']}
    ema50 = {'ETH': rows[0]['ETH'], 'BTC': rows[0]['BTC']}
    side, holding_symbol = 'USDC', None
    usdc, units = P['INITIAL_USDC'], 0.0
    entry_price, last_sell_price = None, {'ETH': 0.0, 'BTC': 0.0}
    sell_peak_price = 0.0
    last_flip_idx, last_entry_idx, last_rotation_idx = -999999, -999999, -999999
    post_rotate_hold_until = -999999
    deep_reentry_seen, deep_reentry_low = False, 0.0
    dq = deque(maxlen=P['DEQUE_MAX'])
    trades, trace = [], []
    rotate_signal_state = {'signal': 'NONE', 'streak': 0}

    for idx, row in enumerate(rows):
        if idx == 0:
            dq.append({'ETH': rows[0]['ETH'], 'BTC': rows[0]['BTC'], 'spread_pct': (rows[0]['ETH']/rows[0]['BTC']-1)*100, 'tick_change_pct': 0.0, 'anchor_distance_pct': 0.0})
            continue

        for sym in ('ETH','BTC'):
            p = row[sym]
            e12 = ema12[sym]; e50 = ema50[sym]
            ema12[sym] = p * P['EMA_12_ALPHA'] + e12 * (1 - P['EMA_12_ALPHA'])
            ema50[sym] = p * P['EMA_50_ALPHA'] + e50 * (1 - P['EMA_50_ALPHA'])

        spread_now = row['ETH'] / row['BTC'] if row['BTC'] else 0
        spread_prev = rows[idx-1]['ETH'] / rows[idx-1]['BTC'] if rows[idx-1]['BTC'] else spread_now
        tick_change_pct = ((spread_now - spread_prev) / spread_prev) * 100 if spread_prev else 0
        anchor_dist = abs((spread_now - (ema12['ETH']/ema12['BTC'])) / (ema12['ETH']/ema12['BTC'])) * 100 if ema12['BTC'] else 0
        dq.append({'ETH': row['ETH'], 'BTC': row['BTC'], 'spread_pct': spread_now, 'tick_change_pct': tick_change_pct, 'anchor_distance_pct': anchor_dist})
        avg_vol = sum(x['anchor_distance_pct'] for x in dq) / len(dq) if dq else 0
        recent_ticks = [x['tick_change_pct'] for x in list(dq)[-5:]]
        spread_lookback = [x['spread_pct'] for x in list(dq)[-P['ROTATE_SIGNAL_LOOKBACK_BARS']:]]
        momentum_peak = max(recent_ticks) if recent_ticks else 0
        momentum_now = recent_ticks[-1] if recent_ticks else 0
        prev_momentum = recent_ticks[-2] if len(recent_ticks) >= 2 else momentum_now

        current_price = row[holding_symbol] if holding_symbol else row['ETH']
        spread_anchor = sum(spread_lookback)/len(spread_lookback) if spread_lookback else spread_now
        spread_dev_pct = ((spread_now - spread_anchor) / spread_anchor * 100) if spread_anchor else 0
        mom_ref = max(0, idx - P['ROTATE_SIGNAL_MOM_BARS'])
        eth_mom_pct = ((row['ETH'] - rows[mom_ref]['ETH']) / rows[mom_ref]['ETH'] * 100) if rows[mom_ref]['ETH'] else 0
        btc_mom_pct = ((row['BTC'] - rows[mom_ref]['BTC']) / rows[mom_ref]['BTC'] * 100) if rows[mom_ref]['BTC'] else 0

        # Rotate signal
        rotate_signal, rotate_edge_pct = 'NONE', 0.0
        if spread_dev_pct >= P['ROTATE_SIGNAL_MIN_DEV_PCT'] and tick_change_pct >= P['ROTATE_SIGNAL_MIN_SPREAD_MOVE_PCT'] and (btc_mom_pct - eth_mom_pct) >= P['ROTATE_SIGNAL_MIN_EDGE_PCT']:
            rotate_signal, rotate_edge_pct = 'ROTATE_TO_BTC', btc_mom_pct - eth_mom_pct
        elif spread_dev_pct <= -P['ROTATE_SIGNAL_MIN_DEV_PCT'] and tick_change_pct <= -P['ROTATE_SIGNAL_MIN_SPREAD_MOVE_PCT'] and (eth_mom_pct - btc_mom_pct) >= P['ROTATE_SIGNAL_MIN_EDGE_PCT']:
            rotate_signal, rotate_edge_pct = 'ROTATE_TO_ETH', eth_mom_pct - btc_mom_pct
        if rotate_signal == rotate_signal_state['signal'] and rotate_signal != 'NONE':
            rotate_signal_state['streak'] += 1
        elif rotate_signal != 'NONE':
            rotate_signal_state = {'signal': rotate_signal, 'streak': 1}
        else:
            rotate_signal_state = {'signal': 'NONE', 'streak': 0}

        if side != 'USDC': sell_peak_price = max(sell_peak_price or 0, current_price)
        else: sell_peak_price = 0.0
        peak_price = sell_peak_price or current_price
        ext_pct = ((peak_price - entry_price) / entry_price * 100) if entry_price else 0
        retrace_pct = ((peak_price - current_price) / peak_price * 100) if peak_price else 0
        ext_hold = side != 'USDC' and ext_pct >= P['SELL_EXTENSION_MIN_PCT'] and retrace_pct < P['SELL_RETRACE_TRIGGER_PCT']
        regime_f = 1.15 if avg_vol >= P['REGIME_VOL_CHAOS_PCT'] else (0.95 if avg_vol <= P['REGIME_VOL_CALM_PCT'] else 1.0)
        trigger = max(P['VOL_FLOOR'], min(P['VOL_CAP'], round(avg_vol * P['VOL_MULTIPLIER'] * regime_f, 2)))
        cooldown_ok = (idx - last_flip_idx) >= P['COOLDOWN_BARS']

        sym_metrics = {}
        for sym in ('ETH','BTC'):
            sp = row[sym]
            exit_p = ema12[sym] * (1 + trigger/100)
            entry_t = ema12[sym] * (1 - trigger/100)
            stop_p = ema50[sym] * (1 - P['STOP_LOSS']/100)
            sym_metrics[sym] = {'price': sp, 'exit_price': exit_p, 'entry_target': entry_t, 'stop_price': stop_p}
        active = sym_metrics[holding_symbol] if holding_symbol else sym_metrics['ETH']
        exit_price = active['exit_price']; entry_target = active['entry_target']; stop_price = active['stop_price']

        momentum_hold = side != 'USDC' and current_price >= exit_price and momentum_peak >= P['MOMENTUM_HOLD_MIN_TICK_PCT'] and momentum_now > max(P['MOMENTUM_NEG_TICK_PCT'], momentum_peak * P['MOMENTUM_FADE_RATIO'])
        continuation_hold = side != 'USDC' and ((current_price >= exit_price and (momentum_hold or ext_hold)) or (ext_pct >= P['SELL_MIN_EXTENSION_EXIT_PCT'] and retrace_pct < P['SELL_ROLLOVER_RETRACE_PCT'] and momentum_now > P['MOMENTUM_NEG_TICK_PCT']))
        rollover_ready = side != 'USDC' and ext_pct >= P['SELL_MIN_EXTENSION_EXIT_PCT'] and (retrace_pct >= P['SELL_ROLLOVER_RETRACE_PCT'] or momentum_now <= P['MOMENTUM_NEG_TICK_PCT'] or (momentum_peak > 0 and momentum_now <= momentum_peak * P['MOMENTUM_FADE_RATIO']))
        ext_profit_rollover = side != 'USDC' and ext_pct >= P['SELL_EXTENDED_PROFIT_EXIT_PCT'] and rollover_ready
        hold_state = 'continuation' if continuation_hold else ('rollover' if rollover_ready else ('armed' if side != 'USDC' and current_price >= exit_price else 'hold'))
        move_ok = anchor_dist >= avg_vol * P['VOL_FILTER'] if avg_vol > 0 else True

        current_eth_equiv = units * (row[holding_symbol] / row['ETH']) if side != 'USDC' and holding_symbol else (usdc / row['ETH'] if row['ETH'] > 0 else 0)
        candidate = {}
        for sym in ('ETH','BTC'):
            tp = row[sym]
            if side == 'USDC': proj_units = (usdc / tp) * P['FEE_FACTOR'] if tp > 0 else 0
            else: proj_units = units_after_swap(units, row[holding_symbol], tp)
            proj_eth = proj_units if sym == 'ETH' else ((proj_units * tp) / row['ETH'] if row['ETH'] > 0 else 0)
            edge = ((proj_eth - current_eth_equiv) / current_eth_equiv * 100) if current_eth_equiv > 0 else 0
            candidate[sym] = {'units': proj_units, 'eth_equiv': proj_eth, 'edge_pct': edge}
        ranked = sorted(candidate.keys(), key=lambda s: candidate[s]['edge_pct'], reverse=True)
        best_sym, second_sym = ranked[0], ranked[1]
        best_edge = candidate[best_sym]['edge_pct']
        rel_strength = best_edge - candidate[second_sym]['edge_pct']
        weth_edge = candidate[best_sym]['edge_pct']
        weth_ok = weth_edge >= P['MIN_WETH_ACCUMULATION_PCT']

        # Deep reentry
        if side == 'USDC' and last_sell_price[best_sym] > 0 and row[best_sym] <= last_sell_price[best_sym] * (1 - P['DEEP_REENTRY_DISCOUNT_PCT']/100):
            deep_reentry_seen = True
            deep_reentry_low = min(deep_reentry_low or row[best_sym], row[best_sym])
        elif side != 'USDC': deep_reentry_seen, deep_reentry_low = False, 0.0

        parity_anchor = last_sell_price[best_sym] if last_sell_price[best_sym] > 0 else ema12[best_sym]
        time_since_flip = max(0, idx - last_flip_idx)
        decay_prog = min(1.0, time_since_flip / P['REENTRY_FORCE_AFTER_BARS']) if P['REENTRY_FORCE_AFTER_BARS'] > 0 else 1
        target_reentry = P['REENTRY_START_DISCOUNT_PCT'] + (P['REENTRY_END_PREMIUM_PCT'] - P['REENTRY_START_DISCOUNT_PCT']) * decay_prog
        reentry_premium = ((row[best_sym] - parity_anchor) / parity_anchor * 100) if parity_anchor else 999
        reanalyze_active = side == 'USDC' and time_since_flip >= P['REENTRY_REANALYZE_AFTER_BARS']
        vol_reentry = min(P['REENTRY_REANALYZE_MAX_PREMIUM_PCT'], max(P['REENTRY_END_PREMIUM_PCT'], avg_vol * P['REENTRY_REANALYZE_VOL_MULTIPLIER']))

        # Two-cycle edge
        if side == 'USDC':
            two_cycle_units = candidate[best_sym]['units']
            two_cycle_edge_pct = candidate[best_sym]['edge_pct']
        else:
            alt_sym = 'BTC' if holding_symbol == 'ETH' else 'ETH'
            two_cycle_units = units_after_swap(units_after_swap(units, row[holding_symbol], row[alt_sym]), row[alt_sym], row[holding_symbol])
            two_cycle_edge_pct = ((two_cycle_units - units) / units * 100) if units > 0 else 0

        # Entry scoring
        recent_prices = [x[best_sym] for x in list(dq)[-12:]]
        local_low = min(recent_prices) if recent_prices else row[best_sym]
        local_high = max(recent_prices) if recent_prices else row[best_sym]
        pullback = ((local_high - row[best_sym]) / local_high * 100) if local_high else 0
        bounce = ((row[best_sym] - local_low) / local_low * 100) if local_low else 0
        wave_q = clamp01((pullback / max(0.2, avg_vol)) * 0.55 + (bounce / max(0.2, avg_vol)) * 0.45)
        trend_drift = clamp01(((row[best_sym] - ema12[best_sym]) / ema12[best_sym] * 100 + avg_vol) / max(0.5, avg_vol*2)) if ema12[best_sym] else 0
        spread_score = clamp01(abs(tick_change_pct) / max(P['PAIR_SPREAD_TRIGGER_PCT'], 0.01))
        reversal_score = clamp01(abs(momentum_now - prev_momentum) / max(P['PAIR_REVERSAL_TRIGGER_PCT'], 0.01))
        edge_score = clamp01((weth_edge + 0.12) / 0.35)
        two_cycle_score = clamp01((two_cycle_edge_pct + 0.18) / 0.55)
        reentry_score = clamp01(wave_q * 0.22 + edge_score * 0.18 + two_cycle_score * 0.20 + trend_drift * 0.12 + spread_score * 0.16 + reversal_score * 0.12)
        recovery_mode = side == 'USDC' and last_sell_price[best_sym] > 0 and row[best_sym] >= last_sell_price[best_sym] and reanalyze_active

        # Entry classification
        entry_class = 'chase'
        pair_entry_ok = (abs(tick_change_pct) >= P['PAIR_SPREAD_TRIGGER_PCT'] or abs(momentum_now - prev_momentum) >= P['PAIR_REVERSAL_TRIGGER_PCT']) and rel_strength >= P['PAIR_ENTRY_MIN_RELATIVE_STRENGTH_PCT']
        arm_wait_ok = not (P['ARM_WAIT_SUPPRESS_DURING_ROTATE'] and rotate_signal != 'NONE' and rotate_edge_pct < P['ARM_WAIT_MIN_ROTATE_EDGE_PCT'])
        if side == 'USDC' and row[best_sym] <= sym_metrics[best_sym]['entry_target'] and (weth_ok or candidate[best_sym]['edge_pct'] >= P['PAIR_ROTATE_MIN_EDGE_PCT']):
            entry_class = 'ideal_dip'
        elif side == 'USDC' and recovery_mode and reentry_premium <= P['REENTRY_RECOVER_ABOVE_SELL_PCT'] and two_cycle_edge_pct >= -0.05 and reentry_score >= P['REENTRY_SCORE_THRESHOLD']:
            entry_class = 'fair_recovery'
        elif side == 'USDC' and pair_entry_ok and reentry_score >= P['REENTRY_SCORE_ARM_THRESHOLD'] and arm_wait_ok:
            entry_class = 'arm_wait'

        discounted_entry = side == 'USDC' and row[best_sym] <= sym_metrics[best_sym]['entry_target'] and (move_ok or pair_entry_ok) and (weth_ok or candidate[best_sym]['edge_pct'] >= P['PAIR_ROTATE_MIN_EDGE_PCT'])
        reentry_signal = side == 'USDC' and cooldown_ok and (entry_class == 'ideal_dip' or (pair_entry_ok and candidate[best_sym]['edge_pct'] >= P['PAIR_ROTATE_MIN_EDGE_PCT'] and arm_wait_ok))
        force_reentry = side == 'USDC' and cooldown_ok and entry_class in ('fair_recovery','arm_wait') and time_since_flip >= max(2, P['REENTRY_FORCE_AFTER_BARS'] // 20)
        vol_reentry_signal = side == 'USDC' and cooldown_ok and entry_class in ('fair_recovery','arm_wait') and (recovery_mode or pair_entry_ok)
        missed_recovery = side == 'USDC' and deep_reentry_seen and deep_reentry_low > 0 and row[best_sym] <= deep_reentry_low * (1 + P['MISSED_REENTRY_RECOVERY_PCT']/100) and row[best_sym] < last_sell_price[best_sym] and cooldown_ok

        # Rotate / exit decisions
        rotate_sym = 'BTC' if holding_symbol == 'ETH' else 'ETH'
        rotation_edge_ok = side != 'USDC' and candidate[rotate_sym]['edge_pct'] >= P['PAIR_ROTATE_MIN_EDGE_PCT']
        relative_exit_ok = side != 'USDC' and candidate[rotate_sym]['edge_pct'] > candidate[holding_symbol]['edge_pct'] + P['PAIR_ROTATE_EXIT_EDGE_PCT']
        rotate_sig_matches = side != 'USDC' and ((rotate_signal == 'ROTATE_TO_BTC' and holding_symbol == 'ETH') or (rotate_signal == 'ROTATE_TO_ETH' and holding_symbol == 'BTC'))
        rotation_commit = side != 'USDC' and rotate_sig_matches and rotate_signal_state['streak'] >= P['ROTATE_SIGNAL_PERSIST_BARS'] and rotate_edge_pct >= P['PAIR_ROTATION_COMMIT_PCT'] and (idx - last_entry_idx) >= P['PAIR_ROTATION_HOLD_BARS']
        churn_guard = side != 'USDC' and (idx - last_flip_idx) < P['PAIR_CHURN_GUARD_BARS']
        post_hold_active = side != 'USDC' and idx < post_rotate_hold_until
        usdc_exit_ok = side != 'USDC' and not post_hold_active and (current_price <= stop_price or (((current_price >= exit_price and rollover_ready) or ext_profit_rollover) and candidate[rotate_sym]['edge_pct'] < P['PAIR_USDC_EXIT_EDGE_PCT']))
        sell_signal = side != 'USDC' and cooldown_ok and not churn_guard and usdc_exit_ok and not rotation_commit
        buy_signal = side == 'USDC' and (discounted_entry or reentry_signal or force_reentry or missed_recovery or vol_reentry_signal) and cooldown_ok

        trace.append({
            'idx': idx, 'ts': row['ts'], 'price': current_price,
            'eth_price': row['ETH'], 'btc_price': row['BTC'],
            'side': side, 'holding_symbol': holding_symbol, 'best_symbol': best_sym,
            'trigger': trigger, 'entry_target': entry_target, 'exit_price': exit_price, 'stop_price': stop_price,
            'pair_entry_ok': pair_entry_ok, 'rotation_edge_ok': rotation_edge_ok,
            'rotation_commit': rotation_commit, 'usdc_exit_ok': usdc_exit_ok,
            'churn_guard': churn_guard, 'post_hold_active': post_hold_active,
            'sell_signal': sell_signal, 'buy_signal': buy_signal,
            'rotate_signal': rotate_signal, 'rotate_edge_pct': rotate_edge_pct,
            'rotate_streak': rotate_signal_state['streak'],
            'entry_class': entry_class, 'hold_state': hold_state,
            'reentry_score': reentry_score, 'weth_edge': weth_edge,
            'two_cycle_edge': two_cycle_edge_pct,
            'in_trade_window': idx >= trade_start_idx,
        })

        # Record trades only in 7-day window
        record = idx >= trade_start_idx

        if sell_signal or rotation_commit:
            before = current_eth_equiv
            side_before = holding_symbol or side
            if rotation_commit:
                target = rotate_sym
                new_units = units_after_swap(units, row[holding_symbol], row[target])
                after = new_units if target == 'ETH' else ((new_units * row[target]) / row['ETH'] if row['ETH'] > 0 else 0)
                units = new_units
                last_sell_price[holding_symbol] = row[holding_symbol]
                holding_symbol = target; side = target
                entry_price = row[target]; sell_peak_price = row[target]
                last_flip_idx = idx; last_rotation_idx = idx; last_entry_idx = idx
                post_rotate_hold_until = idx + P['ROTATE_POST_HOLD_BARS']
                if record:
                    trades.append(Trade(idx, row['ts'], 'ROTATE', side_before, side, row[target], None, hold_state, before, after, after-before, trigger, reentry_score, two_cycle_edge_pct, weth_edge))
            else:
                usdc = units * row[holding_symbol] * P['FEE_FACTOR']
                units = 0; last_sell_price[holding_symbol] = row[holding_symbol]
                side = 'USDC'; holding_symbol = None; last_flip_idx = idx
                entry_price = None
                after = usdc / row['ETH'] if row['ETH'] > 0 else 0
                if record:
                    trades.append(Trade(idx, row['ts'], 'SELL', side_before, side, current_price, None, hold_state, before, after, after-before, trigger, reentry_score, two_cycle_edge_pct, weth_edge))
            continue

        if buy_signal:
            before = current_eth_equiv
            units = (usdc / row[best_sym]) * P['FEE_FACTOR']
            usdc = 0; side_before = side
            side = best_sym; holding_symbol = best_sym
            last_flip_idx = idx; last_entry_idx = idx
            entry_price = row[best_sym]; sell_peak_price = row[best_sym]
            deep_reentry_seen = False; deep_reentry_low = 0
            after = units if best_sym == 'ETH' else ((units * row[best_sym]) / row['ETH'] if row['ETH'] > 0 else 0)
            if record:
                trades.append(Trade(idx, row['ts'], 'BUY', side_before, side, row[best_sym], entry_class, hold_state, before, after, after-before, trigger, reentry_score, two_cycle_edge_pct, weth_edge))

    # Summary — ONLY trades in the 7-day window
    ref = rows[-1]['ETH']
    init_units = P['INITIAL_USDC'] / rows[trade_start_idx]['ETH']
    fin_units = units * (rows[-1][holding_symbol] / ref) if side != 'USDC' and holding_symbol else (usdc / ref if ref > 0 else 0)
    
    seven_day_rows = [r for r in rows if r['ts'] >= cutoff]
    
    summary = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'parameters': {k: v for k, v in sorted(P.items())},
        'data': {
            'total_rows': len(all_rows),
            'warmup_rows': trade_start_idx,
            'seven_day_rows': len(seven_day_rows),
            'seven_day_start_ts': seven_day_rows[0]['ts'] if seven_day_rows else 0,
            'seven_day_end_ts': seven_day_rows[-1]['ts'] if seven_day_rows else 0,
            'seven_day_eth_price_range': f"${min(r['ETH'] for r in seven_day_rows):.0f}-${max(r['ETH'] for r in seven_day_rows):.0f}",
            'seven_day_btc_price_range': f"${min(r['BTC'] for r in seven_day_rows):.0f}-${max(r['BTC'] for r in seven_day_rows):.0f}",
        },
        'results': {
            'initial_usdc': P['INITIAL_USDC'],
            'initial_eth_equiv_units': init_units,
            'final_side': side,
            'final_holding_symbol': holding_symbol,
            'final_usdc': usdc,
            'final_asset_units': units,
            'final_eth_equiv_units': fin_units,
            'eth_equiv_delta_units': fin_units - init_units,
            'eth_equiv_return_pct': ((fin_units - init_units) / init_units * 100) if init_units > 0 else None,
            'trade_count': len(trades),
            'buy_count': sum(1 for t in trades if t.action == 'BUY'),
            'rotate_count': sum(1 for t in trades if t.action == 'ROTATE'),
            'sell_count': sum(1 for t in trades if t.action == 'SELL'),
            'avg_trade_unit_delta': sum(t.net_unit_delta for t in trades) / len(trades) if trades else None,
            'entry_class_counts': {k: sum(1 for t in trades if t.entry_class == k) for k in sorted({t.entry_class for t in trades if t.entry_class})},
            'hold_state_exit_counts': {k: sum(1 for t in trades if t.hold_state == k) for k in sorted({t.hold_state for t in trades if t.hold_state})},
        },
        'trades': [asdict(t) for t in trades],
    }

    out_path = OUT_DIR / 'conor_params_7d_result.json'
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"\n{'='*70}")
    print("CONOR'S PARAMETER SET - 7-DAY REPLAY RESULT")
    print(f"{'='*70}")
    print(f"Data window: {datetime.fromtimestamp(seven_day_rows[0]['ts']/1000)} to {datetime.fromtimestamp(seven_day_rows[-1]['ts']/1000)}")
    print(f"ETH range: ${min(r['ETH'] for r in seven_day_rows):.0f} - ${max(r['ETH'] for r in seven_day_rows):.0f}")
    print(f"BTC range: ${min(r['BTC'] for r in seven_day_rows):.0f} - ${max(r['BTC'] for r in seven_day_rows):.0f}")
    print(f"\n--- Results ---")
    print(f"Starting USDC: ${P['INITIAL_USDC']:.2f}")
    print(f"Starting ETH-equiv: {init_units:.8f}")
    print(f"Final side: {side} ({holding_symbol or 'N/A'})")
    print(f"Final USDC: ${usdc:.2f} | Asset units: {units:.8f}")
    print(f"Final ETH-equiv: {fin_units:.8f}")
    print(f"ETH-equiv delta: {summary['results']['eth_equiv_delta_units']:.8f}")
    print(f"ETH-equiv return: {summary['results']['eth_equiv_return_pct']:.4f}%")
    print(f"\n--- Trades ({len(trades)}) ---")
    print(f"  Buys: {summary['results']['buy_count']}")
    print(f"  Rotates: {summary['results']['rotate_count']}")
    print(f"  Sells: {summary['results']['sell_count']}")
    print(f"  Avg trade delta: {summary['results']['avg_trade_unit_delta']:.8f}")
    print(f"  Entry classes: {summary['results']['entry_class_counts']}")
    print(f"  Exit hold states: {summary['results']['hold_state_exit_counts']}")
    if trades:
        for t in trades:
            print(f"  [{t.idx}] {t.action:6s} {t.side_before:4s}->{t.side_after:4s} @ ${t.price:.0f} | entry_class={t.entry_class} hold={t.hold_state} | delta={t.net_unit_delta:.8f}")
    print(f"\nFull result: {out_path}")

if __name__ == '__main__':
    main()
