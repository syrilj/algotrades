# Hypothesis — v23_devin_overlay

v20b's frozen v15 meta-XGB sizing already has edge, but it ignores the volume-z
research (VOLUME_Z_META.json: `vol_z>=1` lifts OOS WR). By adding a small,
non-linear probability boost to the meta-XGB output when the 20-day volume
z-score is elevated, we increase position size on higher-conviction entries
and reduce or skip lower-conviction entries, raising total return and profit
factor while keeping drawdown contained.

The overlay is intentionally small (max ±0.03 proba delta) to avoid distorting
the proven meta-XGB signal, and is applied to the v20b primary stack unchanged.
Sector/QQQ RS scores are computed but currently disabled because they showed no
measurable additive lift in this window.

No new ML is trained on price; the overlay is a hand-crafted, research-backed
conviction scaler.
