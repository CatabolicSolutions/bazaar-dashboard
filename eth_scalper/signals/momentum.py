"""Compounding volatility signal detection for ETH/BTC"""
import time
from typing import Optional, Dict
from config.settings import (
    MIN_PRICE_MOVEMENT_PCT, MAX_GAS_GWEI, MIN_SIGNAL_SCORE, BASE_ASSET_UNIVERSE, BLOC_SIGNAL_LOOKBACK_SECONDS
)
from signals.price_feed import price_feed
from signals.multi_asset_feed import multi_asset_feed

class MomentumDetector:
    def __init__(self):
        self.recent_signals = []  # Track recent signals for scoring
        self.max_signal_history = 50
    
    def detect_momentum(self) -> Optional[Dict]:
        """Detect best current pullback/reversion signal across enabled ETH/BTC universe."""
        gas = price_feed.get_gas_price_gwei()
        if gas is None or gas > MAX_GAS_GWEI:
            return None

        prices = multi_asset_feed.get_prices()
        best_signal = None
        for asset in sorted([a for a in BASE_ASSET_UNIVERSE if a.get('enabled')], key=lambda a: a.get('priority', 99)):
            symbol = asset['symbol']
            current_price = prices.get(symbol)
            change_pct = multi_asset_feed.get_price_change_60s(symbol)
            if current_price is None:
                continue

            history = multi_asset_feed.price_history.get(symbol, [])
             
            if change_pct is None:
                change_pct = 0.0
            midpoint = sum(p for _, p in history[-12:]) / max(1, len(history[-12:])) if history else current_price
            distance_from_mid = ((current_price - midpoint) / midpoint) * 100 if midpoint else 0.0
            at_or_below_mid = current_price <= midpoint
            price_movement = abs(change_pct)
            if not at_or_below_mid and price_movement < MIN_PRICE_MOVEMENT_PCT:
                continue

            direction = 'down' if at_or_below_mid else ('up' if change_pct > 0 else 'down')
            setup = 'buy_pullback' if at_or_below_mid else ('sell_strength' if direction == 'up' else 'buy_pullback')

            stats = {
                'symbol': symbol,
                'current_price': current_price,
                'change_60s_pct': change_pct,
                'gas_gwei': gas,
                'midpoint_price': midpoint,
                'distance_from_mid_pct': distance_from_mid,
                'setup': setup,
                'lookback_seconds': BLOC_SIGNAL_LOOKBACK_SECONDS,
                'recent_prices': [p for _, p in history[-12:]],
            }
            score = self._calculate_score(stats)
            if score < MIN_SIGNAL_SCORE and not at_or_below_mid:
                continue

            if at_or_below_mid:
                score = max(score, MIN_SIGNAL_SCORE)

            signal = {
                'timestamp': time.time(),
                'symbol': symbol,
                'direction': direction,
                'price': current_price,
                'change_60s_pct': change_pct,
                'gas_gwei': gas,
                'score': score,
                'type': 'volatility_capture',
                'setup': setup,
                'midpoint_price': midpoint,
                'distance_from_mid_pct': distance_from_mid,
                'pullback_bias': current_price <= midpoint,
                'sell_strength_bias': direction == 'up' and current_price >= midpoint,
            }
            if best_signal is None or signal['score'] > best_signal['score']:
                best_signal = signal

        if best_signal:
            self._record_signal(best_signal)
        return best_signal
    
    def _calculate_score(self, stats: Dict) -> int:
        """Calculate signal score 1-10 for chop/reversion setups."""
        score = 0
        price_movement = abs(stats['change_60s_pct'])
        if price_movement >= 0.30:
            score += 3
        elif price_movement >= 0.20:
            score += 2
        elif price_movement >= MIN_PRICE_MOVEMENT_PCT:
            score += 1

        gas = stats['gas_gwei']
        if gas <= 5:
            score += 2
        elif gas <= 15:
            score += 1

        recent_prices = stats.get('recent_prices') or []
        volatility = self._calculate_volatility(recent_prices) if recent_prices else 0
        if volatility >= 0.10:
            score += 2
        elif volatility >= 0.05:
            score += 1

        distance = abs(stats.get('distance_from_mid_pct') or 0)
        if distance >= 0.10:
            score += 2
        elif distance >= 0.05:
            score += 1

        recent_wins = self._get_recent_win_rate()
        if recent_wins >= 0.5:
            score += 1

        return min(score, 10)
    
    def _calculate_volatility(self, prices: list) -> float:
        """Calculate price volatility as std dev / mean"""
        if len(prices) < 2:
            return 0
        
        mean = sum(prices) / len(prices)
        if mean == 0:
            return 0
        
        variance = sum((p - mean) ** 2 for p in prices) / len(prices)
        std_dev = variance ** 0.5
        
        return (std_dev / mean) * 100  # As percentage
    
    def _get_recent_win_rate(self) -> float:
        """Get win rate from recent signals"""
        if not self.recent_signals:
            return 0.5  # Neutral if no history
        
        recent = self.recent_signals[-20:]  # Last 20 signals
        wins = sum(1 for s in recent if s.get('outcome') == 'win')
        return wins / len(recent) if recent else 0.5
    
    def _record_signal(self, signal: Dict):
        """Record signal for tracking"""
        self.recent_signals.append(signal)
        if len(self.recent_signals) > self.max_signal_history:
            self.recent_signals.pop(0)
    
    def update_signal_outcome(self, signal_timestamp: float, outcome: str, pnl: float = 0):
        """Update outcome of a signal (win/loss)"""
        for signal in self.recent_signals:
            if signal['timestamp'] == signal_timestamp:
                signal['outcome'] = outcome
                signal['pnl'] = pnl
                break
    
    def get_stats(self) -> Dict:
        """Get detector statistics"""
        return {
            'total_signals': len(self.recent_signals),
            'recent_win_rate': self._get_recent_win_rate(),
            'avg_score': sum(s['score'] for s in self.recent_signals) / len(self.recent_signals) if self.recent_signals else 0
        }

# Global instance
momentum_detector = MomentumDetector()
