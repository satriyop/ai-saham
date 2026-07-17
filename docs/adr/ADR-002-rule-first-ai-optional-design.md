# ADR-002: Rule-First, AI-Optional Design

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted
**Date:** Not recorded (legacy decision)
**Current implementation:** Rule-first is binding. AI may explain deterministic results or propose artifacts, but it cannot produce authoritative risk, signal, tuning, or application decisions.

## Decision

- The application must remain fully usable without AI.
- AI explanations consume already-computed results and cannot change them.
- AI-authored strategy, formula, configuration, or tuning artifacts remain untrusted until deterministic validation succeeds.
- Applying a validated change requires the repository's explicit human-controlled workflow.
- AI output must never bypass risk, evidence-promotion, configuration, or tuning guardrails.

## Current boundaries

Current swing calibration is deterministic and validator-gated. It uses
backtest evidence, review artifacts, patch validation, explicit application,
and verification under `saham trade`; it does not use the retired proposed
`SwingSignalTunerUseCase` contract.

See ADR-014 for the rejected full-AI bypass and ADR-027 for learning-loop
guardrails. Retired tier/class proposals remain available in git history.

## Rationale

This keeps model output auditable and prevents non-deterministic text from
becoming a hidden source of trading decisions.
