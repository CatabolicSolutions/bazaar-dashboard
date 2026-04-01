#!/usr/bin/env python3
"""
Uniswap V3 DEX Interface
Handles token swaps, price quotes, and liquidity operations
"""

from __future__ import annotations

import json
import os
from decimal import Decimal
from typing import Optional, Tuple
from pathlib import Path

from web3 import Web3
from web3.contract import Contract

# Uniswap V3 Contract Addresses (Ethereum Mainnet)
UNISWAP_V3_ADDRESSES = {
    'factory': '0x1F98431c8aD98523631AE4a59f267346ea31F984',
    'quoter': '0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6',
    'swap_router': '0xE592427A0AEce92De3Edee1F18E0157C05861564',
    'multicall': '0x1F98415757620B543A52E61c46B32Eb19261F984',
}

# Goerli Testnet Addresses
GOERLI_ADDRESSES = {
    'factory': '0x1F98431c8aD98523631AE4a59f267346ea31F984',
    'quoter': '0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6',
    'swap_router': '0xE592427A0AEce92De3Edee1F18E0157C05861564',
}

# Common Token Addresses (Mainnet)
TOKEN_ADDRESSES = {
    'WETH': '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',
    'USDC': '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48',
    'USDT': '0xdAC17F958D2ee523a2206206994597C13D831ec7',
    'DAI': '0x6B175474E89094C44Da98b954EedeAC495271d0F',
    'WBTC': '0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599',
    'LINK': '0x514910771AF9Ca656af840dff83E8264EcF986CA',
    'UNI': '0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984',
}

# Goerli Test Tokens
GOERLI_TOKENS = {
    'WETH': '0xB4FBF271143F4FBf7B91A5ded31805e42b2208d6',
    'USDC': '0x07865c6E87B9F70255377e024ace6630C1Eaa37F',
    'DAI': '0x11fE4B6AE13d2a6055C8D9cD65aE4026Ab644A6e',
}

# ABI Files (simplified - in production load from files)
QUOTER_ABI = [
    {
        "inputs": [
            {"internalType": "bytes", "name": "path", "type": "bytes"},
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"}
        ],
        "name": "quoteExactInput",
        "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    }
]

SWAP_ROUTER_ABI = [
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "bytes", "name": "path", "type": "bytes"},
                    {"internalType": "address", "name": "recipient", "type": "address"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"},
                    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                    {"internalType": "uint256", "name": "amountOutMinimum", "type": "uint256"}
                ],
                "internalType": "struct IV3SwapRouter.ExactInputParams",
                "name": "params",
                "type": "tuple"
            }
        ],
        "name": "exactInput",
        "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
        "stateMutability": "payable",
        "type": "function"
    }
]

ERC20_ABI = [
    {"constant": True, "inputs": [], "name": "name", "outputs": [{"name": "", "type": "string"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
    {"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"},
    {"constant": False, "inputs": [{"name": "_spender", "type": "address"}, {"name": "_value", "type": "uint256"}], "name": "approve", "outputs": [{"name": "", "type": "bool"}], "type": "function"},
    {"constant": True, "inputs": [{"name": "_owner", "type": "address"}, {"name": "_spender", "type": "address"}], "name": "allowance", "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
]


class UniswapV3DEX:
    """Uniswap V3 DEX interface for automated trading"""
    
    def __init__(self, web3_provider: str, network: str = 'mainnet'):
        """
        Initialize DEX connection
        
        Args:
            web3_provider: Web3 provider URL (Infura/Alchemy)
            network: 'mainnet' or 'goerli'
        """
        self.w3 = Web3(Web3.HTTPProvider(web3_provider))
        
        if not self.w3.is_connected():
            raise ConnectionError(f"Failed to connect to {web3_provider}")
        
        self.network = network
        
        # Select addresses based on network
        if network == 'goerli':
            self.addresses = GOERLI_ADDRESSES
            self.tokens = GOERLI_TOKENS
        else:
            self.addresses = UNISWAP_V3_ADDRESSES
            self.tokens = TOKEN_ADDRESSES
        
        # Initialize contracts
        self.quoter = self.w3.eth.contract(
            address=self.w3.to_checksum_address(self.addresses['quoter']),
            abi=QUOTER_ABI
        )
        
        self.swap_router = self.w3.eth.contract(
            address=self.w3.to_checksum_address(self.addresses['swap_router']),
            abi=SWAP_ROUTER_ABI
        )
        
        print(f"✅ Connected to Uniswap V3 on {network}")
        print(f"📊 Block number: {self.w3.eth.block_number}")
    
    def get_token_contract(self, token_symbol: str) -> Contract:
        """Get ERC20 contract for token"""
        if token_symbol not in self.tokens:
            raise ValueError(f"Unknown token: {token_symbol}")
        
        address = self.w3.to_checksum_address(self.tokens[token_symbol])
        return self.w3.eth.contract(address=address, abi=ERC20_ABI)
    
    def get_token_balance(self, token_symbol: str, wallet_address: str) -> Decimal:
        """Get token balance for wallet"""
        contract = self.get_token_contract(token_symbol)
        address = self.w3.to_checksum_address(wallet_address)
        
        balance = contract.functions.balanceOf(address).call()
        decimals = contract.functions.decimals().call()
        
        return Decimal(balance) / Decimal(10 ** decimals)
    
    def get_eth_balance(self, wallet_address: str) -> Decimal:
        """Get ETH balance for wallet"""
        address = self.w3.to_checksum_address(wallet_address)
        balance = self.w3.eth.get_balance(address)
        return Decimal(balance) / Decimal(10 ** 18)
    
    def quote_swap(self, token_in: str, token_out: str, amount_in: Decimal) -> Decimal:
        """
        Get quote for token swap
        
        Args:
            token_in: Input token symbol (e.g., 'WETH')
            token_out: Output token symbol (e.g., 'USDC')
            amount_in: Amount to swap (in token units)
        
        Returns:
            Expected output amount
        """
        # Build path: token_in -> fee -> token_out
        # Using 0.3% fee tier (3000 = 0.3%)
        path = (
            self.w3.to_bytes(hexstr=self.tokens[token_in]) +
            self.w3.to_bytes(3000, 'big', 3) +  # Fee tier
            self.w3.to_bytes(hexstr=self.tokens[token_out])
        )
        
        # Get decimals
        token_in_contract = self.get_token_contract(token_in)
        decimals = token_in_contract.functions.decimals().call()
        
        # Convert to wei
        amount_in_wei = int(amount_in * Decimal(10 ** decimals))
        
        try:
            # Get quote
            amount_out = self.quoter.functions.quoteExactInput(
                path,
                amount_in_wei
            ).call()
            
            # Get output decimals
            token_out_contract = self.get_token_contract(token_out)
            out_decimals = token_out_contract.functions.decimals().call()
            
            return Decimal(amount_out) / Decimal(10 ** out_decimals)
            
        except Exception as e:
            print(f"Quote failed: {e}")
            return Decimal(0)
    
    def build_swap_transaction(
        self,
        token_in: str,
        token_out: str,
        amount_in: Decimal,
        recipient: str,
        slippage_percent: float = 0.5,
        deadline_minutes: int = 20
    ) -> dict:
        """
        Build swap transaction (does not execute)
        
        Returns transaction dict ready for signing
        """
        # Get quote
        expected_out = self.quote_swap(token_in, token_out, amount_in)
        
        if expected_out == 0:
            raise ValueError("Could not get valid quote")
        
        # Calculate minimum output with slippage
        min_out = expected_out * Decimal(1 - slippage_percent / 100)
        
        # Build path
        path = (
            self.w3.to_bytes(hexstr=self.tokens[token_in]) +
            self.w3.to_bytes(3000, 'big', 3) +
            self.w3.to_bytes(hexstr=self.tokens[token_out])
        )
        
        # Get input decimals
        token_in_contract = self.get_token_contract(token_in)
        in_decimals = token_in_contract.functions.decimals().call()
        amount_in_wei = int(amount_in * Decimal(10 ** in_decimals))
        
        # Get output decimals
        token_out_contract = self.get_token_contract(token_out)
        out_decimals = token_out_contract.functions.decimals().call()
        min_out_wei = int(min_out * Decimal(10 ** out_decimals))
        
        # Calculate deadline
        import time
        deadline = int(time.time()) + (deadline_minutes * 60)
        
        # Build transaction
        tx = self.swap_router.functions.exactInput({
            'path': path,
            'recipient': self.w3.to_checksum_address(recipient),
            'deadline': deadline,
            'amountIn': amount_in_wei,
            'amountOutMinimum': min_out_wei
        }).build_transaction({
            'from': recipient,
            'value': 0,
            'gas': 300000,  # Estimate will be better
            'maxFeePerGas': self.w3.to_wei('50', 'gwei'),
            'maxPriorityFeePerGas': self.w3.to_wei('2', 'gwei'),
            'nonce': self.w3.eth.get_transaction_count(recipient),
        })
        
        return tx
    
    def check_allowance(self, token_symbol: str, owner: str, spender: str) -> Decimal:
        """Check token allowance for swap router"""
        contract = self.get_token_contract(token_symbol)
        
        allowance = contract.functions.allowance(
            self.w3.to_checksum_address(owner),
            self.w3.to_checksum_address(spender)
        ).call()
        
        decimals = contract.functions.decimals().call()
        return Decimal(allowance) / Decimal(10 ** decimals)
    
    def build_approve_transaction(
        self,
        token_symbol: str,
        spender: str,
        amount: Decimal,
        owner: str
    ) -> dict:
        """Build approve transaction for token spending"""
        contract = self.get_token_contract(token_symbol)
        decimals = contract.functions.decimals().call()
        amount_wei = int(amount * Decimal(10 ** decimals))
        
        tx = contract.functions.approve(
            self.w3.to_checksum_address(spender),
            amount_wei
        ).build_transaction({
            'from': self.w3.to_checksum_address(owner),
            'gas': 100000,
            'maxFeePerGas': self.w3.to_wei('50', 'gwei'),
            'maxPriorityFeePerGas': self.w3.to_wei('2', 'gwei'),
            'nonce': self.w3.eth.get_transaction_count(owner),
        })
        
        return tx


def main():
    """Test DEX connection"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Uniswap V3 DEX Interface')
    parser.add_argument('--network', default='goerli', choices=['mainnet', 'goerli'])
    parser.add_argument('--infura-key', help='Infura API key')
    parser.add_argument('--quote', nargs=3, metavar=('FROM', 'TO', 'AMOUNT'), 
                       help='Get swap quote')
    parser.add_argument('--balance', nargs=2, metavar=('TOKEN', 'ADDRESS'),
                       help='Check token balance')
    
    args = parser.parse_args()
    
    # Setup provider
    if args.network == 'goerli':
        provider = f"https://goerli.infura.io/v3/{args.infura_key or os.getenv('INFURA_KEY')}"
    else:
        provider = f"https://mainnet.infura.io/v3/{args.infura_key or os.getenv('INFURA_KEY')}"
    
    try:
        dex = UniswapV3DEX(provider, args.network)
        
        if args.quote:
            token_in, token_out, amount = args.quote
            amount_dec = Decimal(amount)
            
            print(f"\n📊 Quote: {amount} {token_in} → {token_out}")
            result = dex.quote_swap(token_in, token_out, amount_dec)
            print(f"💰 Expected output: {result} {token_out}")
        
        elif args.balance:
            token, address = args.balance
            if token == 'ETH':
                balance = dex.get_eth_balance(address)
            else:
                balance = dex.get_token_balance(token, address)
            print(f"\n💳 Balance: {balance} {token}")
        
        else:
            print("\n✅ DEX connection successful!")
            print(f"Network: {args.network}")
            print(f"Block: {dex.w3.eth.block_number}")
            print("\nUse --quote or --balance to test swaps")
    
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
