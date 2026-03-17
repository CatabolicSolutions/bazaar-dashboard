import argparse
from datetime import datetime
from pathlib import Path

from tradier_board_utils import parse_raw_tickets, save_json, top_leaders_by_strategy


RUNS_DIR = Path.home() / '.openclaw' / 'workspace' / 'out' / 'tradier_runs'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--raw', required=True)
    parser.add_argument('--board', required=True)
    args = parser.parse_args()

    generated_at = datetime.now().astimezone()
    run_id = generated_at.strftime('%Y%m%dT%H%M%S%z')
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    raw_text = Path(args.raw).read_text(encoding='utf-8')
    board_text = Path(args.board).read_text(encoding='utf-8')
    tickets = parse_raw_tickets(raw_text)
    leaders = top_leaders_by_strategy(tickets, limit_per_strategy=3)

    (run_dir / 'raw.txt').write_text(raw_text, encoding='utf-8')
    (run_dir / 'board.txt').write_text(board_text, encoding='utf-8')
    save_json(
        run_dir / 'run.json',
        {
            'run_id': run_id,
            'generated_at': generated_at.isoformat(),
            'ticket_count': len(tickets),
            'leader_count': len(leaders),
            'leaders': leaders,
        },
    )


if __name__ == '__main__':
    main()
