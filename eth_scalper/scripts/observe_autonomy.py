"""
Live observation of bot autonomy mechanisms.
Captures real runtime state without manual intervention.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import time
import json
from datetime import datetime

from bot.main import ETHScalper
from execution.trade_manager import trade_manager
from execution.live_executor import live_executor
from signals.price_feed import price_feed
from signals.momentum import momentum_detector
from wallet_monitor import wallet_monitor
from config.settings import AUTO_MANUAL_BUY_FALLBACK_SECONDS, PAPER_TRADING_MODE


async def observe_autonomy():
    """Observe and record bot autonomy in real-time"""
    
    bot = ETHScalper()
    live_executor.enable()
    
    observations = {
        'start_time': datetime.utcnow().isoformat(),
        'price_samples': [],
        'momentum_checks': [],
        'fallback_checks': [],
        'position_state': [],
        'monitoring_checks': [],
        'exit_events': [],
        'final_state': None,
    }
    
    print(f"[{datetime.utcnow().isoformat()}] Starting autonomy observation...")
    print(f"  PAPER_TRADING_MODE: {PAPER_TRADING_MODE}")
    print(f"  AUTO_MANUAL_BUY_FALLBACK_SECONDS: {AUTO_MANUAL_BUY_FALLBACK_SECONDS}")
    print(f"  Will observe for up to 10 minutes...")
    
    position_entered = False
    position_exited = False
    entry_method = None
    
    start_time = time.time()
    last_price_log = 0
    
    while time.time() - start_time < 600:  # 10 minutes max
        now = time.time()
        tick_num = int((now - start_time) / 10)
        
        # 1. Price feed visibility
        current_price = price_feed.get_eth_price()
        stats = price_feed.get_price_stats()
        
        if now - last_price_log >= 30:  # Log every 30 seconds
            sample = {
                'timestamp': datetime.utcnow().isoformat(),
                'price': current_price,
                'history_length': stats['history_length'],
                'change_60s': stats['change_60s_pct'],
                'gas_gwei': stats['gas_gwei'],
            }
            observations['price_samples'].append(sample)
            print(f"[{sample['timestamp']}] Price: ${current_price:.2f}, History: {stats['history_length']}, 60s_change: {stats['change_60s_pct']}")
            last_price_log = now
        
        # 2. Momentum detection
        signal = momentum_detector.detect_momentum()
        if signal:
            sig_record = {
                'timestamp': datetime.utcnow().isoformat(),
                'direction': signal['direction'],
                'price': signal['price'],
                'change_60s_pct': signal['change_60s_pct'],
                'score': signal['score'],
            }
            observations['momentum_checks'].append(sig_record)
            print(f"  🚨 MOMENTUM SIGNAL: {sig_record}")
            
            if not position_entered:
                print(f"  -> Would trigger entry via momentum")
                entry_method = 'momentum'
                position_entered = True
        
        # 3. Fallback check
        time_since_forced = now - bot.last_forced_entry
        open_positions = len(trade_manager.get_open_positions())
        
        if time_since_forced > AUTO_MANUAL_BUY_FALLBACK_SECONDS and open_positions == 0 and not position_entered:
            fallback_record = {
                'timestamp': datetime.utcnow().isoformat(),
                'time_since_forced': time_since_forced,
                'open_positions': open_positions,
                'triggered': True,
            }
            observations['fallback_checks'].append(fallback_record)
            print(f"  ⏰ FALLBACK TRIGGERED: {fallback_record}")
            entry_method = 'fallback'
            position_entered = True
        
        # 4. Position state tracking
        positions = trade_manager.get_open_positions()
        if positions or position_entered:
            pos_state = {
                'timestamp': datetime.utcnow().isoformat(),
                'open_count': len(positions),
                'positions': [{'id': p.id, 'entry': p.entry_price, 'target': p.target_price, 'stop': p.stop_price} for p in positions] if positions else [],
            }
            observations['position_state'].append(pos_state)
            
            if positions:
                print(f"  📊 POSITION: {pos_state}")
        
        # 5. Exit monitoring (if position exists)
        if positions:
            for pos in positions:
                current_price = price_feed.get_eth_price() or pos.entry_price
                hold_time = now - pos.entry_time
                
                monitor_check = {
                    'timestamp': datetime.utcnow().isoformat(),
                    'position_id': pos.id,
                    'current_price': current_price,
                    'target_price': pos.target_price,
                    'stop_price': pos.stop_price,
                    'hold_time': hold_time,
                }
                
                # Check exit conditions
                exit_triggered = False
                exit_reason = None
                
                if pos.direction == 'long':
                    if current_price >= pos.target_price:
                        exit_triggered = True
                        exit_reason = 'target_hit'
                    elif current_price <= pos.stop_price:
                        exit_triggered = True
                        exit_reason = 'stop_loss'
                
                if hold_time > trade_manager.max_hold_time:
                    exit_triggered = True
                    exit_reason = 'timeout'
                
                monitor_check['exit_triggered'] = exit_triggered
                monitor_check['exit_reason'] = exit_reason
                observations['monitoring_checks'].append(monitor_check)
                
                if exit_triggered:
                    print(f"  🔒 EXIT TRIGGERED: {exit_reason}")
                    observations['exit_events'].append({
                        'timestamp': datetime.utcnow().isoformat(),
                        'reason': exit_reason,
                        'position_id': pos.id,
                    })
                    position_exited = True
        
        # Check for completion
        if position_entered and position_exited:
            print(f"\n✅ Full round-trip completed!")
            break
        
        await asyncio.sleep(10)
    
    # Final state
    observations['end_time'] = datetime.utcnow().isoformat()
    observations['duration_seconds'] = time.time() - start_time
    observations['position_entered'] = position_entered
    observations['position_exited'] = position_exited
    observations['entry_method'] = entry_method
    
    # Get final balances
    wallet = wallet_monitor.get_all_balances()
    observations['final_balances'] = wallet
    
    print(f"\n{'='*60}")
    print("OBSERVATION COMPLETE")
    print(f"{'='*60}")
    print(f"Duration: {observations['duration_seconds']:.1f}s")
    print(f"Price samples: {len(observations['price_samples'])}")
    print(f"Momentum signals: {len(observations['momentum_checks'])}")
    print(f"Fallback triggers: {len(observations['fallback_checks'])}")
    print(f"Position entered: {position_entered} ({entry_method})")
    print(f"Position exited: {position_exited}")
    print(f"Final balances: {wallet}")
    
    # Save observations
    with open('/tmp/autonomy_observations.json', 'w') as f:
        json.dump(observations, f, indent=2)
    print(f"\nObservations saved to /tmp/autonomy_observations.json")
    
    return observations


if __name__ == '__main__':
    obs = asyncio.run(observe_autonomy())
    
    # Determine status
    if obs['position_entered'] and obs['position_exited']:
        status = "VERIFIED"
    elif obs['position_entered'] and not obs['position_exited']:
        status = "UNVERIFIED"
    else:
        status = "BLOCKED"
    
    print(f"\nSTATUS: {status}")
