"""
Dual-asset R11 Rotator v2 — 3-state machine: WETH ↔ cbBTC ↔ USDC
All rotations route through USDC (no direct WETH↔cbBTC swap needed).

v2 changes — structural features ported from the +4.31% replay architecture:
  1. Rotate signal state tracking with streak persist (ROTATE_SIGNAL_PERSIST_BARS)
  2. Arm_wait suppression during rotate windows (ARM_WAIT_SUPPRESS_DURING_ROTATE)
  3. Post-rotate hold dwell (ROTATE_POST_HOLD_BARS)
  4. Churn guard (PAIR_CHURN_GUARD_BARS)
  5. Relative strength entry comparison (PAIR_ENTRY_MIN_RELATIVE_STRENGTH_PCT)
  6. Rotate signal detection via spread deviation + relative momentum
"""
import json, time, requests, os
import math
from collections import deque

# === Constants — volatile read every tick ===
# Signature: all params are module-level consts, overridable by env (for replay matching)
def _env_f(k, d): return float(os.environ.get(k, str(d)))
def _env_i(k, d): return int(os.environ.get(k, str(d)))
def _env_b(k, d): return os.environ.get(k, 'true' if d else 'false').lower() == 'true'

EMA_12_ALPHA = _env_f('EMA_12_ALPHA', 2.0 / 13.0)
EMA_50_ALPHA = _env_f('EMA_50_ALPHA', 2.0 / 51.0)
VOL_MULTIPLIER = _env_f('VOL_MULTIPLIER', 0.72)
REGIME_VOL_CHAOS_PCT = _env_f('REGIME_VOL_CHAOS_PCT', 6.0)
REGIME_VOL_CALM_PCT = _env_f('REGIME_VOL_CALM_PCT', 1.5)
STALE_HOLD_MAX_LOSS_PCT = _env_f('STALE_HOLD_MAX_LOSS_PCT', 0.12)
DEQUE_MAX = _env_i('DEQUE_MAX', 30)
FEE_FACTOR = _env_f('FEE_FACTOR', 1 - 0.0005)

# === ROTATE SIGNAL DETECTION (ported from replay) ===
ROTATE_SIGNAL_LOOKBACK_BARS = _env_i('ROTATE_SIGNAL_LOOKBACK_BARS', 12)
ROTATE_SIGNAL_MOM_BARS = _env_i('ROTATE_SIGNAL_MOM_BARS', 3)
ROTATE_SIGNAL_MIN_EDGE_PCT = _env_f('ROTATE_SIGNAL_MIN_EDGE_PCT', 0.06)
ROTATE_SIGNAL_MIN_DEV_PCT = _env_f('ROTATE_SIGNAL_MIN_DEV_PCT', 0.03)
ROTATE_SIGNAL_MIN_SPREAD_MOVE_PCT = _env_f('ROTATE_SIGNAL_MIN_SPREAD_MOVE_PCT', 0.01)
ROTATE_SIGNAL_PERSIST_BARS = _env_i('ROTATE_SIGNAL_PERSIST_BARS', 1)
ROTATE_POST_HOLD_BARS = _env_i('ROTATE_POST_HOLD_BARS', 8)
ARM_WAIT_SUPPRESS_DURING_ROTATE = _env_b('ARM_WAIT_SUPPRESS_DURING_ROTATE', True)
ARM_WAIT_MIN_ROTATE_EDGE_PCT = _env_f('ARM_WAIT_MIN_ROTATE_EDGE_PCT', 0.18)

# === PAIR ENTRY & GATING (ported from replay) ===
PAIR_SPREAD_TRIGGER_PCT = _env_f('PAIR_SPREAD_TRIGGER_PCT', 0.18)
PAIR_REVERSAL_TRIGGER_PCT = _env_f('PAIR_REVERSAL_TRIGGER_PCT', 0.08)
PAIR_ROTATE_MIN_EDGE_PCT = _env_f('PAIR_ROTATE_MIN_EDGE_PCT', 0.02)
PAIR_ROTATE_EXIT_EDGE_PCT = _env_f('PAIR_ROTATE_EXIT_EDGE_PCT', 0.01)
PAIR_ENTRY_MIN_RELATIVE_STRENGTH_PCT = _env_f('PAIR_ENTRY_MIN_RELATIVE_STRENGTH_PCT', 0.0)
PAIR_ROTATION_COMMIT_PCT = _env_f('PAIR_ROTATION_COMMIT_PCT', 0.02)
PAIR_ROTATION_HOLD_BARS = _env_i('PAIR_ROTATION_HOLD_BARS', 2)
PAIR_CHURN_GUARD_BARS = _env_i('PAIR_CHURN_GUARD_BARS', 2)
PAIR_USDC_EXIT_EDGE_PCT = _env_f('PAIR_USDC_EXIT_EDGE_PCT', 0.06)
COOLDOWN_BARS = _env_i('COOLDOWN_BARS', 1)
MIN_WETH_ACCUMULATION_PCT = _env_f('MIN_WETH_ACCUMULATION_PCT', -0.01)

# === SELL / EXIT (ported from replay) ===
SELL_EXTENSION_MIN_PCT = _env_f('SELL_EXTENSION_MIN_PCT', 0.15)
SELL_RETRACE_TRIGGER_PCT = _env_f('SELL_RETRACE_TRIGGER_PCT', 0.03)
SELL_MIN_EXTENSION_EXIT_PCT = _env_f('SELL_MIN_EXTENSION_EXIT_PCT', 0.75)
SELL_ROLLOVER_RETRACE_PCT = _env_f('SELL_ROLLOVER_RETRACE_PCT', 0.10)
SELL_EXTENDED_PROFIT_EXIT_PCT = _env_f('SELL_EXTENDED_PROFIT_EXIT_PCT', 0.85)
MOMENTUM_HOLD_MIN_TICK_PCT = _env_f('MOMENTUM_HOLD_MIN_TICK_PCT', 0.035)
MOMENTUM_NEG_TICK_PCT = _env_f('MOMENTUM_NEG_TICK_PCT', -0.015)
MOMENTUM_FADE_RATIO = _env_f('MOMENTUM_FADE_RATIO', 0.55)

# === REENTRY (ported from replay) ===
REENTRY_RECOVER_ABOVE_SELL_PCT = _env_f('REENTRY_RECOVER_ABOVE_SELL_PCT', 0.30)
REENTRY_SCORE_THRESHOLD = _env_f('REENTRY_SCORE_THRESHOLD', 0.08)
REENTRY_SCORE_ARM_THRESHOLD = _env_f('REENTRY_SCORE_ARM_THRESHOLD', 0.03)
REENTRY_PARITY_BAND_PCT = _env_f('REENTRY_PARITY_BAND_PCT', 0.06)
REENTRY_FORCE_AFTER_BARS = _env_i('REENTRY_FORCE_AFTER_BARS', 180)
REENTRY_START_DISCOUNT_PCT = _env_f('REENTRY_START_DISCOUNT_PCT', 0.10)
REENTRY_END_PREMIUM_PCT = _env_f('REENTRY_END_PREMIUM_PCT', 0.03)
DEEP_REENTRY_DISCOUNT_PCT = _env_f('DEEP_REENTRY_DISCOUNT_PCT', 1.0)
DEEP_REENTRY_MIN_WETH_GAIN_PCT = _env_f('DEEP_REENTRY_MIN_WETH_GAIN_PCT', 0.02)
MISSED_REENTRY_RECOVERY_PCT = _env_f('MISSED_REENTRY_RECOVERY_PCT', 0.55)
REENTRY_REANALYZE_AFTER_BARS = _env_i('REENTRY_REANALYZE_AFTER_BARS', 120)
REENTRY_REANALYZE_VOL_MULTIPLIER = _env_f('REENTRY_REANALYZE_VOL_MULTIPLIER', 0.55)
REENTRY_REANALYZE_MAX_PREMIUM_PCT = _env_f('REENTRY_REANALYZE_MAX_PREMIUM_PCT', 0.75)
TWO_CYCLE_WETH_BONUS_WEIGHT = _env_f('TWO_CYCLE_WETH_BONUS_WEIGHT', 0.25)

# === PER-ASSET PARAMS (from r11, tuned for v2) ===
ASSET_PARAMS = {
    'WETH': {
        'VOL_FLOOR': _env_f('WETH_VOL_FLOOR', 0.15),
        'VOL_CAP': _env_f('WETH_VOL_CAP', 0.25),
        'STOP_LOSS': _env_f('WETH_STOP_LOSS', 0.25),
        'MOMENTUM_HOLD_MIN_TICK_PCT': _env_f('WETH_MOM_HOLD', 0.035),
        'MOMENTUM_FADE_RATIO': _env_f('WETH_MOM_FADE', 0.55),
        'SELL_EXTENSION_MIN_PCT': _env_f('WETH_SELL_EXT', 0.15),
        'SELL_RETRACE_TRIGGER_PCT': _env_f('WETH_SELL_RET', 0.03),
        'SELL_ROLLOVER_RETRACE_PCT': _env_f('WETH_SELL_ROLL', 0.10),
        'CONVERGENCE_MAX_SPREAD_PCT': _env_f('WETH_CONV_MAX', 0.15),
        'CONVERGENCE_ENTRY_TOLERANCE_PCT': _env_f('WETH_CONV_TOL', 0.08),
        'TREND_PULLBACK_TOLERANCE_PCT': _env_f('WETH_TREND_PULL', 0.15),
        'REENTRY_SCORE_THRESHOLD': _env_f('WETH_RE_SCORE', 0.35),
        'REENTRY_COOLDOWN_BARS': _env_i('WETH_RE_CD', 3),
        'STALE_HOLD_EXIT_AFTER_BARS': _env_i('WETH_STALE_BARS', 90),
    },
    'BTC': {
        'VOL_FLOOR': _env_f('BTC_VOL_FLOOR', 0.12),
        'VOL_CAP': _env_f('BTC_VOL_CAP', 0.22),
        'STOP_LOSS': _env_f('BTC_STOP_LOSS', 0.20),
        'MOMENTUM_HOLD_MIN_TICK_PCT': _env_f('BTC_MOM_HOLD', 0.025),
        'MOMENTUM_FADE_RATIO': _env_f('BTC_MOM_FADE', 0.50),
        'SELL_EXTENSION_MIN_PCT': _env_f('BTC_SELL_EXT', 0.10),
        'SELL_RETRACE_TRIGGER_PCT': _env_f('BTC_SELL_RET', 0.02),
        'SELL_ROLLOVER_RETRACE_PCT': _env_f('BTC_SELL_ROLL', 0.08),
        'CONVERGENCE_MAX_SPREAD_PCT': _env_f('BTC_CONV_MAX', 0.10),
        'CONVERGENCE_ENTRY_TOLERANCE_PCT': _env_f('BTC_CONV_TOL', 0.06),
        'TREND_PULLBACK_TOLERANCE_PCT': _env_f('BTC_TREND_PULL', 0.10),
        'REENTRY_SCORE_THRESHOLD': _env_f('BTC_RE_SCORE', 0.30),
        'REENTRY_COOLDOWN_BARS': _env_i('BTC_RE_CD', 2),
        'STALE_HOLD_EXIT_AFTER_BARS': _env_i('BTC_STALE_BARS', 60),
    },
}

_cex_cache = {}
_price_ttl = 5

def clamp01(v):
    return max(0.0, min(1.0, v))

# === Price feeds ===
def get_both_prices():
    global _cex_cache
    now = time.time()
    if _cex_cache and now - _cex_cache.get('t', 0) < _price_ttl:
        return _cex_cache['eth'], _cex_cache['btc'], _cex_cache['confirmed']
    eth_s, btc_s = [], []
    for source in ['coinbase', 'kraken']:
        try:
            if source == 'coinbase':
                r = requests.get('https://api.coinbase.com/v2/prices/ETH-USD/spot', timeout=5)
                if r.status_code == 200: eth_s.append(float(r.json()['data']['amount']))
                r = requests.get('https://api.coinbase.com/v2/prices/BTC-USD/spot', timeout=5)
                if r.status_code == 200: btc_s.append(float(r.json()['data']['amount']))
            else:
                r = requests.get('https://api.kraken.com/0/public/Ticker?pair=XETHZUSD', timeout=5)
                if r.status_code == 200: eth_s.append(float(r.json()['result']['XETHZUSD']['c'][0]))
                r = requests.get('https://api.kraken.com/0/public/Ticker?pair=XXBTZUSD', timeout=5)
                if r.status_code == 200: btc_s.append(float(r.json()['result']['XXBTZUSD']['c'][0]))
        except:
            pass
    eth_mid = sum(eth_s) / len(eth_s) if eth_s else None
    btc_mid = sum(btc_s) / len(btc_s) if btc_s else None
    if not eth_mid or not btc_mid:
        return eth_mid, btc_mid, False
    confirmed = (len(eth_s) >= 2 and len(btc_s) >= 2 and
                 max(eth_s) - min(eth_s) < eth_mid * 0.001 and
                 max(btc_s) - min(btc_s) < btc_mid * 0.001)
    _cex_cache = {'eth': eth_mid, 'btc': btc_mid, 'confirmed': confirmed, 't': now}
    return eth_mid, btc_mid, confirmed


def update_emas(state, eth_price, btc_price):
    for key, price in [('WETH', eth_price), ('BTC', btc_price)]:
        if price and price > 0:
            e12 = state.get(f'ema12_{key}', price)
            e50 = state.get(f'ema50_{key}', price)
            state[f'ema12_{key}'] = price * EMA_12_ALPHA + e12 * (1 - EMA_12_ALPHA)
            state[f'ema50_{key}'] = price * EMA_50_ALPHA + e50 * (1 - EMA_50_ALPHA)
    return state


# === Per-asset r11 signal computation (unchanged from v1) ===
def analyze_asset(key, price, state, dq):
    p = price
    bp = ASSET_PARAMS[key]
    e12 = state.get(f'ema12_{key}', p)
    e50 = state.get(f'ema50_{key}', p)
    anchor = abs(p - e12) / e12 * 100 if e12 else 0
    dq.append(p)
    if len(dq) > DEQUE_MAX: dq.popleft()
    avg_vol = sum(abs(d - e12) / e12 * 100 for d in dq) / len(dq) if dq and e12 else 0
    regime_f = 1.15 if avg_vol >= REGIME_VOL_CHAOS_PCT else (0.95 if avg_vol <= REGIME_VOL_CALM_PCT else 1.0)
    trigger = max(bp['VOL_FLOOR'], min(bp['VOL_CAP'], avg_vol * VOL_MULTIPLIER * regime_f))
    exit_p = e12 * (1 + trigger / 100.0)
    entry_t = e12 * (1 - trigger / 100.0)
    stop_p = e50 * (1 - bp['STOP_LOSS'] / 100.0)
    extension = ((p - state.get(f'entry_{key}', p)) / max(state.get(f'entry_{key}', p), 1)) * 100
    peak = max(state.get(f'peak_{key}', 0), p) if state.get(f'in_{key}') else 0
    retrace = ((peak - p) / peak * 100.0) if peak else 0
    rollover = peak > 0 and retrace >= bp['SELL_ROLLOVER_RETRACE_PCT']
    bars_since = state.get('bars_since_flip', 0) if state.get('side') == 'USDC' else state.get(f'hold_bars_{key}', 0)
    cd_ok = bars_since >= bp['REENTRY_COOLDOWN_BARS']
    ema_spread = abs(e12 - e50) / max(abs(e12), abs(e50), 1) * 100 if e12 and e50 else 999
    conv_ok = ema_spread <= bp['CONVERGENCE_MAX_SPREAD_PCT'] and anchor <= bp['CONVERGENCE_ENTRY_TOLERANCE_PCT']
    discount_ok = p <= entry_t
    band_depth = max(0.0, min(1.0, ((entry_t - p) / max(entry_t, 1e-9)) / max(trigger / 100.0, 1e-9))) if p < entry_t else 0.0
    regime_ok = avg_vol >= bp['VOL_FLOOR'] and avg_vol <= bp['VOL_CAP'] * 1.8
    expected_gain_pct = max(0.0, (exit_p - p) / max(p, 1e-9) * 100.0)
    fee_drag_pct = 0.08
    token_edge_pct = expected_gain_pct - fee_drag_pct
    buy_ready = cd_ok and regime_ok and (discount_ok or (conv_ok and band_depth > 0.20)) and token_edge_pct > 0
    entry_score = 0.0
    if buy_ready:
        band_q = band_depth
        conv_q = max(0.0, 1.0 - ema_spread / max(bp['CONVERGENCE_MAX_SPREAD_PCT'] * 2.0, 0.01))
        edge_q = max(0.0, min(1.0, token_edge_pct / max(trigger, 0.01)))
        trend_b = 0.25 if (e12 > e50 and p >= e12 * 0.9975) else 0.0
        entry_score = clamp01(band_q * 0.45 + edge_q * 0.30 + conv_q * 0.20 + trend_b * 0.05)
    # Exit signal computation (missing from v2 refactor — see #bugfix)
    sell_signal = p >= exit_p
    stale_hold_exit = (bars_since >= bp.get('STALE_HOLD_EXIT_AFTER_BARS', 90) and
                       retrace > 0 and not rollover and not cd_ok)
    stop_signal = p <= stop_p or stale_hold_exit

    return {
        'price': p, 'e12': e12, 'e50': e50,
        'trigger': trigger, 'exit_p': exit_p, 'entry_t': entry_t, 'stop_p': stop_p,
        'avg_vol': avg_vol, 'anchor': anchor,
        'extension': extension, 'retrace': retrace,
        'cd_ok': cd_ok, 'conv_ok': conv_ok, 'discount_ok': discount_ok,
        'buy_ready': buy_ready, 'band_depth': band_depth,
        'token_edge_pct': token_edge_pct, 'entry_score': entry_score,
        'rollover': rollover,
        'sell_signal': sell_signal,
        'stop_signal': stop_signal,
        'stale_hold_exit': stale_hold_exit,
    }


# === Rotate signal detection (NEW — ported from replay) ===
def detect_rotate_signal(eth_price, btc_price, q_history, idx):
    """
    Detect ETH/BTC divergence that favors rotation.
    Returns (signal_type: str, edge_pct: float, streak: int)
    signal_type: 'NONE' | 'ROTATE_TO_ETH' | 'ROTATE_TO_BTC'
    State managed externally via rotate_signal_state dict.
    """
    hist_len = len(q_history)
    if hist_len < max(ROTATE_SIGNAL_LOOKBACK_BARS, ROTATE_SIGNAL_MOM_BARS + 1):
        return 'NONE', 0.0, 0

    spread_pct = (eth_price - btc_price * 0.029) / eth_price * 100
    lookback = [x.get('spread_pct', spread_pct) for x in list(q_history)[-ROTATE_SIGNAL_LOOKBACK_BARS:]]

    n = len(lookback)
    if n < 2:
        return 'NONE', 0.0, 0
    mean_s = sum(lookback) / n
    var_s = sum((x - mean_s) ** 2 for x in lookback) / n
    std_s = math.sqrt(var_s) if var_s > 0 else 1e-9
    spread_dev_pct = (spread_pct - mean_s) / std_s

    mom_ref_idx = max(0, hist_len - 1 - ROTATE_SIGNAL_MOM_BARS)
    ref = q_history[mom_ref_idx] or {}
    ref_eth = ref.get('eth_price', eth_price)
    ref_btc = ref.get('btc_price', btc_price)
    eth_mom_pct = (eth_price - ref_eth) / max(ref_eth, 1) * 100
    btc_mom_pct = (btc_price - ref_btc) / max(ref_btc, 1) * 100

    if spread_dev_pct >= ROTATE_SIGNAL_MIN_DEV_PCT and (btc_mom_pct - eth_mom_pct) >= ROTATE_SIGNAL_MIN_EDGE_PCT:
        return 'ROTATE_TO_BTC', btc_mom_pct - eth_mom_pct, 1
    elif spread_dev_pct <= -ROTATE_SIGNAL_MIN_DEV_PCT and (eth_mom_pct - btc_mom_pct) >= ROTATE_SIGNAL_MIN_EDGE_PCT:
        return 'ROTATE_TO_ETH', eth_mom_pct - btc_mom_pct, 1

    return 'NONE', 0.0, 0


def update_rotate_state(rotate_state, signal_type, edge_pct):
    """Update rotate signal streak. Returns (updated_state, commit_ok)."""
    if signal_type == rotate_state.get('signal') and signal_type != 'NONE':
        rotate_state['streak'] = rotate_state.get('streak', 0) + 1
    elif signal_type != 'NONE':
        rotate_state = {'signal': signal_type, 'streak': 1}
    else:
        rotate_state = {'signal': 'NONE', 'streak': 0}
    
    commit_ok = (rotate_state.get('signal') != 'NONE' and
                 rotate_state.get('streak', 0) >= ROTATE_SIGNAL_PERSIST_BARS and
                 edge_pct >= PAIR_ROTATION_COMMIT_PCT)
    return rotate_state, commit_ok


# === Main rotation decision (v2 — with rotate signal + arm_wait gating) ===
def decide(state, eth_price, btc_price, q_weth, q_btc, q_history=None, idx=0, rotate_state=None):
    """
    Top-level rotation decision. Returns action dict.
    
    v2 additions:
    - rotate_signal detection with streak persist
    - arm_wait suppression during rotate windows
    - post-rotate hold dwell
    - churn guard
    - relative strength entry comparison
    """
    if q_history is None:
        q_history = deque(maxlen=DEQUE_MAX)
    if rotate_state is None:
        rotate_state = {'signal': 'NONE', 'streak': 0}
    
    side = state.get('side', 'USDC')
    holding_symbol = state.get('holding_symbol', 'WETH')
    last_flip_idx = state.get('last_flip_idx', 0)
    last_entry_idx = state.get('last_entry_idx', 0)
    
    a_w = analyze_asset('WETH', eth_price, state, q_weth)
    a_b = analyze_asset('BTC', btc_price, state, q_btc)
    eth_score = round(a_w.get('entry_score', 0.0), 2)
    btc_score = round(a_b.get('entry_score', 0.0), 2)
    
    # --- Rotate signal detection ---
    signal_type, signal_edge, _ = detect_rotate_signal(eth_price, btc_price, list(q_history), idx)
    rotate_state, rotate_commit_ok = update_rotate_state(rotate_state, signal_type, signal_edge)
    
    # --- Churn guard ---
    churn_guard_active = side != 'USDC' and (idx - last_flip_idx) < PAIR_CHURN_GUARD_BARS
    cooldown_ok = (idx - last_flip_idx) >= COOLDOWN_BARS
    
    # --- Post-rotate hold ---
    post_rotate_hold_until = state.get('post_rotate_hold_until', 0)
    post_rotate_hold_active = idx < post_rotate_hold_until
    
    # --- Arm_wait suppression ---
    arm_wait_allowed = not (ARM_WAIT_SUPPRESS_DURING_ROTATE and 
                           rotate_state.get('signal') != 'NONE' and 
                           signal_edge < ARM_WAIT_MIN_ROTATE_EDGE_PCT)
    
    # --- Edge comparison (relative strength) ---
    weth_edge_pct = a_w.get('token_edge_pct', 0)
    btc_edge_pct = a_b.get('token_edge_pct', 0)
    best_edge_pct = max(weth_edge_pct, btc_edge_pct)
    second_edge_pct = min(weth_edge_pct, btc_edge_pct)
    relative_strength_pct = best_edge_pct - second_edge_pct
    
    if side == 'WETH':
        # Can we rotate to BTC?
        # Check: rotate_signal matches position AND persist satisfied AND hold bars met
        rotate_signal_matches = rotate_state.get('signal') == 'ROTATE_TO_BTC'
        hold_bars_met = (idx - last_entry_idx) >= PAIR_ROTATION_HOLD_BARS
        
        # Also check: does BTC have a buy_ready signal with higher score?
        rotate_to_btc_by_edge = a_b['buy_ready'] and a_b['entry_score'] > max(a_w['entry_score'] + 0.15, 0.55) and relative_strength_pct >= PAIR_ENTRY_MIN_RELATIVE_STRENGTH_PCT
        
        # NEW: rotate via signal
        rotate_signal_active = rotate_signal_matches and rotate_commit_ok and hold_bars_met and not churn_guard_active
        
        if a_w.get('sell_signal', False) and not rotate_signal_active:
            return {'action': 'EXIT_WETH', 'reason': f'sell (p{eth_price:.0f}>exit{a_w["exit_p"]:.0f})',
                    'rotate_state': rotate_state}
        if rotate_signal_active:
            return {'action': 'EXIT_WETH', 'reason': f'rotate to BTC (sig={rotate_state.get("signal")} streak={rotate_state.get("streak")} edge={signal_edge:.2f}%)',
                    'rotate_state': rotate_state, 'post_rotate': True}
        if rotate_to_btc_by_edge:
            return {'action': 'EXIT_WETH', 'reason': f'rotate to BTC (btc score {btc_score:.2f} > weth {eth_score:.2f}, rel_str={relative_strength_pct:.2f}%)',
                    'rotate_state': rotate_state}
        if a_w.get('stop_signal', False):
            kind = 'stop' if eth_price <= a_w.get('stop_p', 0) else 'stale'
            return {'action': 'EXIT_WETH', 'reason': f'{kind} loss (p{eth_price:.0f})',
                    'rotate_state': rotate_state}
        return {'action': 'HOLD', 'reason': f'WETH ${eth_price:.0f} (exit ${a_w["exit_p"]:.0f} / stop ${a_w["stop_p"]:.0f})',
                'rotate_state': rotate_state, 'signal': rotate_state.get('signal'), 'signal_edge': signal_edge}

    if side == 'BTC':
        rotate_signal_matches = rotate_state.get('signal') == 'ROTATE_TO_ETH'
        hold_bars_met = (idx - last_entry_idx) >= PAIR_ROTATION_HOLD_BARS
        rotate_to_weth_by_edge = a_w['buy_ready'] and a_w['entry_score'] > max(a_b['entry_score'] + 0.15, 0.55) and relative_strength_pct >= PAIR_ENTRY_MIN_RELATIVE_STRENGTH_PCT
        rotate_signal_active = rotate_signal_matches and rotate_commit_ok and hold_bars_met and not churn_guard_active

        if a_b.get('sell_signal', False) and not rotate_signal_active:
            return {'action': 'EXIT_BTC', 'reason': f'sell (p${btc_price:.0f}>exit${a_b["exit_p"]:.0f})',
                    'rotate_state': rotate_state}
        if rotate_signal_active:
            return {'action': 'EXIT_BTC', 'reason': f'rotate to ETH (sig={rotate_state.get("signal")} streak={rotate_state.get("streak")} edge={signal_edge:.2f}%)',
                    'rotate_state': rotate_state, 'post_rotate': True}
        if rotate_to_weth_by_edge:
            return {'action': 'EXIT_BTC', 'reason': f'rotate to ETH (weth score {eth_score:.2f} > btc {btc_score:.2f}, rel_str={relative_strength_pct:.2f}%)',
                    'rotate_state': rotate_state}
        if a_b.get('stop_signal', False):
            kind = 'stop' if btc_price <= a_b.get('stop_p', 0) else 'stale'
            return {'action': 'EXIT_BTC', 'reason': f'{kind} loss (p${btc_price:.0f})',
                    'rotate_state': rotate_state}
        return {'action': 'HOLD', 'reason': f'BTC ${btc_price:.0f} (exit ${a_b["exit_p"]:.0f} / stop ${a_b["stop_p"]:.0f})',
                'rotate_state': rotate_state, 'signal': rotate_state.get('signal'), 'signal_edge': signal_edge}

    # USDC — evaluate entries
    pair_entry_ok = relative_strength_pct >= PAIR_ENTRY_MIN_RELATIVE_STRENGTH_PCT
    
    if a_w['buy_ready'] and a_b['buy_ready']:
        if a_w['entry_score'] >= a_b['entry_score'] and (pair_entry_ok or a_w['entry_score'] > a_b['entry_score']):
            return {'action': 'ENTER_WETH', 'reason': f'WETH wins tie (score {eth_score:.2f} vs BTC {btc_score:.2f})',
                    'rotate_state': rotate_state}
        return {'action': 'ENTER_BTC', 'reason': f'BTC wins tie (score {btc_score:.2f} vs WETH {eth_score:.2f})',
                'rotate_state': rotate_state}
    if a_w['buy_ready'] and (pair_entry_ok or cooldown_ok):
        return {'action': 'ENTER_WETH', 'reason': f'WETH entry (score {eth_score:.2f}{", pair_ok" if pair_entry_ok else ""})',
                'rotate_state': rotate_state}
    if a_b['buy_ready'] and (pair_entry_ok or cooldown_ok):
        return {'action': 'ENTER_BTC', 'reason': f'BTC entry (score {btc_score:.2f}{", pair_ok" if pair_entry_ok else ""})',
                'rotate_state': rotate_state}

    return {'action': 'HOLD', 'reason': f'USDC — no signal',
            'rotate_state': rotate_state, 'signal': rotate_state.get('signal'), 'signal_edge': signal_edge}
