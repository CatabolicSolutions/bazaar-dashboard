"""Trade manager - position tracking, execution, monitoring"""
import time
import asyncio
from typing import Dict, Optional, List
from dataclasses import dataclass, field
from enum import Enum

class PositionStatus(Enum):
    PENDING = "pending"
    OPEN = "open"
    CLOSING = "closing"
    CLOSED = "closed"
    FAILED = "failed"

@dataclass
class Position:
    id: str
    signal: Dict
    entry_price: float
    size_usd: float
    direction: str  # 'long' or 'short'
    status: PositionStatus = PositionStatus.PENDING
    entry_time: float = field(default_factory=time.time)
    exit_price: Optional[float] = None
    exit_time: Optional[float] = None
    pnl_usd: float = 0.0
    pnl_pct: float = 0.0
    gas_cost_eth: float = 0.0
    gas_cost_usd: float = 0.0
    tx_hash: Optional[str] = None
    exit_tx_hash: Optional[str] = None
    target_price: float = 0.0
    stop_price: float = 0.0
    paper: bool = True

class TradeManager:
    def __init__(self):
        self.positions: Dict[str, Position] = {}
        self.position_counter = 0
        self.trade_history: List[Position] = []
        self.max_history = 100
        self.active_monitors: Dict[str, asyncio.Task] = {}
        
        # Exit parameters
        self.default_target_pct = 0.5  # 0.5% profit target
        self.default_stop_pct = 0.3    # 0.3% stop loss
        self.max_hold_time = 300       # 5 minutes max hold
    
    def create_position(self, signal: Dict, size_usd: float, paper: bool = True) -> Position:
        """Create a new position from signal"""
        self.position_counter += 1
        position_id = f"pos_{self.position_counter}_{int(time.time())}"
        
        # Calculate target and stop prices
        entry = signal['price']
        direction = 'long' if signal['direction'] == 'up' else 'short'
        
        if direction == 'long':
            target = entry * (1 + self.default_target_pct / 100)
            stop = entry * (1 - self.default_stop_pct / 100)
        else:
            target = entry * (1 - self.default_target_pct / 100)
            stop = entry * (1 + self.default_stop_pct / 100)
        
        position = Position(
            id=position_id,
            signal=signal,
            entry_price=entry,
            size_usd=size_usd,
            direction=direction,
            target_price=target,
            stop_price=stop,
            paper=paper
        )
        
        self.positions[position_id] = position
        return position
    
    async def open_position(self, position: Position) -> bool:
        """Execute entry trade - NOTE: Actual swap execution is handled by ETHScalper._execute_live_trade"""
        position.status = PositionStatus.OPEN
        
        if position.paper:
            # Paper trade - just log it
            print(f"📝 Paper position opened: {position.id}")
            print(f"   Entry: ${position.entry_price:.2f}")
            print(f"   Target: ${position.target_price:.2f}")
            print(f"   Stop: ${position.stop_price:.2f}")
            return True
        else:
            # Live trade - swap execution is handled by the bot's _execute_live_trade method
            # This method just marks the position as open for tracking
            print(f"💰 Live position opening: {position.id}")
            print(f"   Entry: ${position.entry_price:.2f}")
            print(f"   Target: ${position.target_price:.2f}")
            print(f"   Stop: ${position.stop_price:.2f}")
            return True
    
    async def close_position(self, position_id: str, current_price: float, reason: str = "target") -> Optional[Position]:
        """Close a position"""
        if position_id not in self.positions:
            return None
        
        position = self.positions[position_id]
        position.status = PositionStatus.CLOSING
        position.exit_time = time.time()
        position.exit_price = current_price
        
        # Calculate P&L
        if position.direction == 'long':
            price_change = (current_price - position.entry_price) / position.entry_price
        else:
            price_change = (position.entry_price - current_price) / position.entry_price
        
        position.pnl_pct = price_change * 100
        position.pnl_usd = position.size_usd * price_change
        
        # Estimate gas cost
        position.gas_cost_usd = 2.0  # Approximate
        position.pnl_usd -= position.gas_cost_usd
        
        position.status = PositionStatus.CLOSED
        
        # Move to history
        self.trade_history.append(position)
        if len(self.trade_history) > self.max_history:
            self.trade_history.pop(0)
        
        del self.positions[position_id]
        
        # Cancel monitor if running
        if position_id in self.active_monitors:
            self.active_monitors[position_id].cancel()
            del self.active_monitors[position_id]
        
        print(f"{'📝' if position.paper else '💰'} Position closed: {position.id}")
        print(f"   Reason: {reason}")
        print(f"   P&L: ${position.pnl_usd:+.2f} ({position.pnl_pct:+.2f}%)")
        
        return position
    
    async def monitor_position(self, position_id: str, price_feed_func):
        """Monitor a position for exit conditions"""
        if position_id not in self.positions:
            return
        
        position = self.positions[position_id]
        
        try:
            while position.status == PositionStatus.OPEN:
                current_price = price_feed_func()
                if not current_price:
                    await asyncio.sleep(5)
                    continue
                
                # Check target hit
                if position.direction == 'long':
                    if current_price >= position.target_price:
                        await self.close_position(position_id, current_price, "target_hit")
                        return
                    if current_price <= position.stop_price:
                        await self.close_position(position_id, current_price, "stop_loss")
                        return
                else:  # short
                    if current_price <= position.target_price:
                        await self.close_position(position_id, current_price, "target_hit")
                        return
                    if current_price >= position.stop_price:
                        await self.close_position(position_id, current_price, "stop_loss")
                        return
                
                # Check timeout
                hold_time = time.time() - position.entry_time
                if hold_time > self.max_hold_time:
                    await self.close_position(position_id, current_price, "timeout")
                    return
                
                await asyncio.sleep(5)  # Check every 5 seconds
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Error monitoring position {position_id}: {e}")
    
    def start_monitoring(self, position_id: str, price_feed_func):
        """Start monitoring task for a position"""
        task = asyncio.create_task(
            self.monitor_position(position_id, price_feed_func)
        )
        self.active_monitors[position_id] = task
    
    def get_open_positions(self) -> List[Position]:
        """Get all open positions"""
        return [p for p in self.positions.values() if p.status == PositionStatus.OPEN]
    
    def get_position(self, position_id: str) -> Optional[Position]:
        """Get a specific position"""
        return self.positions.get(position_id)
    
    def get_stats(self) -> Dict:
        """Get trading statistics"""
        closed = [p for p in self.trade_history if p.status == PositionStatus.CLOSED]
        
        if not closed:
            return {
                'total_trades': 0,
                'win_rate': 0.0,
                'avg_pnl': 0.0,
                'total_pnl': 0.0,
                'open_positions': len(self.get_open_positions())
            }
        
        wins = sum(1 for p in closed if p.pnl_usd > 0)
        total_pnl = sum(p.pnl_usd for p in closed)
        
        return {
            'total_trades': len(closed),
            'win_rate': wins / len(closed),
            'avg_pnl': total_pnl / len(closed),
            'total_pnl': total_pnl,
            'open_positions': len(self.get_open_positions())
        }

# Global instance
trade_manager = TradeManager()
