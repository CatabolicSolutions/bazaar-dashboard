import os
import requests
import json

# Retrieve the API key from environment variables
KALSHI_API_KEY = os.getenv('KALSHI_API_KEY')

if not KALSHI_API_KEY:
    print("Error: KALSHI_API_KEY environment variable not set.")
    exit()

# Define the Kalshi API endpoint for listing markets
# We'll fetch a small number of active markets for this test
url = 'https://kalshi.com/api/v1/markets' # Kalshi's public API endpoint
headers = {
    'Accept': 'application/json'
}
params = {'status': 'active', 'limit': 5} # Fetch 5 active markets

print("Attempting to fetch active markets from Kalshi...")

try:
    response = requests.get(url, params=params, headers=headers)
    response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)

    data = response.json()
    print("Kalshi API Response (first 5 active markets):")
    print(json.dumps(data, indent=2)) # Pretty print the JSON response

    if data and 'markets' in data and data['markets']:
        print(f"\nSuccessfully fetched {len(data['markets'])} active markets from Kalshi.")
        for i, market in enumerate(data['markets']):
            print(f" Market {i+1}: {market.get('title')} (ID: {market.get('id')})")
    else:
        print("No active markets found or API call might be successful but no data.")

except requests.exceptions.RequestException as e:
    print(f"Error making API request: {e}")
except json.JSONDecodeError:
    print("Error: Could not decode JSON response from Kalshi API.")
except Exception as e:
    print(f"An unexpected error occurred: {e}")

