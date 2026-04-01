#!/usr/bin/env python3
"""
Crypto Trading Module for THE BAZAAR Dashboard
Integrates Web3/DEX trading alongside options
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional, Dict, List

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from web3.secure_wallet import SecureWallet
from web3.uniswap_dex import UniswapV3DEX, TOKEN_ADDRESSES, GOERLI_TOKENS

# Configuration
CRYPTO_CONFIG = {
    'max_trade_size_eth': Decimal('0.1'),
    'daily_loss_limit_eth': Decimal('0.05'),
    'default_slippage': 0.5,
    'gas_limit': 300000,
    'network': 'goerli',  # Start with testnet
}

# Trading pairs to monitor
MONITORED_PAIRS = [
    ('WETH', 'USDC'),
    ('WETH', 'DAI'),
    ('WBTC', 'WETH'),
]


class CryptoTrader:
    """Automated crypto trading with safety controls"""
    
    def __init__(self, config_path: str = '/var/www/bazaar/config/crypto.json'):
        self.config_path = Path(config_path)
        self.wallet: Optional[SecureWallet] = None
        self.dex: Optional[UniswapV3DEX] = None
        self.trades_today: List[dict] = []
        self.daily_pnl = Decimal('0')
        self.emergency_stop = False
        
        self._load_config()
    
    def _load_config(self):
        """Load crypto trading configuration"""
        if self.config_path.exists():
            with open(self.config_path) as f:
                config = json.load(f)
                CRYPTO_CONFIG.update(config)
    
    def _save_config(self):
        """Save configuration"""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w') as f:
            json.dump(CRYPTO_CONFIG, f, indent=2, default=str)
    
    def initialize(self, infura_key: str, wallet_password: str) -> bool:
        """
        Initialize crypto trading module
        
        Args:
            infura_key: Infura API key
            wallet_password: Password to decrypt wallet
        
        Returns:
            True if successful
        """
        try:
            # Setup Web3 provider
            network = CRYPTO_CONFIG['network']
            if network == 'goerli':
                provider = f"https://goerli.infura.io/v3/{infura_key}"
            else:
                provider = f"https://mainnet.infura.io/v3/{infura_key}"
            
            # Initialize DEX
            self.dex = UniswapV3DEX(provider, network)
            
            # Load wallet
            self.wallet = SecureWallet('crypto_trading')
            address = self.wallet.load_wallet(wallet_password)
            
            if not address:
                print("❌ Failed to load wallet")
                return False
            
            print(f"✅ Crypto module initialized")
            print(f"📍 Wallet: {address}")
            print(f"🔗 Network: {network}")
            
            return True
            
        except Exception as e:
            print(f"❌ Initialization failed: {e}")
            return False
    
    def get_wallet_info(self) -> dict:
        """Get wallet balance and status"""
        if not self.wallet or not self.dex:
            return {'error': 'Not initialized'}
        
        address = self.wallet.get_address()
        
        # Get ETH balance
        eth_balance = self.dex.get_eth_balance(address)
        
        # Get token balances
        tokens = {}
        network = CRYPTO_CONFIG['network']
        token_list = GOERLI_TOKENS if network == 'goerli' else TOKEN_ADDRESSES
        
        for symbol in ['USDC', 'DAI', 'WBTC']:
            if symbol in token_list:
                try:
                    balance = self.dex.get_token_balance(symbol, address)
                    tokens[symbol] = float(balance)
                except:
                    tokens[symbol] = 0
        
        return {
            'address': address,
            'eth_balance': float(eth_balance),
            'tokens': tokens,
            'network': CRYPTO_CONFIG['network'],
            'daily_pnl': float(self.daily_pnl),
            'emergency_stop': self.emergency_stop,
        }
    
    def check_trade_allowed(self, amount_eth: Decimal) -> tuple[bool, str]:
        """
        Check if trade is allowed based on safety limits
        
        Returns:
            (allowed, reason)
        """
        if self.emergency_stop:
            return False, "Emergency stop is active"
        
        if amount_eth > CRYPTO_CONFIG['max_trade_size_eth']:
            return False, f"Trade size {amount_eth} ETH exceeds max {CRYPTO_CONFIG['max_trade_size_eth']} ETH"
        
        if self.daily_pnl < -CRYPTO_CONFIG['daily_loss_limit_eth']:
            return False, f"Daily loss limit reached: {self.daily_pnl} ETH"
        
        return True, "Trade allowed"
    
    def execute_swap(
        self,
        token_in: str,
        token_out: str,
        amount_in: Decimal,
        slippage: Optional[float] = None
    ) -> dict:
        """
        Execute token swap with safety checks
        
        Returns:
            Trade result dict
        """
        # Check if initialized
        if not self.wallet or not self.dex:
            return {'success': False, 'error': 'Not initialized'}
        
        # Check safety limits
        allowed, reason = self.check_trade_allowed(amount_in)
        if not allowed:
            return {'success': False, 'error': reason}
        
        try:
            # Get quote
            expected_out = self.dex.quote_swap(token_in, token_out, amount_in)
            
            if expected_out == 0:
                return {'success': False, 'error': 'Could not get valid quote'}
            
            # Build transaction
            slippage = slippage or CRYPTO_CONFIG['default_slippage']
            address = self.wallet.get_address()
            
            tx = self.dex.build_swap_transaction(
                token_in, token_out, amount_in, address, slippage
            )
            
            # Sign transaction
            signed_tx = self.wallet.sign_transaction(tx)
            
            # Send transaction
            tx_hash = self.dex.w3.eth.send_raw_transaction(signed_tx)
            
            # Wait for receipt
            receipt = self.dex.w3.eth.wait_for_transaction_receipt(tx_hash)
            
            if receipt['status'] == 1:
                # Success
                trade = {
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'type': 'crypto_swap',
                    'token_in': token_in,
                    'token_out': token_out,
                    'amount_in': float(amount_in),
                    'expected_out': float(expected_out),
                    'tx_hash': tx_hash.hex(),
                    'gas_used': receipt['gasUsed'],
                    'success': True,
                }
                
                self.trades_today.append(trade)
                
                return {
                    'success': True,
                    'tx_hash': tx_hash.hex(),
                    'expected_out': float(expected_out),
                    'gas_used': receipt['gasUsed'],
                }
            else:
                return {'success': False, 'error': 'Transaction failed'}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def scan_for_opportunities(self) -> List[dict]:
        """
        Scan monitored pairs for trading opportunities
        
        Returns:
            List of opportunity signals
        """
        if not self.dex:
            return []
        
        opportunities = []
        
        for token_in, token_out in MONITORED_PAIRS:
            try:
                # Get quote for 0.01 ETH
                test_amount = Decimal('0.01')
                quote = self.dex.quote_swap(token_in, token_out, test_amount)
                
                if quote > 0:
                    opportunities.append({
                        'pair': f"{token_in}/{token_out}",
                        'test_amount': float(test_amount),
                        'quote': float(quote),
                        'signal': 'monitor',
                    })
            except:
                pass
        
        return opportunities
    
    def toggle_emergency_stop(self) -> bool:
        """Toggle emergency stop"""
        self.emergency_stop = not self.emergency_stop
        return self.emergency_stop
    
    def get_trade_history(self) -> List[dict]:
        """Get today's trade history"""
        return self.trades_today
    
    def reset_daily_stats(self):
        """Reset daily statistics (call at midnight)"""
        self.trades_today = []
        self.daily_pnl = Decimal('0')


def main():
    """CLI for crypto trading"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Crypto Trading Module')
    parser.add_argument('--init', action='store_true', help='Initialize module')
    parser.add_argument('--wallet-info', action='store_true', help='Show wallet info')
    parser.add_argument('--quote', nargs=3, metavar=('FROM', 'TO', 'AMOUNT'))
    parser.add_argument('--swap', nargs=3, metavar=('FROM', 'TO', 'AMOUNT'))
    parser.add_argument('--scan', action='store_true', help='Scan for opportunities')
    parser.add_argument('--emergency-stop', action='store_true')
    parser.add_argument('--infura-key', default=os.getenv('INFURA_KEY'))
    
    args = parser.parse_args()
    
    if not args.infura_key:
        print("❌ Need Infura key. Set INFURA_KEY env var or use --infura-key")
        return 1
    
    trader = CryptoTrader()
    
    if args.init:
        from getpass import getpass
        password = getpass("Enter wallet password: ")
        if trader.initialize(args.infura_key, password):
            print("✅ Ready for trading!")
        else:
            print("❌ Initialization failed")
            return 1
    
    elif args.wallet_info:
        # Need to init first
        print("Use --init first to load wallet")
    
    elif args.quote:
        print("Use --init first to initialize")
    
    elif args.swap:
        print("Use --init first to initialize")
    
    elif args.scan:
        print("Use --init first to initialize")
    
    elif args.emergency_stop:
        state = trader.toggle_emergency_stop()
        print(f"🛑 Emergency stop: {'ON' if state else 'OFF'}")
    
    else:
        parser.print_help()
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
