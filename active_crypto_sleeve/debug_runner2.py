import sys, json
sys.path.insert(0, "/var/www/bazaar")
sys.path.insert(0, "/var/www/bazaar/active_crypto_sleeve")
from active_crypto_sleeve.runner import _fetch_mids, _fetch_candle_samples

mids = _fetch_mids()
print("MIDS:", mids)

candles = _fetch_candle_samples("BIP-20DEC30-CDE", 30, "FIVE_MINUTE")
print("BTC candles count:", len(candles))
if candles:
    print("First candle keys:", list(candles[0].keys()))
    print("Sample:", json.dumps(candles[0], indent=2)[:300])
