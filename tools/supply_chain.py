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
import urllib.request
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

CACHE_DIR = Path.home() / ".cache" / "trade-desk"

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# Common English / market acronyms that happen to be SEC tickers but are not useful here.
TICKER_STOPWORDS: set[str] = {
    "A", "AM", "AN", "AS", "AT", "BE", "BY", "DO", "FOR", "GO", "HE", "I", "IF", "IN", "IS", "IT",
    "MY", "NO", "OF", "OFF", "ON", "OR", "SO", "THE", "TO", "UP", "US", "WE", "CEO", "CFO", "CTO",
    "COO", "CIO", "SEC", "FED", "GDP", "CPI", "PPI", "PCE", "ISM", "PMI", "ECB", "FOMC", "WTI",
    "VIX", "SPY", "QQQ", "IWM", "DIA", "USD", "EUR", "GBP", "JPY", "CNY", "BTC", "ETH", "ETF",
    "IPO", "EPS", "ROE", "ROI", "ROA", "YTD", "PCT", "QTD", "MTD", "Q1", "Q2", "Q3", "Q4", "FY",
    "AI", "BI", "ML", "API", "OEM", "SaaS", "PaaS", "IaaS", "GPU", "CPU", "RAM", "ROM", "SSD",
    "HDD", "LCD", "OLED", "LED", "DRAM", "HBM", "NAND", "CMOS", "TSMC", "FOXCONN", "NASDAQ", "NYSE",
    "AMEX", "CBOE", "HTML", "URL", "HTTP", "WWW", "COM", "ORG", "NET", "CO", "LTD", "INC", "LLC",
    "PLC", "AG", "SA", "NV", "BV", "KG", "LP", "GP", "PC", "PA", "REIT", "ADR", "OTC", "FX",
    "QID", "SDS", "UPRO", "SPXU", "TQQQ", "SQQQ", "UVXY", "SVXY", "VXX", "VIXY", "XLF", "XLK",
    "XLE", "XLU", "XLI", "XLP", "XLB", "XRT", "XHB", "XOP", "OIH", "SMH", "SOXX", "IBB", "XBI",
    "ARKK", "ARKQ", "SARK", "TSLA", "AAPL", "MSFT", "AMZN", "GOOGL", "META",
    # Common English words that appear in search text and happen to be valid tickers
    "S", "YOU", "YOUR", "YOURS", "SUCH", "THEY", "THEM", "THEIR", "THEIRS", "THIS", "THAT",
    "THESE", "THOSE", "WITH", "FROM", "HAVE", "HAS", "HAD", "BEEN", "WAS", "WERE", "SAID",
    "SAY", "SAYS", "EACH", "WHICH", "WOULD", "COULD", "SHOULD", "THERE", "OTHER", "AFTER",
    "FIRST", "NEVER", "THINK", "WHERE", "BEING", "EVERY", "GREAT", "WHILE", "ALSO", "BACK",
    "MADE", "MAKE", "MUCH", "MIGHT", "MUST", "ONLY", "OVER", "SAME", "STILL", "VERY", "WELL",
    "WITHOUT", "BETWEEN", "INTO", "THROUGH", "DURING", "BEFORE", "ABOVE", "BELOW", "MANY",
    "SOME", "MOST", "MORE", "LESS", "FEW", "SEVERAL", "BOTH", "ALL", "ANY", "EITHER", "NEITHER",
    "NONE", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE", "TEN",
    "HUNDRED", "THOUSAND", "MILLION", "BILLION", "TRILLION",
    "STOCK", "STOCKS", "SUPPLY", "SUPPLIES", "CHAIN", "MARKET", "MARKETS", "INVESTOR", "INVESTORS",
    "COMPANY", "COMPANIES", "BUSINESS", "BUSINESSES", "REPORT", "REPORTS", "EARNINGS", "QUARTER",
    "FINANCIAL", "FINANCIALS", "SECTOR", "SECTORS", "INDUSTRY", "INDUSTRIES", "ANALYSIS", "ANALYSES",
    "PRICE", "PRICES", "SHARE", "SHARES", "TRADING", "TRADE", "TRADES", "INVESTMENT", "INVESTMENTS",
    "PORTFOLIO", "PORTFOLIOS", "UPDATE", "UPDATES", "NEWS", "TODAY", "YESTERDAY", "TOMORROW",
    "YEAR", "YEARS", "MONTH", "MONTHS", "WEEK", "WEEKS", "DAY", "DAYS", "TIME", "TIMES",
}

# Additional words that appear in financial search text and are not useful supplier tickers.
COMMON_WORDS: set[str] = {
    "P", "VS", "BID", "ASK", "LOW", "HIGH", "OPEN", "CLOSE", "VOL", "VOLUME", "CHANGE",
    "GAIN", "LOSS", "SURGE", "DROP", "RISE", "FALL", "GROWTH", "DECLINE", "RALLY", "PLUNGE",
    "CRASH", "REBOUND", "BOUNCE", "PULLBACK", "CORRECTION", "BREAKOUT", "BREAKDOWN", "TREND",
    "SUPPORT", "RESISTANCE", "MOVING", "AVERAGE", "AVG", "MIN", "MAX", "SUM", "TOTAL", "NET",
    "GROSS", "PRICE", "PRICES", "ADJUSTED", "MA", "RSI", "MACD", "VWAP", "POC", "VAL", "VAH",
    "RVOL", "ATR", "GAP", "RUN", "MOM", "STOP", "ENTRY", "EXIT", "TARGET", "RISK", "TRADE",
    "TRADES", "CALL", "PUT", "BUY", "SELL", "HOLD", "ADD", "CASH", "DEBT", "VALUE", "YIELD",
    "DIVIDEND", "FUND", "FUNDS", "ETFS", "CAP", "MKT",
}
TICKER_STOPWORDS.update(COMMON_WORDS)

# Hand-curated seed for hardware demos; web extraction fills the rest.
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
        from ddgs import DDGS
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


def _sec_tickers_cache() -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / "sec_tickers.json"


def _load_sec_tickers() -> dict[str, str]:
    cache = _sec_tickers_cache()
    max_age = 7 * 24 * 60 * 60
    try:
        if cache.exists() and (datetime.now().timestamp() - cache.stat().st_mtime) < max_age:
            with cache.open("r", encoding="utf-8") as f:
                return dict(json.load(f))
    except Exception:
        pass
    try:
        req = urllib.request.Request(
            SEC_TICKERS_URL,
            headers={"User-Agent": "Mozilla/5.0 (compatible; Bot/0.1)"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = json.load(resp)
        mapping = {v["ticker"].upper(): v["title"] for v in raw.values()}
        with cache.open("w", encoding="utf-8") as f:
            json.dump(mapping, f)
        return mapping
    except Exception:
        return {}


def _sec_title_name(title: str) -> str:
    name = title
    name = re.sub(r"\s*/[A-Z]{1,2}\s*$", "", name)
    name = re.sub(r"\s+(INC|CORP|LTD|LLC|PLC|AG|SA|NV|BV|KG|LP|GP|PC|CO|COMPANY|CORPORATION|LIMITED|HOLDINGS|HOLDING)\b.*$", "", name, flags=re.I)
    name = re.sub(r"[,\.\s]+$", "", name)
    return name.title()


def _clean_company_name(name: str) -> str:
    return re.sub(r"[,\s]+$", "", name).strip()


# Product keywords mapped to a compact human-readable product label.
_PRODUCT_PATTERNS: list[tuple[str, str]] = [
    ("rare earths", "rare earths"),
    ("rare earth", "rare earths"),
    ("hbm", "HBM memory"),
    ("memory chips", "memory chips"),
    ("memory", "memory"),
    ("dram", "DRAM memory"),
    ("nand", "NAND storage"),
    ("storage", "storage"),
    ("batteries", "batteries"),
    ("battery", "batteries"),
    ("lithium", "lithium"),
    ("displays", "displays"),
    ("display", "displays"),
    ("oled", "OLED displays"),
    ("lcd", "LCD displays"),
    ("glass", "Gorilla Glass"),
    ("wafers", "wafers"),
    ("wafer", "wafers"),
    ("etch", "etch equipment"),
    ("process control", "process control"),
    ("inspection", "inspection"),
    ("packaging", "packaging"),
    ("assembly", "assembly"),
    ("testing", "testing"),
    ("test equipment", "test equipment"),
    ("equipment", "equipment"),
    ("semiconductor", "semiconductors"),
    ("semiconductors", "semiconductors"),
    ("chips", "chips"),
    ("chip", "chips"),
    ("sensors", "sensors"),
    ("power", "power components"),
    ("cooling", "cooling systems"),
    ("servers", "servers"),
    ("racks", "racks"),
    ("modules", "modules"),
    ("optical", "optical components"),
    ("networking", "networking"),
    ("rf", "RF components"),
    ("modems", "modems"),
    ("custom silicon", "custom silicon"),
    ("silicon", "silicon"),
    ("materials", "materials"),
    ("subsystems", "subsystems"),
    ("software", "software"),
    ("services", "services"),
    ("hardware", "hardware"),
    ("components", "components"),
    ("foundry", "foundry"),
    ("asic", "ASIC"),
    ("fpga", "FPGA"),
    ("eda", "EDA software"),
    ("supplier", "supplier"),
    ("suppliers", "supplier"),
    ("supply", "supplier"),
    ("vendor", "vendor"),
    ("manufactures", "manufacturing"),
    ("manufacturing", "manufacturing"),
    ("produces", "production"),
    ("provider", "provider"),
    ("makes", "manufacturer"),
    ("offers", "offers"),
    ("designs", "design"),
]


def _context_product(symbol: str, text: str) -> tuple[str, int]:
    """Return a product label and a context count for the symbol in text.

    Searches the text around the symbol for product/supply keywords.
    """
    pattern = re.compile(r"[^.\n]{0,60}\b" + re.escape(symbol) + r"\b[^.\n]{0,60}", re.I)
    contexts = []
    for m in pattern.finditer(text):
        snippet = m.group(0)
        contexts.append(snippet)
    if not contexts:
        return "supplier", 0

    # Find the first product keyword in any snippet, preferring snippets closer to supply terms.
    for pat, product in _PRODUCT_PATTERNS:
        for snippet in contexts:
            if re.search(r"\b" + re.escape(pat) + r"\b", snippet, re.I):
                return product, len(contexts)
    return "supplier", len(contexts)


def _extract_suppliers_from_text(text: str, anchor: str, sec_tickers: dict[str, str]) -> dict[str, dict[str, Any]]:
    """Extract candidate supplier tickers from a web corpus using regex + SEC validation.

    Returns a dict mapping symbol -> {count, context_count, ticker_context_count, product, name_from_sec}.
    """
    anchor = anchor.upper()
    sec_set = set(sec_tickers.keys())
    # Ticker-like tokens are written in uppercase. 3-5 letters are likely tickers; 1-2 letters need a stronger context.
    candidates: dict[str, dict[str, Any]] = {}
    for m in re.finditer(r"\b[A-Z]{1,5}\b", text):
        sym = m.group()
        if len(sym) == 1 or sym == anchor or sym in TICKER_STOPWORDS or sym not in sec_set:
            continue
        if sym not in candidates:
            candidates[sym] = {"count": 0, "context_count": 0, "ticker_context_count": 0, "product": "", "name": _sec_title_name(sec_tickers.get(sym, ""))}
        candidates[sym]["count"] += 1

    # Score ticker context: $SYM, (SYM), NASDAQ:SYM, NYSE:SYM, OTC:SYM.
    ticker_context_re = re.compile(r"(?:\$|\(|NASDAQ:|NYSE:|OTC:|NASDAQ\s+|NYSE\s+)([A-Z]{1,5})\b", re.I)
    for m in ticker_context_re.finditer(text):
        sym = m.group(1).upper()
        if sym in candidates:
            candidates[sym]["ticker_context_count"] += 1

    # Score supply context and derive product.
    for sym in list(candidates):
        product, ctx = _context_product(sym, text)
        candidates[sym]["product"] = product
        candidates[sym]["context_count"] = ctx

    # Very short tickers are too noisy unless they are explicitly marked as a ticker or appear in a strong supply context.
    for sym in list(candidates):
        meta = candidates[sym]
        if len(sym) <= 2 and meta["ticker_context_count"] < 1 and not (meta["context_count"] >= 2 and meta["count"] >= 2):
            del candidates[sym]

    return candidates


def _valid_tickers(symbols: list[str]) -> set[str]:
    """Use a single yfinance download to validate a list of candidate tickers."""
    if not symbols:
        return set()
    try:
        data = yf.download(
            symbols,
            period="5d",
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
        if data is None or data.empty:
            return set()
        if isinstance(data.columns, pd.MultiIndex):
            close = data["Close"]
            valid = [c for c in close.columns if not close[c].dropna().empty]
        else:
            if "Close" in data.columns:
                valid = [symbols[0]] if not data["Close"].dropna().empty else []
            else:
                valid = []
        return set(valid)
    except Exception:
        return set()


def _fetch_page_text(url: str) -> str:
    """Use ddgs extract to read a web page without hitting site anti-bot."""
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            result = ddgs.extract(url, fmt="text_markdown")
        return result.get("content", "") or ""
    except Exception:
        return ""


def _web_extract_suppliers(symbol: str, company_name: str | None, web_results: list[dict[str, str]]) -> list[dict[str, str]]:
    """Non-LLM extraction: harvest ticker symbols from web search snippets and related pages."""
    symbol = symbol.upper()
    sec_tickers = _load_sec_tickers()
    if not sec_tickers:
        return []

    corpus = ""
    # CSIMarket suppliers page is a good structured source for US equities.
    csimarket_urls = [
        f"https://csimarket.com/stocks/competition2.php?supply&code={symbol}",
        f"https://csimarket.com/stocks/suppliers_glance.php?code={symbol}",
    ]
    for url in csimarket_urls:
        try:
            corpus += "\n" + _fetch_page_text(url)
        except Exception:
            pass

    # Add search snippets and extract the first few linked pages.
    seen_hrefs: set[str] = set()
    for r in web_results:
        corpus += "\n" + r.get("title", "") + " " + r.get("body", "")
        href = r.get("href", "")
        if href and href not in seen_hrefs and not any(d in href for d in ("csimarket.com", "facebook.com", "reddit.com", "twitter.com", "x.com")):
            seen_hrefs.add(href)
            if len(seen_hrefs) <= 3:
                try:
                    corpus += "\n" + _fetch_page_text(href)
                except Exception:
                    pass

    # Strip markdown link references and footnote numbers so navigation links don't become tickers.
    corpus = re.sub(r"\[\d+\]", "", corpus)
    corpus = re.sub(r"\[.*?\]", "", corpus)

    candidates = _extract_suppliers_from_text(corpus, symbol, sec_tickers)
    if not candidates:
        return []

    # Rank candidates by a mix of frequency, supply context, and ticker context.
    scored: list[tuple[str, float]] = []
    for sym, meta in candidates.items():
        score = meta["count"] + 2 * meta["context_count"] + 3 * meta["ticker_context_count"]
        scored.append((sym, score))
    scored.sort(key=lambda x: x[1], reverse=True)

    # Validate top candidates with yfinance.
    top_symbols = [sym for sym, _ in scored[:25]]
    valid = _valid_tickers(top_symbols)

    # Build output for validated symbols, looking up friendly names from yfinance if possible.
    suppliers: list[dict[str, str]] = []
    try:
        tickers = yf.Tickers(" ".join(sorted(valid)))
        name_lookup = {s: (tickers.tickers[s].info or {}).get("shortName") for s in valid if s in tickers.tickers}
    except Exception:
        name_lookup = {}

    for sym in top_symbols:
        if sym not in valid:
            continue
        meta = candidates[sym]
        count = meta["count"]
        ctx = meta["context_count"]
        tc = meta["ticker_context_count"]
        if count >= 3 or tc >= 2 or (count >= 2 and ctx >= 1):
            confidence = "high"
        elif count >= 2 or ctx >= 1 or tc >= 1:
            confidence = "medium"
        else:
            confidence = "low"
        name = _clean_company_name(name_lookup.get(sym) or meta["name"] or sym)
        suppliers.append({
            "symbol": sym,
            "name": name,
            "product": meta["product"],
            "source": "web",
            "confidence": confidence,
        })
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
    web_suppliers = _web_extract_suppliers(symbol, company_name, web_results)
    for s in web_suppliers:
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
            "name": fundamentals.get("name") or s.get("name", sym),
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
