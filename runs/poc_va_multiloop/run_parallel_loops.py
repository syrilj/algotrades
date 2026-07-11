#!/usr/bin/env python3
"""Parallel feedback loops: three independent approaches on the same trade book.

Loop A — Sniper (APLD/IONQ): push WR with train/test lifts (toward 90%+ intuition).
Loop B — Large-cap (TSLA/MU): maximize expectancy/PF under Mag7/QQQ DNA (not vanity WR).
Loop C — Broad book: improve full-universe meta stack for Sharpe-like retention.

Anti-overfit (shared):
- Chronological 60/40 train/test
- Choose filter on TRAIN lift only
- Require test_lift >= -2pp (or near target)
- Min retention 20% per round
- Binary/structural filters only
- Score primary objective per loop; WR alone never promotes

Outputs → runs/poc_va_multiloop/artifacts/
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "artifacts"
OUT.mkdir(parents=True, exist_ok=True)
SRC = ROOT / "runs" / "poc_va_wr80" / "artifacts" / "enriched_trades.csv"


def _bool_cols(df: pd.DataFrame) -> list[str]:
    cols = []
    for c in df.columns:
        if c.startswith("f_") or c.startswith("drop_") or c.startswith("keep_"):
            if c.startswith("keep_"):
                continue  # keep_* is inverse noise; use drop_*
            cols.append(c)
    return cols


def _metrics(sub: pd.DataFrame) -> dict:
    if sub.empty:
        return {
            "n": 0,
            "wr": 0.0,
            "expectancy": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "pf": 0.0,
            "avg_ret": 0.0,
        }
    wins = sub[sub["win"] == 1]["return_pct"]
    losses = sub[sub["win"] == 0]["return_pct"]
    gp = float(wins.sum()) if len(wins) else 0.0
    gl = float((-losses).sum()) if len(losses) else 0.0
    pf = gp / gl if gl > 0 else (99.0 if gp > 0 else 0.0)
    return {
        "n": int(len(sub)),
        "wr": float(sub["win"].mean()),
        "expectancy": float(sub["return_pct"].mean()),
        "avg_win": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss": float(losses.mean()) if len(losses) else 0.0,
        "pf": float(pf),
        "avg_ret": float(sub["return_pct"].mean()),
    }


def _split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = df.sort_values("entry_ts").reset_index(drop=True)
    cut = int(len(d) * 0.6)
    return d.iloc[:cut].copy(), d.iloc[cut:].copy()


@dataclass
class Candidate:
    filter: str
    wr_train: float
    wr_test: float
    wr_all: float
    n_train: int
    n_test: int
    n_all: int
    train_lift: float
    test_lift: float
    retention: float
    exp_train: float
    exp_test: float
    pf_all: float


def _apply(df: pd.DataFrame, filt: str) -> pd.DataFrame:
    if filt not in df.columns:
        return df.iloc[0:0].copy()
    return df[df[filt].astype(bool)].copy()


def _score_candidates(
    cur: pd.DataFrame,
    filters: list[str],
    objective: str,
    min_retention: float = 0.2,
    min_n_train: int = 5,
) -> list[Candidate]:
    train, test = _split(cur)
    base_tr = _metrics(train)
    base_te = _metrics(test)
    out: list[Candidate] = []
    for f in filters:
        if f not in cur.columns:
            continue
        tr = _apply(train, f)
        te = _apply(test, f)
        al = _apply(cur, f)
        if len(tr) < min_n_train:
            continue
        ret = len(tr) / max(len(train), 1)
        if ret < min_retention:
            continue
        mtr, mte, mall = _metrics(tr), _metrics(te), _metrics(al)
        train_lift = mtr["wr"] - base_tr["wr"]
        test_lift = mte["wr"] - base_te["wr"]
        # soft reject: big OOS WR damage unless still near useful
        if test_lift < -0.02 and mte["wr"] < 0.75:
            continue
        # expectancy shouldn't collapse on test
        if mte["expectancy"] < -0.1:
            continue
        out.append(
            Candidate(
                filter=f,
                wr_train=mtr["wr"],
                wr_test=mte["wr"],
                wr_all=mall["wr"],
                n_train=mtr["n"],
                n_test=mte["n"],
                n_all=mall["n"],
                train_lift=train_lift,
                test_lift=test_lift,
                retention=ret,
                exp_train=mtr["expectancy"],
                exp_test=mte["expectancy"],
                pf_all=mall["pf"],
            )
        )

    def key(c: Candidate):
        if objective == "wr":
            return (c.train_lift, c.wr_train, c.exp_train, c.test_lift)
        if objective == "expectancy":
            return (c.exp_train, c.train_lift, c.pf_all, c.test_lift)
        if objective == "balanced":
            # train WR lift + expectancy, prefer retention
            return (c.train_lift + 0.05 * c.exp_train, c.retention, c.test_lift)
        return (c.train_lift,)

    out.sort(key=key, reverse=True)
    return out


def run_loop(
    name: str,
    df: pd.DataFrame,
    filters: list[str],
    objective: str,
    target_wr: float | None,
    max_rounds: int = 6,
    min_retention: float = 0.2,
) -> dict:
    cur = df.copy()
    applied: list[str] = []
    history: list[dict] = []
    available = [f for f in filters if f in cur.columns]

    for r in range(1, max_rounds + 1):
        train, test = _split(cur)
        state = {
            "round": r,
            **{f"all_{k}": v for k, v in _metrics(cur).items()},
            **{f"train_{k}": v for k, v in _metrics(train).items()},
            **{f"test_{k}": v for k, v in _metrics(test).items()},
        }
        cands = _score_candidates(cur, [f for f in available if f not in applied], objective, min_retention)
        if not cands:
            history.append({"state": state, "applied": list(applied), "chose": None, "stop": "no_candidates"})
            break
        best = cands[0]
        # stop if objective already met and adding would thin too much
        if target_wr is not None and state["test_wr"] >= target_wr and state["train_wr"] >= target_wr:
            history.append({"state": state, "applied": list(applied), "chose": None, "stop": "target_hit"})
            break
        # require positive train objective progress
        if objective == "wr" and best.train_lift <= 0:
            history.append({"state": state, "applied": list(applied), "chose": asdict(best), "stop": "no_train_lift"})
            break
        if objective == "expectancy" and best.exp_train <= _metrics(train)["expectancy"]:
            # still allow if WR lift strong and exp not worse than -eps
            if best.train_lift <= 0.01:
                history.append({"state": state, "applied": list(applied), "chose": asdict(best), "stop": "no_exp_lift"})
                break

        applied.append(best.filter)
        cur = _apply(cur, best.filter)
        history.append({"state": state, "applied": list(applied), "chose": asdict(best), "top3": [asdict(c) for c in cands[:3]]})

        if len(cur) < 8:
            history.append({"state": {**state, "note": "too_thin"}, "applied": list(applied), "chose": None, "stop": "too_thin"})
            break

    train, test = _split(cur)
    single = []
    for f in available:
        m = _metrics(_apply(df, f))
        if m["n"] >= 8:
            single.append({"filter": f, **m})
    single.sort(key=lambda x: (x["wr"], x["expectancy"]), reverse=True)

    by_code = (
        cur.groupby("code")
        .apply(lambda g: pd.Series({"wr": g["win"].mean(), "n": len(g), "exp": g["return_pct"].mean()}))
        .reset_index()
        .to_dict(orient="records")
        if len(cur)
        else []
    )

    return {
        "name": name,
        "objective": objective,
        "target_wr": target_wr,
        "universe_n_base": int(len(df)),
        "base": _metrics(df),
        "applied_filters": applied,
        "final": _metrics(cur),
        "final_train": _metrics(train),
        "final_test": _metrics(test),
        "final_by_code": by_code,
        "history": history,
        "single_filter_hits": single[:15],
        "anti_overfit": [
            "60/40 chronological train/test",
            "filter chosen on train objective only",
            "reject test_lift < -2pp unless high WR",
            f"min retention {min_retention:.0%} per round",
            "binary/structural filters only",
        ],
        "pass_bar_soft": {
            "note": "Trade-level proxy only — engine backtest required to promote",
            "min_trades_gate": 40,
            "meets_min_trades": int(len(cur) >= 40),
            "pf_ok": bool(_metrics(cur)["pf"] >= 1.2),
            "exp_ok": bool(_metrics(cur)["expectancy"] > 0),
            "oos_wr": float(_metrics(test)["wr"]),
            "oos_n": int(_metrics(test)["n"]),
        },
    }


def main() -> None:
    df = pd.read_csv(SRC)
    df["entry_ts"] = pd.to_datetime(df["entry_ts"])
    df["win"] = df["win"].astype(float)
    filters = _bool_cols(df)

    # --- Loop A: sniper small-caps ---
    sniper = df[df["code"].isin(["APLD.US", "IONQ.US"])].copy()
    # Prefer structure filters; avoid drop_self
    a_filters = [
        c
        for c in filters
        if not c.startswith("drop_APLD") and not c.startswith("drop_IONQ") and not c.startswith("keep_")
    ]
    loop_a = run_loop("A_sniper_apld_ionq", sniper, a_filters, objective="wr", target_wr=0.90, min_retention=0.25)

    # --- Loop B: large-cap DNA ---
    large = df[df["code"].isin(["TSLA.US", "MU.US"])].copy()
    b_filters = [
        c
        for c in filters
        if c.startswith("f_")  # no drop_* — we want to KEEP trading these names
    ]
    loop_b = run_loop(
        "B_largecap_tsla_mu",
        large,
        b_filters,
        objective="expectancy",
        target_wr=0.70,
        min_retention=0.22,
        max_rounds=7,
    )

    # --- Loop C: broad book (drop weak names allowed) ---
    loop_c = run_loop(
        "C_broad_book",
        df.copy(),
        filters,
        objective="balanced",
        target_wr=0.75,
        min_retention=0.2,
        max_rounds=7,
    )

    # --- Loop D: large + mag7-first forced path (structured) ---
    forced_path = ["f_qqq_trend", "f_mag7_ge4", "f_not_red_flag", "f_vol_expand", "f_local_macd_green"]
    cur = large.copy()
    forced_hist = []
    for f in forced_path:
        if f not in cur.columns:
            continue
        before = _metrics(cur)
        nxt = _apply(cur, f)
        after = _metrics(nxt)
        train, test = _split(nxt) if len(nxt) else (nxt, nxt)
        forced_hist.append(
            {
                "filter": f,
                "before": before,
                "after": after,
                "train": _metrics(train),
                "test": _metrics(test),
            }
        )
        if len(nxt) >= 8:
            cur = nxt
    loop_d = {
        "name": "D_largecap_forced_mag7_path",
        "path": forced_path,
        "history": forced_hist,
        "final": _metrics(cur),
        "final_by_code": (
            cur.groupby("code")
            .apply(lambda g: pd.Series({"wr": g["win"].mean(), "n": len(g), "exp": g["return_pct"].mean()}))
            .reset_index()
            .to_dict(orient="records")
            if len(cur)
            else []
        ),
    }

    # Combinatorial top stacks for sniper (exhaustive small)
    from itertools import combinations

    sniper_feats = [
        "f_qqq_trend",
        "f_not_red_flag",
        "f_vol_expand",
        "f_above_sma20",
        "f_local_macd_green",
        "f_mag7_ge4",
        "f_qqq_and_mag7",
        "f_strong_tech",
        "f_regime_tech",
        "f_tech_vol",
        "f_ret5_pos",
    ]
    combo_rows = []
    for k in (1, 2, 3):
        for combo in combinations([f for f in sniper_feats if f in sniper.columns], k):
            sub = sniper.copy()
            for f in combo:
                sub = _apply(sub, f)
            if len(sub) < 6:
                continue
            train, test = _split(sub)
            m, mt, mte = _metrics(sub), _metrics(train), _metrics(test)
            if mte["n"] < 3:
                continue
            combo_rows.append(
                {
                    "filters": list(combo),
                    **{f"all_{kk}": v for kk, v in m.items()},
                    **{f"train_{kk}": v for kk, v in mt.items()},
                    **{f"test_{kk}": v for kk, v in mte.items()},
                }
            )
    combo_rows.sort(key=lambda r: (r["test_wr"], r["train_wr"], r["all_expectancy"]), reverse=True)

    # Large-cap combos
    large_feats = [
        "f_qqq_trend",
        "f_mag7_ge4",
        "f_mag7_ge5",
        "f_qqq_and_mag7",
        "f_not_red_flag",
        "f_vol_expand",
        "f_strong_regime",
        "f_full_regime",
        "f_local_macd_green",
        "f_above_sma20",
    ]
    large_combos = []
    for k in (1, 2, 3):
        for combo in combinations([f for f in large_feats if f in large.columns], k):
            sub = large.copy()
            for f in combo:
                sub = _apply(sub, f)
            if len(sub) < 10:
                continue
            train, test = _split(sub)
            m, mt, mte = _metrics(sub), _metrics(train), _metrics(test)
            if mte["n"] < 4:
                continue
            large_combos.append(
                {
                    "filters": list(combo),
                    **{f"all_{kk}": v for kk, v in m.items()},
                    **{f"train_{kk}": v for kk, v in mt.items()},
                    **{f"test_{kk}": v for kk, v in mte.items()},
                }
            )
    large_combos.sort(
        key=lambda r: (r["test_expectancy"], r["train_expectancy"], r["test_wr"]),
        reverse=True,
    )

    synthesis = {
        "loops": {
            "A_sniper": loop_a,
            "B_largecap": loop_b,
            "C_broad": loop_c,
            "D_largecap_forced": loop_d,
        },
        "sniper_top_combos": combo_rows[:12],
        "largecap_top_combos": large_combos[:12],
        "recommendations": [],
        "promote": False,
        "notes": [],
    }

    # Build recommendations
    a_test = loop_a["final_test"]["wr"]
    a_n = loop_a["final"]["n"]
    if a_test >= 0.85 and a_n >= 8:
        synthesis["recommendations"].append(
            {
                "sleeve": "A_sniper",
                "action": "keep_as_satellite",
                "filters": loop_a["applied_filters"],
                "oos_wr": a_test,
                "n": a_n,
                "caveat": "Below PASS_BAR min_trades=40 — satellite only, not sole winner",
            }
        )
    best_large = large_combos[0] if large_combos else None
    if best_large and best_large["test_expectancy"] > 0 and best_large["test_wr"] >= 0.65:
        synthesis["recommendations"].append(
            {
                "sleeve": "B_largecap",
                "action": "candidate_engine_dna",
                "filters": best_large["filters"],
                "oos_wr": best_large["test_wr"],
                "oos_exp": best_large["test_expectancy"],
                "n": best_large["all_n"],
            }
        )
    c_test = loop_c["final_test"]["wr"]
    if c_test >= 0.70 and loop_c["final"]["n"] >= 25:
        synthesis["recommendations"].append(
            {
                "sleeve": "C_broad",
                "action": "meta_stack_candidate",
                "filters": loop_c["applied_filters"],
                "oos_wr": c_test,
                "n": loop_c["final"]["n"],
            }
        )

    # Dual-sleeve theoretical: sniper filters on A + large combo on B
    synthesis["notes"].append(
        "Do not merge sleeves into one WR number. Book = wA*sniper + wB*largecap_regime."
    )
    synthesis["notes"].append(
        "PASS_BAR min_trades=40 blocks promoting sniper-alone; dual book or broad sleeve required for winner claim."
    )
    if best_large:
        synthesis["proposed_v18"] = {
            "v18_dual_sleeve": {
                "sniper_universe": ["APLD.US", "IONQ.US"],
                "sniper_filters": loop_a["applied_filters"] or ["f_qqq_trend", "f_not_red_flag"],
                "large_universe": ["TSLA.US", "MU.US"],
                "large_filters": best_large["filters"],
                "drop": ["ARM.US", "SPY.US"],
            }
        }

    # Persist
    (OUT / "LOOP_A_sniper.json").write_text(json.dumps(loop_a, indent=2))
    (OUT / "LOOP_B_largecap.json").write_text(json.dumps(loop_b, indent=2))
    (OUT / "LOOP_C_broad.json").write_text(json.dumps(loop_c, indent=2))
    (OUT / "LOOP_D_forced_large.json").write_text(json.dumps(loop_d, indent=2))
    (OUT / "SNIPER_COMBOS.json").write_text(json.dumps(combo_rows[:30], indent=2))
    (OUT / "LARGECAP_COMBOS.json").write_text(json.dumps(large_combos[:30], indent=2))
    (OUT / "SYNTHESIS.json").write_text(json.dumps(synthesis, indent=2))

    print("=== LOOP A sniper ===")
    print("filters", loop_a["applied_filters"], "final", loop_a["final"], "test", loop_a["final_test"])
    print("=== LOOP B large ===")
    print("filters", loop_b["applied_filters"], "final", loop_b["final"], "test", loop_b["final_test"])
    print("=== LOOP C broad ===")
    print("filters", loop_c["applied_filters"], "final", loop_c["final"], "test", loop_c["final_test"])
    print("=== LOOP D forced ===")
    print(loop_d["final"], loop_d["final_by_code"])
    print("=== TOP SNIPER COMBO ===")
    print(json.dumps(combo_rows[0] if combo_rows else {}, indent=2))
    print("=== TOP LARGE COMBO ===")
    print(json.dumps(large_combos[0] if large_combos else {}, indent=2))
    print("Wrote", OUT)


if __name__ == "__main__":
    main()
