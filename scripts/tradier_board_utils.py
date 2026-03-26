import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


def parse_ticket_blocks(text: str) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    in_block = False

    for line in text.splitlines():
        stripped = line.strip()
        if stripped == '---TICKET_START---':
            in_block = True
            current = []
            continue
        if stripped == '---TICKET_END---':
            in_block = False
            continue
        if not in_block:
            continue
        if stripped == '---TICKET_DELIMITER---':
            if current:
                blocks.append(current)
                current = []
            continue
        current.append(line.rstrip())

    if current:
        blocks.append(current)
    return blocks


def parse_ticket(block: list[str]) -> dict[str, Any] | None:
    if not block:
        return None
    first = block[0]
    m = re.search(r'^(\[FALLBACK\] )?(.*?) Opportunity for (\w+) \((.*?)\)\*\*$', first)
    if not m:
        return None

    fallback, strategy, symbol, label = m.groups()
    data: dict[str, Any] = {
        'fallback': bool(fallback),
        'strategy': strategy,
        'symbol': symbol,
        'label': label,
    }

    for line in block[1:]:
        s = line.strip()
        if s.startswith('- Underlying Price: $'):
            data['underlying_price'] = float(s.split('$')[1])
        elif s.startswith('- Current VIX: '):
            data['vix'] = float(s.split(': ')[1])
        elif s.startswith('- Type: '):
            data['option_type'] = s.split(': ')[1].lower()
        elif s.startswith('- Strike: $'):
            data['strike'] = float(s.split('$')[1])
        elif s.startswith('- Expiration: '):
            data['expiration'] = s.split(': ')[1]
        elif s.startswith('- Requested DTE: '):
            data['requested_dte'] = int(s.split(': ')[1])
        elif s.startswith('- Actual DTE: '):
            data['actual_dte'] = int(s.split(': ')[1])
        elif s.startswith('- Last Price: $'):
            tail = s.split('$', 1)[1]
            data['last_price'] = None if tail == 'N/A' else float(tail)
        elif s.startswith('- Bid: $'):
            m2 = re.search(r'\$(.*?) / Ask: \$(.*)$', s)
            if m2:
                data['bid'] = float(m2.group(1))
                data['ask'] = float(m2.group(2))
        elif s.startswith('- Delta: '):
            try:
                data['delta'] = float(s.split(': ')[1])
            except ValueError:
                data['delta'] = None
        elif s.startswith('- Spread Ratio: '):
            data['spread_ratio'] = float(s.split(': ')[1].strip('%')) / 100.0
        elif s.startswith('- Expiry Selection Note: '):
            data['expiry_note'] = s.split(': ', 1)[1]

    data['expiry_fallback'] = (
        ('fallback' in data.get('label', '').lower())
        or bool(data.get('expiry_note'))
        or data.get('fallback', False)
    )
    data['mid_price'] = _mid_price(data)
    data['candidate_id'] = candidate_id(data)
    return data


def _mid_price(ticket: dict[str, Any]) -> float | None:
    bid = ticket.get('bid')
    ask = ticket.get('ask')
    if bid is None or ask is None:
        return None
    return round((bid + ask) / 2.0, 4)


def candidate_id(ticket: dict[str, Any]) -> str:
    option_type = str(ticket.get('option_type', '')).upper()
    strike = float(ticket.get('strike', 0.0))
    strike_text = f"{strike:.2f}".rstrip('0').rstrip('.')
    expiry = str(ticket.get('expiration', ''))
    symbol = str(ticket.get('symbol', '')).upper()
    return f"{symbol}-{expiry}-{option_type}-{strike_text}"


def score_ticket(ticket: dict[str, Any]):
    spread_ratio = ticket.get('spread_ratio', 0.99)
    bid = ticket.get('bid', 0.0)
    actual_dte = ticket.get('actual_dte', 99)
    delta = abs(ticket.get('delta') or 0.0)

    if ticket['strategy'] == 'Scalping Buy':
        target_delta = 0.58 if actual_dte <= 1 else 0.62
        return (
            -abs(delta - target_delta),
            -spread_ratio,
            bid,
            -actual_dte,
            0 if ticket.get('expiry_fallback') else 1,
        )

    target_delta = 0.14
    return (
        -abs(delta - target_delta),
        -spread_ratio,
        bid,
        -actual_dte,
        0 if ticket.get('expiry_fallback') else 1,
    )


def build_board(tickets: list[dict[str, Any]]) -> str:
    if not tickets:
        return (
            'BAZAAR OF FORTUNES — TRADIER LEADERS BOARD\n\n'
            'No Trade\n'
            '- No clean leaders passed the current filters\n'
            '- Best action: wait for cleaner structure or rerun on the next cycle\n'
        )

    leaders: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ticket in tickets:
        leaders[ticket['strategy']].append(ticket)

    for strategy in leaders:
        leaders[strategy].sort(key=score_ticket, reverse=True)

    lines: list[str] = []
    vix = tickets[0].get('vix', 'N/A')
    lines.append('BAZAAR OF FORTUNES — TRADIER LEADERS BOARD')
    lines.append(f'VIX: {vix}')
    lines.append('')

    strategy_order = ['Scalping Buy', 'Credit Spread Sell']
    pretty_names = {
        'Scalping Buy': 'Directional / Scalping Leaders',
        'Credit Spread Sell': 'Premium / Credit Leaders',
    }

    for strategy in strategy_order:
        if strategy not in leaders or not leaders[strategy]:
            continue
        lines.append(pretty_names[strategy])
        for idx, ticket in enumerate(leaders[strategy][:5], start=1):
            fallback_note = ' [fallback-expiry]' if ticket.get('expiry_fallback') else ''
            lines.append(
                f"{idx}. {ticket['symbol']} {ticket['option_type'].upper()} | Underlying {ticket.get('underlying_price', 0.0):.2f} | "
                f"Strike {ticket['strike']:.2f} | Exp {ticket['expiration']} | {ticket['label']} | "
                f"Δ {ticket.get('delta', 0.0):.4f} | Bid/Ask {ticket.get('bid', 0.0):.2f}/{ticket.get('ask', 0.0):.2f}{fallback_note}"
            )
            lines.append(f"   Candidate ID: {ticket['candidate_id']}")
            if strategy == 'Scalping Buy':
                lines.append('   Thesis: best near-ATM momentum leader in current pass')
                lines.append('   Entry: only on confirmation / momentum continuation')
                lines.append('   Invalidation: fail on momentum / hard stop discipline required')
                lines.append('   Targets: T1 quick scale, T2 momentum extension, T3 runner only if trend persists')
                lines.append(f"   Confidence: {7 if not ticket.get('expiry_fallback') else 5}/10 — liquidity/structure driven, downgraded if fallback expiry")
                lines.append('   Risk: defined-risk premium outlay; avoid size creep')
            else:
                lines.append('   Thesis: best OTM premium candidate in the current delta/liquidity band')
                lines.append('   Entry: only as a defined-risk spread, not naked premium')
                lines.append('   Invalidation: abandon if structure requires chasing or volatility regime shifts against the setup')
                lines.append('   Targets: T1 25-35% capture, T2 50% capture, T3 hold only if risk remains contained')
                lines.append(f"   Confidence: {8 if not ticket.get('expiry_fallback') else 6}/10 — clean spread/delta profile, downgraded if fallback expiry")
                lines.append('   Risk: manage in R; premium collection is not a license to overstay')
            if ticket.get('expiry_note'):
                lines.append(f"   Note: {ticket['expiry_note']}")
        lines.append('')

    fallback_count = sum(1 for t in tickets if t.get('expiry_fallback'))
    lines.append('Run Notes')
    lines.append(f'- Leaders emitted: {len(tickets)}')
    lines.append(f'- Fallback-expiry leaders: {fallback_count}')
    if fallback_count:
        lines.append('- Interpret fallback-expiry leaders as second-best structural representations, not literal requested-DTE matches')
    else:
        lines.append('- All leaders matched requested expiry intent directly')

    return '\n'.join(lines).strip() + '\n'


def parse_raw_tickets(text: str) -> list[dict[str, Any]]:
    blocks = parse_ticket_blocks(text)
    tickets = [parse_ticket(block) for block in blocks]
    return [t for t in tickets if t]


def top_leaders_by_strategy(tickets: list[dict[str, Any]], limit_per_strategy: int = 5) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ticket in tickets:
        grouped[ticket['strategy']].append(ticket)
    out: list[dict[str, Any]] = []
    for strategy in ['Scalping Buy', 'Credit Spread Sell']:
        strategy_tickets = sorted(grouped.get(strategy, []), key=score_ticket, reverse=True)
        out.extend(strategy_tickets[:limit_per_strategy])
    return out


def save_json(path: str | Path, data: Any) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write('\n')
