#!/usr/bin/env python3
"""One-shot bounce probability read for user book."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

BOOK = {
    "TSLA": {"target": 397.5, "exp": "tomorrow"},
    "MSTR": {"target": 102.0, "exp": "2026-08-07"},
    "SKHY": {"target": 180.0, "exp": "2026-08-21"},
    "INFQ": {"target": 10.0, "exp": "stock"},
}


def _parse_json(txt: str):
    start = txt.find("{")
    end = txt.rfind("}")
    if start < 0 or end < 0:
        return None
    return json.loads(txt[start : end + 1])


def hist_stats(d, today_ret: float):
    rets = d["Close"].pct_change()
    thr = min(today_ret, -0.01)
    closes = d["Close"]
    fwd1, fwd5 = [], []
    for i in rets[rets <= thr].index:
        loc = closes.index.get_loc(i)
        if not isinstance(loc, (int, np.integer)):
            continue
        loc = int(loc)
        if loc + 1 < len(closes):
            fwd1.append(float(closes.iloc[loc + 1]) / float(closes.iloc[loc]) - 1)
        if loc + 5 < len(closes):
            fwd5.append(float(closes.iloc[loc + 5]) / float(closes.iloc[loc]) - 1)

    def pack(a):
        if not a:
            return None
        a = np.array(a, dtype=float)
        return {
            "n": int(len(a)),
            "p_up": float((a > 0).mean()),
            "med": float(np.median(a)),
            "mean": float(a.mean()),
        }

    return pack(fwd1), pack(fwd5)


def main():
    spot = {}
    print("=== SPOT / STRUCTURE ===")
    for s in BOOK:
        t = yf.Ticker(s)
        d = t.history(period="60d", interval="1d")
        if d.empty:
            print(s, "no data")
            continue
        last = float(d["Close"].iloc[-1])
        prev = float(d["Close"].iloc[-2])
        lo = float(d["Low"].iloc[-1])
        hi = float(d["High"].iloc[-1])
        o = float(d["Open"].iloc[-1])
        h5 = float(d["High"].tail(5).max())
        l5 = float(d["Low"].tail(5).min())
        pos = (last - l5) / (h5 - l5) if h5 > l5 else 0.5
        today_ret = last / prev - 1
        h1, h5s = hist_stats(d, today_ret)
        need = BOOK[s]["target"] / last - 1
        spot[s] = {
            "last": last,
            "day_ret": today_ret,
            "open": o,
            "high": hi,
            "low": lo,
            "pos_in_5d": pos,
            "hist1": h1,
            "hist5": h5s,
            "need_pct": need,
        }
        print(
            f"{s}: last={last:.2f} day={today_ret*100:+.1f}% "
            f"5d_range_pos={pos:.0%} need_tgt={need*100:+.1f}%"
        )
        if h1:
            msg = (
                f"   hist after similar/worse day: next1d P(up)={h1['p_up']:.0%} "
                f"n={h1['n']} med={h1['med']*100:+.1f}%"
            )
            if h5s:
                msg += (
                    f" | next5d P(up)={h5s['p_up']:.0%} med={h5s['med']*100:+.1f}%"
                )
            print(msg)

    print("\n=== MODEL LIVE_PLAN ===")
    models = {}
    for s in BOOK:
        r = subprocess.run(
            [
                str(ROOT / ".venv/bin/python"),
                "tools/live_plan.py",
                "--symbol",
                s,
                "--account",
                "1000",
                "--model",
                "auto",
                "--json",
            ],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            timeout=120,
        )
        d = _parse_json(r.stdout)
        if not d:
            print(s, "no json")
            continue
        live = d.get("live") or {}
        model = d.get("model") or {}
        conf = d.get("confidence") or {}
        dec = d.get("decision") or {}
        ticket = d.get("ticket") or {}
        models[s] = {
            "mode": ticket.get("mode") or dec.get("mode"),
            "analysis": dec.get("analysis_action") or model.get("action_hint"),
            "setup_ok": model.get("setup_ok"),
            "model_id": model.get("model"),
            "model_conf": model.get("confidence"),
            "raw_p": conf.get("raw_probability"),
            "cal_p": conf.get("calibrated_probability"),
            "conf_state": conf.get("state"),
            "go_long": live.get("go_long"),
            "soft_long": live.get("soft_long"),
            "swing_up": live.get("swing_uptrend"),
            "above_vwap": live.get("above_vwap"),
            "macd_pos": live.get("macd_positive"),
            "vol_z": live.get("vol_z"),
            "stop": model.get("stop"),
            "price": live.get("price"),
        }
        m = models[s]
        print(
            f"{s}: model={m['model_id']} analysis={m['analysis']} setup={m['setup_ok']} "
            f"conf={m['model_conf']} state={m['conf_state']} go_long={m['go_long']} "
            f"soft={m['soft_long']} swing={m['swing_up']} vwap={m['above_vwap']} "
            f"macd={m['macd_pos']} volz={m['vol_z']} stop={m['stop']}"
        )

    print("\n=== OPTIONS / VOL ===")
    from options_unusual_flow import scan_symbol
    from vol_package_score import score_symbol

    opts = {}
    for s in BOOK:
        try:
            fl = scan_symbol(s, max_expiries=4, max_dte=45, top_n=10)
        except Exception as e:
            fl = {"ok": False, "error": str(e), "flags": []}
        try:
            vp = score_symbol(s)
        except Exception as e:
            vp = {"ok": False, "error": str(e), "features": {}, "warnings": []}
        flags = fl.get("flags") or []
        calls = sum(
            1 for f in flags if str(f.get("right", "")).upper() in ("C", "CALL")
        )
        puts = sum(
            1 for f in flags if str(f.get("right", "")).upper() in ("P", "PUT")
        )
        prem_c = sum(
            float(f.get("premium") or 0)
            for f in flags
            if str(f.get("right", "")).upper() in ("C", "CALL")
        )
        prem_p = sum(
            float(f.get("premium") or 0)
            for f in flags
            if str(f.get("right", "")).upper() in ("P", "PUT")
        )
        feat = vp.get("features") or {}
        opts[s] = {
            "calls": calls,
            "puts": puts,
            "prem_c": prem_c,
            "prem_p": prem_p,
            "pc": feat.get("put_call_vol_ratio"),
            "atm_iv": feat.get("atm_iv"),
            "rec": (vp.get("recommended") or {}).get("action"),
            "rec_t": (vp.get("recommended") or {}).get("template"),
            "warns": [w.get("code") for w in (vp.get("warnings") or [])],
        }
        o = opts[s]
        iv = None if not o["atm_iv"] else round(o["atm_iv"] * 100, 1)
        print(
            f"{s}: flags C/P={calls}/{puts} premC/P={prem_c:.0f}/{prem_p:.0f} "
            f"PCvol={o['pc']} IV={iv}% rec={o['rec_t']}/{o['rec']} warns={o['warns']}"
        )

    print("\n=== GEX ===")
    gex = {}
    for s in BOOK:
        r = subprocess.run(
            [
                str(ROOT / ".venv/bin/python"),
                "tools/gamma_exposure.py",
                "--symbol",
                s,
                "--json",
            ],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            timeout=90,
        )
        d = _parse_json(r.stdout)
        if not d:
            print(s, "gex fail")
            continue
        gex[s] = {
            "call_wall": d.get("call_wall"),
            "put_wall": d.get("put_wall"),
            "label": d.get("label"),
            "spot": d.get("spot"),
        }
        print(
            f"{s}: spot={gex[s]['spot']} call_wall={gex[s]['call_wall']} "
            f"put_wall={gex[s]['put_wall']} label={gex[s]['label']}"
        )

    print("\n=== COMPOSITE BOUNCE PROB (desk heuristic, not calibrated) ===")
    out_rows = []
    for s in BOOK:
        m = models.get(s, {})
        o = opts.get(s, {})
        g = gex.get(s, {})
        sp = spot.get(s, {})
        score = 0.35
        reasons = []

        if m.get("go_long"):
            score += 0.20
            reasons.append("go_long")
        elif m.get("soft_long"):
            score += 0.10
            reasons.append("soft_long")
        else:
            score -= 0.08
            reasons.append("no_long")

        if m.get("setup_ok"):
            score += 0.12
            reasons.append("setup_ok")
        else:
            score -= 0.05
            reasons.append("setup_not_ok")

        anal = str(m.get("analysis") or "")
        if "BUY" in anal:
            score += 0.12
            reasons.append(anal)
        elif "PULLBACK" in anal:
            score += 0.05
            reasons.append(anal)
        elif "WAIT" in anal or "AVOID" in anal:
            score -= 0.05
            reasons.append(anal)

        conf = m.get("model_conf") or m.get("raw_p") or 0
        if conf:
            score += (float(conf) - 0.5) * 0.25
            reasons.append(f"conf={float(conf):.2f}")

        if m.get("swing_up"):
            score += 0.06
        else:
            score -= 0.06
        if m.get("above_vwap"):
            score += 0.08
        else:
            score -= 0.08
        if m.get("macd_pos"):
            score += 0.05
        else:
            score -= 0.04

        if o.get("calls", 0) > o.get("puts", 0) * 1.2:
            score += 0.08
            reasons.append("call_flow")
        if o.get("puts", 0) > o.get("calls", 0) * 1.2:
            score -= 0.08
            reasons.append("put_flow")
        if (o.get("prem_p") or 0) > (o.get("prem_c") or 0) * 1.5:
            score -= 0.06
            reasons.append("put_premium_heavy")
        if (o.get("prem_c") or 0) > (o.get("prem_p") or 0) * 1.5:
            score += 0.06
            reasons.append("call_premium_heavy")
        pc = o.get("pc")
        if pc and pc > 1.5:
            score -= 0.05
            reasons.append("high_pc_vol")

        lab = str(g.get("label") or "")
        if "amplify" in lab:
            score -= 0.05
            reasons.append("neg_gex_extend")
        if "pin" in lab:
            score += 0.02
            reasons.append("gex_pin")

        h1 = sp.get("hist1") or {}
        if h1.get("p_up") is not None:
            score += (h1["p_up"] - 0.5) * 0.2
            reasons.append(f"hist1d_up={h1['p_up']:.0%}")

        need = sp.get("need_pct") or 0
        if s == "TSLA" and need > 0.015:
            score -= 0.08
            reasons.append("need_+2%_1dte")
        if s == "SKHY" and need > 0.10:
            score -= 0.05
            reasons.append("need_+12%_swing")
        if s == "MSTR" and need > 0.07:
            score -= 0.03
        if s == "INFQ" and need > 0.08:
            score -= 0.03

        bounce = max(0.05, min(0.92, score))
        # hit user target is harder than "any bounce"
        hit = bounce * max(0.12, 1.0 - abs(need) * 2.8)
        if need <= 0:
            hit = max(hit, 0.80)

        # also report model raw as "edge probability" if present
        model_p = m.get("cal_p") or m.get("model_conf") or m.get("raw_p")

        row = {
            "symbol": s,
            "last": sp.get("last"),
            "target": BOOK[s]["target"],
            "need_pct": need,
            "p_bounce_relief": round(bounce, 3),
            "p_hit_target": round(hit, 3),
            "model_conf": model_p,
            "analysis": m.get("analysis"),
            "conf_state": m.get("conf_state"),
            "go_long": m.get("go_long"),
            "reasons": reasons[:10],
        }
        out_rows.append(row)
        print(
            f"{s}: P(bounce_relief)~{bounce*100:.0f}%  "
            f"P(hit_target {BOOK[s]['target']})~{hit*100:.0f}%  "
            f"need={need*100:+.1f}%  model_conf={model_p}"
        )
        print(f"   drivers: {', '.join(reasons[:9])}")

    out = {
        "ok": True,
        "asof_utc": datetime.now(timezone.utc).isoformat(),
        "note": (
            "Bounce probs are a desk heuristic combining live_plan, options flow, "
            "vol package, GEX, and simple historical next-day stats. "
            "Not a calibrated probability model. conf_state ABSTAIN means desk does not size."
        ),
        "rows": out_rows,
        "models": models,
        "opts": opts,
        "gex": gex,
        "spot": {k: {kk: vv for kk, vv in v.items() if kk not in ()} for k, v in spot.items()},
    }
    path = ROOT / "runs" / "_bounce_read.json"
    path.write_text(json.dumps(out, indent=2, default=str))
    print("\nWrote", path)
    print("asof", out["asof_utc"])


if __name__ == "__main__":
    main()
