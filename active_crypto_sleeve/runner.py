"""
Active Crypto Sleeve - Continuous Runner

Runs signal detection every 30s, monitors BTC/ETH perp structure,
detects sweep/reclaim/breakout setups with real levels,
updates pending trade state, and logs heartbeat activity.
"""

from __future__ import annotations

import json
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(os.getenv("ACTIVE_CRYPTO_ROOT", "/var/www/bazaar"))
HEARTBEAT_PATH = ROOT / "state" / "active_crypto_runner_heartbeat.json"
PRICE_HISTORY_PATH = ROOT / "state" / "active_crypto_price_history.json"
PENDING_TRADE_PATH = ROOT / "state" / "active_crypto_sleeve_pending_trade.json"
APPROVAL_STATE_PATH = ROOT / "state" / "active_crypto_sleeve_approval.json"

HISTORY_SIZE = 60  # Keep 60 price samples (30 min at 30s intervals)


def _float(v: Any) -> float | None:
    try:
        if v in (None, ""):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _load_json(path: Path) -> Any:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return None


def _save_json(path: Path, data: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str))


def _load_client():
    """Lazy import to avoid startup dependency."""
    import importlib
    mod = importlib.import_module("active_crypto_sleeve.coinbase_client")
    return mod.CoinbaseAdvancedClient.from_env()


def _fetch_mids() -> dict[str, float]:
    """Fetch latest mid prices for BTC and ETH perps."""
    client = _load_client()
    mids = {}
    for pid in ("BIP-20DEC30-CDE", "ETP-20DEC30-CDE"):
        result = client.get("/best_bid_ask", {"product_ids": pid})
        if not result.get("ok"):
            continue
        payload = result.get("payload", {}) or {}
    pricebooks = payload.get("pricebooks") or []
    mids = {}
    for pb in pricebooks:
        pid = pb.get("product_id")
        bids = pb.get("bids", []) or []
        asks = pb.get("asks", []) or []
        if bids and asks:
            bid = _float(bids[0].get("price"))
            ask = _float(asks[0].get("price"))
            if bid and ask:
                mids[pid] = round((bid + ask) / 2, 2)
    # Fallback: query products endpoint for mid price
    if not mids:
        client = _load_client()
        prod_result = client.get("/products", {"product_type": "FUTURE"})
        if prod_result.get("ok"):
            pp = prod_result.get("payload", {}) or {}
            for pr in pp.get("products", []):
                pid = pr.get("product_id")
                if pid in ("BIP-20DEC30-CDE", "ETP-20DEC30-CDE"):
                    mid = _float(pr.get("mid_market_price") or pr.get("price"))
                    if mid:
                        mids[pid] = mid
    return mids


def _update_price_history(mids: dict[str, float]):
    """Append current mids to rolling price history."""
    now = time.time()
    history = _load_json(PRICE_HISTORY_PATH) or {"samples": [], "products": {}}
    if "samples" not in history:
        history["samples"] = []
    if "products" not in history:
        history["products"] = {}
    for pid, mid in mids.items():
        history["samples"].append({"ts": now, "pid": pid, "mid": mid})
        if pid not in history["products"]:
            history["products"][pid] = []
        history["products"][pid].append({"ts": now, "mid": mid})
        history["products"][pid] = history["products"][pid][-HISTORY_SIZE:]
    history["samples"] = history["samples"][-500:]  # Keep last 500 global samples
    history["last_updated"] = now
    _save_json(PRICE_HISTORY_PATH, history)


def _detect_sweep_reclaim(
    product_id: str,
    label: str,
    current_mid: float,
    history: list[dict],
) -> dict | None:
    """
    Detect liquidation sweep reclaim setup using rolling price history.
    Candle endpoint (401 on CFM) is not available, so structure is detected
    from recent mid samples.
    """
    if not history or len(history) < 10:
        return None
    
    mids = [s["mid"] for s in history]
    if not mids:
        return None
    
    recent = mids[-20:]  # Last ~10 min of samples
    window_1 = mids[:30]  # First half for structure reference
    window_2 = mids[20:]  # Overlapping detection window
    
    high_1 = max(window_1)
    low_1 = min(window_1)
    high_recent = max(recent)
    low_recent = min(recent)
    current_from_low = (current_mid - low_recent) / low_recent * 100
    
    # BTC-specific sweep thresholds
    depth_threshold = current_mid * 0.002  # 0.2% sweep depth minimum to matter
    reclaim_buffer = current_mid * 0.0008  # 0.08% above swept low to confirm

    swing_low = low_1
    swing_high = high_1
    
    # Check if we swept below the swing low
    swept_low = low_recent <= swing_low * 1.001  # Within 0.1% of swing low
    sweep_depth = (swing_low - low_recent) / swing_low * 100 if low_recent < swing_low else 0
    
    # Check if we reclaimed
    reclaimed = current_mid > swing_low + reclaim_buffer
    
    # Check for SHORT sweep (spike above swing high, then failure)
    swept_high = high_recent >= swing_high * 0.999
    spike_depth = (high_recent - swing_high) / swing_high * 100 if high_recent > swing_high else 0
    failed_reclaim = current_mid < swing_high - reclaim_buffer if high_recent > swing_high else False

    results = []
    
    # LONG setup
    if swept_low and reclaimed and sweep_depth > 0.1:
        entry_zone = f"{swing_low + reclaim_buffer:,.2f} - {swing_low * 1.002:,.2f}"
        stop_price = f"{min(low_recent * 0.998, swing_low * 0.995):,.2f}"
        target_1 = f"{swing_low * 1.005:,.2f}"
        target_2 = f"{swing_low * 1.01:,.2f}"
        
        results.append({
            "product_id": product_id,
            "market": label,
            "direction": "LONG",
            "setup_family": "liquidation_sweep_reclaim",
            "confidence": "MEDIUM" if sweep_depth < 0.3 else "HIGH",
            "signal_detail": f"Swept low ${swing_low:,.2f} by {sweep_depth:.2f}%, reclaimed at ${current_mid:,.2f}",
            "current_mid": current_mid,
            "swing_low": swing_low,
            "swing_high": swing_high,
            "sweep_depth_pct": round(sweep_depth, 3),
            "current_reclaim_pct": round(current_from_low, 3),
            "entry_trigger": f"Enter long if price holds above ${entry_zone} with rising volume/momentum",
            "entry_zone": entry_zone,
            "stop": stop_price,
            "stop_pct": round((current_mid - _float(stop_price.replace(',',''))) / current_mid * 100, 3) if _float(stop_price.replace(',','')) else None,
            "target_1": target_1,
            "target_2": target_2,
            "invalidation": f"Abort if price loses ${stop_price} or reclaim fails >30s after entry",
        })
    
    # SHORT setup
    if swept_high and failed_reclaim and spike_depth > 0.1:
        entry_zone = f"{swing_high - reclaim_buffer:,.2f} - {swing_high * 0.998:,.2f}"
        stop_price = f"{max(high_recent * 1.002, swing_high * 1.005):,.2f}"
        target_1 = f"{swing_high * 0.995:,.2f}"
        target_2 = f"{swing_high * 0.99:,.2f}"
        
        results.append({
            "product_id": product_id,
            "market": label,
            "direction": "SHORT",
            "setup_family": "liquidation_sweep_reclaim",
            "confidence": "MEDIUM" if spike_depth < 0.3 else "HIGH",
            "signal_detail": f"Spiked above ${swing_high:,.2f} by {spike_depth:.2f}%, failed back to ${current_mid:,.2f}",
            "current_mid": current_mid,
            "swing_low": swing_low,
            "swing_high": swing_high,
            "spike_depth_pct": round(spike_depth, 3),
            "entry_trigger": f"Enter short if price fails below ${entry_zone} with selling volume",
            "entry_zone": entry_zone,
            "stop": stop_price,
            "target_1": target_1,
            "target_2": target_2,
            "invalidation": f"Abort if price reclaims above ${stop_price} or short fails >30s",
        })
    
    return results[0] if results else None


def _main_loop():
    """Single cycle: fetch data, detect setups, update state."""
    cycle_id = secrets.token_hex(4)
    now = time.time()
    
    try:
        mids = _fetch_mids()
        if not mids:
            return {"ok": False, "cycle": cycle_id, "error": "no mids fetched"}
        
        _update_price_history(mids)
        history = _load_json(PRICE_HISTORY_PATH) or {}
        product_samples = history.get("products", {})
        
        signals = []
        for pid, label in [("BIP-20DEC30-CDE", "BTC PERP"), ("ETP-20DEC30-CDE", "ETH PERP")]:
            mid = mids.get(pid)
            if not mid:
                continue
            prod_history = product_samples.get(pid, [])
            # candles endpoint is 401 on CFM; use rolling price history only
            signal = _detect_sweep_reclaim(pid, label, mid, prod_history)
            if signal:
                signals.append(signal)
        
        # Update pending trade if we have a signal
        existing = _load_json(PENDING_TRADE_PATH)
        current_pending = existing.get("trade_card_id") if existing else None
        
        if signals:
            best_signal = signals[0]
            # Only overwrite if higher confidence or no existing pending trade
            if not current_pending:
                trade_card_id = secrets.token_hex(8)
                pending = {
                    "trade_card_id": trade_card_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "card": best_signal,
                    "submitted": False,
                    "submitted_at": None,
                    "fill_confirmed": False,
                    "stop_order_id": None,
                }
                _save_json(PENDING_TRADE_PATH, pending)
                
                # Also reset approval state for new trade
                approval_state = _load_json(APPROVAL_STATE_PATH) or {}
                if approval_state.get("approved"):
                    # Don't reset if already approved - that's an active approved card
                    pass
                else:
                    _save_json(APPROVAL_STATE_PATH, {
                        "approved": False,
                        "approved_at": None,
                        "trade_card_id": trade_card_id,
                        "conor_message_id": None,
                    })
                
                heartbeat = {
                    "ok": True,
                    "cycle": cycle_id,
                    "ts": now,
                    "time": datetime.now(timezone.utc).isoformat(),
                    "mids": mids,
                    "active_signal": {
                        "direction": best_signal["direction"],
                        "setup": best_signal["setup_family"],
                        "detail": best_signal["signal_detail"],
                    },
                    "pending_trade": True,
                    "pending_trade_card_id": trade_card_id,
                }
            else:
                heartbeat = {
                    "ok": True,
                    "cycle": cycle_id,
                    "ts": now,
                    "time": datetime.now(timezone.utc).isoformat(),
                    "mids": mids,
                    "active_signal": {
                        "direction": best_signal["direction"],
                        "setup": best_signal["setup_family"],
                        "detail": best_signal["signal_detail"],
                    },
                    "pending_trade": True,
                    "note": "Signal detected but pending trade already exists from prior cycle",
                }
        else:
            heartbeat = {
                "ok": True,
                "cycle": cycle_id,
                "ts": now,
                "time": datetime.now(timezone.utc).isoformat(),
                "mids": mids,
                "active_signal": None,
                "pending_trade": current_pending is not None,
                "note": "No actionable setup detected this cycle",
            }
        
        _save_json(HEARTBEAT_PATH, heartbeat)
        return heartbeat
    
    except Exception as e:
        err = {
            "ok": False,
            "cycle": cycle_id,
            "ts": now,
            "error": str(e),
        }
        _save_json(HEARTBEAT_PATH, err)
        return err


def run_once() -> dict:
    """Run one cycle and return result."""
    return _main_loop()


def run_loop(interval: float = 30.0):
    """Run continuous monitoring loop."""
    print(f"[active-crypto-runner] Starting loop, interval={interval}s")
    while True:
        start = time.time()
        result = _main_loop()
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        if result.get("ok"):
            mids = result.get("mids", {})
            signal = result.get("active_signal")
            if signal:
                print(f"[{ts}] MIDS: {mids} | SIGNAL: {signal['direction']} {signal['setup']} | {signal.get('detail','')[:80]}")
            else:
                print(f"[{ts}] MIDS: {mids} | no setup")
        else:
            print(f"[{ts}] ERROR: {result.get('error','unknown')}")
        elapsed = time.time() - start
        sleep_time = max(1.0, interval - elapsed)
        time.sleep(sleep_time)


if __name__ == "__main__":
    import sys
    if "--once" in sys.argv:
        print(json.dumps(run_once(), indent=2))
    elif "--loop" in sys.argv:
        run_loop(interval=30.0)
    else:
        print(json.dumps(run_once(), indent=2))
