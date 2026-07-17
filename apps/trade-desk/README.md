# Trade Desk (frontend)

Next.js operator UI for analyze, live plan, portfolio, and lab.

## Local development

```bash
# Backend (repo root) — required for production-style plan/analyze
uvicorn services.market_runtime.server:app --host 127.0.0.1 --port 8000

# Frontend
cp .env.example .env.local   # set MARKET_RUNTIME_URL=http://127.0.0.1:8000
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

Without `MARKET_RUNTIME_URL`, API routes may spawn monorepo Python (dev-only; not available on Vercel).

## Scripts

| Command | Purpose |
|---------|---------|
| `npm run dev` | Turbopack dev server |
| `npm run build` / `start` | Production Next build |
| `npm run typecheck` | `tsc --noEmit` |
| `npm test` | Format, routes, backend URL, action color contracts |

## Production deploy

See **[`docs/DEPLOY.md`](../../docs/DEPLOY.md)** (repo root):

- **Frontend:** Vercel, root `apps/trade-desk`, env `MARKET_RUNTIME_URL`
- **Backend:** Docker / Render / Cloud Run from monorepo `Dockerfile`

Core flows that hit the remote backend: `/api/live-plan` → `POST /plan`, `/api/analysis-agent` → `POST /analyze`.

## LSE vault data

`LSE_API_KEY` stays on the Python market-runtime service. The frontend never
receives it. The runtime exposes validated read-only routes for `/data/usage`,
`/data/catalog`, `/data/meta`, `/data/candles`, `/data/series`, reference
datasets, options chains, options prints, and option candles.

The shell calendar prefers live `/data/reference/economic_calendar` rows and
falls back to its verified Fed/BLS/BEA schedule. Options flow prefers LSE
time-and-sales and falls back to the existing yfinance chain proxy in local
monorepo development.
