# Trading Algo Integration Package

Drop these files into your website backend:

## Quick Setup

```bash
# Install dependencies
pip install yfinance flask pandas numpy

# Run the signal server
python services/api_server.py
```

## API Endpoints

| Endpoint | Returns |
|----------|---------|
| `/signal/{SYMBOL}` | Signal for single ticker |
| `/scan` | Scan popular tickers |
| `/health` | Health check |

## Example Response

```json
{
  "symbol": "IONQ.US",
  "go_long": true,
  "confidence": 0.75,
  "vol_z": 2.5,
  "signal_strength": 10.0,
  "price": 42.50
}
```

## $1M Trading Logic

When `vol_z >= 1.5` and `go_long == true`:
- vol_z 1.5-2.0: 3x leverage
- vol_z 2.0-2.5: 5x leverage  
- vol_z >= 2.5: 10x leverage

## JavaScript Integration

```javascript
// Frontend fetch
const signal = await fetch('/signal/IONQ.US').then(r => r.json());
if (signal.go_long && signal.vol_z >= 1.5) {
  // Trigger options trade
  placeTrade({symbol: signal.symbol, leverage: signal.signal_strength});
}
```
