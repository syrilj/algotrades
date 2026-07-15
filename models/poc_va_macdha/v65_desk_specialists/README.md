# v65 desk specialists

Multi-symbol router for the desk trading bag.

| Symbol | Family | DNA source |
|--------|--------|------------|
| TSLA | megacap beta | tsla_F_lb30_block |
| MU | semi / memory | mu_A_block |
| IONQ (INFQ) | speculative 4H | ionq_A_4h_v8 |
| MSTR | crypto beta | mstr_crypto_beta |
| SNDK | semi / memory | sndk_semi_block |
| ASTS | speculative 4H | asts_spec_4h |
| META | megacap quality | meta_vwap_trend |
| GOOG | megacap quality | goog_vwap_trend |
| COIN | crypto beta | coin_crypto_beta |

CRWV is **not** in this router — use `v64_crwv_bounce`.

```bash
# discover
.venv/bin/python -c "import sys; sys.path.insert(0,'tools'); import dynamic_model_rank as d; print(d.discover_models(['v65_desk_specialists']))"
```
