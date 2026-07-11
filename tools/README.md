# Trade Desk CLI

Live assistant for **poc_va_macdha** models. Enter a ticker → entry/stop/size/hit-prob. Rank models overall or **per stock**. Switch engines with `--model`.

## Findings / improve loop (shared)

Follow `models/_shared/PLAYBOOK.md`. After every research or backtest claim:

```bash
.venv/bin/python tools/findings.py list
.venv/bin/python tools/findings.py working
.venv/bin/python tools/findings.py failed
.venv/bin/python tools/findings.py next
.venv/bin/python tools/findings.py check --metrics-json models/poc_va_macdha/v14_risk_kelly/results.json
.venv/bin/python tools/findings.py record --family poc_va_macdha --version vN --status auto \
  --kind specialist_routing --summary "one-line result" \
  --metrics-json models/poc_va_macdha/vN/results.json
```

On **fail** → `models/_shared/FAILURE_PROTOCOL.md` (re-research; 3 fails same kind → new EDGE_RESEARCH).

## Which model?
- **Default:** `v14_risk_kelly` (best overall risk-adjusted: Sharpe 1.72, DD −24%)
- **Per stock:** use `--model auto` to pick the historically best *runnable* engine for that symbol
- **Manual:** `--model v12_regime_router` / `v8_4h_daily` / `v3_momflag` / etc.

## Commands

```bash
cd /Users/syriljacob/Desktop/TradingAlgoWork

# Analyze with default (v14)
.venv/bin/python3 tools/trade_desk.py TSLA --account 50000

# Use historically best engine for this ticker
.venv/bin/python3 tools/trade_desk.py IONQ --model auto

# Force a specific model
.venv/bin/python3 tools/trade_desk.py MU --model v12_regime_router

# Rank all models (portfolio)
.venv/bin/python3 tools/trade_desk.py rank
.venv/bin/python3 tools/trade_desk.py rank --engines-only

# Rank models on one stock
.venv/bin/python3 tools/trade_desk.py rank --symbol IONQ --engines-only

# Day / week picks
.venv/bin/python3 tools/trade_desk.py picks --horizon day --model v14_risk_kelly
.venv/bin/python3 tools/trade_desk.py picks --horizon week --model auto

# Sector rotation first → stocks in top hot sectors (default top 5)
.venv/bin/python3 tools/trade_desk.py rotate
.venv/bin/python3 tools/trade_desk.py rotate --top 5 --horizon day
.venv/bin/python3 tools/trade_desk.py picks --sectors memory,photonics,ai_infra,metals
```

## Actions (plain English)
| Action | Meaning |
|--------|---------|
| **BUY NOW** | Classic pullback-in-value — take the trade |
| **BUY BREAKOUT** | Just clearing highs with volume — take **smaller** size |
| **BREAKOUT WATCH** | Pressing highs / about to break — set buy-stop alerts |
| **PULLBACK ZONE** | Trend OK but extended — wait for dip into value |
| **WAIT / AVOID** | Stand aside |

## Ranking score
`0.55×win_rate + 0.30×sharpe_norm + 0.15×PF_norm − DD_penalty`  
Sources: each version’s `results.json` + `TRAINING_LEADERBOARD.json`.

## What you get per symbol
- Verdict, confidence, hit probability (blends live conf + that model’s hist WR on the name)
- Entry / −1.5 ATR stop / trail arm (or breakout trigger level)
- Shares & $ risk (1% account default, confidence sleeve)
- Checklist + **model ranks for that stock**
- Sectors: mag7, memory, photonics, energy, space, quantum, ai_infra, banks, biotech, metals, consumer, crypto, beta