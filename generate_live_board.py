#!/usr/bin/env python3
"""Multi-symbol, multi-expiration options scan → ranked leaders board.
Scans 1-14 DTE across a broad symbol list, scores each option by edge,
writes ranked leaders + structured JSON for auto_trader consumption."""
import os, sys, json, math
from pathlib import Path
from datetime import datetime, timezone, date

ENV_FILES = [
    Path("/var/www/bazaar/.bazaar.env"),
    Path("/etc/default/bazaar-dashboard"),
]
for ENV in ENV_FILES:
    if not ENV.exists():
        continue
    for line in ENV.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"): continue
        if line.startswith("export "): line = line[7:]
        if "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("\"'").strip())

try:
    import requests
except ImportError:
    print("requests not available", file=sys.stderr); sys.exit(1)

K = os.getenv("TRADIER_API_KEY")
if not K: print("No API key", file=sys.stderr); sys.exit(1)
H = {"Authorization": "Bearer " + K, "Accept": "application/json"}
BASE = "https://api.tradier.com/v1/markets"

# ── Scan universe ──
TICKERS = [
    "SPY","QQQ","IWM","XLF","XLK","XLE","XLV",
    "AAPL","MSFT","NVDA","TSLA","AMZN","META","GOOGL",
    "GLD","TLT","JPM","V",
]
TICKERS = list(dict.fromkeys(TICKERS))
TICKERS = list(dict.fromkeys(TICKERS))  # dedup preserve order

MIN_BID = 0.05
MAX_SPREAD = 0.35
MIN_DTE = 1
MAX_DTE = 14
MAX_CANDIDATES = 100

OUT = Path("/var/www/bazaar/out")
LOG = Path("/var/www/bazaar/logs")
OUT.mkdir(parents=True, exist_ok=True)
LOG.mkdir(parents=True, exist_ok=True)
BOARD_FILE = OUT / "tradier_leaders_board.txt"
JSON_FILE = OUT / "leaders_ranked.json"

def log(m):
    ts = datetime.now(timezone.utc).isoformat()[:19]
    print("[" + ts + "] " + m, flush=True)

def get_json(url, params=None, timeout=10):
    try:
        r = requests.get(url, params=params, headers=H, timeout=timeout)
        if r.status_code == 200: return r.json()
    except: pass
    return None

def get_expirations(sym):
    """Get 1–14 DTE expirations for a symbol."""
    data = get_json(BASE + "/options/expirations", {"symbol": sym, "includeAllRoots": "true"})
    if not data: return []
    dates = data.get("expirations", {}).get("date", [])
    today = date.today()
    results = []
    for d in dates:
        dt = d if isinstance(d, str) else d.get("date", "")
        try:
            ed = datetime.strptime(dt, "%Y-%m-%d").date()
            dte = (ed - today).days
            if MIN_DTE <= dte <= MAX_DTE:
                results.append((dt, dte))
        except: pass
    return sorted(results, key=lambda x: x[1])

def get_quote(sym):
    data = get_json(BASE + "/quotes", {"symbols": sym})
    if not data: return None
    q = data.get("quotes", {}).get("quote", {})
    if not isinstance(q, dict): return None
    last = float(q.get("last") or 0)
    bid = float(q.get("bid") or 0)
    ask = float(q.get("ask") or 0)
    prev = float(q.get("prevclose") or 0)
    change = float(q.get("change_percentage") or 0)
    price = last or bid or ask or prev
    return {"price": price, "prevclose": prev, "change_pct": change, "vol": int(q.get("volume") or 0)}

def get_chain(sym, exp):
    data = get_json(BASE + "/options/chains", {"symbol": sym, "expiration": exp, "greeks": "false"}, timeout=15)
    if not data: return []
    opts = data.get("options", {}).get("option", [])
    return opts if isinstance(opts, list) else []

def edge_score(opt, price, exp_volume, sym_volume):
    """Compute edge score for an option candidate.
    Components: volume + OI + spread quality + elasticity (mid/bid) + premium + ATM proximity."""
    strike = float(opt.get("strike", 0))
    otype = (opt.get("option_type") or "").upper()
    bid = float(opt.get("bid") or 0)
    ask = float(opt.get("ask") or 0)
    vol = int(opt.get("volume") or 0)
    oi = int(opt.get("open_interest") or 0)

    if ask <= 0 or bid <= 0: return 0
    mid = (bid + ask) / 2
    spread = (ask - bid) / mid if mid > 0 else 999
    if spread > MAX_SPREAD: return 0
    if mid < 0.05: return 0
    if vol < 100: return 0

    # 1. Volume rank (0-25): relative to total symbol volume
    vol_pct = vol / max(exp_volume, 1)
    vol_score = min(vol_pct * 50, 25)

    # 2. Open interest (0-15): OI score
    oi_score = min(oi / 1000, 15)

    # 3. Spread quality (0-20): tight spread = higher score
    spread_score = max(0, 20 - spread * 60)

    # 4. OTM premium (0-20): reasonable premium is better
    # Too cheap (<0.10) = low edge, too expensive = budget issue
    if mid < 0.10:
        prem_score = mid * 200  # Up to 20
    else:
        prem_score = 20

    # 5. ATM proximity bonus (0-10): closer to ATM = more action
    dist = abs(strike - price)
    atm_score = max(0, 10 - dist * 0.5)

    # 6. Overall volume strength (0-10): raw vol bonus
    raw_vol = min(vol / 50000, 10)

    total = vol_score + oi_score + spread_score + prem_score + atm_score + raw_vol
    return round(total, 1)

def main():
    log("=== Multi-symbol leaders scan ===")
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    all_candidates = []
    scanned_count = 0
    total_api_calls = 0

    for sym in TICKERS:
        # Get quote first
        quote = get_quote(sym)
        if not quote:
            log("Skipping " + sym + " - no quote")
            continue
        total_api_calls += 1
        price = quote["price"]
        sym_vol = quote["vol"]

        # Expirations
        exps = get_expirations(sym)
        if not exps:
            continue

        for exp_date, dte in exps[:3]:  # Max 3 expiration dates per symbol to stay fast
            chain = get_chain(sym, exp_date)
            total_api_calls += 1
            if not chain:
                continue

            exp_total_vol = sum(int(o.get("volume") or 0) for o in chain)
            for opt in chain:
                otype = (opt.get("option_type") or "").upper()
                strike = float(opt.get("strike", 0))
                bid = float(opt.get("bid") or 0)
                ask = float(opt.get("ask") or 0)
                vol = int(opt.get("volume") or 0)
                oi = int(opt.get("open_interest") or 0)

                if bid <= 0 or ask <= 0:
                    continue
                mid = (bid + ask) / 2
                spread = (ask - bid) / mid
                if spread > MAX_SPREAD:
                    continue
                if mid < MIN_BID:
                    continue

                score = edge_score(opt, price, exp_total_vol, sym_vol)
                if score <= 0:
                    continue

                scanned_count += 1
                all_candidates.append({
                    "symbol": sym,
                    "strike": strike,
                    "option_type": otype,
                    "bid": round(bid, 2),
                    "ask": round(ask, 2),
                    "mid": round(mid, 3),
                    "volume": vol,
                    "open_interest": oi,
                    "spread": round(spread, 3),
                    "dte": dte,
                    "expiration": exp_date,
                    "score": score,
                    "price_at_scan": round(price, 2),
                })

    # Rank by score
    all_candidates.sort(key=lambda x: -x["score"])

    log("Scanned " + str(scanned_count) + " options across " + str(len(TICKERS)) + " symbols (" + str(total_api_calls) + " API calls)")
    log("Top candidate: " + str(all_candidates[0]) if all_candidates else "No candidates")

    # Top 10 for quick display
    top_display = all_candidates[:10]

    # ── Write ranked JSON for auto_trader ──
    output = {
        "scan_time": today_str,
        "total_scanned": scanned_count,
        "symbols_scanned": len(TICKERS),
        "api_calls": total_api_calls,
        "ranked_candidates": all_candidates[:MAX_CANDIDATES],
        "top_10": top_display,
    }
    JSON_FILE.write_text(json.dumps(output, indent=2))

    # ── Write human-readable board ──
    lines = ["Tradier Leaders Board (ranked by edge score)"]
    lines.append("Scan: " + today_str + " | " + str(scanned_count) + " options scanned")
    lines.append("")
    lines.append(f"{'Rank':<4} {'Symbol':<6} {'Strike':>8} {'Type':<6} {'Bid':>7} {'Ask':>7} {'Mid':>7} {'Vol':>7} {'OI':>7} {'DTE':<4} {'Expiry':<10} Score")
    lines.append("-" * 100)

    for i, c in enumerate(top_display):
        lines.append(
            f"{i+1:<4} {c['symbol']:<6} {c['strike']:>8.2f} {c['option_type']:<6} "
            f"{c['bid']:>7.2f} {c['ask']:>7.2f} {c['mid']:>7.3f} {c['volume']:>7} "
            f"{c['open_interest']:>7} {c['dte']:<4} {c['expiration']:<10} {c['score']}"
        )

    BOARD_FILE.write_text("\n".join(lines))
    log("Wrote " + str(min(MAX_CANDIDATES, len(all_candidates))) + " ranked candidates to " + str(JSON_FILE))
    log("Wrote top 10 to " + str(BOARD_FILE))

if __name__ == "__main__":
    main()
