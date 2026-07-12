# v38_research_stack

**Parent:** `v37_feedback_meta`  
**Goal:** Fuse all *working* research into one equity engine without hard-filter failure modes.

## Research fused (secondary only)

| Source | What we take |
|--------|----------------|
| v23 / specialists | Primary SIDE, routing, XLP macro, ARM drop |
| v37 | Continuous soft meta size + half-Kelly + evolve feature mults |
| v36_genome_train | risk_pct scale, after_win/loss mults, struct 1.15/0.55 |
| v17b_book_vpa_light | Soft no_demand cut; commitment / stopping_reclaim boost |
| v32/v35 | Soft structure sizing (never hard block) |
| high-WR sleeve / multi-loop | Soft cut high-beta when QQQ RS weak |
| FAIL list | No hard EMA200/vol gates; no climax hard stacks; no side-predict ML |

## Promote if
Beats v37 on same 1H window on (Sharpe, return) without blowing DD past ~15–18%, PASS_BAR, n≥40.
