import sys, json, time
from pathlib import Path

ROOT = Path('/var/www/bazaar/eth_scalper')
PARENT = ROOT.parent
for c in (str(ROOT), str(PARENT)):
    if c not in sys.path:
        sys.path.insert(0, c)

main_py = ROOT / 'bot' / 'main.py'
text = main_py.read_text()
if 'def log_cycle_ledger(' not in text:
    insert_after = """def log_failed_swap(entry):
    try:
        with open(FAILED_SWAP_PATH, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    except Exception:
        pass


"""
    insert = """def log_cycle_ledger(entry):
    try:
        CYCLE_LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CYCLE_LEDGER_PATH, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    except Exception:
        pass


"""
    text = text.replace(insert_after, insert_after + insert)
    main_py.write_text(text)

import bot.main as m  # noqa

# Recover state from wallet + last trade
state = m.load_state()
bal = m.get_balances(retry=3) or {}
price = m.get_eth_price() or state.get('entry_price') or 0
changed = False
wallet_side, changed = m.reconcile_state_with_wallet(state, bal, price)

trade_path = ROOT / 'logs' / 'trades.jsonl'
last_trade = None
if trade_path.exists():
    for line in reversed(trade_path.read_text(errors='ignore').splitlines()):
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get('label') == 'FORCE-REENTER':
            last_trade = row
            break

if wallet_side == 'WETH':
    state['side'] = 'WETH'
    if last_trade:
        state['entry_price'] = float(last_trade.get('exit_price') or price)
        state['last_buy_price'] = float(last_trade.get('exit_price') or price)
        state['last_flip'] = time.time()
        state['trade_count'] = max(int(state.get('trade_count', 0)), int(last_trade.get('trade_count', state.get('trade_count', 0))))
    else:
        state['entry_price'] = price
        state['last_buy_price'] = price
    state['signal_streak'] = 0
    state['deep_reentry_seen'] = False
    state['deep_reentry_low'] = 0
    state['sell_peak_price'] = max(float(state.get('sell_peak_price', 0) or 0), price)

m.save_state(state)
print({'wallet_side': wallet_side, 'price': price, 'weth': bal.get('weth'), 'usdc': bal.get('usdc'), 'entry_price': state.get('entry_price'), 'trade_count': state.get('trade_count')})
