# SignalEngine Design Overview

This document extracts active architectural guidance from the historical
[SignalEngine refactor rationale](archive/signal_refactor_full_rationale.md).
It is design rationale, not proof of current implementation. Verify runtime
behavior against current config, code, and tests.

`ARCHITECTURE_DECISIONS.md`, `AI_AGENT_CHECKLIST.md`, current config, code, and
tests override stale planning text here.

## Executive Conclusion

The intended direction is not one larger composite score. It is a
profile-aware, evidence-based engine that separates:

1. Setup quality: is the chart structure good?
2. Institutional flow: is there real accumulation or distribution?
3. Context: is the market, sector, and liquidity regime supportive?
4. Alpha: is the ticker structurally attractive for the intended horizon?
5. Trigger: is the current window suitable for entry timing?
6. Decision policy: what action is allowed after score, coverage, conviction,
   regime, phase, and gates are considered?

The core design sequence is:

```text
quiet accumulation -> volatility compression -> confirmed price/volume pivot
-> regime-sized entry
```

Flow is not the primary entry trigger. Institutional accumulation and
foreign/broker flow primarily supply Alpha, eligibility, context, diagnostics,
and risk warnings. Raw net-buy intensity must not directly create `ENTER`.
Trigger authority should be dominated by price/volume confirmation such as a
positive pivot, directional squeeze release, volume expansion after dry-up,
VWAP reclaim, or support reclaim.

## Architecture Principles

### One Canonical Scoring Path

The intended production path has one source of truth:

```text
Raw local data
 -> evidence builders
 -> ticker profile diagnostics
 -> Alpha and Trigger scoring
 -> market/setup-regime eligibility and sizing constraints
 -> decision policy
 -> persisted observation
 -> walk-forward tuning
```

Archived or legacy scoring may support parity investigation, but it must not
become a second runtime authority.

### Preserve Score Meaning Across Regimes

Regime should constrain eligibility, thresholds, and sizing rather than hide a
multiplier inside the raw evidence score.

Prefer:

```text
score = 74
RISK_OFF ENTER threshold = 80
decision = WATCH
```

Avoid changing score meaning through an opaque expression such as
`score = 74 * 0.50`. Comparable raw scores support replay and calibration.

### Keep Hard-Gate Authority Separate

RiskEngine remains the only hard trade-risk gate authority. SignalEngine may
compute setup eligibility, max-decision caps, evidence quality, and decision
constraints, but it must not duplicate RiskEngine `BLOCKED` policy.

### Reuse Existing Deterministic Extension Points

Indicators, plugins, formulas, and strategy packages should produce normalized
evidence through existing registries and application workflows. They must not
directly override canonical SignalEngine decisions.

```text
indicator/plugin/formula output -> normalized evidence input
strategy rule match             -> setup-family evidence or diagnostic signal
strategy backtest result        -> empirical validation before authority
```

## Deterministic-First Rule

All scoring, evidence routing, state transitions, constraints, persistence,
and tuning inputs must be deterministic for the same local data and config.
AI may summarize evidence or propose bounded config changes, but AI must not be
the scoring or decision authority. The system must work fully without AI.

## Canonical Scoring Path

The canonical design separates evidence production from policy:

```text
evidence values
 -> canonical group scores
 -> Alpha/Trigger routing
 -> coverage and conviction
 -> setup/regime eligibility constraints
 -> DecisionPolicy
 -> persisted result and fingerprint
```

The canonical groups are:

```text
setup_quality
institutional_flow
market_context
company_quality_context
```

Alpha and Trigger are views over those group scores, not independent scoring
engines. A group defines its Alpha fraction per horizon; Trigger fraction is
derived as `1.0 - alpha_fraction`. Immediate price confirmation is required
before flow may contribute to Trigger authority.

Decision policy remains explicit. A typical ordering is:

```text
hard risk gate
 -> evidence coverage floor
 -> conviction floor
 -> failed/distribution phase constraints
 -> regime/setup max-decision constraints
 -> valid phase sequence and trigger requirements
 -> ENTER/WATCH/AVOID classification
```

Exact thresholds and ordering must be read from current config, code, and tests.

## Coverage Versus Conviction

Do not collapse availability and evidence strength into one confidence number.

```text
coverage_score:
  how much required evidence is available and fresh enough to use

conviction_score:
  how strongly the available evidence supports a directional conclusion
```

Rules:

```text
missing evidence     -> lowers coverage, not conviction
weak or mixed signal -> lowers conviction, not coverage
```

High conviction with low coverage should normally remain `WATCH` or
`INSUFFICIENT_DATA`; it must not become `ENTER` through conviction alone. High
coverage with low conviction should remain weak `WATCH` or `AVOID`.

## Evidence Authority Status

Implementation completeness is not empirical readiness. Evidence fields can be
typed, persisted, and displayed without having proven predictive value.

```text
DIAGNOSTIC = report-only; no score contribution
LOW_WEIGHT = contribution capped by configured status authority
PRODUCTION = normal configured weight is allowed
```

The authority registry belongs in validated config/domain policy and must be
enforced on every aggregation path. Promotion requires manual config change
after validator-approved walk-forward out-of-sample evidence. Tuning output
must not promote evidence automatically, and validators must reject weights
that exceed authority caps.

## Setup-Family Source Contract

Setup family must have one deterministic source contract. Candidate sources
may include:

1. explicit setup name/family from the application workflow;
2. deterministic mapping from a matched strategy or setup rule;
3. deterministic fallback classification when no explicit match exists.

When multiple setup families match, a config-backed priority resolves the
primary family. The primary family and all matches must be persisted for replay.
Priority must not allow mean reversion to shadow genuine accumulation unless
current config explicitly defines and tests that behavior.

Each production-calibrated setup declaration should identify:

```text
target universe
profile
horizon
setup family
primary flow track
required phase sequence
regime scope
patch eligibility gates
```

Thresholds must not be borrowed across patterns without out-of-sample
attribution supporting the transfer.

## Related Documents

- [Evidence Model](signal_engine_evidence_model.md)
- [Output Contract](signal_engine_output_contract.md)
- [Documentation Index](signal_refactor.md)
- [Archived Full Rationale](archive/signal_refactor_full_rationale.md)
