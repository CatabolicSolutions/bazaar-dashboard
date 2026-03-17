import os
import kalshi_python
from datetime import datetime, timezone

KALSHI_API_KEY = os.getenv('KALSHI_API_KEY')

if not KALSHI_API_KEY:
    print("Error: KALSHI_API_KEY environment variable not set.")
    exit()

configuration = kalshi_python.Configuration(api_key={'Api_key': KALSHI_API_KEY})

MARKET_LIMIT = 100
MAX_LEADERS_PER_ZONE = 3
FINANCE_KEYWORDS = [
    's&p', 'spx', 'nasdaq', 'ndx', 'qqq', 'russell', 'iwm', 'dow', 'vix',
    'fed', 'fomc', 'rate', 'rates', 'cpi', 'inflation', 'jobs', 'payrolls',
    'unemployment', 'gdp', 'treasury', 'oil', 'gold', 'bitcoin', 'btc', 'eth',
    'earnings', 'nvda', 'aapl', 'tsla', 'nvidia', 'apple', 'tesla'
]
REJECT_KEYWORDS = [
    'nba', 'nfl', 'mlb', 'nhl', 'soccer', 'tennis', 'golf', 'march madness',
    'duke', 'lakers', 'knicks', 'cavaliers', 'points scored', 'wins by over',
    'rebounds', 'assists', 'player', 'championship', 'sport', 'sports'
]
ZONE_RULES = {
    'delta_neutral': {'low': 0.45, 'high': 0.55, 'label': 'Delta-Neutral Zone'},
    'value_edge': {'low': 0.20, 'high': 0.35, 'label': 'Value Edge Zone'},
    'safe_yield': {'low': 0.85, 'high': 0.99, 'label': 'Safe Yield Zone'},
}


def normalize_text(*parts):
    return ' '.join((p or '') for p in parts).lower()


def is_finance_relevant_market(market):
    text = normalize_text(market.ticker, market.title, market.subtitle, market.event_ticker, market.series_ticker)
    if any(keyword in text for keyword in REJECT_KEYWORDS):
        return False
    return any(keyword in text for keyword in FINANCE_KEYWORDS)


def market_probability(market):
    for candidate in (market.last_price, market.yes_bid, market.yes_ask):
        if candidate is not None:
            value = float(candidate)
            if value > 1:
                value = value / 100.0
            return value

    if market.yes_bid is not None and market.yes_ask is not None:
        bid = float(market.yes_bid)
        ask = float(market.yes_ask)
        if bid > 1:
            bid /= 100.0
        if ask > 1:
            ask /= 100.0
        return (bid + ask) / 2.0

    return None


def detect_zone(probability):
    if probability is None:
        return None
    for key, rule in ZONE_RULES.items():
        if rule['low'] <= probability <= rule['high']:
            return key
    return None


def score_market(market, probability, zone_key):
    zone = ZONE_RULES[zone_key]
    center = (zone['low'] + zone['high']) / 2.0
    distance = abs(probability - center)
    volume = float(market.volume or 0)
    volume_24h = float(market.volume_24h or 0)
    close_ts = market.close_time
    hours_to_close = 999.0
    if close_ts is not None:
        now = datetime.now(timezone.utc)
        if close_ts.tzinfo is None:
            close_ts = close_ts.replace(tzinfo=timezone.utc)
        hours_to_close = max((close_ts - now).total_seconds() / 3600.0, 0.0)
    return (
        -distance,
        volume_24h,
        volume,
        -hours_to_close,
    )


def format_kalshi_market_as_ticket_message(market, probability, zone_key):
    zone_label = ZONE_RULES[zone_key]['label']
    yes_bid = market.yes_bid if market.yes_bid is not None else 'N/A'
    yes_ask = market.yes_ask if market.yes_ask is not None else 'N/A'
    last_price = market.last_price if market.last_price is not None else 'N/A'

    ticket = f"Kalshi {zone_label} Opportunity**\n"
    ticket += f" - Title: {market.title}\n"
    ticket += f" - Ticker: {market.ticker}\n"
    ticket += f" - Close Time: {market.close_time}\n"
    ticket += f" - Status: {market.status}\n"
    ticket += f" - Implied Probability: {probability:.2%}\n"
    ticket += f" - Last Price: {last_price}\n"
    ticket += f" - Yes Bid / Ask: {yes_bid} / {yes_ask}\n"
    ticket += f" - Volume: {market.volume or 0} | Volume 24h: {market.volume_24h or 0}\n"

    if zone_key == 'delta_neutral':
        ticket += "\n*Thesis Hint: Near-even pricing; best used for fast information edge / news scalp, not passive conviction.*\n"
        ticket += "*Action Hint: Only engage when you have a real catalyst edge and a clear exit plan.*\n"
    elif zone_key == 'value_edge':
        ticket += "\n*Thesis Hint: Asymmetric payout zone if external data suggests market underpricing.*\n"
        ticket += "*Action Hint: Use only when supporting macro/market context creates a clear edge.*\n"
    elif zone_key == 'safe_yield':
        ticket += "\n*Thesis Hint: High-probability pricing may support yield harvesting, but only if mispricing is genuinely present.*\n"
        ticket += "*Action Hint: Treat as capped-yield risk trade, not free money.*\n"

    return ticket


if __name__ == '__main__':
    print('DEBUG: Kalshi script started.')
    all_kalshi_ticket_messages = []

    with kalshi_python.ApiClient(configuration) as api_client:
        api_instance = kalshi_python.MarketsApi(api_client)

        try:
            response = api_instance.get_markets(status='open', limit=MARKET_LIMIT)
            markets = response.markets or []
            print(f'DEBUG: Retrieved {len(markets)} open markets from Kalshi.')

            relevant_markets = [market for market in markets if is_finance_relevant_market(market)]
            print(f'DEBUG: {len(relevant_markets)} finance/event-relevant markets survived keyword filtering.')

            zone_buckets = {key: [] for key in ZONE_RULES}
            for market in relevant_markets:
                probability = market_probability(market)
                zone_key = detect_zone(probability)
                if probability is None or zone_key is None:
                    continue
                zone_buckets[zone_key].append((score_market(market, probability, zone_key), market, probability))

            total_candidates = 0
            for zone_key, candidates in zone_buckets.items():
                candidates.sort(reverse=True, key=lambda x: x[0])
                top_candidates = candidates[:MAX_LEADERS_PER_ZONE]
                total_candidates += len(top_candidates)
                for _, market, probability in top_candidates:
                    ticket_message = format_kalshi_market_as_ticket_message(market, probability, zone_key)
                    all_kalshi_ticket_messages.append(ticket_message)

            if total_candidates == 0:
                print('No Kalshi tickets generated for this run.')
                print('No Trade: No finance/event-relevant Kalshi markets met the current zone and pricing criteria.')

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
