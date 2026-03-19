import os
import kalshi_python
from pprint import pprint

TARGETS = [
    'KXMVECROSSCATEGORY-S2026034B67BFCB5-64D12F63E68',
    'KXMVESPORTSMULTIGAMEEXTENDED-S2026F380E7D42B2-C49B04E57CF',
]

configuration = kalshi_python.Configuration(api_key={'Api_key': os.getenv('KALSHI_API_KEY')})
with kalshi_python.ApiClient(configuration) as api_client:
    api = kalshi_python.MarketsApi(api_client)
    for ticker in TARGETS:
        print('===', ticker, '===')
        try:
            resp = api.get_market(ticker)
            market = resp.market
            print(type(market))
            data = market.to_dict() if hasattr(market, 'to_dict') else market.__dict__
            pprint(data)
        except Exception as e:
            print('ERR', repr(e))
