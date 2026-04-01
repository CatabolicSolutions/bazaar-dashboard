#!/usr/bin/env python3
"""
Quick test to verify wallet and connection
"""

from web3 import Web3

# Connect to mainnet via public provider (read-only)
w3 = Web3(Web3.HTTPProvider('https://eth.llamarpc.com'))

# Your wallet address
WALLET_ADDRESS = '0xFf9cc57be71A7b851A422a851600ac23B3843e27'

print(f"Connected to Ethereum: {w3.is_connected()}")
print(f"Block number: {w3.eth.block_number}")
print(f"\nChecking wallet: {WALLET_ADDRESS}")

# Get ETH balance
balance = w3.eth.get_balance(WALLET_ADDRESS)
balance_eth = w3.from_wei(balance, 'ether')

print(f"ETH Balance: {balance_eth} ETH")

# Check if it's a valid address
print(f"\nValid address: {Web3.is_address(WALLET_ADDRESS)}")
print(f"Checksum: {Web3.to_checksum_address(WALLET_ADDRESS)}")
