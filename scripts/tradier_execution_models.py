from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid


VALID_MODES = {'cash_day', 'margin_swing'}
VALID_STRATEGY_TYPES = {'long_call', 'long_put', 'defined_risk_spread'}
VALID_INTENT_STATUSES = {
    'draft',
    'queued',
    'risk_rejected',
    'previewed',
    'approved',
    'committed',
    'placed',
    'filled',
    'cancelled',
    'closed',
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


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
    status: str = 'draft'

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
