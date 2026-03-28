from __future__ import annotations

from typing import Any

from tradier_account import readiness_snapshot
from tradier_board_utils import candidate_id as board_candidate_id
from tradier_broker_interface import TradierBrokerInterface
from tradier_execution_models import ExecutionIntent, OrderRecord, PositionRecord, PreviewRecord
from tradier_risk_controls import evaluate_intent
from tradier_state_store import append_audit, load_state, save_state, transition_persisted_intent, upsert_by_key


SIDE_MAP = {
    'long_call': 'buy_to_open',
    'long_put': 'buy_to_open',
}


class TradierExecutionService:
    def __init__(self, broker: TradierBrokerInterface | None = None):
        self.broker = broker or TradierBrokerInterface()

    def _materialize_intent(self, intent_dict: dict[str, Any]) -> ExecutionIntent:
        allowed_keys = set(ExecutionIntent.__dataclass_fields__.keys())
        return ExecutionIntent(**{key: value for key, value in intent_dict.items() if key in allowed_keys})

    def _persist_intent_updates(self, state: dict[str, Any], intent_id: str, **updates: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        persisted_intent = None
        for intent in state.get('intents', []):
            if intent.get('intent_id') == intent_id:
                persisted_intent = dict(intent)
                break
        if persisted_intent is None:
            raise ValueError(f'Intent not found in persisted state: {intent_id}')
        persisted_intent.update(updates)
        state = dict(state)
        state['intents'] = upsert_by_key(state.get('intents', []), 'intent_id', intent_id, persisted_intent)
        return persisted_intent, state

    def _persist_transition(
        self,
        state: dict[str, Any],
        intent_id: str,
        to_status: str,
        *,
        actor: str = 'alfred',
        note: str = '',
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        return transition_persisted_intent(state, intent_id, to_status, actor=actor, note=note)

    def create_intent_from_leader(
        self,
        leader: dict[str, Any],
        *,
        mode: str,
        qty: int = 1,
        limit_price: float | None = None,
        notes: str = '',
    ) -> dict[str, Any]:
        strategy_type = 'long_call' if leader.get('option_type', '').lower().startswith('c') else 'long_put'
        contract = f"{leader['symbol']} {leader['strike']} {leader['option_type'].upper()} {leader['expiration']}"
        resolved_candidate_id = leader.get('candidate_id') or board_candidate_id(leader)
        intent = ExecutionIntent(
            mode=mode,
            strategy_type=strategy_type,
            symbol=leader['symbol'],
            contract=contract,
            side='buy',
            qty=qty,
            limit_price=limit_price if limit_price is not None else leader.get('mid_price') or leader.get('ask'),
            source='leader',
            candidate_id=resolved_candidate_id,
            strategy_family=leader.get('strategy') or strategy_type,
            strategy_source='tradier_leaders_board',
            strategy_run_id=leader.get('run_id') or resolved_candidate_id,
            origin='system_generated',
            decision_state='proposed',
            decision_actor='system',
            decision_note='Created from leaders board candidate',
            readiness_state='not_ready',
            readiness_reason='Awaiting preview and authorization prerequisites',
            outcome_state='no_outcome',
            outcome_reason='',
            effected_qty=None,
            escalation_state='no_escalation',
            escalation_reason='',
            timing_state='no_timing_pressure',
            timing_reason='',
            external_reference_state='no_external_reference',
            external_reference_id=None,
            external_reference_system='',
            external_reference_note='',
            attempt_state='no_attempt',
            attempt_count=0,
            latest_attempt_id=None,
            latest_attempt_note='',
            reconciliation_state='not_reconciled',
            reconciliation_note='',
            notes=notes,
        )
        state = load_state()
        state['intents'].append(intent.to_dict())
        queued, state = self._persist_transition(
            state,
            intent.intent_id,
            'queued',
            actor='alfred',
            note=f"Created {intent.mode} intent from {intent.candidate_id}",
        )
        save_state(state)
        append_audit('intent_created', 'alfred', intent.intent_id, f"Created {intent.mode} intent from {intent.candidate_id}", {'candidate_id': intent.candidate_id})
        return queued

    def evaluate_risk(self, intent_dict: dict[str, Any], mark_price: float | None = None) -> dict[str, Any]:
        intent = self._materialize_intent(intent_dict)
        account = readiness_snapshot()
        state = load_state()
        decision = evaluate_intent(intent, account, mark_price=mark_price, open_positions=state.get('positions', []))
        state['riskDecisions'] = upsert_by_key(state.get('riskDecisions', []), 'intent_id', intent.intent_id, decision.to_dict())
        save_state(state)
        append_audit('risk_evaluated', 'alfred', intent.intent_id, 'Risk evaluation completed', {'allowed': decision.allowed})
        return decision.to_dict()

    def preview_intent(self, intent_dict: dict[str, Any], *, expiry: str, option_type: str, strike: float) -> dict[str, Any]:
        intent = self._materialize_intent(intent_dict)
        payload = self.broker.build_option_payload(
            intent,
            symbol=intent.symbol,
            expiry=expiry,
            option_type=option_type,
            strike=strike,
            broker_side=SIDE_MAP[intent.strategy_type],
        )
        preview_response = self.broker.preview_order(payload)
        record = PreviewRecord(intent_id=intent.intent_id, broker_payload_summary=payload)
        state = load_state()
        state['previews'] = upsert_by_key(state.get('previews', []), 'intent_id', intent.intent_id, record.to_dict())
        previewed, state = self._persist_transition(
            state,
            intent.intent_id,
            'previewed',
            actor='alfred',
            note='Broker preview created',
        )
        save_state(state)
        append_audit('preview_created', 'alfred', intent.intent_id, 'Broker preview created', {'payload': payload})
        return {'intent': previewed, 'preview': record.to_dict(), 'broker_response': preview_response}

    def approve_intent(self, intent_dict: dict[str, Any], *, actor: str = 'alfred', note: str = 'Approved for execution') -> dict[str, Any]:
        intent = self._materialize_intent(intent_dict)
        state = load_state()
        approved, state = self._persist_transition(state, intent.intent_id, 'approved', actor=actor, note=note)
        approved, state = self._persist_intent_updates(
            state,
            intent.intent_id,
            decision_state='approved',
            decision_actor=actor,
            decision_note=note,
        )
        save_state(state)
        append_audit('intent_approved', actor, intent.intent_id, note)
        return approved

    def mark_intent_ready(self, intent_dict: dict[str, Any], *, reason: str = 'Execution prerequisites satisfied') -> dict[str, Any]:
        intent = self._materialize_intent(intent_dict)
        state = load_state()
        ready, state = self._persist_intent_updates(
            state,
            intent.intent_id,
            readiness_state='ready',
            readiness_reason=reason,
        )
        save_state(state)
        append_audit('intent_ready', 'alfred', intent.intent_id, reason)
        return ready

    def begin_execution_attempt(self, intent_dict: dict[str, Any], *, attempt_id: str, note: str = 'Execution attempt started') -> dict[str, Any]:
        intent = self._materialize_intent(intent_dict)
        state = load_state()
        in_progress, state = self._persist_intent_updates(
            state,
            intent.intent_id,
            attempt_state='attempt_in_progress',
            attempt_count=max(1, int(intent_dict.get('attempt_count') or 0) + 1),
            latest_attempt_id=attempt_id,
            latest_attempt_note=note,
            external_reference_state='pending_external_reference',
            external_reference_note='Awaiting broker linkage',
        )
        save_state(state)
        append_audit('execution_attempt_started', 'alfred', intent.intent_id, note, {'attempt_id': attempt_id})
        return in_progress

    def block_intent(self, intent_dict: dict[str, Any], *, reason: str, escalation_state: str = 'blocked') -> dict[str, Any]:
        intent = self._materialize_intent(intent_dict)
        state = load_state()
        blocked, state = self._persist_intent_updates(
            state,
            intent.intent_id,
            readiness_state='blocked',
            readiness_reason=reason,
            escalation_state=escalation_state,
            escalation_reason=reason,
        )
        save_state(state)
        append_audit('intent_blocked', 'alfred', intent.intent_id, reason, {'escalation_state': escalation_state})
        return blocked

    def fail_execution_attempt(self, intent_dict: dict[str, Any], *, attempt_id: str, reason: str, escalation_state: str = 'blocked') -> dict[str, Any]:
        intent = self._materialize_intent(intent_dict)
        state = load_state()
        failed, state = self._persist_intent_updates(
            state,
            intent.intent_id,
            attempt_state='attempt_failed',
            attempt_count=max(1, int(intent_dict.get('attempt_count') or 0)),
            latest_attempt_id=attempt_id,
            latest_attempt_note=reason,
            outcome_state='failed_execution',
            outcome_reason=reason,
            effected_qty=0,
            readiness_state='blocked',
            readiness_reason=reason,
            escalation_state=escalation_state,
            escalation_reason=reason,
            reconciliation_state='pending_confirmation',
            reconciliation_note='Failure recorded; awaiting external confirmation or operator review',
        )
        save_state(state)
        append_audit('execution_attempt_failed', 'alfred', intent.intent_id, reason, {'attempt_id': attempt_id})
        return failed

    def retry_execution_attempt(self, intent_dict: dict[str, Any], *, attempt_id: str, reason: str = 'Retry attempt started') -> dict[str, Any]:
        intent = self._materialize_intent(intent_dict)
        state = load_state()
        retried, state = self._persist_intent_updates(
            state,
            intent.intent_id,
            attempt_state='attempt_in_progress',
            attempt_count=max(1, int(intent_dict.get('attempt_count') or 0) + 1),
            latest_attempt_id=attempt_id,
            latest_attempt_note=reason,
            readiness_state='ready',
            readiness_reason='Retry attempt in progress',
            outcome_state='no_outcome',
            outcome_reason='',
            effected_qty=None,
            escalation_state='warning',
            escalation_reason=reason,
            external_reference_state='pending_external_reference',
            external_reference_id=None,
            external_reference_system='',
            external_reference_note='Awaiting broker linkage for retry attempt',
            reconciliation_state='not_reconciled',
            reconciliation_note='Retry attempt restarted reconciliation cycle',
        )
        save_state(state)
        append_audit('execution_attempt_retried', 'alfred', intent.intent_id, reason, {'attempt_id': attempt_id})
        return retried

    def record_commit(self, intent_dict: dict[str, Any], broker_response: dict[str, Any]) -> dict[str, Any]:
        intent = self._materialize_intent(intent_dict)
        order = OrderRecord(intent_id=intent.intent_id, broker_order_id=str(broker_response.get('id') or broker_response.get('order', {}).get('id') or ''), status='placed')
        position = PositionRecord(mode=intent.mode, symbol=intent.symbol, contract=intent.contract, qty=intent.qty, entry_price=intent.limit_price)
        state = load_state()
        committed, state = self._persist_transition(
            state,
            intent.intent_id,
            'committed',
            actor='alfred',
            note='Order commit recorded',
        )
        committed, state = self._persist_intent_updates(
            state,
            intent.intent_id,
            external_reference_state='linked_external_reference',
            external_reference_id=order.broker_order_id,
            external_reference_system='tradier',
            external_reference_note='Broker order linked',
            attempt_state='attempt_completed',
            attempt_count=max(1, int(committed.get('attempt_count') or intent_dict.get('attempt_count') or 0)),
            latest_attempt_id=committed.get('latest_attempt_id') or 'attempt-1',
            latest_attempt_note='Execution attempt completed',
            outcome_state='full_execution',
            outcome_reason='Broker order recorded as filled-equivalent for happy path',
            effected_qty=intent.qty,
            reconciliation_state='pending_confirmation',
            reconciliation_note='Awaiting broker confirmation after commit',
        )
        state['orders'].append(order.to_dict())
        state['positions'].append(position.to_dict())
        save_state(state)
        append_audit('order_recorded', 'alfred', intent.intent_id, 'Order commit recorded', {'order_id': order.order_id})
        return {'intent': committed, 'order': order.to_dict(), 'position': position.to_dict()}

    def reconcile_intent(self, intent_dict: dict[str, Any], *, note: str = 'Broker confirmation matched internal record') -> dict[str, Any]:
        intent = self._materialize_intent(intent_dict)
        state = load_state()
        reconciled, state = self._persist_intent_updates(
            state,
            intent.intent_id,
            reconciliation_state='reconciled',
            reconciliation_note=note,
        )
        save_state(state)
        append_audit('intent_reconciled', 'alfred', intent.intent_id, note)
        return reconciled
