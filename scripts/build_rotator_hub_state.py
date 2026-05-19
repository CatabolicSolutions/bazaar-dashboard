import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'out' / 'rotator_hub_state.json'
SSH_KEY = '/home/catabolic_solutions/.ssh/alfred_deploy_key'
HOST = 'root@137.184.144.196'

CMD = r'''cd /var/www/uniswap_rotator && PYTHONPATH=/var/www/uniswap_rotator python3 - <<"PY"
from runtime.integrations.env import load_runtime_env
from runtime.integrations.wallets import RpcWalletReader
import json
from pathlib import Path

env = load_runtime_env()
reader = RpcWalletReader(env.wallet_config())
state = json.loads(Path("runtime_data/state/rotator_state.json").read_text())
ledger_path = Path("runtime_data/ledger/trade_ledger.jsonl")
rows = [json.loads(line) for line in ledger_path.read_text().splitlines() if line.strip()] if ledger_path.exists() else []
snap = reader.build_snapshot(eth_price=0, cbbtc_price=0)
recent = rows[-5:]
print(json.dumps({
  "current_side": state.get("side"),
  "target_side": state.get("target_side") or state.get("side"),
  "balances": {"weth": snap.weth, "cbbtc": snap.cbbtc, "usdc": snap.usdc},
  "portfolio_value_usd": state.get("portfolio_usd", 0.0),
  "status": state.get("status") or "live",
  "posture": state.get("last_reason") or "monitoring live rotation state",
  "latest_alert": state.get("last_signal") or "NONE",
  "recent_performance": {
    "trade_count": len(rows),
    "usd_delta_total": round(sum(float(r.get("usd_delta", 0.0)) for r in rows), 4),
    "recent_trades": recent,
  }
}, indent=2))
PY'''

res = subprocess.run(['ssh', '-i', SSH_KEY, HOST, CMD], capture_output=True, text=True, check=True)
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(res.stdout, encoding='utf-8')
print(res.stdout)
