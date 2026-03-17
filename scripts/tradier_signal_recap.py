import argparse
import json
import os
from datetime import datetime
from pathlib import Path

import requests

RUNS_DIR = Path.home() / '.openclaw' / 'workspace' / 'out' / 'tradier_runs'
BASE_URL = 'https://api.tradier.com/v1/markets/'
TRADIER_API_KEY = os.getenv('TRADIER_API_KEY')
HEADERS = {
    'Accept': 'application/json',
    'Authorization': f'Bearer {TRADIER_API_KEY}'
} if TRADIER_API_KEY else {}


def load_runs(limit: int):
    if not RUNS_DIR.exists():
        return []
    runs = sorted(RUNS_DIR.glob('*/run.json'), reverse=True)
    loaded = []
    for run_path in runs[:limit]:
        with open(run_path, 'r', encoding='utf-8') as f:
            loaded.append(json.load(f))
    return loaded


def get_latest_quote(symbol: str):
    if not TRADIER_API_KEY:
        return None
    url = f'{BASE_URL}quotes'
    params = {'symbols': symbol, 'greeks': 'false'}
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=20)
        response.raise_for_status()
        data = response.json()
        quote = data.get('quotes', {}).get('quote')
        if not quote:
            return None
        return float(quote.get('last'))
    except Exception:
        return None


def pct(a, b):
    if a in (None, 0) or b is None:
        return None
    return ((b - a) / a) * 100.0


def build_report(runs):
    if not runs:
        return 'TRADIER SIGNAL RECAP\n\nNo archived runs found yet.\n'

    lines = []
    lines.append('TRADIER SIGNAL RECAP')
    lines.append('')
    lines.append('Method: compare archived leaders against latest available underlying quote.')
    lines.append('This is a v1 scorecard on direction/timing usefulness, not a full options P/L engine yet.')
    lines.append('')

    for run in runs:
        lines.append(f"Run: {run['run_id']}")
        lines.append(f"Generated: {run['generated_at']}")
        lines.append(f"Leaders archived: {len(run.get('leaders', []))}")
        for leader in run.get('leaders', []):
            latest = get_latest_quote(leader['symbol'])
            move_pct = pct(leader.get('underlying_price'), latest)
            direction = 'UP' if move_pct is not None and move_pct > 0 else 'DOWN' if move_pct is not None and move_pct < 0 else 'FLAT/NA'
            lines.append(
                f"- {leader['strategy']} | {leader['symbol']} {leader['option_type'].upper()} {leader['strike']:.2f} exp {leader['expiration']}"
            )
            lines.append(
                f"  Then: underlying {leader.get('underlying_price', 0.0):.2f} | bid/ask {leader.get('bid', 0.0):.2f}/{leader.get('ask', 0.0):.2f}"
            )
            if latest is None:
                lines.append('  Now: latest quote unavailable')
            else:
                lines.append(
                    f"  Now: underlying {latest:.2f} | move {move_pct:+.2f}% | direction check {direction}"
                )
        lines.append('')

    return '\n'.join(lines).strip() + '\n'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=5)
    args = parser.parse_args()

    runs = load_runs(args.limit)
    print(build_report(runs))


if __name__ == '__main__':
    main()
