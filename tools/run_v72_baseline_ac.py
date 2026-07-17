#!/usr/bin/env python3
import sys
from pathlib import Path

# Add repo root to python path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import json
import tools.dynamic_model_rank as dmr

def main():
    EQUITY_WINNER_BAG = ["TSLA.US", "MU.US", "SPY.US", "IONQ.US", "APLD.US", "XLP.US", "QQQ.US"]
    
    models = dmr.discover_models(["v72_dual_sleeve"])
    if not models:
        print("v72_dual_sleeve model not found!")
        sys.exit(1)
        
    model = models[0]
    print(f"Running baseline for: {model['id']}")
    
    res = dmr.run_one(
        model=model,
        mode="daily",
        codes=EQUITY_WINNER_BAG,
        start="2024-08-01",
        end="2026-07-11",
        tag="v72_ac_baseline",
        force_1d=False,
        reuse=False,
        cash=1000,
        source="local",
        interval="1H",
        extra_cfg={
            "impact_model": "almgren_chriss",
            "ac_eta": 0.1,
            "ac_gamma": 0.0
        }
    )
    
    print("\n======== RESULTS ========")
    print(json.dumps(res, indent=2))
    
    # Save the output to runs/v72_dual_sleeve/results_ac.json
    out_dir = ROOT / "runs" / "v72_dual_sleeve"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results_ac.json").write_text(json.dumps(res, indent=2))
    print(f"Results saved to {out_dir / 'results_ac.json'}")

if __name__ == "__main__":
    main()
