import os
import kalshi_python

configuration = kalshi_python.Configuration(api_key={"Api_key": os.getenv("KALSHI_API_KEY")})
keywords = [
    "S&P", "Nasdaq", "Fed", "CPI", "inflation", "jobs", "GDP", "unemployment",
    "Treasury", "oil", "gold", "bitcoin", "BTC", "ETH", "Dow", "Russell", "VIX",
    "rate", "FOMC", "earnings", "NVDA", "AAPL", "TSLA", "SPX", "QQQ", "IWM"
]

with kalshi_python.ApiClient(configuration) as api_client:
    api = kalshi_python.MarketsApi(api_client)
    cursor = None
    found = []
    total = 0

    for _ in range(12):
        resp = api.get_markets(status="open", limit=100, cursor=cursor)
        markets = resp.markets or []
        total += len(markets)
        for m in markets:
            text = ' '.join([
                m.ticker or '',
                m.title or '',
                m.subtitle or '',
                m.event_ticker or '',
                m.series_ticker or '',
            ])
            if any(k.lower() in text.lower() for k in keywords):
                found.append(m)
        cursor = getattr(resp, 'cursor', None)
        if not cursor:
            break

    print('TOTAL_SCANNED', total)
    print('FOUND', len(found))
    for m in found[:120]:
        print('---')
        print(m.ticker)
        print('EVENT', m.event_ticker, 'SERIES', m.series_ticker)
        print(m.title)
        if m.subtitle:
            print('SUB', m.subtitle)
        print('CLOSE', m.close_time, 'LAST', m.last_price, 'YB', m.yes_bid, 'YA', m.yes_ask, 'NB', m.no_bid, 'NA', m.no_ask)
