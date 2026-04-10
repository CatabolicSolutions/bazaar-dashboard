"""Multi-asset price feed for Base asset universe"""
import requests
import time
from typing import Optional, Dict
from config.settings import BASE_ASSET_UNIVERSE


class MultiAssetPriceFeed:
    def __init__(self):
        self.price_history: Dict[str, list] = {asset['symbol']: [] for asset in BASE_ASSET_UNIVERSE}
        self.max_history = 300
        self.cache_seconds = 5
        self.last_call = 0

    def get_prices(self) -> Dict[str, Optional[float]]:
        now = time.time()
        if now - self.last_call < self.cache_seconds:
            return {
                symbol: history[-1][1] if history else None
                for symbol, history in self.price_history.items()
            }

        prices = {}
        ids = ','.join(asset['coingecko_id'] for asset in BASE_ASSET_UNIVERSE if asset['enabled'])
        try:
            response = requests.get(
                f'https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd',
                timeout=5,
            )
            data = response.json()
            for asset in BASE_ASSET_UNIVERSE:
                if not asset['enabled']:
                    continue
                price = data.get(asset['coingecko_id'], {}).get('usd')
                if price:
                    prices[asset['symbol']] = float(price)
                    self._record_price(asset['symbol'], float(price))
                else:
                    prices[asset['symbol']] = None
        except Exception:
            prices = {
                symbol: history[-1][1] if history else None
                for symbol, history in self.price_history.items()
            }

        self.last_call = now
        return prices

    def _record_price(self, symbol: str, price: float):
        now = time.time()
        self.price_history[symbol].append((now, price))
        cutoff = now - 300
        self.price_history[symbol] = [(t, p) for t, p in self.price_history[symbol] if t > cutoff]

    def get_price_change_60s(self, symbol: str) -> Optional[float]:
        history = self.price_history.get(symbol, [])
        if len(history) < 2:
            return None
        now = time.time()
        current_price = history[-1][1]
        target_time = now - 60
        closest_price = None
        closest_diff = float('inf')
        for timestamp, price in history:
            diff = abs(timestamp - target_time)
            if diff < closest_diff:
                closest_diff = diff
                closest_price = price
        if closest_price and closest_price > 0:
            return ((current_price - closest_price) / closest_price) * 100
        return None


multi_asset_feed = MultiAssetPriceFeed()
