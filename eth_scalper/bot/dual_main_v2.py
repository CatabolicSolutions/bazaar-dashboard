"""
Dual-asset Rotation Bot v2 — Extended entry point.
Runs 3-state rotation: WETH ↔ BTC ↔ USDC.
v2: rotate signal tracking, arm_wait suppression, post-rotate hold, churn guard.
"""
import asyncio, json, time, sys, os
from pathlib import Path
from collections import deque

from bot.dual_rotator import ROTATE_POST_HOLD_BARS

ROOT_DIR = Path(__file__).resolve().parent.parent
PACKAGE_PARENT = ROOT_DIR.parent
for candidate in (str(ROOT_DIR), str(PACKAGE_PARENT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)
from config.settings import WALLET_ADDRESS, BASE_RPC_URL, PRIVATE_KEY, \
    WETH_ADDRESS, USDC_ADDRESS, CBBTC_ADDRESS, CHAIN_ID
from web3 import Web3

from bot.main import (load_state, save_state, load_deque, save_deque,
                      get_balances as _get_balances,
                      do_swap, ensure_approvals, ensure_forward_baseline,
                      log_trade, log_failed_swap, STATE_FILE, TRADE_AUDIT_PATH,
                      live_executor, w3, WETH_ADDR, USDC_ADDR, ERC20_ABI,
                      CHECK_INTERVAL, COOLDOWN_SEC, STOP_LOSS, TRIGGER_PCT,
                      compute_cycle_scorecard, gas_cost_usd, safe_revert_reason,
                      estimate_net_edge_usd)

from bot.dual_rotator import get_both_prices, update_emas, decide

# == Constants ==
CBBTC_ADDR = Web3.to_checksum_address(CBBTC_ADDRESS)
DEQUE_WETH_FILE = Path(__file__).parent.parent / 'state' / 'deque_weth.json'
DEQUE_BTC_FILE = Path(__file__).parent.parent / 'state' / 'deque_btc.json'
ROTATE_STATE_FILE = Path(__file__).parent.parent / 'state' / 'rotate_state.json'
Q_HISTORY_FILE = Path(__file__).parent.parent / 'state' / 'q_history.json'

_cbbtc_token = None

def get_cbbtc_token():
    global _cbbtc_token
    if _cbbtc_token is None:
        _cbbtc_token = w3.eth.contract(address=CBBTC_ADDR, abi=json.loads(
            '[{"constant":true,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf",'
            '"outputs":[{"name":"balance","type":"uint256"}],"type":"function"}]'
        ))
    return _cbbtc_token


def get_balances(retry=2):
    bal = _get_balances(retry)
    if bal is None:
        return None
    try:
        cbbtc_wei = get_cbbtc_token().functions.balanceOf(WALLET_ADDRESS).call()
        bal['cbbtc'] = cbbtc_wei / 1e8
    except:
        bal['cbbtc'] = 0
    return bal


def reconcile_state(state, bal):
    has_weth = bal.get('weth', 0) > 0.0005
    has_btc = bal.get('cbbtc', 0) > 0.00001
    in_asset = has_weth or has_btc
    state['in_WETH'] = bool(has_weth)
    state['in_BTC'] = bool(has_btc)
    if has_weth and not (state.get('entry_WETH') or 0):
        state['entry_WETH'] = bal.get('eth_price') or state.get('last_buy_price') or state.get('ema12_WETH') or 0
    if has_btc and not (state.get('entry_BTC') or 0):
        state['entry_BTC'] = bal.get('btc_price') or state.get('ema12_BTC') or 0
    current_side = state.get('side', 'USDC')
    if in_asset and current_side == 'USDC':
        new_side = 'WETH' if has_weth else 'BTC'
        new_price = bal.get('eth_price' if new_side == 'WETH' else 'btc_price') or state.get(f'entry_{new_side}', 0) or 0
        state['side'] = new_side
        state[f'entry_{new_side}'] = max(state.get(f'entry_{new_side}', 0) or 0, new_price)
        state['entry_price'] = state[f'entry_{new_side}']
        print(f'   🔄 Reconciled side → {new_side} (wallet has asset)')
        return True
    if not in_asset and current_side != 'USDC':
        state['side'] = 'USDC'
        state['in_WETH'] = False
        state['in_BTC'] = False
        state['entry_price'] = 0
        state['last_sell_price'] = bal.get('eth_price', 2300)
        print(f'   🔄 Reconciled side → USDC (wallet empty)')
        return True
    if in_asset and current_side != 'USDC':
        if current_side == 'WETH' and not has_weth and has_btc:
            state['side'] = 'BTC'
            new_price = bal.get('btc_price') or state.get('entry_BTC', 0) or 0
            state['entry_BTC'] = max(state.get('entry_BTC', 0) or 0, new_price)
            state['entry_price'] = state['entry_BTC']
            state['hold_bars_WETH'] = 0
            state['peak_WETH'] = 0
            print(f'   🔄 Reconciled side → BTC (had WETH state but wallet has BTC)')
            return True
        if current_side == 'BTC' and not has_btc and has_weth:
            state['side'] = 'WETH'
            new_price = bal.get('eth_price') or state.get('entry_WETH', 0) or 0
            state['entry_WETH'] = max(state.get('entry_WETH', 0) or 0, new_price)
            state['entry_price'] = state['entry_WETH']
            state['hold_bars_BTC'] = 0
            state['peak_BTC'] = 0
            print(f'   🔄 Reconciled side → WETH (had BTC state but wallet has WETH)')
            return True
    return False


def load_deque(path, default=None):
    try:
        if path.exists():
            d = json.loads(path.read_text())
            return d if isinstance(d, list) else (default or [])
    except: pass
    return default or []


def save_deque(path, dq):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tail = list(dq)[-50:]
        path.write_text(json.dumps(tail))
    except Exception as e:
        print(f'   ⚠️ Deque save: {e}')


def load_rotate_state():
    try:
        if ROTATE_STATE_FILE.exists():
            return json.loads(ROTATE_STATE_FILE.read_text())
    except: pass
    return {'signal': 'NONE', 'streak': 0}


def save_rotate_state(rs):
    try:
        ROTATE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        ROTATE_STATE_FILE.write_text(json.dumps(rs))
    except Exception as e:
        print(f'   ⚠️ Rotate state save: {e}')


async def run():
    live_executor.enable()
    state = load_state()
    qw = deque(load_deque(DEQUE_WETH_FILE, []), maxlen=50)
    qb = deque(load_deque(DEQUE_BTC_FILE, []), maxlen=50)
    rotate_state = load_rotate_state()
    q_history = deque(load_deque(Q_HISTORY_FILE, []), maxlen=50)
    tick = 0

    for k in ['WETH', 'BTC']:
        state.setdefault(f'ema12_{k}', None)
        state.setdefault(f'ema50_{k}', None)
        state.setdefault(f'entry_{k}', 0)
        state.setdefault(f'peak_{k}', 0)
        state.setdefault(f'hold_bars_{k}', 0)
        state.setdefault(f'in_{k}', False)
    state.setdefault('bars_since_flip', 0)
    state.setdefault('side', 'USDC')
    state.setdefault('post_rotate_hold_until', 0)

    print('=' * 70)
    print('🤖 DUAL ROTATOR v2  —  WETH | cbBTC | USDC  (rotate-signal arch)')
    print(f'   Wallet:  {WALLET_ADDRESS[:10]}...')
    print(f'   Side:    {state.get("side","USDC")}')
    print(f'   P&L:     ${state.get("total_pnl",0):.2f} ({state.get("trade_count",0)} trades)')
    print(f'   RotSig:  {rotate_state}')
    print('=' * 70)

    try:
        ensure_approvals()
        from bot.main import live_executor as exe
        ROUTER = Web3.to_checksum_address('0x2626664c2603336E57B271c5C0b26F421741e481')
        cbbtc_tok = w3.eth.contract(address=CBBTC_ADDR, abi=json.loads(
            '[{"constant":true,"inputs":[{"name":"owner","type":"address"},{"name":"spender","type":"address"}],'
            '"name":"allowance","outputs":[{"name":"","type":"uint256"}],"type":"function"},'
            '{"constant":false,"inputs":[{"name":"spender","type":"address"},{"name":"amount","type":"uint256"}],'
            '"name":"approve","outputs":[{"name":"","type":"bool"}],"type":"function"}]'
        ))
        allowance = cbbtc_tok.functions.allowance(WALLET_ADDRESS, ROUTER).call()
        if allowance < 1e6:
            print('   Approving cbBTC for Uniswap Router...')
            tx = cbbtc_tok.functions.approve(ROUTER, 2**256 - 1).build_transaction({
                'chainId': CHAIN_ID, 'from': WALLET_ADDRESS,
                'nonce': w3.eth.get_transaction_count(WALLET_ADDRESS),
                'gas': 80000, 'maxFeePerGas': int(w3.eth.gas_price * 1.1),
                'maxPriorityFeePerGas': int(w3.eth.gas_price * 0.05), 'type': 2,
            })
            signed = w3.eth.account.from_key(PRIVATE_KEY).sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            print(f'   cbBTC approval tx: {tx_hash.hex()}')
            w3.eth.wait_for_transaction_receipt(tx_hash, timeout=90)
    except Exception as e:
        print(f'   ⚠️ Approvals: {e}')

    while True:
        try:
            tick += 1

            eth_p, btc_p, confirmed = get_both_prices()
            if not eth_p or not btc_p:
                print(f'   [{tick}] ⏳ No price source')
                await asyncio.sleep(3)
                continue

            bal = get_balances(retry=2)
            if not bal:
                await asyncio.sleep(3)
                continue
            bal['eth_price'] = eth_p
            bal['btc_price'] = btc_p
            state['last_weth_amount'] = round(bal.get('weth', 0) or 0, 8)
            state['last_btc_amount'] = round(bal.get('cbbtc', 0) or 0, 8)
            state['last_cbbtc_amount'] = state['last_btc_amount']
            state['notional_weth'] = state['last_weth_amount']
            state['notional_btc'] = state['last_btc_amount']
            if state.get('side') == 'BTC' and state['last_btc_amount'] > 0 and ((state.get('entry_BTC', 0) or 0) < 10000):
                state['entry_BTC'] = btc_p
            if state.get('side') == 'WETH' and state['last_weth_amount'] > 0 and not (state.get('entry_WETH', 0) or 0):
                state['entry_WETH'] = eth_p

            changed = reconcile_state(state, bal)
            if changed:
                save_state(state)

            side = state.get('side', 'USDC')

            if state.get('ema12_WETH') is None or state['ema12_WETH'] == 0:
                state['ema12_WETH'] = eth_p
                state['ema50_WETH'] = eth_p
                state['ema12_BTC'] = btc_p
                state['ema50_BTC'] = btc_p
                save_state(state)
                print(f'   [{tick}] EMAs initialized')
                await asyncio.sleep(3)
                continue

            update_emas(state, eth_p, btc_p)

            # Track tick-level history for rotate signal
            q_history.append({'spread_pct': (eth_p - btc_p * 0.029) / eth_p * 100,
                              'eth_price': eth_p, 'btc_price': btc_p})
            if len(q_history) > 50:
                q_history.popleft()

            state['bars_since_flip'] = state.get('bars_since_flip', 0) + 1
            state['in_WETH'] = side == 'WETH'
            state['in_BTC'] = side == 'BTC'
            if side == 'WETH':
                if not (state.get('entry_WETH') or 0):
                    state['entry_WETH'] = eth_p
                state['peak_WETH'] = max(state.get('peak_WETH', 0) or 0, eth_p)
                state['hold_bars_WETH'] = state.get('hold_bars_WETH', 0) + 1
                state['hold_bars_BTC'] = 0
            elif side == 'BTC':
                if not (state.get('entry_BTC') or 0):
                    state['entry_BTC'] = btc_p
                state['peak_BTC'] = max(state.get('peak_BTC', 0) or 0, btc_p)
                state['hold_bars_BTC'] = state.get('hold_bars_BTC', 0) + 1
                state['hold_bars_WETH'] = 0
            else:
                state['peak_WETH'] = 0
                state['peak_BTC'] = 0
                state['hold_bars_WETH'] = 0
                state['hold_bars_BTC'] = 0

            # === 6. Rotation decision (v2 with rotate signal + gating) ===
            action = decide(state, eth_p, btc_p, qw, qb, q_history, tick, rotate_state)
            act = action['action']
            reason = action.get('reason', '')
            rotate_state = action.get('rotate_state', rotate_state)
            
            # Post-rotate hold tracking
            if action.get('post_rotate'):
                state['post_rotate_hold_until'] = tick + ROTATE_POST_HOLD_BARS
                state['last_entry_idx'] = tick
                state['last_flip_idx'] = tick
                # Reset rotate_state streak after commit
                if rotate_state['signal'] != 'NONE':
                    rotate_state['streak'] = 0
                    rotate_state['signal'] = 'NONE'
            
            state['last_action'] = act
            state['last_action_reason'] = reason
            
            signal_info = ''
            if action.get('signal') and action['signal'] != 'NONE':
                signal_info = f' | sig={action["signal"]}({action.get("signal_edge", 0):.2f}%)'
            
            line = f'   [{tick}] {act:12s} | ETH ${eth_p:.0f} BTC ${btc_p:.0f} | {reason[:60]}{signal_info}'
            print(line)

            # === 7. Execute ===
            if act == 'EXIT_WETH':
                raw = int(bal.get('weth', 0) * 1e18) - 1000
                if raw > 1000:
                    do_swap(WETH_ADDR, USDC_ADDR, max(1, raw), f'SELL_WETH_{eth_p:.0f}', eth_p, state, None)

            elif act == 'EXIT_BTC':
                raw = int(bal.get('cbbtc', 0) * 1e8) - 1000
                if raw > 1000:
                    do_swap(CBBTC_ADDR, USDC_ADDR, max(1, raw), f'SELL_BTC_{btc_p:.0f}', btc_p, state, None)

            elif act == 'ENTER_WETH':
                raw = int(bal.get('usdc', 0) * 1e6) - 10
                if raw > 1000:
                    fee = estimate_net_edge_usd('USDC', eth_p, 0, 0, bal)
                    do_swap(USDC_ADDR, WETH_ADDR, max(1, raw), f'BUY_WETH_{eth_p:.0f}', eth_p, state, fee)

            elif act == 'ENTER_BTC':
                raw = int(bal.get('usdc', 0) * 1e6) - 10
                if raw > 1000:
                    fee = estimate_net_edge_usd('USDC', btc_p, 0, 0, bal)
                    do_swap(USDC_ADDR, CBBTC_ADDR, max(1, raw), f'BUY_BTC_{btc_p:.0f}', btc_p, state, fee)

            # === 8. Save state ===
            save_state(state)
            save_rotate_state(rotate_state)
            save_deque(DEQUE_WETH_FILE, qw)
            save_deque(DEQUE_BTC_FILE, qb)
            save_deque(Q_HISTORY_FILE, list(q_history))

            # === 9. Status report ===
            if tick % 6 == 0:
                try:
                    score = compute_cycle_scorecard(eth_p)
                    grp = f'Score: {score:.2f} | P&L: ${state.get("total_pnl",0):.2f}'
                    wb = bal.get('weth', 0)
                    bb = bal.get('cbbtc', 0)
                    print(f'   📊 {grp} | WETH: {wb:.6f} BTC: {bb:.8f} USDC: ${bal.get("usdc",0):.2f}')
                except Exception as e:
                    print(f'   📊 report: {e}')

            # === 10. Arb check ===
            if tick % 3 == 0:
                try:
                    from bot.arb_monitor import check_arb_and_execute, init_web3
                    if not hasattr(check_arb_and_execute, '_w3'):
                        w3a, pool = init_web3(BASE_RPC_URL)
                        check_arb_and_execute._w3 = w3a
                        check_arb_and_execute._pool = pool
                    check_arb_and_execute(do_swap, get_balances,
                                         check_arb_and_execute._w3,
                                         check_arb_and_execute._pool,
                                         state, side, bal, eth_p)
                except Exception as e:
                    print(f'   📊 Arb: {e}')

            await asyncio.sleep(3)

        except KeyboardInterrupt:
            print('\n   🛑 Shutdown')
            save_state(state)
            save_rotate_state(rotate_state)
            save_deque(DEQUE_WETH_FILE, qw)
            save_deque(DEQUE_BTC_FILE, qb)
            save_deque(Q_HISTORY_FILE, list(q_history))
            break
        except Exception as e:
            print(f'   🔴 Loop: {e}')
            import traceback; traceback.print_exc()
            await asyncio.sleep(3)


def main():
    asyncio.run(run())

if __name__ == '__main__':
    main()
