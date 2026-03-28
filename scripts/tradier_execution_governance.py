from __future__ import annotations

from typing import Any


class InvalidExecutionContractCombinationError(ValueError):
    pass


def validate_execution_contract_combinations(contracts: dict[str, Any]) -> None:
    lifecycle = contracts['lifecycle']
    decision = contracts['decision']
    readiness = contracts['readiness']
    outcome = contracts['outcome']
    escalation = contracts['escalation']
    timing = contracts['timing']
    external_reference = contracts['external_reference']
    execution_attempt = contracts['execution_attempt']
    reconciliation = contracts['reconciliation']

    if readiness['is_executable_now'] and not decision['is_authorized']:
        raise InvalidExecutionContractCombinationError(
            'Ready intent must be authorized before it can be executable now'
        )

    if timing['is_expired'] and readiness['is_executable_now']:
        raise InvalidExecutionContractCombinationError(
            'Expired intent cannot be executable now'
        )

    if outcome['has_execution_effect'] and execution_attempt['attempt_count'] == 0:
        raise InvalidExecutionContractCombinationError(
            'Execution effect requires at least one execution attempt'
        )

    if outcome['has_execution_effect'] and not external_reference['has_external_reference']:
        raise InvalidExecutionContractCombinationError(
            'Execution effect requires an external reference'
        )

    if reconciliation['is_aligned'] and not external_reference['has_external_reference']:
        raise InvalidExecutionContractCombinationError(
            'Reconciled state requires an external reference to reconcile against'
        )

    if reconciliation['has_mismatch'] and external_reference['reference_pending']:
        raise InvalidExecutionContractCombinationError(
            'Divergent reconciliation cannot still be pending external reference'
        )

    if lifecycle['status'] in {'rejected', 'cancelled'} and outcome['has_execution_effect']:
        raise InvalidExecutionContractCombinationError(
            'Rejected/cancelled intents cannot report execution effect'
        )

    if escalation['is_terminal_attention_state'] and readiness['is_executable_now']:
        raise InvalidExecutionContractCombinationError(
            'Terminal failure cannot remain executable now'
        )
