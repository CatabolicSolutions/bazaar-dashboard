from pathlib import Path
p = Path('/var/www/bazaar/dashboard/scripts/serve_dashboard.py')
text = p.read_text()
old = """        scalp_pool.update({
            'side': sp.get('side', '--'),
            'entry': sp.get('entry', 0),
            'current_price': price,
            'change_pct': sp.get('change', 0),
            'trades': sp.get('trades', 0),
            'pnl': sp.get('pnl', 0),
            'weth': weth_v,
            'usdc': usdc_v,
            'trigger': sp.get('trigger', 0.20),
            'vol': sp.get('vol', 0),
            'value_usd': round(weth_v * price + usdc_v, 2) if price else usdc_v,
            'ts': sp.get('ts', ''),
        })
"""
new = """        trigger = sp.get('trigger', 0.20)
        ema12 = sp.get('ema_12', 0)
        last_sell = sp.get('last_sell_price', 0)
        vol_reentry = sp.get('volatility_reentry_pct', 0)
        scalp_pool.update({
            'side': sp.get('side', '--'),
            'effective_side': sp.get('side', '--'),
            'state_side': sp.get('side', '--'),
            'entry': sp.get('entry', 0),
            'current_price': price,
            'change_pct': sp.get('change', 0),
            'trades': sp.get('trades', 0),
            'pnl': sp.get('pnl', 0),
            'weth': weth_v,
            'usdc': usdc_v,
            'trigger': trigger,
            'vol': sp.get('vol', 0),
            'ema_12': ema12,
            'ema_50': sp.get('ema_50', 0),
            'prime_sell_price': round(ema12 * (1 + trigger / 100.0), 6) if ema12 else None,
            'prime_buy_price': round((sp.get('entry', 0) or ema12) * (1 - trigger / 100.0), 6) if (sp.get('entry', 0) or ema12) else None,
            'preferred_reentry_price': round((last_sell or price) * (1 + vol_reentry / 100.0), 6) if (last_sell or price) else None,
            'distance_to_prime_buy_pct': (((round((sp.get('entry', 0) or ema12) * (1 - trigger / 100.0), 6) if (sp.get('entry', 0) or ema12) else 0) - price) / price * 100) if price and (sp.get('entry', 0) or ema12) else None,
            'distance_to_preferred_reentry_pct': (((round((last_sell or price) * (1 + vol_reentry / 100.0), 6) if (last_sell or price) else 0) - price) / price * 100) if price and (last_sell or price) else None,
            'value_usd': round(weth_v * price + usdc_v, 2) if price else usdc_v,
            'ts': sp.get('ts', ''),
            'entry_class': sp.get('entry_class'),
            'reentry_score': sp.get('reentry_score'),
            'wave_quality': sp.get('wave_quality'),
            'recovery_mode': sp.get('recovery_mode'),
            'last_sell_price': last_sell,
            'reentry_signal': sp.get('reentry_signal'),
            'force_reentry_signal': sp.get('force_reentry_signal'),
            'volatility_reentry_signal': sp.get('volatility_reentry_signal'),
            'missed_recovery_signal': sp.get('missed_recovery_signal'),
            'reanalyze_active': sp.get('reanalyze_active'),
            'continuation_hold': sp.get('continuation_hold'),
            'rollover_ready': sp.get('rollover_ready'),
            'hold_state': sp.get('hold_state'),
            'extension_from_entry_pct': sp.get('extension_from_entry_pct'),
            'retrace_from_peak_pct': sp.get('retrace_from_peak_pct'),
            'weth_edge_pct': sp.get('weth_edge_pct'),
            'two_cycle_edge_pct': sp.get('two_cycle_edge_pct'),
            'expected_weth_after_cycle': sp.get('expected_weth_after_cycle'),
            'expected_weth_two_cycle': sp.get('expected_weth_two_cycle'),
            'volatility_reentry_pct': vol_reentry,
            'reentry_premium_pct': sp.get('reentry_premium_pct'),
            'time_since_flip_sec': sp.get('time_since_flip_sec'),
            'cycle_scorecard': sp.get('cycle_scorecard', {}),
            'cycle_realized': sp.get('cycle_realized', {}),
        })
"""
text = text.replace(old, new)
p.write_text(text)
print('ok')
