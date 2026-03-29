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
from scripts.tradier_execution_allocation import execution_allocation_for_intent
from scripts.tradier_execution_context import execution_context_for_intent
from scripts.tradier_execution_governance import InvalidExecutionContractCombinationError, validate_execution_contract_combinations
from scripts.tradier_execution_semantics import interpret_operator_execution_state
from tradier_execution_governance import InvalidExecutionContractCombinationError as RuntimeInvalidExecutionContractCombinationError
from scripts.tradier_execution_snapshot import build_execution_intent_snapshot
from scripts.tradier_browser_app_shell import build_browser_app_shell
from scripts.tradier_browser_page_flow import run_tradier_browser_page_flow
from scripts.tradier_cli_interaction_model import build_cli_action_invocation, build_tradier_cli_interaction_model
from scripts.tradier_cli_render_model import render_tradier_cli_product_shell
from scripts.tradier_cli_shell import render_cli_text, run_cli_shell
from scripts.tradier_dashboard_attention_feed_model import build_tradier_dashboard_attention_feed_model
from scripts.tradier_dashboard_detail_model import build_tradier_dashboard_detail_model
from scripts.tradier_dashboard_overview_model import build_tradier_dashboard_overview_model
from scripts.tradier_product_shell_model import build_tradier_product_shell_model
from scripts.tradier_runtime_server import TradierRuntimeConfig, create_runtime_server
from scripts.tradier_ui_page_flow import run_tradier_ui_page_flow
from scripts.tradier_ui_render_model import render_tradier_ui_shell
from scripts.tradier_web_server import dispatch_request
from scripts.tradier_web_shell_action_endpoint import post_tradier_web_shell_action
from scripts.tradier_web_shell_endpoint import get_tradier_web_shell_response
from scripts.tradier_web_shell_model import build_tradier_web_shell_model
from scripts.tradier_desk_action_model import build_trading_desk_action_model
from scripts.tradier_desk_prioritization_model import build_trading_desk_prioritization_model
from scripts.tradier_desk_read_model import build_trading_desk_read_model
from scripts.tradier_desk_summary_model import build_trading_desk_summary_model
from scripts.tradier_execution_snapshot_api import get_execution_intent_snapshot_payload
from scripts.tradier_execution_snapshot_queries import (
    filter_execution_snapshots_by_field,
    get_execution_snapshot_by_intent_id,
    list_latest_execution_snapshots,
)
from scripts.tradier_execution_snapshot_serialization import deserialize_execution_intent_snapshot, serialize_execution_intent_snapshot
from scripts.tradier_execution_attempt import intent_execution_attempt_for_intent
from scripts.tradier_external_reference import intent_external_reference_for_intent
from scripts.tradier_intent_decision import intent_decision_for_intent
from scripts.tradier_intent_escalation import intent_escalation_for_intent
from scripts.tradier_intent_outcome import intent_outcome_for_intent
from scripts.tradier_intent_provenance import intent_provenance_for_intent
from scripts.tradier_intent_readiness import intent_readiness_for_intent
from scripts.tradier_intent_timing import intent_timing_for_intent
from scripts.tradier_position_linkage import position_linkage_for_intent
from scripts.tradier_reconciliation_state import intent_reconciliation_for_intent
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

        self.assertEqual(queued['strategy_source'], 'tradier_leaders_board')
        self.assertEqual(queued['origin'], 'system_generated')
        self.assertEqual(queued['strategy_run_id'], 'IWM-2026-03-20-CALL-250')
        self.assertEqual(queued['decision_state'], 'proposed')
        self.assertEqual(queued['decision_actor'], 'system')
        self.assertEqual(queued['readiness_state'], 'not_ready')
        self.assertEqual(queued['readiness_reason'], 'Awaiting preview and authorization prerequisites')
        self.assertEqual(queued['outcome_state'], 'no_outcome')
        self.assertEqual(queued['escalation_state'], 'no_escalation')
        self.assertEqual(queued['timing_state'], 'no_timing_pressure')
        self.assertEqual(queued['external_reference_state'], 'no_external_reference')
        self.assertEqual(queued['attempt_state'], 'no_attempt')
        self.assertEqual(queued['attempt_count'], 0)
        self.assertEqual(queued['reconciliation_state'], 'not_reconciled')

        persisted = self.load_json_file(state_path)
        self.assertEqual(len(persisted['intents']), 1)
        intent = persisted['intents'][0]
        self.assertEqual(intent['status'], 'previewed')
        self.assertEqual([entry['to'] for entry in intent['transition_history']], ['queued', 'previewed'])
        self.assertEqual(intent['transition_history'][0]['from'], 'candidate')
        self.assertEqual(intent['transition_history'][1]['from'], 'queued')
        self.assertEqual(result['intent']['transition_history'], intent['transition_history'])

    def test_service_retry_path_updates_contracts_coherently_across_steps(self):
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
        approved = service.approve_intent(previewed, actor='ross', note='Authorized')
        ready = service.mark_intent_ready(approved, reason='Preview and approval complete')
        first_attempt = service.begin_execution_attempt(ready, attempt_id='att-1', note='Submitting to broker')
        failed = service.fail_execution_attempt(first_attempt, attempt_id='att-1', reason='Broker timeout', escalation_state='blocked')
        retried = service.retry_execution_attempt(failed, attempt_id='att-2', reason='Retry after timeout')

        failed_snapshot = build_execution_intent_snapshot(failed)
        retried_snapshot = build_execution_intent_snapshot(retried)
        persisted = self.load_json_file(state_path)

        self.assertEqual(failed_snapshot['execution_attempt']['attempt_state'], 'attempt_failed')
        self.assertEqual(failed_snapshot['execution_attempt']['attempt_count'], 1)
        self.assertEqual(failed_snapshot['outcome']['outcome_state'], 'failed_execution')
        self.assertEqual(failed_snapshot['escalation']['escalation_state'], 'blocked')
        self.assertEqual(retried_snapshot['execution_attempt']['attempt_state'], 'attempt_in_progress')
        self.assertEqual(retried_snapshot['execution_attempt']['attempt_count'], 2)
        self.assertTrue(retried_snapshot['execution_attempt']['has_multiple_attempts'])
        self.assertEqual(retried_snapshot['readiness']['readiness_state'], 'ready')
        self.assertEqual(retried_snapshot['escalation']['escalation_state'], 'warning')
        self.assertEqual(retried_snapshot['outcome']['outcome_state'], 'no_outcome')
        self.assertEqual(retried_snapshot['external_reference']['external_reference_state'], 'pending_external_reference')
        self.assertEqual(retried_snapshot['reconciliation']['reconciliation_state'], 'not_reconciled')
        self.assertEqual(persisted['intents'][0]['attempt_state'], 'attempt_in_progress')
        self.assertEqual(persisted['intents'][0]['attempt_count'], 2)
        self.assertEqual(persisted['intents'][0]['latest_attempt_id'], 'att-2')

    def test_service_unhappy_path_updates_contracts_coherently_across_steps(self):
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
        approved = service.approve_intent(previewed, actor='ross', note='Authorized')
        blocked = service.block_intent(approved, reason='Spread widened beyond tolerance', escalation_state='blocked')
        attempting = service.begin_execution_attempt(blocked, attempt_id='att-fail-1', note='Submitting despite degraded conditions')
        failed = service.fail_execution_attempt(attempting, attempt_id='att-fail-1', reason='Broker rejected order', escalation_state='blocked')

        approved_snapshot = build_execution_intent_snapshot(approved)
        blocked_snapshot = build_execution_intent_snapshot(blocked)
        attempting_snapshot = build_execution_intent_snapshot(attempting)
        failed_snapshot = build_execution_intent_snapshot(failed)
        persisted = self.load_json_file(state_path)

        self.assertEqual(approved_snapshot['decision']['decision_state'], 'approved')
        self.assertEqual(blocked_snapshot['readiness']['readiness_state'], 'blocked')
        self.assertEqual(blocked_snapshot['escalation']['escalation_state'], 'blocked')
        self.assertEqual(attempting_snapshot['execution_attempt']['attempt_state'], 'attempt_in_progress')
        self.assertEqual(attempting_snapshot['external_reference']['external_reference_state'], 'pending_external_reference')
        self.assertEqual(failed_snapshot['execution_attempt']['attempt_state'], 'attempt_failed')
        self.assertEqual(failed_snapshot['outcome']['outcome_state'], 'failed_execution')
        self.assertTrue(failed_snapshot['outcome']['is_failed_execution'])
        self.assertEqual(failed_snapshot['readiness']['readiness_state'], 'blocked')
        self.assertEqual(failed_snapshot['escalation']['escalation_state'], 'blocked')
        self.assertEqual(failed_snapshot['reconciliation']['reconciliation_state'], 'pending_confirmation')
        self.assertEqual(persisted['intents'][0]['attempt_state'], 'attempt_failed')
        self.assertEqual(persisted['intents'][0]['outcome_state'], 'failed_execution')
        self.assertEqual(persisted['intents'][0]['escalation_state'], 'blocked')

    def test_service_happy_path_updates_contracts_coherently_across_steps(self):
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
        approved = service.approve_intent(previewed, actor='ross', note='Authorized')
        ready = service.mark_intent_ready(approved, reason='Preview and approval complete')
        attempting = service.begin_execution_attempt(ready, attempt_id='att-1', note='Submitting to broker')
        committed = service.record_commit(attempting, {'id': 'broker-order-1'})['intent']

        approved_snapshot = build_execution_intent_snapshot(approved)
        ready_snapshot = build_execution_intent_snapshot(ready)
        attempting_snapshot = build_execution_intent_snapshot(attempting)
        committed_snapshot = build_execution_intent_snapshot(committed)
        persisted = self.load_json_file(state_path)

        self.assertEqual(approved_snapshot['decision']['decision_state'], 'approved')
        self.assertEqual(approved_snapshot['lifecycle']['status'], 'approved')
        self.assertEqual(ready_snapshot['readiness']['readiness_state'], 'ready')
        self.assertTrue(ready_snapshot['readiness']['is_executable_now'])
        self.assertEqual(attempting_snapshot['execution_attempt']['attempt_state'], 'attempt_in_progress')
        self.assertEqual(attempting_snapshot['external_reference']['external_reference_state'], 'pending_external_reference')
        self.assertEqual(committed_snapshot['lifecycle']['status'], 'committed')
        self.assertEqual(committed_snapshot['execution_attempt']['attempt_state'], 'attempt_completed')
        self.assertEqual(committed_snapshot['external_reference']['external_reference_state'], 'linked_external_reference')
        self.assertEqual(committed_snapshot['external_reference']['external_reference_id'], 'broker-order-1')
        self.assertEqual(committed_snapshot['outcome']['outcome_state'], 'full_execution')
        self.assertEqual(committed_snapshot['reconciliation']['reconciliation_state'], 'pending_confirmation')
        self.assertEqual(persisted['intents'][0]['decision_state'], 'approved')
        self.assertEqual(persisted['intents'][0]['attempt_state'], 'attempt_completed')
        self.assertEqual(persisted['intents'][0]['external_reference_id'], 'broker-order-1')

    def test_service_external_reference_invalidation_updates_snapshot_and_persisted_state(self):
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
        approved = service.approve_intent(previewed, actor='ross', note='Authorized')
        ready = service.mark_intent_ready(approved, reason='Preview and approval complete')
        attempting = service.begin_execution_attempt(ready, attempt_id='att-1', note='Submitting to broker')
        committed = service.record_commit(attempting, {'id': 'broker-order-1'})['intent']
        invalidated = service.invalidate_external_reference(committed, note='Broker order id could not be revalidated')

        committed_snapshot = build_execution_intent_snapshot(committed)
        invalidated_snapshot = build_execution_intent_snapshot(invalidated)
        persisted = self.load_json_file(state_path)

        self.assertEqual(committed_snapshot['external_reference']['external_reference_state'], 'linked_external_reference')
        self.assertEqual(committed_snapshot['outcome']['outcome_state'], 'full_execution')
        self.assertEqual(invalidated_snapshot['external_reference']['external_reference_state'], 'invalid_external_reference')
        self.assertFalse(invalidated_snapshot['external_reference']['reference_valid'])
        self.assertEqual(invalidated_snapshot['outcome']['outcome_state'], 'full_execution')
        self.assertTrue(invalidated_snapshot['outcome']['has_execution_effect'])
        self.assertEqual(invalidated_snapshot['reconciliation']['reconciliation_state'], 'divergent')
        self.assertTrue(invalidated_snapshot['reconciliation']['has_mismatch'])
        self.assertEqual(invalidated_snapshot['escalation']['escalation_state'], 'warning')
        self.assertEqual(persisted['intents'][0]['external_reference_state'], 'invalid_external_reference')
        self.assertEqual(persisted['intents'][0]['reconciliation_state'], 'divergent')

    def test_service_reconciliation_completion_updates_snapshot_and_persisted_state(self):
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
        approved = service.approve_intent(previewed, actor='ross', note='Authorized')
        ready = service.mark_intent_ready(approved, reason='Preview and approval complete')
        attempting = service.begin_execution_attempt(ready, attempt_id='att-1', note='Submitting to broker')
        committed = service.record_commit(attempting, {'id': 'broker-order-1'})['intent']
        reconciled = service.reconcile_intent(committed, note='Broker confirmation matched internal record')

        committed_snapshot = build_execution_intent_snapshot(committed)
        reconciled_snapshot = build_execution_intent_snapshot(reconciled)
        persisted = self.load_json_file(state_path)

        self.assertEqual(committed_snapshot['reconciliation']['reconciliation_state'], 'pending_confirmation')
        self.assertTrue(committed_snapshot['external_reference']['has_external_reference'])
        self.assertEqual(reconciled_snapshot['reconciliation']['reconciliation_state'], 'reconciled')
        self.assertTrue(reconciled_snapshot['reconciliation']['is_aligned'])
        self.assertEqual(reconciled_snapshot['outcome']['outcome_state'], 'full_execution')
        self.assertEqual(reconciled_snapshot['external_reference']['external_reference_id'], 'broker-order-1')
        self.assertEqual(reconciled_snapshot['execution_attempt']['attempt_state'], 'attempt_completed')
        self.assertEqual(persisted['intents'][0]['reconciliation_state'], 'reconciled')
        self.assertEqual(persisted['intents'][0]['reconciliation_note'], 'Broker confirmation matched internal record')

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
        self.assertEqual(operator_view['execution_context']['domain'], 'cash_day_trading')
        self.assertEqual(operator_view['execution_context']['holding_profile'], 'intraday')
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
        self.assertEqual(operator_view['execution_context']['domain'], 'cash_day_trading')
        self.assertEqual(operator_view['execution_context']['review_emphasis'], 'speed_and_day_trade_rules')
        self.assertFalse(operator_view['is_terminal'])

    def test_execution_context_contract_distinguishes_modes(self):
        cash_day = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
        ).to_dict()
        margin_swing = ExecutionIntent(
            mode='margin_swing',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='margin_swing_core',
        ).to_dict()

        cash_context = execution_context_for_intent(cash_day)
        swing_context = execution_context_for_intent(margin_swing)

        self.assertEqual(cash_context['domain'], 'cash_day_trading')
        self.assertEqual(cash_context['holding_profile'], 'intraday')
        self.assertEqual(cash_context['capital_treatment'], 'cash_settled')
        self.assertEqual(cash_context['allocation']['allocation_bucket'], 'cash_day_core')
        self.assertEqual(swing_context['domain'], 'margin_swing_trading')
        self.assertEqual(swing_context['holding_profile'], 'multi_session')
        self.assertEqual(swing_context['capital_treatment'], 'margin_enabled')
        self.assertEqual(swing_context['allocation']['allocation_bucket'], 'margin_swing_core')

    def test_execution_allocation_contract_distinguishes_capital_buckets(self):
        cash_day = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
        ).to_dict()
        margin_swing = ExecutionIntent(
            mode='margin_swing',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='margin_swing_core',
        ).to_dict()

        cash_allocation = execution_allocation_for_intent(cash_day)
        swing_allocation = execution_allocation_for_intent(margin_swing)

        self.assertEqual(cash_allocation['capital_source'], 'cash_day_trading_capital')
        self.assertEqual(cash_allocation['account_profile'], 'cash')
        self.assertEqual(swing_allocation['capital_source'], 'margin_swing_trading_capital')
        self.assertEqual(swing_allocation['account_profile'], 'margin')

    def test_reconciliation_contract_distinguishes_alignment_states(self):
        not_reconciled = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            reconciliation_state='not_reconciled',
        ).to_dict()
        reconciled = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            reconciliation_state='reconciled',
            reconciliation_note='broker matches internal state',
        ).to_dict()
        pending = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            reconciliation_state='pending_confirmation',
            reconciliation_note='awaiting broker confirmation',
        ).to_dict()
        divergent = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            reconciliation_state='divergent',
            reconciliation_note='fill mismatch detected',
        ).to_dict()

        self.assertFalse(intent_reconciliation_for_intent(not_reconciled)['is_aligned'])
        self.assertTrue(intent_reconciliation_for_intent(reconciled)['is_aligned'])
        self.assertTrue(intent_reconciliation_for_intent(pending)['is_pending_confirmation'])
        self.assertTrue(intent_reconciliation_for_intent(divergent)['has_mismatch'])

    def test_execution_attempt_contract_distinguishes_submission_states(self):
        no_attempt = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            attempt_state='no_attempt',
            attempt_count=0,
        ).to_dict()
        in_progress = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            attempt_state='attempt_in_progress',
            attempt_count=1,
            latest_attempt_id='att-1',
            latest_attempt_note='submitting to broker',
        ).to_dict()
        completed = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            attempt_state='attempt_completed',
            attempt_count=1,
            latest_attempt_id='att-1',
        ).to_dict()
        failed = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            attempt_state='attempt_failed',
            attempt_count=1,
            latest_attempt_id='att-1',
        ).to_dict()
        retried = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            attempt_state='retried_attempts',
            attempt_count=2,
            latest_attempt_id='att-2',
            latest_attempt_note='second submission attempt',
        ).to_dict()

        self.assertFalse(intent_execution_attempt_for_intent(no_attempt)['is_in_progress'])
        self.assertTrue(intent_execution_attempt_for_intent(in_progress)['is_in_progress'])
        self.assertTrue(intent_execution_attempt_for_intent(completed)['is_attempt_complete'])
        self.assertTrue(intent_execution_attempt_for_intent(failed)['is_attempt_failed'])
        self.assertTrue(intent_execution_attempt_for_intent(retried)['has_multiple_attempts'])

    def test_external_reference_contract_distinguishes_linkage_states(self):
        no_ref = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            external_reference_state='no_external_reference',
        ).to_dict()
        pending_ref = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            external_reference_state='pending_external_reference',
            external_reference_note='awaiting broker order id',
        ).to_dict()
        linked_ref = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            external_reference_state='linked_external_reference',
            external_reference_id='ord-123',
            external_reference_system='tradier',
        ).to_dict()
        invalid_ref = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            external_reference_state='invalid_external_reference',
            external_reference_id='ord-bad',
            external_reference_system='tradier',
            external_reference_note='missing upstream order',
        ).to_dict()

        self.assertFalse(intent_external_reference_for_intent(no_ref)['has_external_reference'])
        self.assertTrue(intent_external_reference_for_intent(pending_ref)['reference_pending'])
        self.assertTrue(intent_external_reference_for_intent(linked_ref)['reference_valid'])
        self.assertFalse(intent_external_reference_for_intent(invalid_ref)['reference_valid'])

    def test_tradier_cli_shell_runs_render_select_and_invoke(self):
        self.with_temp_state_paths()
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

        ready_leader = {
            'symbol': 'IWM', 'strike': 250.0, 'option_type': 'call', 'expiration': '2026-03-20',
            'candidate_id': 'IWM-2026-03-20-CALL-250', 'mid_price': 1.90,
        }
        blocked_leader = {
            'symbol': 'SPY', 'strike': 510.0, 'option_type': 'put', 'expiration': '2026-03-21',
            'candidate_id': 'SPY-2026-03-21-PUT-510', 'mid_price': 2.10,
        }

        ready = service.create_intent_from_leader(ready_leader, mode='cash_day')
        ready = service.preview_intent(ready, expiry='2026-03-20', option_type='call', strike=250.0)['intent']
        ready = service.approve_intent(ready, actor='ross', note='Authorized')
        ready = service.mark_intent_ready(ready, reason='Ready now')

        blocked = service.create_intent_from_leader(blocked_leader, mode='cash_day')
        blocked = service.preview_intent(blocked, expiry='2026-03-21', option_type='put', strike=510.0)['intent']
        blocked = service.approve_intent(blocked, actor='ross', note='Authorized')
        blocked = service.block_intent(blocked, reason='Spread widened beyond tolerance', escalation_state='blocked')

        default_result = run_cli_shell(['--latest-limit', '10'])
        default_text = render_cli_text(default_result)
        self.assertIn('=== TRADIER OPERATOR CLI ===', default_text)
        self.assertIn('Use --intent-id to focus an item', default_text)
        self.assertIn('OVERVIEW', default_text)
        self.assertIn('PRIORITIZED WORKLIST', default_text)
        self.assertIn('SELECTED ITEM', default_text)
        self.assertIn('AVAILABLE ACTIONS', default_text)
        self.assertIsNotNone(default_result['shell']['selected_detail'])

        selected_result = run_cli_shell(['--latest-limit', '10', '--intent-id', ready['intent_id']])
        self.assertEqual(selected_result['shell']['selected_detail']['intent_id'], ready['intent_id'])

        action_result = run_cli_shell([
            '--latest-limit', '10',
            '--intent-id', ready['intent_id'],
            '--action', 'begin_execution_attempt',
            '--params-json', '{"attempt_id": "att-1"}'
        ])
        self.assertEqual(action_result['action_contract']['intent_id'], ready['intent_id'])
        self.assertEqual(action_result['action_contract']['action_name'], 'begin_execution_attempt')
        self.assertEqual(action_result['action_contract']['params']['attempt_id'], 'att-1')
        rendered_action = render_cli_text(action_result)
        self.assertIn('ACTION CONTRACT', rendered_action)
        self.assertIn('begin_execution_attempt', rendered_action)

    def test_tradier_cli_shell_executes_allowed_actions_and_blocks_unavailable_ones(self):
        self.with_temp_state_paths()
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

        ready_leader = {
            'symbol': 'IWM', 'strike': 250.0, 'option_type': 'call', 'expiration': '2026-03-20',
            'candidate_id': 'IWM-2026-03-20-CALL-250', 'mid_price': 1.90,
        }
        pending_leader = {
            'symbol': 'QQQ', 'strike': 430.0, 'option_type': 'call', 'expiration': '2026-03-20',
            'candidate_id': 'QQQ-2026-03-20-CALL-430', 'mid_price': 1.50,
        }

        ready = service.create_intent_from_leader(ready_leader, mode='cash_day')
        ready = service.preview_intent(ready, expiry='2026-03-20', option_type='call', strike=250.0)['intent']
        ready = service.approve_intent(ready, actor='ross', note='Authorized')

        pending = service.create_intent_from_leader(pending_leader, mode='cash_day')
        pending = service.preview_intent(pending, expiry='2026-03-20', option_type='call', strike=430.0)['intent']
        pending = service.approve_intent(pending, actor='ross', note='Authorized')
        pending = service.mark_intent_ready(pending, reason='Ready now')
        pending = service.begin_execution_attempt(pending, attempt_id='att-1', note='Submitting to broker')
        pending = service.record_commit(pending, {'id': 'broker-order-1'})['intent']

        success = run_cli_shell([
            '--latest-limit', '10',
            '--intent-id', ready['intent_id'],
            '--action', 'mark_intent_ready',
            '--params-json', '{"reason": "Ready via CLI"}'
        ])
        self.assertIsNone(success['action_error'])
        self.assertIsNotNone(success['action_result'])
        self.assertEqual(success['action_result']['readiness_state'], 'ready')
        rendered_success = render_cli_text(success)
        self.assertIn('ACTION RESULT', rendered_success)
        self.assertIn('AVAILABLE ACTIONS', rendered_success)

        blocked = run_cli_shell([
            '--latest-limit', '10',
            '--intent-id', pending['intent_id'],
            '--action', 'retry_execution_attempt',
            '--params-json', '{"attempt_id": "att-2"}'
        ])
        self.assertIsNone(blocked['action_result'])
        self.assertIsNotNone(blocked['action_error'])
        self.assertIn('Action not allowed', blocked['action_error'])
        rendered_blocked = render_cli_text(blocked)
        self.assertIn('ACTION ERROR', rendered_blocked)
        self.assertIn('Action not allowed', rendered_blocked)

    def test_tradier_cli_interaction_model_supports_select_view_and_invoke_contract(self):
        self.with_temp_state_paths()
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

        ready_leader = {
            'symbol': 'IWM', 'strike': 250.0, 'option_type': 'call', 'expiration': '2026-03-20',
            'candidate_id': 'IWM-2026-03-20-CALL-250', 'mid_price': 1.90,
        }
        blocked_leader = {
            'symbol': 'SPY', 'strike': 510.0, 'option_type': 'put', 'expiration': '2026-03-21',
            'candidate_id': 'SPY-2026-03-21-PUT-510', 'mid_price': 2.10,
        }

        ready = service.create_intent_from_leader(ready_leader, mode='cash_day')
        ready = service.preview_intent(ready, expiry='2026-03-20', option_type='call', strike=250.0)['intent']
        ready = service.approve_intent(ready, actor='ross', note='Authorized')
        ready = service.mark_intent_ready(ready, reason='Ready now')

        blocked = service.create_intent_from_leader(blocked_leader, mode='cash_day')
        blocked = service.preview_intent(blocked, expiry='2026-03-21', option_type='put', strike=510.0)['intent']
        blocked = service.approve_intent(blocked, actor='ross', note='Authorized')
        blocked = service.block_intent(blocked, reason='Spread widened beyond tolerance', escalation_state='blocked')

        interaction = build_tradier_cli_interaction_model(latest_limit=10)

        self.assertEqual(interaction['kind'], 'tradier.cli_interaction_model')
        self.assertGreaterEqual(len(interaction['worklist']), 2)
        self.assertIsNotNone(interaction['selected_detail'])
        self.assertIsNotNone(interaction['action_invocation'])
        selected_id = interaction['selected_detail']['intent_id']
        self.assertEqual(selected_id, interaction['action_invocation']['intent_id'])
        self.assertIn('required_fields', interaction['action_invocation']['invoke_contract'])
        self.assertIn('action_name', interaction['action_invocation']['invoke_contract']['required_fields'])

        ready_interaction = build_tradier_cli_interaction_model(latest_limit=10, selected_intent_id=ready['intent_id'])
        self.assertEqual(ready_interaction['selected_detail']['intent_id'], ready['intent_id'])
        self.assertTrue(ready_interaction['selected_detail']['actions']['begin_execution_attempt']['available'])

        invocation = build_cli_action_invocation(ready['intent_id'], 'begin_execution_attempt', {'attempt_id': 'att-1'})
        self.assertEqual(invocation['intent_id'], ready['intent_id'])
        self.assertEqual(invocation['action_name'], 'begin_execution_attempt')
        self.assertEqual(invocation['params']['attempt_id'], 'att-1')

    def test_tradier_cli_render_model_renders_overview_worklist_detail_and_actions(self):
        self.with_temp_state_paths()
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

        ready_leader = {
            'symbol': 'IWM', 'strike': 250.0, 'option_type': 'call', 'expiration': '2026-03-20',
            'candidate_id': 'IWM-2026-03-20-CALL-250', 'mid_price': 1.90,
        }
        blocked_leader = {
            'symbol': 'SPY', 'strike': 510.0, 'option_type': 'put', 'expiration': '2026-03-21',
            'candidate_id': 'SPY-2026-03-21-PUT-510', 'mid_price': 2.10,
        }
        pending_leader = {
            'symbol': 'QQQ', 'strike': 430.0, 'option_type': 'call', 'expiration': '2026-03-20',
            'candidate_id': 'QQQ-2026-03-20-CALL-430', 'mid_price': 1.50,
        }
        divergent_leader = {
            'symbol': 'DIA', 'strike': 390.0, 'option_type': 'put', 'expiration': '2026-03-20',
            'candidate_id': 'DIA-2026-03-20-PUT-390', 'mid_price': 1.20,
        }

        ready = service.create_intent_from_leader(ready_leader, mode='cash_day')
        ready = service.preview_intent(ready, expiry='2026-03-20', option_type='call', strike=250.0)['intent']
        ready = service.approve_intent(ready, actor='ross', note='Authorized')
        ready = service.mark_intent_ready(ready, reason='Ready now')

        blocked = service.create_intent_from_leader(blocked_leader, mode='cash_day')
        blocked = service.preview_intent(blocked, expiry='2026-03-21', option_type='put', strike=510.0)['intent']
        blocked = service.approve_intent(blocked, actor='ross', note='Authorized')
        blocked = service.block_intent(blocked, reason='Spread widened beyond tolerance', escalation_state='blocked')

        pending = service.create_intent_from_leader(pending_leader, mode='cash_day')
        pending = service.preview_intent(pending, expiry='2026-03-20', option_type='call', strike=430.0)['intent']
        pending = service.approve_intent(pending, actor='ross', note='Authorized')
        pending = service.mark_intent_ready(pending, reason='Ready now')
        pending = service.begin_execution_attempt(pending, attempt_id='att-pending', note='Submitting to broker')
        service.record_commit(pending, {'id': 'broker-order-pending'})

        divergent = service.create_intent_from_leader(divergent_leader, mode='cash_day')
        divergent = service.preview_intent(divergent, expiry='2026-03-20', option_type='put', strike=390.0)['intent']
        divergent = service.approve_intent(divergent, actor='ross', note='Authorized')
        divergent = service.mark_intent_ready(divergent, reason='Ready now')
        divergent = service.begin_execution_attempt(divergent, attempt_id='att-div', note='Submitting to broker')
        divergent = service.record_commit(divergent, {'id': 'broker-order-div'})['intent']
        divergent = service.invalidate_external_reference(divergent, note='Broker order id could not be revalidated')

        rendered = render_tradier_cli_product_shell(latest_limit=10)

        self.assertEqual(rendered['kind'], 'tradier.cli_render_model')
        self.assertEqual(rendered['overview_summary']['ready_count'], 1)
        self.assertEqual(rendered['prioritized_worklist'][0]['priority_category'], 'divergent')
        self.assertEqual(rendered['prioritized_worklist'][1]['priority_category'], 'blocked')
        self.assertIsNotNone(rendered['selected_detail'])
        self.assertEqual(rendered['selected_detail']['intent_id'], rendered['prioritized_worklist'][0]['intent_id'])
        self.assertIn('operator', rendered['selected_detail'])
        self.assertIn('actions', rendered['selected_detail'])
        self.assertEqual(rendered['selected_actions'], rendered['selected_detail']['actions'])

    def test_tradier_browser_page_flow_serves_acts_and_refreshes(self):
        self.with_temp_state_paths()
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
            'symbol': 'IWM', 'strike': 250.0, 'option_type': 'call', 'expiration': '2026-03-20',
            'candidate_id': 'IWM-2026-03-20-CALL-250', 'mid_price': 1.90,
        }

        ready = service.create_intent_from_leader(leader, mode='cash_day')
        ready = service.preview_intent(ready, expiry='2026-03-20', option_type='call', strike=250.0)['intent']
        ready = service.approve_intent(ready, actor='ross', note='Authorized')

        flow = run_tradier_browser_page_flow(
            'mark_intent_ready',
            intent_id=ready['intent_id'],
            params={'reason': 'Ready via browser flow'},
            latest_limit=10,
        )

        self.assertEqual(flow['initial']['status_code'], 200)
        self.assertEqual(flow['initial']['page']['kind'], 'tradier.browser_page_response')
        self.assertIn('<main id=\'app-shell\'>', flow['initial']['page']['data']['html'])
        self.assertEqual(flow['action']['status_code'], 200)
        self.assertEqual(flow['action']['response']['status'], 'ok')
        self.assertEqual(flow['action']['response']['data']['action_name'], 'mark_intent_ready')
        self.assertEqual(flow['refreshed']['status_code'], 200)
        self.assertEqual(flow['refreshed']['page']['kind'], 'tradier.browser_page_response')
        self.assertEqual(
            flow['refreshed']['page']['data']['render_model']['detail_panel']['core']['readiness']['readiness_state'],
            'ready',
        )

    def test_tradier_browser_app_shell_builds_first_page_from_server_backed_shell(self):
        self.with_temp_state_paths()
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

        ready_leader = {
            'symbol': 'IWM', 'strike': 250.0, 'option_type': 'call', 'expiration': '2026-03-20',
            'candidate_id': 'IWM-2026-03-20-CALL-250', 'mid_price': 1.90,
        }
        blocked_leader = {
            'symbol': 'SPY', 'strike': 510.0, 'option_type': 'put', 'expiration': '2026-03-21',
            'candidate_id': 'SPY-2026-03-21-PUT-510', 'mid_price': 2.10,
        }

        ready = service.create_intent_from_leader(ready_leader, mode='cash_day')
        ready = service.preview_intent(ready, expiry='2026-03-20', option_type='call', strike=250.0)['intent']
        ready = service.approve_intent(ready, actor='ross', note='Authorized')
        service.mark_intent_ready(ready, reason='Ready now')

        blocked = service.create_intent_from_leader(blocked_leader, mode='cash_day')
        blocked = service.preview_intent(blocked, expiry='2026-03-21', option_type='put', strike=510.0)['intent']
        blocked = service.approve_intent(blocked, actor='ross', note='Authorized')
        service.block_intent(blocked, reason='Spread widened beyond tolerance', escalation_state='blocked')

        page = build_browser_app_shell(latest_limit=10)

        self.assertEqual(page['kind'], 'tradier.browser_app_shell')
        self.assertEqual(page['status_code'], 200)
        self.assertEqual(page['render_model']['kind'], 'tradier.ui_render_model')
        self.assertIn("<main id='app-shell' class='responsive-shell mobile-first'>", page['html'])
        self.assertIn("<meta name='viewport' content='width=device-width, initial-scale=1'>", page['html'])
        self.assertIn("<section id='overview' class='panel overview-panel'>", page['html'])
        self.assertIn("<section id='worklist' class='panel worklist-panel'>", page['html'])
        self.assertIn("<section id='detail' class='panel detail-panel'>", page['html'])
        self.assertIn("<section id='actions' class='panel actions-panel'>", page['html'])
        self.assertIn('touch-target', page['html'])
        self.assertIn('Tradier Operator Shell', page['html'])

    def test_tradier_ui_page_flow_renders_acts_and_rerenders(self):
        self.with_temp_state_paths()
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
            'symbol': 'IWM', 'strike': 250.0, 'option_type': 'call', 'expiration': '2026-03-20',
            'candidate_id': 'IWM-2026-03-20-CALL-250', 'mid_price': 1.90,
        }

        ready = service.create_intent_from_leader(leader, mode='cash_day')
        ready = service.preview_intent(ready, expiry='2026-03-20', option_type='call', strike=250.0)['intent']
        ready = service.approve_intent(ready, actor='ross', note='Authorized')

        flow = run_tradier_ui_page_flow(
            'mark_intent_ready',
            intent_id=ready['intent_id'],
            params={'reason': 'Ready via page flow'},
            latest_limit=10,
        )

        self.assertEqual(flow['initial']['status_code'], 200)
        self.assertEqual(flow['initial']['render']['kind'], 'tradier.ui_render_model')
        self.assertEqual(flow['action']['status_code'], 200)
        self.assertEqual(flow['action']['response']['status'], 'ok')
        self.assertEqual(flow['action']['response']['data']['action_name'], 'mark_intent_ready')
        self.assertEqual(flow['refreshed']['status_code'], 200)
        self.assertEqual(flow['refreshed']['render']['kind'], 'tradier.ui_render_model')
        self.assertEqual(flow['refreshed']['render']['detail_panel']['intent_id'], ready['intent_id'])
        self.assertEqual(flow['refreshed']['render']['detail_panel']['core']['readiness']['readiness_state'], 'ready')
        self.assertEqual(flow['refreshed']['shell']['data']['selected_detail']['core']['readiness']['readiness_state'], 'ready')

    def test_tradier_ui_render_model_renders_server_backed_shell_sections(self):
        self.with_temp_state_paths()
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

        ready_leader = {
            'symbol': 'IWM', 'strike': 250.0, 'option_type': 'call', 'expiration': '2026-03-20',
            'candidate_id': 'IWM-2026-03-20-CALL-250', 'mid_price': 1.90,
        }
        blocked_leader = {
            'symbol': 'SPY', 'strike': 510.0, 'option_type': 'put', 'expiration': '2026-03-21',
            'candidate_id': 'SPY-2026-03-21-PUT-510', 'mid_price': 2.10,
        }

        ready = service.create_intent_from_leader(ready_leader, mode='cash_day')
        ready = service.preview_intent(ready, expiry='2026-03-20', option_type='call', strike=250.0)['intent']
        ready = service.approve_intent(ready, actor='ross', note='Authorized')
        service.mark_intent_ready(ready, reason='Ready now')

        blocked = service.create_intent_from_leader(blocked_leader, mode='cash_day')
        blocked = service.preview_intent(blocked, expiry='2026-03-21', option_type='put', strike=510.0)['intent']
        blocked = service.approve_intent(blocked, actor='ross', note='Authorized')
        service.block_intent(blocked, reason='Spread widened beyond tolerance', escalation_state='blocked')

        status_code, shell_response = dispatch_request('GET', '/shell?latest_limit=10')
        ui = render_tradier_ui_shell(shell_response)

        self.assertEqual(status_code, 200)
        self.assertEqual(ui['kind'], 'tradier.ui_render_model')
        self.assertEqual(ui['header']['title'], 'Tradier Operator Shell')
        self.assertEqual(ui['header']['status'], 'ok')
        self.assertEqual(ui['overview_panel']['ready_count'], 1)
        self.assertEqual(ui['overview_panel']['blocked_count'], 1)
        self.assertGreaterEqual(len(ui['worklist_panel']), 2)
        self.assertIsNotNone(ui['detail_panel']['intent_id'])
        self.assertIsNotNone(ui['detail_panel']['core'])
        self.assertIsNotNone(ui['actions_panel'])

    def test_tradier_runtime_server_exposes_private_default_config_and_server(self):
        runtime = create_runtime_server(TradierRuntimeConfig())
        self.assertEqual(runtime['kind'], 'tradier.runtime_server')
        self.assertEqual(runtime['config']['host'], '127.0.0.1')
        self.assertEqual(runtime['config']['port'], 8000)
        self.assertTrue(runtime['config']['is_private_default'])
        runtime['server'].server_close()

    def test_tradier_runtime_server_accepts_explicit_local_network_config(self):
        runtime = create_runtime_server(TradierRuntimeConfig(host='0.0.0.0', port=8123))
        self.assertEqual(runtime['config']['host'], '0.0.0.0')
        self.assertEqual(runtime['config']['port'], 8123)
        self.assertFalse(runtime['config']['is_private_default'])
        runtime['server'].server_close()

    def test_tradier_web_server_dispatches_read_and_action_routes(self):
        self.with_temp_state_paths()
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

        ready_leader = {
            'symbol': 'IWM', 'strike': 250.0, 'option_type': 'call', 'expiration': '2026-03-20',
            'candidate_id': 'IWM-2026-03-20-CALL-250', 'mid_price': 1.90,
        }
        pending_leader = {
            'symbol': 'QQQ', 'strike': 430.0, 'option_type': 'call', 'expiration': '2026-03-20',
            'candidate_id': 'QQQ-2026-03-20-CALL-430', 'mid_price': 1.50,
        }

        ready = service.create_intent_from_leader(ready_leader, mode='cash_day')
        ready = service.preview_intent(ready, expiry='2026-03-20', option_type='call', strike=250.0)['intent']
        ready = service.approve_intent(ready, actor='ross', note='Authorized')

        pending = service.create_intent_from_leader(pending_leader, mode='cash_day')
        pending = service.preview_intent(pending, expiry='2026-03-20', option_type='call', strike=430.0)['intent']
        pending = service.approve_intent(pending, actor='ross', note='Authorized')
        pending = service.mark_intent_ready(pending, reason='Ready now')
        pending = service.begin_execution_attempt(pending, attempt_id='att-1', note='Submitting to broker')
        pending = service.record_commit(pending, {'id': 'broker-order-1'})['intent']

        read_status, read_payload = dispatch_request('GET', '/shell?latest_limit=10')
        self.assertEqual(read_status, 200)
        self.assertEqual(read_payload['kind'], 'tradier.web_shell_endpoint_response')
        self.assertEqual(read_payload['status'], 'ok')

        page_status, page_payload = dispatch_request('GET', '/app?latest_limit=10')
        self.assertEqual(page_status, 200)
        self.assertEqual(page_payload['kind'], 'tradier.browser_page_response')
        self.assertEqual(page_payload['status'], 'ok')
        self.assertIn('<main id=\'app-shell\'>', page_payload['data']['html'])

        action_status, action_payload = dispatch_request('POST', '/shell/action', {
            'intent_id': ready['intent_id'],
            'action_name': 'mark_intent_ready',
            'params': {'reason': 'Ready via server'},
            'latest_limit': 10,
        })
        self.assertEqual(action_status, 200)
        self.assertEqual(action_payload['status'], 'ok')
        self.assertEqual(action_payload['data']['action_result']['readiness_state'], 'ready')

        blocked_status, blocked_payload = dispatch_request('POST', '/shell/action', {
            'intent_id': pending['intent_id'],
            'action_name': 'retry_execution_attempt',
            'params': {'attempt_id': 'att-2'},
            'latest_limit': 10,
        })
        self.assertEqual(blocked_status, 400)
        self.assertEqual(blocked_payload['status'], 'rejected')
        self.assertIn('Action not allowed', blocked_payload['error'])

    def test_tradier_web_shell_action_endpoint_executes_allowed_and_rejects_blocked_actions(self):
        self.with_temp_state_paths()
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

        ready_leader = {
            'symbol': 'IWM', 'strike': 250.0, 'option_type': 'call', 'expiration': '2026-03-20',
            'candidate_id': 'IWM-2026-03-20-CALL-250', 'mid_price': 1.90,
        }
        pending_leader = {
            'symbol': 'QQQ', 'strike': 430.0, 'option_type': 'call', 'expiration': '2026-03-20',
            'candidate_id': 'QQQ-2026-03-20-CALL-430', 'mid_price': 1.50,
        }

        ready = service.create_intent_from_leader(ready_leader, mode='cash_day')
        ready = service.preview_intent(ready, expiry='2026-03-20', option_type='call', strike=250.0)['intent']
        ready = service.approve_intent(ready, actor='ross', note='Authorized')

        pending = service.create_intent_from_leader(pending_leader, mode='cash_day')
        pending = service.preview_intent(pending, expiry='2026-03-20', option_type='call', strike=430.0)['intent']
        pending = service.approve_intent(pending, actor='ross', note='Authorized')
        pending = service.mark_intent_ready(pending, reason='Ready now')
        pending = service.begin_execution_attempt(pending, attempt_id='att-1', note='Submitting to broker')
        pending = service.record_commit(pending, {'id': 'broker-order-1'})['intent']

        allowed = post_tradier_web_shell_action(
            ready['intent_id'],
            'mark_intent_ready',
            {'reason': 'Ready via endpoint'},
            latest_limit=10,
        )
        self.assertEqual(allowed['kind'], 'tradier.web_shell_action_endpoint_response')
        self.assertEqual(allowed['status'], 'ok')
        self.assertIsNone(allowed['error'])
        self.assertEqual(allowed['data']['action_name'], 'mark_intent_ready')
        self.assertEqual(allowed['data']['action_result']['readiness_state'], 'ready')
        self.assertEqual(allowed['data']['shell']['kind'], 'tradier.web_shell_endpoint_response')

        blocked = post_tradier_web_shell_action(
            pending['intent_id'],
            'retry_execution_attempt',
            {'attempt_id': 'att-2'},
            latest_limit=10,
        )
        self.assertEqual(blocked['status'], 'rejected')
        self.assertIn('Action not allowed', blocked['error'])
        self.assertEqual(blocked['data']['intent_id'], pending['intent_id'])
        self.assertEqual(blocked['data']['action_name'], 'retry_execution_attempt')

    def test_tradier_web_shell_endpoint_returns_stable_shell_payload(self):
        self.with_temp_state_paths()
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

        ready_leader = {
            'symbol': 'IWM', 'strike': 250.0, 'option_type': 'call', 'expiration': '2026-03-20',
            'candidate_id': 'IWM-2026-03-20-CALL-250', 'mid_price': 1.90,
        }
        blocked_leader = {
            'symbol': 'SPY', 'strike': 510.0, 'option_type': 'put', 'expiration': '2026-03-21',
            'candidate_id': 'SPY-2026-03-21-PUT-510', 'mid_price': 2.10,
        }

        ready = service.create_intent_from_leader(ready_leader, mode='cash_day')
        ready = service.preview_intent(ready, expiry='2026-03-20', option_type='call', strike=250.0)['intent']
        ready = service.approve_intent(ready, actor='ross', note='Authorized')
        service.mark_intent_ready(ready, reason='Ready now')

        blocked = service.create_intent_from_leader(blocked_leader, mode='cash_day')
        blocked = service.preview_intent(blocked, expiry='2026-03-21', option_type='put', strike=510.0)['intent']
        blocked = service.approve_intent(blocked, actor='ross', note='Authorized')
        service.block_intent(blocked, reason='Spread widened beyond tolerance', escalation_state='blocked')

        response = get_tradier_web_shell_response(latest_limit=10)

        self.assertEqual(response['kind'], 'tradier.web_shell_endpoint_response')
        self.assertEqual(response['status'], 'ok')
        self.assertEqual(response['data']['kind'], 'tradier.web_shell_model')
        self.assertIn('overview', response['data'])
        self.assertIn('worklist', response['data'])
        self.assertIn('selected_detail', response['data'])
        self.assertIn('selected_actions', response['data'])
        self.assertGreaterEqual(len(response['data']['worklist']['items']), 2)

    def test_tradier_web_shell_model_exposes_overview_worklist_detail_and_actions(self):
        self.with_temp_state_paths()
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

        ready_leader = {
            'symbol': 'IWM', 'strike': 250.0, 'option_type': 'call', 'expiration': '2026-03-20',
            'candidate_id': 'IWM-2026-03-20-CALL-250', 'mid_price': 1.90,
        }
        blocked_leader = {
            'symbol': 'SPY', 'strike': 510.0, 'option_type': 'put', 'expiration': '2026-03-21',
            'candidate_id': 'SPY-2026-03-21-PUT-510', 'mid_price': 2.10,
        }
        pending_leader = {
            'symbol': 'QQQ', 'strike': 430.0, 'option_type': 'call', 'expiration': '2026-03-20',
            'candidate_id': 'QQQ-2026-03-20-CALL-430', 'mid_price': 1.50,
        }
        divergent_leader = {
            'symbol': 'DIA', 'strike': 390.0, 'option_type': 'put', 'expiration': '2026-03-20',
            'candidate_id': 'DIA-2026-03-20-PUT-390', 'mid_price': 1.20,
        }

        ready = service.create_intent_from_leader(ready_leader, mode='cash_day')
        ready = service.preview_intent(ready, expiry='2026-03-20', option_type='call', strike=250.0)['intent']
        ready = service.approve_intent(ready, actor='ross', note='Authorized')
        ready = service.mark_intent_ready(ready, reason='Ready now')

        blocked = service.create_intent_from_leader(blocked_leader, mode='cash_day')
        blocked = service.preview_intent(blocked, expiry='2026-03-21', option_type='put', strike=510.0)['intent']
        blocked = service.approve_intent(blocked, actor='ross', note='Authorized')
        blocked = service.block_intent(blocked, reason='Spread widened beyond tolerance', escalation_state='blocked')

        pending = service.create_intent_from_leader(pending_leader, mode='cash_day')
        pending = service.preview_intent(pending, expiry='2026-03-20', option_type='call', strike=430.0)['intent']
        pending = service.approve_intent(pending, actor='ross', note='Authorized')
        pending = service.mark_intent_ready(pending, reason='Ready now')
        pending = service.begin_execution_attempt(pending, attempt_id='att-pending', note='Submitting to broker')
        service.record_commit(pending, {'id': 'broker-order-pending'})

        divergent = service.create_intent_from_leader(divergent_leader, mode='cash_day')
        divergent = service.preview_intent(divergent, expiry='2026-03-20', option_type='put', strike=390.0)['intent']
        divergent = service.approve_intent(divergent, actor='ross', note='Authorized')
        divergent = service.mark_intent_ready(divergent, reason='Ready now')
        divergent = service.begin_execution_attempt(divergent, attempt_id='att-div', note='Submitting to broker')
        divergent = service.record_commit(divergent, {'id': 'broker-order-div'})['intent']
        divergent = service.invalidate_external_reference(divergent, note='Broker order id could not be revalidated')

        web_shell = build_tradier_web_shell_model(latest_limit=10)

        self.assertEqual(web_shell['kind'], 'tradier.web_shell_model')
        self.assertEqual(web_shell['overview']['kind'], 'tradier.dashboard_overview_model')
        self.assertIn('items', web_shell['worklist'])
        self.assertGreaterEqual(len(web_shell['worklist']['items']), 4)
        self.assertIsNotNone(web_shell['selected_detail'])
        self.assertIsNotNone(web_shell['selected_actions'])
        self.assertEqual(web_shell['worklist']['items'][0]['priority_category'], 'divergent')
        self.assertEqual(web_shell['selected_detail']['intent_id'], web_shell['worklist']['items'][0]['snapshot']['intent_id'])
        self.assertEqual(web_shell['selected_actions'], web_shell['selected_detail']['operator_context']['actions'])

    def test_tradier_product_shell_model_packages_overview_worklist_detail_and_actions(self):
        self.with_temp_state_paths()
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

        ready_leader = {
            'symbol': 'IWM', 'strike': 250.0, 'option_type': 'call', 'expiration': '2026-03-20',
            'candidate_id': 'IWM-2026-03-20-CALL-250', 'mid_price': 1.90,
        }
        blocked_leader = {
            'symbol': 'SPY', 'strike': 510.0, 'option_type': 'put', 'expiration': '2026-03-21',
            'candidate_id': 'SPY-2026-03-21-PUT-510', 'mid_price': 2.10,
        }
        pending_leader = {
            'symbol': 'QQQ', 'strike': 430.0, 'option_type': 'call', 'expiration': '2026-03-20',
            'candidate_id': 'QQQ-2026-03-20-CALL-430', 'mid_price': 1.50,
        }
        divergent_leader = {
            'symbol': 'DIA', 'strike': 390.0, 'option_type': 'put', 'expiration': '2026-03-20',
            'candidate_id': 'DIA-2026-03-20-PUT-390', 'mid_price': 1.20,
        }

        ready = service.create_intent_from_leader(ready_leader, mode='cash_day')
        ready = service.preview_intent(ready, expiry='2026-03-20', option_type='call', strike=250.0)['intent']
        ready = service.approve_intent(ready, actor='ross', note='Authorized')
        ready = service.mark_intent_ready(ready, reason='Ready now')

        blocked = service.create_intent_from_leader(blocked_leader, mode='cash_day')
        blocked = service.preview_intent(blocked, expiry='2026-03-21', option_type='put', strike=510.0)['intent']
        blocked = service.approve_intent(blocked, actor='ross', note='Authorized')
        blocked = service.block_intent(blocked, reason='Spread widened beyond tolerance', escalation_state='blocked')

        pending = service.create_intent_from_leader(pending_leader, mode='cash_day')
        pending = service.preview_intent(pending, expiry='2026-03-20', option_type='call', strike=430.0)['intent']
        pending = service.approve_intent(pending, actor='ross', note='Authorized')
        pending = service.mark_intent_ready(pending, reason='Ready now')
        pending = service.begin_execution_attempt(pending, attempt_id='att-pending', note='Submitting to broker')
        service.record_commit(pending, {'id': 'broker-order-pending'})

        divergent = service.create_intent_from_leader(divergent_leader, mode='cash_day')
        divergent = service.preview_intent(divergent, expiry='2026-03-20', option_type='put', strike=390.0)['intent']
        divergent = service.approve_intent(divergent, actor='ross', note='Authorized')
        divergent = service.mark_intent_ready(divergent, reason='Ready now')
        divergent = service.begin_execution_attempt(divergent, attempt_id='att-div', note='Submitting to broker')
        divergent = service.record_commit(divergent, {'id': 'broker-order-div'})['intent']
        divergent = service.invalidate_external_reference(divergent, note='Broker order id could not be revalidated')

        shell = build_tradier_product_shell_model(latest_limit=10)

        self.assertEqual(shell['kind'], 'tradier.product_shell_model')
        self.assertEqual(shell['overview']['kind'], 'tradier.dashboard_overview_model')
        self.assertEqual(shell['attention_feed']['kind'], 'tradier.dashboard_attention_feed_model')
        self.assertEqual(shell['worklist']['kind'], 'tradier.trading_desk_prioritization_model')
        self.assertIsNotNone(shell['detail'])
        self.assertIsNotNone(shell['selected_item'])
        self.assertEqual(shell['overview']['summary']['ready_count'], 1)
        self.assertEqual(shell['attention_feed']['feed']['current_attention'][0]['priority_category'], 'divergent')
        self.assertEqual(shell['worklist']['items'][0]['priority_category'], 'divergent')
        self.assertEqual(shell['detail']['intent_id'], shell['worklist']['items'][0]['snapshot']['intent_id'])
        self.assertIn('actions', shell['detail']['operator_context'])
        self.assertEqual(shell['selected_item']['snapshot']['intent_id'], shell['detail']['intent_id'])

    def test_dashboard_attention_feed_model_reports_attention_and_recent_review(self):
        self.with_temp_state_paths()
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

        ready_leader = {
            'symbol': 'IWM', 'strike': 250.0, 'option_type': 'call', 'expiration': '2026-03-20',
            'candidate_id': 'IWM-2026-03-20-CALL-250', 'mid_price': 1.90,
        }
        blocked_leader = {
            'symbol': 'SPY', 'strike': 510.0, 'option_type': 'put', 'expiration': '2026-03-21',
            'candidate_id': 'SPY-2026-03-21-PUT-510', 'mid_price': 2.10,
        }
        pending_leader = {
            'symbol': 'QQQ', 'strike': 430.0, 'option_type': 'call', 'expiration': '2026-03-20',
            'candidate_id': 'QQQ-2026-03-20-CALL-430', 'mid_price': 1.50,
        }
        divergent_leader = {
            'symbol': 'DIA', 'strike': 390.0, 'option_type': 'put', 'expiration': '2026-03-20',
            'candidate_id': 'DIA-2026-03-20-PUT-390', 'mid_price': 1.20,
        }

        ready = service.create_intent_from_leader(ready_leader, mode='cash_day')
        ready = service.preview_intent(ready, expiry='2026-03-20', option_type='call', strike=250.0)['intent']
        ready = service.approve_intent(ready, actor='ross', note='Authorized')
        service.mark_intent_ready(ready, reason='Ready now')

        blocked = service.create_intent_from_leader(blocked_leader, mode='cash_day')
        blocked = service.preview_intent(blocked, expiry='2026-03-21', option_type='put', strike=510.0)['intent']
        blocked = service.approve_intent(blocked, actor='ross', note='Authorized')
        service.block_intent(blocked, reason='Spread widened beyond tolerance', escalation_state='blocked')

        pending = service.create_intent_from_leader(pending_leader, mode='cash_day')
        pending = service.preview_intent(pending, expiry='2026-03-20', option_type='call', strike=430.0)['intent']
        pending = service.approve_intent(pending, actor='ross', note='Authorized')
        pending = service.mark_intent_ready(pending, reason='Ready now')
        pending = service.begin_execution_attempt(pending, attempt_id='att-pending', note='Submitting to broker')
        service.record_commit(pending, {'id': 'broker-order-pending'})

        divergent = service.create_intent_from_leader(divergent_leader, mode='cash_day')
        divergent = service.preview_intent(divergent, expiry='2026-03-20', option_type='put', strike=390.0)['intent']
        divergent = service.approve_intent(divergent, actor='ross', note='Authorized')
        divergent = service.mark_intent_ready(divergent, reason='Ready now')
        divergent = service.begin_execution_attempt(divergent, attempt_id='att-div', note='Submitting to broker')
        divergent = service.record_commit(divergent, {'id': 'broker-order-div'})['intent']
        service.invalidate_external_reference(divergent, note='Broker order id could not be revalidated')

        feed = build_tradier_dashboard_attention_feed_model(latest_limit=10, feed_limit=4)

        self.assertEqual(feed['kind'], 'tradier.dashboard_attention_feed_model')
        self.assertTrue(feed['feed']['needs_attention_now'])
        self.assertEqual(len(feed['feed']['current_attention']), 3)
        self.assertEqual(feed['feed']['current_attention'][0]['priority_category'], 'divergent')
        self.assertEqual(feed['feed']['current_attention'][1]['priority_category'], 'blocked')
        self.assertEqual(feed['feed']['current_attention'][2]['priority_category'], 'pending_confirmation')
        self.assertIn('requires review', feed['feed']['current_attention'][0]['reason'])
        self.assertEqual(len(feed['feed']['recent_review']), 4)
        self.assertEqual(feed['feed']['recent_review'][0]['priority_category'], 'divergent')
        self.assertEqual(feed['feed']['recent_review'][3]['priority_category'], 'ready')

    def test_dashboard_detail_model_reports_single_intent_detail_context(self):
        self.with_temp_state_paths()
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
        approved = service.approve_intent(previewed, actor='ross', note='Authorized')
        ready = service.mark_intent_ready(approved, reason='Ready now')
        attempting = service.begin_execution_attempt(ready, attempt_id='att-1', note='Submitting to broker')
        committed = service.record_commit(attempting, {'id': 'broker-order-1'})['intent']
        reconciled = service.reconcile_intent(committed, note='Broker confirmation matched internal record')

        detail = build_tradier_dashboard_detail_model(reconciled)

        self.assertEqual(detail['kind'], 'tradier.dashboard_detail_model')
        self.assertEqual(detail['snapshot_version'], 1)
        self.assertEqual(detail['intent_id'], reconciled['intent_id'])
        self.assertEqual(detail['core']['lifecycle']['status'], 'committed')
        self.assertEqual(detail['core']['decision']['decision_state'], 'approved')
        self.assertEqual(detail['core']['readiness']['readiness_state'], 'ready')
        self.assertEqual(detail['core']['outcome']['outcome_state'], 'full_execution')
        self.assertEqual(detail['operator_context']['operator']['operator_state'], 'sent_to_broker')
        self.assertTrue(detail['operator_context']['actions']['invalidate_external_reference']['available'] is False or isinstance(detail['operator_context']['actions']['invalidate_external_reference']['available'], bool))
        self.assertEqual(detail['external_reference']['external_reference_state'], 'linked_external_reference')
        self.assertEqual(detail['execution_attempt']['attempt_state'], 'attempt_completed')
        self.assertEqual(detail['reconciliation']['reconciliation_state'], 'reconciled')
        self.assertEqual(detail['recent_context']['latest_attempt_id'], 'att-1')
        self.assertEqual(detail['recent_context']['reconciliation_state'], 'reconciled')
        self.assertGreaterEqual(detail['recent_context']['history_count'], 4)

    def test_dashboard_overview_model_reports_summary_attention_and_recent_activity(self):
        self.with_temp_state_paths()
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

        ready_leader = {
            'symbol': 'IWM', 'strike': 250.0, 'option_type': 'call', 'expiration': '2026-03-20',
            'candidate_id': 'IWM-2026-03-20-CALL-250', 'mid_price': 1.90,
        }
        blocked_leader = {
            'symbol': 'SPY', 'strike': 510.0, 'option_type': 'put', 'expiration': '2026-03-21',
            'candidate_id': 'SPY-2026-03-21-PUT-510', 'mid_price': 2.10,
        }
        pending_leader = {
            'symbol': 'QQQ', 'strike': 430.0, 'option_type': 'call', 'expiration': '2026-03-20',
            'candidate_id': 'QQQ-2026-03-20-CALL-430', 'mid_price': 1.50,
        }
        divergent_leader = {
            'symbol': 'DIA', 'strike': 390.0, 'option_type': 'put', 'expiration': '2026-03-20',
            'candidate_id': 'DIA-2026-03-20-PUT-390', 'mid_price': 1.20,
        }

        ready = service.create_intent_from_leader(ready_leader, mode='cash_day')
        ready = service.preview_intent(ready, expiry='2026-03-20', option_type='call', strike=250.0)['intent']
        ready = service.approve_intent(ready, actor='ross', note='Authorized')
        service.mark_intent_ready(ready, reason='Ready now')

        blocked = service.create_intent_from_leader(blocked_leader, mode='cash_day')
        blocked = service.preview_intent(blocked, expiry='2026-03-21', option_type='put', strike=510.0)['intent']
        blocked = service.approve_intent(blocked, actor='ross', note='Authorized')
        service.block_intent(blocked, reason='Spread widened beyond tolerance', escalation_state='blocked')

        pending = service.create_intent_from_leader(pending_leader, mode='cash_day')
        pending = service.preview_intent(pending, expiry='2026-03-20', option_type='call', strike=430.0)['intent']
        pending = service.approve_intent(pending, actor='ross', note='Authorized')
        pending = service.mark_intent_ready(pending, reason='Ready now')
        pending = service.begin_execution_attempt(pending, attempt_id='att-pending', note='Submitting to broker')
        service.record_commit(pending, {'id': 'broker-order-pending'})

        divergent = service.create_intent_from_leader(divergent_leader, mode='cash_day')
        divergent = service.preview_intent(divergent, expiry='2026-03-20', option_type='put', strike=390.0)['intent']
        divergent = service.approve_intent(divergent, actor='ross', note='Authorized')
        divergent = service.mark_intent_ready(divergent, reason='Ready now')
        divergent = service.begin_execution_attempt(divergent, attempt_id='att-div', note='Submitting to broker')
        divergent = service.record_commit(divergent, {'id': 'broker-order-div'})['intent']
        service.invalidate_external_reference(divergent, note='Broker order id could not be revalidated')

        overview = build_tradier_dashboard_overview_model(latest_limit=10, recent_activity_limit=4)

        self.assertEqual(overview['kind'], 'tradier.dashboard_overview_model')
        self.assertEqual(overview['summary']['ready_count'], 1)
        self.assertEqual(overview['summary']['blocked_count'], 1)
        self.assertEqual(overview['summary']['pending_confirmation_count'], 1)
        self.assertEqual(overview['summary']['divergent_count'], 1)
        self.assertTrue(overview['attention']['needs_attention_now'])
        self.assertEqual(len(overview['attention']['top_priority_items']), 3)
        self.assertEqual(overview['attention']['top_priority_items'][0]['priority_category'], 'divergent')
        self.assertEqual(overview['attention']['top_priority_items'][1]['priority_category'], 'blocked')
        self.assertEqual(overview['attention']['top_priority_items'][2]['priority_category'], 'pending_confirmation')
        self.assertEqual(len(overview['recent_activity']), 4)

    def test_trading_desk_prioritization_model_orders_items_by_operator_priority(self):
        self.with_temp_state_paths()
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

        ready_leader = {
            'symbol': 'IWM',
            'strike': 250.0,
            'option_type': 'call',
            'expiration': '2026-03-20',
            'candidate_id': 'IWM-2026-03-20-CALL-250',
            'mid_price': 1.90,
        }
        blocked_leader = {
            'symbol': 'SPY',
            'strike': 510.0,
            'option_type': 'put',
            'expiration': '2026-03-21',
            'candidate_id': 'SPY-2026-03-21-PUT-510',
            'mid_price': 2.10,
        }
        pending_leader = {
            'symbol': 'QQQ',
            'strike': 430.0,
            'option_type': 'call',
            'expiration': '2026-03-20',
            'candidate_id': 'QQQ-2026-03-20-CALL-430',
            'mid_price': 1.50,
        }
        divergent_leader = {
            'symbol': 'DIA',
            'strike': 390.0,
            'option_type': 'put',
            'expiration': '2026-03-20',
            'candidate_id': 'DIA-2026-03-20-PUT-390',
            'mid_price': 1.20,
        }

        ready = service.create_intent_from_leader(ready_leader, mode='cash_day')
        ready = service.preview_intent(ready, expiry='2026-03-20', option_type='call', strike=250.0)['intent']
        ready = service.approve_intent(ready, actor='ross', note='Authorized')
        service.mark_intent_ready(ready, reason='Ready now')

        blocked = service.create_intent_from_leader(blocked_leader, mode='cash_day')
        blocked = service.preview_intent(blocked, expiry='2026-03-21', option_type='put', strike=510.0)['intent']
        blocked = service.approve_intent(blocked, actor='ross', note='Authorized')
        service.block_intent(blocked, reason='Spread widened beyond tolerance', escalation_state='blocked')

        pending = service.create_intent_from_leader(pending_leader, mode='cash_day')
        pending = service.preview_intent(pending, expiry='2026-03-20', option_type='call', strike=430.0)['intent']
        pending = service.approve_intent(pending, actor='ross', note='Authorized')
        pending = service.mark_intent_ready(pending, reason='Ready now')
        pending = service.begin_execution_attempt(pending, attempt_id='att-pending', note='Submitting to broker')
        service.record_commit(pending, {'id': 'broker-order-pending'})

        divergent = service.create_intent_from_leader(divergent_leader, mode='cash_day')
        divergent = service.preview_intent(divergent, expiry='2026-03-20', option_type='put', strike=390.0)['intent']
        divergent = service.approve_intent(divergent, actor='ross', note='Authorized')
        divergent = service.mark_intent_ready(divergent, reason='Ready now')
        divergent = service.begin_execution_attempt(divergent, attempt_id='att-div', note='Submitting to broker')
        divergent = service.record_commit(divergent, {'id': 'broker-order-div'})['intent']
        service.invalidate_external_reference(divergent, note='Broker order id could not be revalidated')

        model = build_trading_desk_prioritization_model(latest_limit=10)
        categories = [item['priority_category'] for item in model['items'][:4]]

        self.assertEqual(model['kind'], 'tradier.trading_desk_prioritization_model')
        self.assertEqual(categories, ['divergent', 'blocked', 'pending_confirmation', 'ready'])
        self.assertEqual(model['items'][0]['priority_rank'], 1)
        self.assertEqual(model['items'][1]['priority_rank'], 2)
        self.assertEqual(model['items'][2]['priority_rank'], 3)
        self.assertEqual(model['items'][3]['priority_rank'], 4)

    def test_trading_desk_summary_model_reports_counts_and_attention(self):
        self.with_temp_state_paths()
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

        ready_leader = {
            'symbol': 'IWM',
            'strike': 250.0,
            'option_type': 'call',
            'expiration': '2026-03-20',
            'candidate_id': 'IWM-2026-03-20-CALL-250',
            'mid_price': 1.90,
        }
        blocked_leader = {
            'symbol': 'SPY',
            'strike': 510.0,
            'option_type': 'put',
            'expiration': '2026-03-21',
            'candidate_id': 'SPY-2026-03-21-PUT-510',
            'mid_price': 2.10,
        }
        pending_leader = {
            'symbol': 'QQQ',
            'strike': 430.0,
            'option_type': 'call',
            'expiration': '2026-03-20',
            'candidate_id': 'QQQ-2026-03-20-CALL-430',
            'mid_price': 1.50,
        }
        divergent_leader = {
            'symbol': 'DIA',
            'strike': 390.0,
            'option_type': 'put',
            'expiration': '2026-03-20',
            'candidate_id': 'DIA-2026-03-20-PUT-390',
            'mid_price': 1.20,
        }

        ready = service.create_intent_from_leader(ready_leader, mode='cash_day')
        ready = service.preview_intent(ready, expiry='2026-03-20', option_type='call', strike=250.0)['intent']
        ready = service.approve_intent(ready, actor='ross', note='Authorized')
        service.mark_intent_ready(ready, reason='Ready now')

        blocked = service.create_intent_from_leader(blocked_leader, mode='cash_day')
        blocked = service.preview_intent(blocked, expiry='2026-03-21', option_type='put', strike=510.0)['intent']
        blocked = service.approve_intent(blocked, actor='ross', note='Authorized')
        service.block_intent(blocked, reason='Spread widened beyond tolerance', escalation_state='blocked')

        pending = service.create_intent_from_leader(pending_leader, mode='cash_day')
        pending = service.preview_intent(pending, expiry='2026-03-20', option_type='call', strike=430.0)['intent']
        pending = service.approve_intent(pending, actor='ross', note='Authorized')
        pending = service.mark_intent_ready(pending, reason='Ready now')
        pending = service.begin_execution_attempt(pending, attempt_id='att-pending', note='Submitting to broker')
        service.record_commit(pending, {'id': 'broker-order-pending'})

        divergent = service.create_intent_from_leader(divergent_leader, mode='cash_day')
        divergent = service.preview_intent(divergent, expiry='2026-03-20', option_type='put', strike=390.0)['intent']
        divergent = service.approve_intent(divergent, actor='ross', note='Authorized')
        divergent = service.mark_intent_ready(divergent, reason='Ready now')
        divergent = service.begin_execution_attempt(divergent, attempt_id='att-div', note='Submitting to broker')
        divergent = service.record_commit(divergent, {'id': 'broker-order-div'})['intent']
        service.invalidate_external_reference(divergent, note='Broker order id could not be revalidated')

        summary = build_trading_desk_summary_model(latest_limit=10)

        self.assertEqual(summary['kind'], 'tradier.trading_desk_summary_model')
        self.assertEqual(summary['summary']['ready_count'], 1)
        self.assertEqual(summary['summary']['blocked_count'], 1)
        self.assertEqual(summary['summary']['pending_confirmation_count'], 1)
        self.assertEqual(summary['summary']['divergent_count'], 1)
        self.assertTrue(summary['summary']['needs_attention_now'])

    def test_trading_desk_action_model_exposes_state_aware_actions(self):
        self.with_temp_state_paths()
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

        ready_leader = {
            'symbol': 'IWM',
            'strike': 250.0,
            'option_type': 'call',
            'expiration': '2026-03-20',
            'candidate_id': 'IWM-2026-03-20-CALL-250',
            'mid_price': 1.90,
        }
        blocked_leader = {
            'symbol': 'SPY',
            'strike': 510.0,
            'option_type': 'put',
            'expiration': '2026-03-21',
            'candidate_id': 'SPY-2026-03-21-PUT-510',
            'mid_price': 2.10,
        }
        pending_leader = {
            'symbol': 'QQQ',
            'strike': 430.0,
            'option_type': 'call',
            'expiration': '2026-03-20',
            'candidate_id': 'QQQ-2026-03-20-CALL-430',
            'mid_price': 1.50,
        }
        divergent_leader = {
            'symbol': 'DIA',
            'strike': 390.0,
            'option_type': 'put',
            'expiration': '2026-03-20',
            'candidate_id': 'DIA-2026-03-20-PUT-390',
            'mid_price': 1.20,
        }

        ready = service.create_intent_from_leader(ready_leader, mode='cash_day')
        ready = service.preview_intent(ready, expiry='2026-03-20', option_type='call', strike=250.0)['intent']
        ready = service.approve_intent(ready, actor='ross', note='Authorized')
        service.mark_intent_ready(ready, reason='Ready now')

        blocked = service.create_intent_from_leader(blocked_leader, mode='cash_day')
        blocked = service.preview_intent(blocked, expiry='2026-03-21', option_type='put', strike=510.0)['intent']
        blocked = service.approve_intent(blocked, actor='ross', note='Authorized')
        blocked = service.block_intent(blocked, reason='Spread widened beyond tolerance', escalation_state='blocked')

        pending = service.create_intent_from_leader(pending_leader, mode='cash_day')
        pending = service.preview_intent(pending, expiry='2026-03-20', option_type='call', strike=430.0)['intent']
        pending = service.approve_intent(pending, actor='ross', note='Authorized')
        pending = service.mark_intent_ready(pending, reason='Ready now')
        pending = service.begin_execution_attempt(pending, attempt_id='att-pending', note='Submitting to broker')
        service.record_commit(pending, {'id': 'broker-order-pending'})

        divergent = service.create_intent_from_leader(divergent_leader, mode='cash_day')
        divergent = service.preview_intent(divergent, expiry='2026-03-20', option_type='put', strike=390.0)['intent']
        divergent = service.approve_intent(divergent, actor='ross', note='Authorized')
        divergent = service.mark_intent_ready(divergent, reason='Ready now')
        divergent = service.begin_execution_attempt(divergent, attempt_id='att-div', note='Submitting to broker')
        divergent = service.record_commit(divergent, {'id': 'broker-order-div'})['intent']
        service.invalidate_external_reference(divergent, note='Broker order id could not be revalidated')

        desk = build_trading_desk_action_model(latest_limit=10)
        views = desk['views']

        self.assertEqual(desk['kind'], 'tradier.trading_desk_action_model')
        ready_actions = views['ready_intents'][0]['actions']
        blocked_actions = views['blocked_intents'][0]['actions']
        pending_actions = views['pending_confirmation_intents'][0]['actions']
        divergent_actions = views['divergent_intents'][0]['actions']

        self.assertTrue(ready_actions['begin_execution_attempt']['available'])
        self.assertTrue(ready_actions['block_intent']['available'])
        self.assertFalse(ready_actions['reconcile_intent']['available'])

        self.assertTrue(blocked_actions['retry_execution_attempt']['available'])
        self.assertFalse(blocked_actions['begin_execution_attempt']['available'])

        self.assertTrue(pending_actions['reconcile_intent']['available'])
        self.assertFalse(pending_actions['retry_execution_attempt']['available'])

        self.assertTrue(divergent_actions['invalidate_external_reference']['available'])
        self.assertFalse(divergent_actions['reconcile_intent']['available'])

    def test_trading_desk_read_model_categorizes_operator_views(self):
        self.with_temp_state_paths()
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

        ready_leader = {
            'symbol': 'IWM',
            'strike': 250.0,
            'option_type': 'call',
            'expiration': '2026-03-20',
            'candidate_id': 'IWM-2026-03-20-CALL-250',
            'mid_price': 1.90,
        }
        blocked_leader = {
            'symbol': 'SPY',
            'strike': 510.0,
            'option_type': 'put',
            'expiration': '2026-03-21',
            'candidate_id': 'SPY-2026-03-21-PUT-510',
            'mid_price': 2.10,
        }
        pending_leader = {
            'symbol': 'QQQ',
            'strike': 430.0,
            'option_type': 'call',
            'expiration': '2026-03-20',
            'candidate_id': 'QQQ-2026-03-20-CALL-430',
            'mid_price': 1.50,
        }
        divergent_leader = {
            'symbol': 'DIA',
            'strike': 390.0,
            'option_type': 'put',
            'expiration': '2026-03-20',
            'candidate_id': 'DIA-2026-03-20-PUT-390',
            'mid_price': 1.20,
        }

        ready = service.create_intent_from_leader(ready_leader, mode='cash_day')
        ready = service.preview_intent(ready, expiry='2026-03-20', option_type='call', strike=250.0)['intent']
        ready = service.approve_intent(ready, actor='ross', note='Authorized')
        service.mark_intent_ready(ready, reason='Ready now')

        blocked = service.create_intent_from_leader(blocked_leader, mode='cash_day')
        blocked = service.preview_intent(blocked, expiry='2026-03-21', option_type='put', strike=510.0)['intent']
        blocked = service.approve_intent(blocked, actor='ross', note='Authorized')
        service.block_intent(blocked, reason='Spread widened beyond tolerance', escalation_state='blocked')

        pending = service.create_intent_from_leader(pending_leader, mode='cash_day')
        pending = service.preview_intent(pending, expiry='2026-03-20', option_type='call', strike=430.0)['intent']
        pending = service.approve_intent(pending, actor='ross', note='Authorized')
        pending = service.mark_intent_ready(pending, reason='Ready now')
        pending = service.begin_execution_attempt(pending, attempt_id='att-pending', note='Submitting to broker')
        service.record_commit(pending, {'id': 'broker-order-pending'})

        divergent = service.create_intent_from_leader(divergent_leader, mode='cash_day')
        divergent = service.preview_intent(divergent, expiry='2026-03-20', option_type='put', strike=390.0)['intent']
        divergent = service.approve_intent(divergent, actor='ross', note='Authorized')
        divergent = service.mark_intent_ready(divergent, reason='Ready now')
        divergent = service.begin_execution_attempt(divergent, attempt_id='att-div', note='Submitting to broker')
        divergent = service.record_commit(divergent, {'id': 'broker-order-div'})['intent']
        service.invalidate_external_reference(divergent, note='Broker order id could not be revalidated')

        desk = build_trading_desk_read_model(latest_limit=10)
        views = desk['views']

        self.assertEqual(desk['kind'], 'tradier.trading_desk_read_model')
        self.assertEqual(desk['source']['kind'], 'tradier.execution_intent_snapshot_collection')
        self.assertGreaterEqual(len(views['latest_activity']), 4)
        self.assertEqual(len(views['ready_intents']), 1)
        self.assertEqual(len(views['blocked_intents']), 1)
        self.assertEqual(len(views['pending_confirmation_intents']), 1)
        self.assertEqual(len(views['divergent_intents']), 1)
        self.assertEqual(views['ready_intents'][0]['snapshot']['readiness']['readiness_state'], 'ready')
        self.assertEqual(views['blocked_intents'][0]['snapshot']['escalation']['escalation_state'], 'blocked')
        self.assertEqual(views['pending_confirmation_intents'][0]['snapshot']['reconciliation']['reconciliation_state'], 'pending_confirmation')
        self.assertEqual(views['divergent_intents'][0]['snapshot']['reconciliation']['reconciliation_state'], 'divergent')

    def test_snapshot_query_boundary_supports_fetch_by_intent_id_latest_and_filter(self):
        self.with_temp_state_paths()
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

        leader_a = {
            'symbol': 'IWM',
            'strike': 250.0,
            'option_type': 'call',
            'expiration': '2026-03-20',
            'candidate_id': 'IWM-2026-03-20-CALL-250',
            'mid_price': 1.90,
        }
        leader_b = {
            'symbol': 'SPY',
            'strike': 510.0,
            'option_type': 'put',
            'expiration': '2026-03-21',
            'candidate_id': 'SPY-2026-03-21-PUT-510',
            'mid_price': 2.10,
        }

        first = service.create_intent_from_leader(leader_a, mode='cash_day')
        first = service.preview_intent(first, expiry='2026-03-20', option_type='call', strike=250.0)['intent']
        first = service.approve_intent(first, actor='ross', note='Authorized')
        first = service.mark_intent_ready(first, reason='Ready now')

        second = service.create_intent_from_leader(leader_b, mode='cash_day')
        second = service.preview_intent(second, expiry='2026-03-21', option_type='put', strike=510.0)['intent']
        second = service.approve_intent(second, actor='ross', note='Authorized')
        second = service.block_intent(second, reason='Spread widened beyond tolerance', escalation_state='blocked')

        by_id = get_execution_snapshot_by_intent_id(first['intent_id'])
        latest = list_latest_execution_snapshots(limit=2)
        filtered = filter_execution_snapshots_by_field('escalation_state', 'blocked', limit=10)

        self.assertEqual(by_id['kind'], 'tradier.execution_intent_snapshot')
        self.assertEqual(by_id['snapshot_version'], 1)
        self.assertEqual(by_id['snapshot']['intent_id'], first['intent_id'])
        self.assertEqual(by_id['snapshot']['readiness']['readiness_state'], 'ready')

        self.assertEqual(latest['kind'], 'tradier.execution_intent_snapshot_collection')
        self.assertEqual(latest['query']['mode'], 'latest')
        self.assertEqual(latest['count'], 2)
        self.assertTrue(all(item['snapshot_version'] == 1 for item in latest['items']))
        self.assertEqual(latest['items'][-1]['snapshot']['intent_id'], second['intent_id'])

        self.assertEqual(filtered['kind'], 'tradier.execution_intent_snapshot_collection')
        self.assertEqual(filtered['query']['mode'], 'filter')
        self.assertEqual(filtered['count'], 1)
        self.assertEqual(filtered['items'][0]['snapshot']['intent_id'], second['intent_id'])
        self.assertEqual(filtered['items'][0]['snapshot']['escalation']['escalation_state'], 'blocked')
        self.assertEqual(filtered['items'][0]['snapshot']['decision']['decision_state'], 'approved')

    def test_snapshot_api_returns_versioned_consumer_payload(self):
        candidate = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=2,
            allocation_bucket='cash_day_core',
            position_relationship='open_new_position',
            strategy_family='scalping_buy',
            strategy_source='tradier_leaders_board',
            strategy_run_id='run-123',
            origin='system_generated',
            decision_state='approved',
            decision_actor='ross',
            readiness_state='ready',
            readiness_reason='all checks complete',
            outcome_state='partial_execution',
            outcome_reason='1 of 2 filled',
            effected_qty=1,
            escalation_state='warning',
            escalation_reason='spread widened',
            timing_state='time_sensitive',
            timing_reason='window closing',
            external_reference_state='linked_external_reference',
            external_reference_id='ord-123',
            external_reference_system='tradier',
            attempt_state='attempt_completed',
            attempt_count=1,
            latest_attempt_id='att-1',
            reconciliation_state='pending_confirmation',
        ).to_dict()
        queued = transition_intent(candidate, 'queued', actor='test')
        previewed = transition_intent(queued, 'previewed', actor='test')
        approved = transition_intent(previewed, 'approved', actor='test')

        payload = get_execution_intent_snapshot_payload(approved)

        self.assertEqual(payload['kind'], 'tradier.execution_intent_snapshot')
        self.assertEqual(payload['snapshot_version'], 1)
        self.assertEqual(payload['snapshot']['lifecycle']['status'], 'approved')
        self.assertEqual(payload['snapshot']['decision']['decision_state'], 'approved')
        self.assertEqual(payload['snapshot']['external_reference']['external_reference_state'], 'linked_external_reference')
        self.assertEqual(payload['snapshot']['execution_attempt']['attempt_state'], 'attempt_completed')
        self.assertEqual(payload['snapshot']['reconciliation']['reconciliation_state'], 'pending_confirmation')

    def test_snapshot_api_payload_preserves_governed_snapshot_shape(self):
        candidate = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            position_relationship='open_new_position',
            strategy_family='scalping_buy',
            strategy_source='tradier_leaders_board',
            strategy_run_id='run-abc',
            origin='system_generated',
            decision_state='approved',
            decision_actor='ross',
            readiness_state='ready',
            outcome_state='no_outcome',
            escalation_state='no_escalation',
            timing_state='no_timing_pressure',
            external_reference_state='pending_external_reference',
            attempt_state='attempt_in_progress',
            attempt_count=1,
            latest_attempt_id='att-1',
            reconciliation_state='pending_confirmation',
        ).to_dict()
        queued = transition_intent(candidate, 'queued', actor='test')
        previewed = transition_intent(queued, 'previewed', actor='test')
        approved = transition_intent(previewed, 'approved', actor='test')

        payload = get_execution_intent_snapshot_payload(approved)
        snapshot = payload['snapshot']

        self.assertIn('lifecycle', snapshot)
        self.assertIn('decision', snapshot)
        self.assertIn('readiness', snapshot)
        self.assertIn('outcome', snapshot)
        self.assertIn('escalation', snapshot)
        self.assertIn('timing', snapshot)
        self.assertIn('external_reference', snapshot)
        self.assertIn('execution_attempt', snapshot)
        self.assertIn('reconciliation', snapshot)
        self.assertIn('provenance', snapshot)
        self.assertIn('execution_context', snapshot)
        self.assertIn('position_linkage', snapshot)
        self.assertIn('operator', snapshot)

    def test_snapshot_serialization_round_trip_preserves_composed_state(self):
        candidate = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=2,
            allocation_bucket='cash_day_core',
            position_relationship='open_new_position',
            strategy_family='scalping_buy',
            strategy_source='tradier_leaders_board',
            strategy_run_id='run-123',
            origin='system_generated',
            decision_state='approved',
            decision_actor='ross',
            readiness_state='ready',
            readiness_reason='all checks complete',
            outcome_state='partial_execution',
            outcome_reason='1 of 2 filled',
            effected_qty=1,
            escalation_state='warning',
            escalation_reason='spread widened',
            timing_state='time_sensitive',
            timing_reason='window closing',
            external_reference_state='linked_external_reference',
            external_reference_id='ord-123',
            external_reference_system='tradier',
            attempt_state='attempt_completed',
            attempt_count=1,
            latest_attempt_id='att-1',
            reconciliation_state='pending_confirmation',
        ).to_dict()
        queued = transition_intent(candidate, 'queued', actor='test')
        previewed = transition_intent(queued, 'previewed', actor='test')
        approved = transition_intent(previewed, 'approved', actor='test')
        snapshot = build_execution_intent_snapshot(approved)

        payload = serialize_execution_intent_snapshot(snapshot)
        restored = deserialize_execution_intent_snapshot(payload)

        self.assertEqual(restored, snapshot)
        self.assertEqual(restored['decision']['decision_state'], 'approved')
        self.assertEqual(restored['outcome']['outcome_state'], 'partial_execution')
        self.assertEqual(restored['external_reference']['external_reference_state'], 'linked_external_reference')
        self.assertEqual(restored['execution_attempt']['attempt_state'], 'attempt_completed')
        self.assertEqual(restored['reconciliation']['reconciliation_state'], 'pending_confirmation')

    def test_snapshot_deserialization_rejects_contradictory_state_without_normalizing(self):
        bad_snapshot = {
            'intent_id': 'intent_bad',
            'lifecycle': {'status': 'approved', 'history_count': 3, 'latest_transition': {'to': 'approved'}},
            'decision': {'decision_state': 'approved', 'decision_actor': 'ross', 'decision_note': '', 'is_authorized': True, 'is_decision_terminal': False},
            'readiness': {'readiness_state': 'ready', 'readiness_reason': '', 'is_executable_now': True, 'is_blocked': False},
            'outcome': {'outcome_state': 'full_execution', 'outcome_reason': 'filled', 'effected_qty': 2, 'has_execution_effect': True, 'is_outcome_complete': True, 'is_failed_execution': False},
            'escalation': {'escalation_state': 'no_escalation', 'escalation_reason': '', 'needs_operator_attention': False, 'blocks_autonomous_progress': False, 'is_terminal_attention_state': False},
            'timing': {'timing_state': 'no_timing_pressure', 'timing_reason': '', 'is_urgent': False, 'is_expired': False, 'is_actionable': True},
            'external_reference': {'external_reference_state': 'no_external_reference', 'external_reference_id': None, 'external_reference_system': '', 'external_reference_note': '', 'has_external_reference': False, 'reference_pending': False, 'reference_valid': False},
            'execution_attempt': {'attempt_state': 'attempt_completed', 'attempt_count': 1, 'latest_attempt_id': 'att-1', 'latest_attempt_note': '', 'is_in_progress': False, 'is_attempt_complete': True, 'is_attempt_failed': False, 'has_multiple_attempts': False},
            'reconciliation': {'reconciliation_state': 'not_reconciled', 'reconciliation_note': '', 'is_aligned': False, 'is_pending_confirmation': False, 'has_mismatch': False},
            'provenance': {'strategy_family': 'scalping_buy', 'strategy_source': 'tradier_leaders_board', 'strategy_run_id': 'run-123', 'origin': 'system_generated'},
            'execution_context': {'mode': 'cash_day', 'domain': 'cash_day_trading', 'operator_lane': 'day_trade', 'holding_profile': 'intraday', 'capital_treatment': 'cash_settled', 'review_emphasis': 'speed_and_day_trade_rules', 'allocation': {'allocation_bucket': 'cash_day_core', 'capital_source': 'cash_day_trading_capital', 'account_profile': 'cash'}},
            'position_linkage': {'position_relationship': 'open_new_position', 'position_effect': 'open', 'holding_scope': 'new_exposure', 'position_id': None},
            'operator': {'operator_state': 'ready_to_send', 'operator_stage': 'execution', 'next_operator_action': 'commit_reject_or_cancel', 'is_terminal': False},
        }

        payload = {'snapshot_version': 1, 'snapshot': bad_snapshot}
        with self.assertRaises((InvalidExecutionContractCombinationError, RuntimeInvalidExecutionContractCombinationError)):
            deserialize_execution_intent_snapshot(payload)

    def test_cross_contract_governance_accepts_representative_valid_state(self):
        contracts = {
            'lifecycle': {'status': 'approved', 'history_count': 3, 'latest_transition': {'to': 'approved'}},
            'decision': {'decision_state': 'approved', 'is_authorized': True},
            'readiness': {'readiness_state': 'ready', 'is_executable_now': True},
            'outcome': {'outcome_state': 'no_outcome', 'has_execution_effect': False},
            'escalation': {'escalation_state': 'no_escalation', 'is_terminal_attention_state': False},
            'timing': {'timing_state': 'time_sensitive', 'is_expired': False},
            'external_reference': {
                'external_reference_state': 'pending_external_reference',
                'has_external_reference': False,
                'reference_pending': True,
            },
            'execution_attempt': {'attempt_state': 'attempt_in_progress', 'attempt_count': 1},
            'reconciliation': {'reconciliation_state': 'pending_confirmation', 'is_aligned': False, 'has_mismatch': False},
        }
        validate_execution_contract_combinations(contracts)

    def test_cross_contract_governance_rejects_contradictory_states(self):
        with self.assertRaises((InvalidExecutionContractCombinationError, RuntimeInvalidExecutionContractCombinationError)):
            validate_execution_contract_combinations({
                'lifecycle': {'status': 'approved', 'history_count': 3, 'latest_transition': {'to': 'approved'}},
                'decision': {'decision_state': 'proposed', 'is_authorized': False},
                'readiness': {'readiness_state': 'ready', 'is_executable_now': True},
                'outcome': {'outcome_state': 'no_outcome', 'has_execution_effect': False},
                'escalation': {'escalation_state': 'no_escalation', 'is_terminal_attention_state': False},
                'timing': {'timing_state': 'no_timing_pressure', 'is_expired': False},
                'external_reference': {'external_reference_state': 'no_external_reference', 'has_external_reference': False, 'reference_pending': False},
                'execution_attempt': {'attempt_state': 'no_attempt', 'attempt_count': 0},
                'reconciliation': {'reconciliation_state': 'not_reconciled', 'is_aligned': False, 'has_mismatch': False},
            })

        contradictory = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=2,
            allocation_bucket='cash_day_core',
            position_relationship='open_new_position',
            strategy_family='scalping_buy',
            strategy_source='tradier_leaders_board',
            strategy_run_id='run-123',
            origin='system_generated',
            decision_state='approved',
            decision_actor='ross',
            readiness_state='ready',
            readiness_reason='all checks complete',
            outcome_state='full_execution',
            outcome_reason='fully filled',
            effected_qty=2,
            escalation_state='no_escalation',
            timing_state='no_timing_pressure',
            external_reference_state='no_external_reference',
            attempt_state='attempt_completed',
            attempt_count=1,
            latest_attempt_id='att-1',
            reconciliation_state='not_reconciled',
        ).to_dict()
        contradictory = transition_intent(contradictory, 'queued', actor='test')
        contradictory = transition_intent(contradictory, 'previewed', actor='test')
        contradictory = transition_intent(contradictory, 'approved', actor='test')

        with self.assertRaises((InvalidExecutionContractCombinationError, RuntimeInvalidExecutionContractCombinationError)):
            interpret_operator_execution_state(contradictory)

    def test_composed_execution_snapshot_includes_all_contracts(self):
        candidate = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=2,
            allocation_bucket='cash_day_core',
            position_relationship='open_new_position',
            strategy_family='scalping_buy',
            strategy_source='tradier_leaders_board',
            strategy_run_id='run-123',
            origin='system_generated',
            decision_state='approved',
            decision_actor='ross',
            readiness_state='ready',
            readiness_reason='all checks complete',
            outcome_state='partial_execution',
            outcome_reason='1 of 2 filled',
            effected_qty=1,
            escalation_state='warning',
            escalation_reason='spread widened',
            timing_state='time_sensitive',
            timing_reason='window closing',
            external_reference_state='linked_external_reference',
            external_reference_id='ord-123',
            external_reference_system='tradier',
            attempt_state='attempt_completed',
            attempt_count=1,
            latest_attempt_id='att-1',
            reconciliation_state='pending_confirmation',
        ).to_dict()
        queued = transition_intent(candidate, 'queued', actor='test')
        previewed = transition_intent(queued, 'previewed', actor='test')
        approved = transition_intent(previewed, 'approved', actor='test')

        snapshot = build_execution_intent_snapshot(approved)

        self.assertEqual(snapshot['lifecycle']['status'], 'approved')
        self.assertEqual(snapshot['decision']['decision_state'], 'approved')
        self.assertEqual(snapshot['readiness']['readiness_state'], 'ready')
        self.assertEqual(snapshot['outcome']['outcome_state'], 'partial_execution')
        self.assertEqual(snapshot['escalation']['escalation_state'], 'warning')
        self.assertEqual(snapshot['timing']['timing_state'], 'time_sensitive')
        self.assertEqual(snapshot['external_reference']['external_reference_state'], 'linked_external_reference')
        self.assertEqual(snapshot['execution_attempt']['attempt_state'], 'attempt_completed')
        self.assertEqual(snapshot['reconciliation']['reconciliation_state'], 'pending_confirmation')
        self.assertEqual(snapshot['provenance']['strategy_source'], 'tradier_leaders_board')
        self.assertEqual(snapshot['execution_context']['allocation']['capital_source'], 'cash_day_trading_capital')
        self.assertEqual(snapshot['position_linkage']['position_effect'], 'open')
        self.assertEqual(snapshot['operator']['operator_state'], 'ready_to_send')

    def test_intent_timing_contract_distinguishes_urgency_and_expiry_states(self):
        normal = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            timing_state='no_timing_pressure',
        ).to_dict()
        urgent = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            timing_state='time_sensitive',
            timing_reason='0DTE window narrowing',
        ).to_dict()
        expired = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            timing_state='expired',
            timing_reason='signal stale',
        ).to_dict()

        self.assertFalse(intent_timing_for_intent(normal)['is_urgent'])
        self.assertTrue(intent_timing_for_intent(urgent)['is_urgent'])
        self.assertFalse(intent_timing_for_intent(urgent)['is_expired'])
        self.assertTrue(intent_timing_for_intent(expired)['is_expired'])
        self.assertFalse(intent_timing_for_intent(expired)['is_actionable'])

    def test_intent_escalation_contract_distinguishes_attention_states(self):
        normal = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            escalation_state='no_escalation',
        ).to_dict()
        warning = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            escalation_state='warning',
            escalation_reason='spread widened',
        ).to_dict()
        blocked = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            escalation_state='blocked',
            escalation_reason='account dependency',
        ).to_dict()
        terminal = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            escalation_state='terminal_failure',
            escalation_reason='contract invalid',
        ).to_dict()

        self.assertFalse(intent_escalation_for_intent(normal)['needs_operator_attention'])
        self.assertTrue(intent_escalation_for_intent(warning)['needs_operator_attention'])
        self.assertFalse(intent_escalation_for_intent(warning)['blocks_autonomous_progress'])
        self.assertTrue(intent_escalation_for_intent(blocked)['blocks_autonomous_progress'])
        self.assertTrue(intent_escalation_for_intent(terminal)['is_terminal_attention_state'])

    def test_intent_outcome_contract_distinguishes_execution_results(self):
        no_outcome = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=2,
            allocation_bucket='cash_day_core',
            outcome_state='no_outcome',
        ).to_dict()
        partial = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=2,
            allocation_bucket='cash_day_core',
            outcome_state='partial_execution',
            outcome_reason='1 contract filled',
            effected_qty=1,
        ).to_dict()
        full = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=2,
            allocation_bucket='cash_day_core',
            outcome_state='full_execution',
            outcome_reason='fully filled',
            effected_qty=2,
        ).to_dict()
        failed = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=2,
            allocation_bucket='cash_day_core',
            outcome_state='failed_execution',
            outcome_reason='broker reject',
            effected_qty=0,
        ).to_dict()

        self.assertFalse(intent_outcome_for_intent(no_outcome)['has_execution_effect'])
        self.assertTrue(intent_outcome_for_intent(partial)['has_execution_effect'])
        self.assertFalse(intent_outcome_for_intent(partial)['is_outcome_complete'])
        self.assertTrue(intent_outcome_for_intent(full)['is_outcome_complete'])
        self.assertTrue(intent_outcome_for_intent(failed)['is_failed_execution'])
        self.assertFalse(intent_outcome_for_intent(failed)['has_execution_effect'])

    def test_intent_readiness_contract_distinguishes_execution_states(self):
        not_ready = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            readiness_state='not_ready',
            readiness_reason='missing preview',
        ).to_dict()
        ready = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            readiness_state='ready',
            readiness_reason='all prerequisites satisfied',
        ).to_dict()
        blocked = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            readiness_state='blocked',
            readiness_reason='account constraint',
        ).to_dict()

        self.assertFalse(intent_readiness_for_intent(not_ready)['is_executable_now'])
        self.assertFalse(intent_readiness_for_intent(not_ready)['is_blocked'])
        self.assertTrue(intent_readiness_for_intent(ready)['is_executable_now'])
        self.assertFalse(intent_readiness_for_intent(ready)['is_blocked'])
        self.assertFalse(intent_readiness_for_intent(blocked)['is_executable_now'])
        self.assertTrue(intent_readiness_for_intent(blocked)['is_blocked'])

    def test_intent_decision_contract_distinguishes_approval_states(self):
        proposed = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            decision_state='proposed',
            decision_actor='system',
        ).to_dict()
        approved = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            decision_state='approved',
            decision_actor='ross',
            decision_note='authorized for execution',
        ).to_dict()
        rejected = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            decision_state='rejected',
            decision_actor='ross',
            decision_note='not authorized',
        ).to_dict()
        revoked = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            decision_state='revoked',
            decision_actor='ross',
            decision_note='approval withdrawn',
        ).to_dict()

        self.assertFalse(intent_decision_for_intent(proposed)['is_authorized'])
        self.assertTrue(intent_decision_for_intent(approved)['is_authorized'])
        self.assertFalse(intent_decision_for_intent(rejected)['is_authorized'])
        self.assertFalse(intent_decision_for_intent(revoked)['is_authorized'])
        self.assertTrue(intent_decision_for_intent(rejected)['is_decision_terminal'])
        self.assertTrue(intent_decision_for_intent(revoked)['is_decision_terminal'])

    def test_intent_provenance_contract_distinguishes_origin_sources(self):
        system_intent = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            strategy_family='scalping_buy',
            strategy_source='tradier_leaders_board',
            strategy_run_id='run-123',
            origin='system_generated',
        ).to_dict()
        human_intent = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            strategy_family='manual_override',
            strategy_source='trading_desk_manual',
            strategy_run_id='desk-ticket-7',
            origin='human_directed',
        ).to_dict()

        system_provenance = intent_provenance_for_intent(system_intent)
        human_provenance = intent_provenance_for_intent(human_intent)

        self.assertEqual(system_provenance['strategy_family'], 'scalping_buy')
        self.assertEqual(system_provenance['strategy_source'], 'tradier_leaders_board')
        self.assertEqual(system_provenance['origin'], 'system_generated')
        self.assertEqual(human_provenance['strategy_family'], 'manual_override')
        self.assertEqual(human_provenance['strategy_source'], 'trading_desk_manual')
        self.assertEqual(human_provenance['origin'], 'human_directed')

    def test_position_linkage_contract_distinguishes_holdings_relationships(self):
        open_intent = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            position_relationship='open_new_position',
        ).to_dict()
        modify_intent = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            position_relationship='modify_existing_position',
            position_id='pos-1',
        ).to_dict()
        reduce_intent = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='sell',
            qty=1,
            allocation_bucket='cash_day_core',
            position_relationship='reduce_or_close_position',
            position_id='pos-1',
        ).to_dict()

        open_linkage = position_linkage_for_intent(open_intent)
        modify_linkage = position_linkage_for_intent(modify_intent)
        reduce_linkage = position_linkage_for_intent(reduce_intent)

        self.assertEqual(open_linkage['position_effect'], 'open')
        self.assertIsNone(open_linkage['position_id'])
        self.assertEqual(modify_linkage['position_effect'], 'modify')
        self.assertEqual(modify_linkage['position_id'], 'pos-1')
        self.assertEqual(reduce_linkage['position_effect'], 'reduce_or_close')
        self.assertEqual(reduce_linkage['position_id'], 'pos-1')

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

    def test_same_lifecycle_state_maps_differently_by_execution_context(self):
        margin_candidate = ExecutionIntent(
            mode='margin_swing',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='margin_swing_core',
            position_relationship='open_new_position',
        ).to_dict()
        margin_queued = transition_intent(margin_candidate, 'queued', actor='test')
        margin_previewed = transition_intent(margin_queued, 'previewed', actor='test')
        margin_approved = transition_intent(margin_previewed, 'approved', actor='test')

        cash_candidate = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            position_relationship='open_new_position',
        ).to_dict()
        cash_queued = transition_intent(cash_candidate, 'queued', actor='test')
        cash_previewed = transition_intent(cash_queued, 'previewed', actor='test')
        cash_approved = transition_intent(cash_previewed, 'approved', actor='test')

        cash_view = interpret_operator_execution_state(cash_approved)
        swing_view = interpret_operator_execution_state(margin_approved)

        self.assertEqual(cash_view['status'], 'approved')
        self.assertEqual(swing_view['status'], 'approved')
        self.assertEqual(cash_view['operator_state'], swing_view['operator_state'])
        self.assertEqual(cash_view['operator_stage'], swing_view['operator_stage'])
        self.assertEqual(cash_view['execution_context']['domain'], 'cash_day_trading')
        self.assertEqual(cash_view['execution_context']['holding_profile'], 'intraday')
        self.assertEqual(cash_view['execution_context']['allocation']['allocation_bucket'], 'cash_day_core')
        self.assertEqual(cash_view['execution_context']['allocation']['capital_source'], 'cash_day_trading_capital')
        self.assertEqual(swing_view['execution_context']['domain'], 'margin_swing_trading')
        self.assertEqual(swing_view['execution_context']['holding_profile'], 'multi_session')
        self.assertEqual(swing_view['execution_context']['allocation']['allocation_bucket'], 'margin_swing_core')
        self.assertEqual(swing_view['execution_context']['allocation']['capital_source'], 'margin_swing_trading_capital')
        self.assertNotEqual(cash_view['execution_context']['review_emphasis'], swing_view['execution_context']['review_emphasis'])
        self.assertNotEqual(cash_view['execution_context']['allocation']['capital_source'], swing_view['execution_context']['allocation']['capital_source'])

    def test_identical_execution_semantics_remain_distinguishable_by_reconciliation_state(self):
        aligned_candidate = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=2,
            allocation_bucket='cash_day_core',
            position_relationship='open_new_position',
            strategy_family='scalping_buy',
            strategy_source='tradier_leaders_board',
            strategy_run_id='run-123',
            origin='system_generated',
            decision_state='approved',
            decision_actor='ross',
            readiness_state='ready',
            readiness_reason='all checks complete',
            outcome_state='full_execution',
            outcome_reason='fully filled',
            effected_qty=2,
            escalation_state='no_escalation',
            timing_state='no_timing_pressure',
            external_reference_state='linked_external_reference',
            external_reference_id='ord-123',
            external_reference_system='tradier',
            attempt_state='attempt_completed',
            attempt_count=1,
            latest_attempt_id='att-1',
            reconciliation_state='reconciled',
            reconciliation_note='broker matches internal record',
        ).to_dict()
        aligned_queued = transition_intent(aligned_candidate, 'queued', actor='test')
        aligned_previewed = transition_intent(aligned_queued, 'previewed', actor='test')
        aligned_approved = transition_intent(aligned_previewed, 'approved', actor='test')

        divergent_candidate = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=2,
            allocation_bucket='cash_day_core',
            position_relationship='open_new_position',
            strategy_family='scalping_buy',
            strategy_source='tradier_leaders_board',
            strategy_run_id='run-123',
            origin='system_generated',
            decision_state='approved',
            decision_actor='ross',
            readiness_state='ready',
            readiness_reason='all checks complete',
            outcome_state='full_execution',
            outcome_reason='fully filled',
            effected_qty=2,
            escalation_state='no_escalation',
            timing_state='no_timing_pressure',
            external_reference_state='linked_external_reference',
            external_reference_id='ord-123',
            external_reference_system='tradier',
            attempt_state='attempt_completed',
            attempt_count=1,
            latest_attempt_id='att-1',
            reconciliation_state='divergent',
            reconciliation_note='broker qty mismatch',
        ).to_dict()
        divergent_queued = transition_intent(divergent_candidate, 'queued', actor='test')
        divergent_previewed = transition_intent(divergent_queued, 'previewed', actor='test')
        divergent_approved = transition_intent(divergent_previewed, 'approved', actor='test')

        aligned_view = interpret_operator_execution_state(aligned_approved)
        divergent_view = interpret_operator_execution_state(divergent_approved)

        self.assertEqual(aligned_view['status'], 'approved')
        self.assertEqual(divergent_view['status'], 'approved')
        self.assertEqual(aligned_view['decision']['decision_state'], divergent_view['decision']['decision_state'])
        self.assertEqual(aligned_view['readiness']['readiness_state'], divergent_view['readiness']['readiness_state'])
        self.assertEqual(aligned_view['outcome']['outcome_state'], divergent_view['outcome']['outcome_state'])
        self.assertEqual(aligned_view['external_reference']['external_reference_state'], divergent_view['external_reference']['external_reference_state'])
        self.assertEqual(aligned_view['execution_attempt']['attempt_state'], divergent_view['execution_attempt']['attempt_state'])
        self.assertEqual(aligned_view['execution_context']['allocation']['capital_source'], divergent_view['execution_context']['allocation']['capital_source'])
        self.assertTrue(aligned_view['reconciliation']['is_aligned'])
        self.assertEqual(aligned_view['reconciliation']['reconciliation_state'], 'reconciled')
        self.assertTrue(divergent_view['reconciliation']['has_mismatch'])
        self.assertEqual(divergent_view['reconciliation']['reconciliation_state'], 'divergent')

    def test_identical_execution_semantics_remain_distinguishable_by_attempt_state(self):
        in_progress_candidate = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=2,
            allocation_bucket='cash_day_core',
            position_relationship='open_new_position',
            strategy_family='scalping_buy',
            strategy_source='tradier_leaders_board',
            strategy_run_id='run-123',
            origin='system_generated',
            decision_state='approved',
            decision_actor='ross',
            readiness_state='ready',
            readiness_reason='all checks complete',
            outcome_state='no_outcome',
            escalation_state='no_escalation',
            timing_state='no_timing_pressure',
            external_reference_state='pending_external_reference',
            attempt_state='attempt_in_progress',
            attempt_count=1,
            latest_attempt_id='att-1',
            latest_attempt_note='submitting to broker',
        ).to_dict()
        in_progress_queued = transition_intent(in_progress_candidate, 'queued', actor='test')
        in_progress_previewed = transition_intent(in_progress_queued, 'previewed', actor='test')
        in_progress_approved = transition_intent(in_progress_previewed, 'approved', actor='test')

        retried_candidate = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=2,
            allocation_bucket='cash_day_core',
            position_relationship='open_new_position',
            strategy_family='scalping_buy',
            strategy_source='tradier_leaders_board',
            strategy_run_id='run-123',
            origin='system_generated',
            decision_state='approved',
            decision_actor='ross',
            readiness_state='ready',
            readiness_reason='all checks complete',
            outcome_state='no_outcome',
            escalation_state='no_escalation',
            timing_state='no_timing_pressure',
            external_reference_state='pending_external_reference',
            attempt_state='retried_attempts',
            attempt_count=2,
            latest_attempt_id='att-2',
            latest_attempt_note='second attempt after timeout',
        ).to_dict()
        retried_queued = transition_intent(retried_candidate, 'queued', actor='test')
        retried_previewed = transition_intent(retried_queued, 'previewed', actor='test')
        retried_approved = transition_intent(retried_previewed, 'approved', actor='test')

        in_progress_view = interpret_operator_execution_state(in_progress_approved)
        retried_view = interpret_operator_execution_state(retried_approved)

        self.assertEqual(in_progress_view['status'], 'approved')
        self.assertEqual(retried_view['status'], 'approved')
        self.assertEqual(in_progress_view['decision']['decision_state'], retried_view['decision']['decision_state'])
        self.assertEqual(in_progress_view['readiness']['readiness_state'], retried_view['readiness']['readiness_state'])
        self.assertEqual(in_progress_view['outcome']['outcome_state'], retried_view['outcome']['outcome_state'])
        self.assertEqual(in_progress_view['external_reference']['external_reference_state'], retried_view['external_reference']['external_reference_state'])
        self.assertEqual(in_progress_view['execution_context']['allocation']['capital_source'], retried_view['execution_context']['allocation']['capital_source'])
        self.assertEqual(in_progress_view['execution_attempt']['attempt_state'], 'attempt_in_progress')
        self.assertTrue(in_progress_view['execution_attempt']['is_in_progress'])
        self.assertEqual(retried_view['execution_attempt']['attempt_state'], 'retried_attempts')
        self.assertTrue(retried_view['execution_attempt']['has_multiple_attempts'])
        self.assertEqual(retried_view['execution_attempt']['attempt_count'], 2)

    def test_identical_execution_semantics_remain_distinguishable_by_external_reference_state(self):
        pending_candidate = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=2,
            allocation_bucket='cash_day_core',
            position_relationship='open_new_position',
            strategy_family='scalping_buy',
            strategy_source='tradier_leaders_board',
            strategy_run_id='run-123',
            origin='system_generated',
            decision_state='approved',
            decision_actor='ross',
            readiness_state='ready',
            readiness_reason='all checks complete',
            outcome_state='no_outcome',
            escalation_state='no_escalation',
            timing_state='no_timing_pressure',
            external_reference_state='pending_external_reference',
            external_reference_note='awaiting broker order id',
        ).to_dict()
        pending_queued = transition_intent(pending_candidate, 'queued', actor='test')
        pending_previewed = transition_intent(pending_queued, 'previewed', actor='test')
        pending_approved = transition_intent(pending_previewed, 'approved', actor='test')

        linked_candidate = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=2,
            allocation_bucket='cash_day_core',
            position_relationship='open_new_position',
            strategy_family='scalping_buy',
            strategy_source='tradier_leaders_board',
            strategy_run_id='run-123',
            origin='system_generated',
            decision_state='approved',
            decision_actor='ross',
            readiness_state='ready',
            readiness_reason='all checks complete',
            outcome_state='no_outcome',
            escalation_state='no_escalation',
            timing_state='no_timing_pressure',
            external_reference_state='linked_external_reference',
            external_reference_id='ord-123',
            external_reference_system='tradier',
        ).to_dict()
        linked_queued = transition_intent(linked_candidate, 'queued', actor='test')
        linked_previewed = transition_intent(linked_queued, 'previewed', actor='test')
        linked_approved = transition_intent(linked_previewed, 'approved', actor='test')

        pending_view = interpret_operator_execution_state(pending_approved)
        linked_view = interpret_operator_execution_state(linked_approved)

        self.assertEqual(pending_view['status'], 'approved')
        self.assertEqual(linked_view['status'], 'approved')
        self.assertEqual(pending_view['decision']['decision_state'], linked_view['decision']['decision_state'])
        self.assertEqual(pending_view['readiness']['readiness_state'], linked_view['readiness']['readiness_state'])
        self.assertEqual(pending_view['outcome']['outcome_state'], linked_view['outcome']['outcome_state'])
        self.assertEqual(pending_view['escalation']['escalation_state'], linked_view['escalation']['escalation_state'])
        self.assertEqual(pending_view['timing']['timing_state'], linked_view['timing']['timing_state'])
        self.assertEqual(pending_view['execution_context']['allocation']['capital_source'], linked_view['execution_context']['allocation']['capital_source'])
        self.assertTrue(pending_view['external_reference']['reference_pending'])
        self.assertFalse(pending_view['external_reference']['has_external_reference'])
        self.assertEqual(linked_view['external_reference']['external_reference_state'], 'linked_external_reference')
        self.assertTrue(linked_view['external_reference']['has_external_reference'])
        self.assertTrue(linked_view['external_reference']['reference_valid'])

    def test_composed_execution_snapshot_preserves_underlying_distinctions(self):
        warning_candidate = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=2,
            allocation_bucket='cash_day_core',
            position_relationship='open_new_position',
            strategy_family='scalping_buy',
            strategy_source='tradier_leaders_board',
            strategy_run_id='run-123',
            origin='system_generated',
            decision_state='approved',
            decision_actor='ross',
            readiness_state='ready',
            readiness_reason='all checks complete',
            outcome_state='no_outcome',
            escalation_state='warning',
            escalation_reason='spread widened but tradable',
            timing_state='time_sensitive',
            timing_reason='window closing fast',
        ).to_dict()
        warning_queued = transition_intent(warning_candidate, 'queued', actor='test')
        warning_previewed = transition_intent(warning_queued, 'previewed', actor='test')
        warning_approved = transition_intent(warning_previewed, 'approved', actor='test')

        blocked_candidate = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=2,
            allocation_bucket='cash_day_core',
            position_relationship='open_new_position',
            strategy_family='scalping_buy',
            strategy_source='tradier_leaders_board',
            strategy_run_id='run-123',
            origin='system_generated',
            decision_state='approved',
            decision_actor='ross',
            readiness_state='not_ready',
            readiness_reason='stale and not executable',
            outcome_state='no_outcome',
            escalation_state='blocked',
            escalation_reason='manual intervention required',
            timing_state='expired',
            timing_reason='signal no longer actionable',
        ).to_dict()
        blocked_queued = transition_intent(blocked_candidate, 'queued', actor='test')
        blocked_previewed = transition_intent(blocked_queued, 'previewed', actor='test')
        blocked_approved = transition_intent(blocked_previewed, 'approved', actor='test')

        warning_snapshot = build_execution_intent_snapshot(warning_approved)
        blocked_snapshot = build_execution_intent_snapshot(blocked_approved)

        self.assertEqual(warning_snapshot['lifecycle']['status'], blocked_snapshot['lifecycle']['status'])
        self.assertEqual(warning_snapshot['decision']['decision_state'], blocked_snapshot['decision']['decision_state'])
        self.assertEqual(warning_snapshot['outcome']['outcome_state'], blocked_snapshot['outcome']['outcome_state'])
        self.assertEqual(warning_snapshot['execution_context']['allocation']['capital_source'], blocked_snapshot['execution_context']['allocation']['capital_source'])
        self.assertEqual(warning_snapshot['position_linkage']['position_effect'], blocked_snapshot['position_linkage']['position_effect'])
        self.assertEqual(warning_snapshot['provenance']['strategy_source'], blocked_snapshot['provenance']['strategy_source'])
        self.assertEqual(warning_snapshot['escalation']['escalation_state'], 'warning')
        self.assertEqual(blocked_snapshot['escalation']['escalation_state'], 'blocked')
        self.assertEqual(warning_snapshot['timing']['timing_state'], 'time_sensitive')
        self.assertEqual(blocked_snapshot['timing']['timing_state'], 'expired')

    def test_identical_execution_semantics_remain_distinguishable_by_timing_state(self):
        urgent_candidate = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=2,
            allocation_bucket='cash_day_core',
            position_relationship='open_new_position',
            strategy_family='scalping_buy',
            strategy_source='tradier_leaders_board',
            strategy_run_id='run-123',
            origin='system_generated',
            decision_state='approved',
            decision_actor='ross',
            readiness_state='ready',
            readiness_reason='all checks complete',
            outcome_state='no_outcome',
            escalation_state='no_escalation',
            timing_state='time_sensitive',
            timing_reason='window closing fast',
        ).to_dict()
        urgent_queued = transition_intent(urgent_candidate, 'queued', actor='test')
        urgent_previewed = transition_intent(urgent_queued, 'previewed', actor='test')
        urgent_approved = transition_intent(urgent_previewed, 'approved', actor='test')

        expired_candidate = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=2,
            allocation_bucket='cash_day_core',
            position_relationship='open_new_position',
            strategy_family='scalping_buy',
            strategy_source='tradier_leaders_board',
            strategy_run_id='run-123',
            origin='system_generated',
            decision_state='approved',
            decision_actor='ross',
            readiness_state='not_ready',
            readiness_reason='expired and no longer executable',
            outcome_state='no_outcome',
            escalation_state='no_escalation',
            timing_state='expired',
            timing_reason='signal no longer actionable',
        ).to_dict()
        expired_queued = transition_intent(expired_candidate, 'queued', actor='test')
        expired_previewed = transition_intent(expired_queued, 'previewed', actor='test')
        expired_approved = transition_intent(expired_previewed, 'approved', actor='test')

        urgent_view = interpret_operator_execution_state(urgent_approved)
        expired_view = interpret_operator_execution_state(expired_approved)

        self.assertEqual(urgent_view['status'], 'approved')
        self.assertEqual(expired_view['status'], 'approved')
        self.assertEqual(urgent_view['decision']['decision_state'], expired_view['decision']['decision_state'])
        self.assertEqual(urgent_view['escalation']['escalation_state'], expired_view['escalation']['escalation_state'])
        self.assertEqual(urgent_view['outcome']['outcome_state'], expired_view['outcome']['outcome_state'])
        self.assertEqual(urgent_view['execution_context']['allocation']['capital_source'], expired_view['execution_context']['allocation']['capital_source'])
        self.assertEqual(urgent_view['timing']['timing_state'], 'time_sensitive')
        self.assertTrue(urgent_view['timing']['is_urgent'])
        self.assertTrue(urgent_view['timing']['is_actionable'])
        self.assertEqual(expired_view['timing']['timing_state'], 'expired')
        self.assertTrue(expired_view['timing']['is_expired'])
        self.assertFalse(expired_view['timing']['is_actionable'])

    def test_identical_execution_semantics_remain_distinguishable_by_escalation_state(self):
        warning_candidate = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=2,
            allocation_bucket='cash_day_core',
            position_relationship='open_new_position',
            strategy_family='scalping_buy',
            strategy_source='tradier_leaders_board',
            strategy_run_id='run-123',
            origin='system_generated',
            decision_state='approved',
            decision_actor='ross',
            readiness_state='ready',
            readiness_reason='all checks complete',
            outcome_state='no_outcome',
            escalation_state='warning',
            escalation_reason='spread widened but tradable',
        ).to_dict()
        warning_queued = transition_intent(warning_candidate, 'queued', actor='test')
        warning_previewed = transition_intent(warning_queued, 'previewed', actor='test')
        warning_approved = transition_intent(warning_previewed, 'approved', actor='test')

        blocked_candidate = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=2,
            allocation_bucket='cash_day_core',
            position_relationship='open_new_position',
            strategy_family='scalping_buy',
            strategy_source='tradier_leaders_board',
            strategy_run_id='run-123',
            origin='system_generated',
            decision_state='approved',
            decision_actor='ross',
            readiness_state='ready',
            readiness_reason='all checks complete',
            outcome_state='no_outcome',
            escalation_state='blocked',
            escalation_reason='manual intervention required',
        ).to_dict()
        blocked_queued = transition_intent(blocked_candidate, 'queued', actor='test')
        blocked_previewed = transition_intent(blocked_queued, 'previewed', actor='test')
        blocked_approved = transition_intent(blocked_previewed, 'approved', actor='test')

        warning_view = interpret_operator_execution_state(warning_approved)
        blocked_view = interpret_operator_execution_state(blocked_approved)

        self.assertEqual(warning_view['status'], 'approved')
        self.assertEqual(blocked_view['status'], 'approved')
        self.assertEqual(warning_view['decision']['decision_state'], blocked_view['decision']['decision_state'])
        self.assertEqual(warning_view['readiness']['readiness_state'], blocked_view['readiness']['readiness_state'])
        self.assertEqual(warning_view['outcome']['outcome_state'], blocked_view['outcome']['outcome_state'])
        self.assertEqual(warning_view['execution_context']['allocation']['capital_source'], blocked_view['execution_context']['allocation']['capital_source'])
        self.assertEqual(warning_view['escalation']['escalation_state'], 'warning')
        self.assertFalse(warning_view['escalation']['blocks_autonomous_progress'])
        self.assertEqual(blocked_view['escalation']['escalation_state'], 'blocked')
        self.assertTrue(blocked_view['escalation']['blocks_autonomous_progress'])

    def test_identical_ready_intents_remain_distinguishable_by_execution_outcome(self):
        partial_candidate = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=2,
            allocation_bucket='cash_day_core',
            position_relationship='open_new_position',
            strategy_family='scalping_buy',
            strategy_source='tradier_leaders_board',
            strategy_run_id='run-123',
            origin='system_generated',
            decision_state='approved',
            decision_actor='ross',
            readiness_state='ready',
            readiness_reason='all checks complete',
            outcome_state='partial_execution',
            outcome_reason='1 of 2 filled',
            effected_qty=1,
            external_reference_state='linked_external_reference',
            external_reference_id='ord-123',
            external_reference_system='tradier',
            attempt_state='attempt_completed',
            attempt_count=1,
            latest_attempt_id='att-1',
        ).to_dict()
        partial_queued = transition_intent(partial_candidate, 'queued', actor='test')
        partial_previewed = transition_intent(partial_queued, 'previewed', actor='test')
        partial_approved = transition_intent(partial_previewed, 'approved', actor='test')

        failed_candidate = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=2,
            allocation_bucket='cash_day_core',
            position_relationship='open_new_position',
            strategy_family='scalping_buy',
            strategy_source='tradier_leaders_board',
            strategy_run_id='run-123',
            origin='system_generated',
            decision_state='approved',
            decision_actor='ross',
            readiness_state='ready',
            readiness_reason='all checks complete',
            outcome_state='failed_execution',
            outcome_reason='broker rejected order',
            effected_qty=0,
        ).to_dict()
        failed_queued = transition_intent(failed_candidate, 'queued', actor='test')
        failed_previewed = transition_intent(failed_queued, 'previewed', actor='test')
        failed_approved = transition_intent(failed_previewed, 'approved', actor='test')

        partial_view = interpret_operator_execution_state(partial_approved)
        failed_view = interpret_operator_execution_state(failed_approved)

        self.assertEqual(partial_view['status'], 'approved')
        self.assertEqual(failed_view['status'], 'approved')
        self.assertEqual(partial_view['decision']['decision_state'], failed_view['decision']['decision_state'])
        self.assertEqual(partial_view['readiness']['readiness_state'], failed_view['readiness']['readiness_state'])
        self.assertEqual(partial_view['execution_context']['allocation']['capital_source'], failed_view['execution_context']['allocation']['capital_source'])
        self.assertTrue(partial_view['outcome']['has_execution_effect'])
        self.assertFalse(partial_view['outcome']['is_outcome_complete'])
        self.assertEqual(partial_view['outcome']['effected_qty'], 1)
        self.assertTrue(failed_view['outcome']['is_failed_execution'])
        self.assertFalse(failed_view['outcome']['has_execution_effect'])
        self.assertEqual(failed_view['outcome']['effected_qty'], 0)

    def test_identical_execution_semantics_remain_distinguishable_by_readiness_state(self):
        waiting_candidate = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            position_relationship='open_new_position',
            strategy_family='scalping_buy',
            strategy_source='tradier_leaders_board',
            strategy_run_id='run-123',
            origin='system_generated',
            decision_state='approved',
            decision_actor='ross',
            readiness_state='not_ready',
            readiness_reason='awaiting preview',
        ).to_dict()
        waiting_queued = transition_intent(waiting_candidate, 'queued', actor='test')
        waiting_previewed = transition_intent(waiting_queued, 'previewed', actor='test')
        waiting_approved = transition_intent(waiting_previewed, 'approved', actor='test')

        ready_candidate = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            position_relationship='open_new_position',
            strategy_family='scalping_buy',
            strategy_source='tradier_leaders_board',
            strategy_run_id='run-123',
            origin='system_generated',
            decision_state='approved',
            decision_actor='ross',
            readiness_state='ready',
            readiness_reason='all checks complete',
        ).to_dict()
        ready_queued = transition_intent(ready_candidate, 'queued', actor='test')
        ready_previewed = transition_intent(ready_queued, 'previewed', actor='test')
        ready_approved = transition_intent(ready_previewed, 'approved', actor='test')

        waiting_view = interpret_operator_execution_state(waiting_approved)
        ready_view = interpret_operator_execution_state(ready_approved)

        self.assertEqual(waiting_view['status'], 'approved')
        self.assertEqual(ready_view['status'], 'approved')
        self.assertEqual(waiting_view['decision']['decision_state'], ready_view['decision']['decision_state'])
        self.assertEqual(waiting_view['execution_context']['allocation']['capital_source'], ready_view['execution_context']['allocation']['capital_source'])
        self.assertEqual(waiting_view['provenance']['strategy_source'], ready_view['provenance']['strategy_source'])
        self.assertFalse(waiting_view['readiness']['is_executable_now'])
        self.assertTrue(ready_view['readiness']['is_executable_now'])
        self.assertEqual(waiting_view['readiness']['readiness_state'], 'not_ready')
        self.assertEqual(ready_view['readiness']['readiness_state'], 'ready')

    def test_identical_execution_semantics_remain_distinguishable_by_decision_state(self):
        proposed_candidate = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            position_relationship='open_new_position',
            strategy_family='scalping_buy',
            strategy_source='tradier_leaders_board',
            strategy_run_id='run-123',
            origin='system_generated',
            decision_state='proposed',
            decision_actor='system',
        ).to_dict()
        proposed_queued = transition_intent(proposed_candidate, 'queued', actor='test')
        proposed_previewed = transition_intent(proposed_queued, 'previewed', actor='test')
        proposed_approved = transition_intent(proposed_previewed, 'approved', actor='test')

        authorized_candidate = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            position_relationship='open_new_position',
            strategy_family='scalping_buy',
            strategy_source='tradier_leaders_board',
            strategy_run_id='run-123',
            origin='system_generated',
            decision_state='approved',
            decision_actor='ross',
            decision_note='authorized',
        ).to_dict()
        authorized_queued = transition_intent(authorized_candidate, 'queued', actor='test')
        authorized_previewed = transition_intent(authorized_queued, 'previewed', actor='test')
        authorized_approved = transition_intent(authorized_previewed, 'approved', actor='test')

        proposed_view = interpret_operator_execution_state(proposed_approved)
        authorized_view = interpret_operator_execution_state(authorized_approved)

        self.assertEqual(proposed_view['status'], 'approved')
        self.assertEqual(authorized_view['status'], 'approved')
        self.assertEqual(proposed_view['operator_state'], authorized_view['operator_state'])
        self.assertEqual(proposed_view['execution_context']['allocation']['capital_source'], authorized_view['execution_context']['allocation']['capital_source'])
        self.assertEqual(proposed_view['provenance']['strategy_source'], authorized_view['provenance']['strategy_source'])
        self.assertFalse(proposed_view['decision']['is_authorized'])
        self.assertTrue(authorized_view['decision']['is_authorized'])
        self.assertEqual(proposed_view['decision']['decision_state'], 'proposed')
        self.assertEqual(authorized_view['decision']['decision_state'], 'approved')
        self.assertNotEqual(proposed_view['decision']['decision_actor'], authorized_view['decision']['decision_actor'])

    def test_identical_execution_semantics_remain_distinguishable_by_provenance(self):
        system_candidate = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            position_relationship='open_new_position',
            strategy_family='scalping_buy',
            strategy_source='tradier_leaders_board',
            strategy_run_id='run-123',
            origin='system_generated',
        ).to_dict()
        system_queued = transition_intent(system_candidate, 'queued', actor='test')
        system_previewed = transition_intent(system_queued, 'previewed', actor='test')
        system_approved = transition_intent(system_previewed, 'approved', actor='test')

        human_candidate = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            position_relationship='open_new_position',
            strategy_family='manual_override',
            strategy_source='trading_desk_manual',
            strategy_run_id='desk-ticket-7',
            origin='human_directed',
        ).to_dict()
        human_queued = transition_intent(human_candidate, 'queued', actor='test')
        human_previewed = transition_intent(human_queued, 'previewed', actor='test')
        human_approved = transition_intent(human_previewed, 'approved', actor='test')

        system_view = interpret_operator_execution_state(system_approved)
        human_view = interpret_operator_execution_state(human_approved)

        self.assertEqual(system_view['status'], 'approved')
        self.assertEqual(human_view['status'], 'approved')
        self.assertEqual(system_view['operator_state'], human_view['operator_state'])
        self.assertEqual(system_view['execution_context']['allocation']['capital_source'], human_view['execution_context']['allocation']['capital_source'])
        self.assertEqual(system_view['position_linkage']['position_effect'], human_view['position_linkage']['position_effect'])
        self.assertEqual(system_view['provenance']['strategy_source'], 'tradier_leaders_board')
        self.assertEqual(system_view['provenance']['origin'], 'system_generated')
        self.assertEqual(human_view['provenance']['strategy_source'], 'trading_desk_manual')
        self.assertEqual(human_view['provenance']['origin'], 'human_directed')
        self.assertNotEqual(system_view['provenance']['strategy_run_id'], human_view['provenance']['strategy_run_id'])

    def test_same_lifecycle_and_allocation_do_not_collapse_position_linkage_meaning(self):
        open_candidate = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            position_relationship='open_new_position',
        ).to_dict()
        open_queued = transition_intent(open_candidate, 'queued', actor='test')
        open_previewed = transition_intent(open_queued, 'previewed', actor='test')
        open_approved = transition_intent(open_previewed, 'approved', actor='test')

        modify_candidate = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            allocation_bucket='cash_day_core',
            position_relationship='modify_existing_position',
            position_id='pos-1',
        ).to_dict()
        modify_queued = transition_intent(modify_candidate, 'queued', actor='test')
        modify_previewed = transition_intent(modify_queued, 'previewed', actor='test')
        modify_approved = transition_intent(modify_previewed, 'approved', actor='test')

        reduce_candidate = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='sell',
            qty=1,
            allocation_bucket='cash_day_core',
            position_relationship='reduce_or_close_position',
            position_id='pos-1',
        ).to_dict()
        reduce_queued = transition_intent(reduce_candidate, 'queued', actor='test')
        reduce_previewed = transition_intent(reduce_queued, 'previewed', actor='test')
        reduce_approved = transition_intent(reduce_previewed, 'approved', actor='test')

        open_view = interpret_operator_execution_state(open_approved)
        modify_view = interpret_operator_execution_state(modify_approved)
        reduce_view = interpret_operator_execution_state(reduce_approved)

        self.assertEqual(open_view['status'], 'approved')
        self.assertEqual(modify_view['status'], 'approved')
        self.assertEqual(reduce_view['status'], 'approved')
        self.assertEqual(open_view['execution_context']['allocation']['capital_source'], 'cash_day_trading_capital')
        self.assertEqual(modify_view['execution_context']['allocation']['capital_source'], 'cash_day_trading_capital')
        self.assertEqual(reduce_view['execution_context']['allocation']['capital_source'], 'cash_day_trading_capital')
        self.assertEqual(open_view['position_linkage']['position_effect'], 'open')
        self.assertEqual(modify_view['position_linkage']['position_effect'], 'modify')
        self.assertEqual(reduce_view['position_linkage']['position_effect'], 'reduce_or_close')
        self.assertIsNone(open_view['position_linkage']['position_id'])
        self.assertEqual(modify_view['position_linkage']['position_id'], 'pos-1')
        self.assertEqual(reduce_view['position_linkage']['position_id'], 'pos-1')

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

    def test_save_state_accepts_valid_cross_contract_state(self):
        self.with_temp_state_paths()
        candidate = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=1,
            decision_state='approved',
            decision_actor='ross',
            readiness_state='ready',
            outcome_state='no_outcome',
            external_reference_state='pending_external_reference',
            attempt_state='attempt_in_progress',
            attempt_count=1,
            latest_attempt_id='att-1',
            reconciliation_state='pending_confirmation',
        ).to_dict()
        queued = transition_intent(candidate, 'queued', actor='test')
        previewed = transition_intent(queued, 'previewed', actor='test')
        approved = transition_intent(previewed, 'approved', actor='test')
        valid_state = {
            'intents': [approved],
            'previews': [],
            'orders': [],
            'positions': [],
            'riskDecisions': [],
        }

        persisted = save_state(valid_state)
        self.assertEqual(persisted['intents'][0]['status'], 'approved')

    def test_save_state_rejects_cross_contract_contradictions(self):
        self.with_temp_state_paths()
        contradictory = ExecutionIntent(
            mode='cash_day',
            strategy_type='long_call',
            symbol='IWM',
            contract='IWM 250 CALL 2026-03-20',
            side='buy',
            qty=2,
            decision_state='proposed',
            decision_actor='system',
            readiness_state='ready',
            outcome_state='full_execution',
            outcome_reason='filled',
            effected_qty=2,
            external_reference_state='no_external_reference',
            attempt_state='attempt_completed',
            attempt_count=1,
            latest_attempt_id='att-1',
            reconciliation_state='reconciled',
        ).to_dict()
        queued = transition_intent(contradictory, 'queued', actor='test')
        previewed = transition_intent(queued, 'previewed', actor='test')
        approved = transition_intent(previewed, 'approved', actor='test')
        contradictory_state = {
            'intents': [approved],
            'previews': [],
            'orders': [],
            'positions': [],
            'riskDecisions': [],
        }

        with self.assertRaises((InvalidExecutionContractCombinationError, RuntimeInvalidExecutionContractCombinationError)):
            save_state(contradictory_state)

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
