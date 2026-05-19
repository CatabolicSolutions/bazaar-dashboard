#!/usr/bin/env python3
"""
Place bracket orders for NVDA 187.5 PUT position.
- Stop loss at 50% loss ($0.35)
- Take profit at 28.6% gain ($0.90)
Orders are GTC to hold overnight, avoiding PDT violation.
"""
import sys
sys.path.insert(0, '/var/www/bazaar/scripts')

from tradier_execution import post_order, list_orders, cancel_order
import json
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

OPTION_SYMBOL = 'NVDA260422P00187500'
QUANTITY = 1
ENTRY_PRICE = 0.70
STOP_LOSS_PRICE = 0.35
TAKE_PROFIT_PRICE = 0.90

def get_existing_orders():
    """Get all open orders for the NVDA option."""
    orders = list_orders()
    logger.info(f"Raw orders response: {json.dumps(orders, indent=2)}")
    # Filter for option symbol and side 'sell_to_close'
    relevant = []
    if isinstance(orders, dict) and 'orders' in orders:
        orders_data = orders['orders']
        if isinstance(orders_data, dict) and 'order' in orders_data:
            order_item = orders_data['order']
            if isinstance(order_item, list):
                order_list = order_item
            elif isinstance(order_item, dict):
                order_list = [order_item]
            else:
                order_list = []
            for order in order_list:
                # Check if order matches our option symbol
                if order.get('symbol') == OPTION_SYMBOL and order.get('side') == 'sell_to_close':
                    relevant.append(order)
    return relevant

def cancel_duplicate_orders():
    """Cancel any existing sell_to_close orders for this option."""
    existing = get_existing_orders()
    cancelled = []
    for order in existing:
        order_id = order.get('id')
        if order_id:
            logger.info(f"Cancelling order {order_id}: {order.get('type')} @ {order.get('price')}")
            try:
                cancel_order(order_id)
                cancelled.append(order_id)
            except Exception as e:
                logger.error(f"Failed to cancel order {order_id}: {e}")
    return cancelled

def place_stop_loss():
    """Place a stop‑limit order for stop loss."""
    payload = {
        'class': 'option',
        'symbol': 'NVDA',
        'option_symbol': OPTION_SYMBOL,
        'side': 'sell_to_close',
        'quantity': QUANTITY,
        'type': 'stop_limit',
        'duration': 'gtc',
        'stop': STOP_LOSS_PRICE,
        'price': STOP_LOSS_PRICE - 0.05,  # limit a bit lower than stop
        'tag': 'auto_stop_loss'
    }
    logger.info(f"Placing stop‑limit order: {payload}")
    response = post_order(payload, preview=False)
    logger.info(f"Stop‑loss order response: {json.dumps(response, indent=2)}")
    return response

def place_take_profit():
    """Place a limit order for take profit."""
    payload = {
        'class': 'option',
        'symbol': 'NVDA',
        'option_symbol': OPTION_SYMBOL,
        'side': 'sell_to_close',
        'quantity': QUANTITY,
        'type': 'limit',
        'duration': 'gtc',
        'price': TAKE_PROFIT_PRICE,
        'tag': 'auto_take_profit'
    }
    logger.info(f"Placing take‑profit order: {payload}")
    response = post_order(payload, preview=False)
    logger.info(f"Take‑profit order response: {json.dumps(response, indent=2)}")
    return response

def main():
    logger.info("=== Setting bracket orders for NVDA 187.5 PUT ===")
    logger.info(f"Entry: ${ENTRY_PRICE}, Stop: ${STOP_LOSS_PRICE}, Target: ${TAKE_PROFIT_PRICE}")
    
    # Cancel any existing duplicate orders
    cancelled = cancel_duplicate_orders()
    if cancelled:
        logger.info(f"Cancelled {len(cancelled)} previous orders")
    
    # Place stop loss
    stop_resp = place_stop_loss()
    if 'order' in stop_resp and 'id' in stop_resp['order']:
        logger.info(f"Stop‑loss order ID: {stop_resp['order']['id']}")
    else:
        logger.error("Failed to place stop‑loss order")
        return
    
    # Place take profit
    tp_resp = place_take_profit()
    if 'order' in tp_resp and 'id' in tp_resp['order']:
        logger.info(f"Take‑profit order ID: {tp_resp['order']['id']}")
    else:
        logger.error("Failed to place take‑profit order")
        return
    
    logger.info("Bracket orders placed successfully. Hold overnight.")

if __name__ == '__main__':
    main()