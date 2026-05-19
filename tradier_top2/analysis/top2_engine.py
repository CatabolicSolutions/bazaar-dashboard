#!/usr/bin/env python3
"""Initial skeleton for the Tradier Top-2 conviction engine."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / 'config'


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def build_stub_output() -> dict[str, Any]:
    universe = load_json(CONFIG_DIR / 'universe.json')
    weights = load_json(CONFIG_DIR / 'scoring_weights.json')
    return {
        'status': 'stub',
        'message': 'Top-2 conviction engine scaffold created. Wiring to Tradier candidate flow is the next step.',
        'universe': universe,
        'weights': weights,
        'top_candidates': [],
        'watchlist_candidates': [],
        'rejected_candidates': [],
    }


def main() -> None:
    print(json.dumps(build_stub_output(), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
