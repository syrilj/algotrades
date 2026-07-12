#!/usr/bin/env python3
"""Dynamic multi-universe model ranking (stocks + options + indices + sectors).

Honest process:
  1) Discover every model with a signal_engine.py
  2) SCREEN all models on a mixed multi-sector bag (one window)
  3) Take top-K by *gain* (total return / $ P&L), not win-rate alone
  4) DEEP-TEST those on sectors + indices + options/equity
  5) Publish multiple leaderboards:
       - greatest $ gain (from --cash, default 10_000)
       - total return %
       - risk (lowest |max DD|)
       - risk-adjusted (calmar-ish = ret / |dd|, sharpe)

Usage:
  .venv/bin/python tools/dynamic_model_rank.py --quick --cash 10000
  .venv/bin/python tools/dynamic_model_rank.py --top 8 --cash 10000
  .venv/bin/python tools/dynamic_model_rank.py --models v22_opts_live,v32_soft_react_opts --cash 10000
  .venv/bin/python tools/dynamic_model_rank.py --full
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from backtest.runner import main as bt_main

ROOT = Path(__file__).resolve().parents[1]
MODELS_ROOT = ROOT / "models" / "poc_va_macdha"
OUT = ROOT / "runs" / "poc_va_dynamic_rank"
STATE = OUT / "DYNAMIC_RANKING.json"
REPORT = OUT / "RANKING.md"

# Overridden in main() via --cash
CASH = 10_000

# --- Universes (sector diversification) ---
SECTORS: dict[str, list[str]] = {
    "semis": ["NVDA.US", "AVGO.US", "AMD.US", "MU.US", "ARM.US"],
    "mega_tech": ["AAPL.US", "MSFT.US", "GOOGL.US", "META.US", "AMZN.US"],
    "high_beta": ["TSLA.US", "MSTR.US", "IONQ.US", "HOOD.US", "COIN.US"],
    "finance": ["JPM.US", "GS.US", "BAC.US", "V.US"],
    "energy": ["XOM.US", "CVX.US", "OXY.US"],
    "health": ["UNH.US", "LLY.US", "JNJ.US"],
    "staples": ["PG.US", "KO.US", "WMT.US"],
    "indices": ["SPY.US", "QQQ.US", "IWM.US", "DIA.US"],
}

# Mixed screen bag: one name per major book + indices
SCREEN_BAG = [
    "NVDA.US",
    "AVGO.US",
    "TSLA.US",
    "JPM.US",
    "XOM.US",
    "UNH.US",
    "HOOD.US",
    "SPY.US",
    "QQQ.US",
]

# Options-friendly liquid bag (premium capacity)
OPTS_BAG = ["IONQ.US", "AVGO.US", "HOOD.US", "MU.US", "TSLA.US", "NVDA.US"]

WINDOWS = {
    "screen": ("2024-08-01", "2026-07-11"),
    "deep_full": ("2024-08-01", "2026-07-11"),
    "deep_late": ("2025-07-01", "2026-07-11"),  # harder recent OOS-ish
}

# Models that only make sense as options (or are known options DNA)
OPTS_NAME_HINTS = (
    "opts",
    "options",
    "flip",
    "vpa_vwap",
    "momo_detector",
    "coldstart",
    "feedback_pro",
    "soft_react",
    "selective_nodes",
)

# Skip non-runnable / specialist-only / incomplete
SKIP_DIRS = {
    "specialists",
    "v23_moonshot_1y",  # custom harness, not SignalEngine runner
    "v35_mixed_dte",  # no engine
    "v22_opts_hunt",
    "v28_feedback",
    "v3_sqz",
    "v4_voldiv",
    "v5_combo",
    "v6_softconf",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def score_metrics(m: dict[str, Any]) -> float:
    """Balanced composite (legacy). Small n gets haircut. WR is secondary to return."""
    if m.get("error") or m.get("n", 0) == 0:
        return -1.0
    ret = float(m.get("ret", 0.0))
    wr = float(m.get("wr", 0.0))
    sh = float(m.get("sharpe", 0.0))
    dd = abs(float(m.get("dd", 0.0)))
    n = int(m.get("n", 0))
    n_pen = 0.0 if n >= 12 else (0.12 if n >= 6 else 0.30)
    # Gain-first: return dominates; WR is a small tie-break only
    return 1.15 * ret + 0.05 * wr + 0.10 * min(sh, 3.0) / 3.0 - 0.40 * dd - n_pen


def score_gain(m: dict[str, Any]) -> float:
    """Pure growth: total return (and $ PnL)."""
    if m.get("error") or m.get("n", 0) == 0:
        return -9.0
    return float(m.get("ret", 0.0))


def score_risk(m: dict[str, Any]) -> float:
    """Safer = less |DD|; tiny bonus for positive return so all-flat doesn't win."""
    if m.get("error") or m.get("n", 0) == 0:
        return -9.0
    dd = abs(float(m.get("dd", 0.0)))
    ret = float(m.get("ret", 0.0))
    return -dd + 0.05 * max(ret, 0.0)


def score_risk_adj(m: dict[str, Any]) -> float:
    """Calmar-ish: ret / |dd|, plus light sharpe. Penalize thin n."""
    if m.get("error") or m.get("n", 0) == 0:
        return -9.0
    ret = float(m.get("ret", 0.0))
    dd = max(abs(float(m.get("dd", 0.0))), 0.02)
    sh = float(m.get("sharpe", 0.0))
    n = int(m.get("n", 0))
    n_pen = 0.0 if n >= 10 else 0.25
    return (ret / dd) + 0.15 * min(sh, 3.0) - n_pen


def enrich_money(m: dict[str, Any], cash: float) -> dict[str, Any]:
    """Attach $ PnL fields for a given starting cash."""
    out = dict(m)
    if m.get("error"):
        out["pnl"] = None
        out["final_at_cash"] = None
        return out
    ret = float(m.get("ret", 0.0))
    # Prefer actual final if same cash was used; else scale by return
    fin = m.get("final")
    if fin is not None and m.get("cash") == cash:
        out["final_at_cash"] = float(fin)
        out["pnl"] = float(fin) - cash
    else:
        out["final_at_cash"] = cash * (1.0 + ret)
        out["pnl"] = cash * ret
    out["cash"] = cash
    return out


def discover_models(only: list[str] | None = None) -> list[dict[str, Any]]:
    found = []
    for d in sorted(MODELS_ROOT.iterdir()):
        if not d.is_dir() or d.name.startswith("_") or d.name in SKIP_DIRS:
            continue
        if only and d.name not in only:
            continue
        eng = d / "signal_engine.py"
        if not eng.exists():
            # robust layout: code/signal_engine.py
            eng2 = d / "code" / "signal_engine.py"
            if not eng2.exists():
                continue
            eng = eng2
            src_dir = d / "code"
        else:
            src_dir = d

        cfg_path = d / "config.json"
        cfg: dict[str, Any] = {}
        if cfg_path.exists():
            try:
                cfg = json.loads(cfg_path.read_text())
            except Exception:
                cfg = {}

        hunt = src_dir / "hunt_config.json"
        if not hunt.exists():
            hunt = d / "hunt_config.json"
        has_hunt = hunt.exists()
        engine_pref = str(cfg.get("engine") or "").lower()
        name = d.name.lower()
        opts_hint = any(h in name for h in OPTS_NAME_HINTS) or has_hunt or engine_pref == "options"
        equity_hint = engine_pref in ("daily", "") or not opts_hint
        # Prefer both when ambiguous (try both in deep)
        if has_hunt and engine_pref == "options":
            modes = ["options"]
        elif opts_hint and not equity_hint:
            modes = ["options"]
        elif equity_hint and not opts_hint:
            modes = ["daily"]
        else:
            modes = ["options", "daily"] if opts_hint else ["daily"]

        interval = str(cfg.get("interval") or "1D")
        # For ranking speed, force 1D unless --keep-interval
        found.append(
            {
                "id": d.name,
                "src_dir": src_dir,
                "model_dir": d,
                "modes": modes,
                "interval": interval,
                "has_hunt": has_hunt,
                "hunt_path": hunt if has_hunt else None,
            }
        )
    return found


def _copy_model_code(model: dict[str, Any], run_code: Path) -> None:
    run_code.mkdir(parents=True, exist_ok=True)
    src: Path = model["src_dir"]
    # core
    for name in (
        "signal_engine.py",
        "_base_engine.py",  # train-loop genome wrapper dependency
        "GENOME.json",
        "hunt_config.json",
        "meta_config.json",
        "meta_xgb_final.json",
        "vpa.py",
        "vwap_peg.py",
        "vwap_dna.json",
        "ROUTING.json",
        "RISK_POLICY.json",
    ):
        p = src / name
        if not p.exists() and model["model_dir"] != src:
            p = model["model_dir"] / name
        if p.exists():
            shutil.copy2(p, run_code / name)


def run_one(
    model: dict[str, Any],
    *,
    mode: str,
    codes: list[str],
    start: str,
    end: str,
    tag: str,
    force_1d: bool = True,
    reuse: bool = True,
    cash: float | None = None,
) -> dict[str, Any]:
    """Run one backtest; return metrics dict with $ PnL at `cash`."""
    mid = model["id"]
    cash = float(cash if cash is not None else CASH)
    cash_tag = f"c{int(cash)}" if cash >= 1000 else f"c{cash:g}"
    run_dir = OUT / "runs" / mid / f"{tag}__{mode}__{cash_tag}"
    metrics_path = run_dir / "artifacts" / "metrics.csv"

    def _pack(row_like: dict, reused: bool) -> dict[str, Any]:
        out = {
            "id": mid,
            "mode": mode,
            "tag": tag,
            "codes": codes,
            "start": start,
            "end": end,
            "cash": cash,
            "ret": float(row_like["total_return"]) if "total_return" in row_like else float(row_like["ret"]),
            "dd": float(row_like.get("max_drawdown", row_like.get("dd", 0))),
            "sharpe": float(row_like.get("sharpe", 0)),
            "n": int(float(row_like.get("trade_count", row_like.get("n", 0)))),
            "wr": float(row_like.get("win_rate", row_like.get("wr", 0))),
            "final": float(row_like.get("final_value", row_like.get("final", 0))),
            "reused": reused,
            "path": str(run_dir.relative_to(ROOT)),
        }
        out = enrich_money(out, cash)
        out["score"] = score_metrics(out)
        out["score_gain"] = score_gain(out)
        out["score_risk"] = score_risk(out)
        out["score_risk_adj"] = score_risk_adj(out)
        return out

    if reuse and metrics_path.exists():
        try:
            row = next(csv.DictReader(open(metrics_path)))
            out = _pack(row, True)
            return out
        except Exception:
            pass

    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_code = run_dir / "code"
    _copy_model_code(model, run_code)

    interval = "1D" if force_1d else model.get("interval", "1D")
    if mode == "options":
        interval = "1D"

    # Scale max contracts roughly with cash (capacity honesty at $10k)
    max_contracts = max(1, int(500 * (cash / 1_000_000)))
    if cash <= 25_000:
        max_contracts = max(1, min(max_contracts, 20))

    # Honor model config.json commission (evolve mutations / stress arms)
    commission = 0.001
    model_cfg_path = Path(model["model_dir"]) / "config.json"
    if model_cfg_path.exists():
        try:
            mc = json.loads(model_cfg_path.read_text())
            if mc.get("commission") is not None:
                commission = float(mc["commission"])
        except Exception:
            pass

    cfg = {
        "source": "yfinance",
        "codes": codes,
        "start_date": start,
        "end_date": end,
        "initial_cash": cash,
        "commission": commission,
        "engine": mode,
        "interval": interval,
        "options_config": {
            "risk_free_rate": 0.05,
            "contract_multiplier": 100,
            "exercise_style": "american",
        },
        "strategy": {
            "model_version": mid,
            "rank_tag": tag,
            "mode": mode,
            "cash": cash,
        },
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "config.json").write_text(json.dumps(cfg, indent=2))

    # Patch / write hunt_config with matching cash + contract cap
    hunt_path = run_code / "hunt_config.json"
    if mode == "options":
        if hunt_path.exists():
            try:
                hc = json.loads(hunt_path.read_text())
            except Exception:
                hc = {}
        else:
            hc = {
                "risk_pct": 0.10,
                "dte_days": 21,
                "otm_pct": 0.0,
                "halt_dd": 0.30,
                "flatten_dd": 0.45,
            }
        hc["initial_cash"] = cash
        hc["contract_multiplier"] = int(hc.get("contract_multiplier") or 100)
        hc["max_contracts"] = min(int(hc.get("max_contracts") or 500), max_contracts)
        # small accounts: allow more aggressive risk fraction or they get 0 lots
        if cash <= 25_000 and float(hc.get("risk_pct") or 0.1) < 0.15:
            hc["risk_pct"] = max(float(hc.get("risk_pct") or 0.1), 0.20)
        hunt_path.write_text(json.dumps(hc, indent=2))

    print(
        f"  RUN {mid:28} {mode:7} {tag:16} cash=${cash:,.0f} {start}→{end} n={len(codes)}",
        flush=True,
    )
    try:
        try:
            bt_main(run_dir.resolve())
        except SystemExit as se:  # runner may sys.exit on engine AST errors
            raise RuntimeError(f"backtest SystemExit: {se}") from se
        row = next(csv.DictReader(open(run_dir / "artifacts" / "metrics.csv")))
        art = run_dir / "artifacts"
        for p in art.glob("ohlcv_*.csv"):
            p.unlink(missing_ok=True)
        out = _pack(row, False)
        print(
            f"    → PnL=${out['pnl']:+,.0f} ({out['ret']*100:6.1f}%) wr={out['wr']*100:4.0f}% "
            f"dd={out['dd']*100:5.1f}% n={out['n']:3d} | gain={out['score_gain']:.3f} "
            f"riskAdj={out['score_risk_adj']:.3f}",
            flush=True,
        )
        return out
    except Exception as e:  # noqa: BLE001
        err = str(e).split("\n")[0][:200]
        print(f"    FAIL {err}", flush=True)
        out = {
            "id": mid,
            "mode": mode,
            "tag": tag,
            "codes": codes,
            "start": start,
            "end": end,
            "cash": cash,
            "error": err,
            "ret": -9.0,
            "dd": -1.0,
            "sharpe": 0.0,
            "n": 0,
            "wr": 0.0,
            "final": 0.0,
            "pnl": None,
            "final_at_cash": None,
            "score": -1.0,
            "score_gain": -9.0,
            "score_risk": -9.0,
            "score_risk_adj": -9.0,
            "path": str(run_dir.relative_to(ROOT)),
        }
        return out


def pick_mode_for_screen(model: dict[str, Any]) -> str:
    modes = model["modes"]
    if "options" in modes and model["has_hunt"]:
        return "options"
    if "options" in modes and any(h in model["id"].lower() for h in OPTS_NAME_HINTS):
        return "options"
    return "daily" if "daily" in modes else modes[0]


def phase_screen(models: list[dict], start: str, end: str, force_1d: bool) -> list[dict]:
    print("\n======== PHASE 1: SCREEN (mixed multi-sector bag) ========", flush=True)
    rows = []
    for m in models:
        mode = pick_mode_for_screen(m)
        r = run_one(
            m,
            mode=mode,
            codes=SCREEN_BAG,
            start=start,
            end=end,
            tag="screen_mixed",
            force_1d=force_1d,
        )
        rows.append(r)
    ok = [r for r in rows if not r.get("error")]
    ok.sort(key=lambda x: x["score"], reverse=True)
    rows_fail = [r for r in rows if r.get("error")]
    return ok + rows_fail


def phase_deep(
    models_by_id: dict[str, dict],
    top_ids: list[str],
    *,
    force_1d: bool,
    sectors: list[str],
    do_late: bool,
) -> dict[str, list[dict]]:
    print("\n======== PHASE 2: DEEP TEST top models ========", flush=True)
    deep: dict[str, list[dict]] = {tid: [] for tid in top_ids}
    start_f, end_f = WINDOWS["deep_full"]
    start_l, end_l = WINDOWS["deep_late"]

    for tid in top_ids:
        m = models_by_id[tid]
        print(f"\n---- deep {tid} modes={m['modes']} ----", flush=True)
        modes = m["modes"]

        # Sector stock universes (daily preferred; options if only options)
        for sec in sectors:
            codes = SECTORS[sec]
            if "daily" in modes:
                deep[tid].append(
                    run_one(
                        m,
                        mode="daily",
                        codes=codes,
                        start=start_f,
                        end=end_f,
                        tag=f"sec_{sec}",
                        force_1d=force_1d,
                    )
                )
            elif "options" in modes:
                deep[tid].append(
                    run_one(
                        m,
                        mode="options",
                        codes=codes,
                        start=start_f,
                        end=end_f,
                        tag=f"sec_{sec}_opts",
                        force_1d=force_1d,
                    )
                )

        # Indices
        if "daily" in modes:
            deep[tid].append(
                run_one(
                    m,
                    mode="daily",
                    codes=SECTORS["indices"],
                    start=start_f,
                    end=end_f,
                    tag="indices",
                    force_1d=force_1d,
                )
            )
        if "options" in modes:
            deep[tid].append(
                run_one(
                    m,
                    mode="options",
                    codes=SECTORS["indices"],
                    start=start_f,
                    end=end_f,
                    tag="indices_opts",
                    force_1d=force_1d,
                )
            )

        # Options growth bag
        if "options" in modes:
            deep[tid].append(
                run_one(
                    m,
                    mode="options",
                    codes=OPTS_BAG,
                    start=start_f,
                    end=end_f,
                    tag="opts_growth",
                    force_1d=force_1d,
                )
            )
            if do_late:
                deep[tid].append(
                    run_one(
                        m,
                        mode="options",
                        codes=OPTS_BAG,
                        start=start_l,
                        end=end_l,
                        tag="opts_growth_late",
                        force_1d=force_1d,
                    )
                )

        # Equity mixed bag (if daily capable)
        if "daily" in modes:
            deep[tid].append(
                run_one(
                    m,
                    mode="daily",
                    codes=SCREEN_BAG,
                    start=start_f,
                    end=end_f,
                    tag="equity_mixed",
                    force_1d=force_1d,
                )
            )
            if do_late:
                deep[tid].append(
                    run_one(
                        m,
                        mode="daily",
                        codes=SCREEN_BAG,
                        start=start_l,
                        end=end_l,
                        tag="equity_mixed_late",
                        force_1d=force_1d,
                    )
                )

    return deep


def aggregate_deep(deep: dict[str, list[dict]], screen_map: dict[str, dict]) -> list[dict]:
    """Build dynamic final ranking from deep + screen."""
    rows = []
    for mid, tests in deep.items():
        ok = [t for t in tests if not t.get("error") and t.get("n", 0) > 0]
        fails = [t for t in tests if t.get("error")]
        if not ok:
            rows.append(
                {
                    "id": mid,
                    "rank_score": -1.0,
                    "mean_ret": None,
                    "mean_wr": None,
                    "mean_dd": None,
                    "mean_sharpe": None,
                    "n_tests_ok": 0,
                    "n_tests_fail": len(fails),
                    "best_test": None,
                    "worst_test": None,
                    "screen_score": screen_map.get(mid, {}).get("score"),
                    "by_family": {},
                }
            )
            continue

        # Family scores
        families = {
            "sector": [t for t in ok if t["tag"].startswith("sec_")],
            "indices": [t for t in ok if "indices" in t["tag"]],
            "options": [t for t in ok if t["mode"] == "options"],
            "equity": [t for t in ok if t["mode"] == "daily"],
            "late": [t for t in ok if t["tag"].endswith("_late")],
        }
        fam_means = {}
        for k, lst in families.items():
            if lst:
                fam_means[k] = {
                    "mean_score": mean(t["score"] for t in lst),
                    "mean_ret": mean(t["ret"] for t in lst),
                    "n": len(lst),
                }

        # Dynamic rank: weighted families
        w = {
            "sector": 0.30,
            "indices": 0.15,
            "options": 0.25,
            "equity": 0.20,
            "late": 0.10,
        }
        num = 0.0
        den = 0.0
        for k, wt in w.items():
            if k in fam_means:
                num += wt * fam_means[k]["mean_score"]
                den += wt
        # blend screen lightly
        sc = screen_map.get(mid, {}).get("score")
        if sc is not None and sc > -0.5:
            num += 0.10 * sc
            den += 0.10
        rank_score = num / den if den > 0 else mean(t["score"] for t in ok)

        best = max(ok, key=lambda t: t["score"])
        worst = min(ok, key=lambda t: t["score"])
        rows.append(
            {
                "id": mid,
                "rank_score": rank_score,
                "mean_ret": mean(t["ret"] for t in ok),
                "mean_wr": mean(t["wr"] for t in ok),
                "mean_dd": mean(t["dd"] for t in ok),
                "mean_sharpe": mean(t["sharpe"] for t in ok),
                "mean_n": mean(t["n"] for t in ok),
                "n_tests_ok": len(ok),
                "n_tests_fail": len(fails),
                "best_test": {
                    "tag": best["tag"],
                    "mode": best["mode"],
                    "ret": best["ret"],
                    "score": best["score"],
                },
                "worst_test": {
                    "tag": worst["tag"],
                    "mode": worst["mode"],
                    "ret": worst["ret"],
                    "score": worst["score"],
                },
                "screen_score": sc,
                "by_family": fam_means,
            }
        )
    rows.sort(key=lambda r: r["rank_score"], reverse=True)
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def _leaderboard_table(rows: list[dict], cash: float, key: str, title: str) -> list[str]:
    lines = [
        f"## {title}",
        "",
        f"Starting cash: **${cash:,.0f}** · sort key: `{key}`",
        "",
        "| Rank | Model | Mode | $ PnL | Final | Ret% | WR% | MaxDD% | n | Sharpe | RiskAdj |",
        "|------|-------|------|-------|-------|------|-----|--------|---|--------|---------|",
    ]
    ok = [r for r in rows if not r.get("error")]
    if key == "gain":
        ok.sort(key=lambda r: float(r.get("pnl") or r.get("ret", -9) * cash), reverse=True)
    elif key == "risk":
        ok.sort(key=lambda r: score_risk(r), reverse=True)
    elif key == "risk_adj":
        ok.sort(key=lambda r: score_risk_adj(r), reverse=True)
    else:
        ok.sort(key=lambda r: float(r.get("ret") or -9), reverse=True)

    for i, r in enumerate(ok, 1):
        pnl = r.get("pnl")
        fin = r.get("final_at_cash") or r.get("final")
        lines.append(
            f"| {i} | `{r['id']}` | {r.get('mode')} | "
            f"{('+' if pnl is not None and pnl>=0 else '')}{(f'${pnl:,.0f}' if pnl is not None else '—')} | "
            f"{(f'${fin:,.0f}' if fin is not None else '—')} | "
            f"{r.get('ret',0)*100:.1f}% | {r.get('wr',0)*100:.0f}% | {r.get('dd',0)*100:.1f}% | "
            f"{r.get('n',0)} | {r.get('sharpe',0):.2f} | {score_risk_adj(r):.2f} |"
        )
    fails = [r for r in rows if r.get("error")]
    if fails:
        lines += ["", f"_Failed / no trades: {', '.join('`'+r['id']+'`' for r in fails)}_", ""]
    else:
        lines.append("")
    return lines


def write_report(state: dict) -> None:
    cash = float(state.get("cash") or CASH)
    lines = [
        "# Dynamic Model Ranking — Gain + Risk",
        "",
        f"Generated: `{state['updated_at']}`",
        "",
        f"Starting account: **${cash:,.0f}** on multi-sector screen bag.",
        "Win rate is shown but **ranking prioritizes $ PnL / total return**, then risk boards.",
        "",
    ]
    screen = state.get("screen") or []
    lines += _leaderboard_table(screen, cash, "gain", "1) Greatest $ gain (screen)")
    lines += _leaderboard_table(screen, cash, "ret", "2) Highest return % (screen)")
    lines += _leaderboard_table(screen, cash, "risk", "3) Lowest risk / drawdown (screen)")
    lines += _leaderboard_table(screen, cash, "risk_adj", "4) Best risk-adjusted (ret÷|DD|) (screen)")

    if state.get("final_ranking"):
        lines += [
            "## Final deep-test dynamic rank",
            "",
            "| Rank | Model | Rank score | Mean ret | Mean $ PnL* | Mean WR | Mean DD | Tests |",
            "|------|-------|------------|----------|-------------|---------|---------|-------|",
        ]
        for r in state["final_ranking"]:
            mr = r.get("mean_ret")
            pnl = (cash * mr) if mr is not None else None
            lines.append(
                f"| {r.get('rank')} | `{r['id']}` | {r['rank_score']:.3f} | "
                f"{(mr*100 if mr is not None else float('nan')):.1f}% | "
                f"{(f'${pnl:+,.0f}' if pnl is not None else '—')} | "
                f"{(r.get('mean_wr') or 0)*100:.0f}% | "
                f"{(r.get('mean_dd') or 0)*100:.1f}% | "
                f"{r.get('n_tests_ok')}/{r.get('n_tests_ok',0)+r.get('n_tests_fail',0)} |"
            )
        lines += ["", "_*Mean $ PnL ≈ start_cash × mean return across deep tests (not path-compounded)._", ""]

    lines += [
        "## Universes",
        "",
        f"- Cash: `${cash:,.0f}`",
        f"- Screen bag: `{', '.join(SCREEN_BAG)}`",
        f"- Options bag: `{', '.join(OPTS_BAG)}`",
        f"- Sectors: `{', '.join(SECTORS.keys())}`",
        "",
        f"Artifacts: `{STATE.relative_to(ROOT)}`",
        "",
    ]
    REPORT.write_text("\n".join(lines))


def main() -> int:
    global CASH
    ap = argparse.ArgumentParser(description="Dynamic multi-universe model ranking")
    ap.add_argument("--quick", action="store_true", help="Fewer sectors, top 5, skip late window")
    ap.add_argument("--full", action="store_true", help="All models, all sectors, late window")
    ap.add_argument("--top", type=int, default=0, help="How many screen survivors to deep-test")
    ap.add_argument("--models", type=str, default="", help="Comma list of model ids only")
    ap.add_argument("--keep-interval", action="store_true", help="Keep model 1H interval (slower)")
    ap.add_argument("--no-reuse", action="store_true", help="Re-run even if metrics exist")
    ap.add_argument("--screen-only", action="store_true", help="Only phase 1")
    ap.add_argument(
        "--cash",
        type=float,
        default=10_000,
        help="Starting account equity for $ PnL ranking (default 10000)",
    )
    args = ap.parse_args()
    CASH = float(args.cash)

    only = [x.strip() for x in args.models.split(",") if x.strip()] or None
    models = discover_models(only)
    if not models:
        print("No models found")
        return 1

    # Default contenders if not full and no --models: curated high-signal set
    if not args.full and not only:
        priority = [
            "v22_opts_live",
            "v29_coldstart_opts",
            "v32_soft_react_opts",
            "v28_feedback_opts",
            "v26_opts_evolve",
            "v23_devin_overlay",
            "v20b_macro_light",
            "v20_profit_risk",
            "v15_meta_xgb",
            "v31_vpa_vwap",
            "v30_flip_any",
            "v31_selective_nodes_opts",
            "v30_feedback_pro",
            "v25_regime_grow",
            "v14_risk_kelly",
            "v21_mstr_tsla",
            "v8_4h_daily",
            "v13_specialists",
        ]
        by = {m["id"]: m for m in models}
        models = [by[i] for i in priority if i in by]
        print(f"Curated model set ({len(models)}): {[m['id'] for m in models]}", flush=True)
    else:
        print(f"Discovered {len(models)} models", flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    force_1d = not args.keep_interval
    global_reuse = not args.no_reuse
    print(f"Starting cash = ${CASH:,.0f}  (gain + risk leaderboards)", flush=True)

    def run_one_wrap(*a, **k):
        k.setdefault("reuse", global_reuse)
        k.setdefault("force_1d", force_1d)
        k.setdefault("cash", CASH)
        return run_one(*a, **k)

    start_s, end_s = WINDOWS["screen"]

    # Phase 1
    screen_rows = []
    for m in models:
        mode = pick_mode_for_screen(m)
        screen_rows.append(
            run_one_wrap(
                m,
                mode=mode,
                codes=SCREEN_BAG,
                start=start_s,
                end=end_s,
                tag="screen_mixed",
            )
        )
    screen_ok = [r for r in screen_rows if not r.get("error") and r.get("n", 0) > 0]
    # Promote by $ gain first (not WR)
    screen_ok.sort(key=lambda x: float(x.get("pnl") if x.get("pnl") is not None else x.get("ret", -9) * CASH), reverse=True)
    screen_fail = [r for r in screen_rows if r.get("error") or r.get("n", 0) == 0]
    screen_sorted = screen_ok + screen_fail

    print(f"\n======== SCREEN RANK @ ${CASH:,.0f} (by $ PnL) ========", flush=True)
    for i, r in enumerate(screen_sorted[:15], 1):
        if r.get("error") or r.get("n", 0) == 0:
            print(f"  {i:2d}. {r['id']:28} FAIL/empty {r.get('error','n=0')[:50]}")
        else:
            print(
                f"  {i:2d}. {r['id']:28} PnL=${r['pnl']:+8,.0f}  ret={r['ret']*100:6.1f}% "
                f"dd={r['dd']*100:5.1f}% wr={r['wr']*100:4.0f}% n={r['n']:3d} "
                f"riskAdj={r['score_risk_adj']:.2f} mode={r['mode']}"
            )

    # Risk boards in console
    print(f"\n======== RISK-ADJUSTED (ret÷|DD|) @ ${CASH:,.0f} ========", flush=True)
    by_ra = sorted(screen_ok, key=score_risk_adj, reverse=True)
    for i, r in enumerate(by_ra[:8], 1):
        print(
            f"  {i:2d}. {r['id']:28} riskAdj={score_risk_adj(r):.2f} "
            f"ret={r['ret']*100:6.1f}% dd={r['dd']*100:5.1f}% sharpe={r['sharpe']:.2f}"
        )
    print(f"\n======== LOWEST DRAWDOWN @ ${CASH:,.0f} ========", flush=True)
    by_dd = sorted(screen_ok, key=score_risk, reverse=True)
    for i, r in enumerate(by_dd[:8], 1):
        print(
            f"  {i:2d}. {r['id']:28} dd={r['dd']*100:5.1f}% ret={r['ret']*100:6.1f}% "
            f"PnL=${r['pnl']:+,.0f}"
        )

    top_n = args.top or (5 if args.quick else 8)
    top_ids = [r["id"] for r in screen_ok[:top_n]]
    print(f"\nDeep-testing top {len(top_ids)} by $ gain: {top_ids}", flush=True)

    state: dict[str, Any] = {
        "updated_at": _now(),
        "cash": CASH,
        "screen_bag": SCREEN_BAG,
        "opts_bag": OPTS_BAG,
        "sectors": {k: v for k, v in SECTORS.items()},
        "windows": WINDOWS,
        "models_considered": [m["id"] for m in models],
        "screen": screen_sorted,
        "leaderboards": {
            "by_gain": [r["id"] for r in screen_ok],
            "by_risk_adj": [r["id"] for r in by_ra],
            "by_low_dd": [r["id"] for r in by_dd],
        },
        "top_ids": top_ids,
        "deep": {},
        "final_ranking": [],
        "notes": [
            f"Starting cash ${CASH:,.0f}",
            "Screen ranked by $ PnL (return × cash), not win rate",
            "Also published: risk (low |DD|) and risk-adjusted (ret/|DD|)",
            "Deep = sectors + indices + options/equity where supported",
            "Small cash lowers max_contracts so options sizing is less fake",
        ],
    }

    if args.screen_only or not top_ids:
        state["final_ranking"] = [
            {
                "id": r["id"],
                "rank": i,
                "rank_score": r.get("score_gain", r.get("score", -1)),
                "mean_ret": r.get("ret"),
                "mean_wr": r.get("wr"),
                "mean_dd": r.get("dd"),
                "mean_pnl": r.get("pnl"),
                "n_tests_ok": 0 if r.get("error") or r.get("n", 0) == 0 else 1,
                "n_tests_fail": 1 if r.get("error") or r.get("n", 0) == 0 else 0,
                "screen_score": r.get("score"),
            }
            for i, r in enumerate(screen_sorted, 1)
        ]
        STATE.write_text(json.dumps(state, indent=2, default=str))
        write_report(state)
        print(f"\nState → {STATE}")
        print(f"Report → {REPORT}")
        return 0

    models_by_id = {m["id"]: m for m in models}
    sectors = list(SECTORS.keys())
    if args.quick:
        sectors = ["semis", "high_beta", "mega_tech", "indices"]
    do_late = bool(args.full) or (not args.quick)

    deep: dict[str, list[dict]] = {tid: [] for tid in top_ids}
    start_f, end_f = WINDOWS["deep_full"]
    start_l, end_l = WINDOWS["deep_late"]

    print("\n======== PHASE 2: DEEP TEST ========", flush=True)
    for tid in top_ids:
        m = models_by_id[tid]
        modes = m["modes"]
        print(f"\n---- deep {tid} modes={modes} ----", flush=True)

        for sec in sectors:
            codes = SECTORS[sec]
            if "daily" in modes:
                deep[tid].append(
                    run_one_wrap(m, mode="daily", codes=codes, start=start_f, end=end_f, tag=f"sec_{sec}")
                )
            if "options" in modes and sec in ("semis", "high_beta", "indices", "mega_tech"):
                deep[tid].append(
                    run_one_wrap(
                        m, mode="options", codes=codes, start=start_f, end=end_f, tag=f"sec_{sec}_opts"
                    )
                )

        if "daily" in modes:
            deep[tid].append(
                run_one_wrap(
                    m, mode="daily", codes=SECTORS["indices"], start=start_f, end=end_f, tag="indices"
                )
            )
            deep[tid].append(
                run_one_wrap(
                    m, mode="daily", codes=SCREEN_BAG, start=start_f, end=end_f, tag="equity_mixed"
                )
            )
            if do_late:
                deep[tid].append(
                    run_one_wrap(
                        m,
                        mode="daily",
                        codes=SCREEN_BAG,
                        start=start_l,
                        end=end_l,
                        tag="equity_mixed_late",
                    )
                )

        if "options" in modes:
            deep[tid].append(
                run_one_wrap(
                    m, mode="options", codes=OPTS_BAG, start=start_f, end=end_f, tag="opts_growth"
                )
            )
            deep[tid].append(
                run_one_wrap(
                    m,
                    mode="options",
                    codes=SECTORS["indices"],
                    start=start_f,
                    end=end_f,
                    tag="indices_opts",
                )
            )
            if do_late:
                deep[tid].append(
                    run_one_wrap(
                        m,
                        mode="options",
                        codes=OPTS_BAG,
                        start=start_l,
                        end=end_l,
                        tag="opts_growth_late",
                    )
                )

    screen_map = {r["id"]: r for r in screen_sorted}
    final = aggregate_deep(deep, screen_map)
    state["deep"] = deep
    state["final_ranking"] = final
    state["updated_at"] = _now()
    STATE.write_text(json.dumps(state, indent=2, default=str))
    write_report(state)

    print("\n======== FINAL DYNAMIC RANK ========", flush=True)
    for r in final:
        print(
            f"  #{r['rank']} {r['id']:28} score={r['rank_score']:.3f} "
            f"mean_ret={(r['mean_ret'] or 0)*100:6.1f}% "
            f"tests={r['n_tests_ok']}/{r['n_tests_ok']+r['n_tests_fail']}"
        )
    if final:
        print(f"\nTOP MODEL: {final[0]['id']}")
    print(f"State → {STATE}")
    print(f"Report → {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
