from __future__ import annotations

from typing import Any

from tradier_desk_prioritization_model import build_trading_desk_prioritization_model
from tradier_desk_summary_model import build_trading_desk_summary_model

DASHBOARD_OVERVIEW_MODEL_KIND = 'tradier.dashboard_overview_model'


def build_tradier_dashboard_overview_model(*, latest_limit: int = 20, recent_activity_limit: int = 5) -> dict[str, Any]:
    summary_model = build_trading_desk_summary_model(latest_limit=latest_limit)
    prioritization_model = build_trading_desk_prioritization_model(latest_limit=latest_limit)

    summary = summary_model['summary']
    prioritized_items = prioritization_model['items']
    top_attention_items = prioritized_items[:3]
    recent_activity = prioritized_items[:recent_activity_limit]

    return {
        'kind': DASHBOARD_OVERVIEW_MODEL_KIND,
        'summary': summary,
        'attention': {
            'needs_attention_now': summary['needs_attention_now'],
            'top_priority_items': top_attention_items,
        },
        'recent_activity': recent_activity,
    }
