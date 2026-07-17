# Feature: Robust Model Ranking and Failure-Guided Evolution

## Summary

The evolution system now selects models using a robustness-aware ranking and
records structured explanations for weak or rejected candidates. The same
feedback is reused to order future mutations, allowing the search process to
learn which changes tend to address recurring failure modes.

## Requirements

- Compare candidates only when dates, symbols, source, and interval match.
- Favor stable out-of-sample performance over a single high-return run.
- Penalize incomplete samples, unstable windows, OOS reversals, and lock fails.
- Store machine-readable failure evidence and human-readable next actions.
- Learn mutation effectiveness from score delta versus its parent control.
- Preserve an exploration term so early results do not permanently narrow search.
- Keep the existing equity/options promotion and audit constraints intact.

## Architecture

`tools/evolve/model_feedback.py` is the shared policy layer. `rank_model_runs`
aggregates comparable runs and emits the robust score, confidence, score
components, and a failure profile. `diagnose_model` owns the failure taxonomy.
The JSON memory functions atomically persist bounded generation history, model
failure counts, and online mutation statistics.

Both `tools/evolve/pipeline.py` and the fold-based direction campaign call this
layer. The standard loop now evaluates parent and mutation candidates on the
same full window and bag. Mutation creation is round-robin across elite parents.
Before each generation, `prioritize_mutation_menu` scores mutation specs from
failure-target matches, learned mean score delta, win rate, and exploration.

## Data Model

Each ranked row adds `rank_score`, `rank_confidence`, `rank_components`, and
`failure_profile`. The memory file has three bounded collections: `models`
stores attempts and cumulative failure counts; `mutations` stores attempts,
wins, mean delta, and latest delta; `generations` stores the last 100 summaries.
The schema is versioned and corrupt or missing files degrade to empty memory.

## Error Handling

Backtest errors and zero-trade results remain rankable as failed rows with a
score of `-99`. Memory writes use a temporary file followed by atomic replace.
Memory read errors do not stop research; the system starts from an empty schema.
Lock failures disable promotion even when raw return is attractive.

## Testing Strategy

Focused tests cover stable-versus-spiky rankings, failure evidence and actions,
memory learning and mutation prioritization, schema stability, and fair mutation
budget distribution across elite parents. Existing evolution, audit, promotion,
and market-runtime tests remain the regression suite.

## Implementation Tasks

- [x] Add robustness-aware ranking and failure taxonomy.
- [x] Add persistent model and mutation memory.
- [x] Make parent/mutation evaluations contract-identical.
- [x] Guide mutation ordering from failures and historical outcomes.
- [x] Distribute mutation budget across elite parents.
- [x] Add leaderboard failure reporting and feedback CLI.
- [x] Add focused tests and usage documentation.
