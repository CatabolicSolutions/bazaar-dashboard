import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import hashlib
import json
from decimal import Decimal

from web3 import Web3

from bot.main import ETHScalper
from execution.trade_manager import trade_manager
from execution.live_executor import live_executor
from wallet_monitor import wallet_monitor
from config.settings import USDC_ADDRESS, WETH_ADDRESS, BASE_RPC_URL


w3 = Web3(Web3.HTTPProvider(BASE_RPC_URL))


def _tx_hash_hex(tx_hash):
    if tx_hash is None:
        return None
    if isinstance(tx_hash, str):
        return tx_hash if tx_hash.startswith('0x') else f'0x{tx_hash}'
    return Web3.to_hex(tx_hash)


def _sha256_hex(value: str):
    return hashlib.sha256(value.encode()).hexdigest()


def _input_prefix(value: str, prefix_len: int = 74):
    if not value:
        return None
    if not value.startswith('0x'):
        value = '0x' + value
    return value[:prefix_len]


def _normalize_balance_snapshot(raw: dict):
    return {
        'USDC': raw.get('usdc'),
        'WETH': raw.get('weth'),
        'ETH': raw.get('eth'),
    }


def _capture_payload(label: str, swap: dict):
    tx = (swap or {}).get('tx') or {}
    data = tx.get('data') or ''
    payload = {
        'label': label,
        'src': swap.get('src_token') if swap else None,
        'dst': swap.get('dst_token') if swap else None,
        'amount': str(swap.get('from_amount')) if swap else None,
        'router_target': tx.get('to'),
        'calldata_prefix': _input_prefix(data),
        'calldata_sha256': _sha256_hex(data) if data else None,
        'tx_value': tx.get('value'),
        'gas': tx.get('gas'),
    }
    return payload


def _fetch_full_tx(tx_hash_hex: str):
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash_hex, timeout=180)
    tx = None
    for _ in range(12):
        try:
            tx = w3.eth.get_transaction(tx_hash_hex)
            break
        except Exception:
            import time
            time.sleep(1)
    if tx is None:
        raise RuntimeError(f'transaction unavailable after receipt: {tx_hash_hex}')
    return {
        'tx_hash': tx_hash_hex,
        'status': receipt.status,
        'block': receipt.blockNumber,
        'gas_used': receipt.gasUsed,
        'to': tx['to'],
        'input_prefix': _input_prefix(tx['input'].hex() if isinstance(tx['input'], bytes) else tx['input']),
    }


async def main():
    if not w3.is_connected():
        raise RuntimeError('Base RPC unavailable')

    bot = ETHScalper()
    live_executor.enable()

    artifacts = {
        'buy_request': None,
        'sell_request': None,
        'approval_request': None,
        'tx_hashes': {
            'buy': None,
            'approval': None,
            'sell': None,
        },
        'receipts': {
            'buy': None,
            'approval': None,
            'sell': None,
        },
        'balances': {
            'pre': _normalize_balance_snapshot(wallet_monitor.get_all_balances()),
            'after_buy': None,
            'after_sell': None,
        },
    }

    signal = {'direction': 'up', 'price': 2200.0, 'timestamp': 0, 'type': 'manual_forced_roundtrip'}
    position = trade_manager.create_position(signal, 1.0, paper=False)

    buy_swap = live_executor.get_swap_data(USDC_ADDRESS, WETH_ADDRESS, 1_000_000)
    if not buy_swap:
        raise RuntimeError('buy swap payload unavailable')
    buy_swap['src_token'] = USDC_ADDRESS
    artifacts['buy_request'] = _capture_payload('buy', buy_swap)

    buy_tx_hash = _tx_hash_hex(live_executor.execute_swap(buy_swap))
    if not buy_tx_hash:
        raise RuntimeError('buy tx submission failed')
    artifacts['tx_hashes']['buy'] = buy_tx_hash
    artifacts['receipts']['buy'] = _fetch_full_tx(buy_tx_hash)

    position.tx_hash = buy_tx_hash
    position.status = position.status.OPEN
    position.executed_to_amount_units = int(buy_swap['to_amount']) / 1e18
    artifacts['balances']['after_buy'] = _normalize_balance_snapshot(wallet_monitor.get_all_balances())

    original_get_swap_data = live_executor.get_swap_data
    approval_tx_hash_holder = {'value': None}

    def instrumented_get_swap_data(from_token, to_token, amount, slippage=None, enforce_semantic_unwind=False):
        before_nonce = w3.eth.get_transaction_count(wallet_monitor.wallet_address, 'latest')
        swap = original_get_swap_data(from_token, to_token, amount, slippage, enforce_semantic_unwind)
        after_nonce = w3.eth.get_transaction_count(wallet_monitor.wallet_address, 'latest')
        if from_token.lower() == WETH_ADDRESS.lower() and to_token.lower() == USDC_ADDRESS.lower() and swap:
            swap['src_token'] = from_token
            artifacts['sell_request'] = _capture_payload('sell', swap)
            artifacts['sell_request']['semantic_provider'] = swap.get('semantic_provider')
        pending = w3.eth.get_transaction_count(wallet_monitor.wallet_address, 'pending')
        if after_nonce > before_nonce or pending > after_nonce:
            latest_block = w3.eth.block_number
            for block_no in range(max(0, latest_block - 20), latest_block + 1):
                block = w3.eth.get_block(block_no, full_transactions=True)
                for tx in block.transactions:
                    if tx['from'].lower() == wallet_monitor.wallet_address.lower() and tx['to'] and tx['to'].lower() == WETH_ADDRESS.lower():
                        receipt = w3.eth.get_transaction_receipt(tx['hash'])
                        if receipt.status == 1:
                            approval_tx_hash_holder['value'] = tx['hash'].hex()
        return swap

    live_executor.get_swap_data = instrumented_get_swap_data
    try:
        close_result = await bot._close_live_position(position, position.entry_price * 1.01, 'forced_roundtrip_test')
    finally:
        live_executor.get_swap_data = original_get_swap_data

    if not close_result or not close_result.get('closed'):
        raise RuntimeError(f"sell leg failed: {close_result}")

    sell_tx_hash = _tx_hash_hex(close_result.get('tx_hash'))
    artifacts['tx_hashes']['sell'] = sell_tx_hash
    artifacts['receipts']['sell'] = _fetch_full_tx(sell_tx_hash)
    artifacts['balances']['after_sell'] = _normalize_balance_snapshot(wallet_monitor.get_all_balances())

    approval_tx_hash = approval_tx_hash_holder['value']
    if approval_tx_hash:
        artifacts['tx_hashes']['approval'] = approval_tx_hash
        artifacts['receipts']['approval'] = _fetch_full_tx(approval_tx_hash)

    print(json.dumps(artifacts, indent=2, sort_keys=True))


asyncio.run(main())
