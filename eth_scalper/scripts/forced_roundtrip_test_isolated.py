"""
Isolated forced round-trip test with strict balance tracking.
This test ensures no interleaving and captures exact balance deltas.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import hashlib
import json
import time

from web3 import Web3

from bot.main import ETHScalper
from execution.trade_manager import trade_manager
from execution.live_executor import live_executor
from config.settings import USDC_ADDRESS, WETH_ADDRESS, BASE_RPC_URL, WALLET_ADDRESS


w3 = Web3(Web3.HTTPProvider('https://base-rpc.publicnode.com'))


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


def get_balances():
    """Get current wallet balances directly from chain."""
    wallet = Web3.to_checksum_address(WALLET_ADDRESS)
    
    # WETH balance
    weth_data = '0x70a08231' + wallet[2:].lower().rjust(64, '0')
    weth_raw = w3.eth.call({'to': Web3.to_checksum_address(WETH_ADDRESS), 'data': weth_data})
    weth_bal = int(weth_raw.hex(), 16) / 1e18
    
    # USDC balance
    usdc_data = '0x70a08231' + wallet[2:].lower().rjust(64, '0')
    usdc_raw = w3.eth.call({'to': Web3.to_checksum_address(USDC_ADDRESS), 'data': usdc_data})
    usdc_bal = int(usdc_raw.hex(), 16) / 1e6
    
    # ETH balance
    eth_bal = w3.eth.get_balance(wallet) / 1e18
    
    return {
        'USDC': usdc_bal,
        'WETH': weth_bal,
        'ETH': eth_bal,
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
        'semantic_provider': swap.get('semantic_provider') if swap else None,
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


def analyze_swap_logs(tx_hash: str, label: str):
    """Analyze ERC20 transfer logs for a swap transaction."""
    rc = w3.eth.get_transaction_receipt(tx_hash)
    
    transfers = []
    for log in rc.logs:
        topics = [t.hex() for t in log['topics']]
        # Transfer event signature
        if topics[0] == '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef':
            addr = log['address'].lower()
            from_addr = '0x' + topics[1][26:]
            to_addr = '0x' + topics[2][26:]
            data_hex = log['data'].hex() if isinstance(log['data'], bytes) else log['data']
            amount = int(data_hex, 16)
            
            token = 'WETH' if addr == WETH_ADDRESS.lower() else ('USDC' if addr == USDC_ADDRESS.lower() else addr)
            
            transfers.append({
                'token': token,
                'from': from_addr,
                'to': to_addr,
                'amount': amount,
                'is_wallet_sender': from_addr.lower() == WALLET_ADDRESS.lower(),
                'is_wallet_receiver': to_addr.lower() == WALLET_ADDRESS.lower(),
            })
    
    return transfers


async def main():
    if not w3.is_connected():
        raise RuntimeError('Base RPC unavailable')

    bot = ETHScalper()
    live_executor.enable()

    # Get pre-test balances
    print("Getting pre-test balances...")
    pre_balances = get_balances()
    print(f"Pre-test: USDC={pre_balances['USDC']}, WETH={pre_balances['WETH']}, ETH={pre_balances['ETH']}")

    artifacts = {
        'buy_request': None,
        'sell_request': None,
        'tx_hashes': {'buy': None, 'sell': None},
        'receipts': {'buy': None, 'sell': None},
        'balances': {
            'pre': pre_balances,
            'after_buy': None,
            'after_sell': None,
        },
        'log_analysis': {'buy': None, 'sell': None},
        'deltas': {'buy': None, 'sell': None},
    }

    # === BUY LEG: USDC -> WETH ===
    print("\n=== EXECUTING BUY LEG (USDC -> WETH) ===")
    signal = {'direction': 'up', 'price': 2200.0, 'timestamp': 0, 'type': 'manual_forced_roundtrip'}
    position = trade_manager.create_position(signal, 1.0, paper=False)

    buy_swap = live_executor.get_swap_data(USDC_ADDRESS, WETH_ADDRESS, 1_000_000)
    if not buy_swap:
        raise RuntimeError('buy swap payload unavailable')
    buy_swap['src_token'] = USDC_ADDRESS
    artifacts['buy_request'] = _capture_payload('buy', buy_swap)
    print(f"Buy request: {json.dumps(artifacts['buy_request'], indent=2)}")

    buy_tx_hash = _tx_hash_hex(live_executor.execute_swap(buy_swap))
    if not buy_tx_hash:
        raise RuntimeError('buy tx submission failed')
    artifacts['tx_hashes']['buy'] = buy_tx_hash
    artifacts['receipts']['buy'] = _fetch_full_tx(buy_tx_hash)
    print(f"Buy tx confirmed: {buy_tx_hash}")

    # Small delay for state to settle
    time.sleep(2)
    
    artifacts['balances']['after_buy'] = get_balances()
    artifacts['log_analysis']['buy'] = analyze_swap_logs(buy_tx_hash, 'buy')
    
    buy_delta = {
        'USDC': artifacts['balances']['after_buy']['USDC'] - artifacts['balances']['pre']['USDC'],
        'WETH': artifacts['balances']['after_buy']['WETH'] - artifacts['balances']['pre']['WETH'],
        'ETH': artifacts['balances']['after_buy']['ETH'] - artifacts['balances']['pre']['ETH'],
    }
    artifacts['deltas']['buy'] = buy_delta
    
    print(f"Post-buy balances: USDC={artifacts['balances']['after_buy']['USDC']}, WETH={artifacts['balances']['after_buy']['WETH']}")
    print(f"Buy delta: USDC={buy_delta['USDC']}, WETH={buy_delta['WETH']}")
    print(f"Buy logs: {json.dumps(artifacts['log_analysis']['buy'], indent=2)}")

    # Verify buy direction
    if buy_delta['USDC'] >= 0:
        print("WARNING: USDC did not decrease after buy!")
    if buy_delta['WETH'] <= 0:
        print("WARNING: WETH did not increase after buy!")

    # Setup position for sell
    position.tx_hash = buy_tx_hash
    position.status = position.status.OPEN
    position.executed_to_amount_units = int(buy_swap['to_amount']) / 1e18

    # === SELL LEG: WETH -> USDC ===
    print("\n=== EXECUTING SELL LEG (WETH -> USDC) ===")
    
    # Patch get_swap_data to capture the sell request
    original_get_swap_data = live_executor.get_swap_data
    
    def instrumented_get_swap_data(from_token, to_token, amount, slippage=None, enforce_semantic_unwind=False):
        swap = original_get_swap_data(from_token, to_token, amount, slippage, enforce_semantic_unwind)
        if from_token.lower() == WETH_ADDRESS.lower() and to_token.lower() == USDC_ADDRESS.lower() and swap:
            swap['src_token'] = from_token
            artifacts['sell_request'] = _capture_payload('sell', swap)
            print(f"Sell request: {json.dumps(artifacts['sell_request'], indent=2)}")
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
    print(f"Sell tx confirmed: {sell_tx_hash}")

    # Small delay for state to settle
    time.sleep(2)
    
    artifacts['balances']['after_sell'] = get_balances()
    artifacts['log_analysis']['sell'] = analyze_swap_logs(sell_tx_hash, 'sell')
    
    sell_delta = {
        'USDC': artifacts['balances']['after_sell']['USDC'] - artifacts['balances']['after_buy']['USDC'],
        'WETH': artifacts['balances']['after_sell']['WETH'] - artifacts['balances']['after_buy']['WETH'],
        'ETH': artifacts['balances']['after_sell']['ETH'] - artifacts['balances']['after_buy']['ETH'],
    }
    artifacts['deltas']['sell'] = sell_delta
    
    print(f"Post-sell balances: USDC={artifacts['balances']['after_sell']['USDC']}, WETH={artifacts['balances']['after_sell']['WETH']}")
    print(f"Sell delta: USDC={sell_delta['USDC']}, WETH={sell_delta['WETH']}")
    print(f"Sell logs: {json.dumps(artifacts['log_analysis']['sell'], indent=2)}")

    # Verify sell direction
    if sell_delta['USDC'] <= 0:
        print("WARNING: USDC did not increase after sell!")
    if sell_delta['WETH'] >= 0:
        print("WARNING: WETH did not decrease after sell!")

    # Calculate round-trip P&L
    total_delta = {
        'USDC': artifacts['balances']['after_sell']['USDC'] - artifacts['balances']['pre']['USDC'],
        'WETH': artifacts['balances']['after_sell']['WETH'] - artifacts['balances']['pre']['WETH'],
        'ETH': artifacts['balances']['after_sell']['ETH'] - artifacts['balances']['pre']['ETH'],
    }
    artifacts['deltas']['total'] = total_delta
    
    print(f"\n=== ROUND-TRIP SUMMARY ===")
    print(f"Total delta: USDC={total_delta['USDC']}, WETH={total_delta['WETH']}, ETH={total_delta['ETH']}")
    
    # Final validation
    artifacts['validation'] = {
        'buy_usdc_decreased': buy_delta['USDC'] < 0,
        'buy_weth_increased': buy_delta['WETH'] > 0,
        'sell_usdc_increased': sell_delta['USDC'] > 0,
        'sell_weth_decreased': sell_delta['WETH'] < 0,
        'semantic_unwind_success': sell_delta['USDC'] > 0 and sell_delta['WETH'] < 0,
    }
    
    print(f"Validation: {json.dumps(artifacts['validation'], indent=2)}")
    
    print("\n=== FULL ARTIFACTS ===")
    print(json.dumps(artifacts, indent=2, sort_keys=True))


asyncio.run(main())
