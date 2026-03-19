import os
import kalshi_python

configuration = kalshi_python.Configuration(api_key={"Api_key": os.getenv("KALSHI_API_KEY")})
with kalshi_python.ApiClient(configuration) as api_client:
    api = kalshi_python.MarketsApi(api_client)
    resp = api.get_markets(status="open", limit=40)
    for m in resp.markets or []:
        print(f"{m.ticker} | EVENT={m.event_ticker} | SERIES={m.series_ticker} | TITLE={m.title}")
