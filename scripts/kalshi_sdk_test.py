import os
import kalshi_python
import json
from datetime import datetime, date
def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError ("Type %s not serializable" % type(obj))


# Retrieve the API key from environment variables
KALSHI_API_KEY = os.getenv('KALSHI_API_KEY')

if not KALSHI_API_KEY:
    print("Error: KALSHI_API_KEY environment variable not set.")
    exit()

# Configure API client
configuration = kalshi_python.Configuration(
    api_key={'Api_key': KALSHI_API_KEY}
)

# Create an instance of the API class
with kalshi_python.ApiClient(configuration) as api_client:
    api_instance = kalshi_python.MarketsApi(api_client)

    try:
        # Fetch up to 5 active markets using the SDK
        # The SDK handles authentication and API calls internally
        response = api_instance.get_markets(status="open", limit=5)
        

        if response.markets:
            print(f"\nSuccessfully fetched {len(response.markets)} active markets from Kalshi using the SDK.")
            for i, market in enumerate(response.markets):
                print(f" Market {i+1}: {market.title} (ID: {market.ticker})")
        else:
            print("No active markets found or API call might be successful but no data.")

    except kalshi_python.ApiException as e:
        print(f"Error calling Kalshi API: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

