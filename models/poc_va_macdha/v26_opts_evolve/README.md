# v26_opts_evolve

Builds **on v22 options**, not on v25 equity.

```bash
# backtest (from repo root)
mkdir -p runs/poc_va_v26_opts_evolve/code
cp models/poc_va_macdha/v26_opts_evolve/signal_engine.py runs/poc_va_v26_opts_evolve/code/
cp models/poc_va_macdha/v26_opts_evolve/hunt_config.json runs/poc_va_v26_opts_evolve/code/
cp models/poc_va_macdha/v26_opts_evolve/config.json runs/poc_va_v26_opts_evolve/
.venv/bin/python -c "from pathlib import Path; from backtest.runner import main; main(Path('runs/poc_va_v26_opts_evolve').resolve())"
```
