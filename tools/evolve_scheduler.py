#!/usr/bin/env python3
import argparse
import sys
import os
import time
import subprocess
import json
from pathlib import Path
from datetime import datetime, timezone

# This file lives in tools/. Runtime and data paths are rooted at the repo, not
# at tools/ (which previously produced tools/runs and tools/tools/... paths).
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Ensure runs/scheduler exists
SCHEDULER_DIR = ROOT / "runs" / "scheduler"
SCHEDULER_DIR.mkdir(parents=True, exist_ok=True)
LOCK_PATH = SCHEDULER_DIR / "LOCK"
LOG_PATH = SCHEDULER_DIR / "scheduler.log"

def log(msg: str):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}\n"
    print(msg)
    with LOG_PATH.open("a") as f:
        f.write(line)

def check_pid(pid: int) -> bool:
    """Check if process with pid is running."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

def acquire_lock() -> bool:
    if LOCK_PATH.exists():
        try:
            pid = int(LOCK_PATH.read_text().strip())
            if check_pid(pid):
                return False
        except (ValueError, OSError):
            pass
    LOCK_PATH.write_text(str(os.getpid()))
    return True

def release_lock():
    if LOCK_PATH.exists():
        try:
            LOCK_PATH.unlink()
        except OSError:
            pass

def check_data_freshness():
    manifest_path = ROOT / "data_cache" / "MANIFEST.json"
    if not manifest_path.exists():
        log("data_cache/MANIFEST.json missing. Refreshing...")
        return False
    
    mtime = manifest_path.stat().st_mtime
    age_days = (time.time() - mtime) / 86400.0
    log(f"data_cache/MANIFEST.json age: {age_days:.2f} days")
    if age_days > 3.0:
        log("Data is older than 3 days. Refreshing...")
        return False
    return True

def refresh_data():
    bin_path = ROOT / ".venv" / "bin" / "python3"
    script_path = ROOT / "tools" / "snapshot_data.py"
    log("Running snapshot_data.py snapshot...")
    res = subprocess.run([str(bin_path), str(script_path), "snapshot"], capture_output=True, text=True)
    if res.returncode != 0:
        log(f"Data refresh FAILED (exit {res.returncode}): {res.stderr or res.stdout}")
        return False
    log("Data refresh completed successfully.")
    return True


def validate_data_quality() -> bool:
    """Fail closed before research consumes a corrupt or mismatched snapshot."""
    bin_path = ROOT / ".venv" / "bin" / "python3"
    script_path = ROOT / "tools" / "data_quality.py"
    output_path = ROOT / "runs" / "monitoring" / "DATA_QUALITY.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [str(bin_path), str(script_path), "--output", str(output_path)]
    log(f"Validating data quality: {' '.join(cmd)}")
    try:
        res = subprocess.run(cmd, timeout=1800, capture_output=True, text=True)
    except subprocess.TimeoutExpired:
        log("Data-quality validation TIMED OUT after 1800s.")
        return False
    if res.returncode != 0:
        log(f"Data-quality validation FAILED (exit {res.returncode}): {res.stderr or res.stdout}")
        return False
    log(f"Data-quality validation passed: {output_path}")
    return True

def run_bounded_evolve():
    """Run a bounded but promotion-grade rank job.

    Promotable scheduled work must execute the multi-lock path. ``--quick``
    suppresses that path in evolve_pipeline, and ``--no-multi-lock`` disables
    it explicitly, so neither flag is allowed here.
    """
    bin_path = ROOT / ".venv" / "bin" / "python3"
    script_path = ROOT / "tools" / "evolve_pipeline.py"
    cmd = [
        str(bin_path),
        str(script_path),
        "rank",
        "--track", "equity",
        "--budget", "1",
    ]
    log(f"Running bounded evolve: {' '.join(cmd)}")
    try:
        res = subprocess.run(cmd, timeout=3600, capture_output=True, text=True)
        if res.returncode != 0:
            log(f"Evolve rank FAILED (exit {res.returncode}): {res.stderr or res.stdout}")
            return False
        log("Evolve rank completed successfully.")
        return True
    except subprocess.TimeoutExpired:
        log("Evolve rank TIMED OUT after 3600s.")
        return False


def settle_and_monitor_models() -> bool:
    """Settle due shadow decisions and write the current model-health artifact."""
    bin_path = ROOT / ".venv" / "bin" / "python3"
    script_path = ROOT / "tools" / "model_monitoring.py"
    output_path = ROOT / "runs" / "monitoring" / "MODEL_HEALTH.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(bin_path),
        str(script_path),
        "--settle-due",
        "--output", str(output_path),
    ]
    log(f"Settling shadow decisions and monitoring models: {' '.join(cmd)}")
    try:
        res = subprocess.run(cmd, timeout=1800, capture_output=True, text=True)
    except subprocess.TimeoutExpired:
        log("Model monitoring TIMED OUT after 1800s.")
        return False
    if res.returncode != 0:
        log(f"Model monitoring FAILED (exit {res.returncode}): {res.stderr or res.stdout}")
        return False
    if not output_path.exists():
        log(f"Model monitoring FAILED: expected output missing: {output_path}")
        return False
    log(f"Model monitoring completed successfully: {output_path}")
    return True

def re_rank_and_health():
    # Import model_registry inside function to load the fresh registry state
    from tools import model_registry
    from tools.evolve import promotion_queue
    
    log("Re-ranking models...")
    try:
        ranked = model_registry.rank_models()
        log("Top 5 models after re-ranking:")
        for idx, r in enumerate(ranked[:5]):
            log(f"  #{idx+1}: {r.get('model')} (Score: {r.get('score')}, Blended Score: {r.get('blended_score')})")
    except Exception as e:
        log(f"Failed to re-rank models: {e}")
        
    log("Checking winner health...")
    try:
        health = promotion_queue.winner_health()
        log(f"Winner Health: degraded={health.get('degraded')}, winner={health.get('winner')}, live_wr={health.get('live_wr')}, threshold={health.get('threshold')}")
        if health.get("degraded"):
            log("WARNING: Current winner is DEGRADED!")
    except Exception as e:
        log(f"Failed to check winner health: {e}")

def main():
    p = argparse.ArgumentParser(description="Nightly evolution scheduler")
    p.add_argument("--once", action="store_true", help="Run once now")
    args = p.parse_args()

    if not args.once:
        log("Scheduler must be run with --once in standard execution. Exiting.")
        return 0

    if not acquire_lock():
        # lock file held by active process, exit 0
        ts = datetime.now(timezone.utc).isoformat()
        print(f"[{ts}] Lockfile held by active process. Exiting cleanly.")
        return 0

    try:
        log("Starting nightly evolution run.")
        if not check_data_freshness():
            if not refresh_data():
                log("ABORTING evolution campaign due to data refresh failure.")
                return 1

        if not validate_data_quality():
            log("ABORTING evolution campaign due to data-quality failure.")
            return 1
        
        if not run_bounded_evolve():
            log("Evolution run failed.")
            return 1

        if not settle_and_monitor_models():
            log("ABORTING health/ranking because model monitoring failed.")
            return 1
            
        re_rank_and_health()
        log("Nightly evolution run completed.")
        return 0
    finally:
        release_lock()

if __name__ == "__main__":
    sys.exit(main())
