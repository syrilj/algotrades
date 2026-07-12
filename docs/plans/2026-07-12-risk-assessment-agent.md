# Risk Assessment Agent Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a research-backed risk assessment engine that computes Kelly sizing, VaR/Expected Shortfall, drawdown analytics, and risk-adjusted ratios (Sharpe/Sortino/Calmar) and surfaces it via a new API route and a minimal panel in the Trade Desk app.

**Architecture:** A pure Python `RiskAssessment` module lives at `tools/risk_assessment.py` with a CLI `assess` subcommand. It accepts account value, returns/trade history, and optional portfolio positions, then returns a JSON report. The Next.js app adds `riskAssessmentScript` in `lib/paths.ts`, `runRiskAssessment` in `lib/tradeDesk.ts`, a new `/api/risk-assessment` route, and a `RiskAssessmentPanel` rendered on the Analyze page.

**Tech Stack:** Python 3.11, NumPy/pandas, Next.js 15 App Router, TypeScript, Tailwind CSS.

---

## Task 1: Create Python risk assessment engine

**Files:**
- Create: `tools/risk_assessment.py`

**Step 1:** Write the module with the following core functions (no new external deps beyond numpy/pandas/scipy if needed; prefer numpy only).

```python
def kelly_fraction(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """f* = (p * b - q) / b, where b = avg_win / avg_loss."""

def kelly_sizes(account: float, win_rate: float, avg_win: float, avg_loss: float, kelly_frac: float = 0.5) -> dict:
    """Return full_kelly, half_kelly, quarter_kelly dollar positions."""

def fixed_fractional_position(account: float, risk_pct: float, stop_loss_dollars: float) -> float:
    """position = account * risk_pct / stop_loss_dollars."""

def parametric_var_es(returns: np.ndarray, portfolio_value: float, confidence: float = 0.95, holding_period_days: int = 1) -> dict:
    """Parametric VaR/ES assuming normal returns."""

def historical_var_es(returns: np.ndarray, portfolio_value: float, confidence: float = 0.95) -> dict:
    """Historical simulation VaR/ES from percentile."""

def drawdown_metrics(equity_curve: np.ndarray) -> dict:
    """Max drawdown, average drawdown, max drawdown duration, current drawdown."""

def risk_adjusted_ratios(returns: np.ndarray, risk_free_annual: float = 0.04, periods_per_year: int = 252) -> dict:
    """Sharpe, Sortino, Calmar."""

def portfolio_variance(weights: np.ndarray, cov: np.ndarray) -> dict:
    """Portfolio variance and diversification benefit."""
```

**Step 2:** Add a CLI `assess` subcommand that parses JSON either from stdin or `--json-file` and prints a JSON envelope. The input schema:

```json
{
  "account": 10000,
  "equity": 9500,
  "peak": 12000,
  "returns": [0.01, -0.005, ...],
  "closed_pnl": [0.02, -0.01, ...],
  "positions": [{"symbol": "TSLA", "weight": 0.4, "returns": [...]}],
  "confidence": 0.95,
  "holding_days": 1,
  "risk_free": 0.04
}
```

Output schema:

```json
{
  "ok": true,
  "account": 10000,
  "drawdown": 0.2083,
  "kelly": {"full": 0.25, "half": 0.125, "quarter": 0.0625, "full_dollar": 2500, "half_dollar": 1250},
  "position_sizing": {"fixed_fractional": {"shares_or_lots": 0.2, "risk_dollars": 100}},
  "var_es": {"parametric": {"var": 329, "es": 412}, "historical": {"var": 300, "es": 450}},
  "risk_adjusted": {"sharpe": 0.55, "sortino": 0.79, "calmar": 0.60},
  "drawdown_metrics": {"max": 0.50, "average": 0.12, "max_duration_days": 45, "current": 0.2083},
  "portfolio": {"variance": 0.016, "std": 0.126, "diversification_benefit_pct": 33.7},
  "reasons": ["list"],
  "asof_utc": "..."
}
```

**Step 3:** Run a smoke test from the repo root.

Run: `python3 tools/risk_assessment.py assess --account 10000 --peak 12000 --equity 9500 --returns 0.01,-0.02,0.005,0.015,-0.01 --json`
Expected: JSON output with `ok: true` and all sections present.

**Step 4:** Commit.

```bash
git add tools/risk_assessment.py
git commit -m "feat: add research-backed risk assessment engine"
```

---

## Task 2: Wire Trade Desk API

**Files:**
- Modify: `apps/trade-desk/src/lib/paths.ts`
- Modify: `apps/trade-desk/src/lib/tradeDesk.ts`
- Modify: `apps/trade-desk/src/lib/types.ts`
- Create: `apps/trade-desk/src/app/api/risk-assessment/route.ts`

**Step 1:** Add `riskAssessmentScript()` in `lib/paths.ts` returning `tools/risk_assessment.py`.

**Step 2:** Add `runRiskAssessment(args, timeoutMs=30_000)` in `lib/tradeDesk.ts`.

**Step 3:** Add `RiskAssessmentResponse` interface to `lib/types.ts` with the output fields above.

**Step 4:** Create `/api/risk-assessment` route that accepts POST JSON, validates `account` and `equity`/`peak`, builds the right command-line/JSON invocation, and returns an `ApiEnvelope<RiskAssessmentResponse>`.

**Step 5:** Run a quick smoke test.

Run: `curl -X POST http://localhost:3000/api/risk-assessment -H "Content-Type: application/json" -d '{"account":10000,"equity":9500,"peak":12000,"returns":[0.01,-0.02,0.005,0.015,-0.01]}'`
Expected: `ok: true` with risk metrics.

**Step 6:** Commit.

```bash
git add apps/trade-desk/src/lib/paths.ts apps/trade-desk/src/lib/tradeDesk.ts apps/trade-desk/src/lib/types.ts apps/trade-desk/src/app/api/risk-assessment/route.ts
git commit -m "feat: expose risk assessment via /api/risk-assessment"
```

---

## Task 3: Add Risk Assessment Panel to Analyze page

**Files:**
- Create: `apps/trade-desk/src/components/risk/RiskAssessmentPanel.tsx`
- Modify: `apps/trade-desk/src/app/page.tsx`

**Step 1:** Build a `RiskAssessmentPanel` component that accepts `symbol` and optional `account`/`equity`/`peak`. It fetches `/api/risk-assessment` when the user clicks a "Assess Risk" button or when the analyze result completes. It displays:

- Drawdown (current, max)
- Kelly fractions (half/quarter recommended)
- VaR / ES at 95% confidence
- Sharpe / Sortino / Calmar
- A terse verdict line: `RISK OK`, `SIZE DOWN`, `HALT NEW`, or `FLATTEN` based on drawdown thresholds from `tools/risk_manager.py`.

**Step 2:** Import and render `<RiskAssessmentPanel symbol={symbol} account={values.account} />` in the Analyze page inside the existing research details section, but keep it collapsed by default to match the design principle of signal over chrome.

**Step 3:** Run `npm run build` in `apps/trade-desk` to catch type errors.

**Step 4:** Commit.

```bash
git add apps/trade-desk/src/components/risk/RiskAssessmentPanel.tsx apps/trade-desk/src/app/page.tsx
git commit -m "feat: add risk assessment panel to analyze page"
```

---

## Task 4: Verify end-to-end

**Files:**
- None

**Step 1:** Start the dev server and the backend.

Run: `cd apps/trade-desk && npm run dev` and `cd /Users/syriljacob/Desktop/TradingAlgoWork && source .venv/bin/activate && python services/standalone_server.py`.

**Step 2:** Open `http://localhost:3000`, enter `TSLA`, click Analyze, then expand the Risk Assessment panel.

Expected: Panel shows current drawdown, Kelly sizes, VaR/ES, and ratios. No console errors.

**Step 3:** Run `python3 tools/risk_assessment.py assess --help` and ensure CLI is usable.

**Step 4:** Final commit or note completion.

```bash
git status
```
