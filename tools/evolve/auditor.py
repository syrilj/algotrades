"""Independent auditor model — reviews other models for overfit / bad practice / cheating.

Does not generate trading signals. Verdicts: PASS | WARN | FAIL | BLOCK.
Used after train epochs and on demand via ``evolve_pipeline.py audit``.
"""
from __future__ import annotations

import ast
import json
import math
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PASS_BAR_PATH = ROOT / "models" / "_shared" / "PASS_BAR.json"
DEFAULT_AUDIT_DIR = ROOT / "runs" / "evolve_audits"

# Severity ranks
_SEV = {"info": 0, "warn": 1, "fail": 2, "block": 3}


@dataclass
class Finding:
    code: str
    severity: str  # info | warn | fail | block
    title: str
    detail: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditReport:
    target: str
    verdict: str  # PASS | WARN | FAIL | BLOCK
    score: float  # 0–100 integrity score
    findings: list[Finding] = field(default_factory=list)
    metrics_snapshot: dict[str, Any] = field(default_factory=dict)
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    auditor: str = "evolve_auditor_v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "verdict": self.verdict,
            "score": self.score,
            "findings": [asdict(f) for f in self.findings],
            "metrics_snapshot": self.metrics_snapshot,
            "ts": self.ts,
            "auditor": self.auditor,
            "may_promote": self.verdict in ("PASS", "WARN"),
            "blocks_train_accept": self.verdict in ("FAIL", "BLOCK"),
        }


def _load_pass_bar() -> dict[str, Any]:
    if PASS_BAR_PATH.exists():
        return json.loads(PASS_BAR_PATH.read_text())
    return {"gates": {"min_trades": 40, "max_drawdown_max_abs": 0.25, "sharpe_min": 0.5}}


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
        return default if v != v else v
    except (TypeError, ValueError):
        return default


def _extract_metrics(obj: dict[str, Any] | None) -> dict[str, Any]:
    if not obj:
        return {}
    if "portfolio" in obj and isinstance(obj["portfolio"], dict):
        p = obj["portfolio"]
        return {
            "ret": _safe_float(p.get("total_return")),
            "sharpe": _safe_float(p.get("sharpe")),
            "dd": abs(_safe_float(p.get("max_drawdown"))),
            "n": int(_safe_float(p.get("trade_count"))),
            "wr": _safe_float(p.get("win_rate")),
            "pf": _safe_float(p.get("profit_factor")) if p.get("profit_factor") is not None else None,
            "expectancy": p.get("expectancy_after_costs", p.get("expectancy")),
        }
    return {
        "ret": _safe_float(obj.get("ret", obj.get("total_return"))),
        "sharpe": _safe_float(obj.get("sharpe")),
        "dd": abs(_safe_float(obj.get("dd", obj.get("max_drawdown")))),
        "n": int(_safe_float(obj.get("n", obj.get("trade_count")))),
        "wr": _safe_float(obj.get("wr", obj.get("win_rate"))),
        "pf": (
            _safe_float(obj.get("pf", obj.get("profit_factor")))
            if obj.get("pf", obj.get("profit_factor")) is not None
            else None
        ),
        "expectancy": obj.get("expectancy_after_costs", obj.get("expectancy")),
        "u_train": obj.get("u_train"),
        "u_oos": obj.get("u_oos"),
        "gap": obj.get("gap"),
        "objective": obj.get("objective"),
    }


# ── Source code static audit ─────────────────────────────────────────────────

_FORBIDDEN_SOURCE = [
    (r"from\s+sklearn\.model_selection\s+import\s+.*KFold", "random_kfold_import", "block",
     "Random/KFold on time series is forbidden (PASS_BAR / ANTI_OVERFIT)"),
    (r"KFold\s*\(", "random_kfold_use", "block", "KFold() detected — chronological splits only"),
    (r"train_test_split\s*\(", "random_split", "fail",
     "train_test_split often shuffles time — use chronological lock"),
    (r"shuffle\s*=\s*True", "shuffle_true", "fail", "shuffle=True on time series is a leak risk"),
    (r"predict.*next.*close|next_close", "predict_next_close", "warn",
     "Predict-next-close as primary is forbidden by PLAYBOOK (meta OK)"),
]

_LOOKAHEAD_PATTERNS = [
    (r"\.shift\s*\(\s*-", "negative_shift", "fail",
     "shift(-n) is look-ahead (uses future bars)"),
    (r"bfill\s*\(|\.bfill\s*\(", "bfill_use", "warn",
     "bfill can leak future values into the past"),
]


def audit_source(engine_path: Path) -> list[Finding]:
    findings: list[Finding] = []
    if not engine_path.exists():
        findings.append(Finding(
            "missing_engine", "fail", "No signal_engine.py",
            f"Missing {engine_path}", {"path": str(engine_path)},
        ))
        return findings

    text = engine_path.read_text(encoding="utf-8", errors="ignore")

    for pat, code, sev, msg in _FORBIDDEN_SOURCE:
        if re.search(pat, text, re.I):
            findings.append(Finding(code, sev, "Forbidden practice in source", msg, {"pattern": pat}))

    for pat, code, sev, msg in _LOOKAHEAD_PATTERNS:
        if re.search(pat, text):
            findings.append(Finding(code, sev, "Possible look-ahead", msg, {"pattern": pat}))

    # AST: top-level executable beyond literals (cheat/sandbox bypass smell)
    try:
        tree = ast.parse(text)
        bad_top = []
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                continue
            if isinstance(node, ast.Assign) and isinstance(node.value, (ast.Constant, ast.Dict, ast.List, ast.Tuple)):
                continue
            if isinstance(node, ast.AnnAssign) and (
                node.value is None or isinstance(node.value, (ast.Constant, ast.Dict, ast.List))
            ):
                continue
            bad_top.append(type(node).__name__)
        if bad_top:
            findings.append(Finding(
                "executable_toplevel", "warn", "Non-literal top-level code",
                "Runner sandbox expects literal-only top-level; may be intentional but review",
                {"nodes": bad_top[:10]},
            ))
    except SyntaxError as e:
        findings.append(Finding("syntax_error", "block", "Engine syntax error", str(e), {}))

    # Primary ML side smell: LSTM/Transformer as main path
    if re.search(r"\b(LSTM|Transformer|GPT|ChatCompletion)\b", text) and re.search(
        r"generate\s*\(", text
    ):
        if "meta" not in engine_path.parent.name.lower():
            findings.append(Finding(
                "heavy_ml_primary", "warn", "Heavy ML in engine",
                "PLAYBOOK: do not replace primary SIDE with raw price ML without research",
                {},
            ))

    return findings


# ── Metrics / overfit audit ──────────────────────────────────────────────────


def audit_metrics(
    train: dict[str, Any] | None,
    oos: dict[str, Any] | None,
    *,
    claim_level: str | None = None,
    data_track: str | None = None,
    evaluation_label: str = "OOS",
) -> list[Finding]:
    findings: list[Finding] = []
    bar = _load_pass_bar()
    gates = bar.get("gates") or {}
    min_n = int(gates.get("min_trades", 40))
    max_dd = float(gates.get("max_drawdown_max_abs", 0.25))

    tm = _extract_metrics(train)
    om = _extract_metrics(oos) if oos else {}

    n = int(om.get("n") or tm.get("n") or 0)
    wr = float(om.get("wr") or tm.get("wr") or 0)
    dd = float(om.get("dd") or tm.get("dd") or 0)
    ret = float(om.get("ret") or tm.get("ret") or 0)
    sharpe = float(om.get("sharpe") or tm.get("sharpe") or 0)

    # Thin sample vanity
    if n > 0 and n < 12:
        findings.append(Finding(
            "thin_sample", "fail", "Too few trades",
            f"n={n} < 12 — cannot claim edge (THIN)",
            {"n": n},
        ))
    elif n < min_n:
        findings.append(Finding(
            "below_claim_n", "warn", "Below CLAIM trade count",
            f"n={n} < PASS_BAR min_trades={min_n}",
            {"n": n, "min_trades": min_n},
        ))

    # Vanity WR
    if wr >= 0.90 and n < 20:
        findings.append(Finding(
            "vanity_wr", "fail", "Vanity win rate",
            f"WR={wr:.0%} with n={n} — classic overfit / noise spike",
            {"wr": wr, "n": n},
        ))
    elif wr >= 0.85 and n < 40:
        findings.append(Finding(
            "high_wr_small_n", "warn", "High WR, small n",
            f"WR={wr:.0%} n={n} — treat as research only",
            {"wr": wr, "n": n},
        ))

    # Hard DD
    if dd >= max_dd:
        findings.append(Finding(
            "hard_drawdown", "fail", "Max DD exceeds PASS_BAR",
            f"|DD|={dd:.1%} >= {max_dd:.0%}",
            {"dd": dd, "limit": max_dd},
        ))

    # Train vs evaluation-window collapse. Train-loop callers label this as
    # validation; final results.json holdouts use OOS/holdout terminology.
    if tm and om and tm.get("n") and om.get("n"):
        tr_ret = float(tm.get("ret") or 0)
        oos_ret = float(om.get("ret") or 0)
        tr_wr = float(tm.get("wr") or 0)
        oos_wr = float(om.get("wr") or 0)
        if tr_ret > 0.1 and oos_ret <= 0:
            findings.append(Finding(
                "evaluation_ret_flip", "fail", f"{evaluation_label} return flip",
                f"Train ret={tr_ret:.1%} but {evaluation_label} ret={oos_ret:.1%} — overfit / regime break",
                {"train_ret": tr_ret, "oos_ret": oos_ret},
            ))
        if tr_wr - oos_wr > 0.15 and int(om.get("n") or 0) >= 5:
            findings.append(Finding(
                "evaluation_wr_collapse", "fail", f"{evaluation_label} win-rate collapse",
                f"Train WR={tr_wr:.0%} → {evaluation_label} WR={oos_wr:.0%} (>{15}pp drop)",
                {"train_wr": tr_wr, "oos_wr": oos_wr},
            ))
        # Train/OOS utility gap — long train windows often score higher than short OOS.
        # Only FAIL when OOS is also bad (collapse). Otherwise WARN.
        u_tr = tm.get("u_train")
        u_oos = om.get("u_oos") or om.get("utility")
        if u_tr is not None and u_oos is not None:
            gap = float(u_tr) - float(u_oos)
            oos_bad = float(om.get("ret") or 0) <= 0 or float(u_oos) <= 0
            if gap > 2.0 and oos_bad:
                findings.append(Finding(
                    "utility_gap", "fail", "Train≫OOS and OOS weak",
                    f"u_train={float(u_tr):.2f} u_eval={float(u_oos):.2f} gap={gap:.2f} {evaluation_label} not viable",
                    {"gap": gap, "u_oos": float(u_oos)},
                ))
            elif gap > 2.0:
                findings.append(Finding(
                    "utility_gap_warn", "warn", "Large train/OOS utility gap",
                    f"gap={gap:.2f} (common when train window ≫ OOS) — OK if OOS still positive",
                    {"gap": gap},
                ))
            elif gap > 1.0:
                findings.append(Finding(
                    "utility_gap_mild", "warn", "Elevated train/OOS gap",
                    f"gap={gap:.2f} — monitor generalization",
                    {"gap": gap},
                ))

    # Miracle returns (cheat / synthetic fantasy)
    if data_track and "options" in data_track and ret > 5.0 and n < 30:
        findings.append(Finding(
            "options_fantasy", "fail", "Unrealistic options return",
            f"ret={ret:.0%} n={n} on synthetic BS — do not promote",
            {"ret": ret, "n": n, "track": data_track},
        ))
    if ret > 20.0 and n < 50:
        findings.append(Finding(
            "miracle_return", "block", "Miracle return / possible leak",
            f"ret={ret:.0%} with n={n} — investigate look-ahead or data bug",
            {"ret": ret, "n": n},
        ))

    # Claiming CLAIM without bars
    if claim_level == "CLAIM" and n < min_n:
        findings.append(Finding(
            "false_claim", "block", "CLAIM without min trades",
            "Claim level CLAIM is invalid under PASS_BAR",
            {"claim_level": claim_level, "n": n},
        ))

    if data_track == "gex_live_only":
        findings.append(Finding(
            "gex_no_history", "block", "GEX cannot be backtest-claimed",
            "No historical OI — live meta only",
            {},
        ))

    if data_track and "options" in str(data_track) and claim_level == "CLAIM":
        findings.append(Finding(
            "options_auto_claim", "block", "Options cannot auto-CLAIM",
            "Synthetic pricing → max RESEARCH",
            {"data_track": data_track},
        ))

    # Zero sharpe with huge ret
    if ret > 0.5 and abs(sharpe) < 0.05 and n > 5:
        findings.append(Finding(
            "ret_sharpe_mismatch", "warn", "Return without Sharpe",
            "High return + near-zero Sharpe — path/risk oddity",
            {"ret": ret, "sharpe": sharpe},
        ))

    return findings


def audit_brain_history(history: list[dict[str, Any]]) -> list[Finding]:
    """Detect train-loop cheating: accept on train only, no OOS, etc."""
    findings: list[Finding] = []
    if not history:
        return findings
    accepts = [h for h in history if h.get("accepted")]
    for h in accepts[-5:]:
        if h.get("u_oos") is not None and h.get("u_train") is not None:
            if float(h["u_train"]) > 0 and float(h["u_oos"]) <= 0:
                findings.append(Finding(
                    "accepted_oos_negative", "block", "Accepted genome with bad OOS",
                    f"epoch {h.get('epoch')}: accepted despite u_oos={h['u_oos']}",
                    h,
                ))
        n = h.get("oos_n")
        if n is not None and int(n) < 5 and h.get("accepted"):
            findings.append(Finding(
                "accepted_thin_oos", "fail", "Accepted on thin OOS",
                f"epoch {h.get('epoch')} oos_n={n}",
                {"epoch": h.get("epoch"), "n": n},
            ))
    # Only train window ever used
    if history and all(h.get("event") != "seed" and h.get("u_oos") is None for h in history if h.get("epoch")):
        findings.append(Finding(
            "no_oos_in_history", "block", "No OOS scores in train history",
            "Train loop must score pure holdout",
            {},
        ))
    return findings


def _verdict_and_score(findings: list[Finding]) -> tuple[str, float]:
    max_sev = 0
    penalty = 0
    for f in findings:
        max_sev = max(max_sev, _SEV.get(f.severity, 0))
        penalty += {"info": 2, "warn": 8, "fail": 20, "block": 40}.get(f.severity, 5)
    score = max(0.0, 100.0 - penalty)
    if max_sev >= 3:
        return "BLOCK", score
    if max_sev >= 2:
        return "FAIL", score
    if max_sev >= 1:
        return "WARN", score
    return "PASS", min(100.0, score if findings else 100.0)


def audit_model(
    *,
    model_id: str,
    model_dir: Path | None = None,
    train_metrics: dict[str, Any] | None = None,
    oos_metrics: dict[str, Any] | None = None,
    claim_level: str | None = None,
    data_track: str | None = None,
    brain_history: list[dict[str, Any]] | None = None,
    results_json: Path | None = None,
    evaluation_label: str = "OOS holdout",
) -> AuditReport:
    findings: list[Finding] = []

    # Resolve paths
    mdir = model_dir
    if mdir is None:
        cand = ROOT / "models" / "poc_va_macdha" / model_id
        if cand.exists():
            mdir = cand

    engine = None
    if mdir:
        engine = mdir / "signal_engine.py"
        if not engine.exists() and (mdir / "code" / "signal_engine.py").exists():
            engine = mdir / "code" / "signal_engine.py"
        if engine and engine.exists():
            findings.extend(audit_source(engine))

    metrics_from_file: dict[str, Any] | None = None
    results_source = results_json or ((mdir / "results.json") if mdir else None)
    if results_source and results_source.exists():
        try:
            loaded = json.loads(results_source.read_text())
            if not isinstance(loaded, dict):
                findings.append(Finding(
                    "malformed_results_json", "fail", "Malformed results.json",
                    "Top-level JSON must be an object", {"path": str(results_source)},
                ))
            else:
                metrics_from_file = loaded
        except Exception as exc:
            findings.append(Finding(
                "bad_results_json", "fail", "Unreadable results.json", str(exc),
                {"path": str(results_source)},
            ))
    elif results_json is not None:
        findings.append(Finding(
            "missing_results_json", "fail", "Missing results.json",
            "Cannot verify a final holdout without the requested results artifact",
            {"path": str(results_json)},
        ))

    if metrics_from_file is not None:
        holdout = metrics_from_file.get("holdout", metrics_from_file.get("oos"))
        if holdout is None:
            findings.append(Finding(
                "missing_holdout", "fail", "Missing holdout metrics",
                "results.json must contain a holdout (or legacy oos) object for an OOS claim",
                {"path": str(results_source)},
            ))
        elif not isinstance(holdout, dict):
            findings.append(Finding(
                "malformed_holdout", "fail", "Malformed holdout metrics",
                "holdout must be a JSON object", {"type": type(holdout).__name__},
            ))
        else:
            required_aliases = {
                "return": ("total_return", "ret"),
                "drawdown": ("max_drawdown", "dd"),
                "sharpe": ("sharpe",),
                "trade_count": ("trade_count", "n"),
                "win_rate": ("win_rate", "wr"),
            }
            missing = [
                name for name, aliases in required_aliases.items()
                if not any(k in holdout and holdout[k] is not None for k in aliases)
            ]
            if missing:
                findings.append(Finding(
                    "incomplete_holdout", "fail", "Incomplete holdout metrics",
                    f"holdout missing required metrics: {', '.join(missing)}",
                    {"missing": missing},
                ))
            invalid: list[str] = []
            for name, aliases in required_aliases.items():
                values = [holdout[k] for k in aliases if k in holdout and holdout[k] is not None]
                if not values:
                    continue
                try:
                    if not math.isfinite(float(values[0])):
                        invalid.append(name)
                except (TypeError, ValueError):
                    invalid.append(name)
            if invalid:
                findings.append(Finding(
                    "malformed_holdout_metrics", "fail", "Malformed holdout metric values",
                    f"holdout metrics must be finite numbers: {', '.join(invalid)}",
                    {"invalid": invalid},
                ))
            if oos_metrics is None:
                oos_metrics = holdout
        if train_metrics is None:
            portfolio = metrics_from_file.get("portfolio")
            train_metrics = portfolio if isinstance(portfolio, dict) else metrics_from_file

    if oos_metrics is None and train_metrics:
        nested_eval = train_metrics.get("holdout", train_metrics.get("oos"))
        if isinstance(nested_eval, dict):
            oos_metrics = nested_eval

    findings.extend(
        audit_metrics(
            train_metrics,
            oos_metrics or train_metrics,
            claim_level=claim_level,
            data_track=data_track,
            evaluation_label=evaluation_label,
        )
    )

    if brain_history:
        findings.extend(audit_brain_history(brain_history))

    snap = _extract_metrics(oos_metrics or train_metrics)
    verdict, score = _verdict_and_score(findings)
    if not findings:
        findings.append(Finding(
            "clean", "info", "No red flags",
            "Static + metrics checks clear under current rules",
            {},
        ))
        verdict, score = "PASS", 100.0

    return AuditReport(
        target=model_id,
        verdict=verdict,
        score=score,
        findings=findings,
        metrics_snapshot=snap,
    )


def audit_train_epoch(
    *,
    candidate_id: str,
    candidate_dir: Path,
    eval_result: dict[str, Any],
    data_track: str,
) -> AuditReport:
    """Gate a train-loop accept: call before promoting genome."""
    train = eval_result.get("train") or {}
    validation = eval_result.get("validation") or eval_result.get("oos") or {}
    # attach train utility fields for gap checks
    train = {
        **train,
        "u_train": eval_result.get("u_train"),
        "n": train.get("n"),
        "ret": train.get("ret"),
        "wr": train.get("wr"),
        "dd": train.get("dd"),
        "sharpe": train.get("sharpe"),
    }
    validation = {
        **validation,
        "u_oos": eval_result.get("u_validation", eval_result.get("u_oos")),
        "utility": eval_result.get("u_validation", eval_result.get("u_oos")),
        "n": validation.get("n"),
        "ret": validation.get("ret"),
        "wr": validation.get("wr"),
        "dd": validation.get("dd"),
        "sharpe": validation.get("sharpe"),
    }
    return audit_model(
        model_id=candidate_id,
        model_dir=candidate_dir,
        train_metrics=train,
        oos_metrics=validation,
        data_track=data_track,
        claim_level=str(validation.get("claim_level") or train.get("claim_level") or ""),
        evaluation_label="validation",
    )


def write_audit(report: AuditReport, out_dir: Path | None = None) -> Path:
    out = out_dir or DEFAULT_AUDIT_DIR
    out.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w.\-]+", "_", report.target)[:80]
    path = out / f"audit_{safe}_{report.ts[:19].replace(':', '')}.json"
    path.write_text(json.dumps(report.to_dict(), indent=2))
    # also latest pointer per target
    (out / f"LATEST_{safe}.json").write_text(json.dumps(report.to_dict(), indent=2))
    md = [
        f"# Audit: `{report.target}`",
        "",
        f"**Verdict: {report.verdict}** · integrity score {report.score:.0f}/100",
        f"Auditor: {report.auditor} · {report.ts}",
        "",
        "## Findings",
        "",
    ]
    for f in report.findings:
        md.append(f"- **[{f.severity.upper()}]** `{f.code}` — {f.title}: {f.detail}")
    md.append("")
    (out / f"LATEST_{safe}.md").write_text("\n".join(md))
    return path


def audit_many(model_ids: list[str], family: str = "poc_va_macdha") -> list[AuditReport]:
    reports = []
    for mid in model_ids:
        mdir = ROOT / "models" / family / mid
        reports.append(
            audit_model(
                model_id=mid,
                model_dir=mdir if mdir.exists() else None,
                results_json=(mdir / "results.json") if mdir.exists() else None,
            )
        )
    return reports
