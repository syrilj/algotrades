"""YAML config loading and schema validation."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

import yaml
from jsonschema import Draft202012Validator

from quantmodel.hashing import hash_config

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA_PATH = PACKAGE_ROOT / "configs" / "experiment_schema.json"
DEFAULT_CONFIG_DIR = PACKAGE_ROOT / "configs"


class ConfigError(ValueError):
    """Raised when configuration is invalid."""


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ConfigError(f"Config root must be a mapping: {path}")
    return data


def _load_schema(path: Path) -> dict[str, Any]:
    import json

    if not path.exists():
        raise ConfigError(f"Schema file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def validate_config(
    config: Mapping[str, Any],
    schema_path: Path | None = None,
) -> list[str]:
    schema = _load_schema(schema_path or DEFAULT_SCHEMA_PATH)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(dict(config)), key=lambda e: list(e.path))
    messages: list[str] = []
    for err in errors:
        path = ".".join(str(p) for p in err.path) or "<root>"
        messages.append(f"{path}: {err.message}")
    # Semantic checks beyond schema
    risk = config.get("risk", {})
    if isinstance(risk, dict):
        ks = risk.get("kill_switch_drawdown")
        resume = risk.get("resume_drawdown")
        if ks is not None and resume is not None and resume < ks:
            messages.append(
                "risk.resume_drawdown must be greater than (less severe than) "
                "risk.kill_switch_drawdown"
            )
    return messages


def load_config(
    path: str | Path,
    *,
    schema_path: str | Path | None = None,
    validate: bool = True,
) -> dict[str, Any]:
    cfg_path = Path(path)
    if not cfg_path.is_absolute() and not cfg_path.exists():
        candidate = DEFAULT_CONFIG_DIR / cfg_path
        if candidate.exists():
            cfg_path = candidate
    config = _load_yaml(cfg_path)
    if validate:
        schema = Path(schema_path) if schema_path else DEFAULT_SCHEMA_PATH
        errors = validate_config(config, schema)
        if errors:
            joined = "\n  - ".join(errors)
            raise ConfigError(f"Invalid configuration ({cfg_path}):\n  - {joined}")
    config = deepcopy(config)
    config["_meta"] = {
        "config_path": str(cfg_path.resolve()),
        "config_hash": hash_config({k: v for k, v in config.items() if k != "_meta"}),
    }
    return config


def resolve_path_relative_to_config(config: Mapping[str, Any], relative: str) -> Path:
    """Resolve a path relative to the config file directory, then package, then cwd."""
    p = Path(relative)
    if p.is_absolute() and p.exists():
        return p
    meta = config.get("_meta", {})
    cfg_path = meta.get("config_path")
    candidates: list[Path] = []
    if cfg_path:
        candidates.append(Path(cfg_path).parent / relative)
    candidates.append(PACKAGE_ROOT / relative)
    candidates.append(PACKAGE_ROOT.parent / relative.lstrip("./"))
    candidates.append(Path.cwd() / relative)
    # common monorepo case: quantmodel/configs -> ../data_cache
    candidates.append(PACKAGE_ROOT.parent / "data_cache")
    for c in candidates:
        if c.exists():
            return c.resolve()
    return (PACKAGE_ROOT / relative).resolve()


def get_cache_root(config: Mapping[str, Any]) -> Path:
    rel = config.get("data", {}).get("cache_root", "../data_cache")
    return resolve_path_relative_to_config(config, rel)
