"""Live trade execution via 1inch"""
import requests
from typing import Optional, Dict, List
from web3 import Web3
from eth_abi import encode
from config.settings import INCH_API_KEY, WALLET_ADDRESS, PRIVATE_KEY, MAX_SLIPPAGE_PERCENT, BASE_RPC_URL, CHAIN_ID, USDC_ADDRESS, WETH_ADDRESS
from config.logger import logger


UNISWAP_V3_SWAP_ROUTER02_BASE = '0x2626664c2603336E57B271c5C0b26F421741e481'
UNISWAP_V3_QUOTER_V2_BASE = '0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a'
UNISWAP_V3_FEE_TIER = 500


class LiveExecutor:
    """Execute real trades on 1inch"""

    def __init__(self):
        self.base_url = f'https://api.1inch.dev/swap/v5.2/{CHAIN_ID}'
        self.headers = {
            'Authorization': f'Bearer {INCH_API_KEY}',
            'Content-Type': 'application/json'
        }
        self.enabled = False  # Must be explicitly enabled

    def enable(self):
        """Enable live trading"""
        self.enabled = True
        logger.info("LIVE TRADING ENABLED")

    def disable(self):
        """Disable live trading"""
        self.enabled = False
        logger.info("LIVE TRADING DISABLED")

    def _get_web3(self):
        rpc_urls: List[str] = [url for url in [
            'https://base-rpc.publicnode.com',
            BASE_RPC_URL,
            'https://mainnet.base.org',
        ] if url]
        last_error = None
        for rpc_url in rpc_urls:
            try:
                w3 = Web3(Web3.HTTPProvider(rpc_url))
                if w3.is_connected():
                    _ = w3.eth.block_number
                    return w3
                last_error = f'not connected: {rpc_url}'
            except Exception as e:
                last_error = f'{rpc_url}: {e}'
        raise RuntimeError(f'Failed to connect to Base RPC: {last_error}')

    def _get_account(self):
        from eth_account import Account
        account = Account.from_key(PRIVATE_KEY)
        if account.address.lower() != WALLET_ADDRESS.lower():
            raise RuntimeError(f"Private key address mismatch: {account.address} != {WALLET_ADDRESS}")
        return account

    def ensure_allowance(self, token_address: str, spender: str, required_amount: int) -> Optional[Dict]:
        """Ensure ERC20 allowance exists for spender, submitting approve() when needed."""
        if token_address.lower() == '0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee':
            return {'skipped': True, 'reason': 'native token path'}

        try:
            w3 = self._get_web3()
            account = self._get_account()

            abi = [
                {
                    'name': 'allowance', 'type': 'function', 'stateMutability': 'view',
                    'inputs': [{'name': 'owner', 'type': 'address'}, {'name': 'spender', 'type': 'address'}],
                    'outputs': [{'name': '', 'type': 'uint256'}]
                },
                {
                    'name': 'approve', 'type': 'function', 'stateMutability': 'nonpayable',
                    'inputs': [{'name': 'spender', 'type': 'address'}, {'name': 'amount', 'type': 'uint256'}],
                    'outputs': [{'name': '', 'type': 'bool'}]
                }
            ]
            contract = w3.eth.contract(address=Web3.to_checksum_address(token_address), abi=abi)
            current = contract.functions.allowance(Web3.to_checksum_address(WALLET_ADDRESS), Web3.to_checksum_address(spender)).call()
            logger.info(f"Allowance read: token={token_address} spender={spender} allowance={current} required={required_amount}")
            if current >= required_amount:
                return {'approved': False, 'allowance': current}

            nonce = w3.eth.get_transaction_count(WALLET_ADDRESS, 'pending')
            latest_block = w3.eth.get_block('latest')
            base_fee = latest_block.get('baseFeePerGas', w3.eth.gas_price)
            network_gas = int(w3.eth.gas_price)
            priority_fee = max(w3.to_wei(0.005, 'gwei'), int(network_gas * 0.1))
            max_fee = max(int(base_fee * 3 + priority_fee), network_gas * 2)
            approve_tx = contract.functions.approve(Web3.to_checksum_address(spender), 2**256 - 1).build_transaction({
                'from': WALLET_ADDRESS,
                'chainId': CHAIN_ID,
                'nonce': nonce,
                'gas': 100000,
                'maxPriorityFeePerGas': priority_fee,
                'maxFeePerGas': max_fee,
                'type': 2,
                'value': 0,
            })
            signed_tx = account.sign_transaction(approve_tx)
            raw_tx = getattr(signed_tx, 'raw_transaction', None) or getattr(signed_tx, 'rawTransaction')
            tx_hash = w3.eth.send_raw_transaction(raw_tx).hex()
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            logger.info(f"Approval submitted: tx_hash={tx_hash} status={receipt.status}")
            refreshed = contract.functions.allowance(Web3.to_checksum_address(WALLET_ADDRESS), Web3.to_checksum_address(spender)).call()
            logger.info(f"Post-approval allowance read: token={token_address} spender={spender} allowance={refreshed}")
            if refreshed < required_amount:
                return {'approved': True, 'approval_tx_hash': tx_hash, 'allowance': refreshed, 'status': receipt.status, 'verified_effective': False}
            return {'approved': True, 'approval_tx_hash': tx_hash, 'allowance': refreshed, 'status': receipt.status, 'verified_effective': True}
        except Exception as e:
            logger.error(f"Allowance ensure failed: {e}")
            return None

    def _build_uniswap_v3_exact_input_single_tx(self, from_token: str, to_token: str, amount: int, slippage: float = None) -> Optional[Dict]:
        try:
            w3 = self._get_web3()
            amount_out = self._quote_uniswap_v3_exact_input_single(w3, from_token, to_token, amount)
            if amount_out is None or amount_out <= 0:
                logger.error("Uniswap V3 quote unavailable for fallback unwind")
                return None

            # Ensure allowance for Uniswap V3 router before building tx
            allowance_result = self.ensure_allowance(from_token, UNISWAP_V3_SWAP_ROUTER02_BASE, amount)
            if not allowance_result or (allowance_result.get('status') == 0):
                logger.error("Approval orchestration failed for Uniswap V3 fallback")
                return None

            # Re-read allowance after approval to ensure it's effective
            from eth_account import Account
            account = Account.from_key(PRIVATE_KEY)
            abi = [
                {'name': 'allowance', 'type': 'function', 'stateMutability': 'view',
                 'inputs': [{'name': 'owner', 'type': 'address'}, {'name': 'spender', 'type': 'address'}],
                 'outputs': [{'name': '', 'type': 'uint256'}]}
            ]
            contract = w3.eth.contract(address=Web3.to_checksum_address(from_token), abi=abi)
            current_allowance = contract.functions.allowance(Web3.to_checksum_address(WALLET_ADDRESS), Web3.to_checksum_address(UNISWAP_V3_SWAP_ROUTER02_BASE)).call()
            if current_allowance < amount:
                logger.error(f"Allowance still insufficient after approval: {current_allowance} < {amount}")
                return None

            effective_slippage = float(slippage if slippage is not None else MAX_SLIPPAGE_PERCENT)
            min_out = int(amount_out * max(0.0, (100.0 - effective_slippage) / 100.0))
            selector = Web3.keccak(text='exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))')[:4]
            params_encoded = encode(
                ['address', 'address', 'uint24', 'address', 'uint256', 'uint256', 'uint160'],
                [Web3.to_checksum_address(from_token), Web3.to_checksum_address(to_token), UNISWAP_V3_FEE_TIER, Web3.to_checksum_address(WALLET_ADDRESS), int(amount), int(min_out), 0]
            )
            data = '0x' + (selector + params_encoded).hex()
            gas_estimate = int(w3.eth.estimate_gas({
                'from': Web3.to_checksum_address(WALLET_ADDRESS),
                'to': Web3.to_checksum_address(UNISWAP_V3_SWAP_ROUTER02_BASE),
                'data': data,
                'value': 0,
            }) * 1.2)
            return {
                'tx': {
                    'from': WALLET_ADDRESS,
                    'to': UNISWAP_V3_SWAP_ROUTER02_BASE,
                    'data': data,
                    'value': '0',
                    'gas': gas_estimate,
                },
                'to_amount': str(amount_out),
                'from_amount': amount,
                'protocols': ['uniswap_v3_fallback_exact_input_single'],
                'dst_token': to_token,
                'src_token': from_token,
                'semantic_provider': 'uniswap_v3_fallback',
            }
        except Exception as e:
            logger.error(f"Failed to build Uniswap V3 fallback swap: {e}")
            return None

    def _quote_uniswap_v3_exact_input_single(self, w3: Web3, from_token: str, to_token: str, amount: int) -> Optional[int]:
        selector = Web3.keccak(text='quoteExactInputSingle((address,address,uint256,uint24,uint160))')[:4]
        params_encoded = encode(
            ['address', 'address', 'uint256', 'uint24', 'uint160'],
            [Web3.to_checksum_address(from_token), Web3.to_checksum_address(to_token), int(amount), UNISWAP_V3_FEE_TIER, 0]
        )
        call_data = '0x' + (selector + params_encoded).hex()
        result = w3.eth.call({'to': Web3.to_checksum_address(UNISWAP_V3_QUOTER_V2_BASE), 'data': call_data})
        if not result:
            return None
        return int.from_bytes(result[:32], 'big')

    def get_swap_data(
        self,
        from_token: str,
        to_token: str,
        amount: int,
        slippage: float = None,
        enforce_semantic_unwind: bool = False,
    ) -> Optional[Dict]:
        """
        Get swap transaction data from 1inch

        Returns tx data that can be signed and sent
        """
        if not self.enabled:
            logger.error("Live trading not enabled")
            return None

        try:
            approve_response = requests.get(
                f'{self.base_url}/approve/spender',
                headers=self.headers,
                timeout=15
            )
            spender = approve_response.json().get('address') if approve_response.ok else '0x1111111254eeb25477b68fb85ed929f73a960582'
            allowance_result = self.ensure_allowance(from_token, spender, amount)
            logger.info(f"Allowance result: {allowance_result}")
            if not allowance_result or (allowance_result.get('status') == 0):
                logger.error("Approval orchestration failed before swap")
                return None

            params = {
                'src': from_token,
                'dst': to_token,
                'amount': str(amount),
                'from': WALLET_ADDRESS,
                'slippage': slippage or MAX_SLIPPAGE_PERCENT,
                'disableEstimate': 'false',
                'allowPartialFill': 'false'
            }

            response = requests.get(
                f'{self.base_url}/swap',
                headers=self.headers,
                params=params,
                timeout=15
            )

            if response.status_code == 429:
                logger.error("1inch rate limit hit")
                return None
            if response.status_code >= 400:
                logger.error(f"1inch swap error: status={response.status_code} url={response.url}")
                logger.error(f"1inch swap error body: {response.text}")
                logger.error(f"1inch swap params: src={from_token[:20]}... dst={to_token[:20]}... amount={amount} chain={CHAIN_ID}")
                response.raise_for_status()
            data = response.json()

            swap_data = {
                'tx': data.get('tx'),
                'to_amount': data.get('toAmount'),
                'from_amount': amount,
                'protocols': data.get('protocols', []),
                'dst_token': to_token,
                'src_token': from_token,
                'semantic_provider': '1inch',
            }

            if enforce_semantic_unwind and from_token.lower() == WETH_ADDRESS.lower() and to_token.lower() == USDC_ADDRESS.lower():
                fallback = self._build_uniswap_v3_exact_input_single_tx(from_token, to_token, amount, slippage)
                if fallback:
                    logger.info("Using Uniswap V3 fallback unwind path for WETH->USDC semantic exit")
                    return fallback

            return swap_data

        except requests.exceptions.RequestException as e:
            logger.error(f"1inch swap error: {e}")
            return None

    def validate_swap(self, swap_data: Dict) -> bool:
        """Validate swap data before execution"""
        if not swap_data or 'tx' not in swap_data:
            return False

        tx = swap_data['tx']

        required = ['to', 'data', 'value', 'gas']
        if not all(k in tx for k in required):
            logger.error(f"Missing tx fields: {tx}")
            return False

        if not tx['to'].startswith('0x'):
            logger.error(f"Invalid to address: {tx['to']}")
            return False

        return True

    def execute_swap(self, swap_data: Dict) -> Optional[str]:
        """Execute a swap transaction by sanitizing tx data for Base/Web3."""
        if not self.validate_swap(swap_data):
            return None

        tx = swap_data['tx']

        try:
            w3 = self._get_web3()
            account = self._get_account()

            nonce = w3.eth.get_transaction_count(WALLET_ADDRESS, 'pending')
            latest_block = w3.eth.get_block('latest')
            base_fee = latest_block.get('baseFeePerGas', w3.eth.gas_price)
            network_gas = int(w3.eth.gas_price)
            priority_fee = max(w3.to_wei(0.005, 'gwei'), int(network_gas * 0.1))
            max_fee = max(int(base_fee * 3 + priority_fee), int(tx.get('gasPrice', network_gas)) * 2, network_gas * 2)

            transaction = {
                'chainId': CHAIN_ID,
                'nonce': nonce,
                'to': Web3.to_checksum_address(tx['to']),
                'data': tx['data'],
                'value': int(tx.get('value', 0)),
                'gas': int(tx.get('gas', 300000)),
                'maxPriorityFeePerGas': priority_fee,
                'maxFeePerGas': max_fee,
                'type': 2,
            }

            signed_tx = account.sign_transaction(transaction)
            raw_tx = getattr(signed_tx, 'raw_transaction', None) or getattr(signed_tx, 'rawTransaction')
            tx_hash = w3.eth.send_raw_transaction(raw_tx)
            tx_hash_hex = tx_hash.hex()

            logger.info(
                "SWAP EXECUTED",
                extra={
                    'type': 'swap_executed',
                    'data': {
                        'tx_hash': tx_hash_hex,
                        'to': tx['to'],
                        'value': tx['value'],
                        'gas': tx['gas'],
                        'semantic_provider': swap_data.get('semantic_provider', 'unknown'),
                    }
                }
            )

            return tx_hash_hex

        except Exception as e:
            logger.error(f"Transaction execution failed: {e}; tx={tx}")
            return None

    def check_transaction_status(self, tx_hash: str) -> Optional[Dict]:
        """Check if a transaction has been confirmed"""
        try:
            w3 = self._get_web3()
            receipt = w3.eth.get_transaction_receipt(tx_hash)

            if receipt:
                return {
                    'confirmed': True,
                    'status': 'success' if receipt['status'] == 1 else 'failed',
                    'block_number': receipt['blockNumber'],
                    'gas_used': receipt['gasUsed']
                }
            else:
                return {'confirmed': False}

        except Exception as e:
            logger.error(f"Failed to check transaction status: {e}")
            return None


# Global instance
live_executor = LiveExecutor()
