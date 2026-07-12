# v25_regime_grow

Hybrid **equity hedge + options attack** book for live trading and growth eval.

| Layer | Implementation |
|-------|----------------|
| SIDE | `v23_devin_overlay` (frozen WINNER DNA) |
| WHETHER / HOW MUCH / VEHICLE | `tools/risk_manager.py` + `RISK_POLICY.json` |
| Options structure | `tools/options_picker.py` |
| Human playbook | `RISK_PLAYBOOK.md` |

## Quick start (live)

### Frontend (recommended)

```bash
cd apps/trade-desk && npm run dev
# open http://localhost:3000/live
```

Nav: **Live** — plan ticket, scan book, options structure, exit rules.

### CLI

```bash
# Full live ticket (features + macro + risk + options)
python3 tools/live_plan.py --symbol APLD --account 1000 --json
python3 tools/live_plan.py --scan --account 1000

# Portfolio mode
python3 tools/risk_manager.py status --equity 1000 --peak 1000

# Plan a name (manual conf)
python3 tools/risk_manager.py plan --symbol APLD --account 1000 --conf 0.85 --vol-z 1.8 --qqq-ok

# Open-position react
python3 tools/risk_manager.py check-open --vehicle options --entry 1.5 --pnl-pct -0.32
```

### Flask API (optional)

```bash
python3 services/api_server.py
# GET /live-plan/APLD?account=1000&no_model=1
# GET /live-scan?account=1000
```

## Status

- **live-ready (operator)** — risk policy + live_plan + frontend Live desk
- Options path is **rules + paper** until defined-risk OOS evidence is thick enough to promote
- See `RESEARCH_EXPANSION.md`
