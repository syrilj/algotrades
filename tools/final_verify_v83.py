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
        hunt_cfg = json.load(f)
        
    print(f"Loaded hunt config for verification: {hunt_cfg}")
    assert hunt_cfg["core_scale"] == 0.0, "Expected core_scale to be 0.0 for verification!"
    
    models = dmr.discover_models(["v83_adaptive_regime"])
    model = models[0]
    
    print("\nRunning final verification backtest...")
    res = dmr.run_one(
        model=model,
        mode="daily",
        codes=EQUITY_WINNER_BAG,
        start="2024-08-01",
        end="2026-07-11",
        tag="v83_final_verification",
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
        print(f"Verification Failed with error: {res['error']}")
        sys.exit(1)
        
    print("\n================ FINAL VERIFICATION METRICS ================")
    print(f"Total Return: {res['ret']:.4%}")
    print(f"Max Drawdown: {res['dd']:.4%}")
    print(f"Sharpe: {res['sharpe']:.4f}")
    print(f"Trades (n): {res['n']}")
    print(f"Win Rate: {res['wr']:.4%}")
    print(f"Final Value: ${res['final']:.4f}")
    
    # Assertions to confirm criteria are met
    assert res["wr"] >= 0.75, f"Win Rate {res['wr']:.2%} is below target 75%"
    assert abs(res["dd"]) <= 0.20, f"Max Drawdown {res['dd']:.2%} exceeds target 20%"
    assert res["n"] >= 30, f"Number of trades {res['n']} is below target 30"
    assert res["ret"] > 0, f"Net Return {res['ret']:.2%} is not positive"
    print("\nSUCCESS: All performance criteria met!")

if __name__ == "__main__":
    main()
