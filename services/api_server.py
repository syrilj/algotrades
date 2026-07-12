#!/usr/bin/env python3
"""Flask API for live signals + v25 hybrid plans (optional beside Next trade-desk).

Run:  python services/api_server.py
Test: curl http://localhost:5000/signal/IONQ.US
      curl 'http://localhost:5000/live-plan/APLD?account=1000&no_model=1'
"""
from __future__ import annotations

import sys
from pathlib import Path

from flask import Flask, jsonify, request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "services"))

from live_signal import LiveSignalEngine, batch_scan  # noqa: E402
from live_plan import plan_symbol, scan as live_scan  # noqa: E402

app = Flask(__name__)
engine = LiveSignalEngine()


@app.route("/signal/<symbol>")
def get_signal(symbol: str):
    result = engine.analyze(symbol)
    return jsonify(result)


@app.route("/scan")
def scan():
    symbols = [
        "IONQ.US",
        "APLD.US",
        "TSLA.US",
        "META.US",
        "NVDA.US",
        "AMD.US",
        "SMCI.US",
        "AVGO.US",
    ]
    results = batch_scan(symbols)
    return jsonify(
        {
            "signals": results,
            "asof": results[0]["timestamp"] if results else None,
        }
    )


@app.route("/live-plan/<symbol>")
def live_plan_route(symbol: str):
    account = float(request.args.get("account", 1000))
    peak = request.args.get("peak")
    no_model = request.args.get("no_model", "0") in ("1", "true", "yes")
    hist_raw = request.args.get("history", "")
    history = [float(x) for x in hist_raw.split(",") if x.strip()] if hist_raw else []
    out = plan_symbol(
        symbol,
        account=account,
        peak=float(peak) if peak else None,
        history=history,
        use_model=not no_model,
    )
    return jsonify(out)


@app.route("/live-scan")
def live_scan_route():
    account = float(request.args.get("account", 1000))
    peak = request.args.get("peak")
    out = live_scan(
        account=account,
        peak=float(peak) if peak else None,
        use_model=False,
    )
    return jsonify(out)


@app.route("/health")
def health():
    return jsonify({"status": "ok", "live_plan": True, "v25": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)