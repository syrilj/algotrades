# v66_best_router

**The best model is the router that picks the best model.**

For each symbol it competes:

| Candidate | Prior |
|-----------|------:|
| Desk specialist (if mapped) | 0.78 |
| `v39d_confluence` | 0.74 |
| `v39b_live_adapt` | 0.68 |
| `v63_spy_prune` / `v50_high_win_rate` | ~0.66 |

Then blends with historical per-symbol scores and fresh symbol-ranker scores when available. **Specialists do not auto-win** — generics can beat them.

## Used by

- `model_registry.route_best_model(symbol)` — selection API
- `recommend_model(symbol)` / `equity_model_for_symbol` — analysis + auto
- This engine — multi-symbol backtests with per-bar routing decisions in `last_routes()`

```bash
.venv/bin/python - <<'PY'
import sys; sys.path.insert(0,'tools')
import model_registry as mr
for s in ['TSLA','CRWV','NFLX','NVDA']:
    r = mr.route_best_model(s)
    print(s, '->', r['model'], r['score'], r['track'])
    for c in (r.get('candidates') or [])[:4]:
        print('   ', c)
PY
```
