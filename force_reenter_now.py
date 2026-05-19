import sys
from pathlib import Path

ROOT = Path('/var/www/bazaar/eth_scalper')
PARENT = ROOT.parent
for candidate in (str(ROOT), str(PARENT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import bot.main as m  # noqa

m.live_executor.enable()
m.live_executor.chain_id = 8453
m.live_executor.wallet = m.WALLET_ADDR

state = m.load_state()
bal = m.get_balances(retry=3)
price = m.get_eth_price() or state.get('entry_price') or 0

if not bal:
    raise SystemExit('no balances available')
if bal.get('usdc', 0) < m.MIN_SWAP_USD:
    raise SystemExit(f'not enough USDC: {bal.get("usdc")}')

usdc_raw = int(bal['usdc'] * 1e6) - 10
if usdc_raw <= 1000:
    raise SystemExit(f'usdc_raw too small: {usdc_raw}')

print({'price': price, 'usdc': bal.get('usdc'), 'state_side': state.get('side'), 'entry_price': state.get('entry_price')})
ok = m.do_swap(m.USDC_ADDR, m.WETH_ADDR, max(1, usdc_raw), 'FORCE-REENTER', price, state, None)
print({'ok': ok})
if not ok:
    raise SystemExit('force re-enter failed')
