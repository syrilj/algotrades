# Dual-track + best-model router

You have **two tracks of candidates**. Analysis / live / `--model auto` do **not**
hard-lock to specialists — they run a **competitive router** that scores both.

```
route_best_model(symbol)
  candidates = specialist (if any) + v39d + v39b + other standards
  score each (prior + hist + ranker)
  → WINNER = best score  (specialist OR generic)
```

Engine: **`v66_best_router`** — “the best model is the router to the best model.”

Hard dual-track (always specialist if mapped) is **not** the default anymore.
Specialists start with a higher prior (0.78 vs ~0.74 for v39d) but can lose.

## Track A — specialized (top stocks you trade)

Per-name DNA tuned for that ticker’s character (crypto beta, semi, megacap, bounce, etc.).

| Symbol | Model | Family |
|--------|--------|--------|
| TSLA | v65_spec_tsla | megacap beta |
| MU | v65_spec_mu | semi / memory |
| IONQ (INFQ) | v65_spec_ionq | speculative 4H |
| MSTR | v65_spec_mstr | crypto beta |
| COIN | v65_spec_coin | crypto beta |
| SNDK | v65_spec_sndk | semi / memory |
| ASTS | v65_spec_asts | speculative 4H |
| META | v65_spec_meta | megacap quality |
| GOOG | v65_spec_goog | megacap quality |
| CRWV | v64_crwv_bounce | demand bounce |
| APLD | v65_spec_apld | AI infra beta |
| ARM | v65_spec_arm | semi spec 4H |
| NVDA | v65_spec_nvda | semi leader |
| AMD | v65_spec_amd | semi |
| SMCI | v65_spec_smci | AI infra beta |
| PLTR | v65_spec_pltr | software beta |
| HOOD | v65_spec_hood | fintech beta |
| AMZN | v65_spec_amzn | megacap quality |
| MSFT | v65_spec_msft | megacap quality |
| AAPL | v65_spec_aapl | megacap quality |

Source of truth: `DESK_ROUTING.json`  
DNA packs: `specialists/<SYM>/`  
Runnable engines: `v65_spec_<sym>/`

## Track B — standard (everything else)

Names you have **not** specialized yet use the normal bag champions:

1. Prefer `fallback_equity` from DESK_ROUTING → **`v39d_confluence`**
2. Else `fallback_equity_alt` → `v39b_live_adapt`
3. Else `WINNER.json` / overall rank

Examples: random midcaps, new tickers, names not in the map → **standard model**.

## Code paths

| Surface | Behavior |
|---------|----------|
| `recommend_model(symbol)` | specialist if mapped, else standard |
| `equity_model_for_symbol(symbol)` | same dual-track |
| `analysis_agent` | auto uses dual-track |
| `live_plan.plan_symbol` | auto uses dual-track |
| `trade_desk --model auto` | dual-track |
| `--model v39d_confluence` | force standard (override) |

## Adding a new specialist later

1. Create `specialists/FOO/config.json` + `signal_engine.py` (copy a peer DNA).
2. Create `v65_spec_foo/` runnable copy.
3. Add `FOO.US` under `DESK_ROUTING.json` → `by_symbol`.
4. Done — analysis auto-routes; all other symbols still use standard models.
