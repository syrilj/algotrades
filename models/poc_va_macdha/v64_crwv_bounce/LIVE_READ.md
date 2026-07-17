# CRWV desk read — 2026-07-14

**Specialist:** `v64_crwv_bounce` / `specialists/CRWV`  
**Spot:** **$79.95** (−4.0% vs prior close $83.31)

---

## Verdict (specialist)

| | |
|--|--|
| **Call** | **BUY ZONE / bounce long bias** at demand |
| **Specialist confidence** | **~83%** (demand + structure score) |
| **Signal size** | ~0.88 (scaled 0.35–1.0 by confluence) |
| **Invalidation** | Hourly close under **78.40**, then **75** put wall |

Your feel on the bounce is **aligned with structure + options**, not contradicted by it.

---

## Why the “best model” only shows ~22%

That low number is **not** saying “levels are fake.”

Global engines (`v39d` / bag meta) are built for **trend continuation** on names in `EQUITY_WINNER_BAG`:

- Prefer HTF MACD-HA green  
- Prefer mid/upper value-area continuation  
- Soft-stand-aside when tape is multi-week below SMA20/50  

CRWV right now:

- RSI14 ~**27** (oversold)  
- Below SMA10 **86.9** / SMA20 **96.7** / EMA21 **93.5**  
- Multi-week drawdown from ~122 → ~80  

So the global model is correctly saying: *“this is not my A+ trend setup.”*  
It is **silent / low-conf** on a **mean-reversion bounce** — a different trade class.

**Specialist confidence (~83%)** measures: *are we sitting on demand with bounce structure?*  
That is the right meter for your thesis.

---

## Levels that matter (your bounce map)

| Level | Why it matters | Role |
|------:|----------------|------|
| **78.40** | Today’s low = 20d low | **Line in the sand** |
| **79.2** | 20d VAL (volume value area low) | Demand / fair-value floor |
| **80** | Spot + heavy put OI / put volume | Put wall / pivot |
| **75** | Largest nearby put OI wall | **Hard invalidation** if lost |
| **70** | Next put OI shelf | Air pocket if 75 fails |
| **82.5–83.3** | Prior open / 20d POC band | First bounce target |
| **85** | Call volume magnet | Extension 1 |
| **90** | Huge call OI + volume | Extension 2 / squeeze magnet |
| **Session VWAP ~80.9** | Today’s auction | Reclaim = bounce confirmation |

You are **exactly in the demand pocket**: ~80, hugging VAL / day-low / 80 put wall.

---

## Options into the day (why calls matter)

Near expiry **2026-07-17** and next few:

- **Call volume > put volume** (calls leading tape interest)  
- Call flow concentrated **85 / 90 / 95 / 100** → traders pricing **upside magnets**, not just put hedges  
- Put OI walls stacked **75 / 70 / 80** → dealers/positioning often **defend or magnetize** those strikes  

**Read:** market is positioned for a **bounce attempt from 78–80** toward **85–90**, **unless** 75 breaks.  
That matches “calls coming into the day” + bounce-off-levels — not a random 22% fade signal.

---

## Playbook (operator English)

1. **Bias:** Long bounce from **78.4–80.5** while above **75**.  
2. **Trigger (prefer):** reclaim **session VWAP ~80.9** with green structure / volume **or** clear stop-volume wick hold at 78.4–80.  
3. **Targets:** **82.5–83.3** → **85** → **90**.  
4. **Stop / kill:** hourly close **&lt; 78.40**; full thesis dead on **&lt; 75**.  
5. **Size:** half until VWAP reclaim; cut if dump red-flag prints.

---

## Model files

- Engine: `models/poc_va_macdha/v64_crwv_bounce/signal_engine.py`  
- Config: `models/poc_va_macdha/v64_crwv_bounce/config.json`  
- Specialist mirror: `models/poc_va_macdha/specialists/CRWV/`  
- JSON snapshot: `models/poc_va_macdha/v64_crwv_bounce/LIVE_READ.json`

```bash
# smoke signal on latest 1H
.venv/bin/python -c "
import yfinance as yf, sys
from pathlib import Path
sys.path.insert(0, 'models/poc_va_macdha/v64_crwv_bounce')
from signal_engine import SignalEngine
h = yf.Ticker('CRWV').history(period='90d', interval='1h')
h.columns = [c.lower() for c in h.columns]
if h.index.tz is not None: h.index = h.index.tz_localize(None)
e = SignalEngine()
s = e.generate({'CRWV.US': h})['CRWV.US']
print('last_sig', float(s.iloc[-1]), e.last_read())
"
```
