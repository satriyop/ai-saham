# Factor Proving Lab (`research/`)

Status: offline research only — **zero decision authority**  
Related: `docs/research/engine_factor_inventory_and_ml_proving.md`  
Roadmap mode: Mode A — Offline research (`docs/roadmap/roadmap_to_machine_learning.md`)

## Purpose

Prove whether factors that feed Signal / Risk / Market Context are supported by
canonical observations and labels. Emit **factor cards** and optional YAML
*proposals*. Never change CLI verdicts, scores, risk gates, or production config.

## Layout

```text
research/
  README.md                 # this charter
  requirements.txt          # optional lab-only deps (do not add to src/)
  lab/
    panel.py                # read-only panel loader from data.db
  scripts/
    factor_card_vwap_buckets.py      # Package A — VWAP depth
    factor_card_bci_flow_sign.py     # Package A2 — BCI × flow sign
    factor_card_accum_components.py  # Package A1 — Accum component ablation
    factor_card_mce_factors.py       # Package D — MCE / regime
  artifacts/                # generated reports (gitignored except .gitkeep)
```

## Allowed dependencies (lab only)

May install into the active venv via `pip install -r research/requirements.txt`
or `pip install -e ".[research]"`:

- pandas / polars / duckdb — panels
- scikit-learn / statsmodels — calibration, linear models
- lightgbm / xgboost — optional shadow rankers (Package E only)
- jupyter / marimo — interactive exploration

Production `src/` and default `[project] dependencies` must remain free of
training frameworks.

## Forbidden

- Importing lab models from `src/domain`, `src/application`, or CLI adapters
- Writing to production YAML from scripts without an explicit human copy step
- Treating quarantine tables as promotion evidence
- Claiming SUCCESS labels are net-executable P&L
- Adding `research/` packages under hatch `packages = ["src"]`
- Naming a folder `research/lib/` (repo `.gitignore` ignores `lib/` globally)

## Contracts the lab must respect

| Contract | Source |
|----------|--------|
| Canonical observations | `candidate_observations` (not quarantine) |
| Labels | `signal_forward_labels` (default horizon `SWING_10D`) |
| Regime | `regime_observations` / `market_context_snapshots` by date |
| Output | markdown/JSON under `research/artifacts/` + stdout |

Join keys: `(ticker, snapshot_date ≈ signal_date, captured_at = observation_captured_at)`.

## Authority ladder

```text
factor card / experiment report
        → human review
        → (optional) YAML patch proposal
        → parked promotion lane / ADR if needed
        → ONLY THEN production config change
```

A green factor card has **no** authority.

## Quick start

```bash
# from repo root, using existing venv (stdlib + pandas already available)
.venv/bin/python research/scripts/factor_card_vwap_buckets.py
.venv/bin/python research/scripts/factor_card_bci_flow_sign.py
.venv/bin/python research/scripts/factor_card_accum_components.py
.venv/bin/python research/scripts/factor_card_mce_factors.py

# optional richer lab deps later
.venv/bin/pip install -e ".[research]"
```

Artifact path is printed on success.
