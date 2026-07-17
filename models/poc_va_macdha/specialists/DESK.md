# Desk specialists (v39d-based)

## What broke before

The original `v65_spec_*` models used a **thin** VA/VWAP engine **without**
the champion `v39d_confluence` XGB meta / confluence stack. On single-name
backtests they often lost money (e.g. TSLA thin specialist −30% vs v39d +34%).

## What works now

Every desk specialist is a **fork of `v39d_confluence`**:

- same signal engine + XGB meta (`meta_xgb_final.json`) + candidate ledger
- **routing DNA** chosen by bakeoff (`tools/bakeoff_specialists.py`)
- `TRADE_DROP` / `REGIME_FLAT` cleared so single-name packs actually trade

Rebuild / re-bake:

```bash
.venv/bin/python tools/bakeoff_specialists.py --quick --promote
.venv/bin/python tools/bakeoff_specialists.py --symbols AVGO,TSM,HOOD --promote
```

Results: `runs/bakeoff_specialists/LEADERBOARD.md`

## DNA edge (multi-lock beat of v39d default)

These names earned a **different** routing DNA that multi-locked (better ret +
Sharpe, DD not much worse):

| Symbol | DNA | Approx edge vs v39d default |
|--------|-----|-----------------------------|
| NVDA | dna_apld | +0.9% → +6.6%, sh 0.10 → 1.30 |
| META | dna_tsla | −1.7% → +2.8% |
| MSTR | dna_tsla | +6.6% → +11.5% |
| AVGO | dna_mu | +8.6% → +16.6% |
| PLTR | dna_tsla | −10.8% → +10.9% |
| CRWV | dna_tsla | +21.1% → +22.2%, better DD/sh |
| AMZN | dna_mu | −8.1% → +12.7% |
| MSFT | dna_tsla | −7.1% → +9.4% |
| HOOD | dna_arm | −2.7% → +49.0% |
| ASTS | dna_apld | +12.0% → +24.3% |
| TSM | dna_mu | −6.3% → +14.8% |
| VRT | dna_tsla | −16.8% → +2.9% |

Bag names where **native DNA already is best** (specialist = v39d DNA):

TSLA (`dna_tsla`), MU (`dna_mu`), IONQ (`dna_ionq`), APLD (`dna_apld`),
AAPL/SPY/SOFI/SNDK/COIN/SMCI/AMD (best default or non-multi-lock).

## Routing

Source of truth: `models/poc_va_macdha/DESK_ROUTING.json`

- `bakeoff_promoted` / `dna_edge`: multi-lock DNA win
- All mapped symbols still get a working `v65_spec_*` engine (v39d-based)
- Unmapped symbols: competitive router → `v39d_confluence` / `v67_universal_specialist`

```bash
.venv/bin/python tools/analysis_agent.py --symbol PLTR --json
.venv/bin/python tools/trade_desk.py HOOD --model auto
```
