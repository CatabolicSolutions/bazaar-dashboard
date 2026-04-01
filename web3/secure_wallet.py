#!/usr/bin/env python3
"""
Secure Wallet Manager for Web3 Trading
Handles encrypted key storage and transaction signing
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional
from getpass import getpass

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
from web3 import Web3
from eth_account import Account

# Configuration
WALLET_DIR = Path('/var/www/bazaar/wallets')
SALT_FILE = WALLET_DIR / '.salt'

class SecureWallet:
    """Encrypted wallet management for automated trading"""
    
    def __init__(self, wallet_name: str = 'trading'):
        self.wallet_name = wallet_name
        self.wallet_file = WALLET_DIR / f'{wallet_name}.wallet'
        self._account: Optional[Account] = None
        self._decrypted = False
        
        WALLET_DIR.mkdir(parents=True, exist_ok=True)
    
    def _get_or_create_salt(self) -> bytes:
        """Get existing salt or create new one"""
        if SALT_FILE.exists():
            return SALT_FILE.read_bytes()
        
        salt = os.urandom(16)
        SALT_FILE.write_bytes(salt)
        os.chmod(SALT_FILE, 0o600)  # Restrict permissions
        return salt
    
    def _derive_key(self, password: str) -> bytes:
        """Derive encryption key from password"""
        salt = self._get_or_create_salt()
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key
    
    def create_wallet(self, password: str) -> str:
        """Create new encrypted wallet"""
        # Generate new account
        acct = Account.create()
        
        # Encrypt private key
        key = self._derive_key(password)
        f = Fernet(key)
        encrypted_key = f.encrypt(acct.key.hex().encode())
        
        # Store wallet data
        wallet_data = {
            'address': acct.address,
            'encrypted_key': encrypted_key.decode(),
            'created_at': str(os.path.getctime(self.wallet_file)) if self.wallet_file.exists() else 'new'
        }
        
        self.wallet_file.write_text(json.dumps(wallet_data))
        os.chmod(self.wallet_file, 0o600)  # Restrict permissions
        
        self._account = acct
        self._decrypted = True
        
        return acct.address
    
    def load_wallet(self, password: str) -> Optional[str]:
        """Load and decrypt existing wallet"""
        if not self.wallet_file.exists():
            return None
        
        try:
            wallet_data = json.loads(self.wallet_file.read_text())
            
            # Decrypt private key
            key = self._derive_key(password)
            f = Fernet(key)
            private_key = f.decrypt(wallet_data['encrypted_key'].encode()).decode()
            
            # Create account from key
            self._account = Account.from_key(private_key)
            self._decrypted = True
            
            # Verify address matches
            if self._account.address != wallet_data['address']:
                raise ValueError("Address mismatch - corrupted wallet?")
            
            return self._account.address
            
        except Exception as e:
            print(f"Failed to decrypt wallet: {e}")
            return None
    
    def get_address(self) -> Optional[str]:
        """Get wallet address without decrypting"""
        if self._account:
            return self._account.address
        
        if self.wallet_file.exists():
            try:
                wallet_data = json.loads(self.wallet_file.read_text())
                return wallet_data['address']
            except:
                pass
        
        return None
    
    def sign_transaction(self, transaction_dict: dict) -> Optional[str]:
        """Sign a transaction with decrypted key"""
        if not self._decrypted or not self._account:
            raise ValueError("Wallet not decrypted. Call load_wallet() first.")
        
        signed = self._account.sign_transaction(transaction_dict)
        return signed.rawTransaction.hex()
    
    def is_unlocked(self) -> bool:
        """Check if wallet is decrypted and ready"""
        return self._decrypted and self._account is not None
    
    def lock(self):
        """Clear decrypted key from memory"""
        self._account = None
        self._decrypted = False


def main():
    """CLI for wallet management"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Secure Wallet Manager')
    parser.add_argument('--create', action='store_true', help='Create new wallet')
    parser.add_argument('--load', action='store_true', help='Load existing wallet')
    parser.add_argument('--address', action='store_true', help='Show address')
    parser.add_argument('--name', default='trading', help='Wallet name')
    
    args = parser.parse_args()
    
    wallet = SecureWallet(args.name)
    
    if args.create:
        if wallet.wallet_file.exists():
            print(f"Wallet '{args.name}' already exists!")
            return
        
        password = getpass("Set wallet password: ")
        confirm = getpass("Confirm password: ")
        
        if password != confirm:
            print("Passwords don't match!")
            return
        
        address = wallet.create_wallet(password)
        print(f"✅ Wallet created!")
        print(f"📍 Address: {address}")
        print(f"💾 Saved to: {wallet.wallet_file}")
        print("\n⚠️  IMPORTANT: Fund this wallet with small amount for gas fees")
        print("🔒 Your private key is encrypted and secure")
        
    elif args.load:
        if not wallet.wallet_file.exists():
            print(f"Wallet '{args.name}' not found!")
            return
        
        password = getpass("Enter wallet password: ")
        address = wallet.load_wallet(password)
        
        if address:
            print(f"✅ Wallet unlocked!")
            print(f"📍 Address: {address}")
            print(f"🔓 Ready for trading")
        else:
            print("❌ Failed to unlock wallet - wrong password?")
            
    elif args.address:
        address = wallet.get_address()
        if address:
            print(f"📍 Wallet address: {address}")
        else:
            print("No wallet found")
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
