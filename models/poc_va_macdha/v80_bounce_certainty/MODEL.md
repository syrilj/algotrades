# v80_bounce_certainty

Calibrated logistic **bounce-from-down-day** predictor.

- Horizon: 5 bar(s)
- Context: train/eval on days with ret_1d < 0
- Features: price structure + support/resistance + QQQ/SPY macro; live desk model optional
- Holdout Brier: 0.1625
- Holdout base rate: 0.733
- High-conf threshold: 0.780
- High-conf hit-rate (n=832): 0.8725961538461539
- Lift vs base: 0.13971283658482314
- INFQ defaults to native stock (not IONQ) unless `--apply-desk-alias`.
- Live: live_plan model + macro_regime + support stack + options/GEX.
