from __future__ import annotations

import json
import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jwt
import requests


ROOT = Path(os.getenv("ACTIVE_CRYPTO_ROOT", "/var/www/bazaar"))
WORKSPACE = Path(os.getenv("WORKSPACE", "/home/catabolic_solutions/.openclaw/workspace"))
DEFAULT_KEY_NAME_PATHS = [
    ROOT / "credentials" / "coinbase_agoraalgo_api_key_name.txt",
    WORKSPACE / "credentials" / "coinbase_agoraalgo_api_key_name.txt",
]
DEFAULT_PRIVATE_KEY_PATHS = [
    ROOT / "credentials" / "coinbase_agoraalgo_private_key.pem",
    WORKSPACE / "credentials" / "coinbase_agoraalgo_private_key.pem",
]


def _first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def _read_secret(env_name: str, paths: list[Path]) -> tuple[str | None, str | None]:
    value = os.getenv(env_name)
    if value:
        return value.strip(), f"env:{env_name}"
    path = _first_existing(paths)
    if path:
        return path.read_text(encoding="utf-8").strip(), str(path)
    return None, None


@dataclass
class CoinbaseConfig:
    key_name: str
    private_key: str
    key_source: str
    private_key_source: str
    host: str = "api.coinbase.com"
    api_prefix: str = "/api/v3/brokerage"


class CoinbaseAdvancedClient:
    def __init__(self, config: CoinbaseConfig):
        self.config = config

    @classmethod
    def from_env(cls) -> "CoinbaseAdvancedClient":
        key_name, key_source = _read_secret("COINBASE_API_KEY_NAME", DEFAULT_KEY_NAME_PATHS)
        private_key, private_key_source = _read_secret("COINBASE_PRIVATE_KEY", DEFAULT_PRIVATE_KEY_PATHS)
        if not key_name or not private_key:
            raise RuntimeError("Coinbase API credentials not found")
        return cls(CoinbaseConfig(key_name, private_key, key_source or "unknown", private_key_source or "unknown"))

    def _jwt(self, method: str, path: str) -> str:
        method = method.upper()
        now = int(time.time())
        uri = f"{method} {self.config.host}{path}"
        payload = {
            "sub": self.config.key_name,
            "iss": "cdp",
            "nbf": now,
            "exp": now + 120,
            "uri": uri,
        }
        headers = {"kid": self.config.key_name, "nonce": secrets.token_hex(16)}
        return jwt.encode(payload, self.config.private_key, algorithm="ES256", headers=headers)

    def get(self, resource: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        path = resource if resource.startswith("/api/") else f"{self.config.api_prefix}{resource}"
        token = self._jwt("GET", path)
        response = requests.get(
            f"https://{self.config.host}{path}",
            params=params,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=20,
        )
        try:
            payload = response.json()
        except Exception:
            payload = {"raw": response.text}
        return {"ok": response.ok, "status_code": response.status_code, "path": path, "payload": payload}


def _payload(result: dict[str, Any], default: Any = None) -> Any:
    if result.get("ok"):
        return result.get("payload", default)
    return default


def _product_summary(product: dict[str, Any]) -> dict[str, Any]:
    details = product.get("future_product_details") or {}
    perp = details.get("perpetual_details") or {}
    return {
        "product_id": product.get("product_id"),
        "display_name": product.get("display_name"),
        "venue": product.get("product_venue"),
        "price": product.get("price"),
        "mid_market_price": product.get("mid_market_price"),
        "best_bid_price": product.get("best_bid_price"),
        "best_ask_price": product.get("best_ask_price"),
        "quote_min_size": product.get("quote_min_size"),
        "base_increment": product.get("base_increment"),
        "price_increment": product.get("price_increment"),
        "status": product.get("status"),
        "trading_disabled": product.get("trading_disabled"),
        "contract_expiry_type": details.get("contract_expiry_type"),
        "contract_code": details.get("contract_code"),
        "funding_rate": perp.get("funding_rate"),
        "funding_time": perp.get("funding_time"),
        "open_interest": perp.get("open_interest"),
        "max_leverage": perp.get("max_leverage"),
    }


def active_crypto_status() -> dict[str, Any]:
    client = CoinbaseAdvancedClient.from_env()
    key_permissions = client.get("/key_permissions")
    balance = client.get("/cfm/balance_summary")
    positions = client.get("/cfm/positions")
    orders = client.get("/orders/historical/batch", {"order_status": "OPEN"})
    products = client.get("/products", {"product_type": "FUTURE"})
    best_bid_ask = client.get("/best_bid_ask", {"product_ids": "BIP-20DEC30-CDE,ETP-20DEC30-CDE"})

    product_rows = (_payload(products, {}) or {}).get("products", [])
    fcm_products = [p for p in product_rows if p.get("product_venue") == "FCM"]
    primary_ids = {"BIP-20DEC30-CDE", "ETP-20DEC30-CDE"}
    primary = [_product_summary(p) for p in fcm_products if p.get("product_id") in primary_ids]

    balance_payload = _payload(balance, {}) or {}
    summary = balance_payload.get("balance_summary") or {}
    position_rows = (_payload(positions, {}) or {}).get("positions", [])
    order_rows = (_payload(orders, {}) or {}).get("orders", [])

    trade_card_template = {
        "required_before_order": [
            "market",
            "direction",
            "setup_family",
            "fundamental_regime",
            "entry_trigger",
            "stop",
            "targets",
            "size_notional",
            "margin",
            "leverage",
            "dollars_at_risk",
            "risk_reward",
            "failure_mode",
            "explicit_conor_approval",
        ],
        "approval_rule": "No Coinbase derivatives order may be placed without explicit Conor approval of the exact order.",
    }

    status = {
        "ok": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "venue": "coinbase_cfm",
        "live_trading_enabled": os.getenv("ACTIVE_CRYPTO_LIVE_ENABLED", "false").lower() == "true",
        "orders_blocked_without_approval": True,
        "credential_sources": {
            "key_name": client.config.key_source,
            "private_key": client.config.private_key_source,
        },
        "checks": {
            "key_permissions": key_permissions,
            "cfm_balance_summary": balance,
            "cfm_positions": positions,
            "open_orders": orders,
            "futures_products": {"ok": products.get("ok"), "status_code": products.get("status_code"), "count": len(product_rows)},
            "best_bid_ask": best_bid_ask,
        },
        "permissions": _payload(key_permissions, {}),
        "balance_summary": summary,
        "positions": position_rows,
        "open_orders": order_rows,
        "primary_products": primary,
        "fcm_products_count": len(fcm_products),
        "guardrails": {
            "max_trade_risk_pct": float(os.getenv("ACTIVE_CRYPTO_MAX_TRADE_RISK_PCT", "50")),
            "max_daily_loss_pct": float(os.getenv("ACTIVE_CRYPTO_MAX_DAILY_LOSS_PCT", "100")),
            "max_leverage": float(os.getenv("ACTIVE_CRYPTO_MAX_LEVERAGE", "2")),
            "max_open_positions": 1,
            "markets": ["BIP-20DEC30-CDE", "ETP-20DEC30-CDE"],
            "approval_required": True,
        },
        "strategy": {
            "families": [
                "liquidation_sweep_reclaim",
                "trend_continuation_after_reclaim",
                "volatility_compression_breakout",
            ],
            "fundamental_regime_filter": [
                "btc_macro_bias",
                "dollar_rates_pressure",
                "crypto_native_flow",
                "funding_friction",
                "volatility_regime",
            ],
        },
        "trade_card_template": trade_card_template,
    }
    try:
        from .signals import build_signal_board

        status["signal_board"] = build_signal_board(status)
    except Exception as exc:
        status["signal_board"] = {"ok": False, "mode": "review_only", "error": str(exc)}
    return status


if __name__ == "__main__":
    print(json.dumps(active_crypto_status(), indent=2))
