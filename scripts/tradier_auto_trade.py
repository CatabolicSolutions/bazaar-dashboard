#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from tradier_board_utils import parse_raw_tickets, top_leaders_by_strategy
from tradier_execution_service import TradierExecutionService

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BOARD = ROOT / 'out' / 'tradier_leaders_board.txt'
DEFAULT_RAW_DIR = ROOT / 'out' / 'tradier_runs'


def latest_raw_run() -> Path | None:
    if not DEFAULT_RAW_DIR.exists():
        return None
    files = sorted(DEFAULT_RAW_DIR.glob('*_raw.txt'))
    return files[-1] if files else None


def load_tickets() -> list[dict[str, Any]]:
    raw_path = latest_raw_run()
    if raw_path and raw_path.exists():
        return parse_raw_tickets(raw_path.read_text(encoding='utf-8'))
    if DEFAULT_BOARD.exists():
        return []
    return []


def select_candidate(tickets: list[dict[str, Any]]) -> dict[str, Any] | None:
    leaders = top_leaders_by_strategy(tickets, limit_per_strategy=5)
    scalps = [t for t in leaders if t.get('strategy') == 'Scalping Buy']
    return scalps[0] if scalps else (leaders[0] if leaders else None)


def main() -> int:
    parser = argparse.ArgumentParser(description='Auto trade top Tradier leader')
    parser.add_argument('--mode', default='cash_day_trade', choices=['cash_day_trade', 'review'])
    parser.add_argument('--qty', type=int, default=1)
    parser.add_argument('--live', action='store_true')
    args = parser.parse_args()

    tickets = load_tickets()
    if not tickets:
        print(json.dumps({'ok': False, 'status': 'no_trade', 'reason': 'NO TRADE — no parsed ticket candidates available'}), flush=True)
        return 1

    candidate = select_candidate(tickets)
    if not candidate:
        print(json.dumps({'ok': False, 'status': 'no_trade', 'reason': 'NO TRADE — no candidate selected'}), flush=True)
        return 1

    service = TradierExecutionService()
    limit_price = candidate.get('mid_price') or candidate.get('ask') or candidate.get('last_price')
    if limit_price is None:
        print(json.dumps({'ok': False, 'status': 'no_trade', 'reason': 'NO TRADE — stale or degraded data'}), flush=True)
        return 1

    intent = service.create_intent_from_leader(candidate, mode=args.mode, qty=args.qty, limit_price=float(limit_price), notes='auto-trade runner')
    decision = service.evaluate_risk(intent, mark_price=float(limit_price))
    if not decision.get('allowed'):
        print(json.dumps({'ok': False, 'status': 'rejected', 'decision': decision}, indent=2), flush=True)
        return 2

    ready = service.mark_intent_ready(intent, readiness_reason='Passed autonomous decision gates')
    preview = service.preview_intent(ready)

    if not args.live:
        print(json.dumps({'ok': True, 'status': 'preview_only', 'intent': ready, 'decision': decision, 'preview': preview}, indent=2), flush=True)
        return 0

    committed = service.record_commit(ready, note='Auto-submitted by tradier_auto_trade')
    print(json.dumps({'ok': True, 'status': 'submitted', 'intent': committed, 'decision': decision, 'preview': preview}, indent=2), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
