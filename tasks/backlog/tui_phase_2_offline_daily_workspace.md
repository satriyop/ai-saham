# TUI Phase 2 — Offline Daily Workspace

Status: `BLOCKED_BY_PHASE_1`

Roadmap: `docs/roadmap/roadmap_tui.md`

Depends on: TUI Phases 0 and 1

Blocks: TUI Phases 3–5

## Task Metadata

- Task type: Feature
- Priority: High
- Semantic classification: `NON_SEMANTIC`
- Chosen decision: make Daily a direct offline presentation of one
  `DailyBriefingUseCase` execution. Implement this option only.

## Problem Statement

The shell has no research content. Daily briefing already owns readiness,
authority, regime, candidate, and warning policy, but a TUI could accidentally
duplicate CLI display logic, probe providers, or calculate statuses itself.

## Desired Outcome

Launch and explicit Reload execute one injected `DailyBriefingUseCase` request
in a worker and render the `DailyBriefingResponse`:

- three data/session clocks;
- overall authority and dataset readiness;
- regime;
- opening observations;
- accumulation summary/candidates and setup-lens impact;
- warnings and honest empty/unavailable sections.

## Non-Goals

- No `GetSystemStatusUseCase`, provider health, or fetch.
- Reload means local recomputation, never provider refresh.
- No standalone candidate/ticker/readiness screen.
- No new thresholds, DTO, writes, AI, config, or timer.

## Ownership And Transport

```text
composition.py
  -> DailyBriefingUseCase + request factory
  -> one callable injected into DailyController
DailyController
  -> one generation-safe worker call
  -> exact DailyBriefingResponse
DailyPresenter
  -> immutable display-only view model
DailyScreen/widgets
  -> render only
```

No adapter component may re-query. Do not transport both the response and an
independently mutable copy of readiness/candidate source data.

Copy Phase 0 decisions before editing:

```text
composition dependencies:
request fields and sources:
excluded network dependencies:
constructor/startup side effects:
expected exceptions:
```

## State And Failure Contract

- `LOADING`: current generation running.
- `READY`: valid response, including `PARTIAL` or `NOT_READY` authority.
- `EMPTY`: universe count zero, regime absent, and all opening/accumulation
  collections empty.
- `UNAVAILABLE`: only if Phase 0 found an explicit typed unavailable result.
- `ERROR`: exact Phase 0-mapped exceptions.

`NOT_READY` is useful business output, not a crash. Show the blocker and never
show suppressed rankings as usable. Malformed DTO/invariant failures reach the
outer error boundary, never EMPTY.

## Exact File Boundary

Expected changes:

- `src/adapters/tui/composition.py`
- `controllers/daily_controller.py`
- `presenters/daily_presenter.py`
- `screens/daily_screen.py`
- minimal daily widgets/styles
- focused controller/presenter/composition/headless tests

No domain or application change is authorized. If the DTO is insufficient,
stop and revise the task instead of deriving business state in the adapter.

## Architecture Impact

- Domain: not touched
- Application: reuse unchanged
- Infrastructure: no implementation change; wiring in composition
- Adapter: Daily UI path
- New dependency: no
- Determinism impact: no
- Persistence: no intentional write; document known schema initialization
- Adapter-owned policy: no

Layer plan:

```md
Layer plan:
- Domain: not touched
- Application: reuse only
- Infrastructure: no implementation changes
- Adapter: daily composition/controller/presenter/screen/widgets
```

## AI And Authority Declaration

No AI involved. Presenter copies application actions/statuses. Signal, risk,
TradeSetup, setup, market context, evidence, observations, labels, and tuning
are unchanged.

## Implementation Checklist

- [ ] Confirm Phases 0/1 are `DONE`.
- [ ] Copy Phase 0 contract data above.
- [ ] State one-response transport before editing.
- [ ] Wire Daily use case.
- [ ] Add generation-safe controller.
- [ ] Add policy-free presenter.
- [ ] Render clocks and authority/readiness first.
- [ ] Render regime/opening/accumulation/setup-lens/warnings.
- [ ] Add explicit local Reload.
- [ ] Add READY/PARTIAL/NOT_READY/EMPTY/ERROR fixtures.
- [ ] Add no-provider/no-write recording fakes.

## Acceptance Criteria

- [ ] Launch makes exactly one Daily call; Reload makes one more.
- [ ] Navigation/focus makes no call.
- [ ] No provider-health/fetch capability is composed or invoked.
- [ ] Exact response is presenter source; no repository reread.
- [ ] Three clocks are distinct.
- [ ] Authority values are copied exactly.
- [ ] NOT_READY does not expose suppressed usable rankings.
- [ ] Empty sections do not fabricate neutral data.
- [ ] Warnings remain reachable.
- [ ] Late Reload cannot overwrite current generation.
- [ ] Tests run offline.
- [ ] Focused, architecture, full tests when feasible, and `git diff --check` pass.
- [ ] Status becomes `DONE`; completion record is filled.

## Required Negative Tests

- Provider fake fails if called.
- Write fake fails on every save/write method.
- PARTIAL/NOT_READY cannot look like READY authority.
- Empty response cannot fabricate regime/candidates.
- Presenter cannot invent unknown action/status.
- Late first result cannot replace Reload result.

## Do Not Interpret This As

- Do not reuse CLI Rich display.
- Do not call `GetSystemStatusUseCase`.
- Do not add freshness/readiness policy or auto-fetch.
- Do not hide warnings to fit.
- Do not add drilldown.

## Verification

Run focused controller/presenter/headless tests, TUI/general architecture tests,
full suite when feasible, and `git diff --check`.

## Data, Persistence, And Documentation

- Reads the same local cached inputs as `DailyBriefingUseCase`.
- Performs no intentional business write and no schema change.
- Does not claim byte-for-byte storage immutability unless Phase 0 proves it.
- No config or existing CLI-output contract changes.
- User documentation is deferred to Phase 5; screen Help must describe Reload
  as local recomputation.

## Agent Execution Protocol

Before editing, confirm prerequisite status, copy Phase 0 resolved contracts,
restate exact response transport and exception mapping, and list files. Stop if
any displayed business value requires adapter derivation. Update acceptance
checks only after focused and negative tests execute.

## Completion Record

- Completed date:
- Implementation commit:
- Files changed:
- Exact Daily request:
- Provider/write call proof:
- Focused tests:
- Architecture tests:
- Full suite:
- `git diff --check`:
- Deferred items:
