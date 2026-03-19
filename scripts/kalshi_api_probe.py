import os
import kalshi_python
from pprint import pprint

TICKER = 'KXMVECROSSCATEGORY-S2026034B67BFCB5-64D12F63E68'
configuration = kalshi_python.Configuration(api_key={'Api_key': os.getenv('KALSHI_API_KEY')})
with kalshi_python.ApiClient(configuration) as api_client:
    markets = kalshi_python.MarketsApi(api_client)
    events = kalshi_python.EventsApi(api_client)

    print('=== get_market ===')
    try:
        market = markets.get_market(TICKER).market
        pprint(market.to_dict() if hasattr(market, 'to_dict') else market.__dict__)
        event_ticker = market.event_ticker
    except Exception as e:
        print('get_market ERR', repr(e))
        event_ticker = None

    print('=== get_market_orderbook ===')
    try:
        ob = markets.get_market_orderbook(TICKER)
        pprint(ob.to_dict() if hasattr(ob, 'to_dict') else ob)
    except Exception as e:
        print('orderbook ERR', repr(e))

    print('=== get_trades ===')
    try:
        trades = markets.get_trades(ticker=TICKER, limit=10)
        pprint(trades.to_dict() if hasattr(trades, 'to_dict') else trades)
    except Exception as e:
        print('trades ERR', repr(e))

    if event_ticker:
        print('=== get_event ===')
        try:
            ev = events.get_event(event_ticker)
            pprint(ev.to_dict() if hasattr(ev, 'to_dict') else ev)
        except Exception as e:
            print('event ERR', repr(e))
        print('=== get_event_metadata ===')
        try:
            meta = events.get_event_metadata(event_ticker)
            pprint(meta.to_dict() if hasattr(meta, 'to_dict') else meta)
        except Exception as e:
            print('event_metadata ERR', repr(e))
