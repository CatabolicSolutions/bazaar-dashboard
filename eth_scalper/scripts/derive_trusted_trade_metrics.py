#!/usr/bin/env python3
"""Derive trusted post-fix trade subset + metrics from persisted position state.

Primary purpose:
- identify rows trustworthy enough for realized metrics
- emit machine-readable artifact for dashboard / harness / review

Current trust rule:
- persisted position
- status == closed
- has entry_price, exit_price, pnl_usd, pnl_pct

This is intentionally strict and small.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'eth_scalper' / 'state' / 'persisted_positions.json'
OUT = ROOT / 'out' / 'bloc_trusted_postfix_metrics.json'


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_positions() -> list[dict]:
    if not SOURCE.exists():
        return []
    try:
        obj = json.loads(SOURCE.read_text())
    except Exception:
        return []
    return obj.get('positions', []) if isinstance(obj, dict) else []


def is_trusted(row: dict) -> tuple[bool, str]:
    if row.get('status') != 'closed':
        return False, 'status_not_closed'
    required = ['entry_price', 'exit_price', 'pnl_usd', 'pnl_pct']
    missing = [k for k in required if row.get(k) is None]
    if missing:
        return False, f"missing_fields:{','.join(missing)}"
    return True, 'closed persisted position with entry/exit/pnl fields present'


def main() -> None:
    positions = load_positions()
    trusted = []
    rejected = []

    for row in positions:
        ok, reason = is_trusted(row)
        if ok:
            trusted.append({**row, 'trusted_reason': reason})
        else:
            rejected.append({'id': row.get('id'), 'reason': reason})

    count = len(trusted)
    wins = sum(1 for row in trusted if float(row.get('pnl_usd') or 0) > 0)
    losses = count - wins
    total_pnl_usd = sum(float(row.get('pnl_usd') or 0) for row in trusted) if count else None
    avg_pnl_usd = (total_pnl_usd / count) if count else None
    avg_pnl_pct = (sum(float(row.get('pnl_pct') or 0) for row in trusted) / count) if count else None

    out = {
        'generated_at': now_iso(),
        'source': str(SOURCE.relative_to(ROOT)),
        'source_count': len(positions),
        'trusted_count': count,
        'trusted_ids': [row.get('id') for row in trusted],
        'metrics': {
            'trade_count': count,
            'wins': wins,
            'losses': losses,
            'win_rate': (wins / count) if count else None,
            'total_pnl_usd': total_pnl_usd,
            'avg_pnl_usd': avg_pnl_usd,
            'avg_pnl_pct': avg_pnl_pct,
            'best_pnl_usd': max((float(row.get('pnl_usd') or 0) for row in trusted), default=None),
            'worst_pnl_usd': min((float(row.get('pnl_usd') or 0) for row in trusted), default=None),
        },
        'trusted_rows': trusted,
        'rejected_rows': rejected,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print(json.dumps(out['metrics'], indent=2))


if __name__ == '__main__':
    main()
