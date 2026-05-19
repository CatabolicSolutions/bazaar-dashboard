from pathlib import Path
p = Path('/var/www/bazaar/eth_scalper/bot/main.py')
text = p.read_text()
orig = text

if 'STALE_HOLD_EXIT_AFTER_SEC' not in text:
    text = text.replace(
        'REENTRY_PARITY_BAND_PCT = 0.04\n',
        'REENTRY_PARITY_BAND_PCT = 0.04\nSTALE_HOLD_EXIT_AFTER_SEC = 900\nSTALE_HOLD_MAX_LOSS_PCT = 0.12\nSTALE_HOLD_MAX_EXTENSION_PCT = 0.05\n'
    )

old = """            sell_signal = side == 'WETH' and move_ok and cooldown_ok and bal['weth'] * p >= MIN_SWAP_USD and fee_ok and weth_ok and ((p >= exit_price and rollover_ready) or extended_profit_rollover_exit)
            discounted_entry_signal = side == 'USDC' and p <= entry_target and move_ok and weth_ok
            buy_signal = side == 'USDC' and (discounted_entry_signal or reentry_signal or force_reentry_signal or missed_recovery_signal or volatility_reentry_signal) and cooldown_ok and bal['usdc'] >= MIN_SWAP_USD and fee_ok
            stop_signal = side == 'WETH' and p <= stop_price and cooldown_ok
"""
new = """            stale_loss_exit = side == 'WETH' and cooldown_ok and time_since_flip >= STALE_HOLD_EXIT_AFTER_SEC and extension_from_entry_pct <= STALE_HOLD_MAX_EXTENSION_PCT and change_pct <= -STALE_HOLD_MAX_LOSS_PCT
            sell_signal = side == 'WETH' and move_ok and cooldown_ok and bal['weth'] * p >= MIN_SWAP_USD and fee_ok and weth_ok and ((p >= exit_price and rollover_ready) or extended_profit_rollover_exit)
            discounted_entry_signal = side == 'USDC' and p <= entry_target and move_ok and weth_ok
            buy_signal = side == 'USDC' and (discounted_entry_signal or reentry_signal or force_reentry_signal or missed_recovery_signal or volatility_reentry_signal) and cooldown_ok and bal['usdc'] >= MIN_SWAP_USD and fee_ok
            stop_signal = side == 'WETH' and cooldown_ok and (p <= stop_price or stale_loss_exit)
"""
text = text.replace(old, new)

old2 = """            elif continuation_hold:
                print(f'   ⏳ SELL hold: continuation alive (tick {momentum_now:.4f}% peak {momentum_peak:.4f}%)')
"""
new2 = """            elif continuation_hold:
                print(f'   ⏳ SELL hold: continuation alive (tick {momentum_now:.4f}% peak {momentum_peak:.4f}%)')
            elif stale_loss_exit:
                print(f'   🛑 SELL stale-loss exit armed ({change_pct:.3f}% after {time_since_flip:.0f}s without extension)')
"""
text = text.replace(old2, new2)

if text == orig:
    raise SystemExit('no change')

Path('/var/www/bazaar/eth_scalper/bot/main.py.staleexitbak').write_text(orig)
p.write_text(text)
print('ok')
