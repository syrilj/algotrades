# Algorithmic Trading Research Platform

A full-stack quantitative trading R&D system that **designs, backtests, evolves, calibrates, and deploys** automated equity and options strategies. It pairs a Python signal-engine + backtesting pipeline with a Next.js trade desk and a FastAPI market-runtime service, all governed by a hash-pinned model registry with fail-closed promotion gates.

> **Disclaimer:** This is a research and educational project. Every performance number here is a **simulated, cost-stressed backtest** — not live trading results — and nothing in this repository is financial advice.

---

## Highlights

- **Versioned signal engines** — 130+ modular, individually versioned `SignalEngine` models (`models/poc_va_macdha/v*`) that emit point-in-time long/flat target positions from OHLCV + engineered features.
- **Cost-aware, causal backtesting** — walk-forward runner with per-trade slippage + commission, out-of-sample lockbox holdouts, and deterministic full-window replay (`tools/`, `services/market_runtime/adaptive_replay.py`).
- **Model evolution engine** — multi-generation genetic mutation and ensemble search that breeds and ranks candidate strategies (`tools/evolve/`, `tools/neuro_evolve.py`, `runs/evolve_*`).
- **Governed deployment** — a SHA256-pinned deployment manifest with ordered, fail-closed fallbacks and an explicit rollback model (`models/poc_va_macdha/DEPLOYMENT_MANIFEST.json`).
- **Live/runtime stack** — FastAPI service streams completed bars and generates trade tickets with an exactly-once, idempotent bar ledger (`services/market_runtime/`).
- **Trade desk UI** — a dense, institutional Next.js + React 19 + TypeScript + Tailwind dashboard with ~30 API routes for scanning, analysis, execution, options, gamma exposure, and model leaderboards (`apps/trade-desk/`).
- **Anti-overfit discipline** — walk-forward folds, lockbox holdouts, cost-stress tests, Platt probability calibration, deflated Sharpe, and Wilson confidence intervals on win rates before any model is promoted.

## How a Model Works

Each model is a self-contained bundle under `models/poc_va_macdha/<version>/`:

```
v72_dual_sleeve/
├── signal_engine.py   # the strategy: features → target position
├── config.json        # universe, interval, costs, engine, strategy params
├── hunt_config.json   # search / gate parameters
├── meta_xgb_final.json# optional XGBoost meta-classifier (trade filter)
└── results.json       # frozen backtest evidence
```

1. **Features → signal.** `SignalEngine` consumes point-in-time OHLCV and derived features (MACD histogram, VPA/volume, RSI, regime and volatility context) and outputs a target position (long / flat) per bar — strictly causal, no look-ahead.
2. **Meta-filter.** Higher-tier models gate raw signals through an **XGBoost meta-classifier** trained on realized outcomes to suppress low-quality trades and raise win rate.
3. **Confidence.** Models expose `last_confidence` as **ordinal** expert support — deliberately *not* treated as a win probability unless a cross-fitted Platt calibrator has passed (see `execution_readiness` in the manifest). This honesty gate is enforced in the deployment contract.
4. **Ensembling / routing.** "Sleeve" and "router" models (e.g. `v72_dual_sleeve`) stack a high-win-rate sniper expert first, then a scaled core expert, under a max-weight cap — with each frozen expert's dependency hashes verified before load.

## Evolution & Promotion Pipeline

```
generate mutations ──▶ walk-forward backtest ──▶ rank (deflated Sharpe, cost-stressed)
       ▲                                                     │
       │                                                     ▼
   ensemble/breed ◀── promotion gates ◀── locked out-of-sample holdout
```

A candidate only replaces the champion if it clears promotion gates on data it was never trained on. Evidence (STATE.json / COMPARE.json), integrity hashes, and calibration status are recorded in the manifest so every live model is fully auditable and reproducible.

## Representative Backtest Results

7-symbol US equity basket (`TSLA`, `MU`, `SPY`, `IONQ`, `APLD`, `XLP`, `QQQ`), 1-hour bars, `$1,000` starting capital, local adjusted data, 5 bp slippage + 5 bp commission. Simulated only:

| Model | Return | Max Drawdown | Sharpe | Trades | Win Rate |
|-------|--------|--------------|--------|--------|----------|
| `v72_dual_sleeve` (promoted live book) | **+513%** | −19.4% | **3.08** | 179 | 72% |
| `v39d_confluence` (best pure model) | +357% | −13.4% | 2.82 | 135 | 67% |
| `v50_high_win_rate` (precision sleeve) | +109% | −19.5% | 1.87 | 52 | **86.5%** |

Corrected-causal, cost-stressed per-model benchmarks — with Wilson 95% confidence intervals on win rate — are tracked under `runs/<model>/LEADERBOARD.md`. The repo intentionally reports these intervals rather than headline point estimates, and blocks probability-sized execution until a calibrator passes.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     apps/trade-desk                          │
│        Next.js dashboard (scan / analyze / execute /         │
│         options / gamma / leaderboard) · ~30 API routes      │
└───────────────────────┬─────────────────────────────────────┘
                        │ REST / WebSocket
┌───────────────────────▼─────────────────────────────────────┐
│                 services/market_runtime                      │
│   FastAPI + uvicorn: bars, /plan tickets, adaptive replay,   │
│   idempotent completed-bar ledger, decision engine           │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────┐
│                        tools/                                │
│   backtest runner · dynamic model ranker · evolve/farm ·     │
│   calibration · stress tests · live_plan · analysis_agent    │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────┐
│                      models/...                              │
│   SignalEngine + config per version · XGB meta-classifiers · │
│   hash-pinned deployment manifest · calibration artifacts    │
└──────────────────────────────────────────────────────────────┘
```

## Tech Stack

- **Backend / ML** — Python 3.13, pandas, NumPy, XGBoost, scikit-learn, FastAPI, uvicorn
- **Data** — local parquet cache, `yfinance`, `lse-data`; explicit train/holdout data contracts
- **Frontend** — Next.js 15, React 19, TypeScript, Tailwind CSS, framer-motion, three.js
- **Infra** — Docker, virtualenv, file-based experiment tracking, GitHub Actions CI
- **Testing** — pytest (Python) + Sucrase/tsc unit tests (frontend)

## Quick Start

```bash
# Set up Python environment
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run the promoted baseline on the equity basket
.venv/bin/python tools/baseline_manifest.py --cash 1000

# Start the market runtime service
uvicorn services.market_runtime.server:app --reload

# Start the trade desk (in another terminal)
cd apps/trade-desk
npm install
npm run dev
```

## Repo Layout

| Path | Purpose |
|------|---------|
| `models/` | Versioned signal engines, configs, meta-classifiers, deployment manifest |
| `tools/` | Backtesting, evolution, calibration, feedback loops, live planning |
| `apps/trade-desk/` | Next.js / React trading dashboard |
| `services/market_runtime/` | Live data, replay ledger, and ticket-generation service |
| `tests/` | Python + frontend unit and integration tests |
| `docs/` | Research notes and design specs |
| `AGENTS.md` | Working notes for current champion models and run commands |

## Status

Active R&D project. The current promoted live book is `v72_dual_sleeve` (hierarchical sniper + core sleeve) with `v39d_confluence` as the ordered fallback. New variants are evaluated through walk-forward backtests and fail-closed promotion gates before they can replace the champion. Probability-sized execution stays blocked until a cross-fitted calibrator passes — by design.

---

*Built as a research / portfolio demonstration of full-stack + quantitative + ML engineering. Not intended for live deployment without independent review and risk controls.*
