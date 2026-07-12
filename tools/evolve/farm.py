"""Backtest farm: discover, screen, deep-test with content cache."""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import dynamic_model_rank as dmr  # noqa: E402
from evolve.cache import cache_key, read_cached_metrics, write_cached_metrics  # noqa: E402
from evolve.data_contracts import DataTrack, infer_track  # noqa: E402
from evolve.gates import apply_gates, claim_min_trades, dd_hard_from_bar  # noqa: E402
from evolve.scoring import enrich_scores  # noqa: E402

# Shared bags / windows (honest defaults)
EQUITY_BAG = [
    "NVDA.US",
    "TSLA.US",
    "JPM.US",
    "XOM.US",
    "HOOD.US",
    "SPY.US",
    "QQQ.US",
    "MU.US",
]
EQUITY_CORE = ["NVDA.US", "TSLA.US", "SPY.US", "HOOD.US", "MU.US"]
OPTS_BAG = ["IONQ.US", "HOOD.US", "APLD.US", "SOFI.US", "PLTR.US"]
OPTS_GROWTH = ["IONQ.US", "HOOD.US", "AVGO.US", "TSLA.US", "NVDA.US"]
# OPTIONS_WINNER v35 bag8 (research track)
OPTS_BAG8 = [
    "IONQ.US",
    "AVGO.US",
    "HOOD.US",
    "MU.US",
    "TSLA.US",
    "GME.US",
    "COIN.US",
    "RKLB.US",
]
# WINNER equity portfolio bag (v23 config spirit)
EQUITY_WINNER_BAG = ["TSLA.US", "MU.US", "SPY.US", "IONQ.US", "APLD.US", "XLP.US", "QQQ.US"]

WINDOWS = {
    "screen": ("2024-08-01", "2026-07-11"),
    "full": ("2024-08-01", "2026-07-11"),
    "late": ("2025-07-01", "2026-07-11"),
    "oos": ("2025-10-01", "2026-07-11"),
    "early_train": ("2024-08-01", "2025-06-30"),
}

SKIP_EXTRA = set(dmr.SKIP_DIRS)


def discover(
    only: list[str] | None = None,
    *,
    family: str = "poc_va_macdha",
) -> list[dict[str, Any]]:
    """Discover signal engines; optionally filter to one family path."""
    # dmr is hard-coded to poc_va_macdha — honor that as primary
    models = dmr.discover_models(only)
    if family != "poc_va_macdha":
        # future multi-family: filter model_dir parents
        models = [m for m in models if family in str(m["model_dir"])]
    return models


def pick_mode(model: dict[str, Any], track: str | None = None) -> str:
    if track == DataTrack.OPTIONS_SYNTHETIC.value or track == "options":
        if "options" in model.get("modes", []) or model.get("has_hunt"):
            return "options"
        return "options"
    if track == DataTrack.EQUITY_OHLCV.value or track == "equity":
        return "daily" if "daily" in model.get("modes", ["daily"]) else model["modes"][0]
    return dmr.pick_mode_for_screen(model)


def _finalize(row: dict[str, Any]) -> dict[str, Any]:
    row = apply_gates(row)
    row = enrich_scores(row, dd_hard=dd_hard_from_bar(), claim_min=claim_min_trades())
    return row


def prefer_force_1d(model: dict[str, Any], mode: str) -> bool:
    """Options always 1D. Equity keeps model interval when config says 1H/2H/4h."""
    if mode == "options":
        return True
    interval = str(model.get("interval") or "1D").upper()
    if interval in ("1H", "2H", "4H", "60", "120", "240"):
        return False
    cfg_path = Path(model["model_dir"]) / "config.json"
    if cfg_path.exists():
        try:
            import json as _json

            mc = _json.loads(cfg_path.read_text())
            iv = str(mc.get("interval") or "").upper()
            if iv in ("1H", "2H", "4H"):
                return False
        except Exception:
            pass
    return True


def run_one_cached(
    model: dict[str, Any],
    *,
    mode: str,
    codes: list[str],
    start: str,
    end: str,
    tag: str,
    cash: float,
    reuse: bool = True,
    use_content_cache: bool = True,
    force_1d: bool | None = None,
) -> dict[str, Any]:
    """Run or reuse one backtest; always attach track/claim/utility."""
    if force_1d is None:
        force_1d = prefer_force_1d(model, mode)
    commission = 0.001
    cfg_path = Path(model["model_dir"]) / "config.json"
    if cfg_path.exists():
        try:
            import json as _json

            mc = _json.loads(cfg_path.read_text())
            if mc.get("commission") is not None:
                commission = float(mc["commission"])
        except Exception:
            pass
    interval_label = "1D" if force_1d else str(model.get("interval") or "1D")
    key = cache_key(
        model,
        mode=mode,
        codes=codes,
        start=start,
        end=end,
        cash=cash,
        interval=interval_label,
        extra={"tag": tag, "commission": commission, "force_1d": force_1d},
    )

    if use_content_cache and reuse:
        hit = read_cached_metrics(key)
        if hit is not None:
            out = {
                "id": model["id"],
                "mode": mode,
                "tag": tag,
                "codes": codes,
                "start": start,
                "end": end,
                "cash": cash,
                "ret": float(hit.get("ret", 0)),
                "dd": float(hit.get("dd", 0)),
                "sharpe": float(hit.get("sharpe", 0)),
                "n": int(hit.get("n", 0)),
                "wr": float(hit.get("wr", 0)),
                "final": float(hit.get("final", 0)),
                "reused": True,
                "from_cache": True,
                "cache_key": key,
                "path": str(dmr.OUT / "runs" / model["id"] / f"{tag}__{mode}"),
            }
            if hit.get("error"):
                out["error"] = hit["error"]
            out = dmr.enrich_money(out, cash)
            return _finalize(out)

    # Delegate to dynamic_model_rank runner (disk reuse inside OUT/runs)
    row = dmr.run_one(
        model,
        mode=mode,
        codes=codes,
        start=start,
        end=end,
        tag=tag,
        force_1d=force_1d,
        reuse=reuse,
        cash=cash,
    )
    row["cache_key"] = key
    row["data_track"] = infer_track(mode, model["id"]).value
    if use_content_cache and not row.get("error"):
        write_cached_metrics(
            key,
            {
                "ret": row.get("ret"),
                "dd": row.get("dd"),
                "sharpe": row.get("sharpe"),
                "n": row.get("n"),
                "wr": row.get("wr"),
                "final": row.get("final"),
                "id": model["id"],
                "mode": mode,
                "start": start,
                "end": end,
                "cash": cash,
            },
            run_dir=ROOT / row["path"] if row.get("path") else None,
        )
    elif use_content_cache and row.get("error"):
        write_cached_metrics(
            key,
            {
                "error": row.get("error"),
                "ret": -9,
                "dd": -1,
                "sharpe": 0,
                "n": 0,
                "wr": 0,
                "final": 0,
            },
        )
    return _finalize(row)


def run_batch(
    models: list[dict[str, Any]],
    *,
    codes: list[str],
    start: str,
    end: str,
    tag: str,
    cash: float,
    track: str | None = None,
    reuse: bool = True,
    workers: int = 1,
    budget: int | None = None,
    on_each: Callable[[dict], None] | None = None,
) -> list[dict[str, Any]]:
    """Run models (optionally parallel). Stops after ``budget`` new non-cache runs if set."""
    todo = list(models)
    if budget is not None:
        todo = todo[: max(0, budget)]

    def _one(m: dict[str, Any]) -> dict[str, Any]:
        mode = pick_mode(m, track)
        r = run_one_cached(
            m,
            mode=mode,
            codes=codes,
            start=start,
            end=end,
            tag=tag,
            cash=cash,
            reuse=reuse,
            force_1d=prefer_force_1d(m, mode),
        )
        if on_each:
            on_each(r)
        return r

    rows: list[dict[str, Any]] = []
    if workers <= 1:
        for m in todo:
            rows.append(_one(m))
        return rows

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_one, m): m["id"] for m in todo}
        for fut in as_completed(futs):
            try:
                rows.append(fut.result())
            except Exception as e:  # noqa: BLE001
                mid = futs[fut]
                rows.append(
                    _finalize(
                        {
                            "id": mid,
                            "mode": "daily",
                            "tag": tag,
                            "error": str(e)[:200],
                            "ret": -9,
                            "dd": -1,
                            "sharpe": 0,
                            "n": 0,
                            "wr": 0,
                            "cash": cash,
                        }
                    )
                )
    # stable order by original model list
    by_id = {r["id"]: r for r in rows}
    return [by_id[m["id"]] for m in todo if m["id"] in by_id] + [
        r for r in rows if r["id"] not in {m["id"] for m in todo}
    ]


def rank_rows(rows: list[dict[str, Any]], key: str = "utility") -> list[dict[str, Any]]:
    ok = [r for r in rows if not r.get("error") and int(r.get("n") or 0) > 0]
    bad = [r for r in rows if r.get("error") or int(r.get("n") or 0) == 0]
    ok.sort(key=lambda x: float(x.get(key) or -99), reverse=True)
    return ok + bad


def filter_track(models: list[dict[str, Any]], track: str) -> list[dict[str, Any]]:
    """Filter discover list by preferred track."""
    out = []
    for m in models:
        modes = m.get("modes") or ["daily"]
        if track in (DataTrack.OPTIONS_SYNTHETIC.value, "options"):
            if "options" in modes or m.get("has_hunt") or any(
                h in m["id"].lower() for h in dmr.OPTS_NAME_HINTS
            ):
                out.append(m)
        elif track in (DataTrack.EQUITY_OHLCV.value, "equity"):
            # Prefer engines that can run daily; skip pure-options-only if they lack daily
            if "daily" in modes or not m.get("has_hunt"):
                out.append(m)
        else:
            out.append(m)
    return out


def bags_for_track(track: str) -> tuple[list[str], list[str]]:
    if track in (DataTrack.OPTIONS_SYNTHETIC.value, "options"):
        return OPTS_BAG8, OPTS_GROWTH
    return EQUITY_WINNER_BAG, EQUITY_CORE
