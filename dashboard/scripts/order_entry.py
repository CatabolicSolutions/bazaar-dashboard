#!/usr/bin/env python3
"""
Order Entry Module
Handles order validation and submission to Tradier
"""

import json
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, Any

# Add scripts to path
ROOT = Path(__file__).resolve().parents[2]


@dataclass
class OrderRequest:
    symbol: str
    option_type: str  # 'call' or 'put'
    strike: float
    expiration: str
    side: str  # 'buy_to_open', 'sell_to_close', etc.
    quantity: int
    order_type: str  # 'market', 'limit', 'stop', 'stop_limit'
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: str = 'day'


class OrderValidator:
    """Validates order requests before submission"""
    
    MAX_POSITION_VALUE = 200.0  # $200 max per trade
    PRICE_TOLERANCE = 0.10  # 10% for fat finger check
    
    def __init__(self, buying_power: float = 1000.0):
        self.buying_power = buying_power
        self.errors = []
    
    def validate(self, order: OrderRequest, current_price: float) -> Dict[str, Any]:
        """Validate order and return result"""
        self.errors = []
        
        # Check quantity
        if order.quantity <= 0:
            self.errors.append("Quantity must be greater than 0")
        
        if order.quantity > 5:
            self.errors.append("Max 5 contracts per order")
        
        # Calculate position value
        if order.order_type == 'market':
            estimated_price = current_price
        elif order.order_type in ['limit', 'stop_limit'] and order.limit_price:
            estimated_price = order.limit_price
        else:
            estimated_price = current_price
        
        position_value = estimated_price * order.quantity * 100  # Options are 100 shares
        
        # Check position size limit
        if position_value > self.MAX_POSITION_VALUE:
            self.errors.append(f"Position value ${position_value:.0f} exceeds ${self.MAX_POSITION_VALUE:.0f} limit")
        
        # Check buying power
        if position_value > self.buying_power:
            self.errors.append(f"Insufficient buying power (${self.buying_power:.0f} available)")
        
        # Fat finger check for limit orders
        if order.order_type in ['limit', 'stop_limit'] and order.limit_price:
            price_diff = abs(order.limit_price - current_price) / current_price
            if price_diff > self.PRICE_TOLERANCE:
                self.errors.append(f"Limit price ${order.limit_price:.2f} is {price_diff*100:.0f}% from market (${current_price:.2f})")
        
        # Validate stop orders
        if order.order_type in ['stop', 'stop_limit'] and not order.stop_price:
            self.errors.append("Stop price required for stop orders")
        
        return {
            'valid': len(self.errors) == 0,
            'errors': self.errors,
            'position_value': position_value,
            'estimated_price': estimated_price
        }


class OrderManager:
    """Manages order submission to Tradier"""
    
    def __init__(self):
        self.api_key = os.getenv('TRADIER_API_KEY')
        self.account_id = os.getenv('TRADIER_ACCOUNT_ID')
        self.base_url = os.getenv('TRADIER_BASE_URL', 'https://api.tradier.com/v1')
    
    def build_option_symbol(self, symbol: str, expiration: str, option_type: str, strike: float) -> str:
        """Build OCC option symbol"""
        # Format: SPY240420C00520000
        # Symbol(6) + YYMMDD(6) + C/P(1) + Strike(8)
        
        # Parse expiration
        try:
            exp_parts = expiration.split('-')
            if len(exp_parts) == 3:
                year = exp_parts[0][2:4]  # Last 2 digits
                month = exp_parts[1]
                day = exp_parts[2]
                exp_str = f"{year}{month}{day}"
            else:
                exp_str = expiration
        except:
            exp_str = expiration
        
        # Format strike (8 digits with 3 decimal places implied)
        strike_int = int(strike * 1000)
        strike_str = f"{strike_int:08d}"
        
        # Option type
        opt_type = 'C' if option_type.lower() == 'call' else 'P'
        
        # Pad symbol to 6 chars
        symbol_padded = symbol.upper().ljust(6)
        
        return f"{symbol_padded}{exp_str}{opt_type}{strike_str}"
    
    def submit_order(self, order: OrderRequest) -> Dict[str, Any]:
        """Submit order to Tradier"""
        import requests
        
        if not self.api_key or not self.account_id:
            return {'ok': False, 'error': 'API credentials not configured'}
        
        # Build option symbol
        option_symbol = self.build_option_symbol(
            order.symbol,
            order.expiration,
            order.option_type,
            order.strike
        )
        
        # Build order payload
        payload = {
            'class': 'option',
            'symbol': option_symbol,
            'side': order.side,
            'quantity': order.quantity,
            'type': order.order_type,
            'duration': order.time_in_force
        }
        
        if order.order_type in ['limit', 'stop_limit'] and order.limit_price:
            payload['price'] = order.limit_price
        
        if order.order_type in ['stop', 'stop_limit'] and order.stop_price:
            payload['stop'] = order.stop_price
        
        try:
            response = requests.post(
                f"{self.base_url}/accounts/{self.account_id}/orders",
                data=payload,
                headers={
                    'Authorization': f'Bearer {self.api_key}',
                    'Accept': 'application/json'
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'ok': True,
                    'order_id': data.get('order', {}).get('id'),
                    'status': data.get('order', {}).get('status'),
                    'details': data
                }
            else:
                return {
                    'ok': False,
                    'error': f"API error: {response.status_code}",
                    'details': response.text
                }
        except Exception as e:
            return {'ok': False, 'error': str(e)}


def main():
    """CLI for testing"""
    import sys
    
    if len(sys.argv) < 2:
        print(json.dumps({'error': 'Usage: order_entry.py <command> [args]'}))
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == 'validate':
        # Test validation
        order = OrderRequest(
            symbol='SPY',
            option_type='call',
            strike=520.0,
            expiration='2026-04-17',
            side='buy_to_open',
            quantity=1,
            order_type='limit',
            limit_price=2.60,
            time_in_force='day'
        )
        
        validator = OrderValidator(buying_power=1000.0)
        result = validator.validate(order, current_price=2.60)
        print(json.dumps(result, indent=2))
    
    elif command == 'build_symbol':
        # Test symbol building
        manager = OrderManager()
        symbol = manager.build_option_symbol('SPY', '2026-04-17', 'call', 520.0)
        print(json.dumps({'symbol': symbol}))
    
    else:
        print(json.dumps({'error': f'Unknown command: {command}'}))


if __name__ == '__main__':
    main()
