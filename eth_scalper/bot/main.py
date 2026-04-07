"""Main event loop for ETH scalper bot"""
import asyncio
import time
import sys
import os

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import validate_config, PAPER_TRADING_MODE, MIN_PROFIT_AFTER_GAS_PERCENT
from config.logger import logger, log_signal, log_trade
from signals.price_feed import price_feed
from signals.momentum import momentum_detector
from execution.oneinch import inch_client
from execution.trade_manager import trade_manager
from execution.live_executor import live_executor
from risk.limits import risk_manager
from risk.safety_checks import safety_checker, EmergencyStopError
from bot.telegram_bot import trading_bot

class ETHScalper:
    def __init__(self):
        self.running = False
        self.check_interval = 10  # Check for signals every 10 seconds
        self.last_stats_time = 0
        self.stats_interval = 300  # Print stats every 5 minutes
        self.last_gas_alert = 0
    
    async def run(self):
        """Main event loop"""
        print("=" * 60)
        print("🤖 ETH SCALPER BOT")
        print("=" * 60)
        
        # Validate config
        try:
            validate_config()
            print("✅ Config validated")
        except ValueError as e:
            print(f"❌ Config error: {e}")
            return
        
        # Start Telegram bot
        await trading_bot.start()
        
        mode = "PAPER TRADING" if PAPER_TRADING_MODE else "LIVE TRADING"
        print(f"📝 Mode: {mode}")
        print(f"⏱️  Check interval: {self.check_interval}s")
        
        if not PAPER_TRADING_MODE:
            print("⚠️  LIVE TRADING MODE - REAL MONEY AT RISK")
            print("   Safety checks: ENABLED")
            print("   Emergency stop: ARMED")
            live_executor.enable()
        
        print("-" * 60)
        
        self.running = True
        
        try:
            while self.running:
                await self._tick()
                await asyncio.sleep(self.check_interval)
        except KeyboardInterrupt:
            print("\n🛑 Stopping bot...")
        finally:
            await trading_bot.stop()
    
    async def _tick(self):
        """Single iteration of the main loop"""
        # Check if bot is paused
        if trading_bot.bot_paused:
            return
        
        # Update price feed
        price_feed.get_eth_price()
        
        # Check gas price for alerts
        await self._check_gas_alert()
        
        # Check for momentum signals
        signal = momentum_detector.detect_momentum()
        
        if signal:
            await self._handle_signal(signal)
        
        # Print stats periodically
        now = time.time()
        if now - self.last_stats_time > self.stats_interval:
            self._print_stats()
            self.last_stats_time = now
    
    async def _check_gas_alert(self):
        """Alert if gas is too high"""
        gas = price_feed.get_gas_price_gwei()
        if not gas:
            return
        
        if gas > 50:
            now = time.time()
            if now - self.last_gas_alert > 3600:  # Alert once per hour
                await trading_bot.send_alert(f"⚠️ Gas spike: {gas:.1f} gwei (>50)")
                self.last_gas_alert = now
    
    async def _handle_signal(self, signal: dict):
        """Handle a detected signal"""
        print(f"\n🔔 SIGNAL DETECTED")
        print(f"   Direction: {signal['direction'].upper()}")
        print(f"   Price: ${signal['price']:.2f}")
        print(f"   Change: {signal['change_60s_pct']:+.2f}%")
        print(f"   Score: {signal['score']}/10")
        
        # CRITICAL: Safety check first
        open_positions = len(trade_manager.get_open_positions())
        risk_status = risk_manager.get_status()
        
        can_trade, reason = safety_checker.pre_trade_check(
            signal=signal,
            open_positions=open_positions,
            daily_pnl=risk_status['daily_pnl'],
            daily_trades=risk_status['daily_trades']
        )
        
        if not can_trade:
            print(f"   ❌ SAFETY CHECK FAILED: {reason}")
            log_signal(signal, executed=False, reason=f"SAFETY: {reason}")
            return
        
        # Check risk limits
        can_trade, reason = risk_manager.can_trade(signal)
        
        if not can_trade:
            print(f"   ❌ Risk check failed: {reason}")
            log_signal(signal, executed=False, reason=reason)
            return
        
        # Get 1inch quote for profit calculation
        from_token = '0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE'  # ETH
        to_token = '0xA0b86a33E6441e0A421e56E4773C3C4b0Db7E5b0'  # USDC
        
        # Check profit potential
        profit = inch_client.calculate_profit_potential(
            from_token=from_token,
            to_token=to_token,
            amount_usd=50,  # Test with $50
            current_price=signal['price']
        )
        
        if profit:
            print(f"   💰 Profit potential: {profit['net_profit_pct']:+.2f}%")
            
            # Only trade if profitable after gas
            if profit['net_profit_pct'] < MIN_PROFIT_AFTER_GAS_PERCENT:
                print(f"   ❌ Not profitable enough after gas")
                log_signal(signal, executed=False, reason="profit_too_low")
                return
        
        # Log the signal
        log_signal(signal, executed=True)
        
        # Create position
        position = trade_manager.create_position(signal, 50, paper=PAPER_TRADING_MODE)
        
        # Send alert
        await trading_bot.send_signal_alert(signal, paper=PAPER_TRADING_MODE)
        
        # Open position
        success = await trade_manager.open_position(position)
        
        if success:
            # Record in risk manager
            risk_manager.record_trade(signal, 50, paper=PAPER_TRADING_MODE)
            
            # Start monitoring
            trade_manager.start_monitoring(position.id, price_feed.get_eth_price)
            
            print(f"   ✅ Position opened: {position.id}")
            
            # For paper trading, auto-execute
            if PAPER_TRADING_MODE:
                asyncio.create_task(self._monitor_paper_position(position.id))
            else:
                # Live trading - prepare swap
                asyncio.create_task(self._prepare_live_swap(position))
        else:
            print(f"   ❌ Failed to open position")
    
    async def _prepare_live_swap(self, position):
        """Prepare swap data for live execution"""
        from_token = '0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE'  # ETH
        to_token = '0xA0b86a33E6441e0A421e56E4773C3C4b0Db7E5b0'  # USDC
        
        # Calculate amount (0.03 ETH ~ $75 at $2500/ETH)
        amount_eth = 0.03
        amount_wei = int(amount_eth * 1e18)
        
        swap_data = live_executor.get_swap_data(
            from_token=from_token,
            to_token=to_token,
            amount=amount_wei
        )
        
        if swap_data:
            tx_hash = live_executor.execute_swap(swap_data)
            if tx_hash:
                position.tx_hash = tx_hash
                print(f"   💰 Swap ready: {tx_hash}")
                await trading_bot.send_alert(
                    f"🎯 SWAP READY\n"
                    f"Position: {position.id}\n"
                    f"Amount: {amount_eth} ETH\n"
                    f"Check logs for tx data"
                )
    
    async def _monitor_paper_position(self, position_id: str):
        """Monitor paper position and report result"""
        # Wait for position to close
        while True:
            position = trade_manager.get_position(position_id)
            if not position or position.status.value == 'closed':
                break
            await asyncio.sleep(5)
        
        # Find in history
        for hist_pos in trade_manager.trade_history:
            if hist_pos.id == position_id:
                result = {
                    'position': {
                        'entry_price': hist_pos.entry_price,
                        'size_usd': hist_pos.size_usd
                    },
                    'exit_price': hist_pos.exit_price,
                    'pnl_usd': hist_pos.pnl_usd,
                    'pnl_pct': hist_pos.pnl_pct,
                    'gas_cost_usd': hist_pos.gas_cost_usd,
                    'paper': hist_pos.paper
                }
                await trading_bot.send_trade_result(result)
                break
    
    def _print_stats(self):
        """Print current statistics"""
        risk = risk_manager.get_status()
        momentum = momentum_detector.get_stats()
        rate = inch_client.get_rate_limit_status()
        trades = trade_manager.get_stats()
        
        print("\n" + "=" * 60)
        print("📊 STATS")
        print("=" * 60)
        print(f"Daily P&L: ${risk['daily_pnl']:+.2f} / ${risk['daily_loss_limit']:.2f} limit")
        print(f"Daily Trades: {risk['daily_trades']}")
        print(f"Open Positions: {risk['open_positions']}")
        print(f"Available Capital: ${risk['available_capital']:.2f}")
        print(f"Recent Win Rate: {momentum['recent_win_rate']:.1%}")
        print(f"1inch Requests: {rate['inch_requests_today']}/{rate['inch_limit']}")
        print(f"Total Trades: {trades['total_trades']}")
        print(f"Trade Win Rate: {trades['win_rate']:.1%}")
        print("=" * 60)

def main():
    """Entry point"""
    bot = ETHScalper()
    asyncio.run(bot.run())

if __name__ == '__main__':
    main()
