import os
import kalshi_python
from datetime import datetime, timezone

KALSHI_API_KEY = os.getenv('KALSHI_API_KEY')

if not KALSHI_API_KEY:
    print("Error: KALSHI_API_KEY environment variable not set.")
    exit()

configuration = kalshi_python.Configuration(api_key={'Api_key': KALSHI_API_KEY})

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
        if value is None:
            return default
        val = float(value)
        if val > 1:
            val /= 100.0
        return val
    except (TypeError, ValueError):
        return default


def market_probability(market):
    for candidate in (market.last_price, market.yes_bid, market.yes_ask):
        value = safe_float(candidate)
        if value is not None:
            return value
    bid = safe_float(market.yes_bid)
    ask = safe_float(market.yes_ask)
    if bid is not None and ask is not None:
        return (bid + ask) / 2.0
    return None


def market_hours_to_close(market):
    close_ts = market.close_time
    if close_ts is None:
        return 999.0
    now = datetime.now(timezone.utc)
    if close_ts.tzinfo is None:
        close_ts = close_ts.replace(tzinfo=timezone.utc)
    return max((close_ts - now).total_seconds() / 3600.0, 0.0)


def text_relevance_classification(market):
    text = normalize_text(market.ticker, market.title, market.subtitle, market.event_ticker, market.series_ticker)
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


def evaluate_market(market):
    relevance = text_relevance_classification(market)
    probability = market_probability(market)
    hours_to_close = market_hours_to_close(market)
    title = market.title or ''
    volume = float(market.volume or 0)
    volume_24h = float(market.volume_24h or 0)

    if relevance == 'reject_hard':
        return {'accepted': False, 'reason': relevance, 'probability': probability, 'hours_to_close': hours_to_close}
    if probability is None:
        return {'accepted': False, 'reason': 'no_price_reference', 'probability': None, 'hours_to_close': hours_to_close}
    if hours_to_close > 168:
        return {'accepted': False, 'reason': 'too_far_to_resolution', 'probability': probability, 'hours_to_close': hours_to_close}
    if len(title) > 220:
        return {'accepted': False, 'reason': 'contract_too_complex', 'probability': probability, 'hours_to_close': hours_to_close}

    zone_key = detect_zone(probability)
    if zone_key is None:
        return {'accepted': False, 'reason': 'outside_target_price_zones', 'probability': probability, 'hours_to_close': hours_to_close}

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
        'volume_24h': volume_24h,
    }


def score_market(market, evaluation):
    probability = evaluation['probability']
    zone = ZONE_RULES[evaluation['zone_key']]
    center = (zone['low'] + zone['high']) / 2.0
    distance = abs(probability - center)
    relevance_bonus = 1 if evaluation['relevance'] == 'strict' else 0
    tier_bonus = 1 if evaluation['tier'] == 'higher_conviction' else 0
    return (
        tier_bonus,
        relevance_bonus,
        -distance,
        evaluation['volume_24h'],
        evaluation['volume'],
        -evaluation['hours_to_close'],
    )


def format_kalshi_market_as_ticket_message(market, evaluation):
    zone_label = ZONE_RULES[evaluation['zone_key']]['label']
    yes_bid = market.yes_bid if market.yes_bid is not None else 'N/A'
    yes_ask = market.yes_ask if market.yes_ask is not None else 'N/A'
    last_price = market.last_price if market.last_price is not None else 'N/A'
    tier = evaluation['tier']

    ticket = f"Kalshi {zone_label} Opportunity**\n"
    ticket += f" - Title: {market.title}\n"
    ticket += f" - Ticker: {market.ticker}\n"
    ticket += f" - Close Time: {market.close_time}\n"
    ticket += f" - Status: {market.status}\n"
    ticket += f" - Tier: {tier}\n"
    ticket += f" - Implied Probability: {evaluation['probability']:.2%}\n"
    ticket += f" - Last Price: {last_price}\n"
    ticket += f" - Yes Bid / Ask: {yes_bid} / {yes_ask}\n"
    ticket += f" - Volume: {market.volume or 0} | Volume 24h: {market.volume_24h or 0}\n"

    if evaluation['zone_key'] == 'delta_neutral':
        ticket += "\n*Thesis Hint: Near-even pricing with enough structure to justify a practice-grade catalyst scalp if the event/read is understandable.*\n"
        ticket += "*Action Hint: Use smaller size; require a concrete reason you think the market is misreading the event path.*\n"
    elif evaluation['zone_key'] == 'value_edge':
        ticket += "\n*Thesis Hint: Asymmetric payout zone where a modest edge can create attractive upside.*\n"
        ticket += "*Action Hint: Best used when contract wording is clean and the market looks meaningfully mispriced.*\n"
    else:
        ticket += "\n*Thesis Hint: High-probability yield candidate if the contract is clean and resolution logic is straightforward.*\n"
        ticket += "*Action Hint: Treat as yield harvesting only if you are comfortable with capped upside and binary downside.*\n"

    return ticket


def audit_line(market, evaluation):
    prob = evaluation.get('probability')
    prob_text = 'N/A' if prob is None else f'{prob:.2%}'
    return f" - {market.ticker} | {market.title[:120]} | reason={evaluation['reason']} | prob={prob_text} | hrs_to_close={evaluation.get('hours_to_close', 'N/A'):.1f}"


if __name__ == '__main__':
    print('DEBUG: Kalshi script started.')
    all_kalshi_ticket_messages = []
    rejected_samples = []

    with kalshi_python.ApiClient(configuration) as api_client:
        api_instance = kalshi_python.MarketsApi(api_client)

        try:
            response = api_instance.get_markets(status='open', limit=MARKET_LIMIT)
            markets = response.markets or []
            print(f'DEBUG: Retrieved {len(markets)} open markets from Kalshi.')

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
            print(f'DEBUG: {len(top_candidates)} accepted candidates survived practical filters.')

            for _, market, evaluation in top_candidates:
                ticket_message = format_kalshi_market_as_ticket_message(market, evaluation)
                all_kalshi_ticket_messages.append(ticket_message)

            if not top_candidates:
                print('No Kalshi tickets generated for this run.')
                print('No Trade: No Kalshi markets cleared the current practical edge filters.')
                print('AUDIT: rejection summary follows.')
                for reason, count in sorted(rejection_counts.items(), key=lambda x: (-x[1], x[0])):
                    print(f' - {reason}: {count}')
                if rejected_samples:
                    print('AUDIT: sample rejected markets')
                    for market, evaluation in rejected_samples:
                        print(audit_line(market, evaluation))

        except kalshi_python.ApiException as e:
            print(f'Error calling Kalshi API: {e}')
        except Exception as e:
            print(f'An unexpected error occurred: {e}')

    if all_kalshi_ticket_messages:
        print('---TICKET_START---')
        for msg in all_kalshi_ticket_messages:
            print(msg)
            print('---TICKET_DELIMITER---')
        print('---TICKET_END---')

    print('\nKalshi processing complete.')
