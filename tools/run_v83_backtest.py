import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.dynamic_model_rank as dmr

EQUITY_WINNER_BAG = ["TSLA.US", "MU.US", "SPY.US", "IONQ.US", "APLD.US", "XLP.US", "QQQ.US"]

def main():
    hunt_config_path = ROOT / "models" / "poc_va_macdha" / "v83_adaptive_regime" / "hunt_config.json"
    
    with open(hunt_config_path, "r", encoding="utf-8") as f:
        base_hunt = json.load(f)
        
    # We will test setting core_scale to 0.0 and keeping other settings default
    cfg = base_hunt.copy()
    cfg["core_scale"] = 0.0
    
    with open(hunt_config_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
        
    models = dmr.discover_models(["v83_adaptive_regime"])
    model = models[0]
    
    try:
        print("\nRunning verification backtest for core_scale = 0.0 ...")
        res = dmr.run_one(
            model=model,
            mode="daily",
            codes=EQUITY_WINNER_BAG,
            start="2024-08-01",
            end="2026-07-11",
            tag="v83_verify_sniper_only",
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
        
        if "error" in res:
            print(f"Error: {res['error']}")
            return
            
        print("\n================ VERIFICATION RESULTS ================")
        print(f"Return: {res['ret']:.2%}")
        print(f"Max DD: {res['dd']:.2%}")
        print(f"Sharpe: {res['sharpe']:.2f}")
        print(f"Trades: {res['n']}")
        print(f"Win Rate: {res['wr']:.2%}")
        print(f"Final Cash: ${res['final']:.2f}")
        
    finally:
        # Restore original config
        with open(hunt_config_path, "w", encoding="utf-8") as f:
            json.dump(base_hunt, f, indent=2)

if __name__ == "__main__":
    main()
