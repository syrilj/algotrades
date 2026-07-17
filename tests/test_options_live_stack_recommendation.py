"""Structural contract: best live high-conf/high-WR options *stack*.

Locks the frozen recommendation from analysis (not a new promotion):
  timing  → DESK_ROUTING high_wr_equity = v71_live_confidence (last_confidence)
  structure OOS engine → OPTIONS_WINNER = v35_softstruct_bag8 (soft-structure sizing)
  live path → live_plan + risk_manager OPTIONS_ATTACK + options_picker debit spreads

These tests drive real shipped artifacts and functions so a stale winner / routing
regression fails the suite.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models" / "poc_va_macdha"
TOOLS = ROOT / "tools"


def _load_json(path: Path) -> dict:
    assert path.is_file(), f"missing artifact: {path}"
    return json.loads(path.read_text())


def _import_tools_module(name: str):
    """Import a tools/*.py module without requiring package install.

    Registers the module in ``sys.modules`` before exec so ``@dataclass``
    and other introspection that looks up ``sys.modules[cls.__module__]`` work.
    """
    path = TOOLS / f"{name}.py"
    assert path.is_file(), f"missing module: {path}"
    mod_name = f"opts_live_{name}"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    # Ensure tools/ is importable for sibling imports inside the module.
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location(mod_name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_options_winner_is_v35_softstruct_bag8():
    ow = _load_json(MODELS / "OPTIONS_WINNER.json")
    assert ow["winner"] == "v35_softstruct_bag8"
    assert ow["stack"] == "options"
    champ = ow["champion_oos"]
    assert champ["model_dir"] == "v35_softstruct_bag8"
    assert champ["mean_oos_score"] == pytest.approx(0.1458, abs=1e-4)
    assert champ["defaults"]["use_soft_structure"] is True
    assert champ["defaults"]["struct_weak_mult"] == pytest.approx(0.55)
    assert champ["defaults"]["struct_good_mult"] == pytest.approx(1.15)
    bag = champ["defaults"]["bag"]
    assert "TSLA.US" in bag and "IONQ.US" in bag and len(bag) == 8

    full = ow["full_window_reference"]["v35_soft_bag8"]
    assert full["win_rate"] == pytest.approx(0.86, abs=0.02)
    assert full["trade_count"] == 28
    assert full["total_return"] == pytest.approx(0.73, abs=0.02)
    assert full["max_drawdown"] == pytest.approx(-0.0907, abs=0.01)

    killed = " ".join(ow.get("killed_this_loop") or [])
    assert "bag8" in killed.lower() or "overlay" in killed.lower() or "OOS" in killed


def test_v35_full_window_metrics_csv_matches_winner():
    csv_path = MODELS / "v35_softstruct_bag8" / "full_window_metrics.csv"
    assert csv_path.is_file()
    lines = csv_path.read_text().strip().splitlines()
    assert len(lines) >= 2
    # final_value,total_return,...,trade_count,win_rate,...
    cols = lines[0].split(",")
    row = lines[1].split(",")
    data = dict(zip(cols, row))
    assert float(data["total_return"]) == pytest.approx(0.729986, abs=1e-5)
    assert int(float(data["trade_count"])) == 28
    assert float(data["win_rate"]) == pytest.approx(0.8571, abs=1e-3)
    assert float(data["max_drawdown"]) == pytest.approx(-0.090701, abs=1e-5)
    assert float(data["sharpe"]) == pytest.approx(1.7847, abs=1e-3)


def test_v35_engine_has_soft_structure_sizing():
    eng_path = MODELS / "v35_softstruct_bag8" / "signal_engine.py"
    text = eng_path.read_text()
    assert "use_soft_structure" in text
    assert "struct_weak_mult" in text
    assert "struct_good_mult" in text
    hunt = _load_json(MODELS / "v35_softstruct_bag8" / "hunt_config.json")
    assert hunt.get("use_soft_structure") is True
    assert float(hunt["struct_weak_mult"]) == pytest.approx(0.55)
    assert float(hunt["struct_good_mult"]) == pytest.approx(1.15)


def test_desk_routing_high_wr_and_dual_sleeve():
    routing = _load_json(MODELS / "DESK_ROUTING.json")
    assert routing["high_wr_equity"] == "v71_live_confidence"
    assert routing["dual_sleeve_equity"] == "v72_dual_sleeve"
    assert routing["fallback_equity"] == "v39d_confluence"
    # Options OOS winner is not equity routing — but must not be invented here.
    assert "v35_softstruct_bag8" not in (routing.get("by_symbol") or {})


def test_v71_exposes_last_confidence_and_oos_wr():
    eng_path = MODELS / "v71_live_confidence" / "signal_engine.py"
    text = eng_path.read_text()
    assert "last_confidence" in text
    res = _load_json(MODELS / "v71_live_confidence" / "results.json")
    assert res.get("promoted") is True
    full = res["portfolio"]
    assert full["win_rate"] == pytest.approx(0.86, abs=0.01)
    assert full["trade_count"] == 50
    hold = res["holdout"]
    assert hold["win_rate"] == pytest.approx(0.769, abs=0.02)
    assert hold["trade_count"] == 26
    assert hold["total_return"] == pytest.approx(0.309, abs=0.02)


def test_v70_is_not_primary_live_high_wr_due_to_thin_holdout():
    """v70 has higher full WR but fails holdout n floor — not the live conf sleeve."""
    routing = _load_json(MODELS / "DESK_ROUTING.json")
    assert routing["high_wr_equity"] != "v70_high_confidence_wr"
    res = _load_json(MODELS / "v70_high_confidence_wr" / "results.json")
    # Full window can look great; live choice is still v71 per routing + holdout n.
    assert res["portfolio"]["win_rate"] >= 0.90
    # holdout n is not in results.json for v70; contract is documented in v71 MODEL.md
    # and DESK_ROUTING. Keep this assertion on routing identity.
    assert routing["high_wr_equity"] == "v71_live_confidence"


def test_options_picker_defaults_debit_spread_budget():
    op = _import_tools_module("options_picker")
    assert callable(op.propose)
    # Signature defaults: prefer_spread, 14–45 DTE, side long
    import inspect

    sig = inspect.signature(op.propose)
    assert sig.parameters["prefer_spread"].default is True
    assert sig.parameters["min_dte"].default == 14
    assert sig.parameters["max_dte"].default == 45
    assert sig.parameters["side"].default == "long"
    # Module doc / PREFERRED sniper names for $1k book
    assert "APLD" in op.PREFERRED or "IONQ" in op.PREFERRED


def test_risk_manager_options_attack_thresholds():
    rm = _import_tools_module("risk_manager")
    pol = rm._default_policy()
    opt = pol["options"]
    assert float(opt["min_confidence"]) == pytest.approx(0.72)
    assert float(opt["attack_confidence"]) == pytest.approx(0.82)
    assert opt["prefer_debit_spread"] is True
    assert int(opt["min_dte"]) == 14
    assert int(opt["max_dte"]) == 45
    assert int(opt["force_flat_dte"]) == 5

    # Drive plan_entry: high conf + affordable options → OPTIONS_ATTACK enter
    setup = rm.SetupSnapshot(
        symbol="IONQ",
        model_conf=0.90,
        vol_z=2.0,
        trend_ok=True,
        macro_ok=True,
        qqq_ok=True,
        options_affordable=True,
        liquidity_ok=True,
        side="long",
    )
    state = rm.PortfolioState(equity=1000.0, peak=1000.0)
    dec = rm.plan_entry(setup, state, pol)
    assert dec.mode == "OPTIONS_ATTACK"
    assert dec.action == "enter"
    assert dec.risk_pct > 0

    # Low conf → not OPTIONS_ATTACK enter
    setup_low = rm.SetupSnapshot(
        symbol="IONQ",
        model_conf=0.50,
        vol_z=0.2,
        trend_ok=True,
        macro_ok=True,
        qqq_ok=True,
        options_affordable=True,
        side="long",
    )
    dec_low = rm.plan_entry(setup_low, state, pol)
    assert not (dec_low.mode == "OPTIONS_ATTACK" and dec_low.action == "enter")


def test_live_plan_wires_options_picker_on_attack_path():
    lp_path = TOOLS / "live_plan.py"
    text = lp_path.read_text()
    assert "from options_picker import propose as options_propose" in text
    assert "OPTIONS_ATTACK" in text
    assert "attack_path" in text
    assert "proposal_only" in text
    # Confidence runtime is part of live gate (not invent new auto-trade)
    assert "evaluate_confidence" in text
    assert "plan_entry" in text


def test_trade_desk_reads_engine_last_confidence():
    td = (TOOLS / "trade_desk.py").read_text()
    assert "last_confidence" in td
    assert "engine_last_confidence" in td
    assert "v71" in td and "v72" in td


def test_kill_list_artifacts_exist_as_research_only():
    """Killed / hold models remain on disk but are not OPTIONS_WINNER."""
    ow = _load_json(MODELS / "OPTIONS_WINNER.json")
    assert ow["winner"] != "v32_soft_react_opts"
    assert ow["previous_options_default"] == "v34_bag6_opts"
    for mid in (
        "v34_bag6_opts",
        "v29_coldstart_opts",
        "v32_soft_react_opts",
        "v28_feedback_opts",
        "v22_opts_live",
    ):
        assert (MODELS / mid / "signal_engine.py").is_file() or (
            MODELS / mid
        ).is_dir()
    # Vol research modules must not be the options winner identity
    assert ow["winner"].startswith("v35")
