#!/usr/bin/env python3
"""Analyze ETH/WETH reversal structure from CoinGecko market-chart data."""
import json
import statistics
import urllib.request
from dataclasses import dataclass, asdict
from typing import List

URL = 'https://api.coingecko.com/api/v3/coins/ethereum/market_chart?vs_currency=usd&days={days}'

@dataclass
class Turn:
    kind: str
    index: int
    price: float
    pre_abs: float
    post_abs: float
    pre_pct: float
    post_pct: float
    swing_abs: float
    swing_pct: float


def fetch_prices(days: int = 5):
    with urllib.request.urlopen(URL.format(days=days), timeout=20) as r:
        data = json.load(r)
    return [(ts / 1000.0, float(px)) for ts, px in data['prices']]


def detect_turns(points) -> List[Turn]:
    turns = []
    for i in range(1, len(points) - 1):
        p0 = points[i - 1][1]
        p1 = points[i][1]
        p2 = points[i + 1][1]
        d1 = p1 - p0
        d2 = p2 - p1
        if d1 == 0 or d2 == 0:
            continue
        if d1 > 0 and d2 < 0:
            kind = 'peak'
        elif d1 < 0 and d2 > 0:
            kind = 'trough'
        else:
            continue
        turns.append(Turn(
            kind=kind,
            index=i,
            price=p1,
            pre_abs=abs(d1),
            post_abs=abs(d2),
            pre_pct=abs(d1) / p0 * 100 if p0 else 0.0,
            post_pct=abs(d2) / p1 * 100 if p1 else 0.0,
            swing_abs=abs(d1) + abs(d2),
            swing_pct=(abs(d1) + abs(d2)) / p1 * 100 if p1 else 0.0,
        ))
    return turns


def summarize(turns: List[Turn], min_post_pct: float = 0.15):
    filt = [t for t in turns if t.post_pct >= min_post_pct]
    def stats(vals):
        return {
            'mean': statistics.mean(vals),
            'median': statistics.median(vals),
            'count': len(vals),
        } if vals else {'mean': None, 'median': None, 'count': 0}
    return {
        'turn_count': len(turns),
        'post_pct': stats([t.post_pct for t in turns]),
        'swing_pct': stats([t.swing_pct for t in turns]),
        'filtered_min_post_pct': min_post_pct,
        'filtered_turn_count': len(filt),
        'filtered_post_pct': stats([t.post_pct for t in filt]),
        'filtered_swing_pct': stats([t.swing_pct for t in filt]),
        'sample': [asdict(t) for t in filt[:10]],
    }


def main():
    points = fetch_prices(5)
    turns = detect_turns(points)
    print(json.dumps(summarize(turns), indent=2))


if __name__ == '__main__':
    main()
