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
from wallet_monitor import wallet_monitor
from web3 import Web3
from config.settings import BASE_RPC_URL

w3 = Web3(Web3.HTTPProvider(BASE_RPC_URL))


def ts():
    return datetime.now(UTC).isoformat()


def load_persisted():
    return state_manager.load_persisted_positions()


def tx_receipt(tx_hash):
    if not tx_hash:
        return None
    if not str(tx_hash).startswith('0x'):
        tx_hash = '0x' + str(tx_hash)
    rc = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    return {
        'tx_hash': tx_hash,
        'status': rc.status,
        'block': rc.blockNumber,
        'gas_used': rc.gasUsed,
    }


async def main():
    out = {
        'persisted_initial': load_persisted(),
        'monitor_samples': [],
        'resume_result': None,
        'exit_trigger': None,
        'sell_tx_receipt': None,
        'persisted_final': None,
        'realized_pnl': None,
        'blocker': None,
    }

    bot = ETHScalper()
    live_executor.enable()
    resumed = await bot._resume_persisted_live_positions()
    out['resume_result'] = {'timestamp': ts(), 'resumed': resumed, 'open_positions': len(trade_manager.get_open_positions())}

    start = time.time()
    target_pos_id = None
    target_buy_tx = None

    while time.time() - start < 420:
        open_positions = trade_manager.get_open_positions()
        persisted = load_persisted()
        current_price = price_feed.get_eth_price()

        if open_positions and not target_pos_id:
            p = open_positions[0]
            target_pos_id = p.id
            target_buy_tx = getattr(p, 'tx_hash', None)

        sample = {
            'timestamp': ts(),
            'open_positions': len(open_positions),
            'current_price': current_price,
            'persisted_positions': persisted,
        }

        if open_positions:
            p = open_positions[0]
            hold_time = time.time() - p.entry_time
            sample['position'] = {
                'id': p.id,
                'tx_hash': getattr(p, 'tx_hash', None),
                'entry_price': p.entry_price,
                'target_price': p.target_price,
                'stop_price': p.stop_price,
                'hold_time_sec': round(hold_time, 1),
                'max_hold_seconds': getattr(p, 'max_hold_seconds', None),
                'executed_to_amount_units': getattr(p, 'executed_to_amount_units', None),
                'resumable_after_restart': getattr(p, 'resumable_after_restart', None),
            }
            if current_price is not None:
                if current_price >= p.target_price:
                    sample['exit_condition_now'] = 'target'
                elif current_price <= p.stop_price:
                    sample['exit_condition_now'] = 'stop'
                elif hold_time > getattr(p, 'max_hold_seconds', 300):
                    sample['exit_condition_now'] = 'max_hold'
                else:
                    sample['exit_condition_now'] = None
        out['monitor_samples'].append(sample)
        print(json.dumps(sample), flush=True)

        if target_buy_tx and not open_positions:
            hist = None
            for h in reversed(trade_manager.trade_history):
                if getattr(h, 'tx_hash', None) == target_buy_tx:
                    hist = h
                    break
            if hist:
                if hist.exit_price is not None:
                    if hist.exit_price >= hist.target_price:
                        out['exit_trigger'] = 'target'
                    elif hist.exit_price <= hist.stop_price:
                        out['exit_trigger'] = 'stop'
                    else:
                        out['exit_trigger'] = 'max_hold'
                out['realized_pnl'] = {
                    'pnl_usd': hist.pnl_usd,
                    'pnl_pct': hist.pnl_pct,
                    'exit_price': hist.exit_price,
                    'exit_time': hist.exit_time,
                    'exit_tx_hash': getattr(hist, 'exit_tx_hash', None),
                }
                out['sell_tx_receipt'] = tx_receipt(getattr(hist, 'exit_tx_hash', None))
                out['persisted_final'] = load_persisted()
                print(json.dumps({'event': 'closed', 'exit_trigger': out['exit_trigger'], 'realized_pnl': out['realized_pnl'], 'receipt': out['sell_tx_receipt']}, default=str), flush=True)
                print(json.dumps({'event': 'final_wallet', 'wallet': wallet_monitor.get_all_balances()}, default=str), flush=True)
                print(json.dumps(out, default=str), flush=True)
                return
            out['blocker'] = 'Position disappeared from open set without matching trade_history closure entry'
            break

        await asyncio.sleep(10)

    if not out['blocker']:
        persisted = load_persisted()
        out['persisted_final'] = persisted
        if persisted:
            out['blocker'] = 'Autonomous closure did not occur within observation window'
        else:
            out['blocker'] = 'No persisted position remained to observe'
    print(json.dumps({'event': 'blocked', 'blocker': out['blocker'], 'persisted_final': out['persisted_final']}, default=str), flush=True)
    print(json.dumps(out, default=str), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
