from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


PRIMARY_MARKETS = {
    "BIP-20DEC30-CDE": {
        "label": "BTC PERP",
        "risk_stop_pct": 0.28,
        "target_1_pct": 0.42,
        "target_2_pct": 0.75,
        "notional_multiplier": 1.25,
        "max_buying_power_pct": 0.80,
    },
    "ETP-20DEC30-CDE": {
        "label": "ETH PERP",
        "risk_stop_pct": 0.38,
        "target_1_pct": 0.55,
        "target_2_pct": 0.95,
        "notional_multiplier": 1.00,
        "max_buying_power_pct": 0.70,
    },
}


@dataclass
class TradeCard:
    product_id: str
    market: str
    direction: str
    setup_family: str
    regime: str
    current_mid: float | None
    entry_trigger: str
    invalidation: str
    targets: list[str]
    max_notional_usd: float
    max_dollars_at_risk: float
    max_leverage: float
    approval_state: str
    order_state: str


def _float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _money(value: float | None) -> str:
    if value is None:
        return "unknown"
    return f"${value:,.2f}"


def _price(value: float | None) -> str:
    if value is None:
        return "unknown"
    return f"{value:,.2f}"


def _balance_numbers(status: dict[str, Any]) -> tuple[float, float]:
    summary = status.get("balance_summary") or {}
    futures_buying_power = summary.get("futures_buying_power")
    if isinstance(futures_buying_power, dict):
        futures_buying_power = futures_buying_power.get("value")
    buying_power = _float(futures_buying_power) or 0.0
    cfm_usd = _float(summary.get("cfm_usd_balance", {}).get("value")) or 0.0
    return buying_power, cfm_usd


def _permission_flag(status: dict[str, Any], name: str) -> bool:
    permissions = status.get("permissions") or {}
    value = permissions.get(name)
    if isinstance(value, str):
        return value.lower() == "true"
    return bool(value)


def _trade_cards(status: dict[str, Any]) -> list[TradeCard]:
    buying_power, cfm_usd = _balance_numbers(status)
    guardrails = status.get("guardrails") or {}
    max_trade_risk_pct = _float(guardrails.get("max_trade_risk_pct")) or 25.0
    max_leverage = _float(guardrails.get("max_leverage")) or 2.0
    max_risk = cfm_usd * (max_trade_risk_pct / 100.0)

    cards: list[TradeCard] = []
    for product in status.get("primary_products") or []:
        product_id = product.get("product_id")
        spec = PRIMARY_MARKETS.get(product_id)
        if not spec:
            continue

        mid = _float(product.get("mid_market_price") or product.get("price"))
        max_notional = min(
            cfm_usd * spec["notional_multiplier"],
            buying_power * spec["max_buying_power_pct"],
        )

        if mid:
            long_entry = mid * 1.0012
            stop = mid * (1 - spec["risk_stop_pct"] / 100.0)
            target_1 = mid * (1 + spec["target_1_pct"] / 100.0)
            target_2 = mid * (1 + spec["target_2_pct"] / 100.0)
            entry_trigger = (
                f"Review long only if price reclaims and holds above {_price(long_entry)} "
                "with rising momentum and no failed retest."
            )
            invalidation = f"Abort if price loses {_price(stop)} or reclaim fails after entry window."
            targets = [
                f"trim/raise stop near {_price(target_1)}",
                f"exit runner near {_price(target_2)} or on momentum failure",
            ]
        else:
            entry_trigger = "No executable trigger: live midpoint unavailable."
            invalidation = "No trade until Coinbase market data is fresh."
            targets = ["unavailable"]

        cards.append(
            TradeCard(
                product_id=product_id,
                market=spec["label"],
                direction="WAIT_FOR_LONG_RECLAIM",
                setup_family="sweep_reclaim / trend_reclaim / compression_breakout",
                regime="BTC-biased, only trade when momentum confirms. USDC is a defensive pause, not the default objective.",
                current_mid=mid,
                entry_trigger=entry_trigger,
                invalidation=invalidation,
                targets=targets,
                max_notional_usd=round(max(0.0, max_notional), 2),
                max_dollars_at_risk=round(max(0.0, max_risk), 2),
                max_leverage=max_leverage,
                approval_state="REQUIRES_CONOR_APPROVAL",
                order_state="NO_ORDER_BUILT",
            )
        )
    return cards


def _protections(status: dict[str, Any]) -> list[dict[str, str]]:
    guardrails = status.get("guardrails") or {}
    positions = status.get("positions") or []
    open_orders = status.get("open_orders") or []
    live_enabled = bool(status.get("live_trading_enabled"))
    can_transfer = _permission_flag(status, "can_transfer")

    protections = [
        {
            "name": "explicit approval",
            "state": "ENFORCED",
            "detail": "No Coinbase derivatives order can be sent unless Conor approves the exact trade card.",
        },
        {
            "name": "live switch",
            "state": "OFF" if not live_enabled else "ARMED",
            "detail": "ACTIVE_CRYPTO_LIVE_ENABLED must be true before live order code can run.",
        },
        {
            "name": "open positions",
            "state": "CLEAR" if len(positions) == 0 else "BLOCKED",
            "detail": f"{len(positions)} current Coinbase CFM position(s); max is {guardrails.get('max_open_positions', 1)}.",
        },
        {
            "name": "open orders",
            "state": "CLEAR" if len(open_orders) == 0 else "BLOCKED",
            "detail": f"{len(open_orders)} open Coinbase order(s); new proposals require clean order state.",
        },
        {
            "name": "per-trade risk",
            "state": "ENFORCED",
            "detail": f"Max planned risk is {guardrails.get('max_trade_risk_pct', 25)}% of CFM USD balance.",
        },
        {
            "name": "daily loss cap",
            "state": "ENFORCED",
            "detail": f"Stop proposing new trades after {guardrails.get('max_daily_loss_pct', 30)}% daily realized loss.",
        },
        {
            "name": "leverage cap",
            "state": "ENFORCED",
            "detail": f"Max strategy leverage is {guardrails.get('max_leverage', 2)}x even if Coinbase permits more.",
        },
        {
            "name": "withdrawals/transfers",
            "state": "BLOCKED" if can_transfer else "ENFORCED",
            "detail": "API transfer permission is disabled." if not can_transfer else "Transfer permission is enabled; key should be reduced before production.",
        },
        {
            "name": "stop required",
            "state": "ENFORCED",
            "detail": "Every approval card must include invalidation and stop behavior before an order can be submitted.",
        },
    ]
    return protections


def build_signal_board(status: dict[str, Any]) -> dict[str, Any]:
    cards = _trade_cards(status)
    protections = _protections(status)
    buying_power, cfm_usd = _balance_numbers(status)
    return {
        "ok": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "review_only",
        "capital": {
            "buying_power": round(buying_power, 2),
            "cfm_usd": round(cfm_usd, 2),
            "display": f"CFM USD {_money(cfm_usd)} / buying power {_money(buying_power)}",
        },
        "logic": {
            "bias": "BTC first; ETH is secondary only when BTC is messy and ETH has cleaner momentum.",
            "entry": "Long reclaim after sweep, VWAP/midline reclaim, or compression breakout with confirmation.",
            "exit": "Take profit into extension, tighten stop after first target, exit fast on failed reclaim.",
            "no_trade": "No trade during stale data, unclear trend, active order uncertainty, or after daily loss cap.",
        },
        "cards": [asdict(card) for card in cards],
        "protections": protections,
    }
