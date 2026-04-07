"""Price feed from Alchemy and other sources"""
import requests
import time
from typing import Optional, Dict
from config.settings import ALCHEMY_URL, rate_limiter

class PriceFeed:
    def __init__(self):
        self.eth_price_history = []  # [(timestamp, price), ...]
        self.max_history = 300  # 5 minutes of data
        self.last_alchemy_call = 0
        self.alchemy_cache_seconds = 5
    
    def get_eth_price(self) -> Optional[float]:
        """Get current ETH price in USD from Alchemy"""
        # Simple cache to avoid hammering API
        now = time.time()
        if now - self.last_alchemy_call < self.alchemy_cache_seconds:
            # Return last known price
            if self.eth_price_history:
                return self.eth_price_history[-1][1]
        
        try:
            # Use Alchemy's eth_call to get price from a reliable source
            # For now, using a simple approach - in production use Chainlink or similar
            response = requests.post(
                ALCHEMY_URL,
                json={
                    'jsonrpc': '2.0',
                    'method': 'eth_gasPrice',
                    'params': [],
                    'id': 1
                },
                timeout=10
            )
            
            # Also fetch from Binance as reference
            binance_price = self._get_binance_eth_price()
            
            if binance_price:
                self._record_price(binance_price)
                self.last_alchemy_call = now
                return binance_price
            
            return None
            
        except Exception as e:
            print(f"Error fetching ETH price: {e}")
            # Return last known price if available
            if self.eth_price_history:
                return self.eth_price_history[-1][1]
            return None
    
    def _get_binance_eth_price(self) -> Optional[float]:
        """Get ETH price from Binance (no API key needed)"""
        try:
            response = requests.get(
                'https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDC',
                timeout=5
            )
            data = response.json()
            return float(data['price'])
        except Exception as e:
            print(f"Error fetching Binance price: {e}")
            return None
    
    def _record_price(self, price: float):
        """Record price with timestamp"""
        now = time.time()
        self.eth_price_history.append((now, price))
        
        # Trim old data
        cutoff = now - 300  # 5 minutes ago
        self.eth_price_history = [(t, p) for t, p in self.eth_price_history if t > cutoff]
    
    def get_price_change_60s(self) -> Optional[float]:
        """Get price change % in last 60 seconds"""
        if len(self.eth_price_history) < 2:
            return None
        
        now = time.time()
        current_price = self.eth_price_history[-1][1]
        
        # Find price from ~60 seconds ago
        target_time = now - 60
        closest_price = None
        closest_diff = float('inf')
        
        for timestamp, price in self.eth_price_history:
            diff = abs(timestamp - target_time)
            if diff < closest_diff:
                closest_diff = diff
                closest_price = price
        
        if closest_price and closest_price > 0:
            change_pct = ((current_price - closest_price) / closest_price) * 100
            return change_pct
        
        return None
    
    def get_gas_price_gwei(self) -> Optional[float]:
        """Get current gas price in gwei"""
        try:
            response = requests.post(
                ALCHEMY_URL,
                json={
                    'jsonrpc': '2.0',
                    'method': 'eth_gasPrice',
                    'params': [],
                    'id': 1
                },
                timeout=10
            )
            data = response.json()
            gas_wei = int(data['result'], 16)
            gas_gwei = gas_wei / 1e9
            return gas_gwei
        except Exception as e:
            print(f"Error fetching gas price: {e}")
            return None
    
    def get_price_stats(self) -> Dict:
        """Get current price statistics"""
        current = self.get_eth_price()
        change_60s = self.get_price_change_60s()
        gas = self.get_gas_price_gwei()
        
        return {
            'current_price': current,
            'change_60s_pct': change_60s,
            'gas_gwei': gas,
            'history_length': len(self.eth_price_history),
            'timestamp': time.time()
        }

# Global instance
price_feed = PriceFeed()
