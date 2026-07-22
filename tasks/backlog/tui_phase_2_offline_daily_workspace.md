# TUI Phase 2 — Offline Daily Workspace

Status: `DONE`

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

Phase 0 decisions (binding):

```text
composition dependencies: SQLite market/broker repositories; effective-session
  resolver; MarketContextEngine; configured AccumulationScreenUseCase with
  local cached enrichment, signal/risk engines, rules/indicator dependencies;
  YamlUniverseConfigLoader; DailySetupLensImpactUseCase with four setup-bound
  local-only swing workflows
request: DailyBriefingRequest(
  universe=app_config.analysis.universe,
  top=3,
  as_of_date=None,
  opening_data_dir=Path("data/opening"),
  universe_config_path=Path("config/universes.yaml"),
)
transport: preserve the exact DailyBriefingResponse through the controller to
  the presenter; presenter fields are the three clocks, historical/universe
  metadata, freshness/readiness/authority, regime, opening sections,
  accumulation summary/daily candidates, setup-lens impact, and warnings
excluded network dependencies: GetSystemStatusUseCase, auto_refresh_swing_data,
  fetch_swing_sentiment, and any provider-health/fetch callable; inject
  `_forbid_tui_refresh` and `_forbid_tui_sentiment` from `composition.py`; each
  raises RuntimeError with the exact Phase 0 message if called, while cached
  Stockbit providers retain api_client=None
excluded write dependencies: watchlist save, observation capture, labels,
  journal, tuning, patch, and promotion
constructor/startup side effects: market/broker/candidate-observation,
  corporate-action, and cached Stockbit repository/provider constructors can
  create/migrate schemas; broker initialization can delete superseded Stockbit
  summary rows. V1 is product-read-only, not byte-for-byte immutable.
expected ERROR: composition/startup ValueError, RulesError subclasses,
  CorporateActionPolicyConfigError, sqlite3.Error, MarketDataRepositoryError,
  BrokerDataRepositoryError, and OSError, preserving class/message
typed unavailable: none at screen level; dataset UNAVAILABLE and optional
  absence remain inside a valid response. Invariants propagate outward.
```

Resolved prerequisite: `tasks/backlog/tui_daily_failure_boundary_prerequisite.md`
is `DONE`. `DailyBriefingUseCase` propagates dependency and outer setup-lens
failures; `DailySetupLensImpactUseCase` degrades only typed
`SwingAnalysisDataUnavailable`; optional opening file/decode errors remain
warnings. Phase 2 remains blocked only by Phase 1.

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

- [x] Confirm Phases 0/1 are `DONE`.
- [x] Copy Phase 0 contract data above.
- [x] State one-response transport before editing.
- [x] Wire Daily use case.
- [x] Add generation-safe controller.
- [x] Add policy-free presenter.
- [x] Render clocks and authority/readiness first.
- [x] Render regime/opening/accumulation/setup-lens/warnings.
- [x] Add explicit local Reload.
- [x] Add READY/PARTIAL/NOT_READY/EMPTY/ERROR fixtures.
- [x] Add no-provider/no-write recording fakes.

## Acceptance Criteria

- [x] Launch makes exactly one Daily call; Reload makes one more.
- [x] Navigation/focus makes no call.
- [x] No provider-health/fetch capability is composed or invoked.
- [x] Exact response is presenter source; no repository reread.
- [x] Three clocks are distinct.
- [x] Authority values are copied exactly.
- [x] NOT_READY does not expose suppressed usable rankings.
- [x] Empty sections do not fabricate neutral data.
- [x] Warnings remain reachable.
- [x] Late Reload cannot overwrite current generation.
- [x] Tests run offline.
- [x] Focused and architecture tests plus `git diff --check` pass; full suite ran with only three documented unrelated baseline failures.
- [x] Status becomes `DONE`; completion record is filled.

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

- Completed date: 2026-07-22
- Implementation commit: this phase completion commit
- Files changed: TUI composition, controller, presenter, Daily screen/widgets, Help text, focused tests, and this backlog record
- Exact Daily request: `DailyBriefingRequest(universe=app_config.analysis.universe, top=3, as_of_date=None, opening_data_dir=Path("data/opening"), universe_config_path=Path("config/universes.yaml"))`
- Provider/write call proof: architecture guard passed; cached Stockbit providers use `api_client=None`; exact refresh/sentiment tripwires and failing provider/write fakes passed; real local composition smoke returned a valid `PARTIAL` response
- Focused tests: `28 passed` (`tests/adapters/tui` plus TUI boundary architecture test)
- Architecture tests: `92 passed` (`tests/architecture`, TUI tests, and existing Daily CLI tests)
- Full suite: `5714 passed, 3 failed`; failures are the pre-existing unrelated stale `_FakeScreenerConfig` cases (2) and canonical-window label-count regression (1)
- `git diff --check`: passed
- Deferred items: full-suite baseline failures remain outside TUI Phase 2 scope
