from __future__ import annotations

from typing import Any

from tradier_dashboard_overview_model import build_tradier_dashboard_overview_model
from tradier_desk_prioritization_model import build_trading_desk_prioritization_model

DASHBOARD_ATTENTION_FEED_MODEL_KIND = 'tradier.dashboard_attention_feed_model'


def _reason_for_priority_category(category: str) -> str:
    return {
        'divergent': 'divergent broker/internal state requires review',
        'blocked': 'blocked execution path requires intervention',
        'pending_confirmation': 'pending confirmation should be checked',
        'ready': 'ready intent available for action',
        'other': 'recent activity available for review',
    }[category]


def build_tradier_dashboard_attention_feed_model(*, latest_limit: int = 20, feed_limit: int = 5) -> dict[str, Any]:
    overview = build_tradier_dashboard_overview_model(latest_limit=latest_limit, recent_activity_limit=feed_limit)
    prioritization = build_trading_desk_prioritization_model(latest_limit=latest_limit)

    prioritized_items = prioritization['items']
    current_attention = []
    for item in prioritized_items:
        if item['priority_category'] in {'divergent', 'blocked', 'pending_confirmation'}:
            current_attention.append({
                'snapshot': item['snapshot'],
                'priority_category': item['priority_category'],
                'priority_rank': item['priority_rank'],
                'reason': _reason_for_priority_category(item['priority_category']),
            })
        if len(current_attention) >= feed_limit:
            break

    recent_review = []
    for item in prioritized_items[:feed_limit]:
        recent_review.append({
            'snapshot': item['snapshot'],
            'priority_category': item['priority_category'],
            'priority_rank': item['priority_rank'],
            'reason': _reason_for_priority_category(item['priority_category']),
        })

    return {
        'kind': DASHBOARD_ATTENTION_FEED_MODEL_KIND,
        'summary': overview['summary'],
        'feed': {
            'needs_attention_now': overview['attention']['needs_attention_now'],
            'current_attention': current_attention,
            'recent_review': recent_review,
        },
    }
