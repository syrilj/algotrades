# IB / live desk hookup

The desk does **not** place broker orders. It builds tickets and adapts size from paper results so you can plug IB later safely.

## Equity WINNER

- Engine: `v39b_live_adapt` (`models/poc_va_macdha/WINNER.json`)
- Philosophy: react to volume-profile nodes + Coulling VPA; do not predict price

## Paths that matter

| Path | Role |
|------|------|
| `runs/paper_ledger/ledger.jsonl` | Paper opens/closes |
| `runs/live_adapt/STATE.json` | Streak / size mult after closes |
| `runs/live_adapt/LAST_TICKET.json` | Latest IB-ready flat ticket |

## Operator loop (today) — especially for the open

```bash
# 0) FULL MARKET OPEN SCANNER (use this at 9:25–9:40 ET)
.venv/bin/python tools/open_scan.py --account 10000 --top 12
# or: .venv/bin/python tools/trade_desk.py openscan --top 12
# → runs/live_adapt/LAST_OPEN_SCAN.json + WATCHLIST.txt
# → .venv/bin/python tools/trade_desk.py watch $(cat runs/live_adapt/WATCHLIST.txt) --every 30

# 1) Narrow VPA bias (optional)
.venv/bin/python tools/vpa_scan.py --symbols TSLA,IONQ,APLD,MU --json

# 2) Live ticket (equity WINNER + risk mode + options structure)
.venv/bin/python tools/live_plan.py --symbol IONQ --account 1000 --json

# 3) Paper open (desk UI Positions / Analyze also does this)
.venv/bin/python tools/paper_ledger.py open --symbol IONQ --side long \
  --shares 10 --entry 40 --stop 38 --model v39b_live_adapt --json

# 4) Paper close → feeds live_adapt automatically
.venv/bin/python tools/paper_ledger.py close --id <id> --exit 42 --json

# 5) Next plan is size-scaled
.venv/bin/python tools/live_adapt.py snapshot --json
.venv/bin/python tools/trade_desk.py IONQ --model auto --json   # sizing.live_adapt_mult
```

## UI

- **Scan** → `/scan` (VPA+VWAP)
- **Watch** → `/watch` (multi-symbol analyze board)
- **Live** → `/live` (risk ticket; model auto → WINNER)
- **Options** → `/options` (structure + mode)
- **Adapt** → `GET /api/live-adapt`

## Future IB bridge

Read `runs/live_adapt/LAST_TICKET.json`:

```json
{
  "ticket": {
    "symbol": "IONQ",
    "side": "BUY",
    "qty": 12,
    "order_type": "LMT",
    "limit": 41.2,
    "stop": 38.5,
    "tif": "DAY",
    "vehicle": "equity"
  },
  "adapt": { "size_mult": 1.05 }
}
```

Map to `ib_insync` / TWS API yourself. Keep human confirm on first versions.
