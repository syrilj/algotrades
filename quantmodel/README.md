# quantmodel — Donchian Swing Trend Research System

Production-oriented, fully auditable **long-only US equity** Donchian swing-trend research package for a hypothetical **$1,000,000** account.

## Question this system answers

> Does a volume-confirmed Donchian breakout strategy produce a robust, net-of-cost, out-of-sample edge strong enough to justify live deployment?

## Priorities

1. Correctness  
2. Reproducibility  
3. Leakage prevention  
4. Survivorship-bias control  
5. Risk containment  
6. Experiment tracking  
7. Simple components first  
8. Auditability  

**Research software only. Live order routing is disabled.**

## Quick start

```bash
cd quantmodel
python -m pip install -e ".[dev]"
# Fixed research profile (wider stops, Donchian trail, lighter filters)
python run_demo.py --config configs/demo_v2_fixed.yaml
# Ablation table
python scripts/run_ablations.py configs/demo_v2_fixed.yaml
# LSE cache (deploy blocked — survivorship bias)
python scripts/run_backtest.py --config configs/lse_v2_fixed.yaml
```

Artifacts land under `artifacts/runs/<run_id>/` with:

- `config.yaml`, `manifest.json`, `metrics.json`
- `equity_curve.csv`, fills/orders/signals parquet or csv
- `audit_report.md`, `audit_report.html`

## Data

| Vendor | Config | Notes |
|--------|--------|-------|
| `synthetic` | `configs/demo_synthetic.yaml` | Deterministic multi-name universe with splits/delists/earnings |
| `lse_cache` | `configs/base.yaml` | Reads monorepo `data_cache/lse/1d` (**survivorship-biased**) |
| `local_cache` | — | `data_cache/1d` fallback |

LSE/cache runs are **DEPLOYMENT_BLOCKED** until a delisted point-in-time vendor is wired.

## Core strategy (defaults)

- Entry: close > prior 55d high **and** volume ≥ 1.5× prior 50d median **and** close > SMA200 **and** SPY > SMA200  
- Exit: prior 20d low **or** ATR(20)×2 stop **or** kill switch / delist  
- Risk: 0.5% equity per trade, 4% portfolio heat, −12% kill / −8% shadow resume  
- Execution: next open + slippage/commission  

All parameters live in YAML (`configs/`). Invalid configs fail loudly via JSON Schema.

## Tests

```bash
pytest -q
```

## Package layout

See the Implementation and Audit Specification. Main code under `src/quantmodel/`.

## License

MIT
