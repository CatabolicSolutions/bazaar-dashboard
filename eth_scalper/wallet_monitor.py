"""Wallet monitor - fetches wallet balances from configured RPC providers"""
import requests
from typing import Optional, Dict, List
from config.settings import ALCHEMY_URL, BASE_RPC_URL, WALLET_ADDRESS, USDC_ADDRESS, WETH_ADDRESS

class WalletMonitor:
    """Monitor wallet balances via one or more Ethereum RPC providers"""

    def __init__(self):
        self.wallet_address = WALLET_ADDRESS
        self.rpc_urls: List[str] = [url for url in [
            BASE_RPC_URL,
            ALCHEMY_URL,
            'https://base-rpc.publicnode.com',
        ] if url]

    def _rpc_call(self, method: str, params: list) -> Optional[dict]:
        last_error = None
        for rpc_url in self.rpc_urls:
            try:
                response = requests.post(
                    rpc_url,
                    json={
                        'jsonrpc': '2.0',
                        'method': method,
                        'params': params,
                        'id': 1
                    },
                    timeout=10
                )
                response.raise_for_status()
                data = response.json()
                if 'error' in data:
                    last_error = f"{rpc_url}: {data['error']}"
                    continue
                return data
            except Exception as e:
                last_error = f"{rpc_url}: {e}"
                continue
        print(f"RPC call failed for {method}: {last_error}")
        return None
    
    def get_eth_balance(self) -> Optional[float]:
        """Get ETH balance in ETH (not wei)"""
        try:
            data = self._rpc_call('eth_getBalance', [self.wallet_address, 'latest'])
            if not data or 'result' not in data:
                return None
            balance_wei = int(data['result'], 16)
            return balance_wei / 1e18
        except Exception as e:
            print(f"Failed to get ETH balance: {e}")
            return None
    
    def get_usdc_balance(self) -> Optional[float]:
        """Get USDC balance"""
        padded_address = self.wallet_address[2:].lower().rjust(64, '0')
        data = '0x70a08231' + padded_address

        try:
            result = self._rpc_call('eth_call', [{
                'to': USDC_ADDRESS,
                'data': data
            }, 'latest'])
            if not result:
                return None
            raw = result.get('result')
            if raw in (None, '0x'):
                return 0.0
            balance_raw = int(raw, 16)
            return balance_raw / 1e6
        except Exception as e:
            print(f"Failed to get USDC balance: {e}")
            return None
    
    def get_weth_balance(self) -> Optional[float]:
        """Get WETH balance"""
        padded_address = self.wallet_address[2:].lower().rjust(64, '0')
        data = '0x70a08231' + padded_address
        try:
            result = self._rpc_call('eth_call', [{
                'to': WETH_ADDRESS,
                'data': data
            }, 'latest'])
            if not result:
                return None
            raw = result.get('result')
            if raw in (None, '0x'):
                return 0.0
            balance_raw = int(raw, 16)
            return balance_raw / 1e18
        except Exception as e:
            print(f"Failed to get WETH balance: {e}")
            return None

    def get_gas_price(self) -> Optional[float]:
        """Get current gas price in gwei"""
        try:
            data = self._rpc_call('eth_gasPrice', [])
            if not data or 'result' not in data:
                return None
            gas_wei = int(data['result'], 16)
            return gas_wei / 1e9
        except Exception as e:
            print(f"Failed to get gas price: {e}")
            return None
    
    def get_all_balances(self) -> Dict:
        """Get all wallet info"""
        eth = self.get_eth_balance()
        weth = self.get_weth_balance()
        usdc = self.get_usdc_balance()
        gas = self.get_gas_price()
        
        return {
            'eth': eth if eth is not None else 0.0,
            'weth': weth if weth is not None else 0.0,
            'usdc': usdc if usdc is not None else 0.0,
            'gas': gas if gas is not None else 0.0,
            'address': self.wallet_address,
            'estimated_total_usd': ((eth or 0.0) * 2200) + ((weth or 0.0) * 2200) + (usdc or 0.0)
        }

# Global instance
wallet_monitor = WalletMonitor()
