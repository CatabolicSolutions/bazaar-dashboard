import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import json
import time
from datetime import datetime, UTC

from bot.main import ETHScalper
from execution.live_executor import live_executor
from execution.trade_manager import trade_manager
from signals.price_feed import price_feed
from state_manager import state_manager

TARGET_ID = 'pos_1_1775983277'


def ts():
    return datetime.now(UTC).isoformat()


async def main():
    bot = ETHScalper()
    live_executor.enable()
    resumed = await bot._resume_persisted_live_positions()
    print(json.dumps({'event': 'resume', 'timestamp': ts(), 'resumed': resumed, 'open_positions': len(trade_manager.get_open_positions())}), flush=True)

    start = time.time()
    while time.time() - start < 360:
        pos = trade_manager.get_position(TARGET_ID)
        current_price = price_feed.get_eth_price()
        persisted = [p for p in state_manager.load_persisted_positions() if p.get('id') == TARGET_ID]
        sample = {
            'event': 'sample',
            'timestamp': ts(),
            'current_price': current_price,
            'persisted': persisted,
            'active_found': bool(pos),
        }
        if pos:
            hold_time = time.time() - pos.entry_time
            sample['position'] = {
                'id': pos.id,
                'tx_hash': getattr(pos, 'tx_hash', None),
                'entry_price': pos.entry_price,
                'target_price': pos.target_price,
                'stop_price': pos.stop_price,
                'hold_time_sec': round(hold_time, 1),
                'max_hold_seconds': getattr(pos, 'max_hold_seconds', None),
                'executed_to_amount_units': getattr(pos, 'executed_to_amount_units', None),
                'resumable_after_restart': getattr(pos, 'resumable_after_restart', None),
            }
        print(json.dumps(sample), flush=True)

        if not pos:
            for h in reversed(trade_manager.trade_history):
                if getattr(h, 'id', None) == TARGET_ID or getattr(h, 'tx_hash', None) == '1cac33823b66f08a66d92d34af5f305269d717cee400ce6baa4967c53ec8b9c9':
                    print(json.dumps({
                        'event': 'closed',
                        'id': h.id,
                        'exit_tx_hash': getattr(h, 'exit_tx_hash', None),
                        'exit_price': h.exit_price,
                        'pnl_usd': h.pnl_usd,
                        'pnl_pct': h.pnl_pct,
                        'exit_time': h.exit_time,
                    }, default=str), flush=True)
                    return
        await asyncio.sleep(10)


if __name__ == '__main__':
    asyncio.run(main())
