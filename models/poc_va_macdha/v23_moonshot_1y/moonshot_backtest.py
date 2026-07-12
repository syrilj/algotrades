#!/usr/bin/env python3
"""v23_moonshot_1y — attempt $1k → $1M in ~1 year via convex options + pyramid.

Doctrine (from books + prior models):
- Options guide: long calls want MOVEMENT; match structure to shock/trend regime
- Sniper DNA (v18/v20b): APLD/IONQ + vol expand — highest asymmetry for $1k
- Anti-martingale / pyramid winners (Soros-style: press when thesis working)
- Cut losers fast (LSE / OPTIONS_1K_PLAYBOOK TP/SL research)
- Concentrate: 1 idea at a time on $1k

This is a RESEARCH moonshot. Synthetic BS premiums (IV=rv20). Not exchange fills.
Goal metric: did equity ever reach $1,000,000 within a 1-year window?
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
from options_bs import bs_price, round_strike  # noqa: E402

OUT = ROOT / "models" / "poc_va_macdha" / "v23_moonshot_1y"
ART = ROOT / "runs" / "poc_va_v23_moonshot_1y" / "artifacts"
TRADES = ROOT / "runs" / "poc_va_v20b_macro_light" / "artifacts" / "trades.csv"
GOAL = 1_000_000.0
START = 1_000.0

# Torque universe: sniper + hunt winners that fit $1k premiums
CODES = ["APLD.US", "IONQ.US", "HOOD.US", "MARA.US", "SMCI.US", "GME.US"]

WINDOWS = [
    ("y1_a", "2024-07-11", "2025-07-11"),
    ("y1_b", "2025-07-11", "2026-07-11"),
    ("full", "2024-08-01", "2026-07-11"),
]


@dataclass
class RunResult:
    name: str
    window: str
    final: float
    ret: float
    max_dd: float
    peak: float
    hit_1m: bool
    days_to_1m: int | None
    n: int
    wr: float
    max_trade_mult: float
    path_note: str


def roundtrips_from_stock_trades(path: Path, codes: list[str], start: str, end: str) -> pd.DataFrame:
    t = pd.read_csv(path, parse_dates=["timestamp"])
    t = t[(t.timestamp >= start) & (t.timestamp <= end)]
    buys, sells = t[t.side == "buy"], t[t.side == "sell"]
    rows = []
    for code in codes:
        gb = buys[buys.code == code].reset_index(drop=True)
        gs = sells[sells.code == code].reset_index(drop=True)
        n = min(len(gb), len(gs))
        for i in range(n):
            rows.append(
                {
                    "code": code,
                    "entry": pd.Timestamp(gb.loc[i, "timestamp"]),
                    "exit": pd.Timestamp(gs.loc[i, "timestamp"]),
                    "entry_px": float(gb.loc[i, "price"]),
                    "exit_px": float(gs.loc[i, "price"]),
                    "stock_ret": float(gs.loc[i, "return_pct"]) / 100.0
                    if abs(float(gs.loc[i, "return_pct"])) > 1.5
                    else float(gs.loc[i, "return_pct"]),
                }
            )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("entry").reset_index(drop=True)


def load_daily(code: str, start: str, end: str) -> pd.DataFrame:
    yf_sym = code.replace(".US", "")
    df = yf.download(yf_sym, start=start, end=end, auto_adjust=True, progress=False)
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower() for c in df.columns]
    else:
        df.columns = [str(c).lower() for c in df.columns]
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df["ret"] = df["close"].pct_change()
    df["rv20"] = df["ret"].rolling(20).std() * np.sqrt(252)
    df["rv20"] = df["rv20"].clip(0.2, 2.0).fillna(0.6)
    return df


def synth_signals_from_price(df: pd.DataFrame, code: str) -> pd.DataFrame:
    """Fallback big-move detector when stock model has no trades for a name.

    Setup: 20d breakout + vol expand + positive 5d momentum (movement regime).
    Hold ~3-8 days or until 10% giveback from peak.
    """
    if df.empty or len(df) < 40:
        return pd.DataFrame()
    c = df["close"]
    vol = df["volume"] if "volume" in df.columns else pd.Series(1.0, index=df.index)
    hi20 = c.rolling(20).max().shift(1)
    vol_ma = vol.rolling(20).mean()
    mom5 = c.pct_change(5)
    entry = (c > hi20) & (vol > 1.3 * vol_ma) & (mom5 > 0.03)
    rows = []
    in_pos = False
    ent = peak = None
    for ts, is_e in entry.items():
        px = float(c.loc[ts])
        if not in_pos and bool(is_e):
            in_pos = True
            ent = ts
            peak = px
            ent_px = px
        elif in_pos:
            peak = max(peak, px)
            days = (ts - ent).days
            giveback = px < peak * 0.90
            if days >= 8 or giveback or px < ent_px * 0.92:
                rows.append(
                    {
                        "code": code,
                        "entry": ent,
                        "exit": ts,
                        "entry_px": ent_px,
                        "exit_px": px,
                        "stock_ret": px / ent_px - 1.0,
                    }
                )
                in_pos = False
    return pd.DataFrame(rows)


def option_path_pnl(
    spot_entry: float,
    spot_exit: float,
    iv: float,
    dte: int,
    otm: float,
    hold_days: float,
) -> tuple[float, float, float]:
    """Return (entry_prem, exit_prem, multiple)."""
    raw_k = spot_entry * (1.0 + otm)
    k = round_strike(spot_entry, raw_k)
    t0 = max(dte, 1) / 365.0
    t1 = max(dte - max(hold_days, 0.5), 0.5) / 365.0
    p0 = max(bs_price(spot_entry, k, t0, 0.05, iv, True), 0.05)
    p1 = bs_price(spot_exit, k, t1, 0.05, iv, True)
    # intrinsic floor at exit
    p1 = max(p1, max(spot_exit - k, 0.0))
    return p0, p1, (p1 / p0) if p0 > 0 else 0.0


def run_variant(
    name: str,
    window: str,
    start: str,
    end: str,
    signals: pd.DataFrame,
    pxmap: dict[str, pd.DataFrame],
    *,
    otm: float,
    dte: int,
    base_risk: float,
    pyramid: list[float],
    tp_mult: float,
    sl_frac: float,
    max_contracts: int = 5000,
) -> RunResult:
    cash = START
    peak = cash
    max_dd = 0.0
    wins_streak = 0
    trades = []
    hit_day = None
    start_ts = pd.Timestamp(start)
    max_trade_mult = 0.0

    for _, row in signals.iterrows():
        code = row["code"]
        if code not in pxmap or pxmap[code].empty:
            continue
        df = pxmap[code]
        ent = pd.Timestamp(row["entry"]).tz_localize(None)
        ex = pd.Timestamp(row["exit"]).tz_localize(None)
        # align to daily index
        if ent not in df.index:
            idx = df.index[df.index <= ent]
            if len(idx) == 0:
                continue
            ent = idx[-1]
        if ex not in df.index:
            idx = df.index[df.index <= ex]
            if len(idx) == 0:
                continue
            ex = idx[-1]
        spot0 = float(df.loc[ent, "close"])
        spot1 = float(df.loc[ex, "close"])
        iv = float(df.loc[ent, "rv20"])
        hold = max((ex - ent).days, 1)
        p0, p1, mult = option_path_pnl(spot0, spot1, iv, dte, otm, hold)
        # apply early TP/SL on option multiple vs hold-to-exit
        # approximate: if stock moved enough for TP, cap mult; if loser, floor
        stock_move = spot1 / spot0 - 1.0
        # rough delta~0.35 OTM mapping
        approx = 1.0 + stock_move * (0.35 / max(p0 / spot0, 1e-6)) * 0.01
        # better: use computed mult, then clip by TP/SL
        realized = mult
        if realized >= tp_mult:
            realized = tp_mult
        if realized <= (1.0 - sl_frac):
            realized = 1.0 - sl_frac
        max_trade_mult = max(max_trade_mult, realized)

        risk_pct = pyramid[min(wins_streak, len(pyramid) - 1)]
        risk_pct = max(risk_pct, base_risk)
        budget = cash * risk_pct
        if budget < p0 * 100 * 0.5:
            # can't afford half contract notionally — skip
            continue
        qty = int(budget / (p0 * 100))
        qty = max(1, min(qty, max_contracts))
        debit = qty * p0 * 100
        if debit > cash * 0.99:
            qty = max(1, int(cash * 0.95 / (p0 * 100)))
            debit = qty * p0 * 100
        if debit > cash or qty < 1:
            continue
        credit = qty * (p0 * realized) * 100
        pnl = credit - debit
        cash = cash - debit + credit
        cash = max(cash, 0.0)
        peak = max(peak, cash)
        dd = (peak - cash) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)
        win = pnl > 0
        wins_streak = wins_streak + 1 if win else 0
        trades.append({"code": code, "pnl": pnl, "mult": realized, "cash": cash, "entry": str(ent.date())})
        if hit_day is None and cash >= GOAL:
            hit_day = (ex - start_ts).days

    wr = float(np.mean([t["pnl"] > 0 for t in trades])) if trades else 0.0
    note = f"n={len(trades)} peak=${peak:,.0f}"
    if hit_day is not None:
        note += f" HIT_$1M_in_{hit_day}d"
    return RunResult(
        name=name,
        window=window,
        final=cash,
        ret=cash / START - 1.0,
        max_dd=-max_dd,
        peak=peak,
        hit_1m=cash >= GOAL or peak >= GOAL,
        days_to_1m=hit_day,
        n=len(trades),
        wr=wr,
        max_trade_mult=max_trade_mult,
        path_note=note,
    )


def build_signal_book(start: str, end: str, pxmap: dict[str, pd.DataFrame]) -> pd.DataFrame:
    parts = []
    # Prefer v20b roundtrips for APLD/IONQ
    if TRADES.exists():
        rt = roundtrips_from_stock_trades(TRADES, ["APLD.US", "IONQ.US"], start, end)
        if not rt.empty:
            parts.append(rt)
    # Synth big-move for remaining / fill
    have = set()
    if parts:
        have = set(parts[0]["code"].unique()) if not parts[0].empty else set()
    for code in CODES:
        if code in have:
            continue
        syn = synth_signals_from_price(pxmap.get(code, pd.DataFrame()), code)
        if not syn.empty:
            parts.append(syn)
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True).sort_values("entry").reset_index(drop=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ART.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    variants = [
        # name, otm, dte, base_risk, pyramid, tp, sl
        ("sniper_pyramid_otm10", 0.10, 14, 0.25, [0.25, 0.40, 0.60, 0.80], 3.0, 0.50),
        ("sniper_pyramid_otm15", 0.15, 10, 0.30, [0.30, 0.50, 0.70, 0.90], 4.0, 0.55),
        ("moon_yolo_otm20", 0.20, 7, 0.40, [0.40, 0.65, 0.85, 0.95], 5.0, 0.60),
        ("press_hard_otm12", 0.12, 10, 0.35, [0.35, 0.55, 0.75, 0.95], 3.5, 0.50),
    ]

    for wname, start, end in WINDOWS:
        pxmap = {c: load_daily(c, start, end) for c in CODES}
        signals = build_signal_book(start, end, pxmap)
        print(f"Window {wname} signals={len(signals)}", flush=True)
        for vname, otm, dte, base, pyr, tp, sl in variants:
            r = run_variant(
                vname,
                wname,
                start,
                end,
                signals,
                pxmap,
                otm=otm,
                dte=dte,
                base_risk=base,
                pyramid=pyr,
                tp_mult=tp,
                sl_frac=sl,
            )
            results.append(asdict(r))
            flag = "HIT" if r.hit_1m else ""
            print(
                f"  {vname:28s} final=${r.final:>12,.0f} peak=${r.peak:>12,.0f} "
                f"dd={r.max_dd*100:5.1f}% n={r.n:3d} wr={r.wr*100:4.0f}% {flag}",
                flush=True,
            )

    results.sort(key=lambda x: x["peak"], reverse=True)
    (OUT / "results.json").write_text(json.dumps({"goal": GOAL, "start": START, "results": results}, indent=2) + "\n")
    (ART / "results.json").write_text(json.dumps({"goal": GOAL, "start": START, "results": results}, indent=2) + "\n")

    best = results[0] if results else None
    hits = [r for r in results if r["hit_1m"]]
    lines = [
        "# v23_moonshot_1y results",
        "",
        "Goal: **$1,000 → $1,000,000 in ~1 year** via sniper timing + OTM calls + pyramid winners.",
        "",
        f"Hits $1M: **{len(hits)}** / {len(results)} variant-windows",
        "",
        "| variant | window | final | peak | DD | n | WR | hit |",
        "|---------|--------|------:|-----:|---:|--:|---:|:---:|",
    ]
    for r in results[:20]:
        lines.append(
            f"| `{r['name']}` | {r['window']} | ${r['final']:,.0f} | ${r['peak']:,.0f} | "
            f"{r['max_dd']*100:.0f}% | {r['n']} | {r['wr']*100:.0f}% | {'YES' if r['hit_1m'] else ''} |"
        )
    if best:
        lines += [
            "",
            "## Best peak path",
            f"- `{best['name']}` on `{best['window']}` peak **${best['peak']:,.0f}** final **${best['final']:,.0f}**",
            f"- {best['path_note']}",
        ]
    if not hits:
        lines += [
            "",
            "## Verdict",
            "No variant hit $1M in these synthetic paths. Closest peaks show what convexity + pyramid can do;",
            "1000× in 1y still needs a rare streak of large option multiples in sequence.",
        ]
    else:
        lines += ["", "## Verdict", "At least one path hit $1M — inspect days_to_1m and promote carefully (BS not live fills)."]
    (OUT / "REPORT.md").write_text("\n".join(lines) + "\n")
    print("\nWrote", OUT / "REPORT.md", flush=True)
    if best:
        print(f"BEST PEAK ${best['peak']:,.0f} ({best['name']} / {best['window']}) hit={best['hit_1m']}", flush=True)


if __name__ == "__main__":
    main()
