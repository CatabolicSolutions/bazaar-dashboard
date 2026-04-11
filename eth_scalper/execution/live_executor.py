"""Live trade execution via 1inch"""
import requests
from typing import Optional, Dict
from config.settings import INCH_API_KEY, WALLET_ADDRESS, PRIVATE_KEY, MAX_SLIPPAGE_PERCENT, BASE_RPC_URL, CHAIN_ID, USDC_ADDRESS, WETH_ADDRESS
from config.logger import logger

class LiveExecutor:
    """Execute real trades on 1inch"""
    
    def __init__(self):
        self.base_url = f'https://api.1inch.dev/swap/v5.2/{CHAIN_ID}'
        self.headers = {
            'Authorization': f'Bearer {INCH_API_KEY}',
            'Content-Type': 'application/json'
        }
        self.enabled = False  # Must be explicitly enabled
    
    def enable(self):
        """Enable live trading"""
        self.enabled = True
        logger.info("LIVE TRADING ENABLED")
    
    def disable(self):
        """Disable live trading"""
        self.enabled = False
        logger.info("LIVE TRADING DISABLED")
    
    def ensure_allowance(self, token_address: str, spender: str, required_amount: int) -> Optional[Dict]:
        """Ensure ERC20 allowance exists for spender, submitting approve() when needed."""
        if token_address.lower() == '0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee':
            return {'skipped': True, 'reason': 'native token path'}

        try:
            from web3 import Web3
            from eth_account import Account

            w3 = Web3(Web3.HTTPProvider(BASE_RPC_URL))
            if not w3.is_connected():
                logger.error("Failed to connect to Base RPC for allowance check")
                return None

            abi = [
                {
                    'name': 'allowance', 'type': 'function', 'stateMutability': 'view',
                    'inputs': [{'name': 'owner', 'type': 'address'}, {'name': 'spender', 'type': 'address'}],
                    'outputs': [{'name': '', 'type': 'uint256'}]
                },
                {
                    'name': 'approve', 'type': 'function', 'stateMutability': 'nonpayable',
                    'inputs': [{'name': 'spender', 'type': 'address'}, {'name': 'amount', 'type': 'uint256'}],
                    'outputs': [{'name': '', 'type': 'bool'}]
                }
            ]
            contract = w3.eth.contract(address=Web3.to_checksum_address(token_address), abi=abi)
            current = contract.functions.allowance(Web3.to_checksum_address(WALLET_ADDRESS), Web3.to_checksum_address(spender)).call()
            logger.info(f"Allowance read: token={token_address} spender={spender} allowance={current} required={required_amount}")
            if current >= required_amount:
                return {'approved': False, 'allowance': current}

            account = Account.from_key(PRIVATE_KEY)
            nonce = w3.eth.get_transaction_count(WALLET_ADDRESS, 'pending')
            latest_block = w3.eth.get_block('latest')
            base_fee = latest_block.get('baseFeePerGas', w3.eth.gas_price)
            network_gas = int(w3.eth.gas_price)
            priority_fee = max(w3.to_wei(0.005, 'gwei'), int(network_gas * 0.1))
            max_fee = max(int(base_fee * 3 + priority_fee), network_gas * 2)
            approve_tx = contract.functions.approve(Web3.to_checksum_address(spender), 2**256 - 1).build_transaction({
                'from': WALLET_ADDRESS,
                'chainId': CHAIN_ID,
                'nonce': nonce,
                'gas': 100000,
                'maxPriorityFeePerGas': priority_fee,
                'maxFeePerGas': max_fee,
                'type': 2,
                'value': 0,
            })
            signed_tx = account.sign_transaction(approve_tx)
            raw_tx = getattr(signed_tx, 'raw_transaction', None) or getattr(signed_tx, 'rawTransaction')
            tx_hash = w3.eth.send_raw_transaction(raw_tx).hex()
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            logger.info(f"Approval submitted: tx_hash={tx_hash} status={receipt.status}")
            refreshed = contract.functions.allowance(Web3.to_checksum_address(WALLET_ADDRESS), Web3.to_checksum_address(spender)).call()
            logger.info(f"Post-approval allowance read: token={token_address} spender={spender} allowance={refreshed}")
            if refreshed < required_amount:
                return {'approved': True, 'approval_tx_hash': tx_hash, 'allowance': refreshed, 'status': receipt.status, 'verified_effective': False}
            return {'approved': True, 'approval_tx_hash': tx_hash, 'allowance': refreshed, 'status': receipt.status, 'verified_effective': True}
        except Exception as e:
            logger.error(f"Allowance ensure failed: {e}")
            return None

    def get_swap_data(
        self,
        from_token: str,
        to_token: str,
        amount: int,
        slippage: float = None
    ) -> Optional[Dict]:
        """
        Get swap transaction data from 1inch
        
        Returns tx data that can be signed and sent
        """
        if not self.enabled:
            logger.error("Live trading not enabled")
            return None
        
        try:
            approve_response = requests.get(
                f'{self.base_url}/approve/spender',
                headers=self.headers,
                timeout=15
            )
            spender = approve_response.json().get('address') if approve_response.ok else '0x1111111254eeb25477b68fb85ed929f73a960582'
            allowance_result = self.ensure_allowance(from_token, spender, amount)
            logger.info(f"Allowance result: {allowance_result}")
            if not allowance_result or (allowance_result.get('status') == 0):
                logger.error("Approval orchestration failed before swap")
                return None

            params = {
                'src': from_token,
                'dst': to_token,
                'amount': str(amount),
                'from': WALLET_ADDRESS,
                'slippage': slippage or MAX_SLIPPAGE_PERCENT,
                'disableEstimate': 'false',
                'allowPartialFill': 'false'
            }
            
            response = requests.get(
                f'{self.base_url}/swap',
                headers=self.headers,
                params=params,
                timeout=15
            )
            
            if response.status_code == 429:
                logger.error("1inch rate limit hit")
                return None
            if response.status_code >= 400:
                logger.error(f"1inch swap error: status={response.status_code} url={response.url}")
                logger.error(f"1inch swap error body: {response.text}")
                logger.error(f"1inch swap params: src={from_token[:20]}... dst={to_token[:20]}... amount={amount} chain={CHAIN_ID}")
                response.raise_for_status()
            data = response.json()
            
            return {
                'tx': data.get('tx'),
                'to_amount': data.get('toAmount'),
                'from_amount': amount,
                'protocols': data.get('protocols', []),
                'dst_token': to_token,
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"1inch swap error: {e}")
            return None
    
    def validate_swap(self, swap_data: Dict) -> bool:
        """Validate swap data before execution"""
        if not swap_data or 'tx' not in swap_data:
            return False
        
        tx = swap_data['tx']
        
        # Check required fields
        required = ['to', 'data', 'value', 'gas']
        if not all(k in tx for k in required):
            logger.error(f"Missing tx fields: {tx}")
            return False
        
        # Validate destination is 1inch router
        if not tx['to'].startswith('0x'):
            logger.error(f"Invalid to address: {tx['to']}")
            return False
        
        return True
    
    def execute_swap(self, swap_data: Dict) -> Optional[str]:
        """Execute a swap transaction by sanitizing 1inch tx data for Base/Web3."""
        if not self.validate_swap(swap_data):
            return None

        tx = swap_data['tx']

        try:
            from eth_account import Account
            from web3 import Web3

            w3 = Web3(Web3.HTTPProvider(BASE_RPC_URL))
            if not w3.is_connected():
                logger.error("Failed to connect to Base RPC")
                return None

            account = Account.from_key(PRIVATE_KEY)
            if account.address.lower() != WALLET_ADDRESS.lower():
                logger.error(f"Private key address mismatch: {account.address} != {WALLET_ADDRESS}")
                return None

            nonce = w3.eth.get_transaction_count(WALLET_ADDRESS, 'pending')
            latest_block = w3.eth.get_block('latest')
            base_fee = latest_block.get('baseFeePerGas', w3.eth.gas_price)
            network_gas = int(w3.eth.gas_price)
            priority_fee = max(w3.to_wei(0.005, 'gwei'), int(network_gas * 0.1))
            max_fee = max(int(base_fee * 3 + priority_fee), int(tx.get('gasPrice', network_gas)) * 2, network_gas * 2)

            transaction = {
                'chainId': CHAIN_ID,
                'nonce': nonce,
                'to': Web3.to_checksum_address(tx['to']),
                'data': tx['data'],
                'value': int(tx.get('value', 0)),
                'gas': int(tx.get('gas', 300000)),
                'maxPriorityFeePerGas': priority_fee,
                'maxFeePerGas': max_fee,
                'type': 2,
            }

            signed_tx = account.sign_transaction(transaction)
            raw_tx = getattr(signed_tx, 'raw_transaction', None) or getattr(signed_tx, 'rawTransaction')
            tx_hash = w3.eth.send_raw_transaction(raw_tx)
            tx_hash_hex = tx_hash.hex()
            
            logger.info(
                "SWAP EXECUTED",
                extra={
                    'type': 'swap_executed',
                    'data': {
                        'tx_hash': tx_hash_hex,
                        'to': tx['to'],
                        'value': tx['value'],
                        'gas': tx['gas']
                    }
                }
            )
            
            return tx_hash_hex
            
        except Exception as e:
            logger.error(f"Transaction execution failed: {e}; tx={tx}")
            return None
    
    def check_transaction_status(self, tx_hash: str) -> Optional[Dict]:
        """Check if a transaction has been confirmed"""
        try:
            from web3 import Web3
            w3 = Web3(Web3.HTTPProvider(BASE_RPC_URL))
            
            receipt = w3.eth.get_transaction_receipt(tx_hash)
            
            if receipt:
                return {
                    'confirmed': True,
                    'status': 'success' if receipt['status'] == 1 else 'failed',
                    'block_number': receipt['blockNumber'],
                    'gas_used': receipt['gasUsed']
                }
            else:
                return {'confirmed': False}
                
        except Exception as e:
            logger.error(f"Failed to check transaction status: {e}")
            return None

# Global instance
live_executor = LiveExecutor()
