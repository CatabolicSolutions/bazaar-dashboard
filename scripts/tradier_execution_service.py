from __future__ import annotations

from typing import Any

from tradier_account import readiness_snapshot
from tradier_board_utils import candidate_id as board_candidate_id
from tradier_broker_interface import TradierBrokerInterface
from tradier_execution_models import ExecutionIntent, OrderRecord, PositionRecord, PreviewRecord, transition_intent
from tradier_risk_controls import evaluate_intent
from tradier_state_store import append_audit, load_state, save_state, upsert_by_key


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

    def _get_persisted_intent(self, state: dict[str, Any], intent_id: str) -> dict[str, Any]:
        for intent in state.get('intents', []):
            if intent.get('intent_id') == intent_id:
                return dict(intent)
        raise ValueError(f'Intent not found in persisted state: {intent_id}')

    def _persist_transition(
        self,
        state: dict[str, Any],
        intent_id: str,
        to_status: str,
        *,
        actor: str = 'alfred',
        note: str = '',
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        persisted_intent = self._get_persisted_intent(state, intent_id)
        transitioned = transition_intent(persisted_intent, to_status, actor=actor, note=note)
        state['intents'] = upsert_by_key(state.get('intents', []), 'intent_id', intent_id, transitioned)
        return transitioned, state

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
        intent = ExecutionIntent(
            mode=mode,
            strategy_type=strategy_type,
            symbol=leader['symbol'],
            contract=contract,
            side='buy',
            qty=qty,
            limit_price=limit_price if limit_price is not None else leader.get('mid_price') or leader.get('ask'),
            source='leader',
            candidate_id=leader.get('candidate_id') or board_candidate_id(leader),
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
        state['orders'].append(order.to_dict())
        state['positions'].append(position.to_dict())
        save_state(state)
        append_audit('order_recorded', 'alfred', intent.intent_id, 'Order commit recorded', {'order_id': order.order_id})
        return {'intent': committed, 'order': order.to_dict(), 'position': position.to_dict()}
