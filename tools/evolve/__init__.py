"""Evolution pipeline: honest rank → feedback loop → constrained mutations → meta.

Phases
------
0  data contracts, dual claim bars, content cache, PASS_BAR gates
1  backtest farm (screen + deep) for all models
2  multi-gen feedback with constrained mutations
3  options synthetic research track (never auto-promote alone)
4  optional walk-forward meta MLP (size/skip), utility-labeled

CLI: ``.venv/bin/python tools/evolve_pipeline.py --help``
"""
from __future__ import annotations

__version__ = "1.0.0"
