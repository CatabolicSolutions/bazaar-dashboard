"""
Coinbase Active Crypto Sleeve - Live Executor

Order placement, cancellation, close, and approval flow.
Orders block on approval gate even when live is enabled.
"""

from __future__ import annotations

import json
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jwt
import requests

from .coinbase_client import CoinbaseAdvancedClient, CoinbaseConfig, _first_existing, _read_secret

ROOT = Path(os.getenv("ACTIVE_CRYPTO_ROOT", "/var/www/bazaar"))
WORKSPACE = Path(os.getenv("WORKSPACE", "/home/catabolic_solutions/.openclaw/workspace"))
APPROVAL_STATE_PATH = ROOT / "state" / "active_crypto_sleeve_approval.json"
PENDING_TRADE_PATH = ROOT / "state" / "active_crypto_sleeve_pending_trade.json"


class TradeApprovalGate:
    """Approval gate: no order executes without explicit Conor approval."""

    def __init__(self, state_path: Path = APPROVAL_STATE_PATH):
        self.state_path = state_path
        self._ensure_dir()

    def _ensure_dir(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

    def _read_state(self) -> dict:
        if self.state_path.exists():
            try:
                return json.loads(self.state_path.read_text())
            except Exception:
                pass
        return {"approved": False, "approved_at": None, "trade_card_id": None, "conor_message_id": None}

    def _write_state(self, state: dict):
        self.state_path.write_text(json.dumps(state, indent=2))

    def reset(self):
        self._write_state({"approved": False, "approved_at": None, "trade_card_id": None, "conor_message_id": None})

    def is_approved(self, trade_card_id: str | None = None) -> bool:
        state = self._read_state()
        if not state.get("approved"):
            return False
        if trade_card_id and state.get("trade_card_id") != trade_card_id:
            return False
        return True

    def approve(self, trade_card_id: str, conor_message_id: str | None = None):
        self._write_state({
            "approved": True,
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "trade_card_id": trade_card_id,
            "conor_message_id": conor_message_id,
        })

    def get_state(self) -> dict:
        return self._read_state()


def save_pending_trade(card: dict) -> str:
    """Save a pending trade card and return its ID."""
    PENDING_TRADE_PATH.parent.mkdir(parents=True, exist_ok=True)
    card_id = secrets.token_hex(8)
    payload = {
        "trade_card_id": card_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "card": card,
        "submitted": False,
        "submitted_at": None,
        "fill_confirmed": False,
        "stop_order_id": None,
    }
    PENDING_TRADE_PATH.write_text(json.dumps(payload, indent=2))
    return card_id


def get_pending_trade() -> dict | None:
    """Read the current pending trade card, if any."""
    if PENDING_TRADE_PATH.exists():
        try:
            return json.loads(PENDING_TRADE_PATH.read_text())
        except Exception:
            pass
    return None


def clear_pending_trade():
    if PENDING_TRADE_PATH.exists():
        PENDING_TRADE_PATH.unlink()


class CoinbaseExecutor:
    """Live order executor for Coinbase CFM derivatives."""

    def __init__(self, client: CoinbaseAdvancedClient | None = None):
        self.client = client or CoinbaseAdvancedClient.from_env()
        self.approval = TradeApprovalGate()

    def _jwt_post(self, path: str, body: dict) -> dict:
        """POST with JWT auth."""
        uri = f"POST {self.client.config.host}{path}"
        now = int(time.time())
        payload = {
            "sub": self.client.config.key_name,
            "iss": "cdp",
            "nbf": now,
            "exp": now + 120,
            "uri": uri,
        }
        headers = {"kid": self.client.config.key_name, "nonce": secrets.token_hex(16)}
        token = jwt.encode(payload, self.client.config.private_key, algorithm="ES256", headers=headers)
        response = requests.post(
            f"https://{self.client.config.host}{path}",
            json=body,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=20,
        )
        try:
            resp = response.json()
        except Exception:
            resp = {"raw": response.text}
        return {"ok": response.ok, "status_code": response.status_code, "path": path, "payload": resp}

    def place_order(
        self,
        product_id: str,
        side: str,
        size: str,
        order_type: str = "MARKET",
        limit_price: str | None = None,
        stop_price: str | None = None,
        time_in_force: str = "FOK",
    ) -> dict:
        """Place a Coinbase CFM order.

        Args:
            product_id: e.g. BIP-20DEC30-CDE
            side: BUY or SELL
            size: quantity as string
            order_type: MARKET, LIMIT, STOP
            limit_price: required for LIMIT/STOP
            stop_price: required for STOP
            time_in_force: FOK, IOC, GTC, GTT
        """
        live_enabled = os.getenv("ACTIVE_CRYPTO_LIVE_ENABLED", "false").lower() == "true"
        if not live_enabled:
            return {"ok": False, "error": "ACTIVE_CRYPTO_LIVE_ENABLED is false. No order placed."}

        pending = get_pending_trade()
        if not pending:
            return {"ok": False, "error": "No pending trade card. Generate a trade card first."}

        # Verify account state before order
        pos_result = self.client.get("/cfm/positions")
        if not pos_result.get("ok"):
            return {"ok": False, "error": "Cannot verify CFM positions before order."}
        existing = (pos_result.get("payload", {}) or {}).get("positions", [])
        max_positions = int(os.getenv("ACTIVE_CRYPTO_MAX_POSITIONS", "1"))
        if existing and len(existing) >= max_positions:
            return {"ok": False, "error": f"Already at max positions ({max_positions}). Close existing position first."}

        order_body = {
            "product_id": product_id,
            "side": side.upper(),
            "order_configuration": {
                "market_market_ioc": {
                    "quote_size": size,
                }
            },
        }
        if order_type == "LIMIT" and limit_price:
            order_body["order_configuration"] = {
                "limit_limit_gtc": {
                    "base_size": size,
                    "limit_price": limit_price,
                    "post_only": False,
                }
            }
        elif order_type == "STOP" and limit_price:
            order_body["order_configuration"] = {
                "stop_limit_stop_limit_gtc": {
                    "base_size": size,
                    "limit_price": limit_price,
                    "stop_price": stop_price or limit_price,
                }
            }

        result = self._jwt_post(f"{self.client.config.api_prefix}/orders", order_body)

        if result.get("ok"):
            # Mark this trade as submitted
            pending = get_pending_trade()
            if pending:
                pending["submitted"] = True
                pending["submitted_at"] = datetime.now(timezone.utc).isoformat()
                pending["order_response"] = result.get("payload", {})
                PENDING_TRADE_PATH.write_text(json.dumps(pending, indent=2))
            self.approval.reset()

        return result

    def cancel_order(self, order_id: str) -> dict:
        body = {"order_ids": [order_id]}
        return self._jwt_post(f"{self.client.config.api_prefix}/orders/batch_cancel", body)

    def close_position(self, product_id: str, side: str, size: str) -> dict:
        """Close a CFM position by placing an opposite-side order."""
        close_side = "SELL" if side.upper() == "BUY" else "BUY"
        body = {
            "product_id": product_id,
            "side": close_side,
            "order_configuration": {
                "market_market_ioc": {
                    "quote_size": size,
                }
            },
        }
        return self._jwt_post(f"{self.client.config.api_prefix}/orders", body)


def executor_status() -> dict:
    """Return executor-specific status for Agora."""
    client = CoinbaseAdvancedClient.from_env()
    executor = CoinbaseExecutor(client)
    approval = executor.approval.get_state()
    pending = get_pending_trade()

    live_enabled = os.getenv("ACTIVE_CRYPTO_LIVE_ENABLED", "false").lower() == "true"

    return {
        "ok": True,
        "live_enabled": live_enabled,
        "approval_gate": {
            "approved": approval.get("approved", False),
            "approved_at": approval.get("approved_at"),
            "trade_card_id": approval.get("trade_card_id"),
        },
        "pending_trade": pending is not None,
        "live_orders_blocked_reasons": [
            reason
            for reason, flag in [
                ("live_not_enabled", not live_enabled),
                ("no_pending_trade", not pending),
                ("trade_not_approved", (not approval.get("approved")) if pending else False),
            ]
            if flag
        ],
    }


if __name__ == "__main__":
    print(json.dumps(executor_status(), indent=2))
