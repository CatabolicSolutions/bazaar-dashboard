#!/usr/bin/env python3
"""
Close all open day trades before market close.
"""
import argparse
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tradier_broker_interface import TradierBrokerInterface
from tradier_execution_service import TradierExecutionService

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Print actions without executing')
    args = parser.parse_args()
    
    broker = TradierBrokerInterface()
    service = TradierExecutionService(broker=broker)
    
    # Get open positions
    positions = broker.get_positions()
    if not positions:
        print("No open positions.")
        return
    
    print(f"Found {len(positions)} open positions:")
    for pos in positions:
        print(f"  {pos.get('symbol')} x {pos.get('quantity')} ({pos.get('open_date')})")
    
    if args.dry_run:
        print("Dry-run: would close all positions.")
        return
    
    # Close each position
    # Determine side based on position type (simplified)
    for pos in positions:
        symbol = pos.get('symbol')
        qty = pos.get('quantity')
        side = 'sell_to_close'  # default for long options
        try:
            # Use broker's close_position if available
            if hasattr(broker, 'close_position'):
                broker.close_position(symbol, qty, side=side)
            else:
                # Fallback to posting a market order
                order = {
                    'symbol': symbol,
                    'side': side,
                    'quantity': qty,
                    'type': 'market',
                    'duration': 'day'
                }
                # Use broker's post_order if available
                if hasattr(broker, 'post_order'):
                    broker.post_order(order)
                else:
                    print(f"ERROR: No close method for {symbol}")
                    continue
            print(f"Closed {symbol} x {qty}")
        except Exception as e:
            print(f"Error closing {symbol}: {e}")

if __name__ == '__main__':
    main()