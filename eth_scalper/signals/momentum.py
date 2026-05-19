"""Compounding volatility signal detection for ETH/BTC"""
import time
from typing import Optional, Dict
from config.settings import (
    MIN_PRICE_MOVEMENT_PCT, MAX_GAS_GWEI, MIN_SIGNAL_SCORE, BASE_ASSET_UNIVERSE, BLOC_SIGNAL_LOOKBACK_SECONDS,
    BLOC_ROTATE_SIGNAL_LOOKBACK_POINTS, BLOC_ROTATE_SIGNAL_MOM_POINTS, BLOC_ROTATE_SIGNAL_MIN_EDGE_PCT,
    BLOC_ROTATE_SIGNAL_MIN_DEV_PCT, BLOC_ROTATE_SIGNAL_MIN_SPREAD_MOVE_PCT, BLOC_ROTATE_SIGNAL_PERSIST_BARS,
    BLOC_ARM_WAIT_SUPPRESS_DURING_ROTATE, BLOC_ARM_WAIT_MIN_ROTATE_EDGE_PCT,
)
from signals.price_feed import price_feed
from signals.multi_asset_feed import multi_asset_feed

class MomentumDetector:
    def __init__(self):
        self.recent_signals = []  # Track recent signals for scoring
        self.max_signal_history = 50
        self.rotate_signal_state = {'signal': 'NONE', 'streak': 0, 'edge_pct': 0.0}
    
    def _compute_rotate_context(self, prices: Dict[str, float]) -> Dict:
        eth_hist = multi_asset_feed.get_recent_prices('ETH', BLOC_ROTATE_SIGNAL_LOOKBACK_POINTS)
        btc_hist = multi_asset_feed.get_recent_prices('BTC', BLOC_ROTATE_SIGNAL_LOOKBACK_POINTS)
        if len(eth_hist) < max(3, BLOC_ROTATE_SIGNAL_MOM_POINTS + 1) or len(btc_hist) < max(3, BLOC_ROTATE_SIGNAL_MOM_POINTS + 1):
            self.rotate_signal_state = {'signal': 'NONE', 'streak': 0, 'edge_pct': 0.0}
            return {'signal': 'NONE', 'streak': 0, 'edge_pct': 0.0, 'spread_dev_pct': 0.0, 'spread_move_pct': 0.0, 'eth_mom_pct': 0.0, 'btc_mom_pct': 0.0}

        spread_series = [e / b for e, b in zip(eth_hist, btc_hist) if b]
        if len(spread_series) < 3:
            self.rotate_signal_state = {'signal': 'NONE', 'streak': 0, 'edge_pct': 0.0}
            return {'signal': 'NONE', 'streak': 0, 'edge_pct': 0.0, 'spread_dev_pct': 0.0, 'spread_move_pct': 0.0, 'eth_mom_pct': 0.0, 'btc_mom_pct': 0.0}

        spread_now = spread_series[-1]
        spread_prev = spread_series[-2]
        spread_anchor = sum(spread_series) / len(spread_series)
        spread_dev_pct = ((spread_now - spread_anchor) / spread_anchor * 100.0) if spread_anchor else 0.0
        spread_move_pct = ((spread_now - spread_prev) / spread_prev * 100.0) if spread_prev else 0.0
        mom_n = min(BLOC_ROTATE_SIGNAL_MOM_POINTS, len(eth_hist) - 1, len(btc_hist) - 1)
        eth_ref = eth_hist[-1 - mom_n]
        btc_ref = btc_hist[-1 - mom_n]
        eth_mom_pct = ((eth_hist[-1] - eth_ref) / eth_ref * 100.0) if eth_ref else 0.0
        btc_mom_pct = ((btc_hist[-1] - btc_ref) / btc_ref * 100.0) if btc_ref else 0.0

        signal = 'NONE'
        edge_pct = 0.0
        if spread_dev_pct >= BLOC_ROTATE_SIGNAL_MIN_DEV_PCT and spread_move_pct >= BLOC_ROTATE_SIGNAL_MIN_SPREAD_MOVE_PCT and (btc_mom_pct - eth_mom_pct) >= BLOC_ROTATE_SIGNAL_MIN_EDGE_PCT:
            signal = 'ROTATE_TO_BTC'
            edge_pct = btc_mom_pct - eth_mom_pct
        elif spread_dev_pct <= -BLOC_ROTATE_SIGNAL_MIN_DEV_PCT and spread_move_pct <= -BLOC_ROTATE_SIGNAL_MIN_SPREAD_MOVE_PCT and (eth_mom_pct - btc_mom_pct) >= BLOC_ROTATE_SIGNAL_MIN_EDGE_PCT:
            signal = 'ROTATE_TO_ETH'
            edge_pct = eth_mom_pct - btc_mom_pct

        if signal != 'NONE' and signal == self.rotate_signal_state.get('signal'):
            streak = self.rotate_signal_state.get('streak', 0) + 1
        elif signal != 'NONE':
            streak = 1
        else:
            streak = 0
        self.rotate_signal_state = {'signal': signal, 'streak': streak, 'edge_pct': edge_pct}
        return {
            'signal': signal,
            'streak': streak,
            'edge_pct': edge_pct,
            'spread_dev_pct': spread_dev_pct,
            'spread_move_pct': spread_move_pct,
            'eth_mom_pct': eth_mom_pct,
            'btc_mom_pct': btc_mom_pct,
        }

    def detect_momentum(self) -> Optional[Dict]:
        """Detect best current pullback/reversion signal across enabled ETH/BTC universe."""
        gas = price_feed.get_gas_price_gwei()
        if gas is None or gas > MAX_GAS_GWEI:
            return None

        prices = multi_asset_feed.get_prices()
        rotate = self._compute_rotate_context(prices)
        best_signal = None
        for asset in sorted([a for a in BASE_ASSET_UNIVERSE if a.get('enabled')], key=lambda a: a.get('priority', 99)):
            symbol = asset['symbol']
            current_price = prices.get(symbol)
            change_pct = multi_asset_feed.get_price_change_60s(symbol)
            if current_price is None:
                continue

            history = multi_asset_feed.price_history.get(symbol, [])
            reversal = multi_asset_feed.get_reversal_context(symbol, 12)

            if change_pct is None:
                change_pct = 0.0
            midpoint = reversal.get('midpoint_price') or current_price
            distance_from_mid = float(reversal.get('distance_from_mid_pct') or 0.0)
            reversal_strength = float(reversal.get('reversal_strength_pct') or 0.0)
            extension_strength = float(reversal.get('extension_strength_pct') or 0.0)
            pullback_depth = float(reversal.get('pullback_depth_pct') or 0.0)
            at_or_below_mid = current_price <= midpoint
            price_movement = abs(change_pct)
            if not at_or_below_mid and price_movement < MIN_PRICE_MOVEMENT_PCT and reversal_strength < MIN_PRICE_MOVEMENT_PCT:
                continue

            if at_or_below_mid and (change_pct > 0 or reversal_strength >= MIN_PRICE_MOVEMENT_PCT):
                direction = 'up'
                setup = 'buy_reversal'
            elif at_or_below_mid:
                direction = 'down'
                setup = 'buy_pullback'
            else:
                direction = 'up' if change_pct >= 0 else 'down'
                setup = 'sell_strength' if direction == 'up' else 'buy_pullback'

            stats = {
                'symbol': symbol,
                'current_price': current_price,
                'change_60s_pct': change_pct,
                'gas_gwei': gas,
                'midpoint_price': midpoint,
                'distance_from_mid_pct': distance_from_mid,
                'reversal_strength_pct': reversal_strength,
                'extension_strength_pct': extension_strength,
                'pullback_depth_pct': pullback_depth,
                'setup': setup,
                'lookback_seconds': BLOC_SIGNAL_LOOKBACK_SECONDS,
                'recent_prices': [p for _, p in history[-12:]],
            }
            score = self._calculate_score(stats)
            if score < MIN_SIGNAL_SCORE and not at_or_below_mid and reversal_strength < MIN_PRICE_MOVEMENT_PCT:
                continue

            if at_or_below_mid:
                score = max(score, MIN_SIGNAL_SCORE)
            if setup == 'buy_reversal':
                score = min(10, max(score, MIN_SIGNAL_SCORE + 1))

            signal = {
                'timestamp': time.time(),
                'symbol': symbol,
                'direction': direction,
                'price': current_price,
                'change_60s_pct': change_pct,
                'gas_gwei': gas,
                'score': score,
                'type': setup,
                'setup': setup,
                'midpoint_price': midpoint,
                'distance_from_mid_pct': distance_from_mid,
                'reversal_strength_pct': reversal_strength,
                'extension_strength_pct': extension_strength,
                'pullback_depth_pct': pullback_depth,
                'pullback_bias': current_price <= midpoint,
                'sell_strength_bias': direction == 'up' and current_price >= midpoint,
            }
            rotate_bonus = 0
            if rotate['signal'] == f"ROTATE_TO_{symbol}" and rotate['streak'] >= BLOC_ROTATE_SIGNAL_PERSIST_BARS:
                rotate_bonus = 3
            elif rotate['signal'] == f"ROTATE_TO_{symbol}":
                rotate_bonus = 1
            signal['score'] = min(10, signal['score'] + rotate_bonus)
            signal['rotate_signal'] = rotate['signal']
            signal['rotate_signal_streak'] = rotate['streak']
            signal['rotate_edge_pct'] = rotate['edge_pct']
            signal['spread_dev_pct'] = rotate['spread_dev_pct']
            signal['spread_move_pct'] = rotate['spread_move_pct']
            signal['eth_mom_pct'] = rotate['eth_mom_pct']
            signal['btc_mom_pct'] = rotate['btc_mom_pct']
            signal['selection_bias'] = 'conservative_positive_baseline'

            if BLOC_ARM_WAIT_SUPPRESS_DURING_ROTATE and rotate['signal'] != 'NONE' and rotate['edge_pct'] < BLOC_ARM_WAIT_MIN_ROTATE_EDGE_PCT and signal['setup'] == 'buy_pullback':
                continue

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

        reversal_strength = abs(stats.get('reversal_strength_pct') or 0)
        if reversal_strength >= 0.30:
            score += 3
        elif reversal_strength >= 0.15:
            score += 2
        elif reversal_strength >= MIN_PRICE_MOVEMENT_PCT:
            score += 1

        extension_strength = abs(stats.get('extension_strength_pct') or 0)
        if extension_strength >= 0.20:
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
