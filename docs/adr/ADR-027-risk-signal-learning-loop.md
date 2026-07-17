# ADR-027: Risk/Signal Learning Loop

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted — implementation evolved
**Date:** 2026-06-24
**Current implementation:** Swing learning uses deterministic backtest, tuning review, patch validation, explicit apply, and status workflows under `saham trade`.

## Decision

Learning changes production policy only through an auditable evidence loop:

```text
point-in-time observations
  -> forward outcomes
  -> attribution / walk-forward evaluation
  -> readiness and out-of-sample checks
  -> non-authoritative review or patch artifact
  -> deterministic validation
  -> explicit human application
  -> verification and audit history
```

## Guardrails

- Attribution is evidence of association, not causal proof.
- Candidate observations and completed portfolio trades are different evidence
  populations and must not be conflated.
- Insufficient samples, missing provenance, unsupported targets, invalid bounds,
  or absent out-of-sample evidence make a proposed change ineligible.
- Tuning targets must be allowlisted and map to evidence the evaluator actually
  measured.
- Generated review/diff artifacts are non-authoritative. Creation of an artifact
  does not grant permission to apply it.
- Application requires deterministic validation and explicit user action; AI
  cannot make a patch eligible.

## Current CLI contract

Use live `saham trade --help`. The relevant commands currently include:

- `backtest-swing`
- `tune-swing`
- `review-tuning-swing`
- `validate-tuning-patch`
- `apply-tuning-patch`
- `tuning-status`

The proposed `swing learn record/grade/attribute/tune` commands,
`SwingSignalTunerUseCase`, and old journal schemas are retired and remain only
in git history.

## Related decisions

- ADR-002: AI remains non-authoritative.
- ADR-038: point-in-time enrichment requirements.
- ADR-041: canonical evidence input and promotion lifecycle.
