# poc_va_gex

Options / GEX family. Does **not** replace `poc_va_macdha` stock models.

See `GEX_GUIDE.md` for math + architecture.

## Versions

| Version | Role | Status |
|---------|------|--------|
| research/* | Volume-z meta, GEX snapshots, LSE helpers | active research |
| `v1_node_cloud` | Live **reactive** guide: MA cloud compass → which GEX node (wall/flip) spot is heading toward | explore |

## Architecture note (2026-07-11)

Locked playbook still holds: Primary → SIDE · Secondary → WHETHER/HOW MUCH.

- **Historical / backtest SIDE** for the react-to-nodes idea: `poc_va_macdha/v19_node_cloud` (VAL/POC/VAH nodes + EMA cloud; no options history required).
- **Live options nodes**: `v1_node_cloud/node_cloud_guide.py` overlays call_wall / put_wall / flip once chain data exists.
- Classic GEX meta (size/skip on existing candidates) remains the `HYPOTHESIS.md` amplifier path — complementary, not conflicting.
