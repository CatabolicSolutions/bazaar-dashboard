from __future__ import annotations

from typing import Any

from tradier_web_shell_model import build_tradier_web_shell_model

WEB_SHELL_ENDPOINT_KIND = 'tradier.web_shell_endpoint_response'


def get_tradier_web_shell_response(*, latest_limit: int = 20, detail_intent_id: str | None = None) -> dict[str, Any]:
    shell = build_tradier_web_shell_model(latest_limit=latest_limit, detail_intent_id=detail_intent_id)
    return {
        'kind': WEB_SHELL_ENDPOINT_KIND,
        'status': 'ok',
        'data': shell,
    }
