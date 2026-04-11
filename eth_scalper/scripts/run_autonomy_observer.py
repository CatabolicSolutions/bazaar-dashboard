import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import json
import time
from datetime import datetime, UTC

from bot.main import ETHScalper
from signals.price_feed import price_feed
from signals.momentum import momentum_detector
from execution.trade_manager import trade_manager
from execution.live_executor import live_executor
from wallet_monitor import wallet_monitor
from config.settings import AUTO_MANUAL_BUY_FALLBACK_SECONDS, PAPER_TRADING_MODE


def ts():
    return datetime.now(UTC).isoformat()


async def main():
    bot = ETHScalper()
    live_executor.enable()
    print(json.dumps({'event': 'executor_enabled', 'timestamp': ts(), 'enabled': live_executor.enabled, 'id': id(live_executor)}), flush=True)
    bot.check_interval = 10
    bot.dashboard_update_interval = 999999
    bot.heartbeat_interval = 999999
    bot.stats_interval = 999999

    start = time.time()
    history = []
    entry_observed = None
    buy_tx = None
    sell_tx = None
    monitoring = []

    print(json.dumps({
        'event': 'runtime_start',
        'timestamp': ts(),
        'paper_trading_mode': PAPER_TRADING_MODE,
        'fallback_seconds': AUTO_MANUAL_BUY_FALLBACK_SECONDS,
        'check_interval': bot.check_interval,
    }), flush=True)

    while time.time() - start < 420:
        now = time.time()
        current_price = price_feed.get_eth_price()
        stats = price_feed.get_price_stats()
        signal = momentum_detector.detect_momentum()
        open_positions = trade_manager.get_open_positions()
        fallback_ready = (not PAPER_TRADING_MODE and now - bot.last_forced_entry > AUTO_MANUAL_BUY_FALLBACK_SECONDS and len(open_positions) == 0)

        sample = {
            'event': 'sample',
            'timestamp': ts(),
            'elapsed_sec': round(now - start, 1),
            'price': current_price,
            'history_length': stats.get('history_length'),
            'change_60s_pct': stats.get('change_60s_pct'),
            'gas_gwei': stats.get('gas_gwei'),
            'momentum_signal': None if not signal else {
                'direction': signal['direction'],
                'score': signal['score'],
                'change_60s_pct': signal['change_60s_pct'],
                'type': signal['type'],
            },
            'fallback_ready': fallback_ready,
            'open_positions': len(open_positions),
        }
        history.append(sample)
        print(json.dumps(sample), flush=True)

        if entry_observed is None and signal:
            entry_observed = {'path': 'momentum', 'timestamp': ts(), 'signal': signal}
        elif entry_observed is None and fallback_ready:
            entry_observed = {'path': 'fallback', 'timestamp': ts()}

        await bot._tick()

        open_positions = trade_manager.get_open_positions()
        if open_positions:
            for pos in open_positions:
                mon = {
                    'event': 'monitor',
                    'timestamp': ts(),
                    'position_id': pos.id,
                    'entry_price': pos.entry_price,
                    'target_price': pos.target_price,
                    'stop_price': pos.stop_price,
                    'tx_hash': getattr(pos, 'tx_hash', None),
                    'executed_to_amount_units': getattr(pos, 'executed_to_amount_units', None),
                    'hold_time_sec': round(time.time() - pos.entry_time, 1),
                    'current_price': price_feed.get_eth_price(),
                }
                monitoring.append(mon)
                print(json.dumps(mon), flush=True)
                if not buy_tx and getattr(pos, 'tx_hash', None):
                    buy_tx = pos.tx_hash

        if entry_observed and not trade_manager.get_open_positions() and buy_tx:
            # likely exited, capture latest history trade if available
            for hist_pos in reversed(trade_manager.trade_history):
                if getattr(hist_pos, 'tx_hash', None) == buy_tx:
                    sell_tx = getattr(hist_pos, 'exit_tx_hash', None)
                    break
            break

        await asyncio.sleep(bot.check_interval)

    wallet = wallet_monitor.get_all_balances()
    final = {
        'event': 'final',
        'timestamp': ts(),
        'entry_observed': entry_observed,
        'buy_tx_hash': buy_tx,
        'sell_tx_hash': sell_tx,
        'open_positions': len(trade_manager.get_open_positions()),
        'trade_history_count': len(trade_manager.trade_history),
        'final_balances': wallet,
        'samples_collected': len(history),
        'monitor_checks': len(monitoring),
    }
    print(json.dumps(final), flush=True)


asyncio.run(main())
