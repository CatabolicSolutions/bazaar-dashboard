"""Main event loop for ETH scalper bot"""
import asyncio
import time
import sys
import os

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import validate_config, PAPER_TRADING_MODE
from signals.price_feed import price_feed
from signals.momentum import momentum_detector
from execution.oneinch import inch_client
from risk.limits import risk_manager
from bot.telegram_bot import trading_bot

class ETHScalper:
    def __init__(self):
        self.running = False
        self.check_interval = 10  # Check for signals every 10 seconds
        self.last_stats_time = 0
        self.stats_interval = 300  # Print stats every 5 minutes
    
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
        # Update price feed
        price_feed.get_eth_price()
        
        # Check for momentum signals
        signal = momentum_detector.detect_momentum()
        
        if signal:
            await self._handle_signal(signal)
        
        # Print stats periodically
        now = time.time()
        if now - self.last_stats_time > self.stats_interval:
            self._print_stats()
            self.last_stats_time = now
    
    async def _handle_signal(self, signal: dict):
        """Handle a detected signal"""
        print(f"\n🔔 SIGNAL DETECTED")
        print(f"   Direction: {signal['direction'].upper()}")
        print(f"   Price: ${signal['price']:.2f}")
        print(f"   Change: {signal['change_60s_pct']:+.2f}%")
        print(f"   Score: {signal['score']}/10")
        
        # Check risk limits
        can_trade, reason = risk_manager.can_trade(signal)
        
        if not can_trade:
            print(f"   ❌ Risk check failed: {reason}")
            return
        
        # Get 1inch quote for profit calculation
        # For ETH scalping, we check if the move is profitable after gas
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
            if profit['net_profit_pct'] < 0.5:
                print(f"   ❌ Not profitable enough after gas")
                return
        
        # Send alert
        await trading_bot.send_signal_alert(signal, paper=PAPER_TRADING_MODE)
        
        if PAPER_TRADING_MODE:
            # Paper trade - just log it
            position = risk_manager.record_trade(signal, 50, paper=True)
            print(f"   📝 Paper trade recorded")
            
            # Simulate exit after 5 minutes for paper trading
            asyncio.create_task(self._simulate_paper_exit(position, 300))
        else:
            # Live trading - would execute here
            # TODO: Implement actual execution
            print(f"   💰 Live execution would happen here")
    
    async def _simulate_paper_exit(self, position: dict, delay: int):
        """Simulate paper trade exit after delay"""
        await asyncio.sleep(delay)
        
        # Get current price
        current_price = price_feed.get_eth_price()
        if not current_price:
            return
        
        # Close position
        result = risk_manager.close_position(
            pair=risk_manager._get_pair_key(position['signal']),
            exit_price=current_price,
            paper=True
        )
        
        if result:
            print(f"\n📝 Paper trade closed: ${result['pnl_usd']:+.2f}")
            await trading_bot.send_trade_result(result)
    
    def _print_stats(self):
        """Print current statistics"""
        risk = risk_manager.get_status()
        momentum = momentum_detector.get_stats()
        rate = inch_client.get_rate_limit_status()
        
        print("\n" + "=" * 60)
        print("📊 STATS")
        print("=" * 60)
        print(f"Daily P&L: ${risk['daily_pnl']:+.2f} / ${risk['daily_loss_limit']:.2f} limit")
        print(f"Daily Trades: {risk['daily_trades']}")
        print(f"Open Positions: {risk['open_positions']}")
        print(f"Available Capital: ${risk['available_capital']:.2f}")
        print(f"Recent Win Rate: {momentum['recent_win_rate']:.1%}")
        print(f"1inch Requests: {rate['inch_requests_today']}/{rate['inch_limit']}")
        print("=" * 60)

def main():
    """Entry point"""
    bot = ETHScalper()
    asyncio.run(bot.run())

if __name__ == '__main__':
    main()
