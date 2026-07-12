#!/usr/bin/env python3
"""Standalone server that can run alongside Next.js."""
from flask import Flask, jsonify
from live_signal import LiveSignalEngine, batch_scan

app = Flask(__name__)
engine = LiveSignalEngine()

@app.route('/signal/<symbol>')
def get_signal(symbol):
    result = engine.analyze(symbol)
    return jsonify(result)

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'service': 'live-signal'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=False)
