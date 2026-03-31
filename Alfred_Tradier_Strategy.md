# Alfred's Tradier Data Universe and Options Strategy

## I. Symbols to Monitor:
*   SPX
*   SPY
*   NDX
*   QQQ
*   NVDA
*   TSLA
*   XSP
*   IWM
*   VIX
*   AMD
*   AAPL
*   *(And similar high-liquidity, high-volume options-eligible assets)*

## II. Primary Target Expiration Ranges:
*   **0DTE (0 Days To Expiration):**
    *   **Characteristics:** Non-linear, accelerating Theta decay between 10:00 AM - 4:00 PM; high Gamma risk (200-500% jump/80% loss in minutes). "Powerball" territory.
    *   **Primary Goal:** Scalping Momentum (catch 15-minute trend and exit).
    *   **Risk Management:** Strict 20-30% hard stops.
    *   **Favorite Setup:** "Opening Drive" or "Power Hour" (high volume periods), requires lightning-fast execution.
    *   **User Profile:** Disciplined "hunter" capitalizing on intraday volatility, avoiding overnight surprises, and tolerating extreme swings.
*   **1DTE (1 Day To Expiration):**
    *   **Characteristics:** Benefits from "Overnight Effect" (capturing next day's open gaps); high Theta decay but less "lethal" in first two hours.
    *   **Primary Goal:** Mean Reversion / Swing trading.
    *   **Betting Strategy:** Directional bets for next 24 hours, "Overnight Hold," betting on news or gap at open. Allows technical analysis to play out.
    *   **Considerations:** Vulnerable to major geopolitical events (opens at $0 or $5).
    *   **User Profile:** For when 0DTE is too "noisy"; trading technical setups needing > 4 hours to materialize.

## III. Strike Choice (Strategy Dependent):
*   **For Scalping (Buying Calls/Puts):**
    *   **ATM (At-the-Money):** Strikes closest to current price, highest Gamma, fastest value gain during a move.
*   **For 1DTE (Buying Slightly ITM):**
    *   **Slightly ITM (In-the-Money):** Provides some protection against Theta (time) decay.
*   **For Credit Spreads (Selling):**
    *   **OTM (Out-of-the-Money):** Specifically 0.10 to 0.20 Delta range (80-90% theoretical probability of expiring worthless for premium collection).

## IV. Non-Options Stock Data (Leading Indicators to Track):
*   **VWAP (Volume Weighted Average Price):** The critical "anchor" for 0DTE.
    *   Price above VWAP -> Look only for Calls.
    *   Price below VWAP -> Look only for Puts.
*   **Tick Index ($TICK):** Shows NYSE internal health.
    *   Readings > +1000 or < -1000 often signal reversal points for 0DTE scalps.
*   **VIX (Volatility Index):**
    *   Rising VIX -> Credit spread sellers need to move strikes further OTM to account for larger swings.
*   **Expected Move (Market Maker Move):** Alfred should calculate the daily "Expected Move" (EM).
    *   If SPX hits its EM range by 11:00 AM, it is highly likely to "fade" or stay range-bound for the rest of the day.

