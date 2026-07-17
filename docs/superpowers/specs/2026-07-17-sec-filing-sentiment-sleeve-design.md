# SEC Filing Sentiment Sleeve — Design Spec

**Date:** 2026-07-17
**Status:** Approved (Approach 1, broad-universe training)
**New sleeve:** `models/poc_va_macdha/v87_sec_filing_reaction/`
**Cost constraint:** zero paid dependencies — free data sources, free HF checkpoints, local training only

---

## Goal

Train a Hugging Face transformer to read SEC filings (10-K / 10-Q / 8-K) and predict how a stock will move relative to its sector benchmark over the following ~10-20 trading days. Wrap that model in a new standalone sleeve, `v87_sec_filing_reaction`, that plugs into the existing `poc_va_macdha` model family using the same `SignalEngine.generate(data_map) -> Dict[str, pd.Series]` contract as `v83_adaptive_regime` and its siblings.

This is an event-driven signal (filings arrive a handful of times a year per company), unlike the bar-by-bar OHLCV sleeves already in the family. The design forward-fills each filing's prediction across subsequent bars with a staleness decay, so it still satisfies the per-bar contract every other sleeve relies on.

**Out of scope for this pass:** promoting the sleeve to live deployment (`DEPLOYMENT_MANIFEST.json`, `runs/calibration/active/`, `WINNER.json`) — that only happens after it clears the repo's existing backtest/calibration promotion gates, same bar as any other model. Also out of scope: live/real-time EDGAR polling — first cut is historical, backtest-oriented data only.

---

## Architecture overview

```
SEC EDGAR (broad universe: S&P 500)         yfinance OHLCV
        │                                          │
        ▼                                          ▼
 tools/sec_filings.py  ──────────────────►  forward-return labeler
  (fetch + section extraction)               (terciles vs sector ETF,
        │                                     10-20 trading day window)
        ▼                                          │
  labeled dataset (filing_id, ticker, form_type,   │
  filing_date, section_text, label, forward_return)◄
        │
        ▼
 tools/train_sec_sentiment.py
  (chunk → sec-bert-base fine-tune via HF Trainer,
   time-based train/val/test split)
        │
        ▼
 models/poc_va_macdha/v87_sec_filing_reaction/
  ├─ signal_engine.py   (SignalEngine contract, forward-fill + decay,
  │                       ETF/no-filer → neutral)
  └─ config.json        (points at runs/sec_filing_reaction/weights/)
        │
        ▼ (git-ignored, runs/*/)
 runs/sec_filing_reaction/weights/   (fine-tuned checkpoint, save_pretrained)
```

**Reuse:**
- `yfinance` for OHLCV (already used by `tools/econ_narrative.py`)
- Existing `SignalEngine` contract from `models/poc_va_macdha/v83_adaptive_regime/signal_engine.py`
- `confidence_runtime.py`'s `ORDINAL_CONFIDENCE_CAP` clamp for `last_confidence`

**New dependencies:** `torch`, `transformers` (not currently in `requirements.txt`). No paid API calls anywhere in this pipeline.

---

## §1 Data pipeline (`tools/sec_filings.py`)

### Fetch

- SEC EDGAR full-text search / submissions API — free, requires a compliant `User-Agent` header, no API key.
- **Broad training universe:** current S&P 500 constituents, pulled once from a free public source (e.g. Wikipedia's S&P 500 table) and cached as a static list. Point-in-time index-membership drift (companies added/removed over the 2016-present window) is a non-issue here — this list only sources *training* text volume, not the live signal, which only ever runs on the fixed narrow watchlist.
- **Deployment universe:** the live watchlist (`TRAIN_UNIVERSE` in `tools/bounce_predict.py` plus `v65_spec_*` specialists — SPY/QQQ excluded, they have no SEC filer CIK).
- Filing types: 10-K, 10-Q, 8-K. Lookback window: **2016-01-01 → present** (~10 years) — recent enough that filing language and market microstructure stay reasonably comparable to today, long enough that broad-universe volume should reach low-thousands of examples.

### Section extraction

- 10-K / 10-Q → Item 1A (Risk Factors) + Item 7 (MD&A).
- 8-K → narrative body.

### Labeling

- Forward return vs. sector benchmark ETF, computed from `yfinance` OHLCV over the ~10-20 trading days after the filing date.
- **Tercile buckets** (up / flat / down), not a fixed % threshold — keeps classes balanced regardless of the underlying volatility regime.

### Output

- Labeled dataset artifact (parquet/jsonl): `filing_id, ticker, form_type, filing_date, section_text, label, forward_return`.

---

## §2 Model training (`tools/train_sec_sentiment.py`)

### Chunking

- Tokenize with the base checkpoint's tokenizer, chunk to its 512-token window with a ~50-token overlap so sentences aren't cut mid-thought.
- Filing-level prediction = mean-pooled softmax across its chunks.

### Base checkpoint

- Primary: `nlpaueb/sec-bert-base` (pretrained on EDGAR filings — closest domain match).
- Fallback: `yiyanghkust/finbert-tone` if `sec-bert-base` underperforms on validation.

### Training

- HF `Trainer`, 3-class classification head, fine-tuned end-to-end.
- Runs locally on Apple Silicon via MPS — no cloud GPU rental.

### Split discipline (critical — no lookahead leakage)

- **Time-based split, never random.** E.g. train through 2022, validate 2023, test 2024-2025.
- This mirrors the no-lookahead discipline already enforced elsewhere in this repo (see the cross-fitted calibration and ordinal-confidence-cap comments in `tools/confidence_runtime.py`).

### Evaluation

- Standard classification metrics (accuracy / F1 per class) on the time-held-out test split.
- Plus a trading-specific check: does the predicted class actually correlate with realized forward returns out of sample.

### Artifact

- Fine-tuned weights + tokenizer via `save_pretrained`, stored under `runs/sec_filing_reaction/weights/` — this repo already git-ignores `runs/*/` wholesale (`.gitignore:27`), so the 100s-of-MB checkpoint never touches version control. `v87_sec_filing_reaction/config.json` (committed, small) points at that path so the sleeve can locate the weights at load time.

---

## §3 Sleeve integration (`v87_sec_filing_reaction/signal_engine.py`)

- Implements the same `SignalEngine.generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]` contract as `v83_adaptive_regime`.
- For each bar: look up the most recent filing's predicted class/score for that symbol **strictly before that bar's date** (point-in-time correct — no lookahead), forward-fill it across subsequent bars.
- **Staleness decay:** if the most recent filing is older than ~100 trading days (roughly one filing cycle), decay to neutral rather than extrapolating a stale prediction indefinitely.
- **No-filer symbols** (SPY, QQQ): always return neutral / no tilt. They defer entirely to the other sleeves already in the routing system — this sleeve never blocks or gates them.
- `self.last_confidence`: predicted class's softmax probability, mapped into the existing 0.0-1.0 contract and passed through `ORDINAL_CONFIDENCE_CAP` in `confidence_runtime.py`, same as every other uncalibrated sleeve in the family.
- `self.last_sleeve`: new sleeve ID per the family's existing numbering convention.

---

## §4 Testing

- **Point-in-time correctness** (highest priority): a bar's signal must only ever reflect filings dated strictly before that bar — no future filing leaks into a past bar's signal. This is the single most important test given how much this codebase already guards against lookahead leakage.
- No-filer symbols (SPY, QQQ) return neutral, not an error.
- Staleness decay kicks in beyond the ~100-trading-day threshold.
- Backtest smoke test: `generate()` produces well-formed `pd.Series` output (no NaNs/Infs) across the full deployment universe.
- **Not in scope:** exhaustively validating predictive power beyond the training pipeline's own held-out time-split evaluation — that judgment belongs to the backtest/promotion-gate step, which is out of scope for this pass (see Goal section).

---

## Approval record

- Text source: **SEC filings** (10-K/10-Q/8-K)
- Labels: **forward-return, self-supervised** (terciles vs. sector benchmark)
- Prediction target: **3-class direction, position horizon** (~10-20 trading days)
- Integration: **standalone sleeve** in `model_registry.py` family, not a feature/gate
- Training universe: **broad (S&P 500)**, deployment universe: **narrow (live watchlist)**
- Approach: **1** — fine-tune a domain-pretrained checkpoint (`sec-bert-base`) with chunk-pooling, over Approach 2 (frozen embeddings + XGBoost head) and Approach 3 (long-context full fine-tune)
- Cost: **zero** — free data sources, free HF checkpoints, local MPS training
- User cleared to start implementation
