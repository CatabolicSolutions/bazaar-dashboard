from __future__ import annotations

from typing import Any

from tradier_account import balances, positions
from tradier_execution import cancel_order as tradier_cancel_order
from tradier_execution import get_order, list_orders, occ_option_symbol, post_order
from tradier_execution_models import ExecutionIntent


class TradierBrokerInterface:
    def get_balances(self) -> dict[str, Any]:
        return balances()

    def get_positions(self) -> dict[str, Any]:
        return positions()

    def get_orders(self) -> dict[str, Any]:
        return list_orders()

    def get_order(self, order_id: str) -> dict[str, Any]:
        return get_order(order_id)

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        return tradier_cancel_order(order_id)

    def build_option_payload(
        self,
        intent: ExecutionIntent,
        *,
        symbol: str,
        expiry: str,
        option_type: str,
        strike: float,
        broker_side: str,
    ) -> dict[str, Any]:
        payload = {
            'class': 'option',
            'symbol': symbol.upper(),
            'option_symbol': occ_option_symbol(symbol, expiry, option_type, strike),
            'side': broker_side,
            'quantity': intent.qty,
            'type': 'limit' if intent.limit_price is not None else 'market',
            'duration': intent.time_in_force,
            'tag': f'alfred-{intent.mode}-{intent.intent_id}',
        }
        if intent.limit_price is not None:
            payload['price'] = round(float(intent.limit_price), 2)
        return payload

    def preview_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        return post_order(payload, preview=True)

    def place_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        return post_order(payload, preview=False)
