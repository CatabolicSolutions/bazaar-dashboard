from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid


VALID_MODES = {'cash_day', 'margin_swing'}
VALID_STRATEGY_TYPES = {'long_call', 'long_put', 'defined_risk_spread'}

EXECUTION_INTENT_LIFECYCLE = {
    'candidate': {'next': {'queued', 'rejected'}, 'requires_history': False},
    'queued': {'next': {'previewed', 'rejected', 'cancelled'}, 'requires_history': True},
    'previewed': {'next': {'approved', 'rejected', 'cancelled'}, 'requires_history': True},
    'approved': {'next': {'committed', 'rejected', 'cancelled'}, 'requires_history': True},
    'committed': {'next': {'entered', 'cancelled'}, 'requires_history': True},
    'entered': {'next': {'exited'}, 'requires_history': True},
    'rejected': {'next': set(), 'requires_history': True},
    'cancelled': {'next': set(), 'requires_history': True},
    'exited': {'next': set(), 'requires_history': True},
}

VALID_INTENT_STATUSES = set(EXECUTION_INTENT_LIFECYCLE.keys())
ALLOWED_STATUS_TRANSITIONS = {
    status: set(rule['next']) for status, rule in EXECUTION_INTENT_LIFECYCLE.items()
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class InvalidTransitionError(ValueError):
    pass


class InvalidLifecycleStateError(ValueError):
    pass


def lifecycle_rules_for(status: str) -> dict[str, Any]:
    try:
        return EXECUTION_INTENT_LIFECYCLE[status]
    except KeyError as exc:
        raise InvalidLifecycleStateError(f'Unknown intent status: {status}') from exc


def can_transition(from_status: str, to_status: str) -> bool:
    allowed = lifecycle_rules_for(from_status)['next']
    if to_status not in VALID_INTENT_STATUSES:
        raise InvalidTransitionError(f'Unknown to_status: {to_status}')
    return to_status in allowed


def validate_persisted_intent_lifecycle(intent: dict[str, Any]) -> None:
    status = intent.get('status')
    rules = lifecycle_rules_for(status)
    history = list(intent.get('transition_history') or [])

    if not rules['requires_history']:
        if history:
            raise InvalidLifecycleStateError(
                f'Persisted intent status {status} cannot carry transition history'
            )
        return

    if not history:
        raise InvalidLifecycleStateError(
            f'Persisted intent status {status} requires transition history'
        )

    last_to = history[-1].get('to')
    if last_to != status:
        raise InvalidLifecycleStateError(
            f'Persisted intent status/history mismatch: status={status} last_transition_to={last_to}'
        )


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
    allocation_bucket: str | None = None
    position_relationship: str = 'open_new_position'
    position_id: str | None = None
    strategy_family: str | None = None
    strategy_source: str | None = None
    strategy_run_id: str | None = None
    origin: str = 'system_generated'
    decision_state: str = 'proposed'
    decision_actor: str = 'system'
    decision_note: str = ''
    readiness_state: str = 'not_ready'
    readiness_reason: str = ''
    outcome_state: str = 'no_outcome'
    outcome_reason: str = ''
    effected_qty: int | None = None
    escalation_state: str = 'no_escalation'
    escalation_reason: str = ''
    timing_state: str = 'no_timing_pressure'
    timing_reason: str = ''
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
        if not self.allocation_bucket:
            self.allocation_bucket = 'cash_day_core' if self.mode == 'cash_day' else 'margin_swing_core'
        if not self.strategy_family:
            self.strategy_family = self.strategy_type
        if not self.strategy_source:
            self.strategy_source = self.source
        if not self.strategy_run_id:
            self.strategy_run_id = self.candidate_id or self.intent_id
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
