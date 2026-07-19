# Acceptance checklist (spec §30)

## Data

- [x] Vendor interface supports delisted flags (synthetic)
- [x] Permanent security IDs
- [x] Corporate actions hooks (splits/dividends)
- [x] Trading calendar (exchange_calendars / fallback)
- [x] Data manifest hashed
- [x] Data-quality issues reported
- [ ] Full delisted PIT universe (requires Norgate/Polygon) — **blocks deploy on LSE**

## Strategy

- [x] Current bar excluded from breakout windows
- [x] Next-open execution
- [x] Volume confirmation uses prior history
- [x] Stock + benchmark regime filters
- [x] Earnings blackout (when enabled + calendar present)
- [x] Deterministic ranking

## Risk

- [x] 0.5% risk sizing
- [x] Heat / weight / liquidity / sector caps
- [x] Gap stops conservative
- [x] Kill switch + shadow resume structure
- [x] No leverage by default

## Accounting

- [x] Daily cash + MV reconciliation (1 cent)
- [x] Commissions + slippage tracked
- [x] Dividends/splits handled
- [x] Delist exit path

## Validation

- [x] Metrics suite
- [x] Deflated Sharpe
- [x] Stationary bootstrap
- [x] Monte Carlo drawdown
- [x] Promotion gate
- [x] Walk-forward runner
- [x] Stability sweep helper
- [ ] Full multi-decade cost/universe ablations on real delisted data

## Auditability

- [x] Git commit + dirty flag
- [x] Config + data hashes
- [x] Seed recorded
- [x] Append-only experiment registry
- [x] Orders/fills/daily logs
- [x] Deployment status explicit; live routing off
