# Hypothesis

**Version:** `vN_name`  
**Family:** `poc_va_macdha`  
**Date:** YYYY-MM-DD

## Claim (one paragraph)

What changes vs WINNER, and why it should raise OOS expectancy / PF / Sharpe or cut DD.

## Finds applied

- List `findings.jsonl` ids / summaries this version uses

## Finds avoided

- List failed findings we are not repeating

## Pass bar target

Must beat: PF ≥ 1.2, |DD| ≤ 25%, Sharpe ≥ 0.5, trades ≥ 40 on claimed window.

## Kill criteria

If OOS fails → record with `tools/findings.py record --status fail` and follow `models/_shared/FAILURE_PROTOCOL.md`.
