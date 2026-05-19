#!/usr/bin/env python3
"""
Live trade journal – logs all trades from Tradier & Bloc.
"""
import json, os, datetime

JOURNAL_PATH = "/var/www/bazaar/logs/trade_journal.jsonl"

def log_trade(system, symbol, side, quantity, price, pnl=None, notes=""):
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "system": system,  # "tradier" or "bloc"
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "price": price,
        "pnl": pnl,
        "notes": notes
    }
    with open(JOURNAL_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")