from pathlib import Path
p = Path('/var/www/bazaar/eth_scalper/bot/main.py')
text = p.read_text()
orig = text

if 'FAST_RECLAIM_WINDOW_SEC' not in text:
    text = text.replace(
        'REENTRY_FORCE_AFTER_SEC = 1800\nREENTRY_START_DISCOUNT_PCT = 0.10\n',
        'REENTRY_FORCE_AFTER_SEC = 1800\nFAST_RECLAIM_WINDOW_SEC = 600\nFAST_RECLAIM_MIN_SCORE = 0.28\nFAST_RECLAIM_ABOVE_SELL_PCT = 0.00\nREENTRY_START_DISCOUNT_PCT = 0.10\n'
    )

old_block = """            reanalyze_active = side == 'USDC' and time_since_flip >= REENTRY_REANALYZE_AFTER_SEC
            volatility_reentry_pct = min(REENTRY_REANALYZE_MAX_PREMIUM_PCT, max(REENTRY_END_PREMIUM_PCT, avg_vol * REENTRY_REANALYZE_VOL_MULTIPLIER))
            reentry_premium_pct = ((p - last_sell_price) / last_sell_price * 100.0) if last_sell_price > 0 else 0.0
            expected_weth_two_cycle = expected_weth_after_two_cycles(side, p, exit_price, entry_target, bal)
            current_weth_equiv = bal['weth'] if side == 'WETH' else (bal['usdc'] / p if p > 0 else 0.0)
            two_cycle_edge_pct = (((expected_weth_two_cycle - current_weth_equiv) / current_weth_equiv) * 100.0) if current_weth_equiv > 0 else 0.0
            recent_prices = [x.get('price', p) for x in deque[-12:] if isinstance(x, dict)]
            local_low = min(recent_prices) if recent_prices else p
            local_high = max(recent_prices) if recent_prices else p
            pullback_from_high_pct = (((local_high - p) / local_high) * 100.0) if local_high else 0.0
            bounce_from_low_pct = (((p - local_low) / local_low) * 100.0) if local_low else 0.0
            wave_quality = clamp01((pullback_from_high_pct / max(0.2, avg_vol)) * 0.55 + (bounce_from_low_pct / max(0.2, avg_vol)) * 0.45)
            trend_drift = clamp01(((p - ema12) / ema12 * 100.0 + avg_vol) / max(0.5, avg_vol * 2)) if ema12 else 0.0
            edge_score = clamp01((weth_edge_pct + 0.12) / 0.35)
            two_cycle_score = clamp01((two_cycle_edge_pct + 0.18) / 0.55)
            reentry_score = clamp01(wave_quality * 0.35 + edge_score * 0.25 + two_cycle_score * TWO_CYCLE_WETH_BONUS_WEIGHT + trend_drift * 0.15)
            entry_class = 'chase'
            if side == 'USDC' and p <= entry_target and weth_ok:
                entry_class = 'ideal_dip'
            elif side == 'USDC' and recovery_mode and reentry_premium_pct <= REENTRY_RECOVER_ABOVE_SELL_PCT and two_cycle_edge_pct >= 0.0 and reentry_score >= REENTRY_SCORE_THRESHOLD:
                entry_class = 'fair_recovery'
            elif side == 'USDC' and reentry_score >= REENTRY_SCORE_ARM_THRESHOLD:
                entry_class = 'arm_wait'
            recovery_mode = side == 'USDC' and last_sell_price > 0 and p >= last_sell_price and reanalyze_active
            volatility_reentry_signal = side == 'USDC' and cooldown_ok and bal['usdc'] >= MIN_SWAP_USD and fee_ok and entry_class == 'fair_recovery' and recovery_mode
            missed_recovery_signal = side == 'USDC' and state.get('deep_reentry_seen') and deep_low > 0 and p <= deep_low * (1 + MISSED_REENTRY_RECOVERY_PCT / 100.0) and p < last_sell_price and cooldown_ok and bal['usdc'] >= MIN_SWAP_USD and fee_ok
            reentry_signal = side == 'USDC' and cooldown_ok and bal['usdc'] >= MIN_SWAP_USD and fee_ok and entry_class == 'ideal_dip'
            force_reentry_signal = side == 'USDC' and cooldown_ok and bal['usdc'] >= MIN_SWAP_USD and fee_ok and entry_class == 'fair_recovery' and time_since_flip >= REENTRY_FORCE_AFTER_SEC
"""
new_block = """            reanalyze_active = side == 'USDC' and time_since_flip >= REENTRY_REANALYZE_AFTER_SEC
            volatility_reentry_pct = min(REENTRY_REANALYZE_MAX_PREMIUM_PCT, max(REENTRY_END_PREMIUM_PCT, avg_vol * REENTRY_REANALYZE_VOL_MULTIPLIER))
            reentry_premium_pct = ((p - last_sell_price) / last_sell_price * 100.0) if last_sell_price > 0 else 0.0
            fast_reclaim_active = side == 'USDC' and last_sell_price > 0 and time_since_flip <= FAST_RECLAIM_WINDOW_SEC and p >= last_sell_price * (1 + FAST_RECLAIM_ABOVE_SELL_PCT / 100.0)
            recovery_mode = side == 'USDC' and last_sell_price > 0 and p >= last_sell_price and (reanalyze_active or fast_reclaim_active)
            expected_weth_two_cycle = expected_weth_after_two_cycles(side, p, exit_price, entry_target, bal)
            current_weth_equiv = bal['weth'] if side == 'WETH' else (bal['usdc'] / p if p > 0 else 0.0)
            two_cycle_edge_pct = (((expected_weth_two_cycle - current_weth_equiv) / current_weth_equiv) * 100.0) if current_weth_equiv > 0 else 0.0
            recent_prices = [x.get('price', p) for x in deque[-12:] if isinstance(x, dict)]
            local_low = min(recent_prices) if recent_prices else p
            local_high = max(recent_prices) if recent_prices else p
            pullback_from_high_pct = (((local_high - p) / local_high) * 100.0) if local_high else 0.0
            bounce_from_low_pct = (((p - local_low) / local_low) * 100.0) if local_low else 0.0
            wave_quality = clamp01((pullback_from_high_pct / max(0.2, avg_vol)) * 0.55 + (bounce_from_low_pct / max(0.2, avg_vol)) * 0.45)
            trend_drift = clamp01(((p - ema12) / ema12 * 100.0 + avg_vol) / max(0.5, avg_vol * 2)) if ema12 else 0.0
            edge_score = clamp01((weth_edge_pct + 0.12) / 0.35)
            two_cycle_score = clamp01((two_cycle_edge_pct + 0.18) / 0.55)
            reclaim_bonus = 0.18 if fast_reclaim_active and p >= ema12 else 0.0
            reentry_score = clamp01(wave_quality * 0.35 + edge_score * 0.25 + two_cycle_score * TWO_CYCLE_WETH_BONUS_WEIGHT + trend_drift * 0.15 + reclaim_bonus)
            entry_class = 'chase'
            if side == 'USDC' and p <= entry_target and weth_ok:
                entry_class = 'ideal_dip'
            elif side == 'USDC' and fast_reclaim_active and p >= ema12 and reentry_score >= FAST_RECLAIM_MIN_SCORE:
                entry_class = 'fast_reclaim'
            elif side == 'USDC' and recovery_mode and reentry_premium_pct <= REENTRY_RECOVER_ABOVE_SELL_PCT and two_cycle_edge_pct >= 0.0 and reentry_score >= REENTRY_SCORE_THRESHOLD:
                entry_class = 'fair_recovery'
            elif side == 'USDC' and reentry_score >= REENTRY_SCORE_ARM_THRESHOLD:
                entry_class = 'arm_wait'
            volatility_reentry_signal = side == 'USDC' and cooldown_ok and bal['usdc'] >= MIN_SWAP_USD and fee_ok and entry_class == 'fair_recovery' and recovery_mode
            missed_recovery_signal = side == 'USDC' and state.get('deep_reentry_seen') and deep_low > 0 and p <= deep_low * (1 + MISSED_REENTRY_RECOVERY_PCT / 100.0) and p < last_sell_price and cooldown_ok and bal['usdc'] >= MIN_SWAP_USD and fee_ok
            reentry_signal = side == 'USDC' and cooldown_ok and bal['usdc'] >= MIN_SWAP_USD and fee_ok and (entry_class == 'ideal_dip' or entry_class == 'fast_reclaim')
            force_reentry_signal = side == 'USDC' and cooldown_ok and bal['usdc'] >= MIN_SWAP_USD and fee_ok and entry_class == 'fair_recovery' and time_since_flip >= REENTRY_FORCE_AFTER_SEC
"""
text = text.replace(old_block, new_block)

text = text.replace("'reentry_signal': reentry_signal, 'force_reentry_signal': force_reentry_signal, 'volatility_reentry_signal': volatility_reentry_signal, 'entry_class': entry_class,",
                    "'reentry_signal': reentry_signal, 'force_reentry_signal': force_reentry_signal, 'volatility_reentry_signal': volatility_reentry_signal, 'fast_reclaim_active': fast_reclaim_active, 'entry_class': entry_class,")

if text == orig:
    raise SystemExit('no change')
Path('/var/www/bazaar/eth_scalper/bot/main.py.fastreclaimbak').write_text(orig)
p.write_text(text)
print('ok')
