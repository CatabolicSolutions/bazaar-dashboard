import os
import requests
import json

# Retrieve the API key from environment variables
TRADIER_API_KEY = os.getenv('TRADIER_API_KEY')

if not TRADIER_API_KEY:
    print("Error: TRADIER_API_KEY environment variable not set.")
    exit()

# Define the Tradier API endpoint for a quote
# We'll use a well-known symbol like SPY for this test
url = 'https://api.tradier.com/v1/markets/quotes'
headers = {
'Accept': 'application/json',
'Authorization': f'Bearer {TRADIER_API_KEY}'
}
params = {'symbols': 'SPY'}

print("Attempting to fetch SPY quote from Tradier...")

try:
    response = requests.get(url, params=params, headers=headers)
    response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)

    data = response.json()
    print("Tradier API Response:")
    print(json.dumps(data, indent=2)) # Pretty print the JSON response

    if data and 'quotes' in data and data['quotes'] and data['quotes']['quote']:
        quote = data['quotes']['quote']
        print(f"\nSuccessfully fetched quote for {quote['symbol']}:")
        print(f" Last Price: {quote['last']}")
        print(f" Bid: {quote['bid']}")
        print(f" Ask: {quote['ask']}")
    else:
        print("No quote data found for SPY. API call might be successful but no data.")

except requests.exceptions.RequestException as e:
    print(f"Error making API request: {e}")
except json.JSONDecodeError:
    print("Error: Could not decode JSON response from Tradier API.")
except Exception as e:
    print(f"An unexpected error occurred: {e}")
