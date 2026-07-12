# Research expansion — v25 live hybrid (2026-07-11)

Built on existing model findings, not a greenfield rewrite.

## Working DNA reused

| Source | What we took |
|--------|----------------|
| v23_devin_overlay / v20b | SIDE rules + XLP/SPY defensive stand-aside + vol_z conviction |
| OPTIONS_1K_PLAYBOOK | Debit spreads, 14–45 DTE, cut −30%, trail +40%, flat 5 DTE |
| REALISTIC_LIMITS (v24) | Do not full-account compound; capital is tied while open |
| ANTI_OVERFIT / PASS_BAR | No random k-fold; WR vanity banned; size feedback ≠ rule retune |
| live_signal | Universal any-ticker features when model map missing |
| trade_desk | Operator workflow for equity levels |

## Live gaps closed in this pass

1. **Vehicle choice** is explicit (options attack vs equity hedge vs cash).
2. **Macro regime** computed live (QQQ EMA20/50 + XLP/SPY ratio defensive).
3. **One ticket** from `tools/live_plan.py` (features + risk + structure).
4. **Frontend Live desk** at `/live` for operator use without CLI.
5. **Scan** ranks book for attack/hedge priority under current macro.

## Still research / paper

- Options OOS with real marks (LSE) — sample still thin; do not claim WINNER options.
- Multi-position portfolio equity path vs v23 full backtest — pending formal run card.
- Earnings calendar auto-gate (manual / yfinance next).

## Operator rule

If Live desk says STAND_ASIDE or options skip → **do not force** naked weeklies. Equity hedge or cash only.
