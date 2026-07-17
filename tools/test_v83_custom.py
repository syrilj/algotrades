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
        
    # We will test configurations targeting WR >= 75%
    configs = [
        {
            "name": "Sniper Only (core_scale=0)",
            "core_scale": 0.0,
            "core_trend_low_vol_scale": 0.0,
            "core_trend_high_vol_scale": 0.0,
            "core_chop_low_vol_scale": 0.0,
            "core_chop_high_vol_scale": 0.0,
            "core_rsi_ob_filter": 70.0,
            "core_rsi_os_filter": 30.0
        },
        {
            "name": "Very Conservative Core (core_scale=0.2)",
            "core_scale": 0.20,
            "core_trend_low_vol_scale": 0.5,
            "core_trend_high_vol_scale": 0.0,
            "core_chop_low_vol_scale": 0.0,
            "core_chop_high_vol_scale": 0.0,
            "core_rsi_ob_filter": 70.0,
            "core_rsi_os_filter": 30.0
        },
        {
            "name": "Trend-Only Core (low-vol trend only)",
            "core_scale": 0.50,
            "core_trend_low_vol_scale": 1.0,
            "core_trend_high_vol_scale": 0.0,
            "core_chop_low_vol_scale": 0.0,
            "core_chop_high_vol_scale": 0.0,
            "core_rsi_ob_filter": 70.0,
            "core_rsi_os_filter": 30.0
        },
        {
            "name": "Trend-Only Core + RSI Adj",
            "core_scale": 0.50,
            "core_trend_low_vol_scale": 1.0,
            "core_trend_high_vol_scale": 0.0,
            "core_chop_low_vol_scale": 0.0,
            "core_chop_high_vol_scale": 0.0,
            "core_rsi_ob_filter": 65.0,
            "core_rsi_os_filter": 35.0
        }
    ]
    
    models = dmr.discover_models(["v83_adaptive_regime"])
    model = models[0]
    
    results = []
    try:
        for cfg in configs:
            name = cfg["name"]
            print(f"\nRunning: {name}")
            temp_hunt = base_hunt.copy()
            for k, v in cfg.items():
                if k != "name":
                    temp_hunt[k] = v
            
            with open(hunt_config_path, "w", encoding="utf-8") as f:
                json.dump(temp_hunt, f, indent=2)
                
            res = dmr.run_one(
                model=model,
                mode="daily",
                codes=EQUITY_WINNER_BAG,
                start="2024-08-01",
                end="2026-07-11",
                tag=f"tune_v83_custom_{name.replace(' ', '_').replace('=', '_').replace('(', '').replace(')', '')}",
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
                continue
                
            metrics = {
                "name": name,
                "ret": res["ret"],
                "dd": res["dd"],
                "sharpe": res["sharpe"],
                "n": res["n"],
                "wr": res["wr"],
                "final": res["final"],
                "config": temp_hunt
            }
            results.append(metrics)
            print(f"  Return: {metrics['ret']:.2%}, Max DD: {metrics['dd']:.2%}, Trades: {metrics['n']}, Win Rate: {metrics['wr']:.2%}")
            
    finally:
        with open(hunt_config_path, "w", encoding="utf-8") as f:
            json.dump(base_hunt, f, indent=2)
            
    print("\n================ CUSTOM LEADERBOARD ================")
    for r in results:
        print(f"{r['name']:<35} | {r['ret']:.2%} | {r['dd']:.2%} | {r['sharpe']:.2f} | {r['n']:<6} | {r['wr']:.2%}")

if __name__ == "__main__":
    main()
