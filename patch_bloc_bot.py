def patch_bloc_bot():
    """Add trade journal logging to ETH scalper bot"""
    path = '/var/www/bazaar/eth_scalper/bot/main.py'
    if not os.path.exists(path):
        print(f"ERROR: {path} not found")
        return False
    backup(path)
    with open(path, 'r') as f:
        lines = f.readlines()
    
    # 1. Add import after sys.path.insert line
    for i, line in enumerate(lines):
        if 'sys.path.insert' in line:
            # Insert after this line
            indent = len(line) - len(line.lstrip())
            lines.insert(i+1, ' ' * indent + 'from trade_journal import log_trade\n')
            break
    
    # 2. Find line with risk_manager.record_trade(position.signal, position.size_usd, paper=False)
    for i, line in enumerate(lines):
        if 'risk_manager.record_trade(position.signal, position.size_usd, paper=False)' in line:
            indent = len(line) - len(line.lstrip())
            # Add log_trade after this line
            # Determine side from signal.direction
            side = 'buy'
            # We'll attempt to get direction from position.signal.direction
            # If not available, default to buy
            # Determine quantity: position.size_usd / position.entry_price
            # entry_price may be position.entry_price
            # We'll use placeholder values; can be improved later
            log_line = ' ' * indent + 'try:\n'
            log_line += ' ' * indent + '    side = "buy" if position.signal.direction == "long" else "sell"\n'
            log_line += ' ' * indent + '    quantity = position.size_usd / position.entry_price if position.entry_price else 0\n'
            log_line += ' ' * indent + '    log_trade("bloc", "WETH", side, quantity, position.entry_price, pnl=None, notes="ETH scalper")\n'
            log_line += ' ' * indent + 'except Exception as e:\n'
            log_line += ' ' * indent + '    print(f"Failed to log trade: {e}")\n'
            lines.insert(i+1, log_line)
            break
    
    with open(path, 'w') as f:
        f.writelines(lines)
    print(f"Patched {path}")
    return True