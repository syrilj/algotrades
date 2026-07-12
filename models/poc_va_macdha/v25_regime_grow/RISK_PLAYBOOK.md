# Live Risk Playbook — v25 Hybrid

**Goal:** Grow capital (eval: $1,000 → $1,000,000 path) without dying.  
**Doctrine:** Equities when options suck. Bet big when options are A+. Cut losers fast.

---

## Daily checklist (5 minutes)

1. **Mark account equity + peak** (high-water since start of book).
2. Run portfolio status:
   ```bash
   python3 tools/risk_manager.py status --equity 1000 --peak 1200 --history 1,1,-1
   ```
3. If mode is `FLATTEN` → close everything. If `HALT_NEW` → manage opens only.
4. Scan names (desk):
   ```bash
   python3 tools/trade_desk.py rotate --model v25_regime_grow --account 1000
   ```
5. For each candidate, **plan** vehicle:
   ```bash
   python3 tools/risk_manager.py plan \
     --symbol APLD --account 1000 --conf 0.85 --vol-z 1.8 --qqq-ok
   ```
6. If `OPTIONS_ATTACK` → pick structure:
   ```bash
   python3 tools/options_picker.py --symbol APLD --account 1000 --risk-pct 0.22
   ```
7. If `EQUITY_HEDGE` → size stock from desk risk-pct (engine stops).
8. If `STAND_ASIDE` → **cash is a position**. Do nothing.

---

## Modes (what to do)

| Mode | When | What you do |
|------|------|-------------|
| **OPTIONS_ATTACK** | High conviction + QQQ ok + not defensive + options affordable | Debit spread (preferred). Risk **12–22%** of book max loss (hard cap 25%). |
| **EQUITY_HEDGE** | Model edge but not A+ options | Stock long, **1–2%** risk to stop. Up to 4 names. |
| **STAND_ASIDE** | Defensive macro / no edge | No new risk. |
| **HALT_NEW** | DD ≥ 18% from peak | No new entries; manage exits. |
| **FLATTEN** | DD ≥ 28% from peak | Close all. Rebuild only after write-up. |

---

## Options: bet big + cut fast

### Entry (A+ only)

All roughly true:

- Model confidence ≥ ~0.72 (attack ≥ ~0.82)
- Volume z healthy (≥1 better; ≥2 best)
- QQQ trend ok
- Not XLP/SPY defensive
- Earnings not ≤3 days (≤7 days → size down)
- Max loss for 1 structure ≤ risk budget
- Prefer **bull call debit spread**, 14–45 DTE, long Δ ~0.35–0.50

### Exit (tape these on every ticket)

| Rule | Trigger | Action |
|------|---------|--------|
| **Cut loser** | Premium ≤ **−30%** from entry | Exit immediately. No hope. |
| **Stagnant** | 2 sessions, option barely moved (<8%) & stock <2% | Exit. Free capital. |
| **Trail winner** | After **+40%** premium | Exit if give back **25%** of peak premium |
| **Time** | ≤ **5 DTE** | Flat. No lottery holds. |
| **Side gone** | Stock model flips off / macro defensive | Exit options |

```bash
# Example: premium down 32% from entry
python3 tools/risk_manager.py check-open \
  --vehicle options --symbol APLD --entry 1.50 --pnl-pct -0.32
```

---

## Equities: the “wait for options” hedge

- Same **SIDE** rules as v23 (POC/VA + HTF + meta + vol-z + macro).
- Risk **~1%** of equity to ATR stop (max ~2% on high conviction).
- Max **4** concurrent equity names.
- Purpose: stay compound-positive and **liquid** so you can rotate into A+ options when they appear.
- Do **not** turn equity hedge into leverage FOMO.

---

## Position sizing formulas (mental math)

**Options max loss $**  
`account × risk_pct`  
Example: $1,000 × 0.22 = **$220** max loss on the idea (1–2 contracts max on $1k).

**Equity shares**  
`risk_$ / (entry − stop)`  
Example: $10 risk, $2 stop distance → **5 shares**.

**Feedback (after closed trades)**  

| Last results | Next size mult |
|--------------|----------------|
| Last was a **loss** | **0.35×** |
| 1–2 wins in a row | **0.70×** |
| 3+ wins in a row | **1.15×** (capped) |

Feedback never overrides flatten/halt.

---

## Portfolio DD ladder

| Drawdown from peak | Behavior |
|--------------------|----------|
| 0–8% | Full policy |
| 8–18% | Soft throttle (size down) |
| 18–28% | **Halt new** entries |
| ≥28% | **Flatten all** |

---

## $1k → $1M honesty

- 1000× requires **years of edge + compounding + not blowing up**, not a 30-day miracle.
- Best *realistic* options chains in prior research were ~30–50× in lucky windows with high variance.
- Your job as operator: **survive every bad month**, then let attack trades stack when the tape pays.

---

## What not to do

- Stack more entry filters to chase 90% WR (thin sample / overfit).
- Full account into one naked weekly.
- Hold options “because it might bounce.”
- Retune rules on the same window you evaluate (anti-overfit).
- Trade MU ATM weeklies on a $1k book.

---

## Files

| File | Role |
|------|------|
| `tools/risk_manager.py` | Live plan / check-open / status |
| `RISK_POLICY.json` | Numeric gates (edit carefully) |
| `tools/options_picker.py` | Structure + DTE + budget |
| `tools/trade_desk.py` | Scans + model state |
| `signal_engine.py` | Equity SIDE = v23 wrapper for backtests |
