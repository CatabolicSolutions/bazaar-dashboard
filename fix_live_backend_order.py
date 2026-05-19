from pathlib import Path
p = Path('/var/www/bazaar/dashboard/scripts/serve_dashboard.py')
text = p.read_text()
old = """    # ── Operator summary ──
    parts = []
    if has_live_tradier:
        parts.append(f'Tradier API live: buying_power={tradier_buying_power}')
    else:
        parts.append('Tradier: stale file fallback')
    if live_positions:
        parts.append(f'{len(live_positions)} live positions')
    sv = scalp_pool.get('value_usd', 0)
    parts.append(f'Scalp wallet: ${sv:.2f}' if sv > 0 else 'Scalp: idle')
    parts.append(f'bias={direction["bias"]} confidence={direction["confidence"]}')
    operator_summary = ' | '.join(parts)

    next_actions = direction.get('next_actions', [])
    if not has_live_tradier:
        next_actions.insert(0, 'Tradier API unavailable — verify credentials or network')
    if freshness.get('bloc_stale', False):
        next_actions.append('Bloc state is stale — check eth-scalper service')

    # -- Live scalp pool (from algo bot status file) --
"""
new = """    # -- Live scalp pool (from algo bot status file) --
"""
text = text.replace(old, new, 1)
anchor = """    # -- Live tradier pool --
"""
insert = """
    # ── Operator summary ──
    parts = []
    if has_live_tradier:
        parts.append(f'Tradier API live: buying_power={tradier_buying_power}')
    else:
        parts.append('Tradier: stale file fallback')
    if live_positions:
        parts.append(f'{len(live_positions)} live positions')
    sv = scalp_pool.get('value_usd', 0)
    parts.append(f'Scalp wallet: ${sv:.2f}' if sv > 0 else 'Scalp: idle')
    parts.append(f'bias={direction["bias"]} confidence={direction["confidence"]}')
    operator_summary = ' | '.join(parts)

    next_actions = direction.get('next_actions', [])
    if not has_live_tradier:
        next_actions.insert(0, 'Tradier API unavailable — verify credentials or network')
    if freshness.get('bloc_stale', False):
        next_actions.append('Bloc state is stale — check eth-scalper service')

"""
text = text.replace(anchor, insert + anchor, 1)
p.write_text(text)
print('ok')
