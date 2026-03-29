from __future__ import annotations

from typing import Any

from tradier_dashboard_attention_feed_model import build_tradier_dashboard_attention_feed_model
from tradier_dashboard_detail_model import build_tradier_dashboard_detail_model
from tradier_dashboard_overview_model import build_tradier_dashboard_overview_model
from tradier_desk_prioritization_model import build_trading_desk_prioritization_model
from tradier_execution_snapshot_queries import get_execution_snapshot_by_intent_id
from tradier_state_store import load_state

PRODUCT_SHELL_MODEL_KIND = 'tradier.product_shell_model'


def build_tradier_product_shell_model(*, latest_limit: int = 20, detail_intent_id: str | None = None) -> dict[str, Any]:
    overview = build_tradier_dashboard_overview_model(latest_limit=latest_limit, recent_activity_limit=5)
    attention_feed = build_tradier_dashboard_attention_feed_model(latest_limit=latest_limit, feed_limit=5)
    worklist = build_trading_desk_prioritization_model(latest_limit=latest_limit)

    resolved_detail_intent_id = detail_intent_id
    if resolved_detail_intent_id is None and worklist['items']:
        resolved_detail_intent_id = worklist['items'][0]['snapshot']['intent_id']

    detail = None
    if resolved_detail_intent_id is not None:
        state = load_state()
        for intent in state.get('intents', []):
            if intent.get('intent_id') == resolved_detail_intent_id:
                detail = build_tradier_dashboard_detail_model(intent)
                break

    selected_item = None
    if resolved_detail_intent_id is not None:
        selected_item = get_execution_snapshot_by_intent_id(resolved_detail_intent_id)

    return {
        'kind': PRODUCT_SHELL_MODEL_KIND,
        'overview': overview,
        'worklist': worklist,
        'attention_feed': attention_feed,
        'detail': detail,
        'selected_item': selected_item,
    }
