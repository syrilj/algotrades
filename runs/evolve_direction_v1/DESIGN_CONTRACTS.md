# evolve_direction_v1 — Interface Contracts (PINNED)

Authoritative interface spec for all work packets. If code and this doc disagree, this doc wins;
if you must deviate, record the deviation in your summary. Full design: `/Users/syriljacob/.claude/plans/i-want-to-make-tidy-pascal.md`.

## Honesty preamble (copy verbatim into runs/evolve_direction_v1/README.md)

> $1k→$1M is not a planning input. Repo findings: every leverage escalation failed OOS;
> v13_long_oos (2020–2026 1D) failed PASS_BAR. This system optimizes direction-signal quality and
> drawdown control. The likely first finding is that v39b's OOS-honest baseline is far below +365%
> and 2022 fails — that is the system working, not failing. Every trial, including failures, is
> logged. Selection happens ONLY on purged out-of-sample folds; the lockbox is opened once per
> campaign and its result is binding.

## Verified environment facts (do not re-derive)

- Python: `/Users/syriljacob/Desktop/TradingAlgoWork/.venv/bin/python` (python3.13). Repo root: `/Users/syriljacob/Desktop/TradingAlgoWork`.
- Backtest engine: installed pkg `.venv/lib/python3.13/site-packages/backtest/` (`vibe-trading-ai==0.1.11`). Entrypoint `backtest.runner.main(run_dir)`; run dir needs `config.json` + `code/signal_engine.py`.
- Equity engine (`backtest/engines/global_equity.py`): US commission is **hardcoded 0 by design**; `slippage_us` **is** read from config (line 44, default 0.0005), applied per side to fills. Config key `commission` is IGNORED for `.US` — never write it.
- Signals: `SignalEngine.generate(data_map) -> Dict[symbol, pd.Series]` of target weights in [-1,1]; shifted 1 bar; fills at next bar open; sum(|w|) normalized to ≤ 1.
- Loader cache: env `VIBE_TRADING_DATA_CACHE=1`, `VIBE_TRADING_DATA_CACHE_ROOT`; key = exact (source, symbol, timeframe, start, end) — a full-range snapshot does NOT serve sub-window requests.
- Local loader (`backtest/loaders/local_loader.py`, source name `"local"`): reads `~/.vibe-trading/data-bridge/config.yaml`, entries `{symbol, type: parquet|csv, path, columns?, date_format?}`; slices requested [start,end] from the file; tz dropped automatically; interval arg effectively ignored (file granularity rules).
- Metrics annualization (`backtest/metrics.py`): 1H → 1764 bars/yr, 1D → 252.
- `backtest/validation.py`: `run_validation` / `monte_carlo_test` (trade-ORDER shuffle → DD-path only; Sharpe p-value uninformative — document as such) / `bootstrap_sharpe_ci` / `walk_forward_analysis`. Never called by runner — we invoke post-hoc.
- Governance: `models/_shared/PASS_BAR.json` (gates + utility_reward + ml_rules.forbid). Findings API: `tools/findings.py::append_finding(row) -> row` (appends to `models/_shared/findings.jsonl`).
- Evolve chassis: `tools/evolve/{farm,mutations,scoring,gates,auditor,meta_train,pipeline}.py` — extend, don't fork. `scoring.utility_score` already implements PASS_BAR utility_reward.
- yfinance 1H history: ~730-day rolling cliff (start ≈ 2024-07-13 as of 2026-07-12, slides daily). 1D history: stable to 2018+.
- Shell note: `~/.zshenv` prints a harmless cargo error line — ignore it in subprocess output.

## Data strategy (PINNED)

- **Track A (1H)**: engine configs use `"source": "local"`. Snapshot writes per-symbol 1H parquet under `data_cache/1h/` and a bridge config `data_cache/bridge_config_1h.yaml`. The loop copies the right bridge config to `~/.vibe-trading/data-bridge/config.yaml` before each batch (`loop_core.use_bridge("1h"|"1d")`); Track A and Track B batches never run concurrently.
- **Track B (1D, 2020→)**: engine configs use `"source": "local"` with `data_cache/bridge_config_1d.yaml` (per-symbol 1D parquet under `data_cache/1d/`, 2018-01-01→today).
- If `~/.vibe-trading/data-bridge/config.yaml` already exists at snapshot time, back it up beside itself as `config.yaml.bak-<date>` before overwriting.
- Reference copies for analytics (regime build, direction report) read the SAME parquet files directly — one source of truth.
- `data_cache/MANIFEST.json`: `{generated_utc, package_version, entries: [{symbol, interval, path, start, end, rows, sha256}]}`. sha256 = hash of the parquet file bytes.

## Universe (PINNED)

```
CORE_BAG   = TSLA.US MU.US SPY.US IONQ.US APLD.US
GATE_ETFS  = QQQ.US XLP.US HYG.US LQD.US
CANDIDATES = ARM.US COIN.US RKLB.US NVDA.US PLTR.US MSTR.US
SECTORS    = XLK.US XLF.US XLE.US XLV.US XLY.US XLI.US XLU.US XLB.US XLC.US
INDICES    = ^VIX ^TNX            (1D only, regime inputs; best-effort)
```
1H snapshot: CORE_BAG + GATE_ETFS + CANDIDATES (window: earliest available → today).
1D snapshot: everything, 2018-01-01 → today. yfinance tickers: strip `.US` (`TSLA`), indices as-is (`^VIX`).

## Fold layout (PINNED — Track A 1H)

Warmup pad: 45 calendar days before OOS start (run window = [warmup_start, oos_end]); metrics computed ONLY on the OOS slice. Meta train window = 2024-08-01 → train_end, labels purged at the boundary.

| Fold | train_end | OOS start | OOS end |
|---|---|---|---|
| F1 | 2025-03-31 | 2025-04-16 | 2025-07-15 |
| F2 | 2025-06-30 | 2025-07-16 | 2025-10-15 |
| F3 | 2025-09-30 | 2025-10-16 | 2026-01-15 |
| F4 | 2025-12-31 | 2026-01-16 | 2026-04-15 |
| LOCKBOX | 2026-03-31 | 2026-04-16 | 2026-07-11 |

Gap: nominal 15 calendar days; `derive_gap_days()` recomputes max(15, ceil(p95_holding_days)+2) from a trades.csv and the campaign records the derived value (folds themselves stay fixed; if derived gap > 16, flag in audit).
LOCKBOX: never scored during evolution; opened once per campaign at promotion; result binding.

Track B (1D): train 2020-01-01→Dec-31(Y), 15d gap, OOS = calendar year Y+1, for OOS years 2021, 2022, 2023, 2024, 2025, 2026H1 (2026-01-01→2026-07-11).

## Unified objective (PINNED — models/_shared/OBJECTIVE.json)

```
U_f     = ret + 0.35*min(sharpe,3) + 0.15*min(calmar,10) + 0.05*wr
          - 0.55*max(0,|dd|-0.15) - 50*(|dd|>=0.25)
FITNESS = reliability(n_pooled,40) * ( mean_f(U_f) - 0.5*std_f(U_f) )
```
ret = OOS-slice total return (decimal), wr in [0,1], dd negative decimal, calmar = ret_annualized/max(|dd|,0.02), std over the 4 fold utilities (ddof=0). reliability(n,40)=min(1,n/40) (exists in scoring.py). `model_registry.score_metrics` is UI-only — never used for selection.

## New-file ownership & signatures (PINNED)

WP1 — `tools/snapshot_data.py` (CLI: `snapshot`, `verify`), `data_cache/*` (generated), `tests/evolve_v1/test_snapshot_manifest.py`
WP2 — `tools/evolve/folds.py`, `tools/evolve/costs.py`, `models/_shared/OBJECTIVE.json`, append-only additions to `tools/evolve/scoring.py`, `tests/evolve_v1/test_folds_costs.py`
WP3 — `tools/evolve/stats.py`, `tests/evolve_v1/test_stats.py`
WP4 — `tools/regime.py`, `models/_shared/REGIME_SPEC.json`, `tools/evolve/regime_gate.py`, `tests/evolve_v1/test_regime.py`
WP6 — `tools/direction_report.py`, `tools/evolve/audit_gen.py`, `tools/evolve/validate_run.py`, `models/_shared/AUDIT_GATES.json`, `tests/evolve_v1/test_direction_audit.py`
WP5 — `tools/evolve/loop_core.py`, appends to `tools/evolve/mutations.py`, `runs/evolve_direction_v1/{driver.py,README.md}`, `tests/evolve_v1/test_loop_smoke.py`

Touch ONLY your owned files. All tests under `tests/evolve_v1/` (create dir; plain pytest, run with `.venv/bin/python -m pytest tests/evolve_v1/<your file> -q`).

```python
# folds.py
FOLDS_1H: list[dict]      # keys: name, train_start, train_end, gap_days, oos_start, oos_end, warmup_start (ISO str)
LOCKBOX: dict             # same shape, name="LOCKBOX"
FOLDS_1D_TRACKB: list[dict]
def derive_gap_days(trades_csv: str|Path) -> int
def slice_oos(run_dir: str|Path, oos_start: str, oos_end: str) -> tuple[pd.DataFrame, pd.Series]
    # trades filtered to entry_time >= oos_start & <= oos_end (entry basis);
    # equity.csv sliced to [oos_start, oos_end], rebased to 1.0 at slice start
def fold_metrics(trades: pd.DataFrame, equity: pd.Series, bars_per_year: int) -> dict
    # keys: ret, sharpe, calmar, dd, wr, pf, n, expectancy, avg_hold_days
def purged_label_mask(entry_times: pd.Series, horizon_days: float, train_end: str) -> "np.ndarray[bool]"
    # True = KEEP (label horizon ends on/before train_end)

# costs.py
SLIPPAGE_BASE = 0.0010; SLIPPAGE_STRESS = 0.0020
def expectancy_after_costs(trades: pd.DataFrame, slippage_per_side: float) -> float   # $/trade mean net of ADDED friction delta vs engine-applied
def probe_slippage_applied(run_dir: str|Path, expected_slippage: float, n_probe: int = 3) -> None  # raises RuntimeError on drift

# scoring.py (append only)
def fold_utility(m: dict) -> float
def fold_fitness(fold_ms: list[dict]) -> float   # applies reliability on pooled n internally

# stats.py
def signflip_permutation(pnls: "sequence[float]", n_perm: int = 2000, seed: int = 7) -> dict  # {p_value, obs_mean, n, n_perm}
def deflated_sharpe(sr_hat: float, n_obs: int, skew: float, kurt: float,
                    n_trials: int, var_trials_sr: float) -> dict  # {dsr, sr0, psr}; kurt = Pearson (normal=3)

# regime.py CLI
#   build --start 2018-01-01 --end <today> [--out models/_shared/regime/regime_daily.parquet]
#   uses data_cache/1d parquet if present else yfinance; STRICTLY causal (rolling ops only)
# parquet columns: index date; score (float [-1,1]); label (risk_on|neutral|risk_off);
#   comp_index_trend, comp_defensive, comp_vix, comp_rates, comp_credit (floats in [-1,1]);
#   sector_ok_<ETF> (bool per SECTORS member)
# regime_gate.py — STANDALONE reader (stdlib+pandas only; no repo imports; copied into run code/ dirs)
def regime_at(date, parquet_path=None) -> dict|None      # last row with index <= date - 1 day  (t-1 lag)
def gate(symbol: str, date, sector_map: dict, parquet_path=None) -> dict
    # {index_ok: bool, sector_ok: bool, regime: str, score: float}

# direction_report.py
def build_direction_report(trades_csv, bars: dict[str, pd.DataFrame], ks=(3,5,10),
                           regime_parquet=None) -> dict
# CLI: --run-dir --out DIRECTION.json (+ .md); hit@k = sign(close[t+k]-entry) matches called side;
# binomial 95% CI (Wilson) + one-sided p vs 0.5; MFE/MAE medians within holding period

# validate_run.py
def run_package_validation(run_dir) -> dict  # {mc_dd_pvalue, sharpe_ci_low, sharpe_ci_high, notes}

# audit_gen.py
def write_audit(candidate: dict, gate_results: list[dict], out_path) -> Path
# gate_results item: {gate_id:int, name, threshold, measured, passed: bool, notes}
```

## trials.jsonl row (PINNED — models/_shared/trials.jsonl)

```json
{"ts": "...", "campaign_id": "c1", "gen": 3, "variant_id": "g3_v07", "parent": "g2_v02",
 "mutations": [{"op":"param_perturb","field":"vol_z_min","delta":0.1,"hypothesis":"..."}],
 "fold_metrics": {"F1": {...fold_metrics dict...}, "F2": {}, "F3": {}, "F4": {}},
 "fitness": 0.0, "package_version": "0.1.11", "manifest_sha": "<sha of MANIFEST.json>",
 "status": "scored|error", "notes": ""}
```

## Audit gates (PINNED — models/_shared/AUDIT_GATES.json, 13 gates)

1 pooled PASS_BAR (PF≥1.2, Sharpe≥0.5, n≥40, expectancy>0 after costs) + |DD|≤0.25 every fold ·
2 U_f>0 in ≥3/4 folds, n≥8/fold · 3 sign-flip p≤0.05 · 4 MC DD-path p≥0.05 · 5 bootstrap Sharpe
CI low>0 · 6 DSR≥0.95 · 7 PASS_BAR holds at slippage 0.0020 · 8 ±20% perturb: mean fitness ≥0.6×,
none<0 · 9 Track B floor (pooled ret>0, |DD|≤0.30); DURABLE_CLAIM = full PASS_BAR on Track B ·
10 expectancy>0 in ≥2/3 regime slices, no slice |DD|>0.25 · 11 hit@5d>50% binomial p≤0.10 +
expectancy>0 · 12 auditor.py source scan clean + meta WF-stitched · 13 LOCKBOX fitness>0, binding.

## Style & discipline

- Follow existing tools/evolve code style (type hints, short docstrings, module docstring stating purpose).
- Determinism: every stochastic function takes an explicit seed. No network calls at import time.
- No lookahead: any rolling computation must only use data ≤ t. If you can't prove it, don't ship it.
- Tests must RUN GREEN before you report done (`.venv/bin/python -m pytest tests/evolve_v1/... -q`).
