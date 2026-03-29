from __future__ import annotations

import argparse
import json
from typing import Any

from tradier_cli_interaction_model import build_cli_action_invocation, build_tradier_cli_interaction_model
from tradier_execution_service import TradierExecutionService
from tradier_state_store import load_state


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Tradier operator CLI shell')
    parser.add_argument('--latest-limit', type=int, default=20)
    parser.add_argument('--intent-id', type=str, default=None)
    parser.add_argument('--action', type=str, default=None)
    parser.add_argument('--params-json', type=str, default=None)
    return parser


def _load_intent_by_id(intent_id: str) -> dict[str, Any] | None:
    state = load_state()
    for intent in state.get('intents', []):
        if intent.get('intent_id') == intent_id:
            return intent
    return None


def _execute_allowed_action(intent: dict[str, Any], action_name: str, params: dict[str, Any]) -> dict[str, Any]:
    service = TradierExecutionService()
    action_map = {
        'mark_intent_ready': lambda: service.mark_intent_ready(intent, reason=params.get('reason', 'Ready via CLI')),
        'block_intent': lambda: service.block_intent(intent, reason=params.get('reason', 'Blocked via CLI'), escalation_state=params.get('escalation_state', 'blocked')),
        'retry_execution_attempt': lambda: service.retry_execution_attempt(intent, attempt_id=params['attempt_id'], reason=params.get('reason', 'Retry via CLI')),
        'reconcile_intent': lambda: service.reconcile_intent(intent, note=params.get('note', 'Reconciled via CLI')),
        'invalidate_external_reference': lambda: service.invalidate_external_reference(intent, note=params.get('note', 'Invalidated via CLI')),
    }
    if action_name not in action_map:
        raise ValueError(f'Unsupported CLI action execution: {action_name}')
    return action_map[action_name]()


def run_cli_shell(argv: list[str] | None = None) -> dict[str, Any]:
    parser = build_parser()
    args = parser.parse_args(argv)

    interaction = build_tradier_cli_interaction_model(
        latest_limit=args.latest_limit,
        selected_intent_id=args.intent_id,
    )

    action_contract = None
    action_result = None
    action_error = None
    if args.action and interaction['selected_detail'] is not None:
        params = json.loads(args.params_json) if args.params_json else {}
        action_contract = build_cli_action_invocation(
            interaction['selected_detail']['intent_id'],
            args.action,
            params,
        )
        selected_actions = interaction['selected_detail']['actions']
        if not selected_actions.get(args.action, {}).get('available', False):
            action_error = f'Action not allowed for selected intent: {args.action}'
        else:
            persisted_intent = _load_intent_by_id(interaction['selected_detail']['intent_id'])
            action_result = _execute_allowed_action(persisted_intent, args.action, params)
            interaction = build_tradier_cli_interaction_model(
                latest_limit=args.latest_limit,
                selected_intent_id=interaction['selected_detail']['intent_id'],
            )

    return {
        'shell': interaction,
        'action_contract': action_contract,
        'action_result': action_result,
        'action_error': action_error,
    }


def render_cli_text(result: dict[str, Any]) -> str:
    shell = result['shell']
    selected = shell['selected_detail']
    lines = []
    lines.append('TRADIER CLI SHELL')
    lines.append('WORKLIST')
    for item in shell['worklist']:
        lines.append(f"- {item['priority_rank']} {item['priority_category']} {item['intent_id']}")
    if selected is not None:
        lines.append('SELECTED DETAIL')
        lines.append(f"intent_id: {selected['intent_id']}")
        lines.append(f"status: {selected['core']['lifecycle']['status']}")
        lines.append(f"operator_state: {selected['operator']['operator_state']}")
        lines.append('ACTIONS')
        for action_name, config in selected['actions'].items():
            lines.append(f"- {action_name}: {'available' if config['available'] else 'unavailable'}")
    if result['action_contract'] is not None:
        lines.append('ACTION CONTRACT')
        lines.append(json.dumps(result['action_contract'], sort_keys=True))
    if result.get('action_result') is not None:
        lines.append('ACTION RESULT')
        lines.append(json.dumps(result['action_result'], sort_keys=True))
    if result.get('action_error') is not None:
        lines.append('ACTION ERROR')
        lines.append(result['action_error'])
    return '\n'.join(lines)


if __name__ == '__main__':
    print(render_cli_text(run_cli_shell()))
