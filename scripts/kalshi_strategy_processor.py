import os
from datetime import datetime, timezone
import requests

KALSHI_API_KEY = os.getenv('KALSHI_API_KEY')

if not KALSHI_API_KEY:
    print("Error: KALSHI_API_KEY environment variable not set.")
    exit()

BASE_URL = 'https://api.elections.kalshi.com/trade-api/v2'
HEADERS = {'Authorization': KALSHI_API_KEY}
MARKET_LIMIT = 100
MAX_LEADERS_TOTAL = 5
AUDIT_SAMPLE_SIZE = 8
STRICT_KEYWORDS = [
    's&p', 'spx', 'nasdaq', 'ndx', 'qqq', 'russell', 'iwm', 'dow', 'vix',
    'fed', 'fomc', 'rate', 'rates', 'cpi', 'inflation', 'jobs', 'payrolls',
    'unemployment', 'gdp', 'treasury', 'oil', 'gold', 'earnings', 'nvda',
    'aapl', 'tsla', 'nvidia', 'apple', 'tesla'
]
SOFT_ALLOW_KEYWORDS = [
    'bitcoin', 'btc', 'eth', 'crypto', 'election', 'policy', 'tariff', 'recession',
    'close between', 'close above', 'close below', 'price of', 'index', 'stocks',
    'market', 'economy', 'yield', 'volatility', 'claims', 'beat estimates', 'raise rates'
]
HARD_REJECT_KEYWORDS = [
    'rebounds', 'assists', 'touchdowns', 'goals scored', 'points scored', 'wins by over',
    'player', 'parlay', 'same game', 'multi game', 'multi-leg'
]
SPORTS_CONTEXT_KEYWORDS = [
    'nba', 'nfl', 'mlb', 'nhl', 'soccer', 'tennis', 'golf', 'march madness', 'duke', 'lakers',
    'knicks', 'cavaliers', 'arsenal', 'chelsea', 'barcelona', 'hurricanes', 'islanders', 'sharks'
]
ZONE_RULES = {
    'delta_neutral': {'low': 0.40, 'high': 0.60, 'label': 'Delta-Neutral Zone'},
    'value_edge': {'low': 0.15, 'high': 0.40, 'label': 'Value Edge Zone'},
    'safe_yield': {'low': 0.80, 'high': 0.97, 'label': 'Safe Yield Zone'},
}


def normalize_text(*parts):
    return ' '.join((p or '') for p in parts).lower()


def safe_float(value, default=None):
    try:
        if value is None or value == '':
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def fetch_open_markets(limit=MARKET_LIMIT):
    r = requests.get(f'{BASE_URL}/markets', headers=HEADERS, params={'status': 'open', 'limit': limit}, timeout=30)
    r.raise_for_status()
    return r.json().get('markets', [])


def market_probability(market):
    for field in ('last_price_dollars', 'yes_ask_dollars', 'yes_bid_dollars'):
        val = safe_float(market.get(field))
        if val is not None:
            return val
    yb = safe_float(market.get('yes_bid_dollars'))
    ya = safe_float(market.get('yes_ask_dollars'))
    if yb is not None and ya is not None:
        return (yb + ya) / 2.0
    return None


def market_hours_to_close(market):
    close_str = market.get('close_time') or market.get('expiration_time')
    if not close_str:
        return 999.0
    try:
        close_ts = datetime.fromisoformat(close_str.replace('Z', '+00:00'))
    except Exception:
        return 999.0
    now = datetime.now(timezone.utc)
    return max((close_ts - now).total_seconds() / 3600.0, 0.0)


def text_relevance_classification(market):
    text = normalize_text(market.get('ticker'), market.get('title'), market.get('subtitle'), market.get('event_ticker'), market.get('series_ticker'))
    if any(keyword in text for keyword in HARD_REJECT_KEYWORDS):
        return 'reject_hard'
    if any(keyword in text for keyword in STRICT_KEYWORDS):
        return 'strict'
    if any(keyword in text for keyword in SOFT_ALLOW_KEYWORDS):
        return 'soft'
    if any(keyword in text for keyword in SPORTS_CONTEXT_KEYWORDS):
        return 'sports_context'
    return 'unknown'


def detect_zone(probability):
    if probability is None:
        return None
    for key, rule in ZONE_RULES.items():
        if rule['low'] <= probability <= rule['high']:
            return key
    return None


def complexity_score(market):
    title = market.get('title') or ''
    comma_count = title.count(',')
    custom_strike = market.get('custom_strike') or {}
    legs = custom_strike.get('Associated Markets', '') if isinstance(custom_strike, dict) else ''
    leg_count = len([x for x in str(legs).split(',') if x]) if legs else 0
    return max(comma_count + 1, leg_count if leg_count else 1)


def evaluate_market(market):
    relevance = text_relevance_classification(market)
    probability = market_probability(market)
    hours_to_close = market_hours_to_close(market)
    volume = safe_float(market.get('volume_dollars'), 0.0) or 0.0
    liquidity = safe_float(market.get('liquidity_dollars'), 0.0) or 0.0
    complexity = complexity_score(market)

    if relevance == 'reject_hard':
        return {'accepted': False, 'reason': 'reject_hard', 'probability': probability, 'hours_to_close': hours_to_close}
    if probability is None:
        return {'accepted': False, 'reason': 'no_probability_reference', 'probability': None, 'hours_to_close': hours_to_close}
    if hours_to_close > 168:
        return {'accepted': False, 'reason': 'too_far_to_resolution', 'probability': probability, 'hours_to_close': hours_to_close}
    if complexity > 6:
        return {'accepted': False, 'reason': 'contract_too_complex', 'probability': probability, 'hours_to_close': hours_to_close}

    zone_key = detect_zone(probability)
    if zone_key is None:
        return {'accepted': False, 'reason': 'outside_target_probability_zones', 'probability': probability, 'hours_to_close': hours_to_close}

    tier = 'practice'
    if relevance == 'strict' and zone_key in ('value_edge', 'safe_yield'):
        tier = 'higher_conviction'

    return {
        'accepted': True,
        'reason': 'accepted',
        'relevance': relevance,
        'zone_key': zone_key,
        'tier': tier,
        'probability': probability,
        'hours_to_close': hours_to_close,
        'volume': volume,
        'liquidity': liquidity,
        'complexity': complexity,
    }


def score_market(market, evaluation):
    probability = evaluation['probability']
    zone = ZONE_RULES[evaluation['zone_key']]
    center = (zone['low'] + zone['high']) / 2.0
    distance = abs(probability - center)
    relevance_bonus = 1 if evaluation['relevance'] == 'strict' else 0
    tier_bonus = 1 if evaluation['tier'] == 'higher_conviction' else 0
    sports_penalty = -1 if evaluation['relevance'] == 'sports_context' else 0
    return (
        tier_bonus,
        relevance_bonus,
        sports_penalty,
        -distance,
        evaluation['liquidity'],
        evaluation['volume'],
        -evaluation['hours_to_close'],
        -evaluation['complexity'],
    )


def format_kalshi_market_as_ticket_message(market, evaluation):
    zone_label = ZONE_RULES[evaluation['zone_key']]['label']
    ticket = f"Kalshi {zone_label} Opportunity**\n"
    ticket += f" - Title: {market.get('title')}\n"
    ticket += f" - Ticker: {market.get('ticker')}\n"
    ticket += f" - Event Ticker: {market.get('event_ticker')}\n"
    ticket += f" - Close Time: {market.get('close_time')}\n"
    ticket += f" - Status: {market.get('status')}\n"
    ticket += f" - Tier: {evaluation['tier']}\n"
    ticket += f" - Implied Probability: {evaluation['probability']:.2%}\n"
    ticket += f" - Yes Bid / Ask ($): {market.get('yes_bid_dollars', 'N/A')} / {market.get('yes_ask_dollars', 'N/A')}\n"
    ticket += f" - Last Price ($): {market.get('last_price_dollars', 'N/A')}\n"
    ticket += f" - Liquidity ($): {market.get('liquidity_dollars', '0.0000')}\n"
    ticket += f" - Complexity Score: {evaluation['complexity']}\n"
    if evaluation['zone_key'] == 'delta_neutral':
        ticket += "\n*Thesis Hint: Near-even implied probability; requires a catalyst or information edge.*\n"
        ticket += "*Action Hint: Practice-grade only unless you have a concrete fair-probability reason.*\n"
    elif evaluation['zone_key'] == 'value_edge':
        ticket += "\n*Thesis Hint: Better asymmetry zone for a probability-first long candidate.*\n"
        ticket += "*Action Hint: Preferred if contract is simple and the market estimate looks stale.*\n"
    else:
        ticket += "\n*Thesis Hint: High-probability yield zone; capped upside, binary downside.*\n"
        ticket += "*Action Hint: Only engage if settlement logic is clean and overconfidence risk is understood.*\n"
    return ticket


def audit_line(market, evaluation):
    prob = evaluation.get('probability')
    prob_text = 'N/A' if prob is None else f'{prob:.2%}'
    return f" - {market.get('ticker')} | {str(market.get('title', ''))[:120]} | reason={evaluation['reason']} | prob={prob_text} | hrs_to_close={evaluation.get('hours_to_close', 'N/A'):.1f}"


if __name__ == '__main__':
    print('DEBUG: Kalshi probability-first raw-api script started.')
    all_kalshi_ticket_messages = []
    rejected_samples = []
    try:
        markets = fetch_open_markets()
        print(f'DEBUG: Retrieved {len(markets)} open markets from Kalshi raw API.')
        accepted = []
        rejection_counts = {}
        for market in markets:
            evaluation = evaluate_market(market)
            if evaluation['accepted']:
                accepted.append((score_market(market, evaluation), market, evaluation))
            else:
                reason = evaluation['reason']
                rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
                if len(rejected_samples) < AUDIT_SAMPLE_SIZE:
                    rejected_samples.append((market, evaluation))
        accepted.sort(reverse=True, key=lambda x: x[0])
        top_candidates = accepted[:MAX_LEADERS_TOTAL]
        print(f'DEBUG: {len(top_candidates)} accepted candidates survived probability-first practical filters.')
        for _, market, evaluation in top_candidates:
            all_kalshi_ticket_messages.append(format_kalshi_market_as_ticket_message(market, evaluation))
        if not top_candidates:
            print('No Kalshi tickets generated for this run.')
            print('No Trade: No Kalshi markets cleared the current probability-first practical filters.')
            print('AUDIT: rejection summary follows.')
            for reason, count in sorted(rejection_counts.items(), key=lambda x: (-x[1], x[0])):
                print(f' - {reason}: {count}')
            if rejected_samples:
                print('AUDIT: sample rejected markets')
                for market, evaluation in rejected_samples:
                    print(audit_line(market, evaluation))
    except requests.RequestException as e:
        print(f'Error calling Kalshi raw API: {e}')
    except Exception as e:
        print(f'An unexpected error occurred: {e}')

    if all_kalshi_ticket_messages:
        print('---TICKET_START---')
        for msg in all_kalshi_ticket_messages:
            print(msg)
            print('---TICKET_DELIMITER---')
        print('---TICKET_END---')

    print('\nKalshi processing complete.')
