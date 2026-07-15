"""Constrained mutation menu — no free-form strategy invention.

Mutations live under runs/evolve_*/mutations/ as temporary model bundles.
Options: hunt_config patches. Equity: config/strategy overlays only.
"""
from __future__ import annotations

import ast
import json
import re
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

# Fixed menu — each is one change from a base winner/contender
MUTATION_MENU: list[dict[str, Any]] = [
    {
        "name": "opts_risk_tight",
        "applies": "options",
        "targets": ["hard_drawdown", "oos_degradation"],
        "hunt": {"risk_pct": 0.08, "halt_dd": 0.20, "flatten_dd": 0.30},
        "hypothesis": "Lower risk_pct + tighter DD halt to cut path risk.",
    },
    {
        "name": "opts_risk_wide",
        "applies": "options",
        "targets": ["no_trades", "thin_sample"],
        "hunt": {"risk_pct": 0.25, "halt_dd": 0.35, "flatten_dd": 0.50},
        "hypothesis": "Higher risk_pct for $1k bag capacity; accept more DD.",
    },
    {
        "name": "opts_dte_14",
        "applies": "options",
        "targets": ["negative_return", "weak_sharpe"],
        "hunt": {"dte_days": 14},
        "hypothesis": "Shorter DTE for faster theta/turn; fewer multi-week holds.",
    },
    {
        "name": "opts_dte_35",
        "applies": "options",
        "targets": ["negative_return", "unstable_windows"],
        "hunt": {"dte_days": 35},
        "hypothesis": "Longer DTE reduces theta bleed on swing holds.",
    },
    {
        "name": "opts_atm_only",
        "applies": "options",
        "targets": ["negative_return", "oos_degradation"],
        "hunt": {"otm_pct": 0.0},
        "hypothesis": "Force ATM strikes for cleaner delta vs OTM lottery.",
    },
    {
        "name": "opts_otm_3",
        "applies": "options",
        "targets": ["negative_return"],
        "hunt": {"otm_pct": 0.03},
        "hypothesis": "Slight OTM for cheaper premium on high-beta names.",
    },
    {
        "name": "equity_note_volz",
        "applies": "equity",
        "targets": ["weak_sharpe", "unstable_windows"],
        "strategy": {"mutate": "prefer_vol_z_meta", "vol_z_min": 1.0},
        "hypothesis": "Document vol_z meta preference (engines that read strategy note).",
    },
    {
        "name": "equity_commission_tight",
        "applies": "equity",
        "targets": ["oos_degradation"],
        "config": {"commission": 0.0015},
        "strategy": {"mutate": "higher_cost_stress"},
        "hypothesis": "Stress edge under higher commission (1.5 bps → 15 bps).",
    },
    {
        "name": "equity_commission_base",
        "applies": "equity",
        "config": {"commission": 0.001},
        "strategy": {"mutate": "base_cost"},
        "hypothesis": "Baseline commission re-copy for control arm.",
    },
    {
        "name": "equity_cash_1k_scale",
        "applies": "equity",
        "config": {"initial_cash": 1000},
        "strategy": {"mutate": "small_account_scale"},
        "hypothesis": "Small-account config path for $1k desk realism.",
    },
]


def _is_options_model(model: dict[str, Any]) -> bool:
    mid = model["id"].lower()
    return bool(model.get("has_hunt")) or "opts" in mid or "options" in mid


def spawn_mutations(
    base_models: list[dict[str, Any]],
    out_root: Path,
    *,
    max_mutations: int = 8,
    menu: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Copy base engines + apply menu patches. Returns discover-compatible dicts."""
    menu = menu or MUTATION_MENU
    out_root.mkdir(parents=True, exist_ok=True)
    spawned: list[dict[str, Any]] = []
    n = 0

    # Round-robin across parents.  The previous parent-first loop let the first
    # elite consume the entire mutation budget, which reduced diversity and
    # made later elites impossible to improve.
    for spec in menu:
        for base in base_models:
            if n >= max_mutations:
                break
            is_opts = _is_options_model(base)
            applies = spec.get("applies", "any")
            if applies == "options" and not is_opts:
                continue
            if applies == "equity" and is_opts:
                continue

            mut_id = f"mut_{base['id']}_{spec['name']}"
            dest = out_root / mut_id
            if dest.exists():
                shutil.rmtree(dest)
            dest.mkdir(parents=True)
            src: Path = base["src_dir"]
            model_dir: Path = base["model_dir"]

            # copy engine bundle
            for name in (
                "signal_engine.py",
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
                if not p.exists() and model_dir != src:
                    p = model_dir / name
                if p.exists():
                    shutil.copy2(p, dest / name)

            # base config
            cfg_path = model_dir / "config.json"
            cfg: dict[str, Any] = {}
            if cfg_path.exists():
                try:
                    cfg = json.loads(cfg_path.read_text())
                except Exception:
                    cfg = {}
            cfg.setdefault("strategy", {})
            if isinstance(cfg["strategy"], dict):
                cfg["strategy"]["model_version"] = mut_id
                cfg["strategy"]["parent"] = base["id"]
                cfg["strategy"]["mutation"] = spec["name"]
                if "strategy" in spec:
                    cfg["strategy"].update(spec["strategy"])
            if "config" in spec and isinstance(spec["config"], dict):
                cfg.update(spec["config"])
            if is_opts:
                cfg["engine"] = "options"
            else:
                cfg.setdefault("engine", "daily")
            (dest / "config.json").write_text(json.dumps(cfg, indent=2))

            # hunt patches
            if is_opts and "hunt" in spec:
                hunt_path = dest / "hunt_config.json"
                hc: dict[str, Any] = {}
                if hunt_path.exists():
                    try:
                        hc = json.loads(hunt_path.read_text())
                    except Exception:
                        hc = {}
                hc.update(spec["hunt"])
                # realism defaults from REALISTIC_LIMITS spirit
                hc.setdefault("contract_multiplier", 100)
                hc.setdefault("max_contracts", 5)
                hunt_path.write_text(json.dumps(hc, indent=2))

            (dest / "HYPOTHESIS.md").write_text(
                f"# {mut_id}\n\nParent: `{base['id']}`\n\n{spec.get('hypothesis','')}\n"
            )
            (dest / "MUTATION.json").write_text(
                json.dumps(
                    {
                        "id": mut_id,
                        "parent": base["id"],
                        "spec": spec,
                        "feedback_priority": spec.get("feedback_priority"),
                        "feedback_targets": spec.get("feedback_targets", spec.get("targets", [])),
                    },
                    indent=2,
                )
            )

            modes = ["options"] if is_opts else ["daily"]
            spawned.append(
                {
                    "id": mut_id,
                    "src_dir": dest,
                    "model_dir": dest,
                    "modes": modes,
                    "interval": "1D",
                    "has_hunt": (dest / "hunt_config.json").exists(),
                    "hunt_path": dest / "hunt_config.json" if (dest / "hunt_config.json").exists() else None,
                    "is_mutation": True,
                    "parent": base["id"],
                    "mutation_name": spec["name"],
                    "mutation_targets": spec.get("feedback_targets", spec.get("targets", [])),
                    "feedback_priority": spec.get("feedback_priority"),
                }
            )
            n += 1
        if n >= max_mutations:
            break

    return spawned


def promote_mutation_to_models(
    mut: dict[str, Any],
    *,
    family: str = "poc_va_macdha",
    version_name: str | None = None,
) -> Path:
    """Copy a winning mutation into models/<family>/ for permanence."""
    name = version_name or mut["id"].replace("mut_", "v_evolve_")
    dest = ROOT / "models" / family / name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(mut["model_dir"], dest)
    return dest


# Direction-equity mutation menu for evolve_direction_v1.
# Each spec is a runtime variant (no source copy needed) via config codes / extra_cfg.
DIRECTION_MUTATION_MENU: list[dict[str, Any]] = [
    {
        "name": "base",
        "codes": None,  # use parent
        "extra_cfg": {},
        "hypothesis": "Parent control arm.",
    },
    {
        "name": "add_arm",
        "targets": ["no_trades", "thin_sample"],
        "codes": ["TSLA.US", "MU.US", "SPY.US", "IONQ.US", "APLD.US", "XLP.US", "QQQ.US", "ARM.US"],
        "extra_cfg": {},
        "hypothesis": "Add ARM back to the bag.",
    },
    {
        "name": "drop_xlp",
        "targets": ["negative_return", "weak_sharpe", "unstable_windows"],
        "codes": ["TSLA.US", "MU.US", "SPY.US", "IONQ.US", "APLD.US", "QQQ.US"],
        "extra_cfg": {},
        "hypothesis": "Drop XLP (REGIME_FLAT) to concentrate capacity.",
    },
    {
        "name": "add_nvda_pltr",
        "targets": ["negative_return", "thin_sample"],
        "codes": ["TSLA.US", "MU.US", "SPY.US", "IONQ.US", "APLD.US", "XLP.US", "QQQ.US", "NVDA.US", "PLTR.US"],
        "extra_cfg": {},
        "hypothesis": "Expand to high-momentum tech names.",
    },
    {
        "name": "add_mstr_coin",
        "targets": ["negative_return", "thin_sample"],
        "codes": ["TSLA.US", "MU.US", "SPY.US", "IONQ.US", "APLD.US", "XLP.US", "QQQ.US", "MSTR.US", "COIN.US"],
        "extra_cfg": {},
        "hypothesis": "Add crypto-correlated high-beta exposure.",
    },
    {
        "name": "slip_stress_15",
        "targets": ["oos_degradation"],
        "codes": None,
        "extra_cfg": {"slippage_us": 0.0015},
        "hypothesis": "Stress slippage to 15 bps per side.",
    },
    {
        "name": "comm_tight",
        "codes": None,
        "extra_cfg": {"commission": 0.0005},
        "hypothesis": "Tighter commission for optimistic capacity test.",
    },
]


# Code-level mutation menu for v39b signal_engine.py.
# Each entry writes a temporary model bundle with a patched signal_engine.py.
CODE_MUTATION_MENU: list[dict[str, Any]] = [
    {
        "name": "unblock_arm",
        "targets": ["no_trades", "thin_sample"],
        "add_codes": ["ARM.US"],
        "code_mutation": {"op": "remove_from_set", "set_name": "TRADE_DROP", "symbol": "ARM.US"},
        "hypothesis": "Remove ARM from TRADE_DROP and let it trade.",
    },
    {
        "name": "allow_qqq",
        "targets": ["no_trades", "thin_sample"],
        "code_mutation": {"op": "remove_from_set", "set_name": "REGIME_FLAT", "symbol": "QQQ.US"},
        "hypothesis": "Allow QQQ to trade by removing it from REGIME_FLAT.",
    },
    {
        "name": "vwap_uptrend_tsla",
        "targets": ["negative_return", "weak_sharpe", "unstable_windows"],
        "code_mutation": {"op": "set_routing_flag", "symbol": "TSLA.US", "key": "require_vwap_uptrend", "value": True},
        "hypothesis": "Require VWAP uptrend for TSLA entries.",
    },
    {
        "name": "soft_confidence_tsla",
        "targets": ["no_trades", "thin_sample"],
        "code_mutation": [
            {"op": "set_routing_flag", "symbol": "TSLA.US", "key": "soft_confidence", "value": True},
            {"op": "set_routing_param", "symbol": "TSLA.US", "key": "min_confidence", "value": 0.55},
        ],
        "hypothesis": "Use soft confidence with lower threshold for TSLA.",
    },
    {
        "name": "tight_stop_all",
        "targets": ["hard_drawdown", "oos_degradation"],
        "code_mutation": {"op": "set_routing_param", "symbol": "__all__", "key": "stop_atr", "value": 1.0},
        "hypothesis": "Tighten hard stops to 1.0 ATR for all symbols.",
    },
    {
        "name": "risk_pct_down",
        "targets": ["hard_drawdown"],
        "code_mutation": {"op": "set_genome", "key": "risk_pct", "value": 0.10},
        "hypothesis": "Lower risk_pct to reduce position sizing.",
    },
    {
        "name": "struct_good_up",
        "targets": ["negative_return", "weak_sharpe"],
        "code_mutation": {"op": "set_genome", "key": "struct_good_mult", "value": 1.25},
        "hypothesis": "Boost struct_good multiplier for stronger structure.",
    },
]


COMBINED_MUTATION_MENU: list[dict[str, Any]] = DIRECTION_MUTATION_MENU + CODE_MUTATION_MENU


# Output directory used by tools.dynamic_model_rank (OUT/runs/<id>/).
DMR_OUT = ROOT / "runs" / "poc_va_dynamic_rank"


class SignalEngineMutator:
    """Patch literal _ROUTING / _GENOME / top-level sets in signal_engine.py."""

    def __init__(self, src: Path | str):
        self.text = src if isinstance(src, str) else Path(src).read_text()
        self._routing_match = re.search(r"^_ROUTING = (.*)$", self.text, re.MULTILINE)
        self._genome_match = re.search(r"^_GENOME = .*?}$", self.text, re.MULTILINE | re.DOTALL)
        if not self._routing_match or not self._genome_match:
            raise ValueError("signal_engine.py must define _ROUTING and _GENOME top-level assigns")
        self.routing: dict[str, Any] = ast.literal_eval(self._routing_match.group(1))
        self.genome: dict[str, Any] = ast.literal_eval(
            self._genome_match.group(0).split("=", 1)[1].strip()
        )

    def _write_routing(self) -> None:
        self.text = re.sub(
            r"^_ROUTING = .*$",
            lambda _m: f"_ROUTING = {repr(self.routing)}",
            self.text,
            flags=re.MULTILINE,
            count=1,
        )

    def _write_genome(self) -> None:
        self.text = re.sub(
            r"^_GENOME = .*?}$",
            lambda _m: f"_GENOME = {repr(self.genome)}",
            self.text,
            flags=re.MULTILINE | re.DOTALL,
            count=1,
        )

    def _symbols(self, symbol: str | None) -> list[str]:
        if symbol is None or symbol == "__all__":
            return list(self.routing.keys())
        return [symbol]

    def apply_mutation(self, spec: dict[str, Any]) -> dict[str, Any]:
        """Apply one mutation spec and return a summary."""
        op = spec["op"]
        summary: dict[str, Any] = {"op": op}

        if op == "set_routing_flag":
            for sym in self._symbols(spec.get("symbol")):
                old = bool(self.routing[sym][spec["key"]])
                self.routing[sym][spec["key"]] = bool(spec["value"])
                summary["symbol"] = spec.get("symbol", "__all__")
                summary["key"] = spec["key"]
                summary["old"] = old
                summary["new"] = spec["value"]
            self._write_routing()

        elif op == "set_routing_param":
            for sym in self._symbols(spec.get("symbol")):
                old = self.routing[sym].get(spec["key"])
                self.routing[sym][spec["key"]] = spec["value"]
                summary["symbol"] = spec.get("symbol", "__all__")
                summary["key"] = spec["key"]
                summary["old"] = old
                summary["new"] = spec["value"]
            self._write_routing()

        elif op == "scale_routing_param":
            scale = float(spec["scale"])
            for sym in self._symbols(spec.get("symbol")):
                old = self.routing[sym].get(spec["key"])
                if isinstance(old, bool):
                    new = bool(old)
                elif isinstance(old, (int, float)):
                    new = old * scale
                    if isinstance(old, int):
                        new = int(round(new))
                    else:
                        new = round(new, 4)
                else:
                    new = old
                self.routing[sym][spec["key"]] = new
                summary["symbol"] = spec.get("symbol", "__all__")
                summary["key"] = spec["key"]
                summary["old"] = old
                summary["new"] = new
            self._write_routing()

        elif op == "set_genome":
            old = self.genome[spec["key"]]
            self.genome[spec["key"]] = spec["value"]
            summary["key"] = spec["key"]
            summary["old"] = old
            summary["new"] = spec["value"]
            self._write_genome()

        elif op == "scale_genome":
            old = self.genome[spec["key"]]
            new = round(old * float(spec["scale"]), 4)
            self.genome[spec["key"]] = new
            summary["key"] = spec["key"]
            summary["old"] = old
            summary["new"] = new
            self._write_genome()

        elif op in ("remove_from_set", "add_to_set"):
            set_name = spec["set_name"]
            symbol = spec["symbol"]
            m = re.search(rf"^{set_name} = (.*)$", self.text, re.MULTILINE)
            if not m:
                raise ValueError(f"set {set_name} not found in signal_engine.py")
            items = set(ast.literal_eval(m.group(1)))
            old = sorted(items)
            if op == "remove_from_set":
                items.discard(symbol)
            else:
                items.add(symbol)
            new = sorted(items)
            self.text = re.sub(
                rf"^{set_name} = .*$",
                lambda _m: f"{set_name} = {repr(new)}",
                self.text,
                flags=re.MULTILINE,
                count=1,
            )
            summary["set_name"] = set_name
            summary["symbol"] = symbol
            summary["old"] = old
            summary["new"] = new

        else:
            raise ValueError(f"unknown mutation op: {op}")

        return summary

    def write(self, dest: Path) -> None:
        dest.write_text(self.text)


def apply_code_mutation(
    base_model_dir: Path,
    variant_id: str,
    mutation_spec: dict[str, Any] | list[dict[str, Any]],
    out_root: Path | None = None,
) -> Path:
    """Copy base model + patch signal_engine.py; return mutated model_dir."""
    dest = (out_root or DMR_OUT / "runs") / variant_id
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    # copy the minimal bundle needed to run
    for name in ("config.json", "meta_config.json", "meta_xgb_final.json", "signal_engine.py"):
        src = base_model_dir / name
        if src.exists():
            shutil.copy2(src, dest / name)

    mutator = SignalEngineMutator(dest / "signal_engine.py")
    specs = mutation_spec if isinstance(mutation_spec, list) else [mutation_spec]
    summaries = [mutator.apply_mutation(s) for s in specs]
    mutator.write(dest / "signal_engine.py")

    (dest / "MUTATION.json").write_text(
        json.dumps({"variant_id": variant_id, "parent": base_model_dir.name, "mutations": summaries}, indent=2)
    )
    return dest


def spawn_direction_variants(
    base_model: dict[str, Any],
    menu: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build runtime variant specs for direction-equity evolution.

    Supports code_mutation specs that create temporary model bundles.
    """
    menu = menu or COMBINED_MUTATION_MENU
    base_codes = base_model.get("codes") or []
    if not base_codes:
        cfg = base_model.get("model_dir") / "config.json" if base_model.get("model_dir") else None
        if cfg and cfg.exists():
            try:
                base_codes = json.loads(cfg.read_text()).get("codes", [])
            except Exception:
                pass
    if not base_codes:
        base_codes = ["TSLA.US", "MU.US", "SPY.US", "IONQ.US", "APLD.US", "XLP.US", "QQQ.US"]

    variants = []
    for spec in menu:
        codes = spec.get("codes") or base_codes
        if spec.get("add_codes"):
            codes = list(codes) + [c for c in spec["add_codes"] if c not in codes]
        vid = f"{base_model['id']}_{spec['name']}"

        model_dir = base_model["model_dir"]
        src_dir = base_model["src_dir"]
        if spec.get("code_mutation"):
            model_dir = apply_code_mutation(Path(model_dir), vid, spec["code_mutation"])
            src_dir = model_dir

        variants.append(
            {
                "id": vid,
                "parent": base_model["id"],
                "model_dir": model_dir,
                "src_dir": src_dir,
                "codes": list(codes),
                "extra_cfg": dict(spec.get("extra_cfg", {})),
                "mutations": [
                    {
                        "name": spec["name"],
                        "hypothesis": spec.get("hypothesis", ""),
                        "targets": spec.get("feedback_targets", spec.get("targets", [])),
                        "feedback_priority": spec.get("feedback_priority"),
                    }
                ],
                "mutation_name": spec["name"],
                "mutation_targets": spec.get("feedback_targets", spec.get("targets", [])),
                "feedback_priority": spec.get("feedback_priority"),
                "interval": "1H",
            }
        )
    return variants
