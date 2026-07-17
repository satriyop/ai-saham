# ADR-010: Risk Gates as Policy Layer

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted
**Date:** Not recorded (legacy decision)
**Current implementation:** Aligned — RiskEngine uses deterministic gates and exposes OPEN/BLOCKED semantics; profiles are retired.
**Decision**
Risk assessment is gate-based. A configured gate either fires or it does not,
producing `BLOCKED` or `OPEN`. Conservative/balanced/aggressive risk profiles
are retired from the current application because they no longer affect gate
outcomes.

**Implications**

* No prediction or trading execution — gates are deterministic policy only.
* Gate trigger thresholds (Piotroski F-score cutoff, market cap floor, liquidity floor, free float minimum, bandar distribution labels, technical gate thresholds) MUST be configurable in `config/risk_engine.yaml`.
* Each gate MUST declare an `enabled: bool` field in the YAML config. A gate with `enabled: false` is skipped entirely from the pipeline — no evaluation, no block decision. This supports backtesting, A/B comparison, and T2 Tuner proposals without code changes. See ADR-024 Engine Configurability Contract for the full gate YAML schema.
* Risk-engine YAML schema MUST be validated at startup via `yaml_loader.py`. Invalid config aborts startup with a clear error, not a silent fallback.
* Gate thresholds may be tightened based on market context (RISK_OFF/VOLATILE) — see ADR-029 for MarketContextEngine regime labels and integration rules.

**Implementation status (2026-06-29)**
`config/risk_engine.yaml` controls gate enablement and gate thresholds through
`create_risk_engine()`. The risk profile/sensitivity path and `--all` profile
comparison are removed.

**Rationale**
Separates math from policy. Config-driven thresholds enable the learning loop (ADR-027) to propose adjustments without requiring code changes, and enable calibration for IDX market specifics (ADR-028) without maintaining duplicate profile paths.
