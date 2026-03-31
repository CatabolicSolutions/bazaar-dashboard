#!/usr/bin/env python3
"""
Dashboard-to-Tradier Execution Bridge
Converts dashboard leader selection to ExecutionIntent and executes through Tradier
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

# Add scripts directory to path
ROOT = Path('/home/catabolic_solutions/.openclaw/workspace')
sys.path.insert(0, str(ROOT / 'scripts'))

from tradier_execution_service import TradierExecutionService
from tradier_broker_interface import TradierBrokerInterface


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def execute_leader(leader: dict, qty: int = 1, mode: str = 'cash_day') -> dict:
    """
    Execute a trade from dashboard leader data
    
    Flow:
    1. Create ExecutionIntent from leader
    2. Evaluate risk
    3. Preview order
    4. Place order (if approved)
    5. Record position
    """
    service = TradierExecutionService()
    
    # Determine strategy type from option_type
    option_type = leader.get('option_type', '').lower()
    if 'call' in option_type:
        strategy_type = 'long_call'
    elif 'put' in option_type:
        strategy_type = 'long_put'
    else:
        return {'ok': False, 'error': f'Unknown option_type: {option_type}'}
    
    # Map dashboard fields to execution service expected fields
    mapped_leader = dict(leader)
    if 'exp' in mapped_leader and 'expiration' not in mapped_leader:
        mapped_leader['expiration'] = mapped_leader['exp']
    
    try:
        # Step 1: Create intent from leader
        intent_dict = service.create_intent_from_leader(
            mapped_leader,
            mode=mode,
            qty=qty,
            limit_price=leader.get('ask'),  # Use ask price as limit
            notes=f"Dashboard execution: {leader.get('headline', '')}"
        )
        
        # Step 2: Evaluate risk
        risk_decision = service.evaluate_risk(intent_dict)
        if not risk_decision.get('allowed'):
            return {
                'ok': False,
                'error': 'Risk check failed',
                'risk_decision': risk_decision,
                'intent_id': intent_dict.get('intent_id')
            }
        
        # Step 3: Preview order
        expiry = mapped_leader.get('expiration', mapped_leader.get('exp', ''))
        option_type_clean = 'call' if 'call' in option_type else 'put'
        try:
            strike = float(leader.get('strike', 0))
        except (ValueError, TypeError):
            return {'ok': False, 'error': f'Invalid strike price: {leader.get("strike")}'}
        
        preview_result = service.preview_intent(
            intent_dict,
            expiry=expiry,
            option_type=option_type_clean,
            strike=strike
        )
        
        # Return preview for user approval
        return {
            'ok': True,
            'stage': 'preview',
            'intent_id': intent_dict.get('intent_id'),
            'preview': preview_result.get('preview', {}),
            'broker_response': preview_result.get('broker_response', {}),
            'risk_decision': risk_decision,
            'message': 'Order preview ready for approval'
        }
        
    except Exception as e:
        return {'ok': False, 'error': str(e), 'stage': 'preview_failed'}


def approve_and_execute(intent_id: str) -> dict:
    """
    Approve a previewed intent and place the order
    """
    service = TradierExecutionService()
    
    try:
        # Load state to find the intent
        from tradier_state_store import load_state
        state = load_state()
        
        intent_dict = None
        for intent in state.get('intents', []):
            if intent.get('intent_id') == intent_id:
                intent_dict = intent
                break
        
        if not intent_dict:
            return {'ok': False, 'error': f'Intent not found: {intent_id}'}
        
        # Approve intent
        approved = service.approve_intent(intent_dict, actor='dashboard', note='Approved via dashboard')
        
        # Mark ready
        ready = service.mark_intent_ready(approved, reason='Dashboard approval received')
        
        # Begin execution attempt
        import uuid
        attempt_id = f"attempt_{uuid.uuid4().hex[:12]}"
        in_progress = service.begin_execution_attempt(ready, attempt_id=attempt_id, note='Dashboard execution started')
        
        # Place order
        expiry = approved.get('contract', '').split()[2] if len(approved.get('contract', '').split()) > 2 else ''
        option_type = 'call' if approved.get('strategy_type') == 'long_call' else 'put'
        try:
            strike_str = approved.get('contract', '').split()[1] if len(approved.get('contract', '').split()) > 1 else '0'
            strike = float(strike_str)
        except (ValueError, IndexError):
            return {'ok': False, 'error': 'Could not parse strike from contract'}
        
        # Build and place order
        broker = TradierBrokerInterface()
        payload = broker.build_option_payload(
            service._materialize_intent(in_progress),
            symbol=approved.get('symbol', ''),
            expiry=expiry,
            option_type=option_type,
            strike=strike,
            broker_side='buy_to_open'
        )
        
        order_response = broker.place_order(payload)
        
        # Record commit
        commit_result = service.record_commit(in_progress, order_response)
        
        # Reconcile
        reconciled = service.reconcile_intent(commit_result.get('intent', {}), note='Order placed via dashboard')
        
        return {
            'ok': True,
            'stage': 'executed',
            'intent_id': intent_id,
            'order': commit_result.get('order', {}),
            'position': commit_result.get('position', {}),
            'broker_response': order_response,
            'message': 'Order placed successfully'
        }
        
    except Exception as e:
        return {'ok': False, 'error': str(e), 'stage': 'execution_failed', 'intent_id': intent_id}


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Dashboard execution bridge')
    parser.add_argument('--preview', action='store_true', help='Preview order only')
    parser.add_argument('--execute', metavar='INTENT_ID', help='Execute approved intent')
    parser.add_argument('--leader', help='JSON string of leader data')
    parser.add_argument('--qty', type=int, default=1, help='Quantity')
    parser.add_argument('--mode', default='cash_day', choices=['cash_day', 'margin_swing'])
    
    args = parser.parse_args()
    
    if args.execute:
        result = approve_and_execute(args.execute)
        print(json.dumps(result, indent=2))
    elif args.leader:
        leader = json.loads(args.leader)
        result = execute_leader(leader, qty=args.qty, mode=args.mode)
        print(json.dumps(result, indent=2))
    else:
        parser.print_help()
        sys.exit(1)
