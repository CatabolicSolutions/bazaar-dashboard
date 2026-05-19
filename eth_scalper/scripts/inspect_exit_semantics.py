import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from execution.live_executor import live_executor
from config.settings import WETH_ADDRESS, USDC_ADDRESS
import json

live_executor.enable()
swap = live_executor.get_swap_data(WETH_ADDRESS, USDC_ADDRESS, 443091428857404)
print(json.dumps({
  'src': WETH_ADDRESS,
  'dst': USDC_ADDRESS,
  'amount': 443091428857404,
  'swap_none': swap is None,
  'router_to': None if not swap else swap['tx'].get('to'),
  'tx_value': None if not swap else swap['tx'].get('value'),
  'tx_data_prefix': None if not swap else swap['tx'].get('data','')[:120],
  'to_amount': None if not swap else swap.get('to_amount'),
}, indent=2))
