# Model Leaderboard

Dedicated ranking surface for Trade Desk. CLI: `tools/trade_desk.py rank` · Registry: `tools/model_registry.py`.

Nav: **Analyze · Watch · Picks · Leaderboard · Models** · Route: `/leaderboard` (`/rank` redirects here).

---

## Data sources

| Source | Use |
|--------|-----|
| `rank_models(engines_only)` | Portfolio / overall table |
| `rank_models_for_symbol(sym, engines_only)` | Per-symbol hist ranks |
| `score_metrics(wr, sharpe, pf, max_dd)` | Composite `score` column |
| `list_engine_models()` / `has_engine` | Engines-only filter + Engine badge |
| `WINNER.json` | Winner badge (`winner` key) |
| `DEFAULT_MODEL` (`v15_meta_xgb`) | Default badge (may ≠ winner) |
| `TRAINING_LEADERBOARD.json` | Merged via `all_model_cards` / `load_leaderboard_cards` |
| Per-version `results.json` | Portfolio + per_symbol metrics |
| `MODEL.md` | Status / hypothesis for side panel |

### Row schema (API / CLI `--json`)

```
rank, model, score, win_rate, sharpe, profit_factor, max_drawdown,
total_return, trade_count, has_engine, source
+ code, specialist   # symbol mode only
```

CLI print columns (`_print_rank`): `# model score WR Sh PF DD ret`.

---

## Modes

1. **Portfolio overall** — `GET /api/leaderboard` → `rank`
2. **Per-symbol** — `?symbol=IONQ` → `rank --symbol IONQ`
3. **Engines only** — toggle → `--engines-only`

---

## Visual design

- Dense ranked table; medals for ranks 1–3 (gold/silver/bronze tokens in DESIGN_TOKENS)
- Sortable headers; default sort = `score` desc
- `ScoreBar` relative to column max
- Winner row: brand left rail + Winner badge
- Side panel / expand: MODEL.md one-liner, metrics, Open model, Analyze with this, Use auto
- Footer echo: CLI command equivalent

### Analyze bridge

`TopModelsStrip` on Analyze shows top 3 for symbol → `/leaderboard?symbol=TSLA`.

---

## Empty / loading

| State | Copy |
|-------|------|
| Loading | Skeleton rows |
| No portfolio metrics | “No model cards with portfolio metrics” |
| No symbol hist | “No hist for {SYMBOL}.US — try engines with per_symbol results” |

---

## Wireframe

See [`SCREENS.md`](./SCREENS.md) § Leaderboard. Components: [`component-inventory.md`](./component-inventory.md).
