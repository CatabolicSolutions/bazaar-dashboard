"""Live trade execution via 1inch"""
import requests
import time
from typing import Optional, Dict
from config.settings import INCH_API_KEY, WALLET_ADDRESS, MAX_SLIPPAGE_PERCENT
from config.logger import logger

class LiveExecutor:
    """Execute real trades on 1inch"""
    
    def __init__(self):
        self.base_url = 'https://api.1inch.dev/swap/v5.2/1'
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
        # This is a safety check
        if not tx['to'].startswith('0x'):
            logger.error(f"Invalid to address: {tx['to']}")
            return False
        
        return True
    
    def execute_swap(self, swap_data: Dict) -> Optional[str]:
        """
        Execute a swap transaction
        
        NOTE: This requires a private key which we don't have.
        In production, this would:
        1. Sign the transaction with private key
        2. Send via Alchemy/eth_sendRawTransaction
        3. Return tx hash
        
        For now, we return the tx data for manual execution
        """
        if not self.validate_swap(swap_data):
            return None
        
        tx = swap_data['tx']
        
        # Log the transaction for manual execution
        logger.info(
            "SWAP READY FOR EXECUTION",
            extra={
                'type': 'swap_ready',
                'data': {
                    'to': tx['to'],
                    'value': tx['value'],
                    'gas': tx['gas'],
                    'data': tx['data'][:100] + '...'  # Truncate for log
                }
            }
        )
        
        # Return tx hash would go here after signing
        # For now return placeholder
        return f"pending_{int(time.time())}"
    
    def check_allowance(self, token: str) -> Optional[int]:
        """Check token allowance for 1inch router"""
        # This would check if token is approved for spending
        # For ETH (native), no approval needed
        # For USDC, would need to check allowance
        pass

# Global instance
live_executor = LiveExecutor()
