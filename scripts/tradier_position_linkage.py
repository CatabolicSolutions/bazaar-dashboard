from __future__ import annotations

from typing import Any


POSITION_LINKAGE_RELATIONSHIPS = {
    'open_new_position': {
        'position_effect': 'open',
        'requires_position_id': False,
        'holding_scope': 'new_exposure',
    },
    'modify_existing_position': {
        'position_effect': 'modify',
        'requires_position_id': True,
        'holding_scope': 'existing_exposure',
    },
    'reduce_or_close_position': {
        'position_effect': 'reduce_or_close',
        'requires_position_id': True,
        'holding_scope': 'existing_exposure',
    },
}


def position_linkage_for_intent(intent: dict[str, Any]) -> dict[str, Any]:
    relationship = intent.get('position_relationship') or 'open_new_position'
    if relationship not in POSITION_LINKAGE_RELATIONSHIPS:
        raise ValueError(f'Unknown position relationship: {relationship}')

    position_id = intent.get('position_id')
    rules = POSITION_LINKAGE_RELATIONSHIPS[relationship]
    if rules['requires_position_id'] and not position_id:
        raise ValueError(
            f'Position relationship {relationship} requires position_id'
        )
    if not rules['requires_position_id'] and position_id:
        raise ValueError(
            f'Position relationship {relationship} cannot carry position_id'
        )

    return {
        'position_relationship': relationship,
        'position_effect': rules['position_effect'],
        'holding_scope': rules['holding_scope'],
        'position_id': position_id,
    }
