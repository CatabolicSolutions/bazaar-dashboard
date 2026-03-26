import sys
import unittest
from pathlib import Path
from unittest.mock import patch

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = WORKSPACE_ROOT / 'scripts'
for p in [str(WORKSPACE_ROOT), str(SCRIPTS_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from scripts.tradier_execution import occ_option_symbol
from scripts.tradier_position_flow import parse_command
from scripts.tradier_approval_flow import contract_key, build_execution_card
from scripts.tradier_board_utils import candidate_id, parse_raw_tickets, top_leaders_by_strategy
from scripts.tradier_execution_models import ExecutionIntent
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
