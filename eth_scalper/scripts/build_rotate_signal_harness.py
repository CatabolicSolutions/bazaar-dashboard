#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[2]
ETH_PATH = ROOT / 'eth_scalper' / 'out_eth_market_chart_30d.json'
BTC_PATH = ROOT / 'eth_scalper' / 'out_btc_market_chart_30d.json'
OUT_DIR = ROOT / 'out'
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = OUT_DIR / 'rotate_signal_probe.json'

FEE = 0.0005
FEE_FACTOR = 1 - FEE
HORIZONS = [3, 6, 12, 24]

@dataclass
class Probe:
    idx: int
    ts: int
    signal: str
    spread_move_pct: float
    spread_z_like: float
    eth_mom_pct: float
    btc_mom_pct: float
    alt_advantage_now_pct: float
    horizon: int
    rotate_win_pct: float


def load(path: Path):
    obj = json.loads(path.read_text())
    return obj['prices']


def main():
    eth = load(ETH_PATH)
    btc = load(BTC_PATH)
    n = min(len(eth), len(btc))
    rows = []
    for i in range(n):
        rows.append({'ts': int(eth[i][0]), 'ETH': float(eth[i][1]), 'BTC': float(btc[i][1])})

    spreads = [r['ETH']/r['BTC'] for r in rows]
    probes = []
    for i in range(24, n - max(HORIZONS)):
        spread = spreads[i]
        prev = spreads[i-1]
        look = spreads[max(0, i-12):i]
        anchor = mean(look)
        anchor_dev_pct = ((spread - anchor) / anchor * 100.0) if anchor else 0.0
        spread_move_pct = ((spread - prev) / prev * 100.0) if prev else 0.0
        eth_mom = ((rows[i]['ETH'] - rows[i-3]['ETH']) / rows[i-3]['ETH'] * 100.0) if rows[i-3]['ETH'] else 0.0
        btc_mom = ((rows[i]['BTC'] - rows[i-3]['BTC']) / rows[i-3]['BTC'] * 100.0) if rows[i-3]['BTC'] else 0.0
        signal = 'ROTATE_TO_BTC' if anchor_dev_pct > 0 and spread_move_pct > 0 and btc_mom > eth_mom else ('ROTATE_TO_ETH' if anchor_dev_pct < 0 and spread_move_pct < 0 and eth_mom > btc_mom else 'NONE')
        if signal == 'NONE':
            continue
        alt_advantage = (btc_mom - eth_mom) if signal == 'ROTATE_TO_BTC' else (eth_mom - btc_mom)
        for h in HORIZONS:
            eth_hold = rows[i+h]['ETH'] / rows[i]['ETH']
            btc_hold_eth_equiv = rows[i+h]['BTC'] / rows[i]['BTC']
            if signal == 'ROTATE_TO_BTC':
                rotate_value = (rows[i+h]['BTC'] / rows[i]['BTC']) * (FEE_FACTOR ** 2)
                hold_value = eth_hold
            else:
                rotate_value = (rows[i+h]['ETH'] / rows[i]['ETH']) * (FEE_FACTOR ** 2)
                hold_value = btc_hold_eth_equiv
            rotate_win_pct = ((rotate_value - hold_value) / hold_value * 100.0) if hold_value else 0.0
            probes.append(Probe(i, rows[i]['ts'], signal, spread_move_pct, anchor_dev_pct, eth_mom, btc_mom, alt_advantage, h, rotate_win_pct))

    summary = {}
    for signal in ('ROTATE_TO_BTC', 'ROTATE_TO_ETH'):
        subset = [p for p in probes if p.signal == signal]
        summary[signal] = {}
        for h in HORIZONS:
            sh = [p.rotate_win_pct for p in subset if p.horizon == h]
            if not sh:
                continue
            summary[signal][str(h)] = {
                'count': len(sh),
                'mean_rotate_win_pct': mean(sh),
                'win_rate_pct': sum(1 for x in sh if x > 0) / len(sh) * 100.0,
            }

    out = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'horizons': HORIZONS,
        'summary': summary,
        'sample': [asdict(p) for p in probes[:40]],
    }
    OUT_PATH.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))

if __name__ == '__main__':
    main()
