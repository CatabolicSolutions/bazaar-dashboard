import json
import sys
from pathlib import Path

from tradier_board_utils import build_board, leader_components, parse_raw_tickets, top_leaders_by_strategy, save_json

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / 'out'
LEADERS_JSON = OUT_DIR / 'tradier_final_leaders.json'


def main():
    raw = sys.stdin.read()
    tickets = parse_raw_tickets(raw)
    leaders = top_leaders_by_strategy(tickets, limit_per_strategy=2)
    enriched = []
    for leader in leaders:
        merged = dict(leader)
        merged.update(leader_components(leader))
        enriched.append(merged)
    save_json(LEADERS_JSON, {
        'leaders_count': len(enriched),
        'leaders': enriched,
    })
    print(build_board(leaders))


if __name__ == '__main__':
    main()
