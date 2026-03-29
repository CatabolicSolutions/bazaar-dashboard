from __future__ import annotations

from typing import Any

from tradier_product_shell_model import build_tradier_product_shell_model

WEB_SHELL_MODEL_KIND = 'tradier.web_shell_model'


def build_tradier_web_shell_model(*, latest_limit: int = 20, detail_intent_id: str | None = None) -> dict[str, Any]:
    shell = build_tradier_product_shell_model(latest_limit=latest_limit, detail_intent_id=detail_intent_id)

    return {
        'kind': WEB_SHELL_MODEL_KIND,
        'overview': shell['overview'],
        'worklist': {
            'items': shell['worklist']['items'],
        },
        'selected_detail': shell['detail'],
        'selected_actions': shell['detail']['operator_context']['actions'] if shell['detail'] else None,
    }
