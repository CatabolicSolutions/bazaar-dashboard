"""1inch API wrapper for quotes and swaps"""
import requests
import time
from typing import Optional, Dict
from config.settings import INCH_API_KEY, rate_limiter, WALLET_ADDRESS, CHAIN_ID

class OneInchClient:
    def __init__(self):
        self.base_url = f'https://api.1inch.dev/swap/v5.2/{CHAIN_ID}'
        self.headers = {
            'Authorization': f'Bearer {INCH_API_KEY}',
            'Content-Type': 'application/json'
        }
        self.last_quote = None
        self.last_quote_time = 0
        self.quote_cache_seconds = 5
    
    def _can_make_request(self) -> bool:
        """Check if we can make a request (rate limiting)"""
        if not rate_limiter.can_make_inch_request():
            print(f"1inch rate limit reached: {rate_limiter.get_status()}")
            return False
        return True
    
    def get_quote(
        self,
        from_token: str,
        to_token: str,
        amount: int,
        use_cache: bool = True
    ) -> Optional[Dict]:
        """
        Get swap quote from 1inch
        
        Args:
            from_token: Token address to swap from
            to_token: Token address to swap to
            amount: Amount in smallest unit (wei for ETH)
            use_cache: Whether to use cached quote if available
        """
        # Check cache
        now = time.time()
        if use_cache and self.last_quote:
            cache_age = now - self.last_quote_time
            if cache_age < self.quote_cache_seconds:
                print(f"Using cached quote (age: {cache_age:.1f}s)")
                return self.last_quote
        
        # Check rate limit
        if not self._can_make_request():
            return None
        
        try:
            params = {
                'src': from_token,
                'dst': to_token,
                'amount': str(amount),
                'from': WALLET_ADDRESS,
                'slippage': 1,  # 1% slippage
                'disableEstimate': 'false'
            }
            
            response = requests.get(
                f'{self.base_url}/quote',
                headers=self.headers,
                params=params,
                timeout=10
            )
            
            # Record request
            rate_limiter.record_inch_request()
            print(f"1inch requests today: {rate_limiter.get_status()['inch_requests_today']}/900")
            
            if response.status_code == 429:
                print("1inch rate limit hit (429)")
                return None
            
            response.raise_for_status()
            data = response.json()
            
            # Cache the quote
            self.last_quote = data
            self.last_quote_time = now
            
            return data
            
        except requests.exceptions.RequestException as e:
            print(f"1inch API error: {e}")
            return None
    
    def calculate_profit_potential(
        self,
        from_token: str,
        to_token: str,
        amount_usd: float,
        current_price: float
    ) -> Optional[Dict]:
        """
        Calculate profit potential for a swap
        
        Returns dict with expected profit % or None if not profitable
        """
        # Convert USD amount to token amount (approximate)
        if 'ETH' in from_token or from_token.lower().endswith('eee'):
            amount_eth = amount_usd / current_price
            amount_wei = int(amount_eth * 1e18)
        else:
            # USDC has 6 decimals
            amount_wei = int(amount_usd * 1e6)
        
        quote = self.get_quote(from_token, to_token, amount_wei)
        
        if not quote:
            return None
        
        # Calculate expected output
        to_amount = int(quote.get('toAmount', 0))
        
        # Convert back to USD for comparison
        if 'ETH' in to_token or to_token.lower().endswith('eee'):
            to_amount_eth = to_amount / 1e18
            to_amount_usd = to_amount_eth * current_price
        else:
            to_amount_usd = to_amount / 1e6
        
        # Calculate profit
        profit_usd = to_amount_usd - amount_usd
        profit_pct = (profit_usd / amount_usd) * 100 if amount_usd > 0 else 0
        
        # Estimate gas cost
        gas_cost_eth = self._estimate_gas_cost(quote)
        gas_cost_usd = gas_cost_eth * current_price if gas_cost_eth else 2  # Default $2
        
        # Net profit after gas
        net_profit_usd = profit_usd - gas_cost_usd
        net_profit_pct = (net_profit_usd / amount_usd) * 100 if amount_usd > 0 else 0
        
        return {
            'gross_profit_usd': profit_usd,
            'gross_profit_pct': profit_pct,
            'gas_cost_usd': gas_cost_usd,
            'net_profit_usd': net_profit_usd,
            'net_profit_pct': net_profit_pct,
            'quote': quote
        }
    
    def _estimate_gas_cost(self, quote: Dict) -> Optional[float]:
        """Estimate gas cost in ETH"""
        try:
            gas = int(quote.get('estimatedGas', 150000))
            # Base gas is much lower than mainnet, use 0.1 gwei default estimate
            gas_cost_eth = (gas * 0.1 * 1e9) / 1e18
            return gas_cost_eth
        except:
            return None
    
    def get_rate_limit_status(self) -> Dict:
        """Get current rate limit status"""
        return rate_limiter.get_status()

# Global instance
inch_client = OneInchClient()
