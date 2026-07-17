import json
from pathlib import Path
import sys

# Ensure repo root is in python path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.dynamic_model_rank as dmr

EQUITY_WINNER_BAG = ["TSLA.US", "MU.US", "SPY.US", "IONQ.US", "APLD.US", "XLP.US", "QQQ.US"]

def main():
    hunt_config_path = ROOT / "models" / "poc_va_macdha" / "v83_adaptive_regime" / "hunt_config.json"
    
    # Read base config
    with open(hunt_config_path, "r", encoding="utf-8") as f:
        base_hunt = json.load(f)
        
    print(f"Loaded base hunt config: {base_hunt}")
    
    # We will test the following configurations:
    configs = [
        {
            "name": "Variant A (Default)",
            "core_trend_low_vol_scale": 1.0,
            "core_trend_high_vol_scale": 0.60,
            "core_chop_low_vol_scale": 0.30,
            "core_chop_high_vol_scale": 0.00,
            "core_rsi_ob_filter": 70.0,
            "core_rsi_os_filter": 30.0
        },
        {
            "name": "Variant B",
            "core_trend_low_vol_scale": 0.9,
            "core_trend_high_vol_scale": 0.50,
            "core_chop_low_vol_scale": 0.20,
            "core_chop_high_vol_scale": 0.00,
            "core_rsi_ob_filter": 70.0,
            "core_rsi_os_filter": 30.0
        },
        {
            "name": "Variant C",
            "core_trend_low_vol_scale": 0.8,
            "core_trend_high_vol_scale": 0.40,
            "core_chop_low_vol_scale": 0.10,
            "core_chop_high_vol_scale": 0.00,
            "core_rsi_ob_filter": 70.0,
            "core_rsi_os_filter": 30.0
        },
        {
            "name": "Variant A + RSI Adj (Variant D - A)",
            "core_trend_low_vol_scale": 1.0,
            "core_trend_high_vol_scale": 0.60,
            "core_chop_low_vol_scale": 0.30,
            "core_chop_high_vol_scale": 0.00,
            "core_rsi_ob_filter": 65.0,
            "core_rsi_os_filter": 35.0
        },
        {
            "name": "Variant B + RSI Adj (Variant D - B)",
            "core_trend_low_vol_scale": 0.9,
            "core_trend_high_vol_scale": 0.50,
            "core_chop_low_vol_scale": 0.20,
            "core_chop_high_vol_scale": 0.00,
            "core_rsi_ob_filter": 65.0,
            "core_rsi_os_filter": 35.0
        },
        {
            "name": "Variant C + RSI Adj (Variant D - C)",
            "core_trend_low_vol_scale": 0.8,
            "core_trend_high_vol_scale": 0.40,
            "core_chop_low_vol_scale": 0.10,
            "core_chop_high_vol_scale": 0.00,
            "core_rsi_ob_filter": 65.0,
            "core_rsi_os_filter": 35.0
        }
    ]
    
    results = []
    models = dmr.discover_models(["v83_adaptive_regime"])
    if not models:
        print("Could not discover model v83_adaptive_regime!")
        return
    model = models[0]
    
    try:
        for cfg in configs:
            name = cfg["name"]
            print(f"\n========================================\nRunning: {name}\n========================================")
            # Apply parameters
            temp_hunt = base_hunt.copy()
            for k, v in cfg.items():
                if k != "name":
                    temp_hunt[k] = v
            
            with open(hunt_config_path, "w", encoding="utf-8") as f:
                json.dump(temp_hunt, f, indent=2)
                
            # Run backtest
            res = dmr.run_one(
                model=model,
                mode="daily",
                codes=EQUITY_WINNER_BAG,
                start="2024-08-01",
                end="2026-07-11",
                tag=f"tune_v83_{name.replace(' ', '_').replace('+', 'plus').replace('(', '').replace(')', '').replace('-', '_')}",
                force_1d=False,
                reuse=False,  # Force fresh run to avoid caching issues with changing hunt_config!
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
                print(f"Error running backtest for {name}: {res['error']}")
                continue
                
            metrics = {
                "name": name,
                "trend_low": cfg["core_trend_low_vol_scale"],
                "trend_high": cfg["core_trend_high_vol_scale"],
                "chop_low": cfg["core_chop_low_vol_scale"],
                "chop_high": cfg["core_chop_high_vol_scale"],
                "rsi_ob": cfg["core_rsi_ob_filter"],
                "rsi_os": cfg["core_rsi_os_filter"],
                "ret": res["ret"],
                "dd": res["dd"],
                "sharpe": res["sharpe"],
                "n": res["n"],
                "wr": res["wr"],
                "final": res["final"]
            }
            results.append(metrics)
            print(f"Result for {name}:")
            print(f"  Return: {metrics['ret']:.2%}")
            print(f"  Max DD: {metrics['dd']:.2%}")
            print(f"  Sharpe: {metrics['sharpe']:.2f}")
            print(f"  Trades: {metrics['n']}")
            print(f"  Win Rate: {metrics['wr']:.2%}")
            print(f"  Final Cash: ${metrics['final']:.2f}")
            
    finally:
        # Restore original hunt_config
        with open(hunt_config_path, "w", encoding="utf-8") as f:
            json.dump(base_hunt, f, indent=2)
        print("\nRestored original hunt_config.json")
        
    # Print leaderboard
    print("\n================ LEADERBOARD ================")
    print(f"{'Name':<35} | {'Return':<8} | {'Max DD':<8} | {'Sharpe':<6} | {'Trades':<6} | {'Win Rate':<8}")
    print("-" * 85)
    for r in results:
        print(f"{r['name']:<35} | {r['ret']:.2%} | {r['dd']:.2%} | {r['sharpe']:.2f} | {r['n']:<6} | {r['wr']:.2%}")

if __name__ == "__main__":
    main()
