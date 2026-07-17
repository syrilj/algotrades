# v70_high_confidence_wr

High-confidence / high win-rate equity candidate.

## Hypothesis

Entry *selection* (not forced early exits) drives win rate:

1. **Teacher**: `v45_ultimate_rsi` mean-reversion (Ultimate RSI red→long, green→flat).
2. **Trend**: price above SMA(250), applied **entry-only**.
3. **Quality score** (≥2 of 3, causal):
   - constructive finished bar (`close >= open`)
   - volume ≥ 0.85 × 20-bar average
   - ATR% ≤ 1.35 × expanding median of *prior* ATR%
4. **Sizing**: `signal_scale = 0.225`.

## Integrity

- Parameters frozen in `hunt_config.json` before holdout evaluation.
- Train window end registered: `2025-08-01`.
- Holdout: `2025-08-01` → `2026-07-11` (no retune after seeing results).
- Evaluation contract: `EQUITY_WINNER_BAG`, `source=local`, `interval=1H`, cash `$1,000`.

## Relationship to prior models

| Model | Role |
|-------|------|
| `v45_ultimate_rsi` | Primary mean-reversion teacher |
| `v50_high_win_rate` | Prior high-WR baseline (v45 + SMA250, no quality score) |
| `v49_precision_trend` | Inspiration for entry-episode / score gates (different teacher) |
| `v39d_confluence` | Return champion baseline for comparison, not a WR peer |
