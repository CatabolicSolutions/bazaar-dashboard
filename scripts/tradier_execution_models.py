from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid


VALID_MODES = {'cash_day', 'margin_swing'}
VALID_STRATEGY_TYPES = {'long_call', 'long_put', 'defined_risk_spread'}
VALID_INTENT_STATUSES = {
    'candidate',
    'queued',
    'previewed',
    'approved',
    'committed',
    'entered',
    'rejected',
    'cancelled',
    'exited',
}

ALLOWED_STATUS_TRANSITIONS = {
    'candidate': {'queued', 'rejected'},
    'queued': {'previewed', 'rejected', 'cancelled'},
    'previewed': {'approved', 'rejected', 'cancelled'},
    'approved': {'committed', 'rejected', 'cancelled'},
    'committed': {'entered', 'cancelled'},
    'entered': {'exited'},
    'rejected': set(),
    'cancelled': set(),
    'exited': set(),
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class InvalidTransitionError(ValueError):
    pass


def can_transition(from_status: str, to_status: str) -> bool:
    if from_status not in ALLOWED_STATUS_TRANSITIONS:
        raise InvalidTransitionError(f'Unknown from_status: {from_status}')
    if to_status not in VALID_INTENT_STATUSES:
        raise InvalidTransitionError(f'Unknown to_status: {to_status}')
    return to_status in ALLOWED_STATUS_TRANSITIONS[from_status]


def transition_intent(intent: dict[str, Any], to_status: str, *, actor: str = 'system', note: str = '') -> dict[str, Any]:
    current_status = intent.get('status')
    if current_status not in VALID_INTENT_STATUSES:
        raise InvalidTransitionError(f'Unknown current status: {current_status}')
    if not can_transition(current_status, to_status):
        raise InvalidTransitionError(f'Invalid transition: {current_status} -> {to_status}')

    updated = dict(intent)
    updated['status'] = to_status
    history = list(updated.get('transition_history') or [])
    history.append({
        'from': current_status,
        'to': to_status,
        'actor': actor,
        'note': note,
        'timestamp': now_iso(),
    })
    updated['transition_history'] = history
    updated['updated_at'] = now_iso()
    return updated


@dataclass
class ExecutionIntent:
    mode: str
    strategy_type: str
    symbol: str
    contract: str
    side: str
    qty: int
    limit_price: float | None = None
    time_in_force: str = 'day'
    source: str = 'manual'
    candidate_id: str | None = None
    notes: str = ''
    intent_id: str = field(default_factory=lambda: new_id('intent'))
    created_at: str = field(default_factory=now_iso)
    status: str = 'candidate'
    transition_history: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        if self.mode not in VALID_MODES:
            raise ValueError(f'Unsupported mode: {self.mode}')
        if self.strategy_type not in VALID_STRATEGY_TYPES:
            raise ValueError(f'Unsupported strategy_type: {self.strategy_type}')
        if self.status not in VALID_INTENT_STATUSES:
            raise ValueError(f'Unsupported status: {self.status}')
        if self.qty <= 0:
            raise ValueError('qty must be > 0')
        self.symbol = self.symbol.upper()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RiskDecision:
    intent_id: str
    mode: str
    allowed: bool
    reasons: list[str]
    checks: dict[str, Any]
    timestamp: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PreviewRecord:
    intent_id: str
    broker_payload_summary: dict[str, Any]
    estimated_cost: float | None = None
    fees: float | None = None
    buying_power_effect: float | None = None
    warnings: list[str] = field(default_factory=list)
    preview_id: str = field(default_factory=lambda: new_id('preview'))
    timestamp: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OrderRecord:
    intent_id: str
    broker_order_id: str | None
    status: str
    avg_fill_price: float | None = None
    remaining_qty: int | None = None
    submitted_at: str = field(default_factory=now_iso)
    filled_at: str | None = None
    order_id: str = field(default_factory=lambda: new_id('order'))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PositionRecord:
    mode: str
    symbol: str
    contract: str
    qty: int
    entry_price: float | None = None
    current_status: str = 'open'
    invalidation: str = ''
    targets: str = ''
    notes: str = ''
    opened_at: str = field(default_factory=now_iso)
    closed_at: str | None = None
    position_id: str = field(default_factory=lambda: new_id('position'))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
