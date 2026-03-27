from __future__ import annotations

from typing import Any


ALLOCATION_BUCKETS = {
    'cash_day_core': {
        'bucket': 'cash_day_core',
        'capital_source': 'cash_day_trading_capital',
        'account_profile': 'cash',
        'domain_modes': {'cash_day'},
    },
    'margin_swing_core': {
        'bucket': 'margin_swing_core',
        'capital_source': 'margin_swing_trading_capital',
        'account_profile': 'margin',
        'domain_modes': {'margin_swing'},
    },
}


def execution_allocation_for_intent(intent: dict[str, Any]) -> dict[str, Any]:
    bucket = intent.get('allocation_bucket')
    mode = intent.get('mode')
    if bucket not in ALLOCATION_BUCKETS:
        raise ValueError(f'Unknown allocation bucket: {bucket}')

    allocation = ALLOCATION_BUCKETS[bucket]
    if mode not in allocation['domain_modes']:
        raise ValueError(
            f'Allocation bucket {bucket} is not valid for execution mode {mode}'
        )

    return {
        'allocation_bucket': allocation['bucket'],
        'capital_source': allocation['capital_source'],
        'account_profile': allocation['account_profile'],
    }
