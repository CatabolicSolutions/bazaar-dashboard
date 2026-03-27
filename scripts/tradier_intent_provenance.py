from __future__ import annotations

from typing import Any


VALID_PROVENANCE_ORIGINS = {'human_directed', 'system_generated'}


def intent_provenance_for_intent(intent: dict[str, Any]) -> dict[str, Any]:
    strategy_family = intent.get('strategy_family') or intent.get('strategy_type')
    strategy_source = intent.get('strategy_source') or intent.get('source')
    strategy_run_id = intent.get('strategy_run_id') or intent.get('run_id') or intent.get('candidate_id')
    origin = intent.get('origin') or 'system_generated'

    if not strategy_family:
        raise ValueError('Intent provenance requires strategy_family')
    if not strategy_source:
        raise ValueError('Intent provenance requires strategy_source')
    if not strategy_run_id:
        raise ValueError('Intent provenance requires strategy_run_id')
    if origin not in VALID_PROVENANCE_ORIGINS:
        raise ValueError(f'Unknown intent origin: {origin}')

    return {
        'strategy_family': strategy_family,
        'strategy_source': strategy_source,
        'strategy_run_id': strategy_run_id,
        'origin': origin,
    }
