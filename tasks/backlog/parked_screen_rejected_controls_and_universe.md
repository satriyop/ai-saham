# Parked — Screen-Rejected Controls And PIT Universe

Status: `PARKED`

Retired sources:

- `tasks/done/audit_signal_refactor_contract.md` → Task `CONTROL-POPULATION`
- `tasks/done/audit_data_quality.md` → DQ-003 Slice C finding + deferrals
- `tasks/done/signal_evidence_program.md` (parked list)

Lean `CONTROL-POPULATION` for `accumulation-discovery` is **closed** with
stamped limitations (`contains_control_population=false`, current-universe
survivorship disclosure). This task owns only the parked product gaps.

## Task Metadata

- Task type: Feature
- Priority: Medium when a consumer needs recall/filter-value or unbiased
  membership; otherwise parked
- Semantic classification: `OBSERVATION_SCHEMA` (and possibly
  `CONFIG_MATERIAL` if capture filter policy changes)
- Chosen decision: when triggered, capture genuine screen-rejected controls
  and/or reconstruct PIT universe membership as a deliberate product mode.
  Implement only the triggered slice.

## Activation Triggers

| Trigger | Wake this parked slice |
|---|---|
| Readiness / evaluation needs screener recall or filter-value claims | Genuine screen-rejected control capture |
| Survivorship must be corrected, not merely disclosed | PIT historical universe-membership platform |
| A named consumer refuses candidate-only datasets | Both slices as required by that consumer |

## Problem Statement

Production capture currently disables reject gates
(`disable_score_filters=True`, market-cap/Piotroski floors at 0), so every
evaluated ticker persists as `screen_result="pass"`. Candidate-only corpora
cannot honestly measure false negatives or filter value. Current-universe
membership is survivorship-biased and only disclosed, not corrected.

## Desired Outcome

Triggered slice A — rejected controls:

- Capture path can persist genuine `screen_result != "pass"` controls under
  one shared PIT cutoff with selected candidates.
- Tightening a filter cannot hide rejected outcomes.
- `contains_control_population` becomes true only when real rejected rows exist.

Triggered slice B — PIT universe:

- Historical eligible-universe membership is reconstructed or the run is marked
  invalid for unbiased claims.
- Delisted/suspended/unavailable names remain represented truthfully.

## Non-Goals

- No faking `rejected_*` rows in golden fixtures without a real capture mode.
- No reopening DQ-003 lean close criteria.
- No using interactive `screen` / `analyze` as writers.
- No claiming recall authority while still candidate-only.

## Hard Invariants

- Selected and control rows share source cutoff/config identity but cannot
  overwrite one another.
- Ordinary screen/analyze remain read-only assessment paths.
- Capture stays a dedicated application use case.
- Clean break if observation meaning changes.
- Candidate-only datasets remain recall-ineligible until slice A lands.

## Exact Work Boundary

Likely touchpoints when activated:

- Accumulation capture / backfill request construction (reject-gate policy)
- `RecordAccumulationObservationsUseCase` / persister / backfill response stamps
- Universe membership source identity and survivorship policy
- Readiness / evaluation consumers that check `contains_control_population`

Product decision required before coding slice A: either stop disabling reject
gates on the canonical capture path, or define a separate capture mode. Do not
silently change live screen defaults.

## Required Reading

- `AGENT_QUICKSTART.md`, `AGENTS.md`, `TASK_TEMPLATE.md`
- `tasks/done/audit_data_quality.md` → DQ-003 Slice C finding
- `tasks/done/audit_signal_refactor_contract.md` → `CONTROL-POPULATION`
- Current backfill composition and screen request filter flags

## Architecture Impact

```md
Layer plan:
- Domain: observation inclusion/exclusion identities if needed
- Application: capture mode / filter policy / universe membership orchestration
- Infrastructure: membership warehouse or source adapters if slice B woken
- Adapter: thin CLI flags for capture mode only; no policy ownership
```

## Exact Contract

For each observation session (full original scope — deliver only woken parts):

- Persist inclusion/exclusion status, rejection stage/reasons, pre-filter
  measurements, missing-data state, and candidate rank.
- Delisted, suspended, stale, and unavailable names remain represented.
- Backfill reconstructs historical universe or marks invalid.
- Report inserted / already-existing / unavailable / rejected / failed counts.
- Re-running the same semantic capture must not increase sample size.

## Implementation Checklist

- [ ] Confirm which trigger fired and which slice is authorized.
- [ ] For slice A: record the product decision (enable gates vs separate mode).
- [ ] Implement capture without making interactive screen a writer.
- [ ] Update `contains_control_population` / recall eligibility honestly.
- [ ] Golden PIT fixtures for selected + rejected + unavailable.
- [ ] For slice B: membership reconstruction or hard invalidation path.

## Acceptance Criteria

- [ ] Triggered slice only; lean stamped limitations remain true until delivered.
- [ ] Genuine rejected controls (slice A) or PIT membership (slice B) meet the
      contract above.
- [ ] Candidate-only corpora still cannot claim recall until slice A is real.
- [ ] Focused tests + `git diff --check` pass.

## Do Not Interpret This As

- Do not stub reject gates in tests and call controls real.
- Do not loosen DQ-003 golden fixtures to invent rejected rows.
- Do not treat survivorship disclosure as unbiased membership.
- Do not implement `NAMED-SWING-SETUP-CAPTURE` here
  (`parked_named_swing_setup_capture.md`).

## Completion Record

- Completed date:
- Trigger / slice delivered:
- Implementation commit:
- Files changed:
- Commands run:
- Verification result:
- Remaining parked slices:
