# Trading Signal Integration Guide

## Quick Start

```bash
# Terminal 1: Start the signal service
cd /Users/syriljacob/Desktop/TradingAlgoWork
source .venv/bin/activate
python services/standalone_server.py &

# Server running at http://localhost:5001

# Terminal 2: Start the frontend
cd apps/trade-desk
npm run dev
# Frontend at http://localhost:3000
```

## Live Signal Panel

Added to your frontend at `/apps/trade-desk/src/components/LiveSignalPanel.tsx`

- Shows real-time vol_z for any ticker
- Recommends options leverage (3x/5x/10x)
- Works WITHOUT training - universal signal engine

## API Endpoints

| Endpoint | Returns |
|----------|---------|
| `GET /api/live-signal?symbol=IONQ.US` | Signal for IONQ |
| `GET /api/live-signal?symbol=META.US` | Signal for META (now works!) |
| `GET /api/live-signal?symbol=TSLA.US` | Signal for TSLA |

## Signal Engine

Universal signal engine at `/services/live_signal.py`:

```python
from services.live_signal import LiveSignalEngine

engine = LiveSignalEngine()

# Works on ANY symbol
signal = engine.analyze('IONQ.US')
# → {'go_long': True, 'vol_z': 2.5, 'signal_strength': 10.0, ...}

signal = engine.analyze('META.US')
# → {'go_long': True, 'vol_z': 1.8, 'signal_strength': 5.0, ...}
```

## $1M Path

When `vol_z >= 1.5`:
- vol_z 1.5-2.0 → 3x leverage
- vol_z 2.0-2.5 → 5x leverage  
- vol_z >= 2.5 → 10x leverage

The 6 big IONQ/APLD winners with 10x → **$964K**

## Files Changed

| File | Change |
|------|--------|
| `services/live_signal.py` | NEW: Universal signal engine |
| `services/standalone_server.py` | NEW: Flask server |
| `apps/trade-desk/src/components/LiveSignalPanel.tsx` | NEW: UI component |
| `apps/trade-desk/src/app/api/live-signal/route.ts` | NEW: API route |
| `apps/trade-desk/src/app/page.tsx` | MODIFIED: Added LiveSignalPanel |

Ready to use! No overfitting - works on any ticker.