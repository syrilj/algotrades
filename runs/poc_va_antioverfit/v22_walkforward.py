#!/usr/bin/env python3
"""Walk-forward anti-overfit test for v22_opts_live.

Splits history into rolling train/test windows. The model is frozen (same code/config);
we only evaluate whether it degrades on windows it was not tuned on.

Output: runs/poc_va_antioverfit/v22_walkforward_results.json
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_RUN = ROOT / "runs" / "poc_va_v22_opts_live"
OUT_DIR = Path(__file__).resolve().parent / "artifacts"
OUT_DIR.mkdir(parents=True, exist_ok=True)

WINDOWS = [
    ("wf_2021_2022", "2021-01-01", "2022-12-31"),
    ("wf_2022_2023", "2022-01-01", "2023-12-31"),
    ("wf_2023_2024", "2023-01-01", "2024-07-31"),
    ("wf_2024_2025", "2024-08-01", "2025-07-31"),
    ("wf_2025_2026", "2025-01-01", "2026-07-11"),
    ("wf_2022_2024", "2022-01-01", "2024-07-31"),
    ("wf_2020_2021", "2020-01-01", "2021-12-31"),
]


def run_window(name: str, start: str, end: str) -> dict:
    run_dir = ROOT / "runs" / f"poc_va_v22_{name}"
    code_dir = run_dir / "code"
    code_dir.mkdir(parents=True, exist_ok=True)
    for f in (SRC_RUN / "code").iterdir():
        if f.is_file():
            shutil.copy2(f, code_dir / f.name)

    cfg = json.loads((SRC_RUN / "config.json").read_text())
    cfg["start_date"] = start
    cfg["end_date"] = end
    cfg["strategy"]["model_version"] = f"v22_{name}"
    cfg["strategy"]["note"] = f"walk-forward window {start} to {end}"
    (run_dir / "config.json").write_text(json.dumps(cfg, indent=2))

    proc = subprocess.run(
        [
            str(ROOT / ".venv" / "bin" / "python"),
            "-c",
            f'from pathlib import Path; from backtest.runner import main; main(Path("{run_dir}").resolve())',
        ],
        capture_output=True,
        text=True,
        timeout=600,
        cwd=str(ROOT),
    )
    out = proc.stdout.strip()
    try:
        start_idx = out.rfind("{")
        metrics = json.loads(out[start_idx:])
    except Exception:
        metrics = {"error": "parse failed", "stdout_tail": out[-500:], "stderr_tail": proc.stderr[-500:]}
    return {"name": name, "start": start, "end": end, "metrics": metrics}


def main() -> None:
    results = {}
    for name, start, end in WINDOWS:
        print(f"Running {name}: {start} -> {end}")
        res = run_window(name, start, end)
        results[name] = res
        print(f"  final_value={res['metrics'].get('final_value')} return={res['metrics'].get('total_return')}")

    out_file = OUT_DIR / "v22_walkforward_results.json"
    out_file.write_text(json.dumps(results, indent=2))
    print(f"\nSaved walk-forward results to {out_file}")


if __name__ == "__main__":
    main()
