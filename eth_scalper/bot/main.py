"""Main event loop for ETH scalper bot"""
import asyncio
import time
import sys
import os
from pathlib import Path

# Add package roots to path for both local runs and systemd `/usr/bin/python3 -m bot.main`
BOT_DIR = Path(__file__).resolve().parent
ROOT_DIR = BOT_DIR.parent
PACKAGE_PARENT = ROOT_DIR.parent
for candidate in (str(ROOT_DIR), str(PACKAGE_PARENT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from config.settings import validate_config, PAPER_TRADING_MODE, MIN_PROFIT_AFTER_GAS_PERCENT, ETH_ADDRESS, USDC_ADDRESS, WETH_ADDRESS, CBBTC_ADDRESS, MAX_POSITION_USD, AUTO_MANUAL_BUY_FALLBACK_SECONDS, BLOC_MIN_NET_PROFIT_PCT, BLOC_MIN_LIQUIDITY_USD
from config.logger import logger, log_signal, log_trade
from signals.price_feed import price_feed
from signals.momentum import momentum_detector
from signals.multi_asset_feed import multi_asset_feed
from execution.oneinch import inch_client
from execution.trade_manager import trade_manager
from execution.live_executor import live_executor
def emit_event(**kwargs):
    return kwargs
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
            await self._resume_persisted_live_positions()
        
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

        eth_prices = multi_asset_feed.get_prices()
        eth_history = multi_asset_feed.price_history.get('ETH', [])
        eth_mid = sum(p for _, p in eth_history[-12:]) / max(1, len(eth_history[-12:])) if eth_history else eth_prices.get('ETH')
        eth_cur = eth_prices.get('ETH')
        if eth_cur is not None and eth_mid is not None:
            print(f"   📏 ETH midpoint check: current=${eth_cur:.2f}, midpoint=${eth_mid:.2f}, at_or_below_mid={eth_cur <= eth_mid}")

        if signal:
            await self._handle_signal(signal)
        elif (eth_cur is not None and eth_mid is not None and eth_cur <= eth_mid and len(trade_manager.get_open_positions()) == 0):
            print("🎯 Natural midline buy condition met, forcing immediate buy_pullback handling")
            mid_signal = {
                'timestamp': time.time(),
                'symbol': 'ETH',
                'direction': 'down',
                'price': eth_cur,
                'change_60s_pct': 0.0,
                'gas_gwei': price_feed.get_gas_price_gwei() or 0.0,
                'score': 10,
                'type': 'midline_buy',
                'setup': 'buy_pullback',
                'midpoint_price': eth_mid,
                'distance_from_mid_pct': abs(((eth_cur - eth_mid) / eth_mid) * 100) if eth_mid else 0.0,
                'pullback_bias': True,
                'sell_strength_bias': False,
            }
            await self._handle_signal(mid_signal)
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
        
        change_60s = 0.0
        history = list(getattr(price_feed, 'eth_price_history', []) or [])
        if len(history) >= 2:
            now_ts = time.time()
            target_ts = now_ts - 60
            current_px = history[-1][1]
            nearest = min(history, key=lambda item: abs(item[0] - target_ts))
            prior_px = nearest[1]
            if prior_px:
                change_60s = ((current_px - prior_px) / prior_px) * 100
        if abs(change_60s) < 0.10:
            print(f"   ❌ Manual fallback skipped: insufficient real move ({change_60s:+.4f}% / 60s)")
            return

        signal = {
            'timestamp': time.time(),
            'symbol': 'ETH',
            'direction': 'down' if change_60s < 0 else 'up',
            'price': current_price,
            'change_60s_pct': change_60s,
            'gas_gwei': price_feed.get_gas_price_gwei() or 30,
            'score': 10,
            'type': 'manual',
            'setup': 'buy_pullback' if change_60s < 0 else 'sell_strength',
            'pullback_bias': change_60s < 0,
            'sell_strength_bias': change_60s > 0,
            'distance_from_mid_pct': abs(change_60s),
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

            deployable_capital = float(wallet.get('usdc', 0.0) or 0.0)
            state_manager.update_bot_state(
                status=status,
                pnl_today=risk['daily_pnl'],
                pnl_total=trades.get('total_pnl', 0),
                requests_used=rate['inch_requests_today'],
                daily_trades=risk['daily_trades'],
                open_positions=inferred_open_positions,
                available_capital=deployable_capital,
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
        print(f"   Asset: {signal.get('symbol', 'ETH')}")
        print(f"   Direction: {signal['direction'].upper()}")
        print(f"   Price: ${signal['price']:.2f}")
        print(f"   Change: {signal['change_60s_pct']:+.2f}%")
        print(f"   Score: {signal['score']}/10")
        
        trade_id = f"bloc-{int(time.time()*1000)}"
        emit_event(engine='bloc_1inch', trade_id=trade_id, position_id=None, stage='detected', outcome_type='info', status='success', setup_type=signal.get('type'), data={'signal': signal})
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
            emit_event(engine='bloc_1inch', trade_id=trade_id, position_id=None, stage='rejected', outcome_type='rejected_setup', status='failure', setup_type=signal.get('type'), notes=reason)
            state_manager.log_signal(signal, executed=False, reason=f"SAFETY: {reason}")
            return
        
        # Check risk limits
        can_trade, reason = risk_manager.can_trade(signal)
        
        if not can_trade:
            print(f"   ❌ Risk check failed: {reason}")
            emit_event(engine='bloc_1inch', trade_id=trade_id, position_id=None, stage='rejected', outcome_type='rejected_setup', status='failure', setup_type=signal.get('type'), notes=reason)
            state_manager.log_signal(signal, executed=False, reason=reason)
            return
        
        # Sprint-grade economic gate is applied after inventory selection so it evaluates the real funded path.
        
        wallet = wallet_monitor.get_all_balances()
        estimated_total_usd = wallet.get('estimated_total_usd', 0.0)
        size_usd = min(MAX_POSITION_USD, max(1.0, estimated_total_usd * 0.4))

        if not PAPER_TRADING_MODE:
            native_eth_balance = wallet.get('eth', 0.0)
            native_eth_usd = native_eth_balance * signal['price']
            weth_balance = wallet.get('weth', 0.0)
            weth_balance_usd = weth_balance * signal['price']
            usdc_balance = wallet.get('usdc', 0.0)

            target_asset = signal.get('symbol', 'ETH')
            if target_asset == 'ETH' and weth_balance_usd >= 1.0:
                resumed = await self._resume_persisted_live_positions()
                if resumed:
                    print(f"   🧭 Existing WETH exposure detected and resumed into active monitoring")
                    state_manager.log_signal(signal, executed=False, reason="existing_weth_exposure_resumed")
                    return
                print(f"   🧭 Existing WETH exposure detected: ${weth_balance_usd:.2f} inventory. Treating as managed compounding inventory and seeking exit/recycle conditions.")
                synthetic_position = trade_manager.create_position({
                    'timestamp': time.time(),
                    'direction': 'up',
                    'price': signal['price'],
                    'type': 'inventory_reconciliation',
                    'symbol': 'ETH',
                }, weth_balance_usd, paper=False)
                synthetic_position.entry_price = signal['price']
                synthetic_position.target_price = signal['price'] * (1 + BLOC_MIN_NET_PROFIT_PCT / 100)
                synthetic_position.stop_price = signal['price'] * (1 - 0.10 / 100)
                synthetic_position.executed_to_amount_units = weth_balance
                synthetic_position.source = 'inventory_reconciliation'
                synthetic_position.resumable_after_restart = True
                synthetic_position.max_hold_seconds = trade_manager.max_hold_time
                synthetic_position.status = synthetic_position.status.OPEN
                trade_manager.positions[synthetic_position.id] = synthetic_position
                state_manager.persist_live_position(synthetic_position)
                state_manager.update_positions(trade_manager.get_open_positions())
                print(f"   ✅ Promoted orphan WETH inventory into managed live position: {synthetic_position.id}")
                asyncio.create_task(self._monitor_live_position(synthetic_position))
                state_manager.log_signal(signal, executed=False, reason="existing_weth_inventory_promoted_to_managed_position")
                return

            if usdc_balance >= BLOC_MIN_LIQUIDITY_USD:
                funded_side = 'USDC'
                size_usd = usdc_balance
            elif native_eth_usd >= 25.0:
                funded_side = 'ETH'
                size_usd = min(MAX_POSITION_USD, 40.0, native_eth_usd)
            elif usdc_balance >= 1.0:
                funded_side = 'USDC'
                size_usd = min(MAX_POSITION_USD, usdc_balance)
            elif native_eth_usd >= 1.0:
                funded_side = 'ETH'
                size_usd = min(MAX_POSITION_USD, native_eth_usd)
            else:
                funded_side = None

            if funded_side is None:
                print(f"   ❌ Live wallet underfunded for entry: need deployable inventory, have ~${native_eth_usd:.2f} native ETH, ${usdc_balance:.2f} USDC, ${weth_balance_usd:.2f} WETH inventory")
                emit_event(engine='bloc_1inch', trade_id=trade_id, position_id=None, stage='rejected', outcome_type='rejected_setup', status='failure', setup_type=signal.get('type'), notes='wallet_underfunded')
                state_manager.log_signal(signal, executed=False, reason="wallet_underfunded")
                return
            signal['funded_side'] = funded_side
            signal['native_eth_balance'] = native_eth_balance
            signal['native_eth_usd'] = native_eth_usd
            signal['weth_inventory_usd'] = weth_balance_usd
            signal['tradable_usdc_side_usd'] = usdc_balance
            signal['selected_inventory'] = funded_side
            signal['selected_size_usd'] = size_usd

            # All-in compounding gate for meaningful USDC-funded ETH/USDC attempts
            has_open_position = len(trade_manager.get_open_positions()) > 0
            if has_open_position:
                emit_event(engine='bloc_1inch', trade_id=trade_id, position_id=None, stage='rejected', outcome_type='rejected_setup', status='failure', setup_type=signal.get('type'), notes='open_position_exists')
                state_manager.log_signal(signal, executed=False, reason='open_position_exists')
                return
            if funded_side != 'USDC':
                emit_event(engine='bloc_1inch', trade_id=trade_id, position_id=None, stage='rejected', outcome_type='rejected_setup', status='failure', setup_type=signal.get('type'), notes='usdc_inventory_required_for_redeployment')
                state_manager.log_signal(signal, executed=False, reason='usdc_inventory_required_for_redeployment')
                return
            if size_usd < BLOC_MIN_LIQUIDITY_USD:
                emit_event(engine='bloc_1inch', trade_id=trade_id, position_id=None, stage='rejected', outcome_type='rejected_setup', status='failure', setup_type=signal.get('type'), notes='insufficient_exit_liquidity')
                state_manager.log_signal(signal, executed=False, reason='insufficient_exit_liquidity')
                return

            base_token = WETH_ADDRESS if signal.get('symbol', 'ETH') == 'ETH' else CBBTC_ADDRESS
            print(f"   🔎 Requesting quote: size=${size_usd:.2f}, base_token={base_token}, usdc_balance=${usdc_balance:.2f}")
            quote = inch_client.get_quote(USDC_ADDRESS, base_token, int(size_usd * 1e6), use_cache=False)
            print(f"   🔎 Quote returned: {'yes' if quote else 'no'}")
            if not quote:
                print("   ❌ Rejected: missing_quote")
                emit_event(engine='bloc_1inch', trade_id=trade_id, position_id=None, stage='rejected', outcome_type='rejected_setup', status='failure', setup_type=signal.get('type'), notes='missing_quote')
                state_manager.log_signal(signal, executed=False, reason='missing_quote')
                return
            quote_age_seconds = max(0.0, time.time() - inch_client.last_quote_time)
            if quote_age_seconds > 5.0:
                print(f"   ❌ Rejected: quote_stale ({quote_age_seconds:.2f}s)")
                emit_event(engine='bloc_1inch', trade_id=trade_id, position_id=None, stage='rejected', outcome_type='rejected_setup', status='failure', setup_type=signal.get('type'), notes='quote_stale')
                state_manager.log_signal(signal, executed=False, reason='quote_stale')
                return

            decimals = 18 if signal.get('symbol', 'ETH') == 'ETH' else 8
            quoted_units = int(quote.get('toAmount', 0)) / (10 ** decimals)
            quoted_out_usd = quoted_units * signal['price']
            gross_edge_pct = abs(signal.get('distance_from_mid_pct') or signal.get('change_60s_pct') or 0.0)
            estimated_gas_units = int(quote.get('estimatedGas', 150000) or 150000)
            gas_cost_usd = ((estimated_gas_units * max(wallet.get('gas') or 0.006, 0.006) * 1e9) / 1e18) * max(price_feed.get_eth_price() or 2200.0, 1.0)
            friction_pct = (gas_cost_usd / size_usd) * 100 if size_usd > 0 else 999.0
            expected_edge_pct = gross_edge_pct - friction_pct
            print(f"   🔎 Quote analytics: quoted_units={quoted_units:.8f}, quoted_out_usd=${quoted_out_usd:.2f}, gross_edge={gross_edge_pct:.4f}%, friction={friction_pct:.4f}%, expected_edge={expected_edge_pct:.4f}%")
            signal['quote_age_seconds'] = quote_age_seconds
            signal['gross_edge_pct'] = gross_edge_pct
            signal['expected_edge_pct'] = expected_edge_pct
            signal['estimated_gas_units'] = estimated_gas_units
            signal['estimated_gas_usd'] = gas_cost_usd
            signal['estimated_friction_pct'] = friction_pct
            signal['quoted_out_usd'] = quoted_out_usd

            if friction_pct >= gross_edge_pct:
                print(f"   ❌ Rejected: friction_exceeds_edge (friction={friction_pct:.4f}%, gross_edge={gross_edge_pct:.4f}%)")
                emit_event(engine='bloc_1inch', trade_id=trade_id, position_id=None, stage='rejected', outcome_type='rejected_setup', status='failure', setup_type=signal.get('type'), notes='friction_exceeds_edge', data={'friction_pct': friction_pct, 'gross_edge_pct': gross_edge_pct})
                state_manager.log_signal(signal, executed=False, reason='friction_exceeds_edge')
                return
            if expected_edge_pct < BLOC_MIN_NET_PROFIT_PCT:
                print(f"   ❌ Rejected: edge_below_net_target (expected_edge={expected_edge_pct:.4f}%, target={BLOC_MIN_NET_PROFIT_PCT:.4f}%)")
                emit_event(engine='bloc_1inch', trade_id=trade_id, position_id=None, stage='rejected', outcome_type='rejected_setup', status='failure', setup_type=signal.get('type'), notes='edge_below_net_target', data={'expected_edge_pct': expected_edge_pct})
                state_manager.log_signal(signal, executed=False, reason='edge_below_net_target')
                return

        print(f"   ✅ Qualified for execution: size=${size_usd:.2f}, expected_edge={signal.get('expected_edge_pct')}, funded_side={signal.get('funded_side')}")
        emit_event(engine='bloc_1inch', trade_id=trade_id, position_id=None, stage='qualified', outcome_type='info', status='success', setup_type=signal.get('type'), data={'size_usd': size_usd})
        state_manager.log_signal(signal, executed=True, reason="passed_all_checks")

        # Create position
        position = trade_manager.create_position(signal, size_usd, paper=False)
        position.trade_id = trade_id

        print(f"   📊 Position created: {position.id}")

        if PAPER_TRADING_MODE:
            print("   ❌ Production live path blocked: PAPER_TRADING_MODE is enabled")
            emit_event(engine='bloc_1inch', trade_id=trade_id, position_id=position.id, stage='failed', outcome_type='execution_failure', status='failure', setup_type=signal.get('type'), notes='paper_mode_enabled')
            return

        asyncio.create_task(self._execute_live_trade(position))
    
    async def _resume_persisted_live_positions(self):
        """Load durable live positions and resume monitoring after restart."""
        try:
            wallet = wallet_monitor.get_all_balances()
            reconciled = state_manager.build_reconciled_positions(wallet, trade_manager.get_open_positions())
            resumed_any = False
            for item in reconciled:
                if not item.get('linked_to_wallet_inventory', True):
                    continue
                if not item.get('resumable_after_restart'):
                    continue
                if item.get('status') not in ('open', 'allocated', 'tracked_trade_manager_state') and item.get('source') != 'inventory_reconciliation':
                    continue
                position = trade_manager.get_position(item.get('id')) if item.get('id') else None
                if position is None:
                    entry_price = float(item.get('entry_price') or 0) or 2200.0
                    signal = {
                        'timestamp': item.get('entry_time') or time.time(),
                        'direction': 'up',
                        'price': entry_price,
                        'type': item.get('source', 'persisted_resume'),
                    }
                    position = trade_manager.create_position(signal, float(item.get('size_usd') or (float(item.get('allocated_units') or item.get('lot_units') or 0)) * entry_price), paper=False)
                    if item.get('id'):
                        position.id = item.get('id')
                    position.entry_price = entry_price
                    position.target_price = float(item.get('target_price') or (entry_price * 1.005))
                    position.stop_price = float(item.get('stop_price') or (entry_price * 0.997))
                    position.entry_time = float(item.get('entry_time') or time.time())
                    position.direction = 'long'
                    position.tx_hash = item.get('tx_hash')
                    position.executed_to_amount_units = float(item.get('allocated_units') or item.get('lot_units') or 0)
                    position.status = position.status.OPEN
                    position.paper = False
                    position.signal = signal
                    position.source = item.get('source', 'persisted_resume')
                    position.resumable_after_restart = True
                    trade_manager.positions[position.id] = position
                if position.id not in trade_manager.active_monitors:
                    print(f"   ♻️ Resuming persisted live position {position.id} from {item.get('source')}")
                    asyncio.create_task(self._monitor_live_position(position))
                    resumed_any = True
            return resumed_any
        except Exception as e:
            print(f"   ❌ Failed to resume persisted live positions: {e}")
            return False

    async def _execute_live_trade(self, position):
        """Execute live trade on-chain"""
        from web3 import Web3
        w3 = Web3()
        print(f"   🧪 EXECUTOR STATE: enabled={live_executor.enabled} id={id(live_executor)} position={position.id}")
        funded_side = position.signal.get('funded_side', 'USDC')
        target_symbol = position.signal.get('symbol', 'ETH')
        target_token = WETH_ADDRESS if target_symbol == 'ETH' else CBBTC_ADDRESS
        if funded_side == 'USDC':
            from_token = USDC_ADDRESS
            to_token = target_token
            amount_wei = int(position.size_usd * 1e6)
            print(f"   🔄 Getting swap quote for ${position.size_usd:.2f} USDC -> {target_symbol} using runtime-visible USDC inventory...")
        else:
            from_token = ETH_ADDRESS
            to_token = WETH_ADDRESS
            native_eth_available = float(position.signal.get('native_eth_balance') or 0.0)
            target_amount_eth = min(position.size_usd / max(position.entry_price, 1), native_eth_available)
            provisional_amount_wei = int(target_amount_eth * 1e18)
            print(f"   🔄 Getting provisional swap quote for {target_amount_eth:.6f} ETH -> WETH (native available {native_eth_available:.6f})...")

            provisional_swap = live_executor.get_swap_data(
                from_token=from_token,
                to_token=to_token,
                amount=provisional_amount_wei
            )
            if not provisional_swap:
                print(f"   ❌ Failed to get provisional swap quote")
                return

            wallet = wallet_monitor.get_all_balances()
            native_eth_balance = float(wallet.get('eth') or 0.0)
            native_eth_balance_wei = int(native_eth_balance * 1e18)
            quote_gas = int(((provisional_swap.get('tx') or {}).get('gas') or 250000))
            gas_price_wei = int(w3.to_wei(max(wallet.get('gas') or 0.006, 0.006), 'gwei'))
            estimated_gas_cost_wei = quote_gas * gas_price_wei
            min_gas_buffer_wei = int(0.0003 * 1e18)
            gas_reserve_wei = max(int(estimated_gas_cost_wei * 3), min_gas_buffer_wei)
            spendable_wei = max(0, native_eth_balance_wei - gas_reserve_wei)

            print(f"   ⛽ Native ETH balance: {native_eth_balance_wei} wei")
            print(f"   ⛽ Estimated gas cost: {estimated_gas_cost_wei} wei")
            print(f"   ⛽ Gas reserve chosen: {gas_reserve_wei} wei")
            print(f"   ⛽ Final spendable ETH: {spendable_wei} wei")

            if spendable_wei < int(0.0005 * 1e18):
                print(f"   ❌ Spendable ETH after gas reserve too small: {spendable_wei} wei")
                return

            amount_wei = min(provisional_amount_wei, spendable_wei)
            amount_eth = amount_wei / 1e18
            print(f"   🔄 Getting final swap quote for {amount_eth:.6f} ETH -> WETH after gas reserve...")

        invariant_check = live_executor.pretrade_invariant_check(
            from_token=from_token,
            to_token=to_token,
            amount=amount_wei,
        )
        if not invariant_check.get('ok'):
            print(f"   ❌ Invariant gate failed: {invariant_check.get('reason')}")
            emit_event(engine='bloc_1inch', trade_id=getattr(position, 'trade_id', None), position_id=position.id, stage='failed', outcome_type='execution_failure', status='failure', setup_type=position.signal.get('type'), notes=invariant_check.get('reason'), data=invariant_check)
            return

        emit_event(engine='bloc_1inch', trade_id=getattr(position, 'trade_id', None), position_id=position.id, stage='previewed', outcome_type='info', status='success', setup_type=position.signal.get('type'), data=invariant_check)
        swap_data = live_executor.get_swap_data(
            from_token=from_token,
            to_token=to_token,
            amount=amount_wei
        )
        
        if not swap_data:
            print(f"   ❌ Failed to get swap quote")
            emit_event(engine='bloc_1inch', trade_id=getattr(position, 'trade_id', None), position_id=position.id, stage='failed', outcome_type='execution_failure', status='failure', setup_type=position.signal.get('type'), notes='swap_quote_failed')
            return
        
        print(f"   💰 Swap quote received, executing...")
        emit_event(engine='bloc_1inch', trade_id=getattr(position, 'trade_id', None), position_id=position.id, stage='submitted', outcome_type='info', status='success', setup_type=position.signal.get('type'), data={'swap_data_present': True})
        
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

            success = await trade_manager.open_position(position)
            if not success:
                print(f"   ❌ Failed to open position after live tx")
                emit_event(engine='bloc_1inch', trade_id=getattr(position, 'trade_id', None), position_id=position.id, stage='failed', outcome_type='reconciliation_failure', status='failure', setup_type=position.signal.get('type'), notes='open_position_failed_after_tx')
                return

            emit_event(engine='bloc_1inch', trade_id=getattr(position, 'trade_id', None), position_id=position.id, stage='filled', outcome_type='info', status='success', setup_type=position.signal.get('type'), data={'tx_hash': tx_hash})
            risk_manager.record_trade(position.signal, position.size_usd, paper=False)
            trade_manager.start_monitoring(position.id, price_feed.get_eth_price)
            position.source = 'autonomous_entry'
            position.resumable_after_restart = True
            position.max_hold_seconds = trade_manager.max_hold_time
            state_manager.persist_live_position(position)
            print(f"   ✅ POSITION OPENED WITH LIVE TX: {position.id}")
            print(f"   ✅ SWAP EXECUTED: {tx_hash}")
            print(f"   🔗 View on Basescan: https://basescan.org/tx/{tx_hash}")
            
            # Monitor the trade
            asyncio.create_task(self._monitor_live_position(position))
        else:
            print(f"   ❌ Swap execution failed")
            emit_event(engine='bloc_1inch', trade_id=getattr(position, 'trade_id', None), position_id=position.id, stage='failed', outcome_type='execution_failure', status='failure', setup_type=position.signal.get('type'), notes='swap_execution_failed')
    
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
            emit_event(engine='bloc_1inch', trade_id=getattr(position, 'trade_id', None), position_id=position.id, stage='failed', outcome_type='reconciliation_failure', status='failure', setup_type=position.signal.get('type'), notes='exit_no_swap_data')
            return {'closed': False, 'reason': 'no_swap_data'}

        tx_hash = live_executor.execute_swap(swap_data)
        if not tx_hash:
            print(f"   ❌ Exit blocked - sell swap failed")
            emit_event(engine='bloc_1inch', trade_id=getattr(position, 'trade_id', None), position_id=position.id, stage='failed', outcome_type='execution_failure', status='failure', setup_type=position.signal.get('type'), notes='exit_swap_failed')
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
            state_manager.mark_position_closed(
                position=closed_position,
                exit_price=current_price,
                exit_time=closed_position.exit_time,
                pnl_usd=closed_position.pnl_usd,
                pnl_pct=closed_position.pnl_pct,
                reason=reason,
            )
            
            emit_event(engine='bloc_1inch', trade_id=getattr(position, 'trade_id', None), position_id=position.id, stage='closed', outcome_type='closed_trade_outcome', status='success', setup_type=position.signal.get('type'), data={'tx_hash': tx_hash, 'pnl_usd': pnl_usd, 'pnl_pct': pnl_pct, 'result': 'losing_trade' if pnl_usd < 0 else 'winning_trade'})
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
        print(f"Available Capital: ${wallet['usdc']:.2f}")
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
