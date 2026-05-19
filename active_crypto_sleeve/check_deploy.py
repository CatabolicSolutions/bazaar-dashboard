import json, sys, os
from pathlib import Path
sys.path.insert(0, "/var/www/bazaar")

def load(p):
    path = Path(p)
    if path.exists():
        try:
            return json.loads(path.read_text())
        except:
            pass
    return None

h = load("/var/www/bazaar/state/active_crypto_runner_heartbeat.json")
print("HEARTBEAT ok=%s mids=%s" % (h.get("ok"), h.get("mids")))
print("NOTE:", str(h.get("note", ""))[:80])
e = load("/var/www/bazaar/state/active_crypto_last_execution.json")
if e:
    print("EXEC NOTIFICATION:", json.dumps(e, indent=2)[:400])
else:
    print("No execution notification")
