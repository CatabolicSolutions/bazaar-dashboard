"""Setup validation scaffold for short-DTE opportunity review."""

from typing import Any


def validate_setup(candidate: dict[str, Any], market_context: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        'passed': False,
        'validators_passed': [],
        'validators_failed': ['not_implemented'],
        'notes': 'Setup validator not implemented yet.'
    }
