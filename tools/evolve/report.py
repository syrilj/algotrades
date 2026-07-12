"""Leaderboard + STATE writers."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state = dict(state)
    state["updated_at"] = _now()
    path.write_text(json.dumps(state, indent=2, default=str))


def write_leaderboard(path: Path, state: dict[str, Any]) -> None:
    lines = [
        "# Evolution pipeline leaderboard",
        "",
        f"Updated: `{state.get('updated_at', _now())}`",
        f"Track: **`{state.get('track')}`** · cash `${state.get('cash', 0):,.0f}`",
        f"Family: `{state.get('family', 'poc_va_macdha')}`",
        "",
        "Claim levels: `THIN` (n&lt;12) · `RESEARCH` (cannot ship) · `CLAIM` (PASS_BAR + equity only).",
        "Options synthetic never auto-promotes. GEX is live-only.",
        "",
        "## Ranking (utility = money + Sharpe − DD, × reliability(n))",
        "",
        "| # | Model | Mode | Claim | Track | Ret | Sharpe | DD | n | Utility | Cache |",
        "|---|-------|------|-------|-------|-----|--------|----|---|---------|-------|",
    ]
    ranking = state.get("ranking") or state.get("screen") or []
    for i, r in enumerate(ranking[:40], 1):
        if r.get("error"):
            lines.append(
                f"| {i} | `{r.get('id')}` | {r.get('mode')} | ERROR | — | FAIL | — | — | 0 | -99 | — |"
            )
            continue
        cache = "hit" if r.get("from_cache") or r.get("reused") else "miss"
        lines.append(
            f"| {i} | `{r.get('id')}` | {r.get('mode')} | {r.get('claim_level','?')} | "
            f"{r.get('data_track','?')} | {100*float(r.get('ret') or 0):.1f}% | "
            f"{float(r.get('sharpe') or 0):.2f} | {100*float(r.get('dd') or 0):.1f}% | "
            f"{int(r.get('n') or 0)} | {float(r.get('utility') or 0):.3f} | {cache} |"
        )

    claimable = [r for r in ranking if r.get("may_auto_promote")]
    lines += ["", "## Promote-eligible (equity CLAIM + PASS_BAR)", ""]
    if not claimable:
        lines.append("_None this run._")
    else:
        for r in claimable[:10]:
            lines.append(
                f"- `{r['id']}` utility={float(r.get('utility') or 0):.3f} "
                f"ret={100*float(r.get('ret') or 0):.1f}% n={r.get('n')}"
            )

    if state.get("multi_lock"):
        lines += ["", "## Multi-lock OOS", ""]
        for mid, v in state["multi_lock"].items():
            lines.append(f"- `{mid}`: **{v.get('status')}** flags={v.get('flags')}")

    if state.get("generations"):
        lines += ["", "## Feedback generations", ""]
        for g in state["generations"]:
            lines.append(
                f"- Gen {g.get('gen')}: best=`{g.get('best_id')}` "
                f"utility={g.get('best_utility')} mutations={g.get('n_mutations', 0)}"
            )

    if state.get("meta"):
        lines += ["", "## Meta MLP (phase 4)", ""]
        m = state["meta"]
        if m.get("ok"):
            lines.append(
                f"- mean_accuracy={m.get('mlp', {}).get('mean_accuracy')} "
                f"features={len(m.get('selected_features') or [])}"
            )
        else:
            lines.append(f"- skipped/failed: {m.get('error')}")

    lines += [
        "",
        "## Honesty notes",
        "",
        f"- pricing / track labels on every row",
        f"- content cache: `runs/evolve_cache/`",
        f"- state: `{state.get('state_path', 'STATE.json')}`",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))
