# Deploy: Trade Desk (FE) + market-runtime (BE)

## Architecture

| Surface | Host | Role |
|---------|------|------|
| **Trade Desk** (`apps/trade-desk`) | **Vercel** (or any Next.js host) | UI + thin API routes |
| **market-runtime** (`services/market_runtime`) | **Render / Cloud Run / Docker** | Plan, analyze, health, stream |

Production rule: set `MARKET_RUNTIME_URL` on the frontend so `/api/live-plan` and `/api/analysis-agent` call the Python service over HTTP. Without it, local monorepo mode may spawn `tools/live_plan.py` / `tools/analysis_agent.py` (dev only — not available on Vercel).

```
Browser → Next.js (Vercel)
            ├─ static UI
            └─ /api/live-plan  ──HTTP──►  market-runtime /plan
            └─ /api/analysis-agent ────►  market-runtime /analyze
```

## Backend (Render / Cloud Run)

### Docker (recommended)

From monorepo root:

```bash
docker build -t market-runtime .
docker run --rm -p 8000:8000 \
  -e LSE_API_KEY="${LSE_API_KEY:-}" \
  -e MARKET_RUNTIME_API_TOKEN="${MARKET_RUNTIME_API_TOKEN:?set a production API token}" \
  market-runtime
```

Smoke:

```bash
curl -s http://127.0.0.1:8000/health | jq .
curl -s -X POST http://127.0.0.1:8000/plan \
  -H "Authorization: Bearer ${MARKET_RUNTIME_API_TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"SPY","account":1000,"no_model":true}' | jq '{ok,action,runtime}'
```

### Local without Docker

```bash
# monorepo root, venv active
export PYTHONPATH="$(pwd):$(pwd)/tools:$(pwd)/services"
uvicorn services.market_runtime.server:app --host 0.0.0.0 --port 8000
```

### Env vars (backend)

| Var | Required | Notes |
|-----|----------|--------|
| `LSE_API_KEY` | Required in production | Sole production source for live candles, streaming, options flow, and market context. Development may use yfinance only for local diagnostics; production never falls back. |
| `MARKET_RUNTIME_ENV` | Yes in deployment | The image sets `production`; production refuses to start without an API token and defaults stream-dependent requests to fail closed. |
| `MARKET_RUNTIME_API_TOKEN` | **Yes in production** | Shared bearer token required by backend API middleware. Configure the same server-only value on Trade Desk; never use a `NEXT_PUBLIC_*` variable. |
| `PORT` | No | Default `8000` |
| `MARKET_RUNTIME_REQUIRE_STREAM` | No | Explicit stream-policy override. Production defaults to `1`; development defaults to `0`. |
| `MARKET_RUNTIME_MAX_SYMBOLS` | No | Stream catalog cap |

## Frontend (Vercel)

1. Root directory: `apps/trade-desk`
2. Build: `npm run build` / Start: `npm run start`
3. Env:

| Var | Required in prod | Example |
|-----|------------------|---------|
| `MARKET_RUNTIME_URL` | **Yes** | `https://market-runtime-xxxx.onrender.com` |
| `MARKET_RUNTIME_API_TOKEN` | **Yes in production** | Same server-only shared bearer token configured on the backend; frontend API routes forward it. |

Copy `apps/trade-desk/.env.example` → Vercel project env.

### Local FE against local BE

```bash
# terminal 1 — backend
uvicorn services.market_runtime.server:app --host 127.0.0.1 --port 8000

# terminal 2 — frontend
cd apps/trade-desk
export MARKET_RUNTIME_URL=http://127.0.0.1:8000
export MARKET_RUNTIME_API_TOKEN="replace-with-the-same-backend-token"
npm run dev
```

When `MARKET_RUNTIME_API_TOKEN` is configured, direct backend requests must send
`Authorization: Bearer <token>`. Keep `/health` available to the host's health
probe according to the backend middleware policy. Rotate the token by updating
both services together, then redeploying the backend before the frontend.

## Reproducible verification

The container and CI both use Python 3.11. Production installs the exact direct
dependencies in `requirements-runtime.txt`; CI adds only pytest and parquet
support from `requirements-ci.txt`.

```bash
python3.11 -m venv .venv-ci
.venv-ci/bin/python -m pip install -r requirements-ci.txt
.venv-ci/bin/python -m pytest

cd apps/trade-desk
npm ci
npm test
npm run typecheck
```

The image runs as the unprivileged `runtime` user. Mount writable state at
`/app/data`, `/app/data_cache`, or `/app/runs`; `.env`, research runs, caches,
databases, Git history, and frontend dependencies are excluded from the build
context.

## Core operator paths

1. **Command / Analyze** — symbol → verdict/ticket (`/`, `/analyze`, analysis-agent)
2. **Execution / Live plan** — `/live` → `/api/live-plan` → backend `/plan`
3. **Portfolio / Lab** — positions, leaderboard (read models + ledger; research tools may still need monorepo for evolve/backtest)

Research-only spawns (evolve, robust backtest) are **not** day-one production surfaces on Vercel.

## Math / display contracts

- Risk budget = `account × risk_pct` (fraction, e.g. `0.005` = 0.5%)
- Shares = `floor(risk_budget / risk_per_share)` capped by sleeve notional
- `formatPct` multiplies fractions by 100 once — never pass already-percent values
- Backend is source of truth for size/risk; UI only formats

See `tests/test_risk_units.py` and `apps/trade-desk/src/lib/format.test.ts`.
