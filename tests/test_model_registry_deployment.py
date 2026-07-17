import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import model_registry as registry  # noqa: E402


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _setup(monkeypatch, tmp_path: Path):
    models = tmp_path / "models"
    active = models / "v72_dual_sleeve"
    fallback = models / "v39d_confluence"
    active.mkdir(parents=True)
    fallback.mkdir(parents=True)
    (active / "signal_engine.py").write_text("ACTIVE = True\n")
    (fallback / "signal_engine.py").write_text("FALLBACK = True\n")
    manifest = models / "DEPLOYMENT_MANIFEST.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "active": {
                    "equity_model": "v72_dual_sleeve",
                    "bundle": {"signal_engine_sha256": _sha(active / "signal_engine.py")},
                },
                "rollback_model": "v39d_confluence",
                "fallbacks": {"equity": ["v39d_confluence"]},
            }
        )
    )
    monkeypatch.setattr(registry, "MODELS_ROOT", models)
    monkeypatch.setattr(registry, "DEPLOYMENT_MANIFEST_PATH", manifest)
    return active, fallback, manifest


def test_live_default_comes_from_hash_verified_manifest(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    assert registry.equity_default_model() == "v72_dual_sleeve"
    assert registry.standard_equity_model() == "v72_dual_sleeve"


def test_tampered_active_fails_over_to_declared_rollback(monkeypatch, tmp_path):
    active, _, _ = _setup(monkeypatch, tmp_path)
    (active / "signal_engine.py").write_text("TAMPERED = True\n")
    assert registry.load_deployment_manifest() == {}
    assert registry.equity_default_model() == "v39d_confluence"


def test_symbol_route_remains_competitive(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    monkeypatch.setattr(
        registry,
        "route_best_model",
        lambda symbol, horizon=None: {"model": "v65_spec_tsla"},
    )
    assert registry.equity_model_for_symbol("TSLA") == "v65_spec_tsla"
    assert registry.equity_model_for_symbol() == "v72_dual_sleeve"
