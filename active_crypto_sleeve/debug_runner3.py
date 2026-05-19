import sys, json
sys.path.insert(0, "/var/www/bazaar")
from active_crypto_sleeve.coinbase_client import CoinbaseAdvancedClient

client = CoinbaseAdvancedClient.from_env()

print("=== best_bid_ask for BIP ===")
bb = client.get("/best_bid_ask", {"product_ids": "BIP-20DEC30-CDE"})
print("ok:", bb.get("ok"), "status:", bb.get("status_code"))
print(json.dumps(bb.get("payload", {}), indent=2)[:1000])

print()
print("=== candles for BIP ===")
cc = client.get("/candles", {"product_id": "BIP-20DEC30-CDE", "granularity": "FIVE_MINUTE"})
print("ok:", cc.get("ok"), "status:", cc.get("status_code"))
print(json.dumps(cc.get("payload", {}), indent=2)[:1000])
