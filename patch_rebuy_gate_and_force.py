from pathlib import Path
p = Path('/var/www/bazaar/eth_scalper/bot/main.py')
text = p.read_text()
orig = text
text = text.replace('MIN_WETH_ACCUMULATION_PCT = 0.12', 'MIN_WETH_ACCUMULATION_PCT = 0.05')
text = text.replace('FAST_RECLAIM_MIN_SCORE = 0.28', 'FAST_RECLAIM_MIN_SCORE = 0.22')
text = text.replace("entry_class = 'ideal_dip'", "entry_class = 'ideal_dip'")
text = text.replace("            discounted_entry_signal = side == 'USDC' and p <= entry_target and move_ok and weth_ok\n", "            discounted_entry_signal = side == 'USDC' and p <= entry_target and move_ok and (weth_ok or two_cycle_edge_pct >= 0.05)\n")
if text == orig:
    raise SystemExit('no change')
p.write_text(text)
print('ok')
