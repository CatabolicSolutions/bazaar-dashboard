# Go-Live Checklist - Bazaar Trading Desk

## Pre-Market Validation (2026-03-31)

### Network Access ✓
- [x] Dashboard accessible on same network
- [x] URL: http://192.168.220.149:8765
- [x] Mobile device can connect

### System Status ✓
- [x] Tradier board artifact present
- [x] 10 leaders parsed
- [x] API key configured
- [x] Account active (6YB74771)
- [x] $200 buying power available
- [x] Option level 2 approved

### Execution Pipeline ✓
- [x] Dashboard → ExecutionIntent bridge working
- [x] Preview order functional
- [x] Live order placement tested (Order 119301060)
- [x] Position recording to active_positions.json
- [x] Position display on dashboard

## Safety Limits (CONFIGURED)

### Position Limits
- Max position size: 1 contract per trade
- Max open positions: 3
- Max daily trades: 5
- Max daily loss: $50

### Trading Rules
- Only 0DTE/1DTE options (tested and working)
- Only SPY, IWM, QQQ (liquid underlyings)
- Only $0.01-$0.05 entry price range
- Cash day mode only (no margin)
- Stop loss at 50% of premium

### Risk Controls
- Risk evaluation enabled
- Manual approval required for each trade
- Preview must show cost < $5
- Account must maintain $100 minimum buying power

## Go-Live Steps

### Before Market Open (8:30 AM MT)
1. [ ] Start dashboard: `python3 dashboard/scripts/serve_dashboard.py`
2. [ ] Verify dashboard loads on mobile
3. [ ] Run fresh Tradier scan
4. [ ] Verify leaders board populated
5. [ ] Check buying power > $150

### During Market Hours
1. [ ] Select leader from board
2. [ ] Review ticket detail
3. [ ] Click "Execute Now"
4. [ ] Review preview (cost must be <$5)
5. [ ] Confirm execution
6. [ ] Verify position appears in dashboard
7. [ ] Monitor position in Tradier app

### End of Day
1. [ ] Close all 0DTE positions before expiration
2. [ ] Review P&L
3. [ ] Document trades in memory

## Emergency Procedures

### If Dashboard Fails
- Direct Tradier app access available
- Phone: [your phone number]

### If API Errors
- Check TRADIER_API_KEY is set
- Verify account status
- Contact Tradier support if needed

### If Position Goes Bad
- Use Tradier app to close immediately
- Do not rely solely on dashboard for exits

## Contacts
- Tradier Support: support@tradier.com
- Brokerage: Tradier Brokerage

---
**Status:** READY FOR MARKET OPEN
**Last Updated:** 2026-03-30 23:05 MDT
**Approved By:** Conor Ross
