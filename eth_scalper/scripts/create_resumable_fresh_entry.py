import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import json
import time
from web3 import Web3

from execution.live_executor import live_executor
from execution.trade_manager import trade_manager
from signals.price_feed import price_feed
from state_manager import state_manager
from config.settings import USDC_ADDRESS, BASE_RPC_URL

w3 = Web3(Web3.HTTPProvider(BASE_RPC_URL))


def wait_for_receipt(tx_hash_hex, timeout=180):
    return w3.eth.wait_for_transaction_receipt(tx_hash_hex, timeout=timeout)


async def main():
    live_executor.enable()
    current_price = price_feed.get_eth_price()
    signal = {
        'direction': 'up',
        'price': current_price,
        'timestamp': time.time(),
        'type': 'autonomous_fresh_entry_resumable'
    }
    position = trade_manager.create_position(signal, 10.0, paper=False)
    position.source = 'autonomous_entry'
    position.entry_derivation = 'tracked_live_execution'
    position.target_derivation = 'tracked_live_execution'
    position.stop_derivation = 'tracked_live_execution'
    position.resumable_after_restart = True
    position.max_hold_seconds = trade_manager.max_hold_time

    buy_swap = live_executor.get_swap_data(USDC_ADDRESS, '0x4200000000000000000000000000000000000006', int(10 * 1e6))
    if not buy_swap:
        raise RuntimeError('no swap data for fresh entry')

    tx_hash = live_executor.execute_swap(buy_swap)
    if not tx_hash:
        raise RuntimeError('fresh entry tx failed')

    tx_hash_hex = tx_hash.hex() if hasattr(tx_hash, 'hex') else str(tx_hash)
    receipt = wait_for_receipt(tx_hash_hex)

    position.tx_hash = tx_hash_hex
    position.status = position.status.OPEN
    to_amount = buy_swap.get('to_amount')
    if to_amount is not None:
        position.executed_to_amount_units = int(to_amount) / 1e18

    state_manager.persist_live_position(position)

    print(json.dumps({
        'position_id': position.id,
        'entry_price': position.entry_price,
        'target_price': position.target_price,
        'stop_price': position.stop_price,
        'max_hold_seconds': position.max_hold_seconds,
        'resumable_after_restart': position.resumable_after_restart,
        'executed_to_amount_units': getattr(position, 'executed_to_amount_units', None),
        'tx_hash': tx_hash_hex,
        'receipt': {
            'status': receipt.status,
            'block': receipt.blockNumber,
            'gas_used': receipt.gasUsed,
        }
    }, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
