#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/catabolic_solutions/.openclaw/workspace/scripts')
from tradier_board_utils import parse_raw_tickets, score_ticket

def condense_ticket(ticket):
    fallback = ticket.get('expiry_fallback', False)
    fallback_mark = ' [fallback-expiry]' if fallback else ''
    line = (f"{ticket['strategy']}: {ticket['symbol']} {ticket['option_type'].upper()} | "
            f"Underlying {ticket.get('underlying_price', 0.0):.2f} | "
            f"Strike {ticket['strike']:.2f} | Exp {ticket['expiration']} | "
            f"{ticket['label']} | Δ {ticket.get('delta', 0.0):.4f} | "
            f"Bid/Ask {ticket.get('bid', 0.0):.2f}/{ticket.get('ask', 0.0):.2f}{fallback_mark}")
    return line

def main():
    # read board from stdin (or file)
    raw = sys.stdin.read()
    tickets = parse_raw_tickets(raw)
    if not tickets:
        print("BAZAAR OF FORTUNES — TRADIER LEADERS BOARD")
        print("VIX: N/A")
        print("\nDirectional / Scalping Leaders")
        print("No Trade")
        print("- No clean directional/scalping leader survived the current filters")
        print("- Best action: do not force momentum exposure here, wait for cleaner near-ATM structure and confirmation")
        print("\nPremium / Credit Leaders")
        print("No Trade")
        print("- No clean premium/credit leader survived the current filters")
        print("- Best action: wait for cleaner OTM structure and confirmation")
        return
    
    vix = tickets[0].get('vix', 'N/A')
    print(f"BAZAAR OF FORTUNES — TRADIER LEADERS BOARD")
    print(f"VIX: {vix}")
    
    # group by strategy
    from collections import defaultdict
    grouped = defaultdict(list)
    for t in tickets:
        grouped[t['strategy']].append(t)
    
    for strategy in ['Scalping Buy', 'Credit Spread Sell']:
        if strategy not in grouped:
            continue
        tickets_strat = grouped[strategy]
        tickets_strat.sort(key=score_ticket, reverse=True)
        pretty = 'Directional / Scalping Leaders' if strategy == 'Scalping Buy' else 'Premium / Credit Leaders'
        print(f"\n{pretty}")
        for idx, t in enumerate(tickets_strat[:5], 1):
            line = condense_ticket(t)
            print(f"{idx}. {line}")
            # add confidence and risk framing for first two only
            if idx <= 2:
                confidence = 7 if not t.get('expiry_fallback') else 5 if strategy == 'Scalping Buy' else 6
                conf_text = f"{confidence}/10"
                if t.get('expiry_fallback'):
                    conf_text += ', downgraded for fallback expiry'
                print(f"   Confidence: {conf_text}")
                risk = 'defined-risk only; avoid size creep' if strategy == 'Scalping Buy' else 'defined-risk only; do not overstay premium'
                print(f"   Risk framing: {risk}")
    
    # run notes
    fallback_count = sum(1 for t in tickets if t.get('expiry_fallback'))
    print(f"\nRun Notes")
    print(f"- Leaders emitted: {len(tickets)}")
    print(f"- Fallback-expiry leaders: {fallback_count}")
    if fallback_count:
        print("- Interpret fallback-expiry leaders as second-best structural representations, not literal requested-DTE matches")
    else:
        print("- All leaders matched requested expiry intent directly")
    
    # operator framing
    if any(t['strategy'] == 'Scalping Buy' for t in tickets):
        print("- Directional setups are present; only engage if momentum confirms and structure is clean")
    if any(t['strategy'] == 'Credit Spread Sell' for t in tickets):
        print("- Premium setups are present; treat as defined-risk spreads, not naked premium selling")
    if not tickets:
        print("- No Trade guidance: if entries require chasing, spreads widen, or vol regime shifts against entry, stand down.")

if __name__ == '__main__':
    main()