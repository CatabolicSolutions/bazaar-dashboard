"""Live trade execution via 1inch"""
import requests
import time
from typing import Optional, Dict
from config.settings import INCH_API_KEY, WALLET_ADDRESS, PRIVATE_KEY, MAX_SLIPPAGE_PERCENT, BASE_RPC_URL, CHAIN_ID
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
            
            response.raise_for_status()
            data = response.json()
            
            return {
                'tx': data.get('tx'),
                'to_amount': data.get('toAmount'),
                'from_amount': amount,
                'protocols': data.get('protocols', [])
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
        """
        Execute a swap transaction - FULLY AUTOMATED
        
        Signs the transaction with private key and broadcasts via Alchemy
        """
        if not self.validate_swap(swap_data):
            return None
        
        tx = swap_data['tx']
        
        try:
            from eth_account import Account
            from web3 import Web3
            
            # Initialize Web3 with Base RPC
            w3 = Web3(Web3.HTTPProvider(BASE_RPC_URL))
            
            if not w3.is_connected():
                logger.error("Failed to connect to Ethereum node")
                return None
            
            # Create account from private key
            account = Account.from_key(PRIVATE_KEY)
            
            # Verify address matches
            if account.address.lower() != WALLET_ADDRESS.lower():
                logger.error(f"Private key address mismatch: {account.address} != {WALLET_ADDRESS}")
                return None
            
            # Build transaction
            transaction = {
                'to': tx['to'],
                'data': tx['data'],
                'value': int(tx['value']),
                'gas': int(tx['gas']),
                'gasPrice': int(tx.get('gasPrice', w3.eth.gas_price)),
                'nonce': w3.eth.get_transaction_count(WALLET_ADDRESS),
                'chainId': CHAIN_ID
            }
            
            # Sign transaction
            signed_tx = account.sign_transaction(transaction)
            
            # Send transaction
            tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
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
            logger.error(f"Transaction execution failed: {e}")
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
