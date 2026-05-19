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

    def get_recent_prices(self, symbol: str, lookback_points: int = 12) -> list:
        history = self.price_history.get(symbol, [])
        return [p for _, p in history[-lookback_points:]]

    def get_midpoint(self, symbol: str, lookback_points: int = 12) -> Optional[float]:
        recent = self.get_recent_prices(symbol, lookback_points)
        if not recent:
            latest = self.price_history.get(symbol, [])
            return latest[-1][1] if latest else None
        return sum(recent) / len(recent)

    def get_reversal_context(self, symbol: str, lookback_points: int = 12) -> Dict[str, Optional[float]]:
        recent = self.get_recent_prices(symbol, lookback_points)
        if len(recent) < 3:
            latest = recent[-1] if recent else None
            return {
                'midpoint_price': latest,
                'distance_from_mid_pct': 0.0,
                'reversal_strength_pct': 0.0,
                'extension_strength_pct': 0.0,
                'pullback_depth_pct': 0.0,
                'trend_bias': None,
            }

        current = recent[-1]
        midpoint = sum(recent) / len(recent)
        window_low = min(recent)
        window_high = max(recent)
        prev = recent[-2]
        prev2 = recent[-3]
        last_change_pct = ((current - prev) / prev * 100) if prev else 0.0
        prev_change_pct = ((prev - prev2) / prev2 * 100) if prev2 else 0.0
        reversal_strength_pct = 0.0
        if prev_change_pct < 0 < last_change_pct:
            reversal_strength_pct = abs(prev_change_pct) + abs(last_change_pct)
        elif prev_change_pct > 0 > last_change_pct:
            reversal_strength_pct = abs(prev_change_pct) + abs(last_change_pct)
        extension_strength_pct = abs(last_change_pct)
        distance_from_mid_pct = ((current - midpoint) / midpoint * 100) if midpoint else 0.0
        pullback_depth_pct = ((midpoint - window_low) / midpoint * 100) if midpoint else 0.0
        trend_bias = 'up' if current > midpoint else 'down'
        return {
            'midpoint_price': midpoint,
            'distance_from_mid_pct': distance_from_mid_pct,
            'reversal_strength_pct': reversal_strength_pct,
            'extension_strength_pct': extension_strength_pct,
            'pullback_depth_pct': pullback_depth_pct,
            'window_low': window_low,
            'window_high': window_high,
            'trend_bias': trend_bias,
        }

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
