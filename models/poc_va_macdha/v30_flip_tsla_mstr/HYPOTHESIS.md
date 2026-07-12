# v30_flip_tsla_mstr

## Style (user)

- **TSLA + MSTR only**
- **Calls** on pullback bounces, **puts** on downside breaks
- Catch the move → **get out** (1–2 days typical, **max 5 days**)
- **No spreads / straddles** — long calls or long puts only
- **Growth first**: risk a large share of the book per flip (not a 10% “safe” sleeve)

## Rules

| Piece | Setting |
|-------|---------|
| Names | TSLA.US, MSTR.US |
| DTE | ~7 (short-dated for flip) |
| Strike | ATM |
| Call entry | Dip into lower band / RSI rebound with bounce day |
| Put entry | Breakdown / RSI fade with red momentum day |
| Exit | Signal flip, **max_hold_days**, or quick underlying target |
| Size | `risk_pct` of equity in premium (default **0.70**) |
| Risk gates | Minimal — no soft DD haircuts; only avoid $0 cash |

## Not this model

- v29 bag (IONQ/AVGO/HOOD/MU) long-only ATM 21D
- Credit spreads, iron condors, defined-risk multi-leg
