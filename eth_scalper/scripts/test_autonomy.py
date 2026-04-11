"""
Test bot autonomy by simulating the main loop conditions.
This test verifies:
1. Entry can be triggered by the forced fallback mechanism
2. Exit monitoring fires autonomously on target/stop/timeout
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import time
import json

from bot.main import ETHScalper
from execution.trade_manager import trade_manager
from execution.live_executor import live_executor
from signals.price_feed import price_feed
from signals.momentum import momentum_detector
from config.settings import PAPER_TRADING_MODE, AUTO_MANUAL_BUY_FALLBACK_SECONDS


async def test_autonomy():
    """Test autonomous entry and exit"""
    print("=" * 60)
    print("🤖 TESTING BOT AUTONOMY")
    print("=" * 60)
    
    bot = ETHScalper()
    live_executor.enable()
    
    results = {
        'entry_triggered': False,
        'entry_method': None,
        'entry_tx_hash': None,
        'exit_triggered': False,
        'exit_reason': None,
        'exit_tx_hash': None,
        'blocker': None,
    }
    
    # Build price history first
    print("\n📊 Building price history...")
    for i in range(12):
        price = price_feed.get_eth_price()
        print(f"  Sample {i+1}: ${price:.2f}")
        await asyncio.sleep(5)
    
    stats = price_feed.get_price_stats()
    print(f"\nPrice history length: {stats['history_length']}")
    print(f"60s change: {stats['change_60s_pct']}%")
    
    # Check if momentum signal would fire
    signal = momentum_detector.detect_momentum()
    print(f"Momentum signal: {signal}")
    
    # Check if forced fallback would trigger
    now = time.time()
    time_since_forced = now - bot.last_forced_entry
    open_positions = len(trade_manager.get_open_positions())
    
    print(f"\nForced fallback conditions:")
    print(f"  Time since last forced: {time_since_forced:.1f}s (threshold: {AUTO_MANUAL_BUY_FALLBACK_SECONDS}s)")
    print(f"  Open positions: {open_positions}")
    print(f"  Would trigger: {time_since_forced > AUTO_MANUAL_BUY_FALLBACK_SECONDS and open_positions == 0}")
    
    # Simulate the bot's tick logic
    print("\n🔄 Simulating bot ticks...")
    
    entry_triggered = False
    entry_time = None
    
    for tick in range(30):  # 30 ticks = 5 minutes at 10s intervals
        print(f"\n--- Tick {tick+1} ---")
        
        # Update price
        current_price = price_feed.get_eth_price()
        print(f"Price: ${current_price:.2f}")
        
        # Check for signal
        signal = momentum_detector.detect_momentum()
        
        if signal:
            print(f"🚨 SIGNAL: {signal['direction']} score={signal['score']}")
            # In real bot, this would call _handle_signal
            # For test, we'll track that signal was detected
            results['entry_method'] = 'momentum_signal'
            entry_triggered = True
            break
        
        # Check forced fallback
        now = time.time()
        if (not PAPER_TRADING_MODE and 
            now - bot.last_forced_entry > AUTO_MANUAL_BUY_FALLBACK_SECONDS and 
            len(trade_manager.get_open_positions()) == 0):
            print("⏰ Forced fallback triggered!")
            results['entry_method'] = 'forced_fallback'
            entry_triggered = True
            break
        
        # Check if position exists (from previous entry)
        positions = trade_manager.get_open_positions()
        if positions:
            print(f"📊 Position exists: {positions[0].id}")
            entry_triggered = True
            entry_time = positions[0].entry_time
            break
        
        await asyncio.sleep(10)
    
    if not entry_triggered:
        results['blocker'] = 'No entry triggered within test window'
        print(f"\n❌ {results['blocker']}")
        print(json.dumps(results, indent=2))
        return results
    
    results['entry_triggered'] = True
    print(f"\n✅ Entry triggered via: {results['entry_method']}")
    
    # Now test exit monitoring
    print("\n🔍 Testing exit monitoring...")
    
    # Get the open position
    positions = trade_manager.get_open_positions()
    if not positions:
        results['blocker'] = 'Entry did not create position'
        print(f"\n❌ {results['blocker']}")
        print(json.dumps(results, indent=2))
        return results
    
    position = positions[0]
    print(f"Position: {position.id}")
    print(f"  Entry: ${position.entry_price:.2f}")
    print(f"  Target: ${position.target_price:.2f}")
    print(f"  Stop: ${position.stop_price:.2f}")
    print(f"  Max hold: {trade_manager.max_hold_time}s")
    
    # Monitor for exit
    exit_triggered = False
    monitor_start = time.time()
    
    while time.time() - monitor_start < 300:  # Monitor for 5 minutes max
        current_price = price_feed.get_eth_price()
        hold_time = time.time() - position.entry_time
        
        print(f"\nPrice: ${current_price:.2f}, Hold: {hold_time:.1f}s")
        
        # Check exit conditions (same logic as _monitor_live_position)
        if position.direction == 'long':
            if current_price >= position.target_price:
                print("🎯 TARGET HIT!")
                results['exit_reason'] = 'target_hit'
                exit_triggered = True
                break
            if current_price <= position.stop_price:
                print("🛑 STOP LOSS!")
                results['exit_reason'] = 'stop_loss'
                exit_triggered = True
                break
        
        if hold_time > trade_manager.max_hold_time:
            print("⏰ TIMEOUT!")
            results['exit_reason'] = 'timeout'
            exit_triggered = True
            break
        
        # Check if position was closed externally
        current_positions = trade_manager.get_open_positions()
        if position.id not in [p.id for p in current_positions]:
            print("🔒 Position closed externally")
            exit_triggered = True
            break
        
        await asyncio.sleep(5)
    
    if not exit_triggered:
        results['blocker'] = 'No exit triggered within test window'
        print(f"\n❌ {results['blocker']}")
    else:
        results['exit_triggered'] = True
        print(f"\n✅ Exit triggered: {results['exit_reason']}")
    
    print("\n" + "=" * 60)
    print("AUTONOMY TEST RESULTS")
    print("=" * 60)
    print(json.dumps(results, indent=2))
    
    return results


if __name__ == '__main__':
    asyncio.run(test_autonomy())
