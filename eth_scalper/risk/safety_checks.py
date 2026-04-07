"""Critical safety checks for live trading"""
import time
from typing import Tuple, Optional
from config.settings import (
    INITIAL_CAPITAL_USD, MAX_POSITION_USD, MAX_DAILY_LOSS_USD,
    MAX_OPEN_POSITIONS, MAX_DAILY_TRADES
)

class SafetyChecker:
    """Pre-flight checks before any live trade"""
    
    def __init__(self):
        self.emergency_stop = False
        self.consecutive_errors = 0
        self.max_consecutive_errors = 5
        self.last_error_time = 0
        self.daily_stats = {
            'trades': 0,
            'losses': 0,
            'pnl': 0.0,
            'start_time': time.time()
        }
    
    def pre_trade_check(self, signal: dict, open_positions: int, 
                        daily_pnl: float, daily_trades: int) -> Tuple[bool, str]:
        """
        Comprehensive pre-trade safety check
        Returns: (can_trade, reason)
        """
        
        # 1. Emergency stop
        if self.emergency_stop:
            return False, "EMERGENCY STOP ACTIVE"
        
        # 2. Too many consecutive errors
        if self.consecutive_errors >= self.max_consecutive_errors:
            # Reset if it's been 5 minutes since last error
            if time.time() - self.last_error_time > 300:
                self.consecutive_errors = 0
            else:
                return False, f"Too many errors ({self.consecutive_errors})"
        
        # 3. Daily loss limit
        if daily_pnl <= -MAX_DAILY_LOSS_USD:
            self.trigger_emergency_stop("Daily loss limit hit")
            return False, f"DAILY LOSS LIMIT: ${daily_pnl:.2f}"
        
        # 4. Max daily trades
        if daily_trades >= MAX_DAILY_TRADES:
            return False, f"Max daily trades ({MAX_DAILY_TRADES}) reached"
        
        # 5. Max open positions
        if open_positions >= MAX_OPEN_POSITIONS:
            return False, f"Max open positions ({MAX_OPEN_POSITIONS})"
        
        # 6. Signal validation
        if not self._validate_signal(signal):
            return False, "Invalid signal data"
        
        # 7. Price sanity check
        price = signal.get('price', 0)
        if price < 1000 or price > 10000:
            return False, f"Price out of range: ${price}"
        
        # 8. Gas sanity check
        gas = signal.get('gas_gwei', 0)
        if gas > 100:
            return False, f"Gas too high: {gas} gwei"
        
        return True, "PASS"
    
    def _validate_signal(self, signal: dict) -> bool:
        """Validate signal has required fields"""
        required = ['price', 'direction', 'score', 'gas_gwei']
        return all(k in signal for k in required)
    
    def record_error(self, error: Exception):
        """Record an error and check thresholds"""
        self.consecutive_errors += 1
        self.last_error_time = time.time()
        
        if self.consecutive_errors >= self.max_consecutive_errors:
            self.trigger_emergency_stop(f"Error threshold: {error}")
    
    def record_success(self):
        """Reset error counter on success"""
        self.consecutive_errors = 0
    
    def trigger_emergency_stop(self, reason: str):
        """Trigger emergency stop - requires manual reset"""
        self.emergency_stop = True
        # This will be logged and alerted
        raise EmergencyStopError(f"EMERGENCY STOP: {reason}")
    
    def reset_emergency_stop(self):
        """Manual reset of emergency stop"""
        self.emergency_stop = False
        self.consecutive_errors = 0
    
    def get_status(self) -> dict:
        """Get current safety status"""
        return {
            'emergency_stop': self.emergency_stop,
            'consecutive_errors': self.consecutive_errors,
            'can_trade': not self.emergency_stop and self.consecutive_errors < self.max_consecutive_errors
        }

class EmergencyStopError(Exception):
    """Raised when emergency stop is triggered"""
    pass

# Global instance
safety_checker = SafetyChecker()
