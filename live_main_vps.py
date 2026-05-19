"""ETH Scalper - MA-Anchored Triplet Guard (final hardening pass)

Adds:
- receipt-based gas accounting
- improved revert reason extraction
- realized net P&L after gas
- failure logging with tx receipt metadata when available
"""
import sys, os, time, asyncio, requests, json
from pathlib import Path
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import WALLET_ADDRESS, BASE_RPC_URL, PRIVATE_KEY, WETH_ADDRESS, USDC_ADDRESS
from execution.live_executor import live_executor
from web3 import Web3

TRIGGER_PCT = 0.20
MIN_SWAP_USD = 5.0
COOLDOWN_SEC = 30
CHECK_INTERVAL = 10
LOG_EVERY = 6
MAX_UINT_256 = 2**256 - 1
INCH_ROUTER_ADDR = '0x2626664c2603336E57B271c5C0b26F421741e481'
WETH_ADDR = Web3.to_checksum_address(WETH_ADDRESS)
USDC_ADDR = Web3.to_checksum_address(USDC_ADDRESS)
ROUTER_ADDR = Web3.to_checksum_address(INCH_ROUTER_ADDR)
WALLET_ADDR = Web3.to_checksum_address(WALLET_ADDRESS)
ERC20_ABI = json.dumps([
    {"constant":True,"inputs":[{"name":"_owner","type":"address"},{"name":"_spender","type":"address"}],"name":"allowance","outputs":[{"name":"","type":"uint256"}],"type":"function"},
    {"constant":False,"inputs":[{"name":"_spender","type":"address"},{"name":"_value","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"type":"function"},
    {"constant":True,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"},
])

w3 = Web3(Web3.HTTPProvider(BASE_RPC_URL))
account = w3.eth.account.from_key(PRIVATE_KEY)
w3.eth.default_account = account.address
weth_token = w3.eth.contract(address=WETH_ADDR, abi=ERC20_ABI)
usdc_token = w3.eth.contract(address=USDC_ADDR, abi=ERC20_ABI)

STATE_FILE = Path(__file__).parent.parent / 'state' / 'scalp_state.json'
DEQUE_FILE = Path(__file__).parent.parent / 'state' / 'tick_deque.json'
TRADE_AUDIT_PATH = Path(__file__).parent.parent / 'logs' / 'trades.jsonl'
FAILED_SWAP_PATH = Path(__file__).parent.parent / 'logs' / 'failed_swaps.jsonl'
CYCLE_SCORECARD_PATH = Path('/var/www/bazaar/logs/eth_scalper_cycle_scorecard.json')
CYCLE_REALIZED_METRICS_PATH = Path('/var/www/bazaar/logs/eth_scalper_cycle_realized.json')
BLOC_TRACE_PATH = Path('/var/www/bazaar/logs/bloc_trace.jsonl')
CYCLE_LEDGER_PATH = Path('/var/www/bazaar/logs/eth_scalper_cycle_ledger.jsonl')
FORWARD_BASELINE_PATH = Path('/var/www/bazaar/logs/eth_scalper_forward_baseline.json')
DEQUE_MAX = 30
VOL_FLOOR = 0.12
VOL_CAP = 0.20
VOL_MULTIPLIER = 1.10
VOL_FILTER = 0.3
STOP_LOSS = 0.15
EMA_12_ALPHA = 2.0 / 13.0
EMA_50_ALPHA = 2.0 / 51.0
SIGNAL_CONFIRM = 1
PRICE_TOLERANCE = 0.10
RPC_RETRY_BACKOFF = 3
DEFAULT_EST_ROUNDTRIP_FEE_USD = 0.07
MIN_NET_EDGE_BUFFER_USD = 0.00
MIN_WETH_ACCUMULATION_PCT = 0.12
MOMENTUM_HOLD_MIN_TICK_PCT = 0.035
MOMENTUM_FADE_RATIO = 0.55
MOMENTUM_NEG_TICK_PCT = -0.015
SELL_EXTENSION_MIN_PCT = 0.15
SELL_RETRACE_TRIGGER_PCT = 0.03
SELL_ROLLOVER_RETRACE_PCT = 0.10
SELL_ROLLOVER_NEG_TICK_PCT = -0.02
SELL_MIN_EXTENSION_EXIT_PCT = 0.75
REENTRY_RECOVER_ABOVE_SELL_PCT = 0.30
REENTRY_SCORE_THRESHOLD = 0.42
REENTRY_SCORE_ARM_THRESHOLD = 0.34
TWO_CYCLE_WETH_BONUS_WEIGHT = 0.45
SELL_EXTENDED_PROFIT_EXIT_PCT = 0.85
REENTRY_PARITY_BAND_PCT = 0.06
REENTRY_MAX_PREMIUM_PCT = 0.12
REENTRY_COOLDOWN_SEC = 300
REENTRY_FORCE_AFTER_SEC = 1800
REENTRY_START_DISCOUNT_PCT = 0.10
REENTRY_END_PREMIUM_PCT = 0.03
DEEP_REENTRY_DISCOUNT_PCT = 1.0
DEEP_REENTRY_MIN_WETH_GAIN_PCT = 0.02
MISSED_REENTRY_RECOVERY_PCT = 0.55
REENTRY_REANALYZE_AFTER_SEC = 1200
REENTRY_REANALYZE_VOL_MULTIPLIER = 0.55
REENTRY_REANALYZE_MAX_PREMIUM_PCT = 0.75
REENTRY_REANALYZE_MIN_EXPECTED_EDGE_PCT = -0.02
REGIME_VOL_CHAOS_PCT = 6.0
REGIME_VOL_CALM_PCT = 1.5

STATE_FILE.parent.mkdir(exist_ok=True)
TRADE_AUDIT_PATH.parent.mkdir(exist_ok=True)
FAILED_SWAP_PATH.parent.mkdir(exist_ok=True)


def load_state():
    try:
        s = json.loads(STATE_FILE.read_text())
        for k in ('ema_12','ema_50','entry_price','signal_streak','last_trigger','last_sell_price','last_buy_price','last_side','last_weth_amount','last_usdc_amount'):
            s.setdefault(k, 0)
        return s
    except Exception:
        return {'side': 'WETH', 'entry_price': 0, 'last_flip': 0,
                'total_pnl': 0.0, 'trade_count': 0, 'ema_12': 0, 'ema_50': 0,
                'signal_streak': 0, 'last_trigger': 0, 'last_sell_price': 0, 'last_buy_price': 0, 'last_side': 'WETH', 'last_weth_amount': 0, 'last_usdc_amount': 0}

def save_state(s):
    STATE_FILE.write_text(json.dumps(s, indent=2))

def load_deque():
    try: return json.loads(DEQUE_FILE.read_text())
    except Exception: return []

def save_deque(dq):
    try: DEQUE_FILE.write_text(json.dumps(dq))
    except Exception: pass

_price_cache = None
_price_cache_time = 0
_price_ttl = 8

def get_eth_price():
    global _price_cache, _price_cache_time
    now = time.time()
    if _price_cache and now - _price_cache_time < _price_ttl:
        return _price_cache
    get_dual_price()
    return _price_cache

def get_dual_price():
    global _price_cache, _price_cache_time
    now = time.time()
    cb_p = kr_p = None
    try:
        r = requests.get('https://api.coinbase.com/v2/prices/ETH-USD/spot', timeout=5)
        if r.status_code == 200:
            cb_p = float(r.json().get('data', {}).get('amount', 0))
    except Exception:
        pass
    try:
        r = requests.get('https://api.kraken.com/0/public/Ticker?pair=XETHZUSD', timeout=5)
        if r.status_code == 200:
            kr_p = float(r.json().get('result', {}).get('XETHZUSD', {}).get('c', ['0'])[0])
    except Exception:
        pass
    if cb_p and cb_p > 0:
        _price_cache, _price_cache_time = cb_p, now
    if cb_p and kr_p and cb_p > 0 and kr_p > 0:
        div = abs(cb_p - kr_p) / ((cb_p + kr_p) / 2) * 100
        return cb_p, kr_p, div <= PRICE_TOLERANCE
    if cb_p: return cb_p, kr_p, False
    if kr_p: return kr_p, kr_p, False
    return None, None, False

def get_balances(retry=2):
    for attempt in range(retry):
        try:
            weth_wei = weth_token.functions.balanceOf(WALLET_ADDR).call()
            usdc_raw = usdc_token.functions.balanceOf(WALLET_ADDR).call()
        except Exception as e:
            if '429' in str(e) and attempt < retry - 1:
                print(f'   ⏳ RPC rate limit, retry in {RPC_RETRY_BACKOFF}s...')
                time.sleep(RPC_RETRY_BACKOFF)
                continue
            print(f'   ⚠️ Balance read: {e}')
            return None
        weth = weth_wei / 1e18
        usdc = usdc_raw / 1e6
        eth_raw = w3.eth.get_balance(WALLET_ADDR) / 1e18
        p = get_eth_price() or 2300
        return {'weth': weth, 'usdc': usdc, 'eth_raw': eth_raw, 'eth_price': p, 'weth_usd': weth * p, 'total_usd': weth * p + usdc}
    return None

def recent_roundtrip_fee_usd():
    vals = []
    for path in (TRADE_AUDIT_PATH, FAILED_SWAP_PATH):
        try:
            lines = path.read_text().strip().splitlines()[-20:]
            for line in lines:
                if not line.strip():
                    continue
                d = json.loads(line)
                g = d.get('gas_cost_usd')
                if g is not None:
                    vals.append(float(g))
        except Exception:
            pass
    if vals:
        return max(0.01, round((sum(vals) / len(vals)) * 2, 4))
    return DEFAULT_EST_ROUNDTRIP_FEE_USD

def estimate_net_edge_usd(side, price, exit_price, entry_target, bal):
    """Round-trip expectancy gate.
    For WETH: sell now, estimate rebuy at entry_target.
    For USDC: buy now, estimate resell at exit_price.
    """
    if side == 'WETH':
        if price <= entry_target:
            gross_usd = 0.0
        else:
            gross_usd = bal['weth'] * max(0.0, price - entry_target)
    else:
        if exit_price <= price or price <= 0:
            gross_usd = 0.0
        else:
            weth_now = bal['usdc'] / price
            usdc_back = weth_now * exit_price
            gross_usd = max(0.0, usdc_back - bal['usdc'])
    return gross_usd - recent_roundtrip_fee_usd()

def fee_gate_ok(side, price, exit_price, entry_target, bal):
    net_edge = estimate_net_edge_usd(side, price, exit_price, entry_target, bal)
    return net_edge >= MIN_NET_EDGE_BUFFER_USD, net_edge


def expected_weth_after_roundtrip(side, price, exit_price, entry_target, bal):
    fee_factor = 1 - 0.0005
    if side == 'WETH':
        weth_now = bal['weth']
        if price <= 0 or entry_target <= 0: return 0.0
        usdc_after_sell = weth_now * price * fee_factor
        weth_back = (usdc_after_sell / entry_target) * fee_factor
        return weth_back
    else:
        usdc_now = bal['usdc']
        if price <= 0 or exit_price <= 0: return 0.0
        weth_buy = (usdc_now / price) * fee_factor
        return weth_buy

def weth_accumulation_ok(side, price, exit_price, entry_target, bal, state=None):
    current_weth_equiv = bal['weth'] if side == 'WETH' else (bal['usdc'] / price if price > 0 else 0.0)
    expected_weth = expected_weth_after_roundtrip(side, price, exit_price, entry_target, bal)
    if current_weth_equiv <= 0: return False, 0.0, expected_weth
    improvement_pct = ((expected_weth - current_weth_equiv) / current_weth_equiv) * 100.0
    if side == 'USDC' and state:
        last_sell_price = state.get('last_sell_price', 0) or 0
        if last_sell_price > 0 and price <= last_sell_price * (1 - DEEP_REENTRY_DISCOUNT_PCT / 100.0):
            deep_reentry_weth = (bal['usdc'] / price) * (1 - 0.0005) if price > 0 else 0.0
            deep_gain_pct = ((deep_reentry_weth - current_weth_equiv) / current_weth_equiv) * 100.0 if current_weth_equiv > 0 else 0.0
            return deep_gain_pct >= DEEP_REENTRY_MIN_WETH_GAIN_PCT, deep_gain_pct, deep_reentry_weth
    return improvement_pct >= MIN_WETH_ACCUMULATION_PCT, improvement_pct, expected_weth


def expected_weth_after_two_cycles(side, price, exit_price, entry_target, bal):
    fee_factor = 1 - 0.0005
    if side == 'USDC':
        if price <= 0 or exit_price <= 0 or entry_target <= 0:
            return 0.0
        weth1 = (bal['usdc'] / price) * fee_factor
        usdc_after_sell = weth1 * exit_price * fee_factor
        weth2 = (usdc_after_sell / entry_target) * fee_factor
        return weth2
    return expected_weth_after_roundtrip(side, price, exit_price, entry_target, bal)

def clamp01(v):
    return max(0.0, min(1.0, v))

def gas_cost_usd(receipt, eth_price):
    try:
        gas_used = int(receipt.gasUsed)
        eff = int(getattr(receipt, 'effectiveGasPrice', 0) or 0)
        eth_cost = Decimal(gas_used) * Decimal(eff) / Decimal(10**18)
        usd = float(eth_cost) * eth_price
        return round(usd, 6), gas_used, eff
    except Exception:
        return None, None, None

def safe_revert_reason(tx_hash_hex):
    try:
        tx = w3.eth.get_transaction(tx_hash_hex)
        w3.eth.call({
            'to': tx['to'],
            'from': tx['from'],
            'data': tx['input'],
            'value': tx.get('value', 0),
        }, block_identifier=tx['blockNumber'] - 1)
        return None
    except Exception as e:
        return str(e)[:500]

def log_trade(entry):
    try:
        with open(TRADE_AUDIT_PATH, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    except Exception:
        pass

def log_failed_swap(entry):
    try:
        with open(FAILED_SWAP_PATH, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    except Exception:
        pass



def ensure_forward_baseline(current_price=None, bal=None):
    if FORWARD_BASELINE_PATH.exists():
        try:
            return json.loads(FORWARD_BASELINE_PATH.read_text())
        except Exception:
            pass
    bal = bal or get_balances(retry=2) or {}
    price = current_price or get_eth_price() or 0
    baseline = {
        'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'price': price,
        'weth': round(bal.get('weth', 0), 8),
        'usdc': round(bal.get('usdc', 0), 4),
        'weth_equiv': round((bal.get('weth', 0) if bal.get('weth', 0) > 0 else ((bal.get('usdc', 0) / price) if price else 0)), 8),
        'mode': 'forward_canonical_reset'
    }
    FORWARD_BASELINE_PATH.write_text(json.dumps(baseline))
    return baseline

def compute_cycle_scorecard(current_price=None):
    try:
        lines = CYCLE_LEDGER_PATH.read_text().strip().splitlines()
        trades = [json.loads(x) for x in lines if x.strip()]
    except Exception:
        trades = []
    cycles = []
    pending_sell = None
    for t in trades:
        side_before = t.get('side_before')
        side_after = t.get('side_after')
        start_weth = float(t.get('weth_equiv_before', 0) or 0)
        end_weth = float(t.get('weth_equiv_after', 0) or 0)
        if side_before == 'WETH' and side_after == 'USDC' and start_weth > 0:
            pending_sell = t
            continue
        if side_before == 'USDC' and side_after == 'WETH' and pending_sell:
            first, second = pending_sell, t
            cycle_pnl = float(first.get('net_pnl_trade', 0)) + float(second.get('net_pnl_trade', 0))
            cycle_start_weth = float(first.get('weth_equiv_before', 0) or 0)
            cycle_end_weth = float(second.get('weth_equiv_after', 0) or 0)
            if cycle_start_weth > 0 and cycle_end_weth > 0:
                cycles.append({
                    'start_ts': first.get('ts'),
                    'end_ts': second.get('ts'),
                    'path': f"{first.get('side_before')}->{first.get('side_after')}->{second.get('side_after')}",
                    'net_pnl_usd': round(cycle_pnl, 6),
                    'net_weth_change': round(cycle_end_weth - cycle_start_weth, 8),
                    'start_weth': round(cycle_start_weth, 8),
                    'end_weth': round(cycle_end_weth, 8),
                    'entry_class': second.get('entry_class'),
                    'exit_class': first.get('exit_class'),
                    'tx_hashes': [first.get('tx_hash'), second.get('tx_hash')],
                })
            pending_sell = None
    wins = sum(1 for c in cycles if c['net_weth_change'] > 0)
    losses = sum(1 for c in cycles if c['net_weth_change'] < 0)
    total = round(sum(c['net_pnl_usd'] for c in cycles), 6)
    total_weth = round(sum(c['net_weth_change'] for c in cycles), 8)
    baseline = ensure_forward_baseline(current_price)
    baseline_weth = float((baseline or {}).get('weth_equiv', 0) or 0)
    realized_total_weth = round((cycles[-1]['end_weth'] - baseline_weth), 8) if cycles else 0
    score = {
        'cycles_completed': len(cycles),
        'wins': wins,
        'losses': losses,
        'flat': len(cycles) - wins - losses,
        'net_cycle_pnl_usd': total,
        'avg_cycle_pnl_usd': round(total / len(cycles), 6) if cycles else 0,
        'net_weth_change': total_weth,
        'forward_realized_weth_change': realized_total_weth,
        'forward_baseline_weth': baseline_weth,
        'forward_realized_weth_change': realized_total_weth,
        'avg_cycle_weth_change': round(total_weth / len(cycles), 8) if cycles else 0,
        'last_cycle': cycles[-1] if cycles else None,
        'current_mark_price': current_price,
        'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }
    realized = {
        'cycles_completed': len(cycles),
        'forward_baseline': baseline,
        'capital_truth': 'WETH held',
        'net_weth_change': total_weth,
        'forward_baseline_weth': baseline_weth,
        'forward_realized_weth_change': realized_total_weth,
        'avg_cycle_weth_change': round(total_weth / len(cycles), 8) if cycles else 0,
        'positive_cycles': wins,
        'negative_cycles': losses,
        'last_cycle': cycles[-1] if cycles else None,
        'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }
    try:
        CYCLE_SCORECARD_PATH.write_text(json.dumps(score))
        CYCLE_REALIZED_METRICS_PATH.write_text(json.dumps(realized))
    except Exception:
        pass
    return score

def ensure_approvals():
    print('   🔑 Checking token approvals...')
    for name, token, spender in [('WETH', weth_token, ROUTER_ADDR), ('USDC', usdc_token, ROUTER_ADDR)]:
        try:
            allowance = token.functions.allowance(WALLET_ADDR, spender).call()
            if allowance < 10**30:
                print(f'   🔓 Approving {name} for UniV3 SwapRouter...')
                tx = token.functions.approve(spender, MAX_UINT_256).build_transaction({
                    'from': WALLET_ADDR,
                    'nonce': w3.eth.get_transaction_count(WALLET_ADDR),
                    'chainId': 8453,
                    'gas': 80000,
                    'maxFeePerGas': int(w3.eth.gas_price * 1.1),
                    'maxPriorityFeePerGas': int(w3.eth.gas_price * 0.05),
                })
                signed = account.sign_transaction(tx)
                tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
                print(f'   ✅ {name} approve: {Web3.to_hex(tx_hash)}')
                w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
                print(f'   ✅ {name} approved')
            else:
                print(f'   ✅ {name} already approved')
        except Exception as e:
            print(f'   ⚠️ {name} check: {e}')

def do_swap(from_token, to_token, amount_wei, label, entry_price, state, net_edge_estimate=None):
    current_price = get_eth_price() or entry_price
    b_before = get_balances(retry=2) or {}
    change = ((current_price - entry_price) / entry_price * 100) if entry_price else 0
    print(f'\n   🔄 {label} (${current_price:.2f}, {change:+.2f}% from entry)')
    print(f'   📦 Amount: {amount_wei} wei')
    if net_edge_estimate is not None:
        print(f'   📐 Net edge est: ${net_edge_estimate:.2f}')
    swap_data = live_executor.get_swap_data(from_token, to_token, amount_wei)
    if not swap_data:
        print('   ❌ swap quote: no swap data')
        return False
    expected_out = int(swap_data.get('quoted_out', swap_data.get('to_amount', '0')))
    if expected_out <= 0:
        print('   ❌ swap quote: zero output')
        return False
    tx_hash = live_executor.execute_swap(swap_data)
    if not tx_hash:
        print('   ❌ Swap execution failed')
        return False
    print(f'   ✅ Tx: {tx_hash}')

    flip_pnl = 0.0
    tx_confirmed = False
    revert_reason = None
    receipt_block = None
    gas_usd = None
    gas_used = None
    eff_gas_price = None
    tx_hash_hex = tx_hash if isinstance(tx_hash, str) else Web3.to_hex(tx_hash)

    try:
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash_hex, timeout=60)
        receipt_block = receipt.blockNumber
        gas_usd, gas_used, eff_gas_price = gas_cost_usd(receipt, get_eth_price() or entry_price)
        if receipt.status == 1:
            tx_confirmed = True
            print(f'   ✅ Confirmed block {receipt.blockNumber}')
            if gas_usd is not None:
                print(f'   ⛽ Gas cost: ${gas_usd:.4f}')
            current_price = get_eth_price() or entry_price
            b = get_balances(retry=3)
            weth_v = b.get('weth_usd', 0) if b else 0
            usdc_v = b.get('usdc', 0) if b else 0
            if from_token == WETH_ADDR:
                flip_pnl = (current_price - entry_price) / entry_price * weth_v
            else:
                base_val = usdc_v if usdc_v > 0 else current_price * (b.get('weth', 0) if b else 0)
                flip_pnl = -(current_price - entry_price) / entry_price * base_val
            net_after_gas = flip_pnl - (gas_usd or 0)
            state['total_pnl'] = round(state['total_pnl'] + net_after_gas, 2)
            print(f'   💰 Gross P&L: ${flip_pnl:.2f} | Net after gas: ${net_after_gas:.2f} (cumulative: ${state["total_pnl"]:.2f})')
        else:
            revert_reason = safe_revert_reason(tx_hash_hex) or f'receipt status 0 in block {receipt.blockNumber}'
            print(f'   ❌ Tx reverted ({revert_reason})')
    except Exception as e:
        revert_reason = str(e)
        print(f'   ⚠️ Confirm: {e}')

    if not tx_confirmed:
        print(f'   🛑 Swap failed; preserving state as {state["side"]} @ ${state["entry_price"]:.2f}')
        log_failed_swap({
            'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'label': label,
            'from_token': from_token,
            'to_token': to_token,
            'amount': amount_wei,
            'entry_price': entry_price,
            'tx_hash': tx_hash_hex,
            'reason': revert_reason or 'unconfirmed failure',
            'receipt_block': receipt_block,
            'gas_used': gas_used,
            'effective_gas_price': eff_gas_price,
            'gas_cost_usd': gas_usd,
            'state_side': state.get('side'),
            'state_entry': state.get('entry_price'),
        })
        return False

    new_side = 'USDC' if to_token == USDC_ADDR else 'WETH'
    state['last_side'] = state.get('side')
    if new_side == 'USDC':
        state['last_sell_price'] = current_price
    else:
        state['last_buy_price'] = current_price
    state['side'] = new_side
    if new_side != 'USDC':
        state['deep_reentry_seen'] = False
        state['deep_reentry_low'] = 0
    state['entry_price'] = current_price
    state['last_flip'] = time.time()
    state['trade_count'] += 1
    state['signal_streak'] = 0
    b_after = get_balances(retry=2) or {}
    trade_row = {
        'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'label': label,
        'side_before': 'USDC' if from_token == USDC_ADDR else 'WETH',
        'side_after': new_side,
        'entry_price': round(entry_price, 2),
        'exit_price': round(current_price, 2),
        'change_pct': round((current_price - entry_price) / entry_price * 100 if entry_price else 0, 2),
        'amount': amount_wei,
        'gross_pnl_trade': round(flip_pnl, 4),
        'gas_cost_usd': gas_usd,
        'net_pnl_trade': round(flip_pnl - (gas_usd or 0), 4),
        'pnl_cumulative': round(state['total_pnl'], 2),
        'trade_count': state['trade_count'],
        'tx_hash': tx_hash_hex,
        'receipt_block': receipt_block,
        'gas_used': gas_used,
        'effective_gas_price': eff_gas_price,
        'ema_12': round(state.get('ema_12', 0), 2),
        'ema_50': round(state.get('ema_50', 0), 2),
        'trigger': state.get('last_trigger', 0),
        'net_edge_estimate_usd': round(net_edge_estimate, 4) if net_edge_estimate is not None else None,
        'weth_before': round((b_before or {}).get('weth', 0), 8),
        'weth_after': round((b_after or {}).get('weth', 0), 8),
        'usdc_before': round((b_before or {}).get('usdc', 0), 4),
        'usdc_after': round((b_after or {}).get('usdc', 0), 4),
        'cycle_start_weth_equiv': round(((b_before or {}).get('weth', 0) if (b_before or {}).get('weth', 0) > 0 else (((b_before or {}).get('usdc', 0) / entry_price) if entry_price else 0)), 8),
        'cycle_end_weth_equiv': round(((b_after or {}).get('weth', 0) if (b_after or {}).get('weth', 0) > 0 else (((b_after or {}).get('usdc', 0) / current_price) if current_price else 0)), 8),
    }
    log_trade(trade_row)
    log_cycle_ledger({
        'ts': trade_row['ts'],
        'label': label,
        'side_before': trade_row['side_before'],
        'side_after': trade_row['side_after'],
        'entry_class': state.get('entry_class', 'in_position' if new_side == 'WETH' else None),
        'exit_class': state.get('hold_state', 'rollover' if new_side == 'USDC' else None),
        'tx_hash': tx_hash_hex,
        'net_pnl_trade': trade_row['net_pnl_trade'],
        'weth_before': round((b_before or {}).get('weth', 0), 8),
        'weth_after': round((b_after or {}).get('weth', 0), 8),
        'usdc_before': round((b_before or {}).get('usdc', 0), 4),
        'usdc_after': round((b_after or {}).get('usdc', 0), 4),
        'weth_equiv_before': trade_row['cycle_start_weth_equiv'],
        'weth_equiv_after': trade_row['cycle_end_weth_equiv'],
    })
    save_state(state)
    print(f'   ✅ Now in {new_side} @ ${current_price:.2f}')
    return True


def reconcile_state_with_wallet(state, bal, market_price=None):
    wallet_side = 'WETH' if (bal or {}).get('weth', 0) > 0.000001 else ('USDC' if (bal or {}).get('usdc', 0) > 0.01 else state.get('side', 'USDC'))
    price = market_price or state.get('entry_price') or 0
    changed = False
    if state.get('side') != wallet_side:
        state['side'] = wallet_side
        changed = True
    if wallet_side == 'WETH':
        if price > 0 and (not state.get('entry_price') or state.get('entry_price', 0) <= 0):
            state['entry_price'] = price
            changed = True
        state['deep_reentry_seen'] = False
        state['deep_reentry_low'] = 0
    if wallet_side == 'USDC':
        state['sell_peak_price'] = 0
    return wallet_side, changed

async def run():
    live_executor.enable(); live_executor.chain_id = 8453; live_executor.wallet = WALLET_ADDR
    state = load_state(); deque = load_deque(); tick = 0
    print('=' * 65)
    print('🤖 COMPOUND SCALP v3 (Triplet Guard)')
    print(f'   Wallet:     {WALLET_ADDR[:10]}...')
    print(f'   Trigger:    {TRIGGER_PCT}% adaptive | Cooldown: {COOLDOWN_SEC}s')
    print(f'   Anchor:     EMA_12 / EMA_50 | Stop: {STOP_LOSS}% below EMA_50')
    print(f'   Guards:     {SIGNAL_CONFIRM}x confirm | dual-source price | on-chain')
    print(f'   Current:    {state["side"]} @ ${state["entry_price"] or "—"}')
    print(f'   Trades:     {state["trade_count"]} | P&L: ${state["total_pnl"]:.2f}')
    print(f'   EMA_12:     {state.get("ema_12", 0):.2f} | EMA_50: {state.get("ema_50", 0):.2f}')
    print('=' * 65)
    try: ensure_approvals()
    except Exception as e: print(f'   ⚠️ Approval: {e}')
    while True:
        try:
            tick += 1
            cb_p, kr_p, price_confirmed = get_dual_price()
            if cb_p and cb_p > 0: p = cb_p
            elif kr_p and kr_p > 0: p = kr_p
            else:
                print('   ⏳ No price source'); await asyncio.sleep(CHECK_INTERVAL); continue
            bal = get_balances(retry=2)
            if not bal:
                await asyncio.sleep(CHECK_INTERVAL); continue
            wallet_side, changed = reconcile_state_with_wallet(state, bal, cb_p or kr_p)
            if changed: save_state(state)
            entry_price = state['entry_price']
            if entry_price == 0:
                state['entry_price'] = p; state['ema_12'] = p; state['ema_50'] = p; save_state(state)
                await asyncio.sleep(CHECK_INTERVAL); continue
            if state['ema_12'] == 0 or state['ema_12'] is None:
                state['ema_12'] = p; state['ema_50'] = p
            else:
                state['ema_12'] = p * EMA_12_ALPHA + state['ema_12'] * (1 - EMA_12_ALPHA)
                state['ema_50'] = p * EMA_50_ALPHA + state['ema_50'] * (1 - EMA_50_ALPHA)
            cooldown_ok = time.time() - state['last_flip'] >= COOLDOWN_SEC
            side = state['side']; ema12 = state['ema_12']; ema50 = state['ema_50']
            change_pct = (p - entry_price) / entry_price * 100
            tick_change_pct = ((p - deque[-1]['price']) / deque[-1]['price'] * 100) if deque and isinstance(deque[-1], dict) and deque[-1].get('price') else 0.0
            anchor_distance_pct = abs((p - ema12) / ema12) * 100 if ema12 else 0.0
            deque.append({'price': round(p, 6), 'anchor_distance_pct': round(anchor_distance_pct, 4), 'tick_change_pct': round(tick_change_pct, 5)})
            if len(deque) > DEQUE_MAX: deque.pop(0)
            avg_vol = sum(x['anchor_distance_pct'] if isinstance(x, dict) else x for x in deque) / len(deque) if deque else 0.0
            recent_ticks = [x.get('tick_change_pct', 0.0) for x in deque[-5:] if isinstance(x, dict)]
            momentum_peak = max(recent_ticks) if recent_ticks else 0.0
            momentum_now = recent_ticks[-1] if recent_ticks else 0.0
            if side == 'WETH':
                state['sell_peak_price'] = max(state.get('sell_peak_price', 0) or 0, p)
            else:
                state['sell_peak_price'] = 0
            peak_price = state.get('sell_peak_price', 0) or p
            extension_from_entry_pct = ((peak_price - entry_price) / entry_price * 100.0) if entry_price else 0.0
            retrace_from_peak_pct = ((peak_price - p) / peak_price * 100.0) if peak_price else 0.0
            extension_hold = side == 'WETH' and extension_from_entry_pct >= SELL_EXTENSION_MIN_PCT and retrace_from_peak_pct < SELL_RETRACE_TRIGGER_PCT
            regime_factor = 1.15 if avg_vol >= REGIME_VOL_CHAOS_PCT else (0.95 if avg_vol <= REGIME_VOL_CALM_PCT else 1.0)
            trigger = max(VOL_FLOOR, min(VOL_CAP, round(avg_vol * VOL_MULTIPLIER * regime_factor, 2)))
            state['last_trigger'] = trigger; save_deque(deque)
            exit_price = ema12 * (1 + trigger / 100.0)
            momentum_hold = side == 'WETH' and p >= exit_price and momentum_peak >= MOMENTUM_HOLD_MIN_TICK_PCT and momentum_now > max(MOMENTUM_NEG_TICK_PCT, momentum_peak * MOMENTUM_FADE_RATIO)
            continuation_hold = side == 'WETH' and ((p >= exit_price and (momentum_hold or extension_hold)) or (extension_from_entry_pct >= SELL_MIN_EXTENSION_EXIT_PCT and retrace_from_peak_pct < SELL_ROLLOVER_RETRACE_PCT and momentum_now > SELL_ROLLOVER_NEG_TICK_PCT))
            rollover_ready = side == 'WETH' and extension_from_entry_pct >= SELL_MIN_EXTENSION_EXIT_PCT and (retrace_from_peak_pct >= SELL_ROLLOVER_RETRACE_PCT or momentum_now <= SELL_ROLLOVER_NEG_TICK_PCT or (momentum_peak > 0 and momentum_now <= momentum_peak * MOMENTUM_FADE_RATIO))
            extended_profit_rollover_exit = side == 'WETH' and extension_from_entry_pct >= SELL_EXTENDED_PROFIT_EXIT_PCT and rollover_ready
            hold_state = 'continuation' if continuation_hold else ('rollover' if rollover_ready else ('armed' if side == 'WETH' and p >= exit_price else 'hold'))
            entry_target = ema12 * (1 - trigger / 100.0)
            stop_price = ema50 * (1 - STOP_LOSS / 100.0)
            move_ok = anchor_distance_pct >= avg_vol * VOL_FILTER if avg_vol > 0 else True
            fee_ok, fee_edge = fee_gate_ok(side, p, exit_price, entry_target, bal)
            weth_ok, weth_edge_pct, expected_weth = weth_accumulation_ok(side, p, exit_price, entry_target, bal, state)
            last_sell_price = state.get('last_sell_price', 0) or 0
            if side == 'USDC' and last_sell_price > 0 and p <= last_sell_price * (1 - DEEP_REENTRY_DISCOUNT_PCT / 100.0):
                state['deep_reentry_seen'] = True
                state['deep_reentry_low'] = min(state.get('deep_reentry_low', p) or p, p)
            elif side != 'USDC':
                state['deep_reentry_seen'] = False
                state['deep_reentry_low'] = 0
            parity_anchor = last_sell_price if last_sell_price > 0 else ema12
            time_since_flip = max(0.0, time.time() - state.get('last_flip', 0))
            decay_progress = min(1.0, time_since_flip / REENTRY_FORCE_AFTER_SEC) if REENTRY_FORCE_AFTER_SEC > 0 else 1.0
            target_reentry_pct = REENTRY_START_DISCOUNT_PCT + (REENTRY_END_PREMIUM_PCT - REENTRY_START_DISCOUNT_PCT) * decay_progress
            reentry_target_price = parity_anchor * (1 + target_reentry_pct / 100.0)
            reentry_band_price = ema12 * (1 + REENTRY_PARITY_BAND_PCT / 100.0)
            reentry_ceiling_price = min(reentry_target_price, reentry_band_price)
            reentry_premium_pct = ((p - parity_anchor) / parity_anchor * 100.0) if parity_anchor else 999
            reentry_window_ok = side == 'USDC' and time_since_flip <= REENTRY_COOLDOWN_SEC
            deep_low = state.get('deep_reentry_low', 0) or 0
            reanalyze_active = side == 'USDC' and time_since_flip >= REENTRY_REANALYZE_AFTER_SEC
            volatility_reentry_pct = min(REENTRY_REANALYZE_MAX_PREMIUM_PCT, max(REENTRY_END_PREMIUM_PCT, avg_vol * REENTRY_REANALYZE_VOL_MULTIPLIER))
            volatility_reentry_ceiling = parity_anchor * (1 + volatility_reentry_pct / 100.0) if parity_anchor else 0
            expected_weth_two_cycle = expected_weth_after_two_cycles(side, p, exit_price, entry_target, bal)
            current_weth_equiv = bal['weth'] if side == 'WETH' else (bal['usdc'] / p if p > 0 else 0.0)
            two_cycle_edge_pct = (((expected_weth_two_cycle - current_weth_equiv) / current_weth_equiv) * 100.0) if current_weth_equiv > 0 else 0.0
            recent_prices = [x.get('price', p) for x in deque[-12:] if isinstance(x, dict)]
            local_low = min(recent_prices) if recent_prices else p
            local_high = max(recent_prices) if recent_prices else p
            pullback_from_high_pct = (((local_high - p) / local_high) * 100.0) if local_high else 0.0
            bounce_from_low_pct = (((p - local_low) / local_low) * 100.0) if local_low else 0.0
            wave_quality = clamp01((pullback_from_high_pct / max(0.2, avg_vol)) * 0.55 + (bounce_from_low_pct / max(0.2, avg_vol)) * 0.45)
            trend_drift = clamp01(((p - ema12) / ema12 * 100.0 + avg_vol) / max(0.5, avg_vol * 2)) if ema12 else 0.0
            edge_score = clamp01((weth_edge_pct + 0.12) / 0.35)
            two_cycle_score = clamp01((two_cycle_edge_pct + 0.18) / 0.55)
            reentry_score = clamp01(wave_quality * 0.35 + edge_score * 0.25 + two_cycle_score * TWO_CYCLE_WETH_BONUS_WEIGHT + trend_drift * 0.15)
            entry_class = 'chase'
            if side == 'USDC' and p <= entry_target and weth_ok:
                entry_class = 'ideal_dip'
            elif side == 'USDC' and recovery_mode and reentry_premium_pct <= REENTRY_RECOVER_ABOVE_SELL_PCT and two_cycle_edge_pct >= 0.0 and reentry_score >= REENTRY_SCORE_THRESHOLD:
                entry_class = 'fair_recovery'
            elif side == 'USDC' and reentry_score >= REENTRY_SCORE_ARM_THRESHOLD:
                entry_class = 'arm_wait'
            recovery_mode = side == 'USDC' and last_sell_price > 0 and p >= last_sell_price and reanalyze_active
            volatility_reentry_signal = side == 'USDC' and cooldown_ok and bal['usdc'] >= MIN_SWAP_USD and fee_ok and entry_class == 'fair_recovery' and recovery_mode
            missed_recovery_signal = side == 'USDC' and state.get('deep_reentry_seen') and deep_low > 0 and p <= deep_low * (1 + MISSED_REENTRY_RECOVERY_PCT / 100.0) and p < last_sell_price and cooldown_ok and bal['usdc'] >= MIN_SWAP_USD and fee_ok
            reentry_signal = side == 'USDC' and cooldown_ok and bal['usdc'] >= MIN_SWAP_USD and fee_ok and entry_class == 'ideal_dip'
            force_reentry_signal = side == 'USDC' and cooldown_ok and bal['usdc'] >= MIN_SWAP_USD and fee_ok and entry_class == 'fair_recovery' and time_since_flip >= REENTRY_FORCE_AFTER_SEC
            sell_signal = side == 'WETH' and move_ok and cooldown_ok and bal['weth'] * p >= MIN_SWAP_USD and fee_ok and weth_ok and ((p >= exit_price and rollover_ready) or extended_profit_rollover_exit)
            discounted_entry_signal = side == 'USDC' and p <= entry_target and move_ok and weth_ok
            buy_signal = side == 'USDC' and (discounted_entry_signal or reentry_signal or force_reentry_signal or missed_recovery_signal or volatility_reentry_signal) and cooldown_ok and bal['usdc'] >= MIN_SWAP_USD and fee_ok
            stop_signal = side == 'WETH' and p <= stop_price and cooldown_ok

            if sell_signal or stop_signal:
                state['signal_streak'] = max(1, state.get('signal_streak', 0) + 1)
            elif buy_signal and (reentry_signal or force_reentry_signal or missed_recovery_signal or volatility_reentry_signal):
                state['signal_streak'] = SIGNAL_CONFIRM
            elif buy_signal:
                state['signal_streak'] = max(1, state.get('signal_streak', 0) + 1)
            else:
                state['signal_streak'] = 0
            streak = state['signal_streak']
            signal_ok = streak >= SIGNAL_CONFIRM

            if tick % LOG_EVERY == 0:
                src = f'CB${cb_p:.2f}' if cb_p else ''
                if kr_p: src += f' KR${kr_p:.2f}'
                if price_confirmed: src += ' ✅'
                fee_est = recent_roundtrip_fee_usd()
                print(f'   [{time.strftime("%H:%M:%S")}] {side} {src} MA12=${ema12:.2f} MA50=${ema50:.2f} Δ{p-ema12:+.2f} v{avg_vol*100:.2f}% trig={trigger}% streak={streak}/{SIGNAL_CONFIRM} feeEst=${fee_est:.2f} edge=${fee_edge:.2f} | W={bal["weth"]:.4f} S={bal["usdc"]:.2f} | {state["trade_count"]}t ${state["total_pnl"]:.2f}')
            if side == 'WETH' and p >= exit_price and not fee_ok:
                print(f'   ⛔ SELL gate blocked by fee math (net est ${fee_edge:.2f})')
            elif side == 'WETH' and p >= exit_price and not weth_ok:
                print(f'   ⛔ SELL gate blocked by WETH accumulation math ({weth_edge_pct:.3f}%)')
            elif continuation_hold:
                print(f'   ⏳ SELL hold: continuation alive (tick {momentum_now:.4f}% peak {momentum_peak:.4f}%)')
            elif side == 'USDC' and (discounted_entry_signal or reentry_signal or force_reentry_signal or missed_recovery_signal) and not fee_ok:
                print(f'   ⛔ BUY gate blocked by fee math (net est ${fee_edge:.2f})')
            elif side == 'USDC' and (discounted_entry_signal or reentry_signal or force_reentry_signal or volatility_reentry_signal) and not weth_ok:
                print(f'   ⛔ BUY gate blocked by WETH accumulation math ({weth_edge_pct:.3f}%)')
            elif missed_recovery_signal:
                print(f'   ♻️ BUY recovery: deep-discount rebound entry armed (low ${deep_low:.2f})')

            if sell_signal and signal_ok:
                weth_wei = int(bal['weth'] * 1e18) - 1000
                if weth_wei > 1000:
                    do_swap(WETH_ADDR, USDC_ADDR, max(1, weth_wei), f'SELL (p>{exit_price:.2f})', p, state, fee_edge)
            elif buy_signal and signal_ok:
                usdc_raw = int(bal['usdc'] * 1e6) - 10
                if usdc_raw > 1000:
                    buy_label = f'BUY (p<{entry_target:.2f})'
                    if missed_recovery_signal:
                        buy_label = f'BUY-RECOVERY (low {deep_low:.2f})'
                    do_swap(USDC_ADDR, WETH_ADDR, max(1, usdc_raw), buy_label, p, state, fee_edge)
            elif stop_signal and signal_ok:
                weth_wei = int(bal['weth'] * 1e18) - 1000
                if weth_wei > 1000:
                    do_swap(WETH_ADDR, USDC_ADDR, max(1, weth_wei), f'STOP (p<{stop_price:.2f})', p, state, None)
            if tick % 30 == 0: save_state(state)
            if tick % 6 == 0:
                try:
                    cycle_score = compute_cycle_scorecard(p)
                    status_payload = {
                        'side': state['side'], 'price': p, 'entry': state['entry_price'], 'ema_12': round(ema12, 2), 'ema_50': round(ema50, 2),
                        'change': round(change_pct, 2), 'trades': state['trade_count'], 'pnl': round(state['total_pnl'], 2), 'weth': round(bal['weth'], 6),
                        'usdc': round(bal['usdc'], 2), 'trigger': trigger, 'vol': round(avg_vol * 100, 2), 'signal_streak': streak,
                        'price_confirmed': price_confirmed, 'fee_gate_ok': fee_ok, 'fee_edge_estimate_usd': round(fee_edge, 4),
                        'reentry_signal': reentry_signal, 'force_reentry_signal': force_reentry_signal, 'volatility_reentry_signal': volatility_reentry_signal, 'entry_class': entry_class, 'reentry_score': round(reentry_score, 4), 'wave_quality': round(wave_quality, 4), 'pullback_from_high_pct': round(pullback_from_high_pct, 4), 'bounce_from_low_pct': round(bounce_from_low_pct, 4), 'expected_weth_two_cycle': round(expected_weth_two_cycle, 8), 'two_cycle_edge_pct': round(two_cycle_edge_pct, 5), 'recovery_mode': recovery_mode, 'last_sell_price': last_sell_price, 'reentry_premium_pct': round(reentry_premium_pct, 4), 'reentry_target_pct': round(target_reentry_pct, 4), 'time_since_flip_sec': round(time_since_flip, 1), 'weth_edge_pct': round(weth_edge_pct, 5), 'expected_weth_after_cycle': round(expected_weth, 8), 'tick_change_pct': round(tick_change_pct, 5), 'momentum_peak_pct': round(momentum_peak, 5), 'continuation_hold': continuation_hold, 'momentum_hold': momentum_hold, 'rollover_ready': rollover_ready, 'extended_profit_rollover_exit': extended_profit_rollover_exit, 'hold_state': hold_state, 'missed_recovery_signal': missed_recovery_signal, 'reanalyze_active': reanalyze_active, 'volatility_reentry_pct': round(volatility_reentry_pct, 4), 'extension_from_entry_pct': round(extension_from_entry_pct, 4), 'retrace_from_peak_pct': round(retrace_from_peak_pct, 4), 'deep_reentry_seen': state.get('deep_reentry_seen'), 'deep_reentry_low': state.get('deep_reentry_low', 0),
                        'cycle_scorecard': cycle_score,
                        'cycle_realized': json.loads(CYCLE_REALIZED_METRICS_PATH.read_text()) if CYCLE_REALIZED_METRICS_PATH.exists() else {},
                        'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                    }
                    Path('/var/www/bazaar/logs/eth_scalper_status.json').write_text(json.dumps(status_payload))
                    try:
                        BLOC_TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
                        with BLOC_TRACE_PATH.open('a') as fh:
                            fh.write(json.dumps({
                                'ts': status_payload['ts'],
                                'price': status_payload['price'],
                                'entry': status_payload['entry'],
                                'ema_12': status_payload['ema_12'],
                                'trigger': status_payload['trigger'],
                                'prime_sell': round(status_payload['ema_12'] * (1 + status_payload['trigger'] / 100.0), 6),
                                'prime_buy': round(status_payload['entry'] * (1 - status_payload['trigger'] / 100.0), 6) if status_payload['entry'] else 0,
                                'preferred_reentry': round((status_payload['last_sell_price'] or status_payload['price']) * (1 + status_payload['volatility_reentry_pct'] / 100.0), 6),
                                'hold_state': status_payload['hold_state'],
                                'continuation_hold': status_payload['continuation_hold'],
                                'rollover_ready': status_payload['rollover_ready'],
                                'weth_edge_pct': status_payload['weth_edge_pct']
                            }) + '\n')
                    except Exception:
                        pass
                except Exception: pass
            await asyncio.sleep(CHECK_INTERVAL)
        except Exception as e:
            print(f'   ❌ Loop: {e}'); await asyncio.sleep(10)

def main(): asyncio.run(run())
if __name__ == '__main__': main()
