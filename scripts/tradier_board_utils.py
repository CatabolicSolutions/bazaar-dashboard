import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

MAX_LEADERS_TOTAL = 3
MIN_DIRECTIONAL_CONVICTION = 55.0
MIN_ASYMMETRY_SCORE = 50.0
MIN_EXECUTION_QUALITY = 50.0
MAX_ACCEPTABLE_SPREAD_RATIO = 0.35
MIN_BID_FOR_LEADER = 0.05


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
        elif s.startswith('- Setup Family: '):
            data['setup_family'] = s.split(': ', 1)[1]
        elif s.startswith('- Structure Score: '):
            data['structure_score'] = float(s.split(': ', 1)[1])
        elif s.startswith('- Confidence Score: '):
            data['confidence_score'] = int(s.split(': ', 1)[1].split('/')[0])
        elif s.startswith('- Liquidity Score: '):
            data['liquidity_score'] = float(s.split(': ', 1)[1])
        elif s.startswith('- Expiry Quality Score: '):
            data['expiry_quality_score'] = float(s.split(': ', 1)[1])
        elif s.startswith('- Delta Fit Score: '):
            data['delta_fit_score'] = float(s.split(': ', 1)[1])
        elif s.startswith('- Distance Score: '):
            data['distance_score'] = float(s.split(': ', 1)[1])
        elif s.startswith('- VIX Regime: '):
            data['vix_regime'] = s.split(': ', 1)[1]
        elif s.startswith('- Narrative: '):
            data['narrative'] = s.split(': ', 1)[1]
        elif s.startswith('- Expectations: '):
            data['expectations'] = s.split(': ', 1)[1]
        elif s.startswith('- Invalidation: '):
            data['invalidation'] = s.split(': ', 1)[1]
        elif s.startswith('- Risk Profile: '):
            data['risk_profile'] = s.split(': ', 1)[1]
        elif s.startswith('- Selection Reason: '):
            data['selection_reason'] = s.split(': ', 1)[1]
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


def quality_components(ticket: dict[str, Any]) -> dict[str, Any]:
    spread_ratio = float(ticket.get('spread_ratio') or 0.99)
    bid = float(ticket.get('bid') or 0.0)
    ask = float(ticket.get('ask') or 0.0)
    mid = float(ticket.get('mid_price') or 0.0)
    actual_dte = int(ticket.get('actual_dte') or 99)
    requested_dte = int(ticket.get('requested_dte') or actual_dte)
    delta = abs(float(ticket.get('delta') or 0.0))
    fallback_penalty = 12 if ticket.get('expiry_fallback') else 0
    spread_score = max(0.0, 20.0 - min(spread_ratio, 1.0) * 60.0)
    premium_score = min(mid * 1.2, 12.0)
    dte_penalty = max(0, actual_dte - requested_dte) * 3.0

    if ticket['strategy'] == 'Scalping Buy':
        target_delta = 0.58 if actual_dte <= 1 else 0.62
        delta_score = max(0.0, 20.0 - abs(delta - target_delta) * 90.0)
        structure_score = max(0.0, 45.0 + spread_score + premium_score + delta_score - fallback_penalty - dte_penalty)
        setup_family = 'directional_momentum'
        narrative = 'Liquid near-ATM directional expression with strong delta efficiency; requires real momentum confirmation before entry.'
        expectations = 'Best used when price confirms continuation and intraday follow-through is present; avoid dead tape or late chasing.'
        invalidation = 'Momentum fails, tape stalls, or spread deteriorates beyond acceptable execution quality.'
        target_text = 'T1 quick scale, T2 momentum extension, T3 runner only if trend and tape quality persist.'
    else:
        target_delta = 0.14
        delta_score = max(0.0, 20.0 - abs(delta - target_delta) * 180.0)
        structure_score = max(0.0, 45.0 + spread_score + premium_score + delta_score - fallback_penalty - dte_penalty)
        setup_family = 'defined_risk_premium'
        narrative = 'OTM premium candidate with cleaner delta/liquidity structure, suitable only inside a defined-risk spread framework.'
        expectations = 'Best used when the underlying is stable-to-favorable and implied risk does not demand chasing or over-sizing.'
        invalidation = 'Volatility regime shifts, structure widens, or the spread no longer offers favorable defined-risk capture.'
        target_text = 'T1 25-35% capture, T2 50% capture, T3 only while risk remains clearly contained.'

    confidence = max(1, min(10, round((structure_score - 35.0) / 6.0)))
    return {
        'spread_score': round(spread_score, 2),
        'premium_score': round(premium_score, 2),
        'delta_score': round(delta_score, 2),
        'fallback_penalty': fallback_penalty,
        'dte_penalty': round(dte_penalty, 2),
        'structure_score': round(structure_score, 2),
        'confidence': confidence,
        'setup_family': setup_family,
        'narrative': narrative,
        'expectations': expectations,
        'invalidation': invalidation,
        'targets': target_text,
    }


def leader_components(ticket: dict[str, Any]) -> dict[str, Any]:
    qc = quality_components(ticket)
    spread_ratio = float(ticket.get('spread_ratio') or 0.99)
    bid = float(ticket.get('bid') or 0.0)
    ask = float(ticket.get('ask') or 0.0)
    mid = float(ticket.get('mid_price') or 0.0)
    underlying = float(ticket.get('underlying_price') or 0.0)
    delta = abs(float(ticket.get('delta') or 0.0))
    actual_dte = int(ticket.get('actual_dte') or 99)
    strategy = ticket.get('strategy')

    directional_conviction = 0.0
    asymmetry = 0.0
    execution_quality = 0.0
    invalidation_clarity = 0.0
    tactical_timing = 0.0

    if strategy == 'Scalping Buy':
        directional_conviction = min(100.0, 35.0 + qc['delta_score'] * 1.7 + qc['spread_score'] * 0.6)
        asymmetry = min(100.0, 30.0 + qc['premium_score'] * 2.0 + max(0.0, 12.0 - mid) * 2.5)
        tactical_timing = min(100.0, 45.0 + max(0.0, 20.0 - actual_dte * 2.5) + qc['delta_score'] * 0.7)
    else:
        directional_conviction = min(100.0, 28.0 + qc['delta_score'] * 1.2 + qc['spread_score'] * 0.5)
        asymmetry = min(100.0, 38.0 + qc['premium_score'] * 1.4 + max(0.0, 16.0 - abs(delta - 0.14) * 100.0) * 1.4)
        tactical_timing = min(100.0, 40.0 + max(0.0, 18.0 - actual_dte * 1.8) + qc['spread_score'] * 0.8)

    execution_quality = min(100.0, 35.0 + qc['spread_score'] * 1.8 + qc['premium_score'] * 1.5 + min(bid, 5.0) * 4.0)
    invalidation_clarity = 70.0 if ticket.get('invalidation') else 35.0
    if spread_ratio > MAX_ACCEPTABLE_SPREAD_RATIO or bid < MIN_BID_FOR_LEADER or ask <= 0 or underlying <= 0:
        hard_reject = True
    else:
        hard_reject = False
    leader_score = round(
        directional_conviction * 0.35
        + asymmetry * 0.25
        + execution_quality * 0.20
        + invalidation_clarity * 0.10
        + tactical_timing * 0.10,
        2,
    )
    hard_reject = hard_reject or directional_conviction < MIN_DIRECTIONAL_CONVICTION or asymmetry < MIN_ASYMMETRY_SCORE or execution_quality < MIN_EXECUTION_QUALITY
    return {
        'directional_conviction': round(directional_conviction, 2),
        'asymmetry_score': round(asymmetry, 2),
        'execution_quality': round(execution_quality, 2),
        'invalidation_clarity': round(invalidation_clarity, 2),
        'tactical_timing': round(tactical_timing, 2),
        'leader_score': leader_score,
        'hard_reject': hard_reject,
    }


def leader_sort_key(ticket: dict[str, Any]):
    lc = leader_components(ticket)
    return (
        0 if lc['hard_reject'] else 1,
        lc['leader_score'],
        lc['directional_conviction'],
        lc['asymmetry_score'],
        lc['execution_quality'],
        ticket.get('structure_score', 0.0),
    )


def score_ticket(ticket: dict[str, Any]):
    qc = quality_components(ticket)
    if ticket.get('structure_score') is not None:
        spread_ratio = ticket.get('spread_ratio', 0.99)
        bid = ticket.get('bid', 0.0)
        actual_dte = ticket.get('actual_dte', 99)
        return (
            ticket.get('structure_score', 0.0),
            ticket.get('liquidity_score', 0.0),
            ticket.get('delta_fit_score', 0.0),
            -spread_ratio,
            bid,
            -actual_dte,
            0 if ticket.get('expiry_fallback') else 1,
        )

    spread_ratio = ticket.get('spread_ratio', 0.99)
    bid = ticket.get('bid', 0.0)
    actual_dte = ticket.get('actual_dte', 99)
    delta = abs(ticket.get('delta') or 0.0)

    if ticket['strategy'] == 'Scalping Buy':
        target_delta = 0.58 if actual_dte <= 1 else 0.62
        return (
            qc['structure_score'],
            -abs(delta - target_delta),
            -spread_ratio,
            bid,
            -actual_dte,
            0 if ticket.get('expiry_fallback') else 1,
        )

    target_delta = 0.14
    return (
        qc['structure_score'],
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
        leaders[strategy].sort(key=leader_sort_key, reverse=True)

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
        limit = 2 if strategy == 'Scalping Buy' else 1
        for idx, ticket in enumerate(leaders[strategy][:limit], start=1):
            qc = quality_components(ticket)
            lc = leader_components(ticket)
            if lc['hard_reject']:
                continue
            fallback_note = ' [fallback-expiry]' if ticket.get('expiry_fallback') else ''
            lines.append(
                f"{idx}. {ticket['symbol']} {ticket['option_type'].upper()} | Underlying {ticket.get('underlying_price', 0.0):.2f} | "
                f"Strike {ticket['strike']:.2f} | Exp {ticket['expiration']} | {ticket['label']} | "
                f"Δ {ticket.get('delta', 0.0):.4f} | Bid/Ask {ticket.get('bid', 0.0):.2f}/{ticket.get('ask', 0.0):.2f}{fallback_note}"
            )
            lines.append(f"   Candidate ID: {ticket['candidate_id']}")
            lines.append(f"   Setup Family: {qc['setup_family']}")
            lines.append(f"   Thesis: {qc['narrative']}")
            lines.append(f"   Expectations: {qc['expectations']}")
            lines.append(f"   Invalidation: {qc['invalidation']}")
            lines.append(f"   Targets: {qc['targets']}")
            lines.append(
                f"   Confidence: {qc['confidence']}/10 | Leader Score {lc['leader_score']:.1f} | Structure {qc['structure_score']:.1f}"
            )
            lines.append(
                f"   Rubric: conviction {lc['directional_conviction']:.1f}, asymmetry {lc['asymmetry_score']:.1f}, execution {lc['execution_quality']:.1f}, invalidation {lc['invalidation_clarity']:.1f}, timing {lc['tactical_timing']:.1f}"
            )
            if strategy == 'Scalping Buy':
                lines.append('   Risk: premium-outlay directional trade; demand confirmation and avoid late chasing or size creep')
            else:
                lines.append('   Risk: defined-risk spread only; premium collection is not a license to overstay or sell naked volatility')
            if ticket.get('expiry_note'):
                lines.append(f"   Note: {ticket['expiry_note']}")
        lines.append('')

    fallback_count = sum(1 for t in tickets if t.get('expiry_fallback'))
    lines.append('Run Notes')
    emitted = sum(1 for t in tickets if not leader_components(t)['hard_reject'])
    lines.append(f'- Leaders emitted: {min(emitted, MAX_LEADERS_TOTAL)}')
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


def top_leaders_by_strategy(tickets: list[dict[str, Any]], limit_per_strategy: int = 2) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ticket in tickets:
        grouped[ticket['strategy']].append(ticket)
    out: list[dict[str, Any]] = []
    for strategy in ['Scalping Buy', 'Credit Spread Sell']:
        strategy_tickets = [t for t in sorted(grouped.get(strategy, []), key=leader_sort_key, reverse=True) if not leader_components(t)['hard_reject']]
        out.extend(strategy_tickets[:limit_per_strategy])
    return out[:MAX_LEADERS_TOTAL]
    return out


def save_json(path: str | Path, data: Any) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write('\n')
