# Coinbase Active Crypto Sleeve Blueprint

Date: 2026-05-18
Status: Coinbase Advanced API authenticated; Coinbase Derivatives / FCM wallet and products visible; INTX portfolio endpoints are not the current active lane.
Mandate: real live-trading architecture. No fake PnL, no paper-trade claims, no pretending a signal log is a trade.

## Objective

Create a separate active crypto sleeve for BTC/ETH perpetual trading.

This is not a replacement for:
- BTC CBBTC/USDC rotator
- Tradier/options workflow
- Kalshi/prediction-market engine

It is a separate, boxed account with its own bankroll, API wallet, risk rules, logs, and kill switch.

## Venue Choice

Primary venue: Coinbase Advanced / Coinbase Derivatives US (FCM) futures-perp products.

Secondary venue: Coinbase International Exchange (INTX) perpetuals only if Conor separately enables an INTX portfolio/API scope.

Backup venue: Kraken Derivatives US only if Coinbase perps are unavailable.

Coinbase reasons:
- Conor already has a Coinbase One/Pro relationship, reducing funding/account friction.
- Coinbase Advanced exposes Coinbase Derivatives US (FCM) futures/perp-style products through the same Advanced API.
- The current AGORAALGO key has view/trade on the default portfolio and can read FCM derivatives balance/positions.
- INTX products are visible, but INTX portfolio/balance/position endpoints return PERMISSION_DENIED; treat that as a separate venue/scope, not the current executable wallet.

Kraken notes:
- Kraken non-US derivatives has perpetual futures, but the US derivatives path is described as Kraken Derivatives US / CME crypto futures.
- That can still be useful, but it is less aligned with the low-friction perp scalper blueprint than Coinbase perps.

Required Coinbase setup:
- Confirm Coinbase Advanced derivatives eligibility/onboarding in the UI.
- Transfer starting capital into the Coinbase derivatives/futures wallet.
- Create Coinbase Advanced/CDP API credentials with trade permission, no withdrawal permission.
- Verify read-only calls first: products, CFM balance summary, CFM positions, open orders, fills, best bid/ask, websocket market/user streams.
- Live order permission only after bankroll/risk config exists.

Current access check, 2026-05-18:
- API key name stored locally in credentials/coinbase_agoraalgo_api_key_name.txt.
- EC private key stored locally in credentials/coinbase_agoraalgo_private_key.pem.
- Coinbase Advanced REST JWT auth confirmed against `/api/v3/brokerage/products`.
- FCM derivatives products visible, including `BIP-20DEC30-CDE` (BTC PERP) and `ETP-20DEC30-CDE` (ETH PERP).
- CFM balance endpoint works: futures buying power about `$562.27`, CFM USD balance about `$351.60`, no current positions.
- Open orders query returned zero open orders.
- INTX/perpetual portfolio endpoints returned PERMISSION_DENIED against the visible default portfolio UUID; do not use INTX for this sleeve unless Coinbase exposes a separate INTX portfolio/API scope.
- No orders have been placed.

Agora attachment, 2026-05-18:
- Dashboard endpoint: `/agora/api/agora/active-crypto`.
- Visible panels added to Agora:
  - Coinbase Active Crypto Sleeve
  - Coinbase Trade Approval Gate
  - Coinbase Signal Cards
  - Coinbase Protections
- Signal cards are review-only. They show market, direction, setup family, entry trigger, invalidation, targets, max notional, max dollars at risk, leverage cap, approval state, and order state.
- Current signal mode: `review_only`; live switch is off; zero positions; zero open orders.
- Current automatic card posture: `WAIT_FOR_LONG_RECLAIM` for BTC PERP and ETH PERP. This is not an order. It is the visible proposal layer before approval.
- Current caps from live account snapshot: max planned risk about $2.64 per trade (to be recalibrated to 50% ceiling). BTC max notional about $439.50, ETH max notional about $351.60, subject to explicit approval and fresh account state.

## Starting Bankroll

Recommended initial sleeve: $250-$500.

This is enough to make live behavior meaningful without letting one bug become another K-Day.

Initial limits:
- Max daily loss: 100% of sleeve.
- Max per-trade loss: 50% of sleeve.
- Max open positions: 1.
- Initial markets: BTC and ETH only.
- Initial leverage cap: 2x.
- Absolute leverage ceiling before review: 3x.
- No alt perps until the BTC/ETH process has real fill logs and sane exits.

## Core Strategy

Name: Reclaim/Sweep Perp Scalper

The strategy trades liquid BTC/ETH perp moves where structure is clear and friction is low.

## Fundamental Trading Framework

The sleeve uses fundamentals as a regime filter, not as a reason to ignore price.

Daily market read:
- BTC macro bias: risk-on, risk-off, chop, or liquidation/reset.
- Dollar/rates pressure: DXY, yields, equity futures, and major macro event calendar.
- Crypto-native pressure: ETF flow narrative, major exchange news, regulatory headlines, stablecoin/liquidity stress, and large BTC/ETH unlock or treasury flow if relevant.
- Funding/friction: whether long or short exposure is being charged meaningfully.
- Volatility regime: compression, expansion, post-liquidation recovery, or disorderly trend.

Intraday decision frame:
- Trade with BTC leadership when BTC is driving the market.
- Trade ETH only when ETH has relative strength/weakness versus BTC or cleaner structure.
- Do not short into obvious broad risk-on momentum unless there is a real failed breakout/sweep.
- Do not long into a falling market unless there is a liquidation sweep and reclaim.
- News-driven moves require smaller size or no trade until the spread/order book stabilizes.

Approved trade thesis format:
- Market: BTC or ETH derivative product.
- Direction: long or short.
- Setup family: liquidation sweep reclaim, trend continuation, or volatility compression breakout.
- Fundamental regime: why this market is worth trading now.
- Entry zone: exact price or trigger.
- Stop: exact invalidation level.
- Targets: T1, T2, and trailing logic.
- Size: notional, estimated margin, leverage, and dollars at risk.
- Risk/reward: minimum 1.5R to T1, preferred 2.5R+ to T2.
- Failure mode: what would prove the trade wrong quickly.

No order is allowed unless that format is complete and Conor explicitly approves the exact order.

It has three setup families:

### 1. Liquidation Sweep Reclaim

Long setup:
- Price sweeps below a recent 15m/1h low.
- Fast recovery back above the sweep level.
- Open interest or volume expands into the sweep.
- Funding is not hostile to the long.
- Entry is on reclaim, not on blind falling knife.

Short setup:
- Price sweeps above a recent 15m/1h high.
- Fast failure back below the sweep level.
- Volume/OI confirms a stop run.
- Funding is not strongly hostile to short exposure.

Use case:
- This is the main aggressive mean-reversion setup.

### 2. Trend Continuation After Reclaim

Long setup:
- Higher timeframe trend is up.
- Price pulls back to VWAP/EMA/midline area.
- Price reclaims with momentum.
- BTC and ETH breadth agree or BTC leads.
- Enter with tight invalidation under reclaim.

Short setup:
- Higher timeframe trend is down.
- Price rejects VWAP/EMA/midline.
- Momentum rolls over.
- Enter with stop above failed reclaim.

Use case:
- This catches directional continuation without chasing the high/low.

### 3. Volatility Compression Breakout

Long or short setup:
- Range compresses.
- Funding neutral or favorable.
- Book imbalance and volume expand through range boundary.
- Enter breakout with a tight stop back inside the range.
- Avoid chop if spread/slippage widens.

Use case:
- This is the clean breakout lane for active sessions.

## Signal Stack

Inputs:
- Coinbase Advanced perp market data.
- L2/order-book imbalance.
- Recent candles: 1m, 5m, 15m, 1h.
- Funding rate and funding history.
- Recent user fills/open orders.
- Position and margin state.
- Optional external confirmation: BTC/ETH spot index from Coinbase/Kraken/Binance public feeds.

Derived features:
- VWAP distance.
- EMA 9/21/50 alignment.
- 15m and 1h structure highs/lows.
- Sweep depth and reclaim speed.
- Realized volatility.
- Candle impulse score.
- Book imbalance.
- Funding friction score.
- Trend regime: trend, range, chop, news shock.

## Entry Rules

Every live entry requires:
- One setup family active.
- Explicit direction: long or short.
- Stop distance known before entry.
- Position size computed from risk cap.
- Minimum reward/risk: 1.5R target one, 2.5R target two.
- No conflicting open position.
- No daily loss lockout active.
- No stale data.
- No unconfirmed previous order state.
- Fundamental regime is not hostile to the trade.
- Coinbase CFM balance, positions, and open orders are freshly verified.

Order preference:
- Use marketable limit / IOC for fast entries.
- Avoid resting entries if signal depends on immediate reclaim.
- Place stop immediately after fill.
- Place take-profit or reduce-only exit logic immediately after fill.

## Exit Rules

Initial stop:
- Always placed immediately after entry.
- Based on invalidation, not arbitrary percent.

Profit handling:
- Take partial at 1R or when momentum stalls.
- Trail remainder using structure or VWAP/EMA.
- Close if funding/structure flips against position.
- Close before major known event if spread/volatility becomes disorderly.

Hard exits:
- Stop hit.
- Setup invalidated.
- Daily loss cap reached.
- Exchange/API state uncertain.
- Data stale.
- Duplicate/open-order mismatch.
- Manual kill switch.

## Risk Engine

Required checks before every order:
- Sleeve balance fetched live.
- Existing position fetched live.
- Open orders fetched live.
- Max notional cap.
- Max leverage cap.
- Max daily realized loss.
- Max daily number of trades.
- Cooldown after two consecutive losses.
- No order if stop cannot be placed.

Recommended initial values:
- Max trade risk: 50% of sleeve.
- Max daily risk: 100% of sleeve.
- Max trades/day: 6.
- Cooldown after 2 losses: 30 minutes.
- Max notional: bankroll * 2.
- Max slippage budget: 0.05%-0.12% depending on BTC/ETH liquidity.

Recovery discipline:
- The sleeve exists to grind back losses through repeatable execution, not to revenge trade.
- First objective is net-positive process over 10 live reviewed trades.
- Second objective is recover the first $100 with no rule violations.
- Only after that can size increase be considered.
- Any day that hits the daily loss cap ends trading immediately.

## Live-Proof Standard

A trade only counts if all are logged:
- Signal snapshot.
- Pre-order account state.
- Submitted order payload.
- Exchange response.
- Fill confirmation.
- Stop/TP order confirmation.
- Post-fill account state.
- Exit order/fill.
- Realized PnL.

No paper claims. If it did not fill on Coinbase, it is not a trade.

## System Architecture

Directory:
- active_crypto_sleeve/

Modules:
- config.py: env/config/risk limits.
- client.py: Coinbase Advanced API wrapper first; Kraken adapter later only if needed.
- market_data.py: mids, candles, L2, funding.
- signals.py: setup detection and scoring.
- risk.py: sizing, caps, lockouts.
- executor.py: live order placement, cancel, stops, exits.
- journal.py: immutable JSONL trade/event logs.
- runner.py: main loop.
- review.py: daily review and strategy diagnostics.

Runtime state:
- state/active_crypto_sleeve_state.json
- out/active_crypto_sleeve_events.jsonl
- out/active_crypto_sleeve_trades.jsonl
- out/active_crypto_sleeve_daily_review.json

Environment:
- ACTIVE_CRYPTO_VENUE=coinbase
- COINBASE_API_KEY
- COINBASE_API_SECRET
- COINBASE_API_PASSPHRASE or JWT/CDP credential fields required by the current Coinbase key type
- ACTIVE_CRYPTO_LIVE_ENABLED=false initially
- ACTIVE_CRYPTO_MAX_DAILY_LOSS_PCT=30
- ACTIVE_CRYPTO_MAX_TRADE_RISK_PCT=25
- ACTIVE_CRYPTO_MAX_LEVERAGE=2
- ACTIVE_CRYPTO_MARKETS=BIP-20DEC30-CDE,ETP-20DEC30-CDE

Live switch:
- Orders are blocked unless ACTIVE_CRYPTO_LIVE_ENABLED=true.
- Even when live is enabled, orders are blocked if account state, margin, open orders, or stop placement cannot be verified.

## Build Sequence

1. Read-only connector
- Verify account state.
- Fetch mids/candles/funding.
- Fetch open orders/fills/positions.
- No order functions enabled.

2. Live executor wiring
- Implement order, cancel, market close, trigger stop, reduce-only TP.
- Use minimum-size real order only after explicit funding/arming.

3. Risk engine
- Size from stop distance.
- Enforce daily loss, max notional, max leverage, one-position rule.

4. Signal engine
- Implement sweep reclaim, trend continuation, compression breakout.
- Output only signals that can be translated into exact order/stop/target.

5. Armed live run
- Start with BTC only.
- Minimum viable notional.
- One trade at a time.
- Expand only after real fill logs show sane behavior.

## What This Avoids

- No revenge mode.
- No martingale.
- No averaging down unless prewritten as a scaled-entry setup.
- No unbounded leverage.
- No altcoin perps at launch.
- No trade without stop.
- No live order if logs are broken.
