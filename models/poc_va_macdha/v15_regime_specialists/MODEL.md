# v15_regime_specialists

**Winner** over v13/v14 on risk-adjusted composite (WR + Sharpe + DD + PF).

## Stack
1. **Signal DNA**: same per-symbol routing as `v14_risk_kelly` (not re-tuned)
2. **Risk**: half-Kelly confidence sizing + ATR hard stop / trail (LSE drawdown framing)
3. **Regime**: `gate_qqq_trend` on non-SPY — prior daily QQQ MACD-hist green AND close > SMA20

## Proof
- Walk-forward: `runs/poc_va_regime/artifacts/REGIME_PROOF.json`
- Selected on **train** half only; OOS +8.8pp WR on gated v14 trades (72.7% OOS WR)
- Portfolio backtest: `runs/poc_va_regime/` — WR 63.9%, Sharpe 1.78, DD -17.5%, PF 3.63, 83 trades

## Anti-overfit
- Binary structural gate only (no threshold grid)
- Require train **and** OOS WR lift > 0 to promote
- Did not stack Mag7 gate (higher OOS lift but <40% train retention → ineligible)
- Prior XGB filter found no edge (`runs/artifacts/xgb_report.json`)

## Trade-off
Fewer trades / lower absolute return than v14, by design (skip Nasdaq-dump regimes).
