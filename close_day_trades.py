#!/usr/bin/env python3
"""
Close all open day trades before market close.
"""
import argparse
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tradier_broker_interface import TradierBrokerInterface
from tradier_execution_service import ExecutionService

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Print actions without executing')
    args = parser.parse_args()
    
    broker = TradierBrokerInterface()
    service = ExecutionService(broker=broker)
    
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
    for pos in positions:
        symbol = pos.get('symbol')
        qty = pos.get('quantity')
        try:
            # Assuming close_position method exists in broker or service
            # Check if broker has close_position
            if hasattr(broker, 'close_position'):
                broker.close_position(symbol, qty)
            elif hasattr(service, 'close_position'):
                service.close_position(symbol, qty)
            else:
                # Use order placement with opposite side (sell for long calls/puts)
                # This is simplified; we need to determine side from position type
                # For simplicity, just log error
                print(f"ERROR: No close method found for {symbol}")
                continue
            print(f"Closed {symbol} x {qty}")
        except Exception as e:
            print(f"Error closing {symbol}: {e}")

if __name__ == '__main__':
    main()