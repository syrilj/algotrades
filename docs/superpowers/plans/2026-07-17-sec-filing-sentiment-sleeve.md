# SEC Filing Sentiment Sleeve (v87_sec_filing_reaction) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fine-tune a Hugging Face transformer on SEC filings (10-K/10-Q/8-K) to predict a stock's forward direction vs. its sector benchmark, and wrap it in a new standalone sleeve `models/poc_va_macdha/v87_sec_filing_reaction/` that plugs into the existing model registry with zero paid dependencies.

**Architecture:** A free-data pipeline (SEC EDGAR + yfinance) builds a labeled dataset → `sec-bert-base` is fine-tuned locally via HF `Trainer` with a strict time-based split → a separate scoring pass produces a lightweight per-filing predictions file → the sleeve's `signal_engine.py` forward-fills those predictions onto bars using `pd.merge_asof` (point-in-time correct), decaying to neutral when stale, and never loads the transformer at backtest/live time.

**Tech Stack:** Python 3.10, `torch` + `transformers` (new deps), `pandas`/`yfinance` (existing deps), `pytest`.

## Global Constraints

- Zero paid dependencies — SEC EDGAR, yfinance, and HF Hub checkpoints only, no API keys, no cloud compute. (spec: Cost constraint)
- Time-based train/val/test split only — never random. Train through 2022-12-31, validate through 2023-12-31, test after. (spec §2)
- Point-in-time correctness is mandatory — a bar's signal must only reflect filings dated strictly before that bar's date. (spec §3, §4)
- Disk is tight (~5GB free at plan time) — keep footprint minimal: no intermediate training checkpoints (`save_strategy="no"`), extract only the target filing section (not full filing HTML) to disk, and any test/smoke run must use a tiny randomly-initialized model config instead of downloading the real ~440MB checkpoint. Flag disk usage if it climbs during execution.
- Base checkpoint: `nlpaueb/sec-bert-base` primary, `yiyanghkust/finbert-tone` fallback if validation accuracy is materially worse. (spec §2)
- Broad training universe (S&P 500) for volume, narrow deployment universe (live watchlist, ETFs excluded) for inference. (spec: Architecture overview)
- Weights live under `runs/sec_filing_reaction/weights/`, already covered by the blanket `runs/*/` gitignore rule (`.gitignore:27`) — never committed.
- Out of scope: promotion to `DEPLOYMENT_MANIFEST.json` / `runs/calibration/active/` / `WINNER.json`, and live/real-time EDGAR polling. (spec: Goal)
- `SEC_EDGAR_USER_AGENT` env var (a compliant contact identifier per SEC's developer FAQ) must be set before any live EDGAR call — never hardcode a personal email into source.

---

## File Structure

| File | Responsibility |
|------|-----------------|
| `tools/sec_filing_chunking.py` | Shared token-chunking logic (used by training AND inference so chunk boundaries never drift apart) |
| `tools/sec_filings.py` | EDGAR fetch: ticker→CIK, list filings, download + HTML-strip a filing, extract its target section |
| `tools/sec_labels.py` | Forward-return labeling: sector-ETF resolution, price fetch, excess-return calc, tercile bucketing |
| `tools/build_sec_dataset.py` | Orchestrates the above into `runs/sec_filing_reaction/dataset.jsonl` |
| `tools/train_sec_sentiment.py` | Chunked dataset + time split + HF `Trainer` fine-tune → `runs/sec_filing_reaction/weights/` |
| `tools/score_sec_filings.py` | Loads the fine-tuned checkpoint once, mean-pools chunk predictions per filing → `runs/sec_filing_reaction/predictions.jsonl` |
| `models/poc_va_macdha/v87_sec_filing_reaction/signal_engine.py` | `SignalEngine` — reads `predictions.jsonl`, forward-fills via `merge_asof`, never touches torch/transformers |
| `models/poc_va_macdha/v87_sec_filing_reaction/config.json` | Backtest run config (mirrors `v83_adaptive_regime/config.json`) |
| `models/poc_va_macdha/v87_sec_filing_reaction/hunt_config.json` | Tunable params: `predictions_path`, `staleness_days`, `signal_scale` |
| `tests/test_sec_filing_chunking.py` | Chunk boundary tests |
| `tests/test_sec_filings.py` | HTML-stripping + section-extraction tests (synthetic fixtures, no network) |
| `tests/test_sec_labels.py` | Tercile bucketing + sector resolution tests |
| `tests/test_train_sec_sentiment.py` | Time-split logic + tiny-model training smoke test (no real checkpoint download) |
| `tests/test_score_sec_filings.py` | Mean-pooling logic smoke test (tiny model) |
| `tests/test_v87_signal_engine.py` | Point-in-time correctness, no-filer neutral, staleness decay, backtest smoke test |

`signal_engine.py` deliberately never imports `torch`/`transformers` — it only reads a small JSONL file. This keeps every backtest run of `v87` as fast and disk-light as every other sleeve; the heavy dependencies are confined to the two offline scripts (`train_sec_sentiment.py`, `score_sec_filings.py`).

---

### Task 1: Environment setup — install torch/transformers, verify disk + MPS

**Files:**
- Modify: `requirements.txt`

**Interfaces:**
- Produces: `torch`, `transformers` importable from the repo's active Python (`/usr/local/bin/python3`, confirmed to already hold all other repo deps).

- [ ] **Step 1: Check free disk space before installing anything**

Run: `df -h /Users/syriljacob/Desktop/TradingAlgoWork`
Expected: "Avail" column — note the value. If it's under 2.0Gi, STOP and tell the user before proceeding (torch+transformers install needs roughly 500MB-1GB; the checkpoint download in Task 6 needs another ~450MB).

- [ ] **Step 2: Install torch and transformers**

Run: `pip3 install torch transformers`
Expected: both install successfully. On this Apple Silicon Mac, `pip3` resolves the MPS-capable macOS wheel automatically — no CUDA extras are pulled in.

- [ ] **Step 3: Verify MPS backend is visible to torch**

Run: `python3 -c "import torch; print('mps available:', torch.backends.mps.is_available())"`
Expected: `mps available: True`

- [ ] **Step 4: Capture resolved versions and pin them in requirements.txt**

Run: `pip3 show torch transformers | grep -E "^(Name|Version):"`
Expected output shape:
```
Name: torch
Version: <X.Y.Z>
Name: transformers
Version: <A.B.C>
```
Open `requirements.txt` and insert two new lines in alphabetical position (matching the file's existing sorted `==`-pinned convention) using the exact versions printed above, e.g.:
```
torch==<X.Y.Z>
transformers==<A.B.C>
```
(Insert `torch==...` alphabetically near `tinyhtml5`/`tqdm`, and `transformers==...` right after `transformers` would sort — i.e. near `tqdm`/`tushare`. Follow the file's existing alphabetical ordering exactly.)

- [ ] **Step 5: Purge pip's download cache to reclaim disk**

Run: `pip3 cache purge`
Expected: cache cleared; re-run `df -h /Users/syriljacob/Desktop/TradingAlgoWork` and confirm available space didn't drop by more than ~1.5GB from Step 1's reading.

- [ ] **Step 6: Commit the dependency pin**

```bash
git add requirements.txt
git commit -m "Add torch + transformers deps for v87_sec_filing_reaction

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Shared chunking module

**Files:**
- Create: `tools/sec_filing_chunking.py`
- Test: `tests/test_sec_filing_chunking.py`

**Interfaces:**
- Produces: `chunk_token_ids(token_ids: list[int]) -> list[list[int]]`, constants `MAX_TOKENS = 512`, `CHUNK_OVERLAP = 50`. Used by Task 6 (training) and Task 7 (scoring) so chunk boundaries never drift between train and serve.

- [ ] **Step 1: Write the failing test**

Create `tests/test_sec_filing_chunking.py`:
```python
"""Chunk-boundary tests for the shared SEC filing tokenization helper."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from sec_filing_chunking import CHUNK_OVERLAP, MAX_TOKENS, chunk_token_ids  # noqa: E402


def test_empty_input_returns_one_empty_chunk():
    assert chunk_token_ids([]) == [[]]


def test_short_input_returns_single_chunk():
    ids = list(range(10))
    chunks = chunk_token_ids(ids)
    assert chunks == [ids]


def test_long_input_splits_with_overlap():
    ids = list(range(1200))
    chunks = chunk_token_ids(ids)
    window = MAX_TOKENS - 2
    stride = window - CHUNK_OVERLAP
    assert len(chunks) == len(range(0, len(ids), stride))
    assert chunks[0] == ids[:window]
    assert chunks[1] == ids[stride : stride + window]
    # last chunk must reach the end of the input
    assert chunks[-1][-1] == ids[-1]


def test_no_chunk_exceeds_window_size():
    ids = list(range(5000))
    chunks = chunk_token_ids(ids)
    window = MAX_TOKENS - 2
    assert all(len(c) <= window for c in chunks)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_sec_filing_chunking.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sec_filing_chunking'`

- [ ] **Step 3: Write the implementation**

Create `tools/sec_filing_chunking.py`:
```python
"""Shared tokenization/chunking for SEC filing text (v87_sec_filing_reaction).

Used by both tools/train_sec_sentiment.py (training) and
tools/score_sec_filings.py (inference) so chunk boundaries are identical
between training and serving — a filing-level prediction is always the
mean-pooled softmax over the SAME set of chunks regardless of which script
produced it.
"""
from __future__ import annotations

MAX_TOKENS = 512
CHUNK_OVERLAP = 50


def chunk_token_ids(token_ids: list[int]) -> list[list[int]]:
    """Split token ids into overlapping windows, leaving room for [CLS]/[SEP].

    Always returns at least one chunk (possibly empty) so callers can rely
    on ``chunks[0]`` existing even for empty/degenerate filing text.
    """
    if not token_ids:
        return [[]]
    window = MAX_TOKENS - 2
    stride = window - CHUNK_OVERLAP
    chunks: list[list[int]] = []
    for start in range(0, len(token_ids), stride):
        chunk = token_ids[start : start + window]
        chunks.append(chunk)
        if start + window >= len(token_ids):
            break
    return chunks or [[]]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_sec_filing_chunking.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add tools/sec_filing_chunking.py tests/test_sec_filing_chunking.py
git commit -m "Add shared SEC filing chunking helper

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: EDGAR fetch + section extraction

**Files:**
- Create: `tools/sec_filings.py`
- Test: `tests/test_sec_filings.py`

**Interfaces:**
- Produces: `ticker_to_cik(ticker: str) -> int | None`, `FilingRef` dataclass (`ticker, cik, form_type, filing_date, accession_number, primary_document`), `list_filings(ticker: str, cik: int, start_date: str) -> list[FilingRef]`, `fetch_filing_text(ref: FilingRef) -> str`, `extract_section(text: str, form_type: str) -> str`. Consumed by Task 5 (`build_sec_dataset.py`).
- No network calls in tests — `_strip_html`/`extract_section` are tested on synthetic strings.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sec_filings.py`:
```python
"""EDGAR HTML-stripping and section-extraction tests (no live network calls)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from sec_filings import _strip_html, extract_section  # noqa: E402

SAMPLE_10K = """
<html><body>
<p>Item 1. Business</p>
<p>We make widgets.</p>
<p>Item 1A. Risk Factors</p>
<p>Our supply chain is concentrated. Demand is cyclical.</p>
<p>Item 1B. Unresolved Staff Comments</p>
<p>None.</p>
<p>Item 7. Management&#160;&nbsp;s Discussion and Analysis</p>
<p>Revenue grew 12% year over year on strong widget demand.</p>
<p>Item 7A. Quantitative Disclosures</p>
<p>Not applicable.</p>
</body></html>
"""


def test_strip_html_removes_tags_and_entities():
    text = _strip_html("<script>evil()</script><p>Hello&nbsp;World</p>")
    assert "<" not in text
    assert "evil" not in text
    assert "Hello" in text and "World" in text


def test_extract_section_10k_pulls_risk_factors_and_mda():
    section = extract_section(SAMPLE_10K, "10-K")
    assert "supply chain is concentrated" in section
    assert "Revenue grew 12%" in section
    # must not leak the surrounding items
    assert "We make widgets" not in section
    assert "Not applicable" not in section


def test_extract_section_8k_returns_truncated_body():
    body = "Item 8.01 Other Events. " + ("x" * 30000)
    section = extract_section(body, "8-K")
    assert section.startswith("Item 8.01")
    assert len(section) <= 20000


def test_extract_section_falls_back_when_markers_missing():
    text = "Some filing with no recognizable Item headers at all."
    section = extract_section(text, "10-K")
    assert section == text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_sec_filings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sec_filings'`

- [ ] **Step 3: Write the implementation**

Create `tools/sec_filings.py`:
```python
"""SEC EDGAR filing fetch + section extraction for v87_sec_filing_reaction.

Fetches 10-K/10-Q/8-K filings via the free SEC EDGAR submissions + archive
endpoints and extracts the highest-signal section per form type. No API key
required; SEC requires a compliant User-Agent identifying the caller
(https://www.sec.gov/os/webmaster-faq#developers) — set SEC_EDGAR_USER_AGENT
before running against the live API. Never hardcode a personal contact
string into this file.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass

import requests

EDGAR_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
EDGAR_TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
EDGAR_ARCHIVE_URL = (
    "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/{doc}"
)
FORM_TYPES = ("10-K", "10-Q", "8-K")
REQUEST_DELAY_SECONDS = 0.11  # SEC fair-access guidance: stay under 10 req/s
SECTION_CHAR_LIMIT = 20000


def _user_agent() -> str:
    ua = os.environ.get("SEC_EDGAR_USER_AGENT")
    if not ua:
        raise RuntimeError(
            "SEC_EDGAR_USER_AGENT env var must be set to a compliant "
            "identifier, e.g. 'YourApp your-contact-email@example.com' "
            "(see https://www.sec.gov/os/webmaster-faq#developers)"
        )
    return ua


def _get(url: str) -> requests.Response:
    resp = requests.get(url, headers={"User-Agent": _user_agent()}, timeout=30)
    resp.raise_for_status()
    time.sleep(REQUEST_DELAY_SECONDS)
    return resp


_TICKER_CIK_CACHE: dict[str, int] | None = None


def ticker_to_cik(ticker: str) -> int | None:
    """Resolve a ticker to its SEC CIK using the public ticker map."""
    global _TICKER_CIK_CACHE
    if _TICKER_CIK_CACHE is None:
        data = _get(EDGAR_TICKER_MAP_URL).json()
        _TICKER_CIK_CACHE = {
            row["ticker"].upper(): int(row["cik_str"]) for row in data.values()
        }
    return _TICKER_CIK_CACHE.get(ticker.upper())


@dataclass
class FilingRef:
    ticker: str
    cik: int
    form_type: str
    filing_date: str  # YYYY-MM-DD
    accession_number: str
    primary_document: str


def list_filings(ticker: str, cik: int, start_date: str) -> list[FilingRef]:
    """List 10-K/10-Q/8-K filings for a ticker on/after start_date."""
    payload = _get(EDGAR_SUBMISSIONS_URL.format(cik=cik)).json()
    recent = payload.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    docs = recent.get("primaryDocument", [])

    out: list[FilingRef] = []
    for form, date, accession, doc in zip(forms, dates, accessions, docs):
        if form not in FORM_TYPES:
            continue
        if date < start_date:
            continue
        out.append(
            FilingRef(
                ticker=ticker,
                cik=cik,
                form_type=form,
                filing_date=date,
                accession_number=accession,
                primary_document=doc,
            )
        )
    return out


def fetch_filing_text(ref: FilingRef) -> str:
    """Download a filing's primary document and strip HTML tags.

    Only the returned (already-extracted, section-scoped) text is meant to
    be persisted to disk downstream — the raw HTML itself is never written
    to disk, keeping the disk footprint to just the extracted sections.
    """
    accession_nodash = ref.accession_number.replace("-", "")
    url = EDGAR_ARCHIVE_URL.format(
        cik=ref.cik, accession_nodash=accession_nodash, doc=ref.primary_document
    )
    html = _get(url).text
    return _strip_html(html)


def _strip_html(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


_ITEM_1A_RE = re.compile(
    r"item\s*1a\.?\s*risk factors(.*?)(?=item\s*1b\.|item\s*2\.)",
    re.IGNORECASE | re.DOTALL,
)
_ITEM_7_RE = re.compile(
    r"item\s*7\.?\s*management.{0,3}s discussion(.*?)(?=item\s*7a\.|item\s*8\.)",
    re.IGNORECASE | re.DOTALL,
)


def extract_section(text: str, form_type: str) -> str:
    """Extract the highest-signal section for a given form type.

    10-K/10-Q -> Item 1A (Risk Factors) + Item 7 (MD&A).
    8-K -> full narrative body (8-Ks are short; no sub-item split needed).
    Falls back to the raw text (truncated to SECTION_CHAR_LIMIT) if section
    markers aren't found — filing formatting is inconsistent across
    companies and years.
    """
    if form_type == "8-K":
        return text[:SECTION_CHAR_LIMIT]

    parts = []
    m1a = _ITEM_1A_RE.search(text)
    if m1a:
        parts.append(m1a.group(1).strip())
    m7 = _ITEM_7_RE.search(text)
    if m7:
        parts.append(m7.group(1).strip())
    if parts:
        return "\n\n".join(parts)[:SECTION_CHAR_LIMIT]
    return text[:SECTION_CHAR_LIMIT]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_sec_filings.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add tools/sec_filings.py tests/test_sec_filings.py
git commit -m "Add SEC EDGAR fetch + section extraction module

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Forward-return labeling

**Files:**
- Create: `tools/sec_labels.py`
- Test: `tests/test_sec_labels.py`

**Interfaces:**
- Produces: `SECTOR_ETF_MAP: dict[str, str]`, `DEFAULT_BENCHMARK = "SPY"`, `resolve_sector_benchmark(ticker: str) -> str`, `fetch_price_history(ticker: str, start: str, end: str) -> pd.DataFrame`, `ForwardReturn` dataclass, `compute_forward_return(ticker, filing_date, benchmark, price_cache) -> ForwardReturn | None`, `tercile_bucket(forward_returns: list[float]) -> list[str]`. Consumed by Task 5.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sec_labels.py`:
```python
"""Forward-return labeling tests — pure functions only, no live network."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from sec_labels import (  # noqa: E402
    DEFAULT_BENCHMARK,
    compute_forward_return,
    resolve_sector_benchmark,
    tercile_bucket,
)


def test_tercile_bucket_balanced_and_ordered():
    returns = [-0.10, -0.08, -0.02, 0.00, 0.01, 0.03, 0.09, 0.12, -0.05]
    labels = tercile_bucket(returns)
    assert len(labels) == len(returns)
    assert set(labels) <= {"down", "flat", "up"}
    # the largest return must be "up", the smallest must be "down"
    assert labels[returns.index(max(returns))] == "up"
    assert labels[returns.index(min(returns))] == "down"


def test_tercile_bucket_roughly_equal_class_sizes():
    returns = list(range(-15, 15))  # 30 evenly spaced values
    labels = tercile_bucket([float(r) for r in returns])
    counts = {lbl: labels.count(lbl) for lbl in ("down", "flat", "up")}
    assert all(8 <= c <= 12 for c in counts.values())


def test_resolve_sector_benchmark_maps_known_sector():
    with patch("sec_labels.yf.Ticker") as mock_ticker:
        mock_ticker.return_value.info = {"sector": "Technology"}
        assert resolve_sector_benchmark("AAPL") == "XLK"


def test_resolve_sector_benchmark_falls_back_to_default_on_error():
    with patch("sec_labels.yf.Ticker", side_effect=RuntimeError("network down")):
        assert resolve_sector_benchmark("WHATEVER") == DEFAULT_BENCHMARK


def _price_df(start: str, n: int, closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range(start, periods=n, freq="D")
    return pd.DataFrame({"close": closes}, index=idx)


def test_compute_forward_return_excess_over_benchmark():
    price_cache = {
        "TSLA": _price_df("2024-01-10", 20, [100.0 + i for i in range(20)]),  # +19%
        "SPY": _price_df("2024-01-10", 20, [400.0 + i for i in range(20)]),  # +4.75%
    }
    result = compute_forward_return("TSLA", "2024-01-10", "SPY", price_cache)
    assert result is not None
    assert result.forward_return > 0  # TSLA outperformed SPY


def test_compute_forward_return_none_when_insufficient_history():
    price_cache = {
        "TSLA": _price_df("2024-01-10", 5, [100.0] * 5),  # too short
        "SPY": _price_df("2024-01-10", 20, [400.0] * 20),
    }
    result = compute_forward_return("TSLA", "2024-01-10", "SPY", price_cache)
    assert result is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_sec_labels.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sec_labels'`

- [ ] **Step 3: Write the implementation**

Create `tools/sec_labels.py`:
```python
"""Forward-return tercile labeling for SEC filing reaction (v87).

Given a ticker and a filing date, computes the ticker's excess return over
the following FORWARD_WINDOW_DAYS trading days relative to its GICS sector
benchmark ETF, then buckets into terciles (down / flat / up) fit on the
full label distribution so classes stay balanced regardless of volatility
regime.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import yfinance as yf

FORWARD_WINDOW_DAYS = 15  # trading days; mid-point of the spec's 10-20 day range

SECTOR_ETF_MAP = {
    "Technology": "XLK",
    "Financial Services": "XLF",
    "Financial": "XLF",
    "Energy": "XLE",
    "Healthcare": "XLV",
    "Industrials": "XLI",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Basic Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
    "Communication Services": "XLC",
}
DEFAULT_BENCHMARK = "SPY"


def resolve_sector_benchmark(ticker: str) -> str:
    """Map a ticker to its GICS sector ETF via yfinance metadata.

    Falls back to DEFAULT_BENCHMARK (SPY) if the sector is unknown or the
    metadata lookup fails — this must never raise, since it's called in a
    loop over the broad training universe.
    """
    try:
        sector = yf.Ticker(ticker).info.get("sector")
    except Exception:
        return DEFAULT_BENCHMARK
    return SECTOR_ETF_MAP.get(sector, DEFAULT_BENCHMARK)


def fetch_price_history(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Fetch daily OHLCV for a ticker via yfinance, lower-cased columns."""
    df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
    if df.empty:
        return df
    cols = df.columns.get_level_values(0) if isinstance(df.columns, pd.MultiIndex) else df.columns
    df.columns = [str(c).lower() for c in cols]
    return df


@dataclass
class ForwardReturn:
    ticker: str
    filing_date: str
    forward_return: float  # ticker return minus benchmark return


def compute_forward_return(
    ticker: str,
    filing_date: str,
    benchmark: str,
    price_cache: dict[str, pd.DataFrame],
) -> ForwardReturn | None:
    """Compute ticker's excess forward return vs benchmark after filing_date.

    price_cache maps ticker -> daily OHLCV DataFrame with a lower-cased
    'close' column. Returns None if there isn't enough trailing price
    history to reach FORWARD_WINDOW_DAYS trading days past the filing
    (e.g. filing too recent, or ticker delisted).
    """
    tkr_px = price_cache.get(ticker)
    bench_px = price_cache.get(benchmark)
    if tkr_px is None or bench_px is None or tkr_px.empty or bench_px.empty:
        return None

    filing_ts = pd.Timestamp(filing_date)
    tkr_after = tkr_px[tkr_px.index >= filing_ts]
    bench_after = bench_px[bench_px.index >= filing_ts]
    if len(tkr_after) <= FORWARD_WINDOW_DAYS or len(bench_after) <= FORWARD_WINDOW_DAYS:
        return None

    tkr_ret = float(tkr_after["close"].iloc[FORWARD_WINDOW_DAYS] / tkr_after["close"].iloc[0] - 1.0)
    bench_ret = float(bench_after["close"].iloc[FORWARD_WINDOW_DAYS] / bench_after["close"].iloc[0] - 1.0)
    return ForwardReturn(ticker=ticker, filing_date=filing_date, forward_return=tkr_ret - bench_ret)


def tercile_bucket(forward_returns: list[float]) -> list[str]:
    """Bucket a list of forward returns into balanced terciles."""
    arr = np.array(forward_returns, dtype=float)
    q1, q2 = np.percentile(arr, [33.333, 66.667])
    out = []
    for r in arr:
        if r <= q1:
            out.append("down")
        elif r >= q2:
            out.append("up")
        else:
            out.append("flat")
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_sec_labels.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add tools/sec_labels.py tests/test_sec_labels.py
git commit -m "Add forward-return tercile labeling module

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: Dataset assembly orchestration

**Files:**
- Create: `tools/build_sec_dataset.py`
- Test: `tests/test_build_sec_dataset.py`

**Interfaces:**
- Consumes: `tools.sec_filings.{ticker_to_cik, list_filings, fetch_filing_text, extract_section, FilingRef}`, `tools.sec_labels.{resolve_sector_benchmark, fetch_price_history, compute_forward_return, tercile_bucket}`.
- Produces: `load_universe(name: str) -> list[str]`, `build(universe_name: str, out_path: Path) -> None` writing JSONL rows shaped `{filing_id, ticker, form_type, filing_date, section_text, forward_return, label}`. Consumed by Task 6.

- [ ] **Step 1: Write the failing test**

Create `tests/test_build_sec_dataset.py`:
```python
"""Dataset-assembly orchestration test — all I/O is monkeypatched, no network."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import build_sec_dataset as bsd  # noqa: E402
import sec_filings  # noqa: E402


def _fake_price_df(start: str, n: int, base: float, drift: float) -> pd.DataFrame:
    idx = pd.date_range(start, periods=n, freq="D")
    return pd.DataFrame({"close": [base + i * drift for i in range(n)]}, index=idx)


def test_load_universe_narrow_excludes_etfs():
    tickers = bsd.load_universe("narrow")
    assert "SPY" not in tickers
    assert "QQQ" not in tickers
    assert "TSLA" in tickers


def test_build_writes_labeled_jsonl(tmp_path):
    out_path = tmp_path / "dataset.jsonl"
    fake_ref = sec_filings.FilingRef(
        ticker="TSLA",
        cik=1318605,
        form_type="10-K",
        filing_date="2024-01-10",
        accession_number="0000000000-24-000001",
        primary_document="tsla10k.htm",
    )

    with (
        patch.object(bsd, "load_universe", return_value=["TSLA"]),
        patch.object(sec_filings, "ticker_to_cik", return_value=1318605),
        patch.object(sec_filings, "list_filings", return_value=[fake_ref]),
        patch.object(sec_filings, "fetch_filing_text", return_value="<p>raw html</p>"),
        patch.object(sec_filings, "extract_section", return_value="Risk factors text."),
        patch.object(bsd.sec_labels, "resolve_sector_benchmark", return_value="XLK"),
        patch.object(
            bsd.sec_labels,
            "fetch_price_history",
            side_effect=lambda ticker, start, end: (
                _fake_price_df("2024-01-10", 20, 100.0, 1.0)
                if ticker == "TSLA"
                else _fake_price_df("2024-01-10", 20, 400.0, 0.1)
            ),
        ),
    ):
        bsd.build("narrow", out_path)

    rows = [json.loads(line) for line in out_path.read_text().splitlines()]
    assert len(rows) == 1
    row = rows[0]
    assert row["ticker"] == "TSLA"
    assert row["form_type"] == "10-K"
    assert row["section_text"] == "Risk factors text."
    assert row["label"] in ("down", "flat", "up")


def test_build_raises_when_no_rows_collected(tmp_path):
    out_path = tmp_path / "dataset.jsonl"
    with (
        patch.object(bsd, "load_universe", return_value=["TSLA"]),
        patch.object(sec_filings, "ticker_to_cik", return_value=None),
    ):
        try:
            bsd.build("narrow", out_path)
            assert False, "expected RuntimeError"
        except RuntimeError:
            pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_build_sec_dataset.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'build_sec_dataset'`

- [ ] **Step 3: Write the implementation**

Create `tools/build_sec_dataset.py`:
```python
"""Assemble the v87_sec_filing_reaction training dataset.

Orchestrates: broad-universe SEC filing fetch (sec_filings) -> section
extraction -> forward-return tercile labeling (sec_labels) -> a labeled
JSONL dataset consumed by tools/train_sec_sentiment.py. Only the extracted
section text is persisted — raw filing HTML is never written to disk.

Usage:
  SEC_EDGAR_USER_AGENT="YourApp you@example.com" \
    python tools/build_sec_dataset.py --universe broad \
    --out runs/sec_filing_reaction/dataset.jsonl
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

import sec_filings
import sec_labels

LOOKBACK_START = "2016-01-01"

ROOT = Path(__file__).resolve().parents[1]

# Deployment universe: live watchlist. ETFs (SPY, QQQ) are excluded — they
# have no SEC filer CIK and the sleeve returns neutral for them regardless.
NARROW_UNIVERSE = [
    "TSLA", "MSTR", "IONQ", "MU", "NVDA", "APLD", "COIN", "PLTR",
    "AMZN", "AVGO", "HOOD", "SMCI", "TSM",
]


def load_universe(name: str) -> list[str]:
    if name == "narrow":
        return list(NARROW_UNIVERSE)
    if name == "broad":
        sp500 = pd.read_html(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        )[0]
        return sorted(sp500["Symbol"].str.replace(".", "-", regex=False).unique().tolist())
    raise ValueError(f"unknown universe: {name}")


def _today() -> str:
    return pd.Timestamp.today().strftime("%Y-%m-%d")


def build(universe_name: str, out_path: Path) -> None:
    tickers = load_universe(universe_name)
    rows: list[dict] = []
    price_cache: dict[str, pd.DataFrame] = {}

    for ticker in tickers:
        cik = sec_filings.ticker_to_cik(ticker)
        if cik is None:
            continue
        refs = sec_filings.list_filings(ticker, cik, LOOKBACK_START)
        if not refs:
            continue

        benchmark = sec_labels.resolve_sector_benchmark(ticker)
        if benchmark not in price_cache:
            price_cache[benchmark] = sec_labels.fetch_price_history(
                benchmark, LOOKBACK_START, _today()
            )
        if ticker not in price_cache:
            price_cache[ticker] = sec_labels.fetch_price_history(
                ticker, LOOKBACK_START, _today()
            )

        for ref in refs:
            try:
                raw = sec_filings.fetch_filing_text(ref)
            except Exception:
                continue
            section = sec_filings.extract_section(raw, ref.form_type)
            fwd = sec_labels.compute_forward_return(ticker, ref.filing_date, benchmark, price_cache)
            if fwd is None:
                continue
            rows.append(
                {
                    "filing_id": f"{ticker}-{ref.accession_number}",
                    "ticker": ticker,
                    "form_type": ref.form_type,
                    "filing_date": ref.filing_date,
                    "section_text": section,
                    "forward_return": fwd.forward_return,
                }
            )

    if not rows:
        raise RuntimeError(
            "No filings collected — check SEC_EDGAR_USER_AGENT and network access"
        )

    labels = sec_labels.tercile_bucket([r["forward_return"] for r in rows])
    for row, label in zip(rows, labels):
        row["label"] = label

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    print(f"Wrote {len(rows)} labeled filings to {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", choices=["broad", "narrow"], default="broad")
    parser.add_argument(
        "--out", default=str(ROOT / "runs" / "sec_filing_reaction" / "dataset.jsonl")
    )
    args = parser.parse_args()
    build(args.universe, Path(args.out))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_build_sec_dataset.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add tools/build_sec_dataset.py tests/test_build_sec_dataset.py
git commit -m "Add SEC filing dataset assembly orchestration

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: Training script (time split + fine-tune)

**Files:**
- Create: `tools/train_sec_sentiment.py`
- Test: `tests/test_train_sec_sentiment.py`

**Interfaces:**
- Consumes: `tools.sec_filing_chunking.chunk_token_ids`.
- Produces: `LABEL_TO_ID = {"down": 0, "flat": 1, "up": 2}`, `ID_TO_LABEL`, `load_rows(path) -> list[dict]`, `split_by_time(rows) -> tuple[list, list, list]`, `ChunkedFilingDataset(rows, tokenizer)` (a `torch.utils.data.Dataset`), `collate(batch, pad_token_id) -> dict`, `train(dataset_path, out_dir, checkpoint=BASE_CHECKPOINT) -> None`. `BASE_CHECKPOINT = "nlpaueb/sec-bert-base"`.
- The smoke test uses a tiny randomly-initialized `BertConfig`, never the real 440MB checkpoint — keeps CI fast and disk-light per the Global Constraints.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_train_sec_sentiment.py`:
```python
"""Time-split correctness + a tiny-model training smoke test (no real checkpoint download)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import train_sec_sentiment as tss  # noqa: E402

transformers = pytest.importorskip("transformers")
torch = pytest.importorskip("torch")


def test_split_by_time_no_leakage():
    rows = [
        {"filing_date": "2020-01-01"},
        {"filing_date": "2022-12-31"},
        {"filing_date": "2023-06-01"},
        {"filing_date": "2023-12-31"},
        {"filing_date": "2024-01-01"},
    ]
    train, val, test = tss.split_by_time(rows)
    assert [r["filing_date"] for r in train] == ["2020-01-01", "2022-12-31"]
    assert [r["filing_date"] for r in val] == ["2023-06-01", "2023-12-31"]
    assert [r["filing_date"] for r in test] == ["2024-01-01"]
    # every row must land in exactly one split
    assert len(train) + len(val) + len(test) == len(rows)


def test_load_rows_reads_jsonl(tmp_path):
    path = tmp_path / "dataset.jsonl"
    path.write_text(
        json.dumps({"filing_date": "2020-01-01", "label": "up"}) + "\n"
        + json.dumps({"filing_date": "2020-01-02", "label": "down"}) + "\n"
    )
    rows = tss.load_rows(path)
    assert len(rows) == 2
    assert rows[0]["label"] == "up"


def _tiny_tokenizer_and_model():
    """A tiny, randomly-initialized BERT — never downloads the real checkpoint."""
    from transformers import BertConfig, BertForSequenceClassification, BertTokenizerFast

    # Use a minimal built-in vocab via the fast WordPiece tokenizer trained
    # on the fly from a tiny corpus, so this test needs zero network access.
    tokenizer = BertTokenizerFast.from_pretrained(
        "hf-internal-testing/tiny-random-bert"
    )
    config = BertConfig(
        vocab_size=tokenizer.vocab_size,
        hidden_size=16,
        num_hidden_layers=1,
        num_attention_heads=2,
        intermediate_size=32,
        num_labels=3,
    )
    model = BertForSequenceClassification(config)
    return tokenizer, model


def test_training_smoke_one_epoch_tiny_model(tmp_path):
    tokenizer, model = _tiny_tokenizer_and_model()

    rows = [
        {"filing_date": "2020-01-01", "section_text": "Risk is elevated this quarter.", "label": "down", "filing_id": "a"},
        {"filing_date": "2020-06-01", "section_text": "Revenue grew steadily and margins improved.", "label": "up", "filing_id": "b"},
        {"filing_date": "2020-09-01", "section_text": "Operations continued as expected.", "label": "flat", "filing_id": "c"},
        {"filing_date": "2020-12-01", "section_text": "Supply chain disruption hurt results.", "label": "down", "filing_id": "d"},
    ]
    dataset = tss.ChunkedFilingDataset(rows, tokenizer)
    assert len(dataset) >= len(rows)  # at least one chunk per filing

    batch = [dataset[i] for i in range(len(dataset))]
    collated = tss.collate(batch, tokenizer.pad_token_id)
    assert collated["input_ids"].shape[0] == len(batch)
    assert collated["labels"].shape[0] == len(batch)

    # One forward+backward pass must run without error on the tiny model.
    outputs = model(
        input_ids=collated["input_ids"],
        attention_mask=collated["attention_mask"],
        labels=collated["labels"],
    )
    assert outputs.loss is not None
    outputs.loss.backward()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_train_sec_sentiment.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'train_sec_sentiment'`

- [ ] **Step 3: Write the implementation**

Create `tools/train_sec_sentiment.py`:
```python
"""Fine-tune a domain-pretrained encoder on labeled SEC filings (v87).

Reads runs/sec_filing_reaction/dataset.jsonl (built by build_sec_dataset.py),
chunks each filing's section text via the shared sec_filing_chunking module,
fine-tunes a 3-class classification head via Hugging Face Trainer with a
strict TIME-based train/val/test split (never random — this is a trading
signal, lookahead leakage is not acceptable). Saves the fine-tuned
checkpoint to runs/sec_filing_reaction/weights/ (git-ignored — see
.gitignore:27). Uses save_strategy="no" so no intermediate checkpoints ever
touch disk; only the final model is written once, given how tight local
disk space is (see docs/superpowers/specs/2026-07-17-sec-filing-sentiment-sleeve-design.md).

Usage:
  python tools/train_sec_sentiment.py \
    --dataset runs/sec_filing_reaction/dataset.jsonl \
    --out runs/sec_filing_reaction/weights
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import Dataset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    Trainer,
    TrainingArguments,
)

from sec_filing_chunking import chunk_token_ids

BASE_CHECKPOINT = "nlpaueb/sec-bert-base"
FALLBACK_CHECKPOINT = "yiyanghkust/finbert-tone"
LABEL_TO_ID = {"down": 0, "flat": 1, "up": 2}
ID_TO_LABEL = {v: k for k, v in LABEL_TO_ID.items()}

TRAIN_END = "2022-12-31"
VAL_END = "2023-12-31"
# test = everything after VAL_END


def load_rows(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    return rows


def split_by_time(rows: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    train = [r for r in rows if r["filing_date"] <= TRAIN_END]
    val = [r for r in rows if TRAIN_END < r["filing_date"] <= VAL_END]
    test = [r for r in rows if r["filing_date"] > VAL_END]
    return train, val, test


class ChunkedFilingDataset(Dataset):
    """Each example is one (filing, chunk) pair; a filing's label is shared
    across all its chunks. Filing-level prediction is mean-pooled at
    inference time (tools/score_sec_filings.py), not during training."""

    def __init__(self, rows: list[dict], tokenizer):
        self.examples: list[dict] = []
        for row in rows:
            ids = tokenizer.encode(row["section_text"], add_special_tokens=False)
            for chunk_ids in chunk_token_ids(ids):
                input_ids = [tokenizer.cls_token_id, *chunk_ids, tokenizer.sep_token_id]
                self.examples.append(
                    {
                        "input_ids": input_ids,
                        "label": LABEL_TO_ID[row["label"]],
                        "filing_id": row["filing_id"],
                    }
                )

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, idx: int) -> dict:
        ex = self.examples[idx]
        return {
            "input_ids": ex["input_ids"],
            "attention_mask": [1] * len(ex["input_ids"]),
            "label": ex["label"],
        }


def collate(batch: list[dict], pad_token_id: int) -> dict:
    max_len = max(len(b["input_ids"]) for b in batch)
    input_ids = torch.full((len(batch), max_len), pad_token_id, dtype=torch.long)
    attention_mask = torch.zeros((len(batch), max_len), dtype=torch.long)
    labels = torch.zeros(len(batch), dtype=torch.long)
    for i, b in enumerate(batch):
        n = len(b["input_ids"])
        input_ids[i, :n] = torch.tensor(b["input_ids"], dtype=torch.long)
        attention_mask[i, :n] = torch.tensor(b["attention_mask"], dtype=torch.long)
        labels[i] = b["label"]
    return {"input_ids": input_ids, "attention_mask": attention_mask, "labels": labels}


def compute_metrics(eval_pred) -> dict:
    logits, labels = eval_pred
    preds = np.argmax(logits, axis=-1)
    return {"accuracy": float((preds == labels).mean())}


def train(dataset_path: Path, out_dir: Path, checkpoint: str = BASE_CHECKPOINT) -> None:
    rows = load_rows(dataset_path)
    train_rows, val_rows, test_rows = split_by_time(rows)
    if not train_rows or not val_rows:
        raise RuntimeError(
            f"Not enough data for a time split: train={len(train_rows)} val={len(val_rows)}"
        )

    tokenizer = AutoTokenizer.from_pretrained(checkpoint)
    model = AutoModelForSequenceClassification.from_pretrained(
        checkpoint, num_labels=3, id2label=ID_TO_LABEL, label2id=LABEL_TO_ID
    )

    train_ds = ChunkedFilingDataset(train_rows, tokenizer)
    val_ds = ChunkedFilingDataset(val_rows, tokenizer)

    args = TrainingArguments(
        output_dir=str(out_dir / "_scratch"),
        per_device_train_batch_size=8,
        per_device_eval_batch_size=8,
        num_train_epochs=3,
        logging_steps=50,
        save_strategy="no",  # disk is tight — save once, manually, at the end
        report_to="none",
    )

    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        data_collator=lambda batch: collate(batch, tokenizer.pad_token_id),
        compute_metrics=compute_metrics,
    )
    trainer.train()
    val_metrics = trainer.evaluate(val_ds)
    print(f"Validation metrics: {val_metrics}")

    out_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out_dir)
    tokenizer.save_pretrained(out_dir)

    if test_rows:
        test_ds = ChunkedFilingDataset(test_rows, tokenizer)
        test_metrics = trainer.evaluate(test_ds)
        print(f"Held-out test metrics: {test_metrics}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--checkpoint", default=BASE_CHECKPOINT)
    args = parser.parse_args()
    train(Path(args.dataset), Path(args.out), args.checkpoint)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_train_sec_sentiment.py -v`
Expected: 3 passed. (First run downloads the tiny `hf-internal-testing/tiny-random-bert` tokenizer, a few KB — not the real checkpoint.)

- [ ] **Step 5: Check disk usage before moving on**

Run: `df -h /Users/syriljacob/Desktop/TradingAlgoWork`
Expected: available space still comfortably above ~1.5GB before Task 7 (which does download the real checkpoint). If it's tighter than that, pause and tell the user before proceeding.

- [ ] **Step 6: Commit**

```bash
git add tools/train_sec_sentiment.py tests/test_train_sec_sentiment.py
git commit -m "Add SEC filing sentiment training script (time-split fine-tune)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: Scoring / inference script

**Files:**
- Create: `tools/score_sec_filings.py`
- Test: `tests/test_score_sec_filings.py`

**Interfaces:**
- Consumes: `tools.sec_filing_chunking.chunk_token_ids`.
- Produces: `ID_TO_LABEL`, `score_filing(model, tokenizer, device, text: str) -> tuple[str, float]`. Writes `runs/sec_filing_reaction/predictions.jsonl` shaped `{ticker, filing_date, form_type, predicted_label, predicted_prob}`. Consumed by Task 8 (`signal_engine.py`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_score_sec_filings.py`:
```python
"""Mean-pooling inference logic test — tiny model, no real checkpoint download."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

torch = pytest.importorskip("torch")

import score_sec_filings as ssf  # noqa: E402


def _tiny_tokenizer_and_model():
    from transformers import BertConfig, BertForSequenceClassification, BertTokenizerFast

    tokenizer = BertTokenizerFast.from_pretrained("hf-internal-testing/tiny-random-bert")
    config = BertConfig(
        vocab_size=tokenizer.vocab_size,
        hidden_size=16,
        num_hidden_layers=1,
        num_attention_heads=2,
        intermediate_size=32,
        num_labels=3,
    )
    model = BertForSequenceClassification(config)
    model.eval()
    return tokenizer, model


def test_score_filing_returns_valid_label_and_probability():
    tokenizer, model = _tiny_tokenizer_and_model()
    device = torch.device("cpu")
    label, prob = ssf.score_filing(model, tokenizer, device, "Revenue grew steadily this quarter.")
    assert label in ssf.ID_TO_LABEL.values()
    assert 0.0 <= prob <= 1.0


def test_score_filing_handles_long_text_via_multiple_chunks():
    tokenizer, model = _tiny_tokenizer_and_model()
    device = torch.device("cpu")
    long_text = "Risk factor discussion. " * 2000  # forces multiple chunks
    label, prob = ssf.score_filing(model, tokenizer, device, long_text)
    assert label in ssf.ID_TO_LABEL.values()
    assert 0.0 <= prob <= 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_score_sec_filings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'score_sec_filings'`

- [ ] **Step 3: Write the implementation**

Create `tools/score_sec_filings.py`:
```python
"""Score SEC filings with the fine-tuned v87 model (mean-pooled over chunks).

Produces runs/sec_filing_reaction/predictions.jsonl — a lightweight
(ticker, filing_date, form_type, predicted_label, predicted_prob) lookup
consumed by models/poc_va_macdha/v87_sec_filing_reaction/signal_engine.py
at backtest/live time, so the sleeve itself never needs to load the full
transformer (see that file's docstring).

Usage:
  python tools/score_sec_filings.py \
    --dataset runs/sec_filing_reaction/dataset.jsonl \
    --weights runs/sec_filing_reaction/weights \
    --out runs/sec_filing_reaction/predictions.jsonl
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
import torch.nn.functional as F
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from sec_filing_chunking import chunk_token_ids

ID_TO_LABEL = {0: "down", 1: "flat", 2: "up"}


def score_filing(model, tokenizer, device, text: str) -> tuple[str, float]:
    """Mean-pool softmax probabilities across a filing's chunks."""
    ids = tokenizer.encode(text, add_special_tokens=False)
    chunks = chunk_token_ids(ids)
    probs = []
    with torch.no_grad():
        for chunk in chunks:
            input_ids = torch.tensor(
                [[tokenizer.cls_token_id, *chunk, tokenizer.sep_token_id]], device=device
            )
            attention_mask = torch.ones_like(input_ids)
            logits = model(input_ids=input_ids, attention_mask=attention_mask).logits
            probs.append(F.softmax(logits, dim=-1).squeeze(0).cpu())
    mean_probs = torch.stack(probs).mean(dim=0)
    pred_id = int(torch.argmax(mean_probs).item())
    return ID_TO_LABEL[pred_id], float(mean_probs[pred_id].item())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--weights", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    tokenizer = AutoTokenizer.from_pretrained(args.weights)
    model = AutoModelForSequenceClassification.from_pretrained(args.weights).to(device)
    model.eval()

    out_rows = []
    with open(args.dataset, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            label, prob = score_filing(model, tokenizer, device, row["section_text"])
            out_rows.append(
                {
                    "ticker": row["ticker"],
                    "filing_date": row["filing_date"],
                    "form_type": row["form_type"],
                    "predicted_label": label,
                    "predicted_prob": prob,
                }
            )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for row in out_rows:
            f.write(json.dumps(row) + "\n")
    print(f"Scored {len(out_rows)} filings -> {out_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_score_sec_filings.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add tools/score_sec_filings.py tests/test_score_sec_filings.py
git commit -m "Add SEC filing scoring/inference script

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 8: The sleeve — `signal_engine.py`

**Files:**
- Create: `models/poc_va_macdha/v87_sec_filing_reaction/signal_engine.py`
- Create: `models/poc_va_macdha/v87_sec_filing_reaction/config.json`
- Create: `models/poc_va_macdha/v87_sec_filing_reaction/hunt_config.json`
- Test: `tests/test_v87_signal_engine.py`

**Interfaces:**
- Produces: `SignalEngine` class implementing `generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]`, `self.last_confidence: Dict[str, pd.Series]`, `self.last_sleeve: Dict[str, pd.Series]` — the same contract as `models/poc_va_macdha/v83_adaptive_regime/signal_engine.py`. Auto-discovered by `tools/model_registry.list_engine_models()` via its `models/poc_va_macdha/v*/signal_engine.py` glob — no registry code changes needed.
- This is the task that directly implements spec §3 and §4 — treat the point-in-time test as the most important test in the whole plan.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_v87_signal_engine.py`:
```python
"""Point-in-time correctness, no-filer neutral, staleness decay, and backtest
smoke tests for the v87_sec_filing_reaction sleeve.

Tests construct a SignalEngine via __new__ (bypassing __init__'s file I/O)
and inject a small in-memory predictions dict directly — this tests the
signal logic in isolation from hunt_config.json / predictions.jsonl loading.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SLEEVE_DIR = Path(__file__).resolve().parents[1] / "models" / "poc_va_macdha" / "v87_sec_filing_reaction"
sys.path.insert(0, str(SLEEVE_DIR))

import signal_engine as se  # noqa: E402


def _engine(predictions: dict, staleness_days: int = 100, signal_scale: float = 0.30) -> se.SignalEngine:
    eng = se.SignalEngine.__new__(se.SignalEngine)
    eng._predictions = predictions
    eng._staleness_days = staleness_days
    eng._signal_scale = signal_scale
    eng.last_confidence = {}
    eng.last_sleeve = {}
    return eng


def _daily_frame(start: str, end: str) -> pd.DataFrame:
    idx = pd.date_range(start, end, freq="D")
    return pd.DataFrame({"close": np.arange(len(idx), dtype=float)}, index=idx)


def test_point_in_time_no_future_leakage():
    df = _daily_frame("2024-01-01", "2024-01-20")
    predictions = {
        "TSLA": [{"filing_date": "2024-01-10", "predicted_label": "up", "predicted_prob": 0.9}]
    }
    eng = _engine(predictions)
    out = eng.generate({"TSLA.US": df})
    series = out["TSLA.US"]

    before = series[df.index <= "2024-01-10"]
    assert (before == 0.0).all(), "signal leaked on/before the filing date"

    after = series[df.index > "2024-01-10"]
    assert (after != 0.0).all()
    assert np.isclose(after.iloc[0], 1.0 * 0.9 * 0.30)


def test_no_filer_symbol_returns_neutral():
    df = _daily_frame("2024-01-01", "2024-01-10")
    eng = _engine(predictions={})  # SPY/QQQ: no entry at all
    out = eng.generate({"SPY.US": df})
    assert (out["SPY.US"] == 0.0).all()
    assert (eng.last_confidence["SPY.US"] == se.NEUTRAL_CONFIDENCE).all()


def test_staleness_decay_to_neutral():
    df = _daily_frame("2024-01-01", "2024-06-01")  # ~150 calendar days
    predictions = {
        "MU": [{"filing_date": "2024-01-05", "predicted_label": "down", "predicted_prob": 0.8}]
    }
    eng = _engine(predictions, staleness_days=100)
    out = eng.generate({"MU.US": df})
    series = out["MU.US"]

    assert series.loc["2024-01-10"] != 0.0  # soon after filing: active
    assert series.loc["2024-06-01"] == 0.0  # well past staleness window: neutral


def test_generate_smoke_no_nan_or_inf_across_symbols():
    df = _daily_frame("2024-01-01", "2024-03-01")
    predictions = {
        "NVDA": [{"filing_date": "2024-01-15", "predicted_label": "flat", "predicted_prob": 0.5}]
    }
    eng = _engine(predictions)
    data_map = {"NVDA.US": df, "SPY.US": df, "QQQ.US": df}
    out = eng.generate(data_map)

    for code, series in out.items():
        assert not series.isna().any(), f"{code} has NaN"
        assert np.isfinite(series.to_numpy()).all(), f"{code} has Inf"
        assert list(series.index) == list(df.index)
        assert code in eng.last_confidence
        assert code in eng.last_sleeve
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_v87_signal_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'signal_engine'`

- [ ] **Step 3: Write the implementation**

Create `models/poc_va_macdha/v87_sec_filing_reaction/signal_engine.py`:
```python
"""v87_sec_filing_reaction: SEC filing reaction sleeve.

Event-driven signal: reads precomputed filing predictions (see
tools/score_sec_filings.py) and forward-fills each symbol's most recent
filing prediction across subsequent bars via pd.merge_asof, decaying to
neutral once the filing is stale (see STALENESS_DAYS default below).
Symbols with no SEC filer (SPY, QQQ, or any ticker missing from the
predictions file) always return neutral — this sleeve never blocks or
gates other sleeves for them.

Point-in-time discipline: a bar's signal only ever reflects filings dated
STRICTLY before that bar's date. This is enforced in _build_symbol_series
by shifting each filing's timestamp forward by 1ns before the merge_asof
backward join, turning the join's default on-or-before semantics into
strictly-before.

This module deliberately never imports torch/transformers — it only reads
a small JSONL lookup file, so every backtest run of this sleeve stays as
fast and disk-light as any other sleeve in the family. The heavy ML
dependencies are confined to tools/train_sec_sentiment.py and
tools/score_sec_filings.py, run offline.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pandas as pd

LABEL_SCORE = {"down": -1.0, "flat": 0.0, "up": 1.0}
NEUTRAL_CONFIDENCE = 0.5


def _find_repo_root(anchor: Path) -> Path:
    for p in anchor.resolve().parents:
        if (p / "models" / "poc_va_macdha").exists():
            return p
    raise RuntimeError("Could not find TradingAlgoWork repo root")


def _load_hunt(self_dir: Path) -> Dict[str, Any]:
    defaults = {
        "predictions_path": "runs/sec_filing_reaction/predictions.jsonl",
        "staleness_days": 100,
        "signal_scale": 0.30,
    }
    hunt_path = self_dir / "hunt_config.json"
    if hunt_path.exists():
        try:
            overrides = json.loads(hunt_path.read_text(encoding="utf-8"))
            if isinstance(overrides, dict):
                defaults.update(overrides)
        except json.JSONDecodeError:
            pass
    return defaults


def _load_predictions(path: Path) -> Dict[str, list[dict]]:
    """Load predictions grouped by ticker; each ticker's list need not be
    pre-sorted, _build_symbol_series sorts by filing_date itself."""
    by_ticker: Dict[str, list[dict]] = {}
    if not path.exists():
        return by_ticker
    with path.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            by_ticker.setdefault(row["ticker"], []).append(row)
    return by_ticker


class SignalEngine:
    """SEC filing reaction sleeve — point-in-time, event-driven, forward-filled."""

    def __init__(self) -> None:
        self_dir = Path(__file__).resolve().parent
        repo_root = _find_repo_root(self_dir)
        self._hunt = _load_hunt(self_dir)

        predictions_path = repo_root / self._hunt["predictions_path"]
        self._predictions = _load_predictions(predictions_path)
        self._staleness_days = int(self._hunt["staleness_days"])
        self._signal_scale = float(self._hunt["signal_scale"])

        self.last_confidence: Dict[str, pd.Series] = {}
        self.last_sleeve: Dict[str, pd.Series] = {}  # 0=neutral, 4=sec_filing_reaction

    @staticmethod
    def _symbol_key(code: str) -> str:
        # data_map codes look like "TSLA.US"; predictions are keyed by bare ticker.
        return code.split(".")[0].upper()

    def _build_symbol_series(self, code: str, idx: pd.DatetimeIndex) -> tuple[pd.Series, pd.Series]:
        ticker = self._symbol_key(code)
        rows = self._predictions.get(ticker)
        if not rows:
            return (
                pd.Series(0.0, index=idx),
                pd.Series(NEUTRAL_CONFIDENCE, index=idx),
            )

        filings = pd.DataFrame(rows)
        filings["filing_date"] = pd.to_datetime(filings["filing_date"])
        filings["score"] = filings.apply(
            lambda r: LABEL_SCORE[r["predicted_label"]] * r["predicted_prob"], axis=1
        )
        filings = filings.sort_values("filing_date")

        # merge_asof's "backward" direction includes an exact-equal match;
        # shift filing_date forward by 1ns so the join becomes
        # strictly-before rather than on-or-before.
        filings_shifted = filings.copy()
        filings_shifted["filing_date"] = filings_shifted["filing_date"] + pd.Timedelta(nanoseconds=1)

        bars = (
            pd.DataFrame({"bar_date": pd.DatetimeIndex(idx)})
            .sort_values("bar_date")
            .reset_index(drop=True)
        )
        joined = pd.merge_asof(
            bars,
            filings_shifted[["filing_date", "score", "predicted_prob"]],
            left_on="bar_date",
            right_on="filing_date",
            direction="backward",
        ).set_index("bar_date")

        # Staleness is measured in calendar days as a practical proxy for
        # the spec's "~100 trading days / one filing cycle" threshold.
        age_days = (joined.index.to_series() - joined["filing_date"]).dt.days
        stale_or_missing = joined["filing_date"].isna() | (age_days > self._staleness_days)
        joined.loc[stale_or_missing, "score"] = 0.0
        joined.loc[stale_or_missing, "predicted_prob"] = NEUTRAL_CONFIDENCE

        joined = joined.reindex(idx)
        score = pd.Series(joined["score"].to_numpy(), index=idx)
        conf = pd.Series(joined["predicted_prob"].to_numpy(), index=idx)
        return score, conf

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        out: Dict[str, pd.Series] = {}
        self.last_confidence = {}
        self.last_sleeve = {}

        for code, df in data_map.items():
            if df is None or df.empty:
                out[code] = pd.Series(0.0, index=pd.DatetimeIndex([]))
                continue
            idx = df.index
            score, conf = self._build_symbol_series(code, idx)
            out[code] = (score * self._signal_scale).astype(float)
            self.last_confidence[code] = conf.astype(float)
            self.last_sleeve[code] = ((score.abs() > 1e-9).astype(int) * 4)

        return out
```

Create `models/poc_va_macdha/v87_sec_filing_reaction/hunt_config.json`:
```json
{
  "predictions_path": "runs/sec_filing_reaction/predictions.jsonl",
  "staleness_days": 100,
  "signal_scale": 0.30
}
```

Create `models/poc_va_macdha/v87_sec_filing_reaction/config.json` (mirrors `v83_adaptive_regime/config.json`'s backtest-run shape):
```json
{
  "source": "local",
  "codes": ["TSLA.US", "MSTR.US", "IONQ.US", "MU.US", "NVDA.US", "APLD.US", "COIN.US", "PLTR.US", "AMZN.US", "AVGO.US", "HOOD.US", "SMCI.US", "TSM.US", "SPY.US", "QQQ.US"],
  "interval": "1D",
  "commission": 0.001,
  "engine": "daily",
  "strategy": {
    "name": "v87_sec_filing_reaction",
    "model_version": "v87_sec_filing_reaction",
    "note": "SEC filing reaction sleeve. Event-driven; forward-fills the most recent filing's predicted class per symbol until staleness_days elapses. SPY/QQQ included in the backtest codes list to verify no-filer neutral behavior end-to-end."
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_v87_signal_engine.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add models/poc_va_macdha/v87_sec_filing_reaction/ tests/test_v87_signal_engine.py
git commit -m "Add v87_sec_filing_reaction sleeve (SignalEngine + config)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 9: Registry auto-discovery check + full suite run

**Files:**
- No new files — verification only.

**Interfaces:**
- Consumes: `tools.model_registry.list_engine_models()`.

- [ ] **Step 1: Confirm the new sleeve is auto-discovered**

Run:
```bash
python3 -c "
import sys
sys.path.insert(0, 'tools')
import model_registry as mr
models = mr.list_engine_models()
assert 'v87_sec_filing_reaction' in models, models
print('v87_sec_filing_reaction is registered:', 'v87_sec_filing_reaction' in models)
"
```
Expected: `v87_sec_filing_reaction is registered: True`

No `tools/model_registry.py` edits are needed for this — `list_engine_models()` already globs `models/poc_va_macdha/v*/signal_engine.py` (see `tools/model_registry.py:687`).

- [ ] **Step 2: Run the full new test suite together**

Run: `python3 -m pytest tests/test_sec_filing_chunking.py tests/test_sec_filings.py tests/test_sec_labels.py tests/test_build_sec_dataset.py tests/test_train_sec_sentiment.py tests/test_score_sec_filings.py tests/test_v87_signal_engine.py -v`
Expected: all tests pass (22 total across the 7 files).

- [ ] **Step 3: Run the full existing repo test suite to confirm no regressions**

Run: `python3 -m pytest tests/ -v`
Expected: all previously-passing tests still pass; the 7 new files add to the total.

- [ ] **Step 4: Final disk usage check**

Run: `df -h /Users/syriljacob/Desktop/TradingAlgoWork`
Expected: report the available space to the user — this task never downloaded the real `sec-bert-base` checkpoint (only the tiny test model), so usage should be close to where Task 1 left it. Note explicitly that running the live pipeline (`build_sec_dataset.py` with `--universe broad`, then `train_sec_sentiment.py`, then `score_sec_filings.py`) is a separate, longer-running step the user triggers manually once `SEC_EDGAR_USER_AGENT` is set — it is NOT part of this plan's automated task sequence, since it needs live network access, takes hours, and is exactly the step that will consume the ~450MB checkpoint + broad-universe dataset space.

- [ ] **Step 5: Commit final state (if anything changed)**

```bash
git status --short
```
If clean (Task 9 was verification-only), nothing to commit — just confirm the 8 prior commits are in place with `git log --oneline -10`.

---

## Post-plan: running the live pipeline (manual, not part of this plan)

Once all 9 tasks are complete and merged, the actual data collection + training + scoring run is a separate manual invocation (not automated here, since it needs live network access and takes hours):

```bash
export SEC_EDGAR_USER_AGENT="YourName your-contact-email@example.com"
python3 tools/build_sec_dataset.py --universe broad --out runs/sec_filing_reaction/dataset.jsonl
python3 tools/train_sec_sentiment.py --dataset runs/sec_filing_reaction/dataset.jsonl --out runs/sec_filing_reaction/weights
python3 tools/score_sec_filings.py --dataset runs/sec_filing_reaction/dataset.jsonl --weights runs/sec_filing_reaction/weights --out runs/sec_filing_reaction/predictions.jsonl
```

After that, `v87_sec_filing_reaction` is a fully backtestable sleeve like any other in `models/poc_va_macdha/`. Promotion to live deployment (`DEPLOYMENT_MANIFEST.json`, `runs/calibration/active/`, `WINNER.json`) is explicitly out of scope per the spec and requires clearing this repo's existing backtest/calibration promotion gates first.
