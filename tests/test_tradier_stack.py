import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = WORKSPACE_ROOT / 'scripts'
for p in [str(WORKSPACE_ROOT), str(SCRIPTS_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from scripts.tradier_execution import occ_option_symbol
from scripts.tradier_position_flow import parse_command
from scripts.tradier_approval_flow import contract_key, build_execution_card
from scripts.tradier_board_utils import candidate_id, parse_raw_tickets, top_leaders_by_strategy
from scripts.tradier_execution_models import (
    EXECUTION_INTENT_LIFECYCLE,
    ExecutionIntent,
    InvalidLifecycleStateError,
    InvalidTransitionError,
    VALID_INTENT_STATUSES,
    can_transition,
    transition_intent,
    validate_persisted_intent_lifecycle,
)
from scripts.tradier_execution_semantics import interpret_operator_execution_state
from scripts.tradier_execution_service import TradierExecutionService
from scripts.tradier_state_store import save_state, transition_persisted_intent
from tradier_execution_models import InvalidLifecycleStateError as RuntimeInvalidLifecycleStateError
from tradier_execution_models import InvalidTransitionError as RuntimeInvalidTransitionError
from scripts.tradier_risk_controls import evaluate_intent
from scripts.tradier_account import readiness_snapshot
from scripts.tradier_exit_policy import classify


RAW_SAMPLE = '''---TICKET_START---
Scalping Buy Opportunity for IWM (0DTE)**
  - Underlying Price: $250.10
  - Current VIX: 19.2
  - Type: CALL
  - Strike: $250.00
  - Expiration: 2026-03-20
  - Requested DTE: 0
  - Actual DTE: 0
  - Last Price: $1.90
  - Bid: $1.88 / Ask: $1.92
  - Delta: 0.5800
  - Spread Ratio: 2.11%
---TICKET_DELIMITER---
Credit Spread Sell Opportunity for SPY (1DTE)**
  - Underlying Price: $510.20
  - Current VIX: 19.2
  - Type: CALL
  - Strike: $515.00
  - Expiration: 2026-03-21
  - Requested DTE: 1
  - Actual DTE: 1
  - Last Price: $0.70
  - Bid: $0.68 / Ask: $0.72
  - Delta: 0.1400
  - Spread Ratio: 5.71%
---TICKET_DELIMITER---
---TICKET_END---
'''


class TradierStackTests(unittest.TestCase):
    def with_temp_state_paths(self):
        tempdir = tempfile.TemporaryDirectory()
        root = Path(tempdir.name)
        state_path = root / 'tradier_execution_state.json'
        audit_path = root / 'tradier_audit_log.json'
        patchers = [
            patch('scripts.tradier_state_store.EXECUTION_STATE_PATH', state_path),
            patch('scripts.tradier_state_store.AUDIT_LOG_PATH', audit_path),
            patch('tradier_state_store.EXECUTION_STATE_PATH', state_path),
            patch('tradier_state_store.AUDIT_LOG_PATH', audit_path),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(tempdir.cleanup)
        return state_path, audit_path

    def load_json_file(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding='utf-8'))

    def test_occ_option_symbol(self):
        self.assertEqual(occ_option_symbol('IWM', '2026-03-20', 'call', 250), 'IWM260320C00250000')
        self.assertEqual(occ_option_symbol('SPY', '3/21/26', 'put', 510), 'SPY260321P00510000')

    def test_parse_in_command_short_form(self):
        parsed = parse_command('/in 2 IWM 250C 3/20/26 @ 1.86')
        self.assertEqual(parsed['action'], 'in')
        self.assertEqual(parsed['symbol'], 'IWM')
        self.assertEqual(parsed['strike'], 250.0)
        self.assertEqual(parsed['option_type'], 'call')
        self.assertEqual(parsed['expiration'], '2026-03-20')
        self.assertEqual(parsed['price'], 1.86)

    def test_parse_out_command_long_form(self):
        parsed = parse_command('/out 2 IWM 250 Call 3/20/26 @ 1.90')
        self.assertEqual(parsed['action'], 'out')
        self.assertEqual(parsed['option_type'], 'call')
        self.assertEqual(parsed['expiration'], '2026-03-20')

    def test_contract_key_supports_common_variants(self):
        leader = {'symbol': 'IWM', 'strike': 250.0, 'option_type': 'call', 'expiration': '2026-03-20'}
        key = contract_key(leader)
        self.assertIn('IWM250C2026-03-20', key)
        self.assertIn('IWM250.0C2026-03-20'.replace('.0', ''), key.replace('.0', ''))

    def test_execution_card_contains_next_step(self):
        leader = {
            'symbol': 'IWM', 'strike': 250.0, 'option_type': 'call', 'expiration': '2026-03-20',
            'strategy': 'Scalping Buy', 'underlying_price': 250.10, 'bid': 1.88, 'ask': 1.92, 'mid_price': 1.90,
        }
        run = {'run_id': '20260320T063000-0600'}
        card = build_execution_card(leader, run)
        self.assertIn('TRADE EXECUTION CARD', card)
        self.assertIn('/take <contract>', card)

    def test_parse_raw_tickets_and_leaders(self):
        tickets = parse_raw_tickets(RAW_SAMPLE)
        self.assertEqual(len(tickets), 2)
        self.assertEqual(tickets[0]['candidate_id'], 'IWM-2026-03-20-CALL-250')
        leaders = top_leaders_by_strategy(tickets, limit_per_strategy=1)
        self.assertEqual(len(leaders), 2)
        self.assertEqual(leaders[0]['symbol'], 'IWM')

    def test_candidate_id_helper(self):
        self.assertEqual(candidate_id({'symbol': 'spy', 'expiration': '2026-03-21', 'option_type': 'put', 'strike': 510.0}), 'SPY-2026-03-21-PUT-510')

    def test_risk_controls_reject_gtc_and_large_drift(self):
        intent = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            limit_price=2.50,
            time_in_force='gtc',
        )
        decision = evaluate_intent(intent, {'ready_for_options_execution': True, 'option_buying_power': 1000.0}, mark_price=2.00)
        self.assertFalse(decision.allowed)
        self.assertTrue(any('day TIF' in reason for reason in decision.reasons))
        self.assertTrue(any('drift' in reason for reason in decision.reasons))

    def test_canonical_lifecycle_contract_defines_statuses_and_transitions(self):
        self.assertEqual(set(EXECUTION_INTENT_LIFECYCLE.keys()), VALID_INTENT_STATUSES)
        self.assertFalse(EXECUTION_INTENT_LIFECYCLE['candidate']['requires_history'])
        self.assertTrue(EXECUTION_INTENT_LIFECYCLE['queued']['requires_history'])
        self.assertEqual(EXECUTION_INTENT_LIFECYCLE['candidate']['next'], {'queued', 'rejected'})
        self.assertEqual(EXECUTION_INTENT_LIFECYCLE['committed']['next'], {'entered', 'cancelled'})

    def test_transition_table_allows_valid_path(self):
        self.assertTrue(can_transition('candidate', 'queued'))
        self.assertTrue(can_transition('queued', 'previewed'))
        intent = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
        ).to_dict()
        queued = transition_intent(intent, 'queued', actor='test')
        previewed = transition_intent(queued, 'previewed', actor='test')
        approved = transition_intent(previewed, 'approved', actor='test')
        self.assertEqual(approved['status'], 'approved')
        self.assertEqual(len(approved['transition_history']), 3)
        self.assertEqual(approved['transition_history'][0]['from'], 'candidate')
        self.assertEqual(approved['transition_history'][-1]['to'], 'approved')

    def test_transition_table_rejects_invalid_jump(self):
        intent = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
        ).to_dict()
        with self.assertRaises(InvalidTransitionError):
            transition_intent(intent, 'approved', actor='test')

    def test_canonical_lifecycle_contract_governs_history_consistency(self):
        candidate = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
        ).to_dict()
        validate_persisted_intent_lifecycle(candidate)

        queued = transition_intent(candidate, 'queued', actor='test')
        validate_persisted_intent_lifecycle(queued)

        with self.assertRaises(InvalidLifecycleStateError):
            validate_persisted_intent_lifecycle({**candidate, 'status': 'queued'})

        with self.assertRaises(InvalidLifecycleStateError):
            validate_persisted_intent_lifecycle({**queued, 'status': 'approved'})

    def test_persisted_flow_valid_transition_writes_history(self):
        state_path, _ = self.with_temp_state_paths()
        broker = Mock()
        broker.build_option_payload.return_value = {'tag': 'preview-payload'}
        broker.preview_order.return_value = {'ok': True}
        service = TradierExecutionService(broker=broker)

        leader = {
            'symbol': 'IWM',
            'strike': 250.0,
            'option_type': 'call',
            'expiration': '2026-03-20',
            'candidate_id': 'IWM-2026-03-20-CALL-250',
            'mid_price': 1.90,
        }
        queued = service.create_intent_from_leader(leader, mode='cash_day')
        result = service.preview_intent(queued, expiry='2026-03-20', option_type='call', strike=250.0)

        persisted = self.load_json_file(state_path)
        self.assertEqual(len(persisted['intents']), 1)
        intent = persisted['intents'][0]
        self.assertEqual(intent['status'], 'previewed')
        self.assertEqual([entry['to'] for entry in intent['transition_history']], ['queued', 'previewed'])
        self.assertEqual(intent['transition_history'][0]['from'], 'candidate')
        self.assertEqual(intent['transition_history'][1]['from'], 'queued')
        self.assertEqual(result['intent']['transition_history'], intent['transition_history'])

    def test_service_flow_valid_multistep_progression_persists_history_order_and_position(self):
        state_path, _ = self.with_temp_state_paths()
        broker = Mock()
        broker.build_option_payload.return_value = {
            'class': 'option',
            'symbol': 'IWM',
            'option_symbol': 'IWM260320C00250000',
            'side': 'buy_to_open',
            'quantity': 1,
            'type': 'limit',
            'duration': 'day',
            'price': 1.90,
            'tag': 'preview-payload',
        }
        broker.preview_order.return_value = {'ok': True, 'preview_id': 'pv-1'}
        service = TradierExecutionService(broker=broker)

        leader = {
            'symbol': 'IWM',
            'strike': 250.0,
            'option_type': 'call',
            'expiration': '2026-03-20',
            'candidate_id': 'IWM-2026-03-20-CALL-250',
            'mid_price': 1.90,
        }

        queued = service.create_intent_from_leader(leader, mode='cash_day')
        previewed = service.preview_intent(queued, expiry='2026-03-20', option_type='call', strike=250.0)['intent']
        state = self.load_json_file(state_path)
        approved, state = transition_persisted_intent(state, previewed['intent_id'], 'approved', actor='test', note='risk cleared')
        save_state(state)
        committed = service.record_commit(approved, {'id': 'broker-order-1'})['intent']

        persisted = self.load_json_file(state_path)
        self.assertEqual(len(persisted['intents']), 1)
        self.assertEqual(len(persisted['previews']), 1)
        self.assertEqual(len(persisted['orders']), 1)
        self.assertEqual(len(persisted['positions']), 1)
        intent = persisted['intents'][0]
        self.assertEqual(intent['status'], 'committed')
        self.assertEqual([entry['to'] for entry in intent['transition_history']], ['queued', 'previewed', 'approved', 'committed'])
        self.assertEqual(committed['transition_history'], intent['transition_history'])
        self.assertEqual(persisted['orders'][0]['broker_order_id'], 'broker-order-1')
        self.assertEqual(persisted['positions'][0]['symbol'], 'IWM')

        operator_view = interpret_operator_execution_state(intent)
        self.assertEqual(operator_view['operator_state'], 'sent_to_broker')
        self.assertEqual(operator_view['operator_stage'], 'execution')
        self.assertEqual(operator_view['next_operator_action'], 'await_entry_or_cancel')
        self.assertFalse(operator_view['is_terminal'])

    def test_transition_persisted_intent_is_single_governed_route(self):
        self.with_temp_state_paths()
        state = {
            'intents': [ExecutionIntent(
                mode='cash_day',
                strategy_type='long_call',
                symbol='IWM',
                contract='IWM 250 CALL 2026-03-20',
                side='buy',
                qty=1,
            ).to_dict()],
            'previews': [],
            'orders': [],
            'positions': [],
            'riskDecisions': [],
        }
        intent_id = state['intents'][0]['intent_id']

        queued, state = transition_persisted_intent(state, intent_id, 'queued', actor='test')
        previewed, state = transition_persisted_intent(state, intent_id, 'previewed', actor='test')

        self.assertEqual(queued['status'], 'queued')
        self.assertEqual(previewed['status'], 'previewed')
        self.assertEqual([entry['to'] for entry in previewed['transition_history']], ['queued', 'previewed'])

    def test_persisted_flow_invalid_transition_does_not_write_history(self):
        state_path, _ = self.with_temp_state_paths()
        broker = Mock()
        broker.build_option_payload.return_value = {'tag': 'preview-payload'}
        broker.preview_order.return_value = {'ok': True}
        service = TradierExecutionService(broker=broker)

        leader = {
            'symbol': 'IWM',
            'strike': 250.0,
            'option_type': 'call',
            'expiration': '2026-03-20',
            'candidate_id': 'IWM-2026-03-20-CALL-250',
            'mid_price': 1.90,
        }
        queued = service.create_intent_from_leader(leader, mode='cash_day')
        before = self.load_json_file(state_path)

        with self.assertRaises((InvalidTransitionError, RuntimeInvalidTransitionError)):
            service.record_commit(queued, {'id': 'broker-order-1'})

        after = self.load_json_file(state_path)
        self.assertEqual(after, before)
        intent = after['intents'][0]
        self.assertEqual(intent['status'], 'queued')
        self.assertEqual([entry['to'] for entry in intent['transition_history']], ['queued'])

    def test_service_flow_invalid_inflight_progression_is_rejected_without_side_effects(self):
        state_path, _ = self.with_temp_state_paths()
        broker = Mock()
        broker.build_option_payload.return_value = {'tag': 'preview-payload'}
        broker.preview_order.return_value = {'ok': True}
        service = TradierExecutionService(broker=broker)

        leader = {
            'symbol': 'IWM',
            'strike': 250.0,
            'option_type': 'call',
            'expiration': '2026-03-20',
            'candidate_id': 'IWM-2026-03-20-CALL-250',
            'mid_price': 1.90,
        }

        queued = service.create_intent_from_leader(leader, mode='cash_day')
        previewed = service.preview_intent(queued, expiry='2026-03-20', option_type='call', strike=250.0)['intent']
        before = self.load_json_file(state_path)

        with self.assertRaises((InvalidTransitionError, RuntimeInvalidTransitionError)):
            service.record_commit(previewed, {'id': 'broker-order-1'})

        after = self.load_json_file(state_path)
        self.assertEqual(after, before)
        self.assertEqual(after['intents'][0]['status'], 'previewed')
        self.assertEqual([entry['to'] for entry in after['intents'][0]['transition_history']], ['queued', 'previewed'])
        self.assertEqual(after['orders'], [])
        self.assertEqual(after['positions'], [])

        operator_view = interpret_operator_execution_state(after['intents'][0])
        self.assertEqual(operator_view['operator_state'], 'awaiting_approval')
        self.assertEqual(operator_view['operator_stage'], 'review')
        self.assertEqual(operator_view['next_operator_action'], 'approve_reject_or_cancel')
        self.assertFalse(operator_view['is_terminal'])

    def test_operator_semantics_for_terminal_statuses(self):
        rejected = transition_intent(
            ExecutionIntent(
                mode='cash_day',
                strategy_type='long_call',
                symbol='IWM',
                contract='IWM 250 CALL 2026-03-20',
                side='buy',
                qty=1,
            ).to_dict(),
            'rejected',
            actor='test',
            note='desk rejected',
        )
        rejected_view = interpret_operator_execution_state(rejected)
        self.assertEqual(rejected_view['operator_state'], 'closed_rejected')
        self.assertEqual(rejected_view['operator_stage'], 'closed')
        self.assertEqual(rejected_view['next_operator_action'], 'none')
        self.assertTrue(rejected_view['is_terminal'])

        queued = transition_intent(
            ExecutionIntent(
                mode='cash_day',
                strategy_type='long_call',
                symbol='IWM',
                contract='IWM 250 CALL 2026-03-20',
                side='buy',
                qty=1,
            ).to_dict(),
            'queued',
            actor='test',
        )
        previewed = transition_intent(queued, 'previewed', actor='test')
        approved = transition_intent(previewed, 'approved', actor='test')
        committed = transition_intent(approved, 'committed', actor='test')
        entered = transition_intent(committed, 'entered', actor='test')
        exited = transition_intent(entered, 'exited', actor='test')
        exited_view = interpret_operator_execution_state(exited)
        self.assertEqual(exited_view['operator_state'], 'closed_exited')
        self.assertEqual(exited_view['operator_stage'], 'closed')
        self.assertEqual(exited_view['next_operator_action'], 'none')
        self.assertTrue(exited_view['is_terminal'])

    def test_service_status_mutations_delegate_to_single_transition_route(self):
        self.with_temp_state_paths()
        broker = Mock()
        broker.build_option_payload.return_value = {'tag': 'preview-payload'}
        broker.preview_order.return_value = {'ok': True}
        service = TradierExecutionService(broker=broker)

        leader = {
            'symbol': 'IWM',
            'strike': 250.0,
            'option_type': 'call',
            'expiration': '2026-03-20',
            'candidate_id': 'IWM-2026-03-20-CALL-250',
            'mid_price': 1.90,
        }

        with patch('scripts.tradier_execution_service.transition_persisted_intent', wraps=transition_persisted_intent) as routed:
            queued = service.create_intent_from_leader(leader, mode='cash_day')
            service.preview_intent(queued, expiry='2026-03-20', option_type='call', strike=250.0)
            self.assertEqual(routed.call_count, 2)
            self.assertEqual(routed.call_args_list[0].args[2], 'queued')
            self.assertEqual(routed.call_args_list[1].args[2], 'previewed')

    def test_save_state_rejects_direct_status_write_without_history(self):
        self.with_temp_state_paths()
        direct_write_state = {
            'intents': [{
                **ExecutionIntent(
                    mode='cash_day',
                    strategy_type='long_call',
                    symbol='IWM',
                    contract='IWM 250 CALL 2026-03-20',
                    side='buy',
                    qty=1,
                ).to_dict(),
                'status': 'queued',
                'transition_history': [],
            }],
            'previews': [],
            'orders': [],
            'positions': [],
            'riskDecisions': [],
        }

        with self.assertRaises((InvalidLifecycleStateError, RuntimeInvalidLifecycleStateError)):
            save_state(direct_write_state)

    def test_save_state_rejects_status_history_mismatch(self):
        self.with_temp_state_paths()
        transitioned = transition_intent(
            ExecutionIntent(
                mode='cash_day',
                strategy_type='long_call',
                symbol='IWM',
                contract='IWM 250 CALL 2026-03-20',
                side='buy',
                qty=1,
            ).to_dict(),
            'queued',
            actor='test',
        )
        mismatched_state = {
            'intents': [{**transitioned, 'status': 'previewed'}],
            'previews': [],
            'orders': [],
            'positions': [],
            'riskDecisions': [],
        }

        with self.assertRaises((InvalidLifecycleStateError, RuntimeInvalidLifecycleStateError)):
            save_state(mismatched_state)

    @patch('scripts.tradier_account.profile')
    @patch('scripts.tradier_account.balances')
    def test_readiness_snapshot_blocks_zero_option_bp(self, mock_balances, mock_profile):
        mock_profile.return_value = {
            'profile': {
                'account': {
                    'status': 'active',
                    'option_level': 2,
                }
            }
        }
        mock_balances.return_value = {
            'balances': {
                'total_cash': 200.0,
                'uncleared_funds': 200.0,
                'margin': {
                    'option_buying_power': 0.0,
                    'stock_buying_power': 0.0,
                },
            }
        }
        snap = readiness_snapshot()
        self.assertFalse(snap['ready_for_options_execution'])
        self.assertIn('option buying power is zero', snap['blockers'])

    def test_exit_policy_classify_warning(self):
        position = {'id': 'x'}
        snap = {'underlying_last': 249.95, 'option_mid': 1.70, 'option_last': 1.70}
        policy = {'underlying_soft_stop': 250.00, 'underlying_hard_stop': 249.90}
        result = classify(position, snap, policy)
        self.assertEqual(result['state'], 'warning')

    def test_exit_policy_classify_exit_now(self):
        position = {'id': 'x'}
        snap = {'underlying_last': 249.85, 'option_mid': 1.58, 'option_last': 1.58}
        policy = {'underlying_hard_stop': 249.90, 'option_hard_stop': 1.60}
        result = classify(position, snap, policy)
        self.assertEqual(result['state'], 'exit_now')

    def test_exit_policy_classify_target_zone(self):
        position = {'id': 'x'}
        snap = {'underlying_last': 250.55, 'option_mid': 2.08, 'option_last': 2.08}
        policy = {'underlying_target': 250.50, 'option_target': 2.05}
        result = classify(position, snap, policy)
        self.assertEqual(result['state'], 'target_zone')


if __name__ == '__main__':
    unittest.main()
