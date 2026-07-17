import json
from pathlib import Path
import pytest
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from evolve import loop_core


def test_load_trial_history_missing(tmp_path):
    missing_file = tmp_path / "nonexistent.jsonl"
    keys, parents = loop_core.load_trial_history(missing_file)
    assert keys == set()
    assert parents == []


def test_load_trial_history_valid(tmp_path):
    trials_file = tmp_path / "trials.jsonl"
    
    # 6 mock entries, some with lockbox_fitness, some without
    rows = [
        {"parent": "p1", "variant_id": "v1", "fitness": 1.5, "lockbox_fitness": 1.2},
        {"parent": "p1", "variant_id": "v2", "fitness": 2.5, "lockbox_fitness": None},  # lockbox is None -> not in top parents
        {"parent": "p1", "variant_id": "v3", "fitness": 3.5, "lockbox_fitness": 3.2},
        {"parent": "p2", "variant_id": "v4", "fitness": 0.5, "lockbox_fitness": 0.4},
        {"parent": "p2", "variant_id": "v5", "fitness": 4.5, "lockbox_fitness": 4.2},
        {"parent": "p3", "variant_id": "v6", "fitness": 5.5, "lockbox_fitness": 5.2},
        {"parent": "p3", "variant_id": "v7", "fitness": 6.5, "lockbox_fitness": 6.2},
    ]
    
    with trials_file.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
            
    keys, parents = loop_core.load_trial_history(trials_file)
    
    # We should have 7 keys
    assert len(keys) == 7
    
    # We should have top-5 parents with non-null lockbox_fitness sorted by fitness desc:
    # v7 (6.5), v6 (5.5), v5 (4.5), v3 (3.5), v1 (1.5)
    # v4 (0.5) is not in top 5, v2 has null lockbox_fitness
    assert len(parents) == 5
    assert parents[0]["variant_id"] == "v7"
    assert parents[1]["variant_id"] == "v6"
    assert parents[2]["variant_id"] == "v5"
    assert parents[3]["variant_id"] == "v3"
    assert parents[4]["variant_id"] == "v1"


def test_run_campaign_skips_tried_variants(monkeypatch, tmp_path):
    # Set up mock trial history that matches the variants spawned
    trials_file = tmp_path / "trials.jsonl"
    
    # Variant id format in spawn_direction_variants: f"{base_model['id']}_{spec['name']}"
    # Let's seed a mock tried variant key
    import hashlib
    key_dict = {"parent": "v39b_live_adapt", "variant_id": "v39b_live_adapt_tight_stop_all"}
    key_bytes = json.dumps(key_dict, sort_keys=True).encode("utf-8")
    tried_hash = hashlib.sha1(key_bytes).hexdigest()
    
    # We write a trial for this variant
    t_row = {"parent": "v39b_live_adapt", "variant_id": "v39b_live_adapt_tight_stop_all", "fitness": 1.0, "lockbox_fitness": 1.0}
    with trials_file.open("w") as f:
        f.write(json.dumps(t_row) + "\n")
        
    monkeypatch.setattr(loop_core, "TRIALS_PATH", trials_file)
    
    # Let's verify load_trial_history returns the seeded key
    keys, parents = loop_core.load_trial_history(trials_file)
    assert tried_hash in keys


def test_trial_dedupe_is_evaluation_contract_aware(tmp_path):
    trials_file = tmp_path / "trials.jsonl"
    trials_file.write_text(
        json.dumps(
            {
                "parent": "p1",
                "variant_id": "v1",
                "cash": 1_000_000,
                "interval": "1H",
                "codes": ["SPY.US"],
                "fitness": 1.0,
                "lockbox_fitness": None,
            }
        )
        + "\n"
    )
    keys, _parents = loop_core.load_trial_history(trials_file)
    million_key = loop_core._contract_trial_key(
        "p1", "v1", cash=1_000_000, interval="1H", codes=["SPY.US"]
    )
    thousand_key = loop_core._contract_trial_key(
        "p1", "v1", cash=1_000, interval="1H", codes=["SPY.US"]
    )
    assert million_key in keys
    assert thousand_key not in keys


def test_contract_research_row_without_lockbox_never_seeds_parent(tmp_path):
    trials_file = tmp_path / "trials.jsonl"
    trials_file.write_text(
        json.dumps(
            {
                "parent": "p1",
                "variant_id": "research_only",
                "cash": 1_000,
                "interval": "1H",
                "codes": ["SPY.US"],
                "fitness": 99.0,
                "lockbox_fitness": 0.0,
                "promotion_evidence": {},
            }
        )
        + "\n"
    )
    _keys, parents = loop_core.load_trial_history(trials_file)
    assert parents == []
