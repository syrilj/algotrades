"""Phase finalization: compare evolve board vs frozen WINNER / OPTIONS_WINNER."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
WINNER_PATH = ROOT / "models" / "poc_va_macdha" / "WINNER.json"
OPTS_WINNER_PATH = ROOT / "models" / "poc_va_macdha" / "OPTIONS_WINNER.json"
PHASES_PATH = ROOT / "models" / "_shared" / "EVOLVE_PHASES.md"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_winner() -> dict[str, Any]:
    if not WINNER_PATH.exists():
        return {}
    return json.loads(WINNER_PATH.read_text())


def load_opts_winner() -> dict[str, Any]:
    if not OPTS_WINNER_PATH.exists():
        return {}
    return json.loads(OPTS_WINNER_PATH.read_text())


def compare_to_winners(state: dict[str, Any]) -> dict[str, Any]:
    """Build promote decision vs frozen winners — never auto-overwrite WINNER."""
    ranking = state.get("ranking") or []
    track = str(state.get("track") or "")
    w = load_winner()
    ow = load_opts_winner()

    top = next((r for r in ranking if not r.get("error")), None)
    equity_winner = w.get("winner")
    opts_winner = ow.get("winner")

    decision = {
        "ts": _now(),
        "track": track,
        "top_evolve": top.get("id") if top else None,
        "top_utility": float(top.get("utility") or 0) if top else None,
        "top_claim": top.get("claim_level") if top else None,
        "frozen_equity_winner": equity_winner,
        "frozen_options_winner": opts_winner,
        "may_auto_promote": bool(top and top.get("may_auto_promote")),
        "action": "hold",
        "reasons": [],
    }

    if not top:
        decision["action"] = "no_data"
        decision["reasons"].append("empty ranking")
        return decision

    if track.startswith("options") or track == "options_synthetic":
        decision["action"] = "research_only"
        decision["reasons"].append("options_synthetic never auto-promotes")
        decision["compare_to"] = opts_winner
        if top.get("id") == opts_winner or top.get("id") == f"v35_soft_bag8":
            decision["reasons"].append("top matches OPTIONS_WINNER lineage")
        return decision

    # equity
    if not top.get("may_auto_promote"):
        decision["action"] = "hold"
        decision["reasons"].append(
            f"top claim_level={top.get('claim_level')} may_auto_promote=False"
        )
        decision["reasons"].append("keep frozen WINNER until CLAIM + multi-lock PASS")
        return decision

    if equity_winner and top.get("id") == equity_winner:
        decision["action"] = "confirm_current_winner"
        decision["reasons"].append(
            f"top CLAIM model `{equity_winner}` already is frozen WINNER — no change"
        )
        return decision

    # CLAIM eligible — still require beating frozen portfolio spirit on utility
    port = (w.get("portfolio") or {}) if w else {}
    if port:
        # rough frozen utility proxy
        fr = float(port.get("total_return") or 0)
        fsh = float(port.get("sharpe") or 0)
        fdd = abs(float(port.get("max_drawdown") or 0))
        frozen_u = fr + 0.35 * min(fsh, 3.0) - 0.55 * max(0.0, fdd - 0.15)
        decision["frozen_utility_proxy"] = frozen_u
        if float(top.get("utility") or 0) < frozen_u * 0.5:
            decision["action"] = "hold"
            decision["reasons"].append(
                f"evolve utility {top.get('utility'):.3f} << frozen proxy {frozen_u:.3f}"
            )
            return decision

    decision["action"] = "candidate_for_manual_promote"
    decision["reasons"].append("CLAIM + PASS_BAR — review multi-lock then update WINNER.json manually")
    return decision


def write_finalize_report(run_dir: Path, state: dict[str, Any]) -> Path:
    decision = compare_to_winners(state)
    path = run_dir / "FINALIZE.md"
    lines = [
        "# Evolve phase finalize",
        "",
        f"Generated: `{decision['ts']}`",
        f"Run: `{run_dir}`",
        f"Track: **{decision.get('track')}**",
        "",
        "## Decision",
        "",
        f"- **action:** `{decision['action']}`",
        f"- top evolve: `{decision.get('top_evolve')}` utility={decision.get('top_utility')} claim={decision.get('top_claim')}",
        f"- frozen equity WINNER: `{decision.get('frozen_equity_winner')}`",
        f"- frozen OPTIONS_WINNER: `{decision.get('frozen_options_winner')}`",
        "",
        "### Reasons",
        "",
    ]
    for r in decision.get("reasons") or []:
        lines.append(f"- {r}")
    lines += [
        "",
        "## Phase checklist",
        "",
        "| Phase | Status |",
        "|-------|--------|",
        "| 0 data contracts / dual bars / cache | shipped |",
        "| 1 rank farm | shipped |",
        "| 2 feedback loop + mutations | shipped |",
        "| 3 options research track | shipped |",
        "| 4 meta MLP secondary | shipped |",
        "| finalize vs WINNER | this report |",
        "",
        "Auto-overwrite of `WINNER.json` is **disabled**. Promote only after manual review.",
        "",
    ]
    path.write_text("\n".join(lines))
    (run_dir / "FINALIZE.json").write_text(json.dumps(decision, indent=2))
    return path


def write_phases_doc() -> Path:
    text = """# Evolution pipeline phases (final)

Status as of finalize module. CLI: `tools/evolve_pipeline.py`.

| Phase | Command | Output | Promote? |
|-------|---------|--------|----------|
| 0 Integrity | (always on) | claim levels, cache keys, PASS_BAR | — |
| 1 Rank farm | `rank --track equity\\|options` | `runs/evolve_*/LEADERBOARD.md` | Equity CLAIM only |
| 2 Feedback loop | `loop --gens N` | mutations + gen scores | Equity CLAIM only |
| 3 Options research | `rank --track options` | synthetic BS board | **Never** auto |
| 4 Meta MLP | `meta` | `META_RECIPE.json` | Secondary size/skip only |
| Finalize | written after rank/loop | `FINALIZE.md` | Manual WINNER update |

## Frozen defaults (do not silent-replace)

- Equity desk / WINNER: see `models/poc_va_macdha/WINNER.json` (`v23_devin_overlay`)
- Options research default: `models/poc_va_macdha/OPTIONS_WINNER.json` (`v35_softstruct_bag8`)

## Smoke vs full-window

Smoke ranks used `--quick` (late window ~1y, thin bag) → low ret / RESEARCH.  
Full ranks use 2024-08→2026-07 + winner bags for honest comparison.
"""
    PHASES_PATH.write_text(text)
    return PHASES_PATH
