"""Contract selection scaffold for 7DTE/14DTE candidates."""

from typing import Any


def select_contract(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not candidates:
        return None
    return candidates[0]
