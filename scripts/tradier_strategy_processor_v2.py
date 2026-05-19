import os
import requests
from datetime import datetime, date

TRADIER_API_KEY = os.getenv('TRADIER_API_KEY')

if not TRADIER_API_KEY:
    print("Error: TRADIER_API_KEY environment variable not set.")
    exit()

BASE_URL = 'https://api.tradier.com/v1/markets/'
HEADERS = {
    'Accept': 'application/json',
    'Authorization': f'Bearer {TRADIER_API_KEY}'
}

SYMBOLS = [
    "SPX", "SPY", "NDX", "QQQ", "NVDA", "TSLA",
    "XSP", "IWM", "VIX", "AMD", "AAPL"
]
TARGET_DTE = [7, 14]

MAX_SCALPING_TICKETS_PER_SYMBOL_DTE = 1
MAX_CREDIT_TICKETS_PER_SYMBOL_DTE = 1
FALLBACK_TICKETS_PER_SYMBOL_DTE = 1
MIN_BID = 0.05
MAX_BID_ASK_SPREAD_RATIO = 0.35
SCALPING_DELTA_RANGES = {
    0: (0.35, 0.65),
    1: (0.50, 0.80),
}
CREDIT_DELTA_RANGE = (0.10, 0.18)
SCALPING_DISTANCE_LIMITS = {0: 0.005, 1: 0.05}
SCALPING_MIN_STRUCTURE_SCORE = 55.0
CREDIT_MIN_STRUCTURE_SCORE = 52.0


def clamp(value, low, high):
    return max(low, min(high, value))


def score_liquidity(option_data):
    spread_ratio = get_spread_ratio(option_data)
    bid = safe_float(option_data.get('bid'), 0.0)
    ask = safe_float(option_data.get('ask'), 0.0)
    mid = get_mid_price(option_data) or 0.0
    if spread_ratio is None or mid <= 0:
        return 0.0
    spread_score = max(0.0, 20.0 - min(spread_ratio, 1.0) * 60.0)
    premium_score = min(mid * 1.2, 12.0)
    sided_size_bonus = min(max(bid, 0.0), 8.0)
    return round(spread_score + premium_score + sided_size_bonus, 2)


def score_expiry_quality(selection_meta):
    requested = int(selection_meta.get('requested_dte') or 0)
    actual = int(selection_meta.get('actual_dte') or requested)
    fallback_penalty = 12.0 if selection_meta.get('is_fallback') else 0.0
    drift_penalty = max(0, actual - requested) * 3.0
    score = max(0.0, 20.0 - fallback_penalty - drift_penalty)
    return round(score, 2)


def directional_bias_text(option_type):
    return 'bullish' if option_type == 'call' else 'bearish'


def compute_candidate_analytics(symbol, option_data, underlying_price, current_vix, strategy_type, dte_value, selection_meta, is_fallback=False):
    delta = abs(get_delta(option_data) or 0.0)
    spread_ratio = get_spread_ratio(option_data)
    mid = get_mid_price(option_data) or 0.0
    dist_pct = distance_pct(option_data, underlying_price)
    option_type = option_data.get('option_type')
    strike = safe_float(option_data.get('strike'), 0.0)

    if spread_ratio is None or dist_pct is None or mid <= 0 or option_type not in ('call', 'put'):
        return None

    liquidity_score = score_liquidity(option_data)
    expiry_score = score_expiry_quality(selection_meta)
    vix_value = safe_float(current_vix, 0.0) or 0.0
    vix_regime = 'calm' if vix_value < 16 else 'normal' if vix_value < 24 else 'elevated'

    if strategy_type == 'scalping_buy':
        target_low, target_high = SCALPING_DELTA_RANGES[dte_value]
        target_delta = (target_low + target_high) / 2.0
        delta_fit_score = max(0.0, 20.0 - abs(delta - target_delta) * 90.0)
        distance_score = max(0.0, 18.0 - dist_pct * 260.0)
        structure_score = round(liquidity_score + expiry_score + delta_fit_score + distance_score, 2)
        threshold = SCALPING_MIN_STRUCTURE_SCORE
        setup_family = 'directional_momentum'
        narrative = f"{symbol} {option_type.upper()} is a liquid {selection_meta['label']} directional candidate with {directional_bias_text(option_type)} exposure and near-target delta efficiency."
        expectations = 'Use only when the underlying confirms continuation and tape quality supports a fast directional expression.'
        invalidation = 'Reject or exit if continuation fails, spread quality widens materially, or the move stalls after entry.'
        risk_profile = 'defined-risk premium outlay; size for quick confirmation failure rather than thesis perfection'
    else:
        target_delta = sum(CREDIT_DELTA_RANGE) / 2.0
        delta_fit_score = max(0.0, 20.0 - abs(delta - target_delta) * 180.0)
        distance_score = max(0.0, 16.0 - abs(dist_pct - 0.03) * 220.0)
        structure_score = round(liquidity_score + expiry_score + delta_fit_score + distance_score, 2)
        threshold = CREDIT_MIN_STRUCTURE_SCORE
        setup_family = 'defined_risk_premium'
        narrative = f"{symbol} {option_type.upper()} sits in the preferred short-premium delta band with cleaner pricing and distance than the broader chain."
        expectations = 'Use only inside a defined-risk spread when the underlying is stable-to-favorable and the volatility regime is not disorderly.'
        invalidation = 'Reject if volatility expands against the structure, fill quality degrades, or the defined-risk profile stops making sense.'
        risk_profile = 'defined-risk spread only; no naked premium and no chasing weak credits'

    confidence_score = int(clamp(round((structure_score - 35.0) / 6.0), 1, 10))
    no_trade = structure_score < threshold
    return {
        'symbol': symbol,
        'strategy_type': strategy_type,
        'setup_family': setup_family,
        'underlying_price': underlying_price,
        'current_vix': current_vix,
        'vix_regime': vix_regime,
        'option_type': option_type,
        'strike': strike,
        'delta_abs': round(delta, 4),
        'mid_price': round(mid, 4),
        'spread_ratio': round(spread_ratio, 4),
        'distance_pct': round(dist_pct, 4),
        'liquidity_score': liquidity_score,
        'expiry_quality_score': expiry_score,
        'delta_fit_score': round(delta_fit_score, 2),
        'distance_score': round(distance_score, 2),
        'structure_score': structure_score,
        'confidence_score': confidence_score,
        'narrative': narrative,
        'expectations': expectations,
        'invalidation': invalidation,
        'risk_profile': risk_profile,
        'selection_label': selection_meta.get('label'),
        'requested_dte': selection_meta.get('requested_dte'),
        'actual_dte': selection_meta.get('actual_dte'),
        'is_fallback': bool(is_fallback or selection_meta.get('is_fallback')),
        'no_trade': no_trade,
        'threshold': threshold,
        'reason_selected': 'passes structure threshold and ranks favorably within current filtered set' if not no_trade else 'below minimum structure threshold',
    }


def candidate_sort_key(analytics):
    return (
        analytics['structure_score'],
        analytics['liquidity_score'],
        analytics['delta_fit_score'],
        analytics['distance_score'],
        -analytics['actual_dte'],
        0 if analytics['is_fallback'] else 1,
    )


def get_underlying_quote(symbol):
    """Fetches the current quote for the underlying symbol."""
    url = f"{BASE_URL}quotes"
    params = {'symbols': symbol, 'greeks': 'false'}
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
    params = {'symbol': symbol, 'expiration': expiration_date.strftime('%Y-%m-%d'), 'greeks': 'true'}
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
            return data['expirations']['date']
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


def get_expiration_selection(symbol, today, dte_target):
    """Returns expiration metadata without lying about DTE labels."""
    available_exp_strs = get_all_expirations(symbol)
    if not available_exp_strs:
        return None

    available_exp_dates = []
    for exp_str in available_exp_strs:
        try:
            exp_date = datetime.strptime(exp_str, '%Y-%m-%d').date()
            if exp_date >= today:
                available_exp_dates.append(exp_date)
        except ValueError:
            continue

    available_exp_dates.sort()
    if not available_exp_dates:
        return None

    target_date = today if dte_target == 0 else today.fromordinal(today.toordinal() + dte_target)
    exact_exp = next((exp for exp in available_exp_dates if exp == target_date), None)
    if exact_exp:
        return {
            'requested_dte': dte_target,
            'actual_dte': (exact_exp - today).days,
            'label': f'{dte_target}DTE',
            'expiration_date': exact_exp,
            'is_exact_match': True,
            'is_fallback': False,
            'fallback_reason': None,
        }

    fallback_exp = next((exp for exp in available_exp_dates if exp >= target_date), None)
    if fallback_exp is None:
        fallback_exp = available_exp_dates[-1]

    actual_dte = (fallback_exp - today).days
    return {
        'requested_dte': dte_target,
        'actual_dte': actual_dte,
        'label': f'{actual_dte}DTE (requested {dte_target}DTE, fallback)',
        'expiration_date': fallback_exp,
        'is_exact_match': False,
        'is_fallback': True,
        'fallback_reason': f'No exact {dte_target}DTE expiry available; using nearest valid expiry {fallback_exp.strftime("%Y-%m-%d")}.',
    }


def safe_float(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def get_delta(option_data):
    greeks = option_data.get('greeks') or {}
    delta = greeks.get('delta')
    return safe_float(delta)


def get_mid_price(option_data):
    bid = safe_float(option_data.get('bid'))
    ask = safe_float(option_data.get('ask'))
    if bid is None or ask is None:
        return None
    return (bid + ask) / 2.0


def get_spread_ratio(option_data):
    bid = safe_float(option_data.get('bid'))
    ask = safe_float(option_data.get('ask'))
    mid = get_mid_price(option_data)
    if bid is None or ask is None or mid is None or mid <= 0:
        return None
    return (ask - bid) / mid


def distance_pct(option_data, underlying_price):
    strike = safe_float(option_data.get('strike'))
    if strike is None or not underlying_price:
        return None
    return abs(strike - underlying_price) / underlying_price


def option_side_is_directionally_valid(option_data, underlying_price, dte_value, strategy_type):
    option_type = option_data.get('option_type')
    strike = safe_float(option_data.get('strike'))
    delta = get_delta(option_data)
    if option_type not in ('call', 'put') or strike is None or delta is None:
        return False

    if strategy_type == 'scalping_buy':
        if dte_value == 0:
            return True
        if dte_value == 1:
            return (option_type == 'call' and strike <= underlying_price) or (option_type == 'put' and strike >= underlying_price)

    if strategy_type == 'credit_spread_sell':
        return (option_type == 'call' and strike > underlying_price) or (option_type == 'put' and strike < underlying_price)

    return False


def basic_liquidity_ok(option_data):
    bid = safe_float(option_data.get('bid'))
    ask = safe_float(option_data.get('ask'))
    if bid is None or ask is None or bid < MIN_BID or ask <= 0 or ask < bid:
        return False
    spread_ratio = get_spread_ratio(option_data)
    if spread_ratio is None or spread_ratio > MAX_BID_ASK_SPREAD_RATIO:
        return False
    return True


def score_scalping_option(option_data, underlying_price, dte_value):
    delta = abs(get_delta(option_data) or 0)
    bid = safe_float(option_data.get('bid'), 0.0)
    ask = safe_float(option_data.get('ask'), 0.0)
    mid = get_mid_price(option_data) or 0.0
    spread_ratio = get_spread_ratio(option_data)
    dist_pct = distance_pct(option_data, underlying_price)

    if spread_ratio is None or dist_pct is None or mid <= 0:
        return None

    target_low, target_high = SCALPING_DELTA_RANGES[dte_value]
    target_delta = (target_low + target_high) / 2.0
    delta_penalty = abs(delta - target_delta)
    liquidity_bonus = min(bid, ask, mid)

    return (
        -delta_penalty,
        -dist_pct,
        -spread_ratio,
        liquidity_bonus,
    )


def score_credit_option(option_data, underlying_price):
    delta = abs(get_delta(option_data) or 0)
    bid = safe_float(option_data.get('bid'), 0.0)
    ask = safe_float(option_data.get('ask'), 0.0)
    spread_ratio = get_spread_ratio(option_data)
    dist_pct = distance_pct(option_data, underlying_price)

    if spread_ratio is None or dist_pct is None:
        return None

    target_delta = sum(CREDIT_DELTA_RANGE) / 2.0
    delta_penalty = abs(delta - target_delta)

    return (
        -delta_penalty,
        -spread_ratio,
        bid,
        dist_pct,
        ask,
    )


def process_options_for_strategy(underlying_price, options_data, current_vix, strategy_type="scalping_buy", dte_value=0, symbol=None, selection_meta=None):
    """Apply stricter strategy filters and rank surviving candidates with reusable analytics."""
    if not options_data or not options_data.get('options') or not options_data['options'].get('option'):
        return []

    print(f" [Strategy Processor] Current VIX: {current_vix}. Applying strict filters.")

    options = options_data['options']['option']
    ranked_candidates = []
    selection_meta = selection_meta or {
        'requested_dte': dte_value,
        'actual_dte': dte_value,
        'label': f'{dte_value}DTE',
        'is_fallback': False,
    }

    for opt in options:
        delta = get_delta(opt)
        if delta is None:
            continue
        if not basic_liquidity_ok(opt):
            continue
        if not option_side_is_directionally_valid(opt, underlying_price, dte_value, strategy_type):
            continue

        dist_pct = distance_pct(opt, underlying_price)
        if dist_pct is None:
            continue

        if strategy_type == "scalping_buy":
            target_low, target_high = SCALPING_DELTA_RANGES[dte_value]
            if not (target_low <= abs(delta) <= target_high):
                continue
            if dist_pct > SCALPING_DISTANCE_LIMITS[dte_value]:
                continue
            score = score_scalping_option(opt, underlying_price, dte_value)
        elif strategy_type == "credit_spread_sell":
            low, high = CREDIT_DELTA_RANGE
            if not (low <= abs(delta) <= high):
                continue
            score = score_credit_option(opt, underlying_price)
        else:
            continue

        if score is None:
            continue
        analytics = compute_candidate_analytics(symbol or '', opt, underlying_price, current_vix, strategy_type, dte_value, selection_meta, is_fallback=False)
        if analytics is None or analytics.get('no_trade'):
            continue
        opt = dict(opt)
        opt['_analytics'] = analytics
        ranked_candidates.append((score, candidate_sort_key(analytics), opt))

    ranked_candidates.sort(reverse=True, key=lambda x: (x[1], x[0]))

    cap = MAX_SCALPING_TICKETS_PER_SYMBOL_DTE if strategy_type == "scalping_buy" else MAX_CREDIT_TICKETS_PER_SYMBOL_DTE
    return [opt for _, _, opt in ranked_candidates[:cap]]


def build_fallback_candidates(options_data, underlying_price, strategy_type, dte_value, symbol=None, current_vix=None, selection_meta=None):
    if not options_data or not options_data.get('options') or not options_data['options'].get('option'):
        return []

    options = options_data['options']['option']
    ranked_candidates = []
    selection_meta = selection_meta or {
        'requested_dte': dte_value,
        'actual_dte': dte_value,
        'label': f'{dte_value}DTE',
        'is_fallback': True,
    }

    for opt in options:
        delta = get_delta(opt)
        if delta is None:
            continue
        if not basic_liquidity_ok(opt):
            continue
        if not option_side_is_directionally_valid(opt, underlying_price, dte_value, strategy_type):
            continue

        abs_delta = abs(delta)
        if strategy_type == 'scalping_buy':
            if not (0.30 <= abs_delta <= 0.70):
                continue
            score = score_scalping_option(opt, underlying_price, min(dte_value, 1))
        else:
            if not (0.08 <= abs_delta <= 0.22):
                continue
            score = score_credit_option(opt, underlying_price)
        if score is None:
            continue
        analytics = compute_candidate_analytics(symbol or '', opt, underlying_price, current_vix, strategy_type, min(dte_value, 1), selection_meta, is_fallback=True)
        if analytics is None:
            continue
        opt = dict(opt)
        opt['_analytics'] = analytics
        ranked_candidates.append((score, candidate_sort_key(analytics), opt))

    ranked_candidates.sort(reverse=True, key=lambda x: (x[1], x[0]))
    return [opt for _, _, opt in ranked_candidates[:FALLBACK_TICKETS_PER_SYMBOL_DTE]]


def should_emit_for_selection(selection_meta, strategy_type):
    """Reject distant fallback expiries for short-dated workflows."""
    if not selection_meta.get('is_fallback'):
        return True

    actual_dte = selection_meta['actual_dte']
    requested_dte = selection_meta['requested_dte']

    if strategy_type == 'scalping_buy':
        return actual_dte <= 1

    if strategy_type == 'credit_spread_sell':
        return actual_dte <= max(2, requested_dte + 1)

    return False


def format_option_as_ticket_message(symbol, display_label, option_data, strategy_type, underlying_price, current_vix, selection_meta, is_fallback=False):
    analytics = option_data.get('_analytics') or {}
    ticket = f"{'[FALLBACK] ' if is_fallback else ''}{strategy_type.replace('_', ' ').title()} Opportunity for {symbol} ({display_label})**\n"
    ticket += f"  - Underlying Price: ${underlying_price:.2f}\n"
    ticket += f"  - Current VIX: {current_vix}\n"
    ticket += f"  - Type: {option_data['option_type'].upper()}\n"
    ticket += f"  - Strike: ${safe_float(option_data['strike'], 0.0):.2f}\n"
    ticket += f"  - Expiration: {option_data['expiration_date']}\n"
    ticket += f"  - Requested DTE: {selection_meta['requested_dte']}\n"
    ticket += f"  - Actual DTE: {selection_meta['actual_dte']}\n"
    ticket += f"  - Last Price: ${option_data['last'] if option_data['last'] is not None else 'N/A'}\n"
    ticket += f"  - Bid: ${safe_float(option_data['bid'], 0.0):.2f} / Ask: ${safe_float(option_data['ask'], 0.0):.2f}\n"

    delta = get_delta(option_data)
    if delta is not None:
        ticket += f"  - Delta: {delta:.4f}\n"
    else:
        ticket += f"  - Delta: N/A\n"

    spread_ratio = get_spread_ratio(option_data)
    if spread_ratio is not None:
        ticket += f"  - Spread Ratio: {spread_ratio:.2%}\n"

    if analytics:
        ticket += f"  - Setup Family: {analytics.get('setup_family', 'unknown')}\n"
        ticket += f"  - Structure Score: {analytics.get('structure_score', 0.0):.2f}\n"
        ticket += f"  - Confidence Score: {analytics.get('confidence_score', 0)}/10\n"
        ticket += f"  - Liquidity Score: {analytics.get('liquidity_score', 0.0):.2f}\n"
        ticket += f"  - Expiry Quality Score: {analytics.get('expiry_quality_score', 0.0):.2f}\n"
        ticket += f"  - Delta Fit Score: {analytics.get('delta_fit_score', 0.0):.2f}\n"
        ticket += f"  - Distance Score: {analytics.get('distance_score', 0.0):.2f}\n"
        ticket += f"  - VIX Regime: {analytics.get('vix_regime', 'unknown')}\n"
        ticket += f"  - Narrative: {analytics.get('narrative', '')}\n"
        ticket += f"  - Expectations: {analytics.get('expectations', '')}\n"
        ticket += f"  - Invalidation: {analytics.get('invalidation', '')}\n"
        ticket += f"  - Risk Profile: {analytics.get('risk_profile', '')}\n"
        ticket += f"  - Selection Reason: {analytics.get('reason_selected', '')}\n"

    if selection_meta.get('is_fallback'):
        ticket += f"  - Expiry Selection Note: {selection_meta['fallback_reason']}\n"

    return ticket


if __name__ == "__main__":
    today = date.today()
    print(f"DEBUG: Today's date: {today}")

    print("DEBUG: Attempting to fetch VIX quote.")
    current_vix = get_vix_quote()
    if current_vix is None:
        print("Error: Could not fetch VIX quote. Exiting.")
        exit()
    print(f"\n--- Current VIX: {current_vix} ---")
    print("DEBUG: VIX fetched successfully. Starting symbol processing loop.")

    for symbol in SYMBOLS:
        print(f"\n--- Processing {symbol} ---")
        underlying_price = get_underlying_quote(symbol)
        if not underlying_price:
            print(f"  Could not fetch underlying price for {symbol}. Skipping.")
            continue
        print(f"  Underlying price for {symbol}: {underlying_price}")

        processed_expiries = set()

        for requested_dte in TARGET_DTE:
            selection = get_expiration_selection(symbol, today, requested_dte)
            if not selection:
                print(f"  No valid expiration found for {symbol} requested {requested_dte}DTE.")
                continue

            exp_date = selection['expiration_date']
            exp_date_str = exp_date.strftime('%Y-%m-%d')
            display_label = selection['label']

            if exp_date_str in processed_expiries:
                print(f"Skipping duplicate expiry {exp_date_str} for {symbol}; already processed via a higher-priority DTE path.")
                continue
            processed_expiries.add(exp_date_str)

            print(f"Fetching option chain for {symbol}, requested DTE: {requested_dte} (Using Expiry: {exp_date_str}, Label: {display_label})...")
            if selection['is_fallback']:
                print(f"  Expiry fallback in use: {selection['fallback_reason']}")

            chain_data = get_option_chain(symbol, exp_date)
            if not chain_data:
                print(f"    No options data to process for {symbol} on {exp_date_str}.")
                continue

            all_ticket_messages = []

            if should_emit_for_selection(selection, "scalping_buy"):
                print(f"Applying 'scalping_buy' strategy for {symbol} on {exp_date_str} (Requested DTE {requested_dte}, Actual DTE {selection['actual_dte']})...")
                filtered_options_buy = process_options_for_strategy(
                    underlying_price, chain_data, current_vix, "scalping_buy", min(selection['actual_dte'], 1), symbol=symbol, selection_meta=selection
                )
                if filtered_options_buy:
                    print(f"Found {len(filtered_options_buy)} ranked options for scalping_buy. Formatting tickets...")
                    for opt in filtered_options_buy:
                        ticket = format_option_as_ticket_message(symbol, display_label, opt, "scalping_buy", underlying_price, current_vix, selection, is_fallback=False)
                        all_ticket_messages.append(ticket)
                else:
                    print("No strict scalping candidates found. Generating fallback shortlist...")
                    fallback_options = build_fallback_candidates(chain_data, underlying_price, "scalping_buy", min(selection['actual_dte'], 1), symbol=symbol, current_vix=current_vix, selection_meta=selection)
                    for opt in fallback_options:
                        ticket = format_option_as_ticket_message(symbol, display_label, opt, "scalping_buy", underlying_price, current_vix, selection, is_fallback=True)
                        all_ticket_messages.append(ticket)
            else:
                print(f"Skipping scalping output for {symbol} requested {requested_dte}DTE because fallback actual DTE {selection['actual_dte']} is too distant.")

            if should_emit_for_selection(selection, "credit_spread_sell"):
                print(f"Applying 'credit_spread_sell' strategy for {symbol} on {exp_date_str} (Requested DTE {requested_dte}, Actual DTE {selection['actual_dte']})...")
                filtered_options_sell = process_options_for_strategy(
                    underlying_price, chain_data, current_vix, "credit_spread_sell", min(selection['actual_dte'], 1), symbol=symbol, selection_meta=selection
                )
                if filtered_options_sell:
                    print(f"Found {len(filtered_options_sell)} ranked options for credit_spread_sell. Formatting tickets...")
                    for opt in filtered_options_sell:
                        ticket = format_option_as_ticket_message(symbol, display_label, opt, "credit_spread_sell", underlying_price, current_vix, selection, is_fallback=False)
                        all_ticket_messages.append(ticket)
                else:
                    print("No strict credit spread candidates found. Generating fallback shortlist...")
                    fallback_options = build_fallback_candidates(chain_data, underlying_price, "credit_spread_sell", min(selection['actual_dte'], 1), symbol=symbol, current_vix=current_vix, selection_meta=selection)
                    for opt in fallback_options:
                        ticket = format_option_as_ticket_message(symbol, display_label, opt, "credit_spread_sell", underlying_price, current_vix, selection, is_fallback=True)
                        all_ticket_messages.append(ticket)
            else:
                print(f"Skipping credit spread output for {symbol} requested {requested_dte}DTE because fallback actual DTE {selection['actual_dte']} is too distant.")

            if all_ticket_messages:
                print("---TICKET_START---")
                for msg in all_ticket_messages:
                    print(msg)
                    print("---TICKET_DELIMITER---")
                print("---TICKET_END---")
            else:
                print("No tickets generated for this symbol/requested DTE.")

    print("\nTradier options processing complete.")
