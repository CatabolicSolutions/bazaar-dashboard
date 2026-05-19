import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / '.bazaar.env'
POSITIONS_FILE = ROOT / 'state' / 'monitored_positions.json'
REPORT_FILE = ROOT / 'out' / 'position_monitor_report.json'

if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:]
        if '=' in line:
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"\''))

TRADIER_BASE = os.getenv('TRADIER_BASE_URL', 'https://api.tradier.com/v1')
TRADIER_HEADERS = {'Authorization': f"Bearer {os.getenv('TRADIER_API_KEY', '')}", 'Accept': 'application/json'}


@dataclass
class PositionStatus:
    account: str
    symbol: str
    option_symbol: str
    qty: int
    entry_price: float
    current_bid: float
    current_ask: float
    current_mid: float
    underlying_last: float
    pnl_per_contract: float
    pnl_total: float
    pnl_pct: float
    state: str
    narrative: str
    alert_level: str
    alert_reason: str


def load_positions() -> list[dict[str, Any]]:
    if not POSITIONS_FILE.exists():
        return []
    return json.loads(POSITIONS_FILE.read_text())


def quote(symbols: list[str]) -> dict[str, Any]:
    r = requests.get(f'{TRADIER_BASE}/markets/quotes', params={'symbols': ','.join(symbols), 'greeks': 'true'}, headers=TRADIER_HEADERS, timeout=30)
    r.raise_for_status()
    q = r.json()['quotes']['quote']
    if isinstance(q, list):
        return {item['symbol']: item for item in q}
    return {q['symbol']: q}


def evaluate_alert(position: dict[str, Any], mid: float, underlying_last: float) -> tuple[str, str]:
    t = position.get('alert_thresholds', {})
    mode = position.get('mode')
    if mode == 'salvage_pre_earnings':
        if mid <= float(t.get('option_pain_mid', -1)) or underlying_last <= float(t.get('underlying_failure', -1)):
            return 'high', 'damage threshold breached'
        if mid >= float(t.get('option_recovery_mid', 9999)) or underlying_last >= float(t.get('underlying_reclaim', 9999)):
            return 'medium', 'recovery threshold triggered'
        return 'low', 'inside salvage watch band'
    if mode == 'continuation_scalp':
        if mid <= float(t.get('option_pain_mid', -1)) or underlying_last <= float(t.get('underlying_failure', -1)):
            return 'high', 'continuation failure threshold breached'
        if mid >= float(t.get('option_target_mid', 9999)) or underlying_last >= float(t.get('underlying_breakout', 9999)):
            return 'medium', 'continuation target threshold triggered'
        return 'low', 'inside continuation watch band'
    return 'low', 'no explicit threshold logic'


def classify(position: dict[str, Any], option_quote: dict[str, Any], underlying_quote: dict[str, Any]) -> PositionStatus:
    bid = float(option_quote.get('bid') or 0.0)
    ask = float(option_quote.get('ask') or 0.0)
    mid = round((bid + ask) / 2.0, 4) if bid and ask else 0.0
    underlying_last = float(underlying_quote.get('last') or 0.0)
    entry = float(position['entry_price'])
    qty = int(position['qty'])
    pnl_per_contract = round((mid - entry) * 100.0, 2)
    pnl_total = round(pnl_per_contract * qty, 2)
    pnl_pct = round(((mid / entry) - 1.0) * 100.0, 2) if entry > 0 else 0.0

    if pnl_pct >= 40:
        state = 'strong_green'
        narrative = 'Position is materially green; protect gains and only hold if follow-through remains alive.'
    elif pnl_pct >= 10:
        state = 'green'
        narrative = 'Position is working, but open-profit discipline matters.'
    elif pnl_pct > -20:
        state = 'neutral_to_red'
        narrative = 'Position is near flat-to-red; requires real continuation to justify holding.'
    else:
        state = 'damage_control'
        narrative = 'Position is materially impaired; hold only on a specific rebound thesis, not passive hope.'

    alert_level, alert_reason = evaluate_alert(position, mid, underlying_last)
    return PositionStatus(
        account=position['account'], symbol=position['underlying_symbol'], option_symbol=position['option_symbol'], qty=qty,
        entry_price=entry, current_bid=bid, current_ask=ask, current_mid=mid, underlying_last=underlying_last,
        pnl_per_contract=pnl_per_contract, pnl_total=pnl_total, pnl_pct=pnl_pct, state=state,
        narrative=narrative, alert_level=alert_level, alert_reason=alert_reason,
    )


def main():
    positions = load_positions()
    symbols = []
    for p in positions:
        symbols.extend([p['option_symbol'], p['underlying_symbol']])
    quotes = quote(symbols) if symbols else {}
    report = []
    for p in positions:
        report.append(asdict(classify(p, quotes[p['option_symbol']], quotes[p['underlying_symbol']])))
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
