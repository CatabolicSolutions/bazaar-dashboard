#!/usr/bin/env python3
"""Patch runner.py and risk_config.json: 5-product tracking, max_positions=3."""
import subprocess, json

RUNNER = "/var/www/bazaar/active_crypto_sleeve/runner.py"
RISK = "/var/www/bazaar/active_crypto_sleeve/risk_config.json"

# ---- 1. Update risk_config.json ----
with open(RISK) as f:
    rc = json.load(f)
# max_positions cap removed per Conor: risk sizing handles aggregate exposure
rc.pop("max_positions", None)
with open("/tmp/risk_patched.json", "w") as f:
    json.dump(rc, f, indent=2)
cp = subprocess.run(["sudo", "cp", "/tmp/risk_patched.json", RISK], capture_output=True, timeout=10)
print(f"risk_config: rc={cp.returncode} max_positions=removed")

# ---- 2. Update runner.py ----
with open(RUNNER) as f:
    content = f.read()

edits = 0

# Edit 1: Add GOLD, SOL, MAG7C to mid fetch product filter
old_mid_fetch = '''        for pr in payload.get("products", []):
        pid = pr.get("product_id")
        if pid in ("BIP-20DEC30-CDE", "ETP-20DEC30-CDE"):
            mid = _float(pr.get("mid_market_price") or pr.get("price"))
            if mid:
                mids[pid] = mid'''

new_mid_fetch = '''        for pr in payload.get("products", []):
        pid = pr.get("product_id")
        if pid in ("BIP-20DEC30-CDE", "ETP-20DEC30-CDE", "GOL-27MAY26-CDE", "SLP-20DEC30-CDE", "MC-18JUN26-CDE"):
            mid = _float(pr.get("mid_market_price") or pr.get("price"))
            if mid:
                mids[pid] = mid'''

if old_mid_fetch in content:
    content = content.replace(old_mid_fetch, new_mid_fetch, 1)
    edits += 1
    print("Edit 1 OK: mid fetch - added GOLD, SOL, MAG7C")
else:
    print("Edit 1 FAIL: mid fetch block not found")

# Edit 2: Add GOLD, SOL, MAG7C to best_bid_ask fallback
old_fallback = '''        for pid in ("BIP-20DEC30-CDE", "ETP-20DEC30-CDE"):
            r = client.get("/best_bid_ask", {"product_ids": pid})'''

new_fallback = '''        for pid in ("BIP-20DEC30-CDE", "ETP-20DEC30-CDE", "GOL-27MAY26-CDE", "SLP-20DEC30-CDE", "MC-18JUN26-CDE"):
            r = client.get("/best_bid_ask", {"product_ids": pid})'''

if old_fallback in content:
    content = content.replace(old_fallback, new_fallback, 1)
    edits += 1
    print("Edit 2 OK: fallback - added GOLD, SOL, MAG7C")
else:
    print("Edit 2 FAIL: fallback block not found")

# Edit 3: Add GOLD, SOL, MAG7C to signal detection loop
old_signal_loop = '''        for pid, label in [("BIP-20DEC30-CDE", "BTC PERP"), ("ETP-20DEC30-CDE", "ETH PERP")]:
            mid = mids.get(pid)
            if not mid:
                continue
            candles = _fetch_candles(pid, "FIVE_MINUTE", 60)
            signal = _detect_sweep_reclaim_candles(pid, label, candles)
            if signal:
                signals.append(signal)'''

new_signal_loop = '''        for pid, label in [
            ("BIP-20DEC30-CDE", "BTC PERP"),
            ("ETP-20DEC30-CDE", "ETH PERP"),
            ("GOL-27MAY26-CDE", "GOLD FUT"),
            ("SLP-20DEC30-CDE", "SOL PERP"),
            ("MC-18JUN26-CDE", "MAG7C FUT"),
        ]:
            mid = mids.get(pid)
            if not mid:
                continue
            candles = _fetch_candles(pid, "FIVE_MINUTE", 60)
            signal = _detect_sweep_reclaim_candles(pid, label, candles)
            if signal:
                signals.append(signal)'''

if old_signal_loop in content:
    content = content.replace(old_signal_loop, new_signal_loop, 1)
    edits += 1
    print("Edit 3 OK: signal loop - added GOLD, SOL, MAG7C")
else:
    print("Edit 3 FAIL: signal loop not found")
    idx = content.find('for pid, label in')
    if idx >= 0:
        print(f"  Found at byte {idx}: {repr(content[idx:idx+150])}")

# Edit 4: Update heartbeat print
old_heartbeat = '''            btc = mids.get("BIP-20DEC30-CDE","?")
            eth = mids.get("ETP-20DEC30-CDE","?")
            print(f"[{ts}] BTC={btc} ETH={eth}")'''

new_heartbeat = '''            btc = mids.get("BIP-20DEC30-CDE","?")
            eth = mids.get("ETP-20DEC30-CDE","?")
            sol = mids.get("SLP-20DEC30-CDE","?")
            gold = mids.get("GOL-27MAY26-CDE","?")
            mag7 = mids.get("MC-18JUN26-CDE","?")
            print(f"[{ts}] BTC={btc} ETH={eth} SOL={sol} GOLD={gold} MAG7C={mag7}")'''

if old_heartbeat in content:
    content = content.replace(old_heartbeat, new_heartbeat, 1)
    edits += 1
    print("Edit 4 OK: heartbeat - added all 5 assets")
else:
    print("Edit 4 FAIL: heartbeat not found")
    idx = content.find('print(f"[{ts}] BTC=')
    if idx >= 0:
        print(f"  Found at byte {idx}: {repr(content[idx:idx+100])}")

# Write back
with open("/tmp/runner_patched.py", "w") as f:
    f.write(content)
cp = subprocess.run(["sudo", "cp", "/tmp/runner_patched.py", RUNNER], capture_output=True, timeout=10)
print(f"Write runner: rc={cp.returncode} stderr={cp.stderr.decode() if cp.stderr else 'none'}")

# Verify
with open(RUNNER) as f:
    final = f.read()
print(f"Runner: {len(final)} bytes, {final.count(chr(10))} lines")
for keyword in ["GOL-27MAY26", "SLP-20DEC30", "MC-18JUN26", "GOLD FUT", "SOL PERP", "MAG7C FUT"]:
    status = "OK" if keyword in final else "MISSING"
    print(f"  {keyword}: {status}")
