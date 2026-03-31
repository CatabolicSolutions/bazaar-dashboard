import os
import requests
import json
from datetime import datetime, date, timedelta

# Retrieve the API key from environment variables
TRADIER_API_KEY = os.getenv('TRADIER_API_KEY')

if not TRADIER_API_KEY:
    print("Error: TRADIER_API_KEY environment variable not set.")
    exit()

# Configuration for Tradier API
BASE_URL = 'https://api.tradier.com/v1/markets/'
HEADERS = {
    'Accept': 'application/json',
    'Authorization': f'Bearer {TRADIER_API_KEY}'
}

# --- Symbols and DTE from Alfred's Tradier Strategy ---
SYMBOLS = [
    "SPX", "SPY", "NDX", "QQQ", "NVDA", "TSLA",
    "XSP", "IWM", "VIX", "AMD", "AAPL"
]
TARGET_DTE = [0, 1] # 0DTE and 1DTE


def get_option_chain(symbol, expiration_date):
    """Fetches option chain for a given symbol and expiration date from Tradier."""
    url = f"{BASE_URL}options/chains"
    params = {'symbol': symbol, 'expiration': expiration_date.strftime('%Y-%m-%d')}
    try:
        response = requests.get(url, params=params, headers=HEADERS)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching option chain for {symbol} on {expiration_date.strftime('%Y-%m-%d')}: {e}")
        return None

def find_closest_expirations(today, dte_target):
    """Finds the expiration date closest to today + dte_target days."""
    target_date = today + timedelta(days=dte_target)
    
    # Tradier API usually returns expiries for the next ~60 days.
    # For this test, let's just use the target date directly.
    # In a real scenario, we'd fetch all expiries and find the closest one.
    return [target_date.strftime('%Y-%m-%d')] # Return as a list for consistency


if __name__ == "__main__":
    today = date.today()
    
    for symbol in SYMBOLS:
        print(f"\n--- Processing {symbol} ---")
        for dte in TARGET_DTE:
            expirations = find_closest_expirations(today, dte)
            for exp_date_str in expirations:
                print(f" Fetching option chain for {symbol}, DTE: {dte} (Expiry: {exp_date_str})...")
                chain_data = get_option_chain(symbol, datetime.strptime(exp_date_str, '%Y-%m-%d').date())
                
                if chain_data and chain_data.get('options') and chain_data['options'].get('option'):
                    print(f" Found {len(chain_data['options']['option'])} options for {symbol} on {exp_date_str}.")
                    # In a real scenario, we would process these options for strategy.
                    # For this test, let's just print a summary.
                    calls = [opt for opt in chain_data['options']['option'] if opt['option_type'] == 'call']
                    puts = [opt for opt in chain_data['options']['option'] if opt['option_type'] == 'put']
                    print(f" Calls: {len(calls)}, Puts: {len(puts)}")
                    # Example: print first few strikes
                    if calls: print(f" Example Call Strikes: {[c['strike'] for c in calls[:3]]}")
                    if puts: print(f" Example Put Strikes: {[p['strike'] for p in puts[:3]]}")
                else:
                    print(f" No options data found for {symbol} on {exp_date_str}.")
print("\nTradier options chain fetching complete.")
