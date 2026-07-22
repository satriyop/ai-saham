# TUI Phase 4 — Research Corpus Health

Status: `DONE`

Roadmap: `docs/roadmap/roadmap_tui.md`

UX contract: `tasks/backlog/tui_ui_ux_design_spec.md`

Depends on: TUI Phases 0–2 and the completed UX contract/alignment task

Blocks: TUI Phase 5

## Task Metadata

- Task type: Feature
- Priority: Medium
- Semantic classification: `NON_SEMANTIC`
- Chosen decision: add a read-only cohort-isolated presentation of
  `ReportSignalReadinessUseCase`. Implement this option only.

## Problem Statement

Readiness output is easy to overstate. Cohorts cannot be pooled, the ephemeral
70/30 split is diagnostic, and patch eligibility is not promotion evidence. A
TUI must make those limits more visible rather than reinterpret them.

## Desired Outcome

The user supplies a target and, when required, semantic compatibility ID. One
worker call returns one `SignalReadinessReport`, displaying:

- parsed target and diagnostic-target status;
- selected/available cohorts;
- observation, label, unique-ticker, and unique-session counts;
- complete exclusion ledger;
- split mode and IS/OOS counts;
- readiness, patch eligibility, metrics, notes, blockers;
- explicit non-promotion status.

An empty corpus is honest and does not block other routes.

## Non-Goals

- No capture, backfill, labels, repair, replay/recompute, tuning, patch, or
  promotion.
- No statistical-validity chart, cohort pooling, alternate threshold/split, or AI.

## Ownership And Transport

```text
target + optional cohort
  -> ReportSignalReadinessRequest
  -> ReportSignalReadinessUseCase
  -> exact SignalReadinessReport
  -> ResearchHealthPresenter
  -> ResearchHealthScreen
```

Keep report intact to presenter. Adapter must not query repositories or
recompute counts, exclusions, deduplication, split, metrics, readiness, or
eligibility.

Phase 0 contracts (binding):

```text
composition dependencies: SQLiteCandidateObservationsRepository,
  SQLiteSignalForwardLabelsRepository, and ReportSignalReadinessUseCase only
request transport: preserve user target and optional cohort in
  ReportSignalReadinessRequest and preserve the exact SignalReadinessReport to
  the presenter; adapter rejects blank target before the call
target rules: use case strips target, requires a SignalLabelHorizon suffix, and
  parses canonical <profile>_<setup>_<bucket>_cap_<horizon> or diagnostic
  <profile>_<setup>_<horizon>; malformed target raises ValueError with its exact
  SignalReadinessTarget.parse message
cohort rules: supplied cohort is stripped and must exist; omitted cohort selects
  the sole available cohort. Zero cohorts returns blocker
  "no semantic_compatibility_id on canonical observations"; multiple return
  "mixed_semantic_cohorts". Both are valid fail-closed reports with no pooled
  IS/OOS rows.
expected ERROR: adapter ValueError("target must not be blank") with zero calls;
  SignalReadinessTarget.parse ValueError; sqlite3.Error or OSError from startup/
  repositories, always preserving class/message
typed unavailable: none; missing/unresolved cohorts are report blockers
constructor/startup side effects: both SQLite repository constructors run
  SqliteMigrationRunner and can create _schema_migrations, tables, indexes,
  columns, and migration rows. Product-read-only only.
invariants: malformed artifacts, incompatible identity/cohort objects, type
  errors, and impossible report states propagate to the outer boundary
```

## State And Authority Contract

- Blank target: adapter `ERROR`, zero use-case calls.
- Invalid target: `ERROR` with exact validation message.
- Zero observations/labels: `EMPTY`, while target/split/blockers/limitation show.
- Valid report with blockers: `READY`, never fabricated success.
- Multiple unresolved cohorts: visibly blocked, never pooled/silently selected.
- `promotion_eligible` is rendered exactly, never inferred.
- `DIAGNOSTIC ONLY — NOT PROMOTION EVIDENCE` is visible with split/eligibility.

## Exact File Boundary

Expected changes:

- `src/adapters/tui/composition.py`
- research-health controller/presenter/screen/minimal widgets
- focused controller/presenter/composition/headless tests

No product-layer, repository, schema, config, CLI research, or signal-program
change is authorized.

## Architecture Impact

- Domain: not touched
- Application: reuse unchanged
- Infrastructure: no implementation change; composition wiring only
- Adapter: readiness input/presentation
- New dependency/determinism impact: no
- Persistence: corpus reads only
- Adapter-owned policy: no

Layer plan:

```md
Layer plan:
- Domain: not touched
- Application: reuse only
- Infrastructure: no implementation changes
- Adapter: research-health UI path
```

## AI And Authority Declaration

No AI involved. Live signal/risk/TradeSetup is unchanged. This task changes no
authority, tuning eligibility, observation identity, label policy/schema, or
promotion gate.

## Implementation Checklist

- [x] Confirm prerequisites are `DONE`.
- [x] Copy exact Phase 0 contracts.
- [x] State one-report transport.
- [x] Wire only readiness use case.
- [x] Add target and optional cohort inputs.
- [x] Add generation-safe execution.
- [x] Render all counts/exclusions/metrics/notes/blockers.
- [x] Render empty and unresolved-cohort states.
- [x] Add permanent diagnostic/non-promotion label.
- [x] Add recording no-write and negative tests.

## Acceptance Criteria

- [x] One submission causes one call; blank target causes zero.
- [x] Request preserves target/cohort exactly.
- [x] Exact report is sole presenter source.
- [x] All exclusion fields show.
- [x] Cohorts are never pooled/normalized.
- [x] Empty corpus does not disable other routes.
- [x] Split and diagnostic-only warning always show.
- [x] Diagnostic, patch, and promotion statuses remain distinct.
- [x] No write-capable research/tuning/promotion dependency is composed.
- [x] Focused, architecture, full tests when feasible, and `git diff --check` pass.
- [x] Status becomes `DONE`; completion record is filled.

## Required Negative Tests

- Blank/malformed target cannot look valid.
- Multiple cohorts without selection cannot yield pooled metrics.
- Diagnostic-ready or patch-eligible cannot change promotion label.
- Presenter cannot drop exclusions/blockers.
- Any attempted write fails.
- Stale result cannot replace newer target/cohort.

## Do Not Interpret This As

- Do not add generate/capture/tuning/patch buttons.
- Do not call repositories from adapter.
- Do not pool/translate cohorts.
- Do not call diagnostic metrics validation/calibration proof.
- Do not hide blockers behind success styling.

## Verification

Run focused readiness UI tests, cohort/negative-authority tests, TUI/general
architecture tests, full suite when feasible, and `git diff --check`.

## Data, Persistence, And Documentation

- Reads canonical observations/labels through the readiness use case only.
- Writes nothing; no schema, config, cohort, label, or CLI contract changes.
- In-app Help must state the split and non-promotion limitation.
- Broader user documentation is finalized in Phase 5.

## Agent Execution Protocol

Before editing, confirm prerequisites, copy Phase 0 input/failure contracts,
restate one-report transport and cohort invariants, and list files. Stop if any
count/metric/eligibility would be recomputed in the adapter. Update completion
only after cohort-isolation and negative-authority tests pass.

## Completion Record

- Completed date: 2026-07-22
- Implementation commit: this phase completion commit
- Files changed: TUI composition/readiness capability, research-health controller/presenter/screen/widgets, shell/Help routes, focused fixtures/tests, architecture guards, and task statuses
- Request contract: blank target fails in the adapter with zero calls; otherwise one submission preserves the exact target and optional cohort in one `ReportSignalReadinessRequest`, and the exact returned `SignalReadinessReport` remains the presenter's sole source
- Cohort-isolation proof: unresolved mixed cohorts render both available IDs, no selected cohort, zero IS/OOS rows, missing metrics, and the exact `mixed_semantic_cohorts` blocker; no adapter normalization or pooling exists
- No-write proof: a real readiness use case test installs repository write tripwires; composition includes only the two canonical read repositories and `ReportSignalReadinessUseCase`; architecture guards reject capture, backfill, label-generation, repair, and tuning use cases
- Focused tests: `24 passed` for readiness contracts, composition, headless TUI behavior, and focused TUI boundaries; broader TUI plus architecture run `86 passed`
- Architecture tests: `37 passed`; TUI plus architecture broader run `86 passed`
- Full suite: `5740 passed, 3 failed`; failures match the pre-existing unrelated stale `_FakeScreenerConfig` cases (2) and canonical-window label-count regression (1)
- `git diff --check`: passed
- Deferred items: Phase 5 hardening/release decision; full-suite baseline failures remain outside TUI scope
