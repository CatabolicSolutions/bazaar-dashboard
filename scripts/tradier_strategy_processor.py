import os
import requests
import json
from datetime import datetime, date, timedelta
import subprocess # NEW IMPORT
import shlex # RE-IMPORT FOR SHELL QUOTING

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
# --- Discord Configuration ---
# IMPORTANT: Replace 'YOUR_DISCORD_CHANNEL_ID_HERE' with the actual ID of your Discord channel.
# To get the Channel ID: In Discord, enable Developer Mode (User Settings -> Advanced -> Developer Mode).
# Then right-click on the channel and select "Copy ID".
DISCORD_CHANNEL_ID = "1483025184775733319"

def send_discord_message(message_content, channel_id=DISCORD_CHANNEL_ID):
    """Sends a message to the specified Discord channel using OpenClaw's message tool."""
    try:
        # Construct the full OpenClaw command as a single string for shell=True execution.
        # This is the most reliable way to ensure the message content is passed correctly to the CLI parser.
        
        # Ensure message_content is and channel_id are safely quoted for the shell
        escaped_channel_id = shlex.quote(channel_id)
        escaped_message_content = shlex.quote(message_content)
        
        full_command_string = (
            f'openclaw message action send '
            f'target {escaped_channel_id} ' # Directly quote channel_id
            f'message {escaped_message_content}' # Directly quote message_content
        )
        
        # Execute the command using subprocess.run with shell=True
        # This relies on the shell to parse the arguements correctly for OpenClaw
        result = subprocess.run(full_command_string, shell=True, capture_output=True, text=True, check=True)
        
        # Execute the command using subprocess.run with shell=True
        # This relies on the shell to correctly parse the full command string for OpenClaw.
        
        print(f"Discord message command executed. Stdout: {result.stdout.strip()}, Stderr: {result.stderr.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error executing Discord message command: {e}. Stderr: {e.stderr.strip()}")
        return False
    except Exception as e:
        # This catches Python-level errors (e.g., shlex not found, subprocess issues)
        print(f"Error preparing or executing Discord message: {e}")
        return False
        

# --- Symbols and DTE from Alfred's Tradier Strategy ---
SYMBOLS = [
    "SPX", "SPY", "NDX", "QQQ", "NVDA", "TSLA",
    "XSP", "IWM", "VIX", "AMD", "AAPL"
]
TARGET_DTE = [0, 1] # 0DTE and 1DTE


def get_underlying_quote(symbol):
    """Fetches the current quote for the underlying symbol."""
    url = f"{BASE_URL}quotes"
    params = {'symbols': symbol, 'greeks': 'false'} # No greeks needed for just last price
    try:
        response = requests.get(url, params=params, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        if data and 'quotes' in data and data['quotes'] and data['quotes']['quote']:
            return data['quotes']['quote']['last']
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching quote for {symbol}: {e}")
        return None

def get_option_chain(symbol, expiration_date):
    """Fetches option chain for a given symbol and expiration date from Tradier."""
    url = f"{BASE_URL}options/chains"
    params = {'symbol': symbol, 'expiration': expiration_date.strftime('%Y-%m-%d'), 'greeks': 'true'} # Need greeks for Delta later
    try:
        response = requests.get(url, params=params, headers=HEADERS)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching option chain for {symbol} on {expiration_date.strftime('%Y-%m-%d')}: {e}")
        return None

def get_all_expirations(symbol):
    """Fetches all available expiration dates for a given symbol from Tradier."""
    url = f"{BASE_URL}options/expirations"
    params = {'symbol': symbol}
    try:
        response = requests.get(url, params=params, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        if data and 'expirations' in data and data['expirations'] and data['expirations'].get('date'):
            return data['expirations']['date'] # Returns a list of date strings
            return []
    except requests.exceptions.RequestException as e:
        print(f"Error fetching expirations for {symbol}: {e}")
        return []

def get_vix_quote():
    """Fetches the current quote for VIX."""
    url = f"{BASE_URL}quotes"
    params = {'symbols': 'VIX', 'greeks': 'false'}
    try:
        response = requests.get(url, params=params, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        if data and 'quotes' in data and data['quotes'] and data['quotes']['quote']:
            return data['quotes']['quote']['last']
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching VIX quote: {e}")
        return None

def find_closest_expirations(symbol, today, dte_target):
    """Finds the expiration date closest to today + dte_target days from available expirations."""
    available_exp_strs = get_all_expirations(symbol)
    if not available_exp_strs:
        return []

    available_exp_dates = []
    for exp_str in available_exp_strs:
        try:
            exp_date = datetime.strptime(exp_str, '%Y-%m-%d').date()
            if exp_date >= today: # Only consider future or today's expirations
                available_exp_dates.append(exp_date)
        except ValueError:
            continue # Skip malformed dates

    if not available_exp_dates:
        return []

    closest_exp = None
    min_days_diff = float('inf')

    for exp_date in available_exp_dates:
        days_diff = (exp_date - today).days
        # We are looking for DTE = 0 or DTE = 1
        if dte_target == 0 and days_diff == 0: # Exactly today's expiration
            return [exp_date.strftime('%Y-%m-%d')]
        elif dte_target == 1 and days_diff == 1: # Exactly tomorrow's expiration
            return [exp_date.strftime('%Y-%m-%d')]
        
        # If not exact match, find the closest valid future expiration
        if days_diff >= dte_target and abs(days_diff - dte_target) < min_days_diff:
            min_days_diff = abs(days_diff - dte_target)
            closest_exp = exp_date

    if closest_exp:
        return [closest_exp.strftime('%Y-%m-%d')]
    return []

def process_options_for_strategy(underlying_price, options_data, current_vix, strategy_type="scalping_buy", dte_value=0):
    """Applies strategy filters to options data."""
    filtered_options = []
    if not options_data or not options_data.get('options') or not options_data['options'].get('option'):
        return filtered_options

def format_option_as_ticket_message(symbol, dte, option_data, strategy_type, underlying_price, current_vix, is_fallback=False):
    """Formats an individual option into a human-readable ticket message."""
    ticket = f"**{strategy_type.replace('_', ' ').title()} Opportunity for {symbol} ({dte}DTE)**\n"
    ticket += f" - Underlying Price: ${underlying_price:.2f}\n"
    ticket += f" - Current Vix: {current_vix}\n"
    ticket += f" - Type: {option_data['option_type'].upper()}\n"
    ticket += f" - Strike: ${option_data['strike']:.2f}\n"
    ticket += f" - Expiration: {option_data['expiration_date']}\n"
    ticket += f" - Last Price: ${option_data['last'] if option_data['last'] is not None else 'N/A'}\n"
    ticket += f" - Bid: ${option_data['bid']:.2f} / Ask: ${option_data['ask']:.2f}\n"
    
    delta = option_data['greeks']['delta'] if 'greeks' in option_data and 'delta' in option_data['greeks'] else 'N/A'
    ticket += f" - Delta: {delta:.4f}\n" if isinstance(delta, (int, float)) else f" - Delta: {delta} \n"
    # Placeholder for more detailed thesis/invalidation/target logic
    if strategy_type == "scalping_buy":
        ticket += f"*Action Hint: Consider entering if clear directional momentum confirms, with tight stops.*\n"
    elif strategy_type == "credit_spread_sell":
        ticket += f"\n*Thesis Hint: High probability of expiring worthless. Income generation play.*\n"
        ticket += f"*Action Hint: Consider selling this OTM option as part of a spread if market outlook is stable.*\n"

    return ticket
    # Placeholder for Vix integration
    print(f" [Strategy Processor] Current VIX: {current_vix}. (Logic to adjust based on VIX will go here).")

    options = options_data['options']['option']

    # --- Strategy: Scalping (Buying Calls/Puts) ---
    # Criteria: ATM strikes for 0DTE, Slightly ITM for 1DTE
    if strategy_type == "scalping_buy":
        for opt in options:
            # Calculate difference to underlying
            price_diff = abs(opt['strike'] - underlying_price)

            # ATM/Slightly ITM logic for buying
            if dte_value == 0: # 0DTE - ATM
                # Define "ATM" as within a small range of underlying price
                # For SPX/NDX, this range might need to be wider
                if price_diff < underlying_price * 0.005: # e.g., within 0.5% of underlying
                    filtered_options.append(opt)
            elif dte_value == 1: # 1DTE - Slightly ITM
                # Define "Slightly ITM" based on price or delta (more precise)
                # For simplicity in this first pass, let's define as strike < price for Calls, strike > price for Puts
                # A better way would be using Delta, e.g., 0.60-0.75 for ITM
                if (opt['option_type'] == 'call' and opt['strike'] < underlying_price) or \
                (opt['option_type'] == 'put' and opt['strike'] > underlying_price):
                    if price_diff < underlying_price * 0.05: # within 5% for 'slightly'
                        filtered_options.append(opt)

    # --- Future Strategy: Credit Spreads (Selling OTM) ---
    # Criteria: 0.10 to 0.20 Delta range
    elif strategy_type == "credit_spread_sell":
        for opt in options:
            if 'greeks' in opt and 'delta' in opt['greeks']:
                delta = abs(opt['greeks']['delta']) # Use absolute delta for calls/puts
                # For credit spreads, we sell options with 0.10 to 0.20 Delta
                # This means it's OTM and has a high probability of expiring worthless.
                if 0.10 <= delta <= 0.20:
                    filtered_options.append(opt)

    return filtered_options


if __name__ == "__main__":
    today = date.today()
    
    # Fetch current Vix once
    current_vix = get_vix_quote()
    if current_vix is None:
        print("Error: Could not fetch VIX quote. Exiting.")
        exit()
    print(f"\n--- Current VIX: {current_vix} ---")

    for symbol in SYMBOLS:
        print(f"\n--- Processing {symbol} ---")
        underlying_price = get_underlying_quote(symbol)
        if not underlying_price:
            print(f" Could not fetch underlying price for {symbol}. Skipping.")
            continue
            print(f" Underlying price for {symbol}: {underlying_price}")

        for dte in TARGET_DTE:
            expirations = find_closest_expirations(symbol, today, dte)
            for exp_date_str in expirations:
                print(f" Fetching option chain for {symbol}, DTE: {dte} (Expiry: {exp_date_str})...")
                chain_data = get_option_chain(symbol, datetime.strptime(exp_date_str, '%Y-%m-%d').date())
                
                if chain_data:
                    all_ticket_messages = []
                    
                    # --- Process for Scalping Buy strategy ---
                    print(f" Applying 'scalping_buy' strategy for {symbol} on {exp_date_str} (DTE {dte})...")
                    filtered_options_buy = process_options_for_strategy(underlying_price, chain_data, current_vix, "scalping_buy", dte)
                    
                    if filtered_options_buy:
                        print(f" Found {len(filtered_options_buy)} STRICT matching options for scalping_buy. Formatting tickets...")
                        for opt in filtered_options_buy:
                            ticket = format_option_as_ticket_message(symbol, dte, opt, "scalping_buy", underlying_price, current_vix, is_fallback=False)
                            all_ticket_messages.append(ticket)
                    else:
                        print(f" No STRICT matching options found for scalping_buy. Generating fallback candidates...")
                        # Fallback: Find 3 nearest ATM options to propose as candidates
                        candidate_options = []
                        if chain_data.get('options') and chain_data['options'].get('option'):
                            options_sorted_by_atm = sorted(chain_data['options']['option'], key=lambda x: abs(x['strike'] - underlying_price))
                            candidate_options = options_sorted_by_atm[:3] # Get 3 nearest ATM
                        
                        if candidate_options:
                            for opt in candidate_options:
                                # Ensure it's a call or put to avoid weird types
                                if opt['option_type'] in ['call', 'put']:
                                    ticket = format_option_as_ticket_message(symbol, dte, opt, "scalping_buy", underlying_price, current_vix, is_fallback=True)
                                    all_ticket_messages.append(ticket)
                        else:
                            print(f" No fallback candidates found for scalping_buy.")


                    # --- Process for Credit Spread Sell strategy ---
                    print(f" Applying 'credit_spread_sell' strategy for {symbol} on {exp_date_str} (DTE {dte})...")
                    filtered_options_sell = process_options_for_strategy(underlying_price, chain_data, current_vix, "credit_spread_sell", dte)

                    if filtered_options_sell:
                        print(f" Found {len(filtered_options_sell)} Strict matching options for credit_spread_sell. Formatting tickets...")
                        for opt in filtered_options_sell:
                            ticket = format_option_as_ticket_message(symbol, dte, opt, "credit_spread_sell", underlying_price, current_vix, is_fallback=Fallback)
                            all_ticket_messages.append(ticket)
                    else:
                        print(f" No STRICT matching options found for credit_spread_sell. Generating fallback candidates...")
                        # Fallback: Find 3 OTM options with Delta between 0.05 and 0.25 to propose
                        candidates_options = []
                        if chain_data.get('options') and chain_data['options'].get('option'):
                            otm_candidates = [
                                opt for opt in chain_data['options']['option']
                                if 'greeks' in opt and 'delta' in opt['greeks'] and
                                0.05 <= abs(opt['greeks']['delta']) <= 0.25
                                ]
                            # Sort by delta for consistency and take up to 3
                            candidate_options = sorted(otm_candidates, key=lambda x: abs(x['greeks']['delta']))[:3]
                        
                        if candidate_options:
                            for opt in candidate_options:
                                if opt['option_type'] in ['call', 'put']:
                                    ticket = format_option_as_ticket_message(symbol, dte, opt, "credit_spread_sell", underlying_price, current_vix, is_fallback=True)
                                    all_ticket_messages.append(ticket)
                        else:
                            print(f" No fallback candidates found for credit_spread_sell.")

                    # Send all collected ticket messages to Discord
                    if all_ticket_messages:
                        print("\n --- Sending Generated Tickets to Discord ---")
                        for msg in all_ticket_messages:
                            send_discord_message(msg)
                        print(" --------------------------")
                    else:
                        print(" No tickets generated for this symbol/DTE.")
                else:
                    print(f" No options data to process for {symbol} on {exp_date_str}.")

print("\nTradier options processing complete.")

