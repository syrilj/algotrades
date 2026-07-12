#!/usr/bin/env python3
"""Flask API wrapper for live signal engine - plug into your website.

Run: python services/api_server.py
Test: curl http://localhost:5000/signal/IONQ.US
"""
from flask import Flask, jsonify
from services.live_signal import LiveSignalEngine, batch_scan

app = Flask(__name__)
engine = LiveSignalEngine()

@app.route('/signal/<symbol>')
def get_signal(symbol):
    """Get signal for single symbol."""
    result = engine.analyze(symbol)
    return jsonify(result)

@app.route('/scan')
def scan():
    """Scan popular symbols."""
    symbols = ['IONQ.US', 'APLD.US', 'TSLA.US', 'META.US', 'NVDA.US', 'AMD.US', 'SMCI.US', 'AVGO.US']
    results = batch_scan(symbols)
    return jsonify({
        'signals': results,
        'asof': results[0]['timestamp'] if results else None
    })

@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)