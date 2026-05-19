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


# ── Cached client (reused across cycles) ────────────────────────────
_CLIENT_CACHE: dict = {}

def _import_le_executor() -> tuple | None:
    """Lazy import the CoinbaseExecutor. Returns None if unavailable."""
    try:
        import importlib
        mod = importlib.import_module("active_crypto_sleeve.executor")
        return mod, getattr(mod, "CoinbaseExecutor", None)
    except Exception:
        return None


def _get_client():
    """Return a cached Coinbase client (initializes once)."""
    if not _CLIENT_CACHE:
        import importlib
        mod = importlib.import_module("active_crypto_sleeve.coinbase_client")
        _CLIENT_CACHE["client"] = mod.CoinbaseAdvancedClient.from_env()
    return _CLIENT_CACHE["client"]


def _fetch_mids() -> dict[str, float]:
    """Fetch latest mid prices for BTC and ETH perps from products endpoint.
    Uses a single API call (products list) instead of 3 separate queries."""
    client = _get_client()
    result = client.get("/products", {"product_type": "FUTURE"})
    if not result.get("ok"):
        return {}
    payload = result.get("payload", {}) or {}
    mids = {}
    for pr in payload.get("products", []):
        pid = pr.get("product_id")
        if pid in ("BIP-20DEC30-CDE", "ETP-20DEC30-CDE"):
            mid = _float(pr.get("mid_market_price") or pr.get("price"))
            if mid:
                mids[pid] = mid
    # Fallback: try best_bid_ask if products endpoint gave nothing
    if not mids:
        for pid in ("BIP-20DEC30-CDE", "ETP-20DEC30-CDE"):
            r = client.get("/best_bid_ask", {"product_ids": pid})
            if not r.get("ok"):
                continue
            pb = (r.get("payload", {}) or {}).get("pricebooks", [])
            for book in pb:
                bids = book.get("bids", []) or []
                asks = book.get("asks", []) or []
                if bids and asks:
                    bid = _float(bids[0].get("price"))
                    ask = _float(asks[0].get("price"))
                    if bid and ask:
                        mids[book.get("product_id")] = round((bid + ask) / 2, 2)
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


def _fetch_candles(product_id: str, granularity: str = "FIVE_MINUTE", count: int = 60) -> list[dict]:
    """Fetch candle data from CFM products endpoint."""
    client = _get_client()
    r = client.get(f"/products/{product_id}/candles", {"granularity": granularity})
    if not r.get("ok"):
        return []
    candles = (r.get("payload", {}) or {}).get("candles", []) or []
    return candles[-count:]


def _detect_sweep_reclaim_candles(
    product_id: str,
    label: str,
    candles: list[dict],
) -> dict | None:
    """
    Detect liquidation sweep reclaim using real OHLC candle data.
    LONG: candle wicks below swing low, reclaims above.
    SHORT: spike above swing high, fails back.
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
    
    # Build candle data for detection
    if not candles or len(candles) < 10:
        return None

    data = []
    for c in candles:
        o = _float(c.get("open"))
        h = _float(c.get("high"))
        l = _float(c.get("low"))
        cl = _float(c.get("close"))
        v = _float(c.get("volume"))
        if o and h and l and cl:
            data.append({"open": o, "high": h, "low": l, "close": cl, "volume": v or 0})

    if len(data) < 10:
        return None

    last = data[-1]
    lookback = data[-20:-2]
    recent_data = data[-5:]

    swing_low = min(c["low"] for c in lookback)
    swing_high = max(c["high"] for c in lookback)
    avg_volume = sum(c["volume"] for c in lookback) / max(len(lookback), 1)

    current_close = last["close"]
    current_volume = last["volume"]
    min_recent_low = min(c["low"] for c in recent_data)
    max_recent_high = max(c["high"] for c in recent_data)
    vol_ratio = current_volume / max(avg_volume, 0.01) if avg_volume > 0 else 0

    # LONG setup
    sweep_long = min_recent_low < swing_low * 0.999
    reclaim_long = current_close > swing_low * 1.0005
    sweep_depth_long = (swing_low - min_recent_low) / swing_low * 100 if sweep_long else 0

    # SHORT setup
    sweep_short = max_recent_high > swing_high * 1.001
    reclaim_short = current_close < swing_high * 0.9995
    spike_depth_short = (max_recent_high - swing_high) / swing_high * 100 if sweep_short else 0

    results = []

    if sweep_long and reclaim_long:
        conf = "HIGH" if sweep_depth_long >= 0.3 else ("MEDIUM" if sweep_depth_long >= 0.15 else "LOW")
        if (conf in ("HIGH", "MEDIUM")) or (vol_ratio > 1.5):
            stop_val = min_recent_low * 0.998
            stop_pct = round((current_close - stop_val) / current_close * 100, 3) if stop_val else None
            results.append({
                "product_id": product_id, "market": label, "direction": "LONG",
                "setup_family": "candle_sweep_reclaim", "confidence": conf,
                "signal_detail": f"Wick ${min_recent_low:,.2f} swept swing low ${swing_low:,.2f} ({sweep_depth_long:.2f}%), reclaimed at ${current_close:,.2f}. Vol {vol_ratio:.1f}x avg",
                "current_mid": current_close, "swing_low": swing_low, "swing_high": swing_high,
                "sweep_depth_pct": round(sweep_depth_long, 3), "volume_ratio": round(vol_ratio, 2),
                "entry_zone": f"{swing_low * 1.001:,.2f} - {swing_low * 1.003:,.2f}",
                "entry_trigger": f"Enter long if price holds above ${swing_low * 1.001:,.2f}",
                "stop": f"{stop_val:,.2f}", "stop_pct": stop_pct,
                "target_1": f"{swing_low * 1.005:,.2f}", "target_2": f"{swing_low * 1.01:,.2f}",
                "invalidation": f"Abort if price loses ${stop_val:,.2f}",
            })

    if sweep_short and reclaim_short:
        conf = "HIGH" if spike_depth_short >= 0.3 else ("MEDIUM" if spike_depth_short >= 0.15 else "LOW")
        if (conf in ("HIGH", "MEDIUM")) or (vol_ratio > 1.5):
            results.append({
                "product_id": product_id, "market": label, "direction": "SHORT",
                "setup_family": "candle_sweep_reclaim", "confidence": conf,
                "signal_detail": f"Spike to ${max_recent_high:,.2f} (${(max_recent_high - swing_high):,.2f} above swing high ${swing_high:,.2f}), failed to ${current_close:,.2f}. Vol {vol_ratio:.1f}x avg",
                "current_mid": current_close, "swing_low": swing_low, "swing_high": swing_high,
                "spike_depth_pct": round(spike_depth_short, 3), "volume_ratio": round(vol_ratio, 2),
                "entry_zone": f"{swing_high * 0.998:,.2f} - {swing_high * 0.9995:,.2f}",
                "entry_trigger": f"Enter short below ${swing_high * 0.999:,.2f}",
                "stop": f"{max_recent_high * 1.002:,.2f}",
                "target_1": f"{swing_high * 0.995:,.2f}", "target_2": f"{swing_high * 0.99:,.2f}",
                "invalidation": f"Abort if price reclaims above ${max_recent_high * 1.002:,.2f}",
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
        
        # Fetch REAL candle data for sweep detection
        signals = []
        for pid, label in [("BIP-20DEC30-CDE", "BTC PERP"), ("ETP-20DEC30-CDE", "ETH PERP")]:
            mid = mids.get(pid)
            if not mid:
                continue
            candles = _fetch_candles(pid, "FIVE_MINUTE", 60)
            signal = _detect_sweep_reclaim_candles(pid, label, candles)
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
                
                # ── AUTO-EXECUTE on HIGH confidence ────────────────────────
                if best_signal["confidence"] == "HIGH":
                    imported = _import_le_executor()
                    if imported:
                        executor_module, CoinbaseExecutor = imported
                        try:
                            # Get balance for sizing
                            client = _get_client()
                            bal_result = client.get("/cfm/balance_summary")
                            cfg_cfm = 0.0
                            if bal_result.get("ok"):
                                bal_payload = (bal_result.get("payload") or {}).get("futures_balance_summary", {}) or {}
                                cfg_cfm = _float(bal_payload.get("total_with_cushion", {}).get("value")) or 0.0
                            
                            # Size: 50% of CFM / stop distance
                            stop_str = best_signal.get("stop", "0")
                            stop_val = _float(stop_str.replace(",", "")) or 0.0
                            entry = best_signal.get("entry_zone", "0-0").split(" - ")[0]
                            entry_val = _float(entry.replace(",", "")) or best_signal["current_mid"]
                            stop_distance = abs(entry_val - stop_val) / entry_val if entry_val and stop_val else 0.01
                            
                            max_risk = cfg_cfm * 0.5  # 50% of CFM
                            position_value = max_risk / max(stop_distance, 0.001)
                            position_value = min(position_value, cfg_cfm * 2.0)  # Cap at 2x leverage
                            position_value = max(position_value, 10.0)  # Min $10
                            
                            executor = CoinbaseExecutor(client)
                            direction = best_signal["direction"]
                            order_side = "BUY" if direction == "LONG" else "SELL"
                            
                            order_result = executor.place_order(
                                product_id=best_signal["product_id"],
                                side=order_side,
                                size=f"{position_value:.2f}",
                            )
                            
                            # Save execution notification state
                            exec_notification = {
                                "executed": order_result.get("ok", False),
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "trade_card_id": trade_card_id,
                                "direction": direction,
                                "market": best_signal["market"],
                                "entry": entry_val,
                                "size_usd": round(position_value, 2),
                                "stop": stop_val if stop_val > 0 else stop_str,
                                "target_1": best_signal.get("target_1", "?"),
                                "target_2": best_signal.get("target_2", "?"),
                                "setup_detail": best_signal["signal_detail"],
                                "order_result": order_result.get("ok", False),
                                "order_error": order_result.get("error"),
                                "sent_to_conor": False,
                            }
                            _save_json(ROOT / "state" / "active_crypto_last_execution.json", exec_notification)
                            
                            if order_result.get("ok"):
                                # Also send via Coinbase executor's built-in flow
                                pending["submitted"] = True
                                pending["submitted_at"] = datetime.now(timezone.utc).isoformat()
                                pending["order_response"] = order_result.get("payload", {})
                                pending["stop_order_id"] = None  # TODO: place stop order after fill
                                _save_json(PENDING_TRADE_PATH, pending)
                        except Exception as exec_err:
                            # Log error but don't crash the cycle
                            _save_json(ROOT / "state" / "active_crypto_last_execution.json", {
                                "executed": False,
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "error": str(exec_err),
                                "sent_to_conor": False,
                            })
                    else:
                        # executor not available - still a valid detection
                        pass
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


def run_loop(interval: float = 120.0):
    """Run continuous monitoring loop."""
    while True:
        start = time.time()
        result = _main_loop()
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        mids = result.get("mids", {}) or {}
        signal = result.get("active_signal")
        if signal:
            print(f"[{ts}] SIGNAL: {signal.get('direction')} on {signal.get('market','')}")
        elif mids:
            btc = mids.get("BIP-20DEC30-CDE","?")
            eth = mids.get("ETP-20DEC30-CDE","?")
            print(f"[{ts}] BTC={btc} ETH={eth}")
        elapsed = time.time() - start
        sleep_time = max(5.0, interval - elapsed)
        time.sleep(sleep_time)


if __name__ == "__main__":
    import sys
    if "--once" in sys.argv:
        print(json.dumps(run_once(), indent=2))
    elif "--loop" in sys.argv:
        run_loop(interval=30.0)
    else:
        print(json.dumps(run_once(), indent=2))
