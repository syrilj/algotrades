# v16 meta_risk — hypothesis

**Claim:** Stacking v14 ATR hard-stop / trail + half-Kelly vol scaling on top of the v15 meta-XGB gate/size improves the Sharpe–PF–DD tradeoff vs meta alone, without undoing meta zero-outs.

**Mechanism**
1. Primary side = v13 specialists (unchanged).
2. Meta-XGB decides entry yes/no and size bucket `{0, 0.25, 0.5, 1.0}` at thr=0.6.
3. Risk overlay only scales *positive* meta sizes by vol (`med_atr/atr`) and Kelly fraction; meta zeros stay zero.
4. In-trade: ATR hard stop (1.5), trail after arm (1.0 / 2.5), soft exits gated like v14 (flicker ignored once armed).

**Caveat:** Same full-sample frozen booster as v15 — treat metrics as upper-bound until WF stitch.

**Success:** Beats v15 on joint (Sharpe, PF, DD). Else keep WINNER at v15_meta_xgb.
