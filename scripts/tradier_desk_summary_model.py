from __future__ import annotations

from typing import Any

from tradier_desk_action_model import build_trading_desk_action_model

DESK_SUMMARY_MODEL_KIND = 'tradier.trading_desk_summary_model'


def build_trading_desk_summary_model(*, latest_limit: int = 20) -> dict[str, Any]:
    action_model = build_trading_desk_action_model(latest_limit=latest_limit)
    views = action_model['views']

    blocked_count = len(views['blocked_intents'])
    pending_confirmation_count = len(views['pending_confirmation_intents'])
    divergent_count = len(views['divergent_intents'])
    ready_count = len(views['ready_intents'])

    needs_attention_now = blocked_count > 0 or pending_confirmation_count > 0 or divergent_count > 0

    return {
        'kind': DESK_SUMMARY_MODEL_KIND,
        'source': action_model['source'],
        'summary': {
            'ready_count': ready_count,
            'blocked_count': blocked_count,
            'pending_confirmation_count': pending_confirmation_count,
            'divergent_count': divergent_count,
            'needs_attention_now': needs_attention_now,
        },
    }
