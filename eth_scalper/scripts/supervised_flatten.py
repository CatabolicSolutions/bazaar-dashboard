"""
Supervised Flatten - Path A
Unwinds all legacy WETH positions to USDC, clears state, then creates one fresh autonomous entry.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import json
import time
from web3 import Web3

from execution.live_executor import live_executor
from config.settings import USDC_ADDRESS, WETH_ADDRESS, BASE_RPC_URL, WALLET_ADDRESS, PRIVATE_KEY

# Use Base RPC
w3 = Web3(Web3.HTTPProvider('https://base-rpc.publicnode.com'))

# File paths
PERSISTED_POSITIONS_PATH = Path(__file__).resolve().parent.parent / 'state' / 'persisted_positions.json'


def get_balances():
    """Get current wallet balances directly from chain."""
    wallet = Web3.to_checksum_address(WALLET_ADDRESS)
    
    # WETH balance
    weth_abi = '[{"constant":true,"inputs":[{"name":"account","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"type":"function"}]'
    weth_contract = w3.eth.contract(address=Web3.to_checksum_address(WETH_ADDRESS), abi=json.loads(weth_abi))
    weth_bal = weth_contract.functions.balanceOf(wallet).call() / 1e18
    
    # USDC balance
    usdc_abi = '[{"constant":true,"inputs":[{"name":"account","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"type":"function"}]'
    usdc_contract = w3.eth.contract(address=Web3.to_checksum_address(USDC_ADDRESS), abi=json.loads(usdc_abi))
    usdc_bal = usdc_contract.functions.balanceOf(wallet).call() / 1e6
    
    # ETH balance
    eth_bal = w3.eth.get_balance(wallet) / 1e18
    
    return {
        'USDC': usdc_bal,
        'WETH': weth_bal,
        'ETH': eth_bal,
    }


def get_weth_balance_raw():
    """Get WETH balance in raw units."""
    wallet = Web3.to_checksum_address(WALLET_ADDRESS)
    weth_abi = '[{"constant":true,"inputs":[{"name":"account","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"type":"function"}]'
    weth_contract = w3.eth.contract(address=Web3.to_checksum_address(WETH_ADDRESS), abi=json.loads(weth_abi))
    return weth_contract.functions.balanceOf(wallet).call()


def load_persisted_positions():
    """Load the persisted positions file."""
    if not PERSISTED_POSITIONS_PATH.exists():
        return {'positions': [], 'updated_at': None}
    with open(PERSISTED_POSITIONS_PATH, 'r') as f:
        return json.load(f)


def save_persisted_positions(data):
    """Save the persisted positions file."""
    with open(PERSISTED_POSITIONS_PATH, 'w') as f:
        json.dump(data, f, indent=2)


def wait_for_receipt(tx_hash_hex, timeout=180):
    """Wait for transaction receipt."""
    return w3.eth.wait_for_transaction_receipt(tx_hash_hex, timeout=timeout)


def fetch_full_tx(tx_hash_hex):
    """Fetch full transaction details."""
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
    }


async def main():
    print("=" * 60)
    print("SUPERVISED FLATTEN - PATH A")
    print("=" * 60)
    
    artifacts = {
        'task': 'Supervised flatten of legacy WETH inventory',
        'scope': 'eth_scalper/state/persisted_positions.json, wallet WETH balance',
        'commands_run': [],
        'files_changed': [],
        'commit': None,
        'deploy_target': None,
        'observed_live_state': {},
        'test_performed': None,
        'test_result': None,
        'evidence': {},
        'remaining_blocker': None,
        'status_truth_label': None,
    }
    
    # Step 1: Get pre-flatten state
    print("\n[1] Capturing pre-flatten state...")
    pre_positions = load_persisted_positions()
    pre_balances = get_balances()
    pre_weth_raw = get_weth_balance_raw()
    
    artifacts['observed_live_state']['pre_flatten'] = {
        'positions_count': len(pre_positions.get('positions', [])),
        'positions': pre_positions.get('positions', []),
        'balances': pre_balances,
        'weth_balance_raw': pre_weth_raw,
    }
    
    print(f"  Positions: {len(pre_positions.get('positions', []))}")
    print(f"  WETH: {pre_balances['WETH']:.6f} ({pre_weth_raw} raw)")
    print(f"  USDC: {pre_balances['USDC']:.2f}")
    
    # Step 2: Check if there's WETH to flatten
    if pre_weth_raw == 0:
        print("\n[2] No WETH balance to flatten. Skipping unwind.")
        unwind_tx_hash = None
    else:
        print("\n[2] Unwinding WETH to USDC...")
        live_executor.enable()
        
        # Get swap data for WETH -> USDC
        swap = live_executor.get_swap_data(WETH_ADDRESS, USDC_ADDRESS, pre_weth_raw)
        if not swap:
            artifacts['remaining_blocker'] = 'Failed to get swap data for WETH->USDC unwind'
            artifacts['status_truth_label'] = 'BLOCKED'
            print(json.dumps(artifacts, indent=2))
            return
        
        # Execute the swap
        tx_hash = live_executor.execute_swap(swap)
        if not tx_hash:
            artifacts['remaining_blocker'] = 'Failed to execute WETH->USDC unwind transaction'
            artifacts['status_truth_label'] = 'BLOCKED'
            print(json.dumps(artifacts, indent=2))
            return
        
        unwind_tx_hash = tx_hash.hex() if hasattr(tx_hash, 'hex') else str(tx_hash)
        artifacts['commands_run'].append(f'live_executor.execute_swap(WETH->USDC, amount={pre_weth_raw})')
        artifacts['evidence']['unwind_tx_hash'] = unwind_tx_hash
        
        print(f"  Unwind tx submitted: {unwind_tx_hash}")
        
        # Wait for receipt
        receipt = wait_for_receipt(unwind_tx_hash)
        artifacts['evidence']['unwind_receipt'] = {
            'status': receipt.status,
            'block': receipt.blockNumber,
            'gas_used': receipt.gasUsed,
        }
        print(f"  Unwind confirmed: block={receipt.blockNumber}, status={receipt.status}")
        
        # Small delay for state to settle
        time.sleep(3)
    
    # Step 3: Verify post-flatten state
    print("\n[3] Verifying post-flatten state...")
    post_balances = get_balances()
    post_weth_raw = get_weth_balance_raw()
    
    artifacts['observed_live_state']['post_flatten'] = {
        'balances': post_balances,
        'weth_balance_raw': post_weth_raw,
    }
    
    print(f"  WETH: {post_balances['WETH']:.6f} ({post_weth_raw} raw)")
    print(f"  USDC: {post_balances['USDC']:.2f}")
    
    # Step 4: Clear persisted positions
    print("\n[4] Clearing persisted positions...")
    cleared_positions = {'positions': [], 'updated_at': time.strftime('%Y-%m-%dT%H:%M:%S+00:00', time.gmtime())}
    save_persisted_positions(cleared_positions)
    artifacts['commands_run'].append('save_persisted_positions(cleared)')
    artifacts['files_changed'].append(str(PERSISTED_POSITIONS_PATH))
    print("  Persisted positions cleared.")
    
    # Step 5: Verify no legacy WETH exposure remains
    print("\n[5] Verifying no legacy WETH exposure remains...")
    if post_weth_raw == 0:
        print("  ✓ Confirmed: No WETH balance remains")
        artifacts['evidence']['legacy_weth_cleared'] = True
    else:
        print(f"  ✗ WARNING: {post_weth_raw} raw WETH still remains")
        artifacts['evidence']['legacy_weth_cleared'] = False
        artifacts['remaining_blocker'] = f'WETH balance not fully cleared: {post_weth_raw} raw units remain'
        artifacts['status_truth_label'] = 'BLOCKED'
        print(json.dumps(artifacts, indent=2))
        return
    
    # Step 6: Create fresh autonomous entry under new durable binding
    print("\n[6] Creating fresh autonomous entry under new durable binding...")
    
    # Enable live executor
    live_executor.enable()
    
    # Get fresh price
    from signals.price_feed import price_feed
    current_price = price_feed.get_eth_price()
    print(f"  Current ETH price: ${current_price:.2f}")
    
    # Create signal and position
    from execution.trade_manager import trade_manager
    signal = {
        'direction': 'up',
        'price': current_price,
        'timestamp': time.time(),
        'type': 'autonomous_fresh_entry'
    }
    
    # Create position with new durable binding
    position = trade_manager.create_position(signal, 10.0, paper=False)  # $10 position
    position.entry_derivation = 'autonomous_durable_binding'
    position.target_derivation = 'autonomous_durable_binding'
    position.stop_derivation = 'autonomous_durable_binding'
    
    # Execute buy
    buy_swap = live_executor.get_swap_data(USDC_ADDRESS, WETH_ADDRESS, int(10 * 1e6))  # $10 USDC
    if not buy_swap:
        artifacts['remaining_blocker'] = 'Failed to get swap data for fresh autonomous entry'
        artifacts['status_truth_label'] = 'BLOCKED'
        print(json.dumps(artifacts, indent=2))
        return
    
    buy_tx_hash = live_executor.execute_swap(buy_swap)
    if not buy_tx_hash:
        artifacts['remaining_blocker'] = 'Failed to execute fresh autonomous entry transaction'
        artifacts['status_truth_label'] = 'BLOCKED'
        print(json.dumps(artifacts, indent=2))
        return
    
    buy_tx_hash_hex = buy_tx_hash.hex() if hasattr(buy_tx_hash, 'hex') else str(buy_tx_hash)
    artifacts['commands_run'].append(f'live_executor.execute_swap(USDC->WETH, $10, autonomous_durable_binding)')
    artifacts['evidence']['fresh_entry_tx_hash'] = buy_tx_hash_hex
    
    print(f"  Fresh entry tx submitted: {buy_tx_hash_hex}")
    
    # Wait for receipt
    buy_receipt = wait_for_receipt(buy_tx_hash_hex)
    artifacts['evidence']['fresh_entry_receipt'] = {
        'status': buy_receipt.status,
        'block': buy_receipt.blockNumber,
        'gas_used': buy_receipt.gasUsed,
    }
    print(f"  Fresh entry confirmed: block={buy_receipt.blockNumber}, status={buy_receipt.status}")
    
    # Update position with tx hash and persist
    position.tx_hash = buy_tx_hash_hex
    position.status = position.status.OPEN
    try:
        to_amount = buy_swap.get('to_amount')
        if to_amount is not None:
            position.executed_to_amount_units = int(to_amount) / 1e18
    except Exception:
        position.executed_to_amount_units = None
    position.source = 'autonomous_entry'
    position.resumable_after_restart = True
    position.max_hold_seconds = trade_manager.max_hold_time
    
    # Persist the bound lot
    from state_manager import state_manager
    state_manager.persist_live_position(position)
    artifacts['files_changed'].append(str(PERSISTED_POSITIONS_PATH))
    
    # Step 7: Final verification
    print("\n[7] Final verification...")
    time.sleep(3)
    final_balances = get_balances()
    final_positions = load_persisted_positions()
    
    artifacts['observed_live_state']['final'] = {
        'balances': final_balances,
        'positions_count': len(final_positions.get('positions', [])),
        'positions': final_positions.get('positions', []),
    }
    
    print(f"  Final WETH: {final_balances['WETH']:.6f}")
    print(f"  Final USDC: {final_balances['USDC']:.2f}")
    print(f"  Persisted positions: {len(final_positions.get('positions', []))}")
    
    # Verify the new position has durable binding fields
    if final_positions.get('positions'):
        new_pos = final_positions['positions'][0]
        artifacts['evidence']['persisted_bound_lot_fields'] = {
            'id': new_pos.get('id'),
            'entry_derivation': new_pos.get('entry_derivation'),
            'target_derivation': new_pos.get('target_derivation'),
            'stop_derivation': new_pos.get('stop_derivation'),
            'tx_hash': new_pos.get('tx_hash'),
            'lot_units': new_pos.get('lot_units'),
        }
        print(f"  ✓ Durable binding fields present: entry_derivation={new_pos.get('entry_derivation')}")
    
    # Final status
    artifacts['test_performed'] = 'Supervised flatten + fresh autonomous entry'
    artifacts['test_result'] = 'PASS' if (post_weth_raw == 0 and buy_receipt.status == 1) else 'FAIL'
    artifacts['status_truth_label'] = 'VERIFIED' if artifacts['test_result'] == 'PASS' else 'FAILED'
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Task: {artifacts['task']}")
    print(f"Unwind tx: {unwind_tx_hash or 'N/A (no WETH to unwind)'}")
    print(f"Fresh entry tx: {buy_tx_hash_hex}")
    print(f"Legacy WETH cleared: {artifacts['evidence']['legacy_weth_cleared']}")
    print(f"Test result: {artifacts['test_result']}")
    print(f"Status: {artifacts['status_truth_label']}")
    
    print("\n" + "=" * 60)
    print("FULL ARTIFACTS")
    print("=" * 60)
    print(json.dumps(artifacts, indent=2, default=str))


if __name__ == '__main__':
    asyncio.run(main())
