# Project Plan: v83_adaptive_regime

This document outlines the step-by-step plan for implementing and verifying the `v83_adaptive_regime` model under Almgren-Chriss market impact.

## Phase 1: Baseline & Test Infra (Milestone 1)
- [x] Task 1.1: Run `v72_dual_sleeve` backtest under Almgren-Chriss impact to establish baseline metrics.
- [x] Task 1.2: Design and implement E2E test suite (`tests/test_v83_e2e.py`) to verify that the model executes correctly, imports the AC engine, and outputs correct format/variables.

## Phase 2: v83 Implementation (Milestone 2)
- [x] Task 2.1: Create `models/poc_va_macdha/v83_adaptive_regime/` directory structure.
- [x] Task 2.2: Implement `signal_engine.py` using dynamic regime routing/sizing based on `tools/institutional_flow/features.py`.
- [x] Task 2.3: Configure default `config.json` and `hunt_config.json` for `v83`.

## Phase 3: Backtest & Optimize (Milestone 3)
- [ ] Task 3.1: Run `v83_adaptive_regime` backtest under AC impact.
- [ ] Task 3.2: Tune regime thresholds and sleeve allocation coefficients.
- [ ] Task 3.3: Target performance validation: Win rate >= 75%, Max Drawdown <= 20%, n >= 30, positive net return.

## Phase 4: Verification & Audit (Milestone 4)
- [ ] Task 4.1: Run all unit and E2E tests for verification.
- [ ] Task 4.2: Trigger Forensic Auditor to verify that implementation is authentic (no cheating, no hardcoding).
- [ ] Task 4.3: Compile the final comparison report contrasting `v83` and `v72`.
- [ ] Task 4.4: Hand off results and close the task.
