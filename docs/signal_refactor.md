# Signal Engine Refactor Documentation Index

This documentation set preserves the SignalEngine refactor rationale while
separating active design guidance from historical planning material.

## Current Status

These documents describe design rationale only. Implementation status must be
checked against current code and tests. Statements about planned phases,
thresholds, rollout order, or readiness may no longer describe runtime behavior.

## Active Guidance

- [SignalEngine Design Overview](signal_engine_design_overview.md) — executive
  conclusion, architecture principles, canonical scoring path, coverage versus
  conviction, evidence authority, and setup-family source contracts.
- [SignalEngine Evidence Model](signal_engine_evidence_model.md) — setup phases,
  trigger patterns, scoring evidence, institutional flow, ticker profiles,
  Alpha/Trigger routing, sector and regime context, and seasonality/events.
- [SignalEngine Output Contract](signal_engine_output_contract.md) — group model,
  persisted fingerprints, output shape, acceptance criteria, and layer plan for
  future work.

## Archive

- [Archived Full Signal Refactor Rationale](archive/signal_refactor_full_rationale.md)
  preserves the complete long-form historical document and its implementation
  phases, examples, calibration proposals, and detailed reasoning.

## Authority Warning

`ARCHITECTURE_DECISIONS.md`, `AI_AGENT_CHECKLIST.md`, current config, code, and
tests override stale planning text in this documentation set. This index and the
linked design documents do not change ADR/checklist authority, runtime policy,
or implemented contracts.
