#!/usr/bin/env python3
"""Supply-chain screener — discover a ticker's suppliers, score fundamentals, and generate plays.

Usage:
    python3 tools/supply_chain.py NVDA --json
    python3 tools/supply_chain.py NVDA --account 100000 --risk-pct 1.0 --model auto --json
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore", category=FutureWarning)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from trade_desk import (  # noqa: E402
    _plain_plan,
    _position_math,
    _to_code,
    analyze,
)

# Hand-curated seed for hardware demos; LLM/web fills the rest.
HARDWARE_SEED: dict[str, list[dict[str, str]]] = {
    "NVDA": [
        {"symbol": "TSM", "name": "Taiwan Semiconductor", "product": "GPU wafers", "source": "seed"},
        {"symbol": "AMAT", "name": "Applied Materials", "product": "chip manufacturing equipment", "source": "seed"},
        {"symbol": "LRCX", "name": "Lam Research", "product": "etch equipment", "source": "seed"},
        {"symbol": "KLAC", "name": "KLA", "product": "process control", "source": "seed"},
        {"symbol": "MU", "name": "Micron", "product": "HBM memory", "source": "seed"},
        {"symbol": "AVGO", "name": "Broadcom", "product": "networking/custom silicon", "source": "seed"},
        {"symbol": "MRVL", "name": "Marvell", "product": "custom AI silicon", "source": "seed"},
        {"symbol": "COHR", "name": "Coherent", "product": "optical components", "source": "seed"},
        {"symbol": "VRT", "name": "Vertiv", "product": "data center power/cooling", "source": "seed"},
        {"symbol": "SMCI", "name": "Super Micro", "product": "AI servers", "source": "seed"},
    ],
    "AAPL": [
        {"symbol": "TSM", "name": "Taiwan Semiconductor", "product": "A-series chips", "source": "seed"},
        {"symbol": "AVGO", "name": "Broadcom", "product": "RF components", "source": "seed"},
        {"symbol": "QCOM", "name": "Qualcomm", "product": "modems", "source": "seed"},
        {"symbol": "LPL", "name": "LG Display", "product": "OLED displays", "source": "seed"},
        {"symbol": "GLW", "name": "Corning", "product": "Gorilla Glass", "source": "seed"},
        {"symbol": "SWKS", "name": "Skyworks", "product": "RF front-end", "source": "seed"},
        {"symbol": "CRUS", "name": "Cirrus Logic", "product": "audio ICs", "source": "seed"},
        {"symbol": "TXN", "name": "Texas Instruments", "product": "power management", "source": "seed"},
    ],
    "TSLA": [
        {"symbol": "ALB", "name": "Albemarle", "product": "lithium", "source": "seed"},
        {"symbol": "SQM", "name": "SQM", "product": "lithium", "source": "seed"},
        {"symbol": "MP", "name": "MP Materials", "product": "rare earths", "source": "seed"},
        {"symbol": "ON", "name": "ON Semiconductor", "product": "power / sensor semis", "source": "seed"},
        {"symbol": "APTV", "name": "Aptiv", "product": "automotive wiring", "source": "seed"},
        {"symbol": "BWA", "name": "BorgWarner", "product": "powertrain components", "source": "seed"},
    ],
    "AMD": [
        {"symbol": "TSM", "name": "Taiwan Semiconductor", "product": "CPU/GPU wafers", "source": "seed"},
        {"symbol": "AMAT", "name": "Applied Materials", "product": "equipment", "source": "seed"},
        {"symbol": "LRCX", "name": "Lam Research", "product": "etch equipment", "source": "seed"},
        {"symbol": "MU", "name": "Micron", "product": "memory", "source": "seed"},
        {"symbol": "INTC", "name": "Intel", "product": "competitor/peer", "source": "seed"},
    ],
    "AVGO": [
        {"symbol": "TSM", "name": "Taiwan Semiconductor", "product": "semiconductor wafers", "source": "seed"},
        {"symbol": "AMAT", "name": "Applied Materials", "product": "equipment", "source": "seed"},
        {"symbol": "QCOM", "name": "Qualcomm", "product": "peer", "source": "seed"},
        {"symbol": "MRVL", "name": "Marvell", "product": "peer", "source": "seed"},
    ],
    "MU": [
        {"symbol": "AMAT", "name": "Applied Materials", "product": "equipment", "source": "seed"},
        {"symbol": "LRCX", "name": "Lam Research", "product": "etch equipment", "source": "seed"},
        {"symbol": "KLAC", "name": "KLA", "product": "inspection", "source": "seed"},
        {"symbol": "WDC", "name": "Western Digital", "product": "peer", "source": "seed"},
        {"symbol": "STX", "name": "Seagate", "product": "peer", "source": "seed"},
    ],
}


def _sanitize_nan(obj: Any) -> Any:
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_nan(v) for v in obj]
    return obj


def _to_yf(symbol: str) -> str:
    return symbol.replace(".", "-").upper()


def _yf_info(symbol: str) -> dict[str, Any]:
    try:
        t = yf.Ticker(_to_yf(symbol))
        info = t.info or {}
        return info
    except Exception:
        return {}


def _last_valid(df: pd.DataFrame | pd.Series, row: str) -> float | None:
    try:
        s = df.loc[row] if row in df.index else None
        if s is None:
            return None
        s = s.dropna()
        return float(s.iloc[-1]) if len(s) else None
    except Exception:
        return None


def _growth_pct(df: pd.DataFrame | pd.Series, row: str) -> float | None:
    try:
        s = df.loc[row] if row in df.index else None
        if s is None:
            return None
        s = s.dropna()
        if len(s) < 2:
            return None
        return float(s.iloc[-1] / s.iloc[-2] - 1)
    except Exception:
        return None


def _fundamentals(symbol: str) -> dict[str, Any]:
    info = _yf_info(symbol)
    name = info.get("longName") or info.get("shortName") or symbol
    try:
        t = yf.Ticker(_to_yf(symbol))
        inc = t.income_stmt if hasattr(t, "income_stmt") else t.financials
        bal = t.balance_sheet
        cf = t.cashflow
    except Exception:
        inc = bal = cf = pd.DataFrame()

    revenue = _last_valid(inc, "Total Revenue") or _last_valid(inc, "Revenue")
    revenue_growth = _growth_pct(inc, "Total Revenue") or _growth_pct(inc, "Revenue")
    net_income = _last_valid(inc, "Net Income")
    net_income_growth = _growth_pct(inc, "Net Income")
    fcf = _last_valid(cf, "Free Cash Flow")
    fcf_growth = _growth_pct(cf, "Free Cash Flow")
    debt = _last_valid(bal, "Total Debt") or _last_valid(bal, "Total Liabilities Net Minority Interest")
    cash = _last_valid(bal, "Cash And Cash Equivalents") or _last_valid(bal, "Cash and Cash Equivalents")
    market_cap = info.get("marketCap") or info.get("enterpriseValue")
    sector = info.get("sector") or info.get("industry") or ""
    industry = info.get("industry") or ""

    return {
        "name": name,
        "revenue": revenue,
        "revenue_yoy": revenue_growth,
        "net_income": net_income,
        "net_income_yoy": net_income_growth,
        "free_cash_flow": fcf,
        "free_cash_flow_yoy": fcf_growth,
        "cash": cash,
        "debt": debt,
        "market_cap": market_cap,
        "sector": sector,
        "industry": industry,
    }


def _correlation(anchor: str, symbol: str) -> float | None:
    try:
        data = yf.download([_to_yf(anchor), _to_yf(symbol)], period="1y", interval="1d", auto_adjust=True, progress=False)
        if isinstance(data.columns, pd.MultiIndex):
            close = data["Close"]
        else:
            close = data[["Close"]] if "Close" in data.columns else data
        returns = close.pct_change().dropna()
        if returns.shape[1] < 2 or len(returns) < 20:
            return None
        return float(returns.corr().iloc[0, 1])
    except Exception:
        return None


def _price_info(symbol: str) -> dict[str, Any]:
    try:
        df = yf.download(_to_yf(symbol), period="1y", interval="1d", auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        close = df["Close"].dropna()
        return {
            "price": float(close.iloc[-1]) if len(close) else None,
            "ytd_return": float(close.iloc[-1] / close.iloc[0] - 1) if len(close) > 1 else None,
        }
    except Exception:
        return {"price": None, "ytd_return": None}


def _web_search_queries(symbol: str, company_name: str | None) -> list[str]:
    queries = [
        f"{symbol} stock suppliers",
        f"{symbol} supply chain companies",
        f"{symbol} key suppliers and partners",
    ]
    if company_name:
        queries.insert(0, f"{company_name} suppliers stock tickers")
    return queries


def _web_search(queries: list[str], max_results: int = 5) -> list[dict[str, str]]:
    try:
        from duckduckgo_search import DDGS
        results: list[dict[str, str]] = []
        with DDGS() as ddgs:
            for q in queries:
                for r in ddgs.text(q, max_results=max_results):
                    results.append({
                        "title": r.get("title", ""),
                        "body": r.get("body", ""),
                        "href": r.get("href", ""),
                    })
        return results
    except Exception:
        return []


def _openai_client() -> Any:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    try:
        import openai
        base = os.environ.get("OPENAI_BASE_URL")
        return openai.OpenAI(api_key=key, base_url=base) if base else openai.OpenAI(api_key=key)
    except Exception:
        return None


def _llm_extract_suppliers(symbol: str, company_name: str | None, web_results: list[dict[str, str]]) -> list[dict[str, str]]:
    client = _openai_client()
    if not client or not web_results:
        return []
    try:
        context = "\n\n".join(f"Title: {r['title']}\n{r['body']}" for r in web_results[:10])
        prompt = (
            f"You are a financial analyst. Extract the publicly traded suppliers and key partners of {symbol}"
            f" ({company_name or 'the company'}). "
            "Return ONLY a JSON object with key 'suppliers' containing a list of objects. "
            "Each object must have keys: symbol (ticker string, uppercase, no exchange suffix), "
            "name (company name), product (what they supply), and confidence (one of high/medium/low). "
            "Include only suppliers whose stock ticker is known and likely tradeable. "
            "If a supplier is not a public company, omit it."
        )
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You output only valid JSON."},
                {"role": "user", "content": f"{prompt}\n\nResearch context:\n{context}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)
        suppliers = data.get("suppliers", []) if isinstance(data, dict) else []
        for s in suppliers:
            sym = re.sub(r"[^A-Z0-9]", "", (s.get("symbol") or "").upper())
            if sym and 1 <= len(sym) <= 8:
                s["symbol"] = sym
                s["source"] = "llm"
                s.setdefault("confidence", "low")
        return [s for s in suppliers if s.get("symbol")]
    except Exception:
        return []


def _discover_suppliers(symbol: str, use_web: bool = True) -> list[dict[str, str]]:
    symbol = symbol.upper()
    seen: set[str] = set()
    suppliers: list[dict[str, str]] = []

    # Seed
    for s in HARDWARE_SEED.get(symbol, []):
        if s["symbol"] not in seen:
            seen.add(s["symbol"])
            suppliers.append({**s, "confidence": "high"})

    if not use_web:
        return suppliers

    info = _yf_info(symbol)
    company_name = info.get("longName") or info.get("shortName") or symbol
    queries = _web_search_queries(symbol, company_name)
    web_results = _web_search(queries)
    llm_suppliers = _llm_extract_suppliers(symbol, company_name, web_results)
    for s in llm_suppliers:
        if s["symbol"] not in seen:
            seen.add(s["symbol"])
            suppliers.append(s)

    # Sector peers as a soft fallback if we still have few
    if len(suppliers) < 3 and info.get("sector"):
        sector = info.get("sector")
        industry = info.get("industry") or ""
        for peer in _sector_peers(sector, industry, symbol, seen):
            suppliers.append(peer)

    return suppliers


def _sector_peers(sector: str, industry: str, exclude: str, seen: set[str]) -> list[dict[str, str]]:
    peers: list[dict[str, str]] = []
    try:
        screen = yf.Sector(sector) if hasattr(yf, "Sector") else None
        if screen is None:
            return peers
        top = getattr(screen, "top_companies", {}) or {}
        for sym in list(top.keys())[:10]:
            sym = sym.upper()
            if sym == exclude or sym in seen:
                continue
            seen.add(sym)
            peers.append({
                "symbol": sym,
                "name": sym,
                "product": "sector peer",
                "source": "sector",
                "confidence": "low",
            })
    except Exception:
        pass
    return peers


def _play_for_supplier(symbol: str, account: float, risk_pct: float, model: str | None) -> dict[str, Any] | None:
    try:
        payload = analyze(symbol, account, risk_pct, model=model, ranks=False)
        st = payload["state"]
        plan = _plain_plan(st)
        return {
            "action": plan["action"],
            "why": plan["why"],
            "do_next": plan["do_next"],
            "confidence": st.get("confidence"),
            "price": st.get("price"),
            "stop": st.get("stop"),
            "entry": st.get("entry"),
            "setup_ok": st.get("setup_ok"),
            "model": payload.get("model"),
        }
    except Exception as e:
        return {"action": "ERROR", "why": str(e), "do_next": "", "confidence": None}


def _score_supplier(row: dict[str, Any]) -> float:
    growth = (row.get("revenue_yoy") or 0) + (row.get("free_cash_flow_yoy") or 0)
    growth = max(-1.0, min(1.0, growth))
    corr = row.get("correlation_1y") or 0
    conf = row.get("confidence") or "low"
    conf_score = {"high": 1.0, "medium": 0.7, "low": 0.4}.get(conf, 0.4)
    small_boost = 1.15 if row.get("is_small_cap") else 1.0
    play = row.get("play") or {}
    play_score = {"BUY NOW": 1.0, "BUY BREAKOUT": 0.9, "BREAKOUT WATCH": 0.6, "PULLBACK ZONE": 0.5}.get(
        play.get("action", ""), 0.0
    )
    return max(0.0, min(1.0, (conf_score * 0.2 + corr * 0.25 + growth * 0.25 + play_score * 0.35) * small_boost))


def _is_small_cap(market_cap: float | None) -> bool:
    return market_cap is not None and 0 < market_cap < 10_000_000_000


def run_supply_chain(
    symbol: str,
    account: float = 100_000,
    risk_pct: float = 1.0,
    model: str | None = "auto",
    use_web: bool = True,
    max_suppliers: int = 12,
) -> dict[str, Any]:
    symbol = symbol.upper()
    anchor_info = _fundamentals(symbol)
    anchor_price = _price_info(symbol)
    anchor_play = _play_for_supplier(symbol, account, risk_pct, model)

    raw_suppliers = _discover_suppliers(symbol, use_web=use_web)
    suppliers: list[dict[str, Any]] = []
    for s in raw_suppliers[:max_suppliers]:
        sym = s["symbol"]
        if sym == symbol:
            continue
        fundamentals = _fundamentals(sym)
        price = _price_info(sym)
        correlation = _correlation(symbol, sym)
        play = _play_for_supplier(sym, account, risk_pct, model)
        row = {
            "symbol": sym,
            "name": s.get("name", sym),
            "product": s.get("product", ""),
            "confidence": s.get("confidence", "low"),
            "source": s.get("source", "unknown"),
            "price": price.get("price"),
            "ytd_return": price.get("ytd_return"),
            "correlation_1y": correlation,
            "market_cap": fundamentals.get("market_cap"),
            "is_small_cap": _is_small_cap(fundamentals.get("market_cap")),
            "sector": fundamentals.get("sector"),
            "industry": fundamentals.get("industry"),
            "revenue": fundamentals.get("revenue"),
            "revenue_yoy": fundamentals.get("revenue_yoy"),
            "net_income_yoy": fundamentals.get("net_income_yoy"),
            "free_cash_flow_yoy": fundamentals.get("free_cash_flow_yoy"),
            "play": play,
        }
        row["score"] = _score_supplier(row)
        suppliers.append(row)

    suppliers.sort(key=lambda x: x["score"], reverse=True)

    return {
        "ok": True,
        "symbol": symbol,
        "asof": datetime.now(timezone.utc).isoformat(),
        "anchor": {
            "symbol": symbol,
            "name": anchor_info.get("name", symbol),
            "price": anchor_price.get("price"),
            "market_cap": anchor_info.get("market_cap"),
            "sector": anchor_info.get("sector"),
            "industry": anchor_info.get("industry"),
            "play": anchor_play,
        },
        "suppliers": suppliers,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Supply-chain screener")
    p.add_argument("symbol", type=str, help="Anchor ticker")
    p.add_argument("--account", type=float, default=100_000)
    p.add_argument("--risk-pct", type=float, default=1.0)
    p.add_argument("--model", type=str, default="auto")
    p.add_argument("--no-web", action="store_true", help="Use seed data only (no web search)")
    p.add_argument("--json", action="store_true", help="Output JSON")
    args = p.parse_args(argv)

    result = run_supply_chain(
        symbol=args.symbol,
        account=args.account,
        risk_pct=args.risk_pct,
        model=args.model if args.model != "auto" else None,
        use_web=not args.no_web,
    )
    result = _sanitize_nan(result)
    if args.json:
        print(json.dumps(result, default=str))
    else:
        print(f"{result['symbol']}: {len(result['suppliers'])} suppliers")
        for r in result["suppliers"][:10]:
            play = r.get("play") or {}
            print(f"  {r['symbol']:<6} score {r['score']:.2f}  {play.get('action', 'WAIT'):<18}  {r['name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
