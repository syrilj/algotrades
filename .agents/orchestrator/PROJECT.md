# Project: v83_adaptive_regime

## Architecture
The `v83_adaptive_regime` model builds upon the hierarchical `v72_dual_sleeve` design, combining `v71_live_confidence` (high-win-rate sniper) and `v39d_confluence` (return-champion core). It introduces a regime detection layer using point-in-time microstructure features from `tools/institutional_flow/features.py`.

```
Data Stream (1H)
       │
       ├──► [features.py] ──► Regime Detection (trend, vol, etc.)
       │                                │
       │                                ▼
       ├──► v71 High-WR Sniper ──► Dynamic Route & Scale
       ├──► v39d Core Sleeve   ──► (Sleeve weights, stop adjustment)
       │                                │
       ▼                                ▼
[GlobalEquityEngine + Almgren-Chriss impact] ──► Backtest Metrics
```

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | Baseline & Test Infra | Run baseline `v72` under AC impact; implement E2E test cases | None | DONE |
| 2 | v83 Implementation | Create v83 model with regime-based sleeve weighting/gating | M1 | DONE |
| 3 | Backtest & Optimize | Run and optimize v83 backtests under AC impact to meet targets | M2 | IN_PROGRESS |
| 4 | Verification & Audit | Verify passing E2E tests, clean auditor run, compile report | M3 | PLANNED |

## Interface Contracts
### `v83_adaptive_regime` ↔ `backtest.runner`
- Exported class: `SignalEngine`
- Signature: `generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]`
- Config settings:
  - `impact_model`: `"almgren_chriss"`
  - `ac_eta`: `0.1`
  - `ac_gamma`: `0.0`
  - `ac_beta`: `0.5`
  - `ac_adv_days`: `20`
  - `ac_vol_days`: `20`
- Target outputs:
  - `self.last_confidence`: per-trade confidence metric (0.0 to 1.0)
  - `self.last_sleeve`: active sleeve ID (0=Flat, 1=Sniper, 2=Core, 3=Both)

### `v83_adaptive_regime` ↔ `tools/institutional_flow/features.py`
- Function call: `compute_features(df, params=None)`
- Input: sorted OHLCV `pd.DataFrame`
- Output: `pd.DataFrame` containing `trend`, `vol_regime`, `atr_pct`, etc.
