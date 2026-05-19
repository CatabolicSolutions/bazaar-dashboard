from pathlib import Path
p=Path('/var/www/bazaar/eth_scalper/bot/main.py')
text=p.read_text()
orig=text
# Ensure durable cycle ledger helper exists
if 'def log_cycle_ledger(' not in text:
    marker="""def log_failed_swap(entry):
    try:
        with open(FAILED_SWAP_PATH, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    except Exception:
        pass


"""
    insert=marker+"""def log_cycle_ledger(entry):
    try:
        CYCLE_LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CYCLE_LEDGER_PATH, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    except Exception:
        pass


"""
    text=text.replace(marker, insert)
# Fence: never crash after confirmed swap just because logging helper is missing
text=text.replace("""    log_trade(trade_row)
    log_cycle_ledger({
""","""    log_trade(trade_row)
    try:
        log_cycle_ledger({
""")
text=text.replace("""        'weth_equiv_before': trade_row['cycle_start_weth_equiv'],
        'weth_equiv_after': trade_row['cycle_end_weth_equiv'],
    })
    save_state(state)
""","""        'weth_equiv_before': trade_row['cycle_start_weth_equiv'],
        'weth_equiv_after': trade_row['cycle_end_weth_equiv'],
        })
    except Exception as e:
        print(f'   ⚠️ cycle ledger log failed: {e}')
    save_state(state)
""")
if text==orig:
    print('no_change')
else:
    p.write_text(text)
    print('ok')
