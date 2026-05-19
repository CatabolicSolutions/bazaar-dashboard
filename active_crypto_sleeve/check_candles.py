import sys, json
sys.path.insert(0, "/var/www/bazaar")
from active_crypto_sleeve.coinbase_client import CoinbaseAdvancedClient
client = CoinbaseAdvancedClient.from_env()

for g in ["ONE_MINUTE", "FIVE_MINUTE", "FIFTEEN_MINUTE", "ONE_HOUR"]:
    r = client.get("/products/BIP-20DEC30-CDE/candles", {"granularity": g})
    candles = ((r.get("payload") or {}).get("candles", [])) if r.get("ok") else []
    print("  %s: %d candles, ok=%s" % (g, len(candles), r.get("ok")))
    if candles:
        first = candles[0]
        last = candles[-1]
        print("    First: start=%s L=%s H=%s O=%s C=%s V=%s" % (first.get("start"), first.get("low"), first.get("high"), first.get("open"), first.get("close"), first.get("volume")))
        print("    Last:  start=%s L=%s H=%s O=%s C=%s V=%s" % (last.get("start"), last.get("low"), last.get("high"), last.get("open"), last.get("close"), last.get("volume")))
