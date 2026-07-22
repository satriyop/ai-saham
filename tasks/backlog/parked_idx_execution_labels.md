# Parked — IDX Execution Labels

Status: `PARKED`

Retired sources:

- `tasks/done/audit_data_quality.md` → DQ-004 lean raw-label amendment
- `tasks/done/audit_signal_refactor_contract.md` → Task `IDX-EXECUTION-LABELS`
- `tasks/done/signal_evidence_program.md` (parked list)

Activation trigger: a promotion/evaluation/calibration task needs net-of-cost
tradeable outcomes (fees, taxes, slippage, fills, price limits).

Raw `outcome_basis="raw_market"` labels already close the research/ML validation
lane and `DQ-BASELINE-GATE`. Do not reopen DQ-004.

## Task Metadata

- Task type: Feature
- Priority: Medium (P1 when activated; required before net-return promotion)
- Semantic classification: `LABEL_POLICY` and `LABEL_SCHEMA`
- Chosen decision: introduce a distinct net-executable label contract beside
  raw market-outcome labels. Implement this option only.

## Problem Statement

Raw market labels measure price movement, not tradeable strategy result. Using
gross close returns for tuning or promotion overstates executable edge under IDX
costs, limits, gaps, and fill uncertainty.

## Desired Outcome

- Labels distinguish market movement from executable strategy result.
- Gross and net outcomes plus execution status are persisted under an
  execution-policy version.
- Untradeable / unsupported fills resolve to typed unavailable states, not
  fabricated fills or zero returns.
- Promotion metrics that need net returns consume only this contract.

## Non-Goals

- No order-book microstructure simulation beyond available data.
- No silent rewrite of existing raw_market rows into net-executable rows.
- No threshold tuning during label-contract introduction.
- No claim that raw_market labels are tradeable.

## Hard Invariants

- Clean break: new label schema/cohort; do not impersonate raw_market rows.
- Raw diagnostic labels cannot enter tuning or promotion metrics.
- Unsupported execution detail fails closed to `UNAVAILABLE` / `UNTRADEABLE`.
- Corporate-action / suspension / limit fixtures remain explicit.
- Deterministic offline computation only.

## Exact Work Boundary

Expected ownership when activated (revise after inventory):

- Label value objects / schema under `src/domain/`
- `GenerateSignalForwardLabelsUseCase` and related application services
- `sqlite_signal_forward_labels_repository.py` + migration
- Accumulation audit claim stamps that currently say `costs_modeled=false`
- Focused golden fixtures for costs/fills/limits

Forbidden:

- Reopening DQ-004 raw_market acceptance as incomplete
- Fabricating fills the data cannot support

## Required Reading

- `AGENT_QUICKSTART.md`, `AGENTS.md`, `TASK_TEMPLATE.md`
- `tasks/done/audit_data_quality.md` → DQ-004 lean amendment
- `tasks/done/audit_signal_refactor_contract.md` → `IDX-EXECUTION-LABELS`
- Current forward-label generator, value object, and repository

## Architecture Impact

```md
Layer plan:
- Domain: executable label identities, execution status enums, policy versions
- Application: cost/fill/window policy and generation orchestration
- Infrastructure: schema migration and repository persistence
- Adapter: explicit raw vs net rendering only
```

## AI And Authority Declaration

- No AI ground truth for fills or costs.
- Net-executable labels do not by themselves authorize evidence promotion;
  promotion still requires `parked_evidence_promotion_lane.md`.

## Exact Contract

Define and version:

```text
entry timestamp/model
fees / taxes
liquidity-tier slippage
price limits
opening gaps
suspensions / missing sessions
corporate actions
partial / unfilled / untradeable states
target/stop ordering ambiguity
execution-policy / entry-model / exit-model / cost-model / label-schema versions
```

Store gross and net outcomes plus execution status
(`FILLED` / `PARTIAL` / `UNFILLED` / `UNTRADEABLE` or explicit equivalent).
Untradeable is not zero return or failure.

Raw market-movement labels may remain for research when explicitly typed
`outcome_basis="raw_market"` and excluded from tuning/promotion.

## Implementation Checklist

- [ ] Confirm activation trigger and semantic classification.
- [ ] Design distinct schema/cohort from raw_market.
- [ ] Implement cost and fill policy with fail-closed unsupported cases.
- [ ] Persist execution-policy version on every net label.
- [ ] Golden fixtures for fees, limits, gaps, suspensions, corporate actions.
- [ ] Prove raw labels cannot enter promotion metrics.
- [ ] Update accum-audit claim stamps when they consume net labels.

## Acceptance Criteria

- [ ] Labels distinguish market movement from executable strategy result.
- [ ] Raw diagnostic labels cannot enter tuning or promotion metrics.
- [ ] Suspended/limit/unfilled/corporate-action fixtures are explicit.
- [ ] Unsupported execution detail fails to typed unavailable/untradeable.
- [ ] Promotion metrics that require net returns use this contract and report
      unavailable rate.
- [ ] Focused tests + `git diff --check` pass.

## Do Not Interpret This As

- Do not invent order-book certainty.
- Do not adjust prices across corporate actions silently; invalidate or model
  explicitly under the new policy.
- Do not treat raw_market research labels as tradeable edge.
- Do not start without a named consumer that needs net outcomes.

## Completion Record

- Completed date:
- Implementation commit:
- Verified source revision:
- Files changed:
- Commands run:
- Verification result:
- Deferred items and owner:
