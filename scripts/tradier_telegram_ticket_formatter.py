import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEADERS_JSON = ROOT / 'out' / 'tradier_final_leaders.json'
OUT_TEXT = ROOT / 'out' / 'tradier_telegram_tickets.txt'


def confirmation_rule(leader: dict) -> str:
    direction = 'bullish' if str(leader.get('option_type', '')).lower().startswith('c') else 'bearish'
    symbol = leader.get('symbol', '')
    strike = leader.get('strike')
    underlying = leader.get('underlying_price')
    if direction == 'bullish':
        return f"Require live confirmation that {symbol} is holding above the entry zone and pressing toward/through {strike:.2f} rather than stalling below it."
    return f"Require live confirmation that {symbol} is failing cleanly and accepting below the entry zone rather than reclaiming back toward {underlying:.2f}."


def invalidation_rule(leader: dict) -> str:
    direction = 'bullish' if str(leader.get('option_type', '')).lower().startswith('c') else 'bearish'
    symbol = leader.get('symbol', '')
    if direction == 'bullish':
        return f"Invalidate if {symbol} loses continuation, stalls quickly after entry, or if option spread quality materially worsens."
    return f"Invalidate if {symbol} reclaims momentum, selling pressure fades, or if option spread quality materially worsens."


def payoff_path(leader: dict) -> str:
    if leader.get('strategy') == 'Scalping Buy':
        return 'Fast directional follow-through with a quick first scale, then only hold extension if momentum and tape quality stay alive.'
    return 'Defined-risk premium capture only; do not overstay or turn a clean capture into a hope-hold.'


def build_ticket(leader: dict, idx: int) -> str:
    option_type = str(leader.get('option_type', '')).upper()
    direction = 'BULLISH' if option_type.startswith('C') else 'BEARISH'
    bid = float(leader.get('bid') or 0.0)
    ask = float(leader.get('ask') or 0.0)
    mid = float(leader.get('mid_price') or 0.0)
    structure = float(leader.get('structure_score') or 0.0)
    conviction = float(leader.get('directional_conviction') or 0.0)
    asymmetry = float(leader.get('asymmetry_score') or 0.0)
    execution = float(leader.get('execution_quality') or 0.0)
    timing = float(leader.get('tactical_timing') or 0.0)
    leader_score = float(leader.get('leader_score') or 0.0)
    return "\n".join([
        f"LEADER {idx}",
        f"Contract: {leader['symbol']} {leader['expiration']} {leader['strike']:.2f} {option_type}",
        f"Bias: {direction} | Strategy: {leader['strategy']}",
        f"Why leader: leader score {leader_score:.1f}; conviction {conviction:.1f}, asymmetry {asymmetry:.1f}, execution {execution:.1f}, timing {timing:.1f}.",
        f"Why now: underlying {leader.get('underlying_price', 0.0):.2f}, DTE {leader.get('actual_dte')}, option market {bid:.2f}/{ask:.2f} (mid {mid:.2f}), structure {structure:.1f}.",
        f"Confirmation: {confirmation_rule(leader)}",
        f"Invalidation: {invalidation_rule(leader)}",
        f"Payoff path: {payoff_path(leader)}",
        f"Risk posture: premium-outlay only and no blind entry; require human signoff before ticket conversion.",
        f"Command path: review -> approve -> build execution ticket -> commit only on explicit signoff.",
    ])


def main():
    data = json.loads(LEADERS_JSON.read_text())
    leaders = data.get('leaders', [])
    if not leaders:
        text = 'No Trade\n- No leaders available for Telegram signoff flow.'
    else:
        sections = ['TRADIER TELEGRAM EXECUTION CANDIDATES', f"Leaders ready: {len(leaders)}", '']
        for i, leader in enumerate(leaders, start=1):
            sections.append(build_ticket(leader, i))
            sections.append('')
        text = '\n'.join(sections).strip() + '\n'
    OUT_TEXT.write_text(text, encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
