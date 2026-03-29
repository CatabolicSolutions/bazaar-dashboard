from __future__ import annotations

import argparse
import json
from typing import Any

from tradier_cli_interaction_model import build_cli_action_invocation, build_tradier_cli_interaction_model


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Tradier operator CLI shell')
    parser.add_argument('--latest-limit', type=int, default=20)
    parser.add_argument('--intent-id', type=str, default=None)
    parser.add_argument('--action', type=str, default=None)
    parser.add_argument('--params-json', type=str, default=None)
    return parser


def run_cli_shell(argv: list[str] | None = None) -> dict[str, Any]:
    parser = build_parser()
    args = parser.parse_args(argv)

    interaction = build_tradier_cli_interaction_model(
        latest_limit=args.latest_limit,
        selected_intent_id=args.intent_id,
    )

    action_contract = None
    if args.action and interaction['selected_detail'] is not None:
        params = json.loads(args.params_json) if args.params_json else {}
        action_contract = build_cli_action_invocation(
            interaction['selected_detail']['intent_id'],
            args.action,
            params,
        )

    return {
        'shell': interaction,
        'action_contract': action_contract,
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
    return '\n'.join(lines)


if __name__ == '__main__':
    print(render_cli_text(run_cli_shell()))
