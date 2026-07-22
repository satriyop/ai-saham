> [!NOTE]
> **Retired 2026-07-22.** Lane indexes removed. Use `tasks/backlog/parked_*.md`
> directly (especially `parked_evidence_promotion_lane.md` for promotion).
> Keep this file as historical orientation only.

# Deterministic Signal Engine Work

## Scope

Active/parked implementation lane for correcting and completing the existing
deterministic signal engine. None of these tasks requires an ML model, an AI
API, or a decision challenger.

Use this document to answer:

> What must be fixed in the application that exists today?

## Gate Snapshot (2026-07-22)

| Gate | State |
|---|---|
| `DQ-CONTRACT-GATE` | Closed |
| `LIVE-CONTRACT-GATE` | Closed |
| `CANONICAL-EVIDENCE-GATE` | Lean-closed |
| `DQ-BASELINE-GATE` | Closed |

Retired mega-docs (historical contracts and completion evidence):

- `tasks/done/signal_evidence_program.md`
- `tasks/done/audit_data_quality.md`
- `tasks/done/audit_signal_refactor_contract.md`

## Agent Entry Point

1. Prefer a `Ready` / activated parked task below over rediscovering archived
   mega-docs.
2. Verify task state against current code and tests before editing.
3. Do not start evidence promotion without
   `parked_evidence_promotion_lane.md` activation criteria.
4. Clean-break policy in `AGENT_QUICKSTART.md` still applies to every residual
   signal-evidence task.

## Live Contract (Done)

| Order | Task | State | Evidence |
|---:|---|---|---|
| 1 | `BENCHMARK-EXCESS-RETURN` | Done | `5b9f3f0` |
| 2 | `CANONICAL-EVIDENCE-BOUNDARY` | Done | `2526608` |
| 3 | `AUTHORITY-COVERAGE-READINESS` | Done | `8c4dee1` |
| 4 | `ARTIFACT-IDENTITY` foundation | Done | `2b0bff1`; lean capture via DQ-003 |
| 5 | `EVIDENCE-BACKED-ASSESSMENT` | Done | `4262ae3` |
| 6 | `CENTRAL-EVIDENCE-AUTHORITY` | Done | `c93363a` / `952d106` |
| 7 | `RETIRE-LEGACY-SIX-FACTOR-BASELINE` | Done | `59bd03b`, `b0e77d9` |
| 8 | `SECTOR-CONTEXT-IDENTITY` | Done | `532135c` |

Archived detailed contracts: `tasks/done/audit_signal_refactor_contract.md`.

## Canonical Data Baseline (Done)

DQ-000…DQ-008, DQ-010, DQ-011 lean-closed / closed. Archived:
`tasks/done/audit_data_quality.md` and companion `tasks/done/dq_*_lean_*.md`
plans. CLI remount: `tasks/done/improvement_cli_restructure.md`.

## Residual Parked Tasks

| Task file | State | Wake when |
|---|---|---|
| [`parked_dq_009_sentiment_outcome_audit.md`](parked_dq_009_sentiment_outcome_audit.md) | Parked | Sentiment calibration / sentiment CLI migration |
| [`parked_idx_execution_labels.md`](parked_idx_execution_labels.md) | Parked | Net-of-cost / tradeable outcomes required |
| [`parked_artifact_identity_apparatus.md`](parked_artifact_identity_apparatus.md) | Parked | Named identity-apparatus trigger |
| [`parked_screen_rejected_controls_and_universe.md`](parked_screen_rejected_controls_and_universe.md) | Parked | Recall/filter-value or unbiased membership needed |
| [`parked_named_swing_setup_capture.md`](parked_named_swing_setup_capture.md) | Parked | Named swing-setup labels/readiness/tuning requested |
| [`parked_output_contract_ownership.md`](parked_output_contract_ownership.md) | Parked / non-blocking | Docs hygiene pass |
| [`parked_evidence_promotion_lane.md`](parked_evidence_promotion_lane.md) | Parked | Named evidence candidate + activation criteria |
| [`evidence_validation_and_promotion.md`](evidence_validation_and_promotion.md) | Lane index | Same as promotion lane |

### Capture Boundary (still binding)

- Interactive `screen` and `analyze` commands are read-only assessment paths.
- Canonical capture is a separate idempotent, universe-driven application use
  case.
- Current `screen accum --multi` cron is not canonical capture.
- CLI/cron migration remains owned by CLI-003 after DQ-011; no temporary
  screen-side write path.

## LIVE-CONTRACT-GATE Close Criteria

**State: satisfied** after `532135c` (`SECTOR-CONTEXT-IDENTITY`).

- [x] one canonical evidence-backed assessment path
- [x] screen and swing preserve the same evidence/provenance contract
- [x] no flags-only canonical assessment path
- [x] diagnostic evidence cannot gain authority from producer config
- [x] no public six-factor signal-shaped result
- [x] canonical artifacts bind compatible identity dimensions (lean)
- [x] partial / unavailable / no evidence remain distinct
- [x] sector evidence uses truthful canonical identity

## Do Not Interpret This As

- Do not tune weights or thresholds while repairing contracts.
- Do not promote diagnostic evidence because implementation is complete.
- Do not implement promotion infrastructure without a concrete candidate.
- Do not add ML or API challenger code to satisfy closed live/DQ gates.
- Do not reopen lean-closed DQ tasks to satisfy parked product scope.

## Solo-Project Proportionality

- Prefer parked task files over expanding archived mega-docs.
- Graduate one parked trigger at a time.
- Keep net-executable labels, full identity apparatus, and promotion as
  separate activations.
