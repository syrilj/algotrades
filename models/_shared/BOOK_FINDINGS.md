# Durable book findings (iteration loop)

Append-only log is `findings.jsonl`. This file is the human-readable index for book-derived edges.

## Working (reuse)
| ID | Finding | Use how |
|----|---------|---------|
| B1 | Coulling **no-demand** (up + thin vol) | Soft size-down or soft veto — not sole hard block on 1H |
| B2 | **Commitment** = confirm_up OR stopping_reclaim OR reflexive_up | Entry credibility gate |
| B3 | **Stopping volume reclaim** | Alternate long path after absorption |
| B4 | Quality↑ capacity↓ (v17b) | Overlay on winner; don't replace v15 |
| B5 | GEX: **vol_z ≥ 1/2** strongest OOS | Primary volume meta for `poc_va_gex` |
| B6 | Soros: don't chase **buying climax** | Size cut / stand aside, coarser TF |
| B7 | Options guide: high-vol climax ≈ regime | Risk overlay, not new side model |

## Failed (avoid)
| ID | Finding | Why |
|----|---------|-----|
| F1 | Full climax+topping+effort on 1H (`v17`) | Over-filter; Sharpe/return collapse vs v15 |
| F2 | Promote PF/DD-only win without beating winner Sharpe | Capacity destroyed |

## Next experiments
See `models/poc_va_macdha/RESEARCH_NEXT.md` (A soft no_demand / B 4H climax / C GEX vol_z wire).

## CLI
```bash
.venv/bin/python tools/findings.py working
.venv/bin/python tools/findings.py failed
.venv/bin/python tools/findings.py next
```
