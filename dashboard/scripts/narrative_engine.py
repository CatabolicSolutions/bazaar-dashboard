#!/usr/bin/env python3
"""
Trade Narrative Engine v1.0
Generates trade setup narrative from leader data and price action
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

# Add scripts to path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))


def calculate_atr(prices, period=14):
    """Calculate Average True Range from price data"""
    if len(prices) < period + 1:
        return prices[-1] * 0.02  # Default 2% if not enough data
    
    true_ranges = []
    for i in range(1, min(period + 1, len(prices))):
        high = prices[i]['high'] if 'high' in prices[i] else prices[i]['close']
        low = prices[i]['low'] if 'low' in prices[i] else prices[i]['close']
        prev_close = prices[i-1]['close']
        
        tr1 = high - low
        tr2 = abs(high - prev_close)
        tr3 = abs(low - prev_close)
        true_ranges.append(max(tr1, tr2, tr3))
    
    return sum(true_ranges) / len(true_ranges) if true_ranges else prices[-1] * 0.02


def classify_setup(price_data, leader):
    """Classify the trade setup type"""
    if not price_data or len(price_data) < 2:
        return "Momentum"  # Default
    
    prices = [p['close'] for p in price_data if 'close' in p]
    if len(prices) < 2:
        return "Momentum"
    
    current = prices[-1]
    previous = prices[0]
    change_pct = ((current - previous) / previous) * 100
    
    # Gap detection
    if abs(change_pct) > 2:
        return "Gap and Go" if change_pct > 0 else "Gap Fade"
    
    # Breakout detection (simplified - would need highs/lows)
    if change_pct > 1:
        return "Breakout"
    elif change_pct < -1:
        return "Pullback"
    
    return "Momentum"


def generate_narrative(symbol, leader, price_data=None):
    """Generate complete trade narrative"""
    
    # Extract data from leader
    underlying = float(leader.get('underlying', 0))
    strike = float(leader.get('strike', 0))
    option_type = leader.get('option_type', 'CALL').upper()
    delta = float(leader.get('delta', 0.5))
    bid = float(leader.get('bid', 0))
    ask = float(leader.get('ask', 0))
    
    # Entry price (use ask for calls, bid for premium estimate)
    entry_price = ask if ask > 0 else (bid + 0.01)
    
    # Calculate ATR for stop placement
    atr = calculate_atr(price_data) if price_data else underlying * 0.02
    
    # Determine setup type
    setup = classify_setup(price_data, leader)
    
    # Directional bias
    is_bullish = option_type == 'CALL' and delta > 0
    
    # Calculate stops and targets based on setup
    if is_bullish:
        # For calls: stop below support, target 2:1 RR
        stop_price = underlying - (atr * 1.5)
        risk = underlying - stop_price
        target_price = underlying + (risk * 2)
        
        # Invalidation - break below stop or momentum fails
        invalidation = f"Price breaks below ${stop_price:.2f} or momentum stalls with volume drop"
        
        # Trigger
        trigger = f"Break above ${underlying:.2f} with volume confirmation"
        
    else:
        # For puts: stop above resistance, target 2:1 RR
        stop_price = underlying + (atr * 1.5)
        risk = stop_price - underlying
        target_price = underlying - (risk * 2)
        
        # Invalidation
        invalidation = f"Price breaks above ${stop_price:.2f} or selling pressure exhausts"
        
        # Trigger
        trigger = f"Break below ${underlying:.2f} with volume confirmation"
    
    # Position sizing ($100-200 risk per trade)
    max_risk_dollars = 150  # Middle of $100-200 range
    option_contract_cost = entry_price * 100  # Per contract
    max_contracts = int(max_risk_dollars / (entry_price * 100)) or 1
    suggested_contracts = min(max_contracts, 5)  # Cap at 5
    position_value = suggested_contracts * option_contract_cost
    
    # Risk:Reward ratio
    rr_ratio = 2.0  # Targeting 1:2
    
    # Confidence score (1-10)
    confidence = 7  # Default, would be enhanced with more data
    if leader.get('confidence'):
        try:
            conf_str = leader['confidence'].split('/')[0]
            confidence = int(conf_str)
        except:
            pass
    
    # Timeframe classification
    dte = leader.get('exp', '').split('-')
    if len(dte) == 3:
        try:
            from datetime import datetime
            exp_date = datetime(int(dte[0]), int(dte[1]), int(dte[2]))
            now = datetime.now()
            days_to_exp = (exp_date - now).days
            timeframe = "Day Trade" if days_to_exp <= 7 else "Swing"
        except:
            timeframe = "Swing"
    else:
        timeframe = "Swing"
    
    narrative = {
        "symbol": symbol,
        "setup": setup,
        "direction": "Bullish" if is_bullish else "Bearish",
        "trigger": trigger,
        "entry": {
            "price": round(entry_price, 2),
            "underlying": round(underlying, 2),
            "contract": f"{symbol} {strike} {option_type}"
        },
        "stop": {
            "price": round(stop_price, 2),
            "distance": round(abs(underlying - stop_price), 2)
        },
        "target": {
            "price": round(target_price, 2),
            "distance": round(abs(target_price - underlying), 2)
        },
        "invalidation": invalidation,
        "timeframe": timeframe,
        "confidence": confidence,
        "position_sizing": {
            "max_risk": max_risk_dollars,
            "suggested_contracts": suggested_contracts,
            "position_value": round(position_value, 2),
            "per_contract_cost": round(option_contract_cost, 2)
        },
        "risk_reward": {
            "ratio": f"1:{int(rr_ratio)}",
            "risk_amount": round(abs(underlying - stop_price) * suggested_contracts * 100, 2),
            "reward_amount": round(abs(target_price - underlying) * suggested_contracts * 100, 2)
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    return narrative


def main():
    """CLI for testing"""
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: narrative_engine.py <symbol> [leader_json]"}))
        sys.exit(1)
    
    symbol = sys.argv[1]
    
    # Default leader for testing
    leader = {
        "symbol": symbol,
        "option_type": "CALL",
        "strike": "520",
        "underlying": "518.50",
        "delta": "0.60",
        "bid": "2.50",
        "ask": "2.60",
        "exp": "2026-04-17",
        "confidence": "7/10"
    }
    
    # Override with provided leader data
    if len(sys.argv) > 2:
        try:
            leader = json.loads(sys.argv[2])
        except:
            pass
    
    narrative = generate_narrative(symbol, leader)
    print(json.dumps(narrative, indent=2))


if __name__ == "__main__":
    main()
