# ADR-025: SignalEngine Architecture

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted — contextual policy contracts
**Date:** 2026-06-24
**Current implementation:** `SignalEngine` is the sole facade for authoritative
production signal assessment. Its public methods name the workflow purpose and
bind the matching policy contract.

## Decision

- No use case, workflow, adapter, or CLI renderer may independently compute a
  production signal score.
- The public production policies are:
  - `evaluate_pre_open_auction_direction()` →
    `PRE_OPEN_AUCTION_DIRECTION` / `pre_open_auction_direction.v1`;
  - `evaluate_accumulation_discovery()` →
    `ACCUMULATION_DISCOVERY` / `accumulation_discovery.v1`;
  - `evaluate_swing_trade_setup()` →
    `SWING_TRADE_SETUP` / `swing_trade_setup.v1`.
- Every `SignalAssessment` carries a required `SignalAssessmentIdentity`.
  Missing, unknown, or mismatched purpose/contract pairs fail closed.
- `evaluate_with_context()` is retired. There is no alias, purpose inference,
  dual reader, or translation from the removed generic API.
- Canonical signal inputs must carry explicit evidence authority, availability,
  provenance, and as-of semantics.
- Missing evidence is not neutral evidence. Signal authority coverage, directional signal score, and typed setup
  readiness remain separate concepts. Diagnostic evidence coverage or
  conviction cannot independently authorize or veto ENTER.
- Market-context conditioning, when requested, occurs inside the authoritative
  assessment path before `TradeSetup` composition; see ADR-037.
- Classification and decision constraints are deterministic and config-backed.

`canonical` is reserved for authoritative production truth: evidence,
observations, decisions, and explicit champion/preview/challenger distinctions.
It is not a synonym for a generic policy, scorer, workflow purpose, or lane.
Accumulation and swing share one private setup/flow evidence scorer without
sharing identity. Pre-open retains its auction-direction scorer and never
fabricates setup/flow evidence.

## Current implementation pointers

- `src/application/services/signal_engine.py`
- `src/application/use_case/assess_signal_evidence_use_case.py`
- `src/domain/value_objects/signal_assessment.py`
- `config/signal_engine.yaml`
- ADR-041 for the authoritative pre-score evidence boundary

The original six-factor `SignalContext`, weights, thresholds, and scoring
formula are retired implementation detail. AssessSignalUseCase and its
six-factor configuration remain in active source as an archived audit/parity
baseline. They have no production scoring or authority role and must not be
used as a production contract.

## Consequences

- New signal evidence enters through the authoritative evidence/scoring boundary.
- Display-only and compatibility scores cannot silently gain production
  authority.
- Current source, tests, and config determine exact factor stages and numeric
  thresholds.
- Contextual identity changes routing and persisted meaning, not scoring
  arithmetic, risk behavior, or `TradeSetup` composition.
