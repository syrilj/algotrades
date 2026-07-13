"""Constrained mutation menu — no free-form strategy invention.

Mutations live under runs/evolve_*/mutations/ as temporary model bundles.
Options: hunt_config patches. Equity: config/strategy overlays only.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

# Fixed menu — each is one change from a base winner/contender
MUTATION_MENU: list[dict[str, Any]] = [
    {
        "name": "opts_risk_tight",
        "applies": "options",
        "hunt": {"risk_pct": 0.08, "halt_dd": 0.20, "flatten_dd": 0.30},
        "hypothesis": "Lower risk_pct + tighter DD halt to cut path risk.",
    },
    {
        "name": "opts_risk_wide",
        "applies": "options",
        "hunt": {"risk_pct": 0.25, "halt_dd": 0.35, "flatten_dd": 0.50},
        "hypothesis": "Higher risk_pct for $1k bag capacity; accept more DD.",
    },
    {
        "name": "opts_dte_14",
        "applies": "options",
        "hunt": {"dte_days": 14},
        "hypothesis": "Shorter DTE for faster theta/turn; fewer multi-week holds.",
    },
    {
        "name": "opts_dte_35",
        "applies": "options",
        "hunt": {"dte_days": 35},
        "hypothesis": "Longer DTE reduces theta bleed on swing holds.",
    },
    {
        "name": "opts_atm_only",
        "applies": "options",
        "hunt": {"otm_pct": 0.0},
        "hypothesis": "Force ATM strikes for cleaner delta vs OTM lottery.",
    },
    {
        "name": "opts_otm_3",
        "applies": "options",
        "hunt": {"otm_pct": 0.03},
        "hypothesis": "Slight OTM for cheaper premium on high-beta names.",
    },
    {
        "name": "equity_note_volz",
        "applies": "equity",
        "strategy": {"mutate": "prefer_vol_z_meta", "vol_z_min": 1.0},
        "hypothesis": "Document vol_z meta preference (engines that read strategy note).",
    },
    {
        "name": "equity_commission_tight",
        "applies": "equity",
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

    for base in base_models:
        is_opts = _is_options_model(base)
        for spec in menu:
            if n >= max_mutations:
                break
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
        "codes": ["TSLA.US", "MU.US", "SPY.US", "IONQ.US", "APLD.US", "XLP.US", "QQQ.US", "ARM.US"],
        "extra_cfg": {},
        "hypothesis": "Add ARM back to the bag.",
    },
    {
        "name": "drop_xlp",
        "codes": ["TSLA.US", "MU.US", "SPY.US", "IONQ.US", "APLD.US", "QQQ.US"],
        "extra_cfg": {},
        "hypothesis": "Drop XLP (REGIME_FLAT) to concentrate capacity.",
    },
    {
        "name": "add_nvda_pltr",
        "codes": ["TSLA.US", "MU.US", "SPY.US", "IONQ.US", "APLD.US", "XLP.US", "QQQ.US", "NVDA.US", "PLTR.US"],
        "extra_cfg": {},
        "hypothesis": "Expand to high-momentum tech names.",
    },
    {
        "name": "add_mstr_coin",
        "codes": ["TSLA.US", "MU.US", "SPY.US", "IONQ.US", "APLD.US", "XLP.US", "QQQ.US", "MSTR.US", "COIN.US"],
        "extra_cfg": {},
        "hypothesis": "Add crypto-correlated high-beta exposure.",
    },
    {
        "name": "slip_stress_15",
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


def spawn_direction_variants(
    base_model: dict[str, Any],
    menu: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build runtime variant specs for direction-equity evolution."""
    menu = menu or DIRECTION_MUTATION_MENU
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
        vid = f"{base_model['id']}_{spec['name']}"
        variants.append(
            {
                "id": vid,
                "parent": base_model["id"],
                "model_dir": base_model["model_dir"],
                "src_dir": base_model["src_dir"],
                "codes": list(codes),
                "extra_cfg": dict(spec.get("extra_cfg", {})),
                "mutations": [{"name": spec["name"], "hypothesis": spec.get("hypothesis", "")}],
                "interval": "1H",
            }
        )
    return variants
