# ADR-027: Risk/Signal Learning Loop

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted — amended by [ADR-049](ADR-049-database-owned-learning-pipeline-clean-break.md)
**Date:** 2026-06-24
**Current implementation:** Database-owned typed evaluations, proposals, paired
OOS validations, explicit YAML application, and application audit records.

## Decision

Learning changes production policy only through an auditable evidence loop:

```text
point-in-time observations
  -> forward outcomes
  -> attribution / walk-forward evaluation
  -> readiness and out-of-sample checks
  -> immutable database-owned policy proposal
  -> deterministic validation
  -> explicit human application
  -> reread verification and database-owned audit history
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

Use live `saham trade swing --help`: `backtest`, `tune`, `review`, `validate`,
`apply`, and `status`. File patch and review-journal workflows are retired.

## Related decisions

- ADR-002: AI remains non-authoritative.
- ADR-038: point-in-time enrichment requirements.
- ADR-041: canonical evidence input and promotion lifecycle.
