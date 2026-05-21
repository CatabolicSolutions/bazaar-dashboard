#!/usr/bin/env python3
"""Update runner with optimized params: 0.5% stop, 1:2.5 R:R targets."""
import subprocess, json

RUNNER = "/var/www/bazaar/active_crypto_sleeve/runner.py"
RISK = "/var/www/bazaar/active_crypto_sleeve/risk_config.json"

# Update risk_config
with open(RISK) as f:
    rc = json.load(f)
rc["stop_pct"] = 0.5
rc["rr_target"] = 2.5
rc["max_risk_per_trade_pct"] = 0.75
rc["max_position_size_leverage"] = 3.0
# max_positions cap removed per Conor: risk sizing handles aggregate exposure
rc.pop("max_positions", None)
rc["max_daily_loss"] = 500
with open("/tmp/risk_opt.json", "w") as f:
    json.dump(rc, f, indent=2)
subprocess.run(["sudo", "cp", "/tmp/risk_opt.json", RISK], timeout=10)
print("risk_config updated")

# Read runner.py
with open(RUNNER) as f:
    content = f.read()

# LONG targets: replace swing_low * 1.005 / 1.01 with R:R based targets
# For LONG: stop_distance = entry - (swing_low * 0.995)
# target_1 = entry + (stop_distance * 1.0)  (1:1)
# target_2 = entry + (stop_distance * 2.5)  (1:2.5)
old_long = '''                "target_1": f"{swing_low * 1.005:,.2f}", "target_2": f"{swing_low * 1.01:,.2f}",
                    "direction": "LONG",
                }'''

new_long = '''                "target_1": f"{entry + (entry - swing_low * 0.995) * 1.0:,.2f}", "target_2": f"{entry + (entry - swing_low * 0.995) * 2.5:,.2f}",
                    "direction": "LONG",
                }'''

count = content.count(old_long)
print("LONG target block found: " + str(count) + " times")
content = content.replace(old_long, new_long)

# SHORT targets: replace swing_high * 0.995 / 0.99 with R:R based targets
old_short = '''                "target_1": f"{swing_high * 0.995:,.2f}", "target_2": f"{swing_high * 0.99:,.2f}",
                    "direction": "SHORT",
                }'''

new_short = '''                "target_1": f"{entry - (swing_high * 1.005 - entry) * 1.0:,.2f}", "target_2": f"{entry - (swing_high * 1.005 - entry) * 2.5:,.2f}",
                    "direction": "SHORT",
                }'''

count2 = content.count(old_short)
print("SHORT target block found: " + str(count2) + " times")
content = content.replace(old_short, new_short)

# Write back
with open("/tmp/runner_opt.py", "w") as f:
    f.write(content)
subprocess.run(["sudo", "cp", "/tmp/runner_opt.py", RUNNER], timeout=10)
print("runner.py updated")

# Verify
with open(RUNNER) as f:
    final = f.read()
print("1.0 target in runner: " + str("* 1.0" in final))
print("2.5 target in runner: " + str("* 2.5" in final))
print("Line count: " + str(len(final.split(chr(10)))))
