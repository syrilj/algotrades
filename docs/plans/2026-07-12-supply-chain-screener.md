# Supply-Chain Screener

Date: 2026-07-12

## Goal

A new desk page (`/supply-chain`) that takes a big-cap ticker, discovers its suppliers using web/LLM extraction, enriches each supplier with fundamentals and price correlation, and surfaces tradeable plays with deep-links into Analyze.

## Scope

Full feature for any sector. MVP-to-v1 in this PR:

1. Python discovery tool (`tools/supply_chain.py`) with pluggable providers.
2. `/api/supply-chain` POST route.
3. `/supply-chain` page with ranking table + play panel.
4. Nav integration and Analyze deep-links.

## Data pipeline

```text
symbol ──▶ web search (ddgs) ──┐
                              ▼
                    LLM extraction (openai) ──▶ supplier list with tickers
                              │
                              ▼
              yfinance fundamentals (growth) + price correlation
                              │
                              ▼
                    trade_desk.py per supplier ──▶ verdict
                              │
                              ▼
                        JSON envelope ──▶ UI
```

- Supplier discovery: DuckDuckGo search (`{symbol} suppliers` / `{symbol} supply chain`) followed by OpenAI structured extraction.
- Fallback: yfinance `info` sector/industry peers + a small manual seed for hardware.
- Fundamentals: yfinance `financials`, `income_stmt`, `cash_flow` — compute revenue/EPS/cash growth.
- Correlation: yfinance `download` 1y daily, Pearson vs anchor ticker.
- Play: reuse `trade_desk.py --json` for each supplier.

## API contract

POST `/api/supply-chain`

```json
{
  "symbol": "NVDA",
  "account": 100000,
  "risk_pct": 1.0,
  "model": "auto"
}
```

Response:

```json
{
  "ok": true,
  "command": "supply_chain",
  "data": {
    "symbol": "NVDA",
    "asof": "...",
    "anchor": { ... },
    "suppliers": [
      {
        "symbol": "TSMC",
        "name": "TSMC",
        "confidence": "medium",
        "growth": { "revenue_yoy": 0.12, "eps_yoy": 0.08, "fcf_yoy": 0.15 },
        "correlation": { "1y": 0.72 },
        "market_cap": 600000000000,
        "is_small_cap": false,
        "verdict": { "action": "BUY BREAKOUT", "confidence": 0.68 },
        "score": 0.81
      }
    ]
  }
}
```

## UI

- Page header: "Supply Chain" + symbol + anchor action.
- Controls: symbol, account, risk pct, model, run.
- Hero play panel: top 3 suppliers with action rail color.
- Ranking table: supplier, confidence, growth, correlation, market cap, small cap flag, score, action, link to Analyze.
- Empty/honest states when no suppliers or API key missing.

## Dependencies

Already installed in `.venv`: `openai`, `ddgs`, `yfinance`, `httpx`, `requests`, `beautifulsoup4`, `langchain`.
Runtime requires `OPENAI_API_KEY` or `LSE_API_KEY` (if LSE is a proxy with OpenAI-compatible endpoint). If no key is present, the tool falls back to sector peers and manual seed.

## Files

- `tools/supply_chain.py`
- `apps/trade-desk/src/app/api/supply-chain/route.ts`
- `apps/trade-desk/src/app/supply-chain/page.tsx`
- `apps/trade-desk/src/components/supply-chain/SupplyChainDesk.tsx`
- `apps/trade-desk/src/lib/supplyChain.ts` (normalize/bridge)
- `apps/trade-desk/src/lib/paths.ts` add `supplyChainScript()`
- `apps/trade-desk/src/lib/routes.ts` add `supplyChainHref()`
- `apps/trade-desk/src/components/shell/DeskShell.tsx` add nav item
