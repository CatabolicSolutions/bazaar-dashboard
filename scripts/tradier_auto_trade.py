#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from tradier_board_utils import parse_raw_tickets, top_leaders_by_strategy
from tradier_execution_service import TradierExecutionService
from tradier_execution import post_order, occ_option_symbol
from engine_lifecycle import emit_event

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BOARD = ROOT / 'out' / 'tradier_leaders_board.txt'
DEFAULT_RAW_DIR = ROOT / 'out' / 'tradier_runs'


def latest_raw_run() -> Path | None:
    if not DEFAULT_RAW_DIR.exists():
        return None
    patterns = ['*_raw.txt', '*.raw.txt', '*raw*.txt']
    files = []
    for pattern in patterns:
        files.extend(DEFAULT_RAW_DIR.glob(pattern))
    files = sorted(set(files))
    return files[-1] if files else None


def load_tickets() -> list[dict[str, Any]]:
    raw_path = latest_raw_run()
    if raw_path and raw_path.exists():
        tickets = parse_raw_tickets(raw_path.read_text(encoding='utf-8'))
        if tickets:
            return tickets
    if DEFAULT_BOARD.exists():
        board_text = DEFAULT_BOARD.read_text(encoding='utf-8')
        try:
            import re
            lines = [line.strip() for line in board_text.splitlines() if line.strip()]
            tickets = []
            current_strategy = 'Scalping Buy'
            line_re = re.compile(r'^(\d+)\.\s+([A-Z]+)\s+(CALL|PUT)\s+\|\s+Underlying\s+([0-9.]+)\s+\|\s+Strike\s+([0-9.]+)\s+\|\s+Exp\s+([0-9\-]+)\s+\|.*?Bid/Ask\s+([0-9.]+)/([0-9.]+)')
            for line in lines:
                if 'Premium / Credit Leaders' in line:
                    current_strategy = 'Credit'
                    continue
                if 'Directional / Scalping Leaders' in line:
                    current_strategy = 'Scalping Buy'
                    continue
                match = line_re.match(line)
                if not match:
                    continue
                _, symbol, option_type, underlying, strike, expiration, bid, ask = match.groups()
                underlying = float(underlying)
                strike = float(strike)
                bid = float(bid)
                ask = float(ask)
                tickets.append({
                    'symbol': symbol,
                    'option_type': option_type.lower(),
                    'underlying_price': underlying,
                    'strike': strike,
                    'expiration': expiration,
                    'bid': bid,
                    'ask': ask,
                    'mid_price': round((bid + ask) / 2, 2),
                    'strategy': 'Scalping Buy' if current_strategy != 'Credit' else 'Credit',
                    'contract': f"{symbol} {strike} {option_type.upper()} {expiration}",
                })
            return tickets
        except Exception:
            return []
    return []


MAX_OPTION_PREMIUM = 1.50
MAX_TOTAL_NOTIONAL = 175.00
ALLOWED_UNDERLYINGS = {'SPY', 'QQQ', 'IWM', 'DIA', 'NVDA', 'AAPL', 'MSFT', 'TSLA', 'AMD', 'META', 'AMZN'}


def candidate_gate_reasons(candidate: dict[str, Any], qty: int) -> list[str]:
    reasons = []
    symbol = str(candidate.get('symbol') or '').upper()
    strategy = str(candidate.get('strategy') or '')
    limit_price = candidate.get('mid_price') or candidate.get('ask') or candidate.get('last_price')
    bid = candidate.get('bid')
    ask = candidate.get('ask')

    if symbol not in ALLOWED_UNDERLYINGS:
        reasons.append('rejected_setup: underlying not in approved universe')
    if strategy != 'Scalping Buy':
        reasons.append('rejected_setup: strategy not approved for auto-entry')
    if limit_price is None:
        reasons.append('rejected_setup: missing option premium')
    else:
        if float(limit_price) > MAX_OPTION_PREMIUM:
            reasons.append('rejected_setup: option premium cap exceeded')
        if float(limit_price) * int(qty) * 100.0 > MAX_TOTAL_NOTIONAL:
            reasons.append('rejected_setup: total notional cap exceeded')
    if bid and ask and float(ask) > 0:
        spread_pct = (float(ask) - float(bid)) / float(ask)
        if spread_pct > 0.12:
            reasons.append('rejected_setup: spread cap exceeded')
    return reasons


def select_candidate(tickets: list[dict[str, Any]], qty: int) -> dict[str, Any] | None:
    leaders = top_leaders_by_strategy(tickets, limit_per_strategy=5)
    viable = [t for t in leaders if not candidate_gate_reasons(t, qty)]
    scalps = [t for t in viable if t.get('strategy') == 'Scalping Buy']
    return scalps[0] if scalps else (viable[0] if viable else None)


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

    candidate = select_candidate(tickets, args.qty)
    if not candidate:
        rejected_summary = []
        for ticket in top_leaders_by_strategy(tickets, limit_per_strategy=5):
            rejected_summary.append({
                'symbol': ticket.get('symbol'),
                'contract': ticket.get('contract'),
                'reasons': candidate_gate_reasons(ticket, args.qty),
            })
        print(json.dumps({'ok': False, 'status': 'no_trade', 'reason': 'NO TRADE — no candidate passed mandate filters', 'rejected_candidates': rejected_summary}, indent=2), flush=True)
        return 1
    trade_id = f"tradier-{candidate.get('symbol')}-{candidate.get('expiration')}-{candidate.get('strike')}"
    emit_event(engine='tradier', trade_id=trade_id, stage='detected', outcome_type='info', status='success', data={'candidate': candidate})

    service = TradierExecutionService()
    limit_price = candidate.get('mid_price') or candidate.get('ask') or candidate.get('last_price')
    if limit_price is None:
        print(json.dumps({'ok': False, 'status': 'no_trade', 'reason': 'NO TRADE — stale or degraded data'}), flush=True)
        return 1

    gate_reasons = candidate_gate_reasons(candidate, args.qty)
    if gate_reasons:
        emit_event(engine='tradier', trade_id=trade_id, stage='rejected', outcome_type='rejected_setup', status='failure', notes='; '.join(gate_reasons), data={'reasons': gate_reasons})
        print(json.dumps({'ok': False, 'status': 'rejected', 'reasons': gate_reasons}, indent=2), flush=True)
        return 2

    intent = service.create_intent_from_leader(candidate, mode=args.mode, qty=args.qty, limit_price=float(limit_price), notes='auto-trade runner')
    decision = service.evaluate_risk(intent, mark_price=float(limit_price))
    if not decision.get('allowed'):
        emit_event(engine='tradier', trade_id=trade_id, stage='rejected', outcome_type='rejected_setup', status='failure', notes='risk_controls_rejected', data={'decision': decision})
        print(json.dumps({'ok': False, 'status': 'rejected', 'decision': decision}, indent=2), flush=True)
        return 2

    ready = service.mark_intent_ready(intent, reason='Passed autonomous decision gates')
    emit_event(engine='tradier', trade_id=trade_id, stage='qualified', outcome_type='info', status='success', data={'intent_id': ready.get('intent_id')})
    preview = service.preview_intent(
        ready,
        expiry=str(candidate.get('expiration') or candidate.get('exp')),
        option_type=str(candidate.get('option_type')),
        strike=float(candidate.get('strike')),
    )

    emit_event(engine='tradier', trade_id=trade_id, stage='previewed', outcome_type='info', status='success', data={'preview': preview})
    if not args.live:
        print(json.dumps({'ok': True, 'status': 'preview_only', 'intent': ready, 'decision': decision, 'preview': preview}, indent=2), flush=True)
        return 0

    expiry = candidate.get('expiration') or candidate.get('exp')
    option_type = (candidate.get('option_type') or '').lower()
    strike = float(candidate.get('strike'))
    option_symbol = occ_option_symbol(candidate['symbol'], str(expiry), option_type, strike)
    payload = {
        'class': 'option',
        'symbol': candidate['symbol'].upper(),
        'option_symbol': option_symbol,
        'side': 'buy_to_open',
        'quantity': args.qty,
        'type': 'limit',
        'duration': 'day',
        'tag': f"auto-{ready['intent_id']}",
        'price': float(limit_price),
    }
    emit_event(engine='tradier', trade_id=trade_id, stage='submitted', outcome_type='info', status='success', data={'payload': payload})
    broker_response = post_order(payload, preview=False)
    committed = service.record_commit(ready, broker_response)
    emit_event(engine='tradier', trade_id=trade_id, stage='filled', outcome_type='info', status='success', data={'broker_response': broker_response})
    print(json.dumps({'ok': True, 'status': 'submitted', 'intent': committed, 'decision': decision, 'preview': preview, 'broker_response': broker_response}, indent=2), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
