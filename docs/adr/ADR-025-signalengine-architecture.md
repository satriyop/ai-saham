# ADR-025: SignalEngine Architecture

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted — canonical scorer evolved
**Date:** 2026-06-24
**Current implementation:** SignalEngine is the sole facade for production signal assessment; canonical scoring delegates to `AssessSignalEvidenceUseCase` and current config-backed policy.

## Decision

- No use case, workflow, adapter, or CLI renderer may independently compute a
  production composite signal score.
- Canonical signal inputs must carry explicit evidence authority, availability,
  provenance, and as-of semantics.
- Missing evidence is not neutral evidence. Signal authority coverage, directional signal score, and typed setup
  readiness remain separate concepts. Diagnostic evidence coverage or
  conviction cannot independently authorize or veto ENTER.
- Market-context conditioning, when requested, occurs inside the canonical
  signal path before `TradeSetup` composition; see ADR-037.
- Classification and decision constraints are deterministic and config-backed.

## Current implementation pointers

- `src/application/services/signal_engine.py`
- `src/application/use_case/assess_signal_evidence_use_case.py`
- `src/domain/value_objects/signal_assessment.py`
- `config/signal_engine.yaml`
- ADR-041 for the target canonical pre-score evidence boundary

The original six-factor `SignalContext`, weights, thresholds, and scoring
formula are retired implementation detail. AssessSignalUseCase and its six-factor configuration remain temporarily in
active source as an archived audit/parity baseline pending HIGH-3. They have
no production scoring or authority role and must not be used as a production
contract.

## Consequences

- New signal evidence enters through the canonical evidence/scoring boundary.
- Display-only and compatibility scores cannot silently gain production
  authority.
- Current source, tests, and config determine exact factor stages and numeric
  thresholds.
