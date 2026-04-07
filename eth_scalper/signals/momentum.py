"""Momentum detection for ETH scalping"""
import time
from typing import Optional, Dict
from config.settings import (
    MIN_PRICE_MOVEMENT_PCT, MAX_GAS_GWEI, MIN_SIGNAL_SCORE
)
from signals.price_feed import price_feed

class MomentumDetector:
    def __init__(self):
        self.recent_signals = []  # Track recent signals for scoring
        self.max_signal_history = 50
    
    def detect_momentum(self) -> Optional[Dict]:
        """
        Detect if there's a momentum signal worth trading
        Returns signal dict or None
        """
        stats = price_feed.get_price_stats()
        
        # Check basic conditions
        if stats['current_price'] is None:
            return None
        
        if stats['change_60s_pct'] is None:
            return None
        
        if stats['gas_gwei'] is None:
            return None
        
        # Check thresholds
        price_movement = abs(stats['change_60s_pct'])
        gas_ok = stats['gas_gwei'] <= MAX_GAS_GWEI
        
        if price_movement < MIN_PRICE_MOVEMENT_PCT:
            return None
        
        if not gas_ok:
            return None
        
        # Determine direction
        direction = 'up' if stats['change_60s_pct'] > 0 else 'down'
        
        # Calculate signal score
        score = self._calculate_score(stats)
        
        if score < MIN_SIGNAL_SCORE:
            return None
        
        signal = {
            'timestamp': time.time(),
            'direction': direction,
            'price': stats['current_price'],
            'change_60s_pct': stats['change_60s_pct'],
            'gas_gwei': stats['gas_gwei'],
            'score': score,
            'type': 'momentum'
        }
        
        self._record_signal(signal)
        return signal
    
    def _calculate_score(self, stats: Dict) -> int:
        """Calculate signal score 1-10"""
        score = 0
        
        # Price momentum strength (weight: 3)
        price_movement = abs(stats['change_60s_pct'])
        if price_movement >= 1.0:
            score += 3
        elif price_movement >= 0.7:
            score += 2
        elif price_movement >= 0.4:
            score += 1
        
        # Gas efficiency (weight: 2)
        gas = stats['gas_gwei']
        if gas <= 15:
            score += 2
        elif gas <= 25:
            score += 1
        
        # Market volatility (weight: 1) - based on recent activity
        if len(price_feed.eth_price_history) > 10:
            recent_prices = [p for _, p in price_feed.eth_price_history[-10:]]
            volatility = self._calculate_volatility(recent_prices)
            if volatility > 0.5:
                score += 1
        
        # Recent win rate (weight: 1)
        recent_wins = self._get_recent_win_rate()
        if recent_wins > 0.6:
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
