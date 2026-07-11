# POC / Value Area + HTF MACD Heikin-Ashi

## Idea

Prior volume-profile levels as the map; higher-timeframe Standardized MACD Heikin-Ashi green for timing.

| Level | Role |
|-------|------|
| POC | Support while held. Lost POC becomes resistance — not a long base. |
| VAL / VAH | ~70% value area — long only inside this band. |
| HTF MACD HA green | Required for entries; primary exit when not green. |

## Tuned defaults (SPY.US 2018-07-11 window via config)

- profile_lookback=20, exit_on_poc_break=False, exit_on_val_break=False
- Sharpe 0.64 | total return +70% | max DD -21% | win rate 68% | 28 trades
- Buy-and-hold SPY ≈ +181% over same window (filtered long lags a strong bull market)

## Run

```bash
.venv/bin/python -c "from pathlib import Path; from backtest.runner import main; main(Path('runs/poc_va_macdha').resolve())"
.venv/bin/vibe-trading run -f prompts/poc_va_macdha_vibe.txt   # needs LLM provider up
```
