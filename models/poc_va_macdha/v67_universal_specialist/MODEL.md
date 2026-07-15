# v67_universal_specialist

One engine for **any** equity symbol.

At `generate()` time it classifies each code into a **family DNA** template (see `tools/specialist_factory.py`) and runs the parametric VA/VWAP/VPA stack with those gates.

## Honesty
- Not a unique ML model per stock.
- Not calibrated confidence.
- Use as a **candidate** against `v39d_confluence` / `v39b_live_adapt`.
- Mint permanent `v65_spec_*` only for names you trade heavily.
