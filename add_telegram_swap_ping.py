from pathlib import Path
p = Path('/var/www/bazaar/eth_scalper/bot/main.py')
text = p.read_text()

if 'def notify_telegram_swap(' not in text:
    insert_after = """def log_cycle_ledger(entry):
    try:
        CYCLE_LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CYCLE_LEDGER_PATH, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    except Exception:
        pass


"""
    insert = """def notify_telegram_swap(trade_row, state, bal_after=None):
    try:
        token = os.getenv('TELEGRAM_BOT_TOKEN')
        chat_id = os.getenv('TELEGRAM_CHAT_ID')
        if not token or not chat_id:
            return
        bal_after = bal_after or {}
        msg = (
            f"🔁 SCALP SWAP\\n"
            f"label: {trade_row.get('label')}\\n"
            f"side: {trade_row.get('side_before')} → {trade_row.get('side_after')}\\n"
            f"price: ${float(trade_row.get('exit_price') or 0):.2f}\\n"
            f"change vs entry: {float(trade_row.get('change_pct') or 0):+.2f}%\\n"
            f"gas: ${float(trade_row.get('gas_cost_usd') or 0):.4f}\\n"
            f"cum pnl: ${float(state.get('total_pnl') or 0):.2f}\\n"
            f"weth: {float(bal_after.get('weth', 0) or 0):.6f}\\n"
            f"usdc: ${float(bal_after.get('usdc', 0) or 0):.2f}\\n"
            f"tx: {trade_row.get('tx_hash')}"
        )
        requests.post(f'https://api.telegram.org/bot{token}/sendMessage', json={'chat_id': chat_id, 'text': msg}, timeout=10)
    except Exception:
        pass


"""
    text = text.replace(insert_after, insert_after + insert)

old = """    log_cycle_ledger({
        'ts': trade_row['ts'],
        'label': trade_row['label'],
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
"""
new = """    log_cycle_ledger({
        'ts': trade_row['ts'],
        'label': trade_row['label'],
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
    notify_telegram_swap(trade_row, state, b_after)
    print(f'   ✅ Now in {new_side} @ ${current_price:.2f}')
    return True
"""
text = text.replace(old, new)

p.write_text(text)
print('ok')
