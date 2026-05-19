"""Debug: test mid fetching and sweep detection."""
import sys, json
sys.path.insert(0, "/var/www/bazaar")
from active_crypto_sleeve.coinbase_client import CoinbaseAdvancedClient

client = CoinbaseAdvancedClient.from_env()

for pid in ["BIP-20DEC30-CDE", "ETP-20DEC30-CDE"]:
    r = client.get("/best_bid_ask", {"product_ids": pid})
    print(f"PID={pid} ok={r.get('ok')} status={r.get('status_code')}")
    if r.get("ok"):
        p = r.get("payload", {}) or {}
        print(f"  keys={list(p.keys())}")
        prods = p.get("products", [])
        for pr in prods:
            print(f"  bid={pr.get('best_bid')} ask={pr.get('best_ask')} price={pr.get('price')}")
    else:
        print(f"  err={r.get('payload', {})}")

# Also try product endpoint for price
r2 = client.get("/products", {"product_type": "FUTURE"})
if r2.get("ok"):
    payload = r2.get("payload", {}) or {}
    prods = payload.get("products", [])
    for pr in prods:
        pid = pr.get("product_id")
        if pid in ("BIP-20DEC30-CDE", "ETP-20DEC30-CDE"):
            print(f"PRODUCT {pid}: price={pr.get('price')} mid={pr.get('mid_market_price')} bid={pr.get('best_bid_price')} ask={pr.get('best_ask_price')}")
else:
    print(f"product err={r2.get('payload',{})}")
