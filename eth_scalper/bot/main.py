"""Main event loop for ETH scalper bot"""
import asyncio
import time
import sys
import os

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import validate_config, PAPER_TRADING_MODE, MIN_PROFIT_AFTER_GAS_PERCENT, ETH_ADDRESS, USDC_ADDRESS, WETH_ADDRESS, MAX_POSITION_USD, AUTO_MANUAL_BUY_FALLBACK_SECONDS
from config.logger import logger, log_signal, log_trade
from signals.price_feed import price_feed
from signals.momentum import momentum_detector
from execution.oneinch import inch_client
from execution.trade_manager import trade_manager
from execution.live_executor import live_executor
from risk.limits import risk_manager
from risk.safety_checks import safety_checker, EmergencyStopError
from state_manager import state_manager
from wallet_monitor import wallet_monitor

class ETHScalper:
    def __init__(self):
        self.running = False
        self.check_interval = 10  # Check for signals every 10 seconds
        self.last_stats_time = 0
        self.stats_interval = 300  # Print stats every 5 minutes
        self.last_gas_alert = 0
        self.last_heartbeat = 0
        self.heartbeat_interval = 300  # 5 minutes
        self.last_price = None
        self.price_change_alert_threshold = 0.5  # Alert on 0.5% moves
        self.last_dashboard_update = 0
        self.dashboard_update_interval = 5  # Update dashboard every 5 seconds
        self.last_forced_entry = 0
    
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
            self._update_dashboard(final=True)
    
    async def _tick(self):
        """Single iteration of the main loop"""
        now = time.time()
        
        # Check for dashboard commands
        command = state_manager.read_command()
        if command:
            await self._handle_command(command)
        
        # Update price feed
        current_price = price_feed.get_eth_price()
        
        # Check gas price for alerts
        await self._check_gas_alert()
        
        # Update dashboard periodically
        if now - self.last_dashboard_update > self.dashboard_update_interval:
            self._update_dashboard()
            self.last_dashboard_update = now
        
        # Send heartbeat/status update periodically
        if now - self.last_heartbeat > self.heartbeat_interval:
            await self._send_heartbeat()
            self.last_heartbeat = now
        
        # Alert on significant price moves even if not trading
        if current_price and self.last_price:
            price_change_pct = abs((current_price - self.last_price) / self.last_price * 100)
            if price_change_pct >= self.price_change_alert_threshold:
                await self._send_price_alert(current_price, price_change_pct)
        
        self.last_price = current_price
        
        # Check for momentum signals
        signal = momentum_detector.detect_momentum()

        if signal:
            await self._handle_signal(signal)
        elif (not PAPER_TRADING_MODE and now - self.last_forced_entry > AUTO_MANUAL_BUY_FALLBACK_SECONDS and len(trade_manager.get_open_positions()) == 0):
            print("⏰ No natural signal recently, forcing fallback live entry")
            self.last_forced_entry = now
            await self._manual_buy()
        
        # Print stats periodically
        if now - self.last_stats_time > self.stats_interval:
            self._print_stats()
            self.last_stats_time = now
    
    async def _handle_command(self, command: str):
        """Handle command from dashboard"""
        print(f"📩 Command received: {command}")
        
        if command == 'STOP':
            self.running = False
            print("🛑 Stopping bot via command")
        elif command == 'PAUSE':
            print("⏸️ Pausing trading")
        elif command == 'RESUME':
            print("▶️ Resuming trading")
        elif command == 'BUY':
            # Manual buy trigger
            await self._manual_buy()
    
    async def _manual_buy(self):
        """Execute manual buy"""
        current_price = price_feed.get_eth_price()
        if not current_price:
            print("❌ Cannot buy - no price data")
            return
        
        signal = {
            'timestamp': time.time(),
            'direction': 'up',
            'price': current_price,
            'change_60s_pct': 0,
            'gas_gwei': price_feed.get_gas_price_gwei() or 30,
            'score': 10,
            'type': 'manual'
        }
        
        print(f"🛒 MANUAL BUY triggered at ${current_price:.2f}")
        await self._handle_signal(signal)
    
    def _update_dashboard(self, final=False):
        """Update dashboard state files"""
        try:
            risk = risk_manager.get_status()
            trades = trade_manager.get_stats()
            rate = inch_client.get_rate_limit_status()
            
            status = 'stopped' if final else 'running'
            mode = 'paper' if PAPER_TRADING_MODE else 'live'
            
            # Update wallet state from live on-chain reads
            wallet = wallet_monitor.get_all_balances()
            weth_balance = wallet.get('weth', 0.0) if isinstance(wallet, dict) else 0.0
            inferred_open_positions = len(trade_manager.get_open_positions())
            live_inventory = {
                'eth': wallet.get('eth', 0.0),
                'weth': weth_balance,
                'usdc': wallet.get('usdc', 0.0),
                'has_live_weth_inventory': bool(weth_balance and weth_balance > 0),
            }
            tracked_positions = trade_manager.get_open_positions()
            if weth_balance and weth_balance > 0 and inferred_open_positions == 0:
                inferred_open_positions = 1
            reconciled_positions = state_manager.build_reconciled_positions(wallet, tracked_positions)

            state_manager.update_bot_state(
                status=status,
                pnl_today=risk['daily_pnl'],
                pnl_total=trades.get('total_pnl', 0),
                requests_used=rate['inch_requests_today'],
                daily_trades=risk['daily_trades'],
                open_positions=inferred_open_positions,
                available_capital=risk['available_capital'],
                mode=mode,
                live_inventory=live_inventory,
                reconciled_positions=reconciled_positions
            )
            
            # Update positions
            state_manager.update_positions(tracked_positions)
            state_manager.update_wallet(wallet)
            
        except Exception as e:
            print(f"Failed to update dashboard: {e}")
    
    async def _check_gas_alert(self):
        """Alert if gas is too high"""
        gas = price_feed.get_gas_price_gwei()
        if not gas:
            return
        
        if gas > 50:
            now = time.time()
            if now - self.last_gas_alert > 3600:  # Alert once per hour
                print(f"⚠️ Gas spike: {gas:.1f} gwei (>50)")
                self.last_gas_alert = now
    
    async def _handle_signal(self, signal: dict):
        """Handle a detected signal"""
        print(f"\n🔔 SIGNAL DETECTED")
        print(f"   Direction: {signal['direction'].upper()}")
        print(f"   Price: ${signal['price']:.2f}")
        print(f"   Change: {signal['change_60s_pct']:+.2f}%")
        print(f"   Score: {signal['score']}/10")
        
        # Log signal to dashboard
        state_manager.log_signal(signal, executed=False, reason="checking")
        
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
            state_manager.log_signal(signal, executed=False, reason=f"SAFETY: {reason}")
            return
        
        # Check risk limits
        can_trade, reason = risk_manager.can_trade(signal)
        
        if not can_trade:
            print(f"   ❌ Risk check failed: {reason}")
            state_manager.log_signal(signal, executed=False, reason=reason)
            return
        
        # Get 1inch quote for profit calculation
        from_token = ETH_ADDRESS
        to_token = USDC_ADDRESS
        
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
                state_manager.log_signal(signal, executed=False, reason="profit_too_low")
                return
        
        wallet = wallet_monitor.get_all_balances()
        size_usd = min(MAX_POSITION_USD, max(25.0, wallet.get('estimated_total_usd', 0.0) * 0.4))

        if not PAPER_TRADING_MODE:
            eth_balance_usd = wallet.get('eth', 0.0) * signal['price']
            usdc_balance = wallet.get('usdc', 0.0)
            funded_side = 'ETH' if eth_balance_usd >= 25.0 else ('USDC' if usdc_balance >= 25.0 else None)
            if funded_side is None:
                print(f"   ❌ Live wallet underfunded for entry: need at least $25 deployable, have ~${eth_balance_usd:.2f} ETH and ${usdc_balance:.2f} USDC")
                state_manager.log_signal(signal, executed=False, reason="wallet_underfunded")
                return
            size_usd = min(size_usd, eth_balance_usd if funded_side == 'ETH' else usdc_balance)
            signal['funded_side'] = funded_side

        # Log the signal as executed
        state_manager.log_signal(signal, executed=True, reason="passed_all_checks")

        # Create position
        position = trade_manager.create_position(signal, size_usd, paper=PAPER_TRADING_MODE)

        print(f"   📊 Position created: {position.id}")

        # Open position
        success = await trade_manager.open_position(position)

        if success:
            # Record in risk manager
            risk_manager.record_trade(signal, size_usd, paper=PAPER_TRADING_MODE)
            
            # Start monitoring
            trade_manager.start_monitoring(position.id, price_feed.get_eth_price)
            
            print(f"   ✅ Position opened: {position.id}")
            
            # Execute the actual swap
            if PAPER_TRADING_MODE:
                asyncio.create_task(self._monitor_paper_position(position.id))
            else:
                # Live trading - execute real swap
                asyncio.create_task(self._execute_live_trade(position))
        else:
            print(f"   ❌ Failed to open position")
    
    async def _execute_live_trade(self, position):
        """Execute live trade on-chain"""
        funded_side = position.signal.get('funded_side', 'ETH')
        if funded_side == 'USDC':
            from_token = USDC_ADDRESS
            to_token = WETH_ADDRESS
            amount_wei = int(position.size_usd * 1e6)
            print(f"   🔄 Getting swap quote for ${position.size_usd:.2f} USDC -> WETH...")
        else:
            from_token = ETH_ADDRESS
            to_token = USDC_ADDRESS
            amount_eth = position.size_usd / max(position.entry_price, 1)
            amount_wei = int(amount_eth * 1e18)
            print(f"   🔄 Getting swap quote for {amount_eth:.6f} ETH...")
        
        swap_data = live_executor.get_swap_data(
            from_token=from_token,
            to_token=to_token,
            amount=amount_wei
        )
        
        if not swap_data:
            print(f"   ❌ Failed to get swap quote")
            return
        
        print(f"   💰 Swap quote received, executing...")
        
        tx_hash = live_executor.execute_swap(swap_data)
        
        if tx_hash:
            position.tx_hash = tx_hash
            try:
                to_amount = swap_data.get('to_amount')
                dst_token = swap_data.get('dst_token')
                if to_amount is not None and dst_token == WETH_ADDRESS:
                    position.executed_to_amount_units = int(to_amount) / 1e18
            except Exception:
                position.executed_to_amount_units = None
            state_manager.persist_live_position(position)
            print(f"   ✅ SWAP EXECUTED: {tx_hash}")
            print(f"   🔗 View on Basescan: https://basescan.org/tx/{tx_hash}")
            
            # Monitor the trade
            asyncio.create_task(self._monitor_live_position(position))
        else:
            print(f"   ❌ Swap execution failed")
    
    async def _monitor_live_position(self, position):
        """Monitor live position and close when target/stop hit"""
        print(f"   👁️  Monitoring position {position.id}...")
        
        while True:
            current_price = price_feed.get_eth_price()
            if not current_price:
                await asyncio.sleep(5)
                continue
            
            # Check target hit
            if position.direction == 'long':
                if current_price >= position.target_price:
                    await self._close_live_position(position, current_price, "target_hit")
                    return
                if current_price <= position.stop_price:
                    await self._close_live_position(position, current_price, "stop_loss")
                    return
            else:  # short
                if current_price <= position.target_price:
                    await self._close_live_position(position, current_price, "target_hit")
                    return
                if current_price >= position.stop_price:
                    await self._close_live_position(position, current_price, "stop_loss")
                    return
            
            # Check timeout
            hold_time = time.time() - position.entry_time
            if hold_time > trade_manager.max_hold_time:
                await self._close_live_position(position, current_price, "timeout")
                return
            
            await asyncio.sleep(5)
    
    async def _close_live_position(self, position, current_price, reason):
        """Close live position and execute reverse swap"""
        print(f"   🔒 Closing position {position.id} - {reason}")
        
        # Calculate P&L
        if position.direction == 'long':
            price_change = (current_price - position.entry_price) / position.entry_price
        else:
            price_change = (position.entry_price - current_price) / position.entry_price
        
        pnl_pct = price_change * 100
        pnl_usd = position.size_usd * price_change
        
        # Execute reverse swap (WETH back to USDC)
        from execution.live_executor import live_executor
        from_token = WETH_ADDRESS
        to_token = USDC_ADDRESS

        executed_units = getattr(position, 'executed_to_amount_units', None)
        if executed_units is None or executed_units <= 0:
            print(f"   ❌ Exit blocked - no executed WETH units recorded for {position.id}")
            return
        sell_amount = int(executed_units * 1e18)

        swap_data = live_executor.get_swap_data(
            from_token=from_token,
            to_token=to_token,
            amount=sell_amount,
            enforce_semantic_unwind=True,
        )
        
        if not swap_data:
            print(f"   ❌ Exit blocked - no swap data returned")
            return {'closed': False, 'reason': 'no_swap_data'}

        tx_hash = live_executor.execute_swap(swap_data)
        if not tx_hash:
            print(f"   ❌ Exit blocked - sell swap failed")
            return {'closed': False, 'reason': 'swap_failed'}

        position.exit_tx_hash = tx_hash
        print(f"   ✅ EXIT SWAP: {tx_hash}")
        
        # Record the trade only after a real exit tx exists
        closed_position = await trade_manager.close_position(position.id, current_price, reason)
        
        if closed_position:
            state_manager.log_trade(
                position=closed_position,
                exit_price=current_price,
                pnl_usd=pnl_usd,
                pnl_pct=pnl_pct,
                gas_cost=2.0,  # Approximate
                reason=reason
            )
            
            print(f"   💰 Trade complete: ${pnl_usd:+.2f} ({pnl_pct:+.2f}%)")
            return {'closed': True, 'tx_hash': tx_hash, 'pnl_usd': pnl_usd, 'pnl_pct': pnl_pct}
        return {'closed': False, 'reason': 'close_position_failed'}
    
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
                print(f"   📝 Paper trade complete: ${hist_pos.pnl_usd:+.2f}")
                break
    
    async def _send_heartbeat(self):
        """Send periodic status update"""
        stats = price_feed.get_price_stats()
        risk = risk_manager.get_status()
        trades = trade_manager.get_stats()
        wallet = wallet_monitor.get_all_balances()
        
        eth_price = stats['current_price']
        change_60s = stats['change_60s_pct'] or 0
        gas = stats['gas_gwei'] or 0
        
        emoji = "🟢" if change_60s >= 0 else "🔴"
        
        print(f"\n💓 HEARTBEAT")
        print(f"   {emoji} ETH: ${eth_price:.2f} ({change_60s:+.2f}% / 60s)")
        print(f"   ⛽ Gas: {gas:.1f} gwei")
        print(f"   💰 Daily P&L: ${risk['daily_pnl']:+.2f}")
        print(f"   📊 Trades: {risk['daily_trades']} today, {trades['total_trades']} total")
        print(f"   🎯 Open: {risk['open_positions']}")
        print(f"   💵 Wallet: {wallet['eth']:.4f} ETH, ${wallet['usdc']:.2f} USDC")
    
    async def _send_price_alert(self, current_price: float, change_pct: float):
        """Send alert on significant price movement"""
        direction = "📈 UP" if current_price > self.last_price else "📉 DOWN"
        print(f"\n{direction} Price Alert: ${current_price:.2f} ({change_pct:.2f}%)")
    
    def _print_stats(self):
        """Print current statistics"""
        risk = risk_manager.get_status()
        momentum = momentum_detector.get_stats()
        rate = inch_client.get_rate_limit_status()
        trades = trade_manager.get_stats()
        wallet = wallet_monitor.get_all_balances()
        
        print("\n" + "=" * 60)
        print("📊 STATS")
        print("=" * 60)
        print(f"Daily P&L: ${risk['daily_pnl']:+.2f} / ${risk['daily_loss_limit']:.2f} limit")
        print(f"Daily Trades: {risk['daily_trades']}")
        print(f"Open Positions: {risk['open_positions']}")
        print(f"Available Capital: ${risk['available_capital']:.2f}")
        print(f"Wallet: {wallet['eth']:.4f} ETH, ${wallet['usdc']:.2f} USDC")
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
