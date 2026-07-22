# TUI Milestone A — Personal Command Center

Status: `BACKLOG`

Roadmap: `docs/roadmap/roadmap_tui.md`

Depends on: `tasks/backlog/tui_remove_research_screen.md`

Blocks: TUI Milestone B

## Task Metadata

- Task type: Feature / workflow redesign
- Priority: High
- Semantic classification: `NON_SEMANTIC`
- Chosen decision: turn the existing cached Daily screen into a personal
  command center with an explicit market-data update workflow. Implement this
  option only.

## Problem Statement

The current TUI shows a long cached briefing but stops when data is stale. The
personal user must leave the workspace, remember a CLI command, update the
correct universe, return, and reload. That breaks the highest-frequency daily
workflow and makes the TUI less useful than the CLI.

The problem is not missing status detail. The user needs one honest path from
stale data to an updated market view and shortlist.

## Desired Outcome

Opening the TUI shows a compact Dashboard with:

- active universe and effective EOD/session date;
- clear cache readiness and last successful update;
- market regime/breadth summary;
- actionable warnings;
- a short candidate table;
- explicit `Update data`, `Reload local`, `Open Discover`, and `Open ticker`
  actions.

`Update data` displays scope and provider plan before execution, reports
per-ticker progress/partial failures, persists through the existing fetch
workflow, and returns one application-owned result containing the refresh
outcome plus the recomputed briefing.

## User Journey

```text
launch
  -> see DATA STALE for LQ45
  -> choose Update data
  -> review scope: LQ45, history/default providers, cache write
  -> confirm
  -> see progress and failures
  -> receive updated Dashboard
  -> open Discover or selected ticker
```

The user never types a CLI command, database path, provider object, or raw
configuration key.

## Chosen Application Contract

Add an application-owned orchestration boundary:

```text
RefreshDailyWorkspaceRequest
  universe: str
  tickers: tuple[str, ...]
  days: int
  force_refresh: bool
  components: ALL | CANDLES_ONLY | BROKER_ONLY
  include_meta: bool
  include_enrichment: bool
  include_calendar: bool
  briefing_top: int

RefreshDailyWorkspaceResult
  refresh: FetchMarketCommandWorkflowResult
  briefing: DailyBriefingResponse
  warnings: tuple[str, ...]

RefreshDailyWorkspaceUseCase.execute(
  request,
  on_start=None,
  on_ticker_complete=None,
) -> RefreshDailyWorkspaceResult
```

The request contains business choices only. It must not contain `Path`, a
provider object/name, database location, config loader, or infrastructure
option. Provider/config resolution belongs in composition.

Add or extract a configured application port/capability such as:

```text
RefreshDailyMarketData.execute(
  business request + progress callbacks
) -> FetchMarketCommandWorkflowResult
```

Its infrastructure composition adapts the existing
`FetchMarketCommandWorkflowUseCase` and supplies database/provider/config
details. The adapter passes neither those details nor the existing command-
oriented request.

Add a pre-execution preview boundary:

```text
PreviewDailyWorkspaceRefreshUseCase.execute(
  RefreshDailyWorkspaceRequest
) -> DailyWorkspaceRefreshPlan

DailyWorkspaceRefreshPlan
  universe and resolved ticker count
  history days and selected components
  resolved candle/broker provider labels
  meta/enrichment/calendar inclusion
  exact local-write disclosure
  warnings/blockers
```

The controller retains the exact `RefreshDailyWorkspaceRequest` used for the
preview and submits that same object after confirmation. It does not rebuild a
request from labels or plan text. A blocking precondition disables Confirm.

The use case owns the sequence:

```text
configured RefreshDailyMarketData capability
  -> existing FetchMarketCommandWorkflowUseCase internally
  -> only after successful/partially successful completion
  -> DailyBriefingUseCase
  -> one RefreshDailyWorkspaceResult
```

The TUI must not independently call fetch and briefing use cases and combine
their results. Progress callbacks carry the existing typed start/ticker events;
they may update progress only and are not the final source of truth.

Expected provider absence and individual ticker failures remain exactly as the
existing fetch workflow represents them. Invalid request/configuration and
contract failures propagate to ERROR; they are not converted to a stale but
apparently valid Dashboard.

Local `Reload` continues to call `DailyBriefingUseCase` only and performs no
provider access or intentional write.

## UX Contract

### Dashboard hierarchy

1. Data state and Update action.
2. Market regime/breadth.
3. Warnings requiring attention.
4. Top candidates.
5. Secondary clocks/details behind disclosure.

Do not preserve the current one-section-after-another dump merely because all
fields exist.

### Update confirmation

Show:

- universe/ticker count;
- history period;
- candle and broker provider names;
- whether enrichment/calendar/meta are included;
- `This updates the local cache`;
- Confirm and Cancel.

No provider secret, token, internal path, or payload is displayed.

### Progress and completion

- Visible overall count and current ticker.
- Per-component success/skip/failure summary.
- Cancellation stops accepting late progress/results; it does not claim remote
  calls or committed writes were rolled back.
- Partial success remains PARTIAL with exact failed tickers/components.
- The prior valid Dashboard remains visible until a new briefing succeeds.

### Shared visual system and shell

This milestone owns the visual foundation used by every later workspace.
Implement this option only:

- one centralized semantic theme with tokens for canvas, surface, raised
  surface, border, primary/muted text, accent/focus, positive, caution,
  negative, unavailable, and selected row;
- reusable application header, route navigation, workspace heading, status
  badge, action bar, section heading, metric, data table, empty/error state,
  confirmation, and Help/key-hint components;
- a restrained visual style: dark neutral canvas, high-contrast text, one
  primary accent, semantic state accents, minimal borders, and no decorative
  gradients, blinking, or emoji-dependent icons;
- a wide layout at `120x40` with market context and candidate summary visible
  together; a compact `80x24` layout that stacks secondary content without
  hiding data status, primary warning, Update, or the focused control;
- a minimum-size guard below `80x24` that asks the user to resize rather than
  rendering clipped controls;
- status text/symbols that remain understandable with color disabled.

Route screens consume these shared primitives. They may choose composition and
content density, but cannot define independent palettes or incompatible focus,
table, dialog, and status styles.

## Scope

- application preview plus refresh-and-briefing workflow, configured refresh
  port/capability, and tests;
- TUI Dashboard controller/presenter/screen redesign;
- explicit confirmation/progress UI;
- universe selection using configured friendly options;
- composition wiring through existing fetch and briefing dependencies;
- Help and focused documentation updates.

## Non-Goals

- No automatic update on launch, mount, focus, schedule, or navigation.
- No arbitrary provider/config editor.
- No corpus capture, labeling, watchlist save, journal write, or tuning.
- No direct infrastructure call from screen/controller/presenter.
- No score, risk, setup, or evidence-authority changes.
- No order execution.

## Architecture Impact

- Domain: not touched
- Application: add refresh-and-briefing orchestration DTO/use case
- Infrastructure: reuse existing fetch/briefing composition; no new provider
- Adapter: Dashboard, confirmation, progress, composition
- Persistence: existing explicit fetch cache writes only
- Determinism: briefing remains deterministic for resulting persisted inputs;
  provider refresh is an explicit I/O action
- AI: none required

Layer plan:

```md
Layer plan:
- Domain: not touched
- Application: RefreshDailyWorkspaceUseCase and typed result
- Infrastructure: reuse existing composition/providers/repositories
- Adapter: Dashboard interaction and presentation only
```

## Expected File Boundary

Expected additions/changes:

- new application refresh-workspace DTO/use-case module;
- application unit tests with recording fakes;
- existing TUI daily controller/presenter/screen/widgets;
- TUI composition and app navigation only as required;
- focused headless tests and Help copy;
- this task completion record.

Do not import `src.adapters.cli.fetch_market_*` from TUI modules. If essential
composition exists only in a CLI factory, extract a shared infrastructure
composition function; do not call the CLI factory from a screen/controller.

## Implementation Checklist

- [ ] Confirm current fetch and Daily request/result fields and failure types.
- [ ] Record exact provider/cache writes and disposable test storage.
- [ ] Add preview and `RefreshDailyWorkspaceUseCase` boundaries with independent
  exact-request/sequence tests.
- [ ] Add confirmation and progress view models.
- [ ] Redesign Dashboard hierarchy.
- [ ] Add universe selector with typed exact value transport.
- [ ] Wire explicit Update separately from local Reload.
- [ ] Preserve previous valid Dashboard during update/error.
- [ ] Add partial-success, cancel, late-result, and retry behavior.
- [ ] Implement the shared semantic theme, shell, reusable visual primitives,
  and responsive/minimum-size behavior.
- [ ] Capture deterministic Dashboard visual baselines at `80x24` and `120x40`
  for READY plus at least STALE/PARTIAL/ERROR.
- [ ] Update Help and user docs.
- [ ] Run focused, architecture, and relevant fetch/Daily tests.
- [ ] Fill completion record only from executed evidence.

## Acceptance Criteria

- [ ] From a stale Dashboard, the user can update data and see a recomputed
  Dashboard without leaving the TUI.
- [ ] Update never runs without explicit confirmation.
- [ ] Reload local never invokes a provider or intentional write.
- [ ] One application result owns refresh plus briefing transport.
- [ ] TUI adapter does not orchestrate fetch followed by briefing.
- [ ] Scope/provider/write effects are visible before confirmation.
- [ ] Confirmation submits the exact request object used to build the preview.
- [ ] Progress and partial failures use exact application events/results.
- [ ] Cancellation prevents late UI mutation and makes no rollback claim.
- [ ] Previous valid content survives failed update/recompute.
- [ ] READY, PARTIAL, NOT_READY, EMPTY, validation ERROR, and infrastructure
  ERROR are distinguishable without color.
- [ ] Dashboard prioritizes data, market, warnings, and candidates.
- [ ] Dashboard has a clear four-level hierarchy: shell, workspace context,
  primary state/action, supporting detail; it is not a stack of equal boxes.
- [ ] Shared theme/component tokens own color, focus, spacing, borders, tables,
  dialogs, and status treatment; Dashboard code contains no private palette.
- [ ] At `80x24` no primary status, warning, action, focused control, or key
  hint is clipped; at `120x40` the additional space improves scanability.
- [ ] READY, STALE, PARTIAL, UNAVAILABLE, and ERROR remain distinguishable in
  a monochrome/color-disabled rendering.
- [ ] Loading and error presentation preserve the last valid Dashboard without
  layout collapse or implying that stale content is current.
- [ ] No Research Health route/dependency returns.
- [ ] No canonical signal/risk/setup behavior changes.
- [ ] Focused tests, boundary tests, full suite when feasible, and
  `git diff --check` pass.

## Required Negative Tests

- Launch/mount/focus cannot start provider work.
- Local Reload cannot call `FetchMarketCommandWorkflowUseCase`.
- Cancelled/older update progress cannot overwrite newer state.
- Fetch failure cannot be rendered as a successfully current Dashboard.
- TUI screen/controller cannot import provider or SQLite implementations.
- A display label cannot change the exact selected universe.
- Route modules cannot introduce raw/private status colors or remove the
  visible keyboard focus indicator.
- A terminal below `80x24` cannot expose clipped actions as if usable.
- Update authorization cannot authorize watchlist/journal/config writes.
- Missing/failed data cannot become neutral evidence or usable rankings.

## Do Not Interpret This As

- Do not add a shell-command runner for `saham fetch market`.
- Do not parse CLI progress text.
- Do not silently update whenever data is stale.
- Do not put refresh/analysis sequencing in the controller.
- Do not hide cache writes behind the word Reload.
- Do not redesign scoring while redesigning presentation.
- Do not broaden this task to Discover filters, ticker charts, Backtest, or Review.

## Verification

Run application orchestration tests; existing fetch/Daily tests; focused TUI
controller/presenter/headless tests at 80x24 and 120x40; TUI/general boundary
tests; strict no-provider local Reload test; disposable-database Update test;
deterministic READY and non-happy rendered-screen baselines at both supported
sizes; monochrome/status-text checks; full suite when feasible; and
`git diff --check`.

## Completion Record

- Completed date:
- Implementation commit:
- Files changed:
- Refresh/write contract proof:
- One-result transport proof:
- Local Reload no-provider proof:
- Partial/cancellation proof:
- Dashboard journey proof:
- Visual baseline paths/proof:
- Responsive/monochrome proof:
- Focused tests:
- Architecture tests:
- Full suite:
- `git diff --check`:
- Deferred items:
