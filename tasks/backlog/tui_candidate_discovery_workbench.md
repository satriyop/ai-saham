# TUI Milestone B — Candidate Discovery Workbench

Status: `BACKLOG`

Roadmap: `docs/roadmap/roadmap_tui.md`

Depends on: TUI Milestone A

Blocks: TUI Milestone C

## Task Metadata

- Task type: Feature / workflow consolidation
- Priority: High
- Semantic classification: `NON_SEMANTIC`
- Chosen decision: build one Discover workspace with Universe, Accumulation,
  and Saved/Compare tabs. Implement this option only.

## Problem Statement

The current Candidate screen runs only a narrow preconfigured accumulation
projection. It does not let the personal user explore a universe, choose the
useful multi-window/filter/sort inputs already available in the CLI, preserve a
shortlist, or compare what changed.

The user needs discovery, narrowing, and shortlist change detection in one
stateful workflow—not a static list and not one screen per CLI command.

## Desired Outcome

The user can:

1. browse a configured universe by foreign flow, price change, volume, or
   ticker;
2. configure and explicitly run accumulation screening;
3. inspect 7/30/90-session evidence without losing canonical rank;
4. filter by score, streak, squeeze, foreign-underwater state, and available
   setup/quality inputs;
5. save the current canonical shortlist under a name;
6. compare a saved snapshot with one explicit fresh screen run;
7. open any ticker and return to the same tab, controls, selection, and scroll.

## Application Contracts

### Existing source of truth

```text
build_universe_view(...) -> UniverseViewResult

RunAccumulationScreenWorkflowUseCase.execute(
  RunAccumulationScreenWorkflowRequest
) -> RunAccumulationScreenWorkflowResult

SaveScreenWatchlistUseCase.execute(
  SaveScreenWatchlistRequest
) -> SaveScreenWatchlistResult
```

The `ScreenAccumSingleProjection` or `ScreenAccumMultiProjection` returned by
the workflow owns inclusion, filters, canonical rank/window, phase, risk, setup,
data state, and canonical order. The adapter never reconstructs candidates.

### Required watchlist extraction

The current CLI lists watchlists by reading the concrete repository and
performs compare orchestration inline. Add business-owned boundaries:

```text
ListScreenWatchlistsRequest
  name: str | None

ListScreenWatchlistsResult
  summaries: tuple[ScreenWatchlistSummary, ...]
  selected_entries: tuple[ScreenWatchlistEntry, ...]

CompareScreenWatchlistRequest
  name: str
  screen_request: RunAccumulationScreenWorkflowRequest

CompareScreenWatchlistResult
  saved_summary: ScreenWatchlistSummary
  fresh_projection: ScreenAccumSingleProjection
  comparison: ScreenCompareResult
```

`CompareScreenWatchlistUseCase` owns snapshot loading, exactly one fresh
screen-workflow execution, and comparison. It must reuse
`compare_screen_snapshots` or its application-owned successor. The TUI must not
load a snapshot, run a screen, and combine results itself.

Missing watchlist is a typed expected unavailable/not-found result or a named
application exception. Choose and test one representation before adapter work;
do not return an ambiguous empty tuple for both missing and valid empty.

## UX Contract

### Universe tab

- Universe selector, as-of date, sort, and optional top-N.
- Table columns: ticker, name/sector when available, close, change, volume,
  foreign net/ratio, source date.
- Missing candle/flow counts always visible.
- Enter opens Ticker Workbench.

### Accumulation tab

Controls map to typed request fields:

- universe or explicit ticker set;
- single/multi mode and windows;
- top;
- minimum streak;
- minimum foreign-flow score;
- minimum signal score when enabled;
- minimum Piotroski;
- squeeze-only and VWAP-only;
- supported sort values.

Controls change pending input only. Explicit Run creates a new result.

The table shows canonical rank separately from presentation order. If the user
sorts locally, label it `View sort`; never mutate the projection or imply the
new order is canonical.

### Candidate preview

Show selected row context without recomputation:

- pattern/phase and multi-window shape;
- foreign flow, streak, VWAP, compression;
- signal/risk/setup state already in the projection;
- data status, warnings, and next/canonical action fields;
- broker-quality summary when present.

### Saved / Compare tab

- List snapshot name, saved time, universe, window, and ticker count.
- Open a saved snapshot without recomputation.
- Compare requires explicit Run and shows new, dropped, strengthening,
  weakening, and unchanged groups.
- Saving names the exact current canonical projection and confirms the write.

## Non-Goals

- No provider fetch; use Milestone A Update for data refresh.
- No adapter-side filtering, business ranking, or target reconstruction.
- No screen observation/corpus write.
- No automatic watchlist save or compare.
- No arbitrary SQL/query builder.
- No ticker analysis recomputation during row movement.
- No changes to accumulation, signal, risk, or setup semantics.

## Architecture Impact

- Domain: reuse/add narrow watchlist read port types only if absent
- Application: typed watchlist list/compare workflow extraction
- Infrastructure: implement/reuse watchlist repository port
- Adapter: stateful Discover tabs, controls, tables, preview, confirmation
- Persistence: explicit watchlist save only
- Determinism: same data/request yields same canonical projection/comparison
- AI: none

Layer plan:

```md
Layer plan:
- Domain: reuse repository contracts; add only if exact read port is missing
- Application: list and compare watchlist workflows
- Infrastructure: wire existing SQLite watchlist implementation to the port
- Adapter: Discover interaction and presentation
```

## Expected File Boundary

- application watchlist query/compare DTOs and use cases;
- application tests with strict repositories/screen fakes;
- Discover controller/presenter/screen/widgets;
- TUI app navigation/state restoration/composition;
- Help and headless tests;
- current candidate screen may be replaced rather than duplicated;
- this completion record.

Do not import `screen_lifecycle_commands.py`,
`screen_accum_compare_factory.py`, CLI displays, or concrete repositories from
non-composition TUI modules.

## Implementation Checklist

- [ ] Confirm exact single/multi projection fields and supported request values.
- [ ] Confirm watchlist repository read/write behavior and missing semantics.
- [ ] Add typed list and compare application workflows.
- [ ] Add one-fresh-screen/read-count lineage tests.
- [ ] Implement Universe tab.
- [ ] Implement Accumulation controls and explicit Run.
- [ ] Implement canonical-rank-preserving table/preview.
- [ ] Implement Save confirmation/result.
- [ ] Implement Saved/Compare tab and grouped differences.
- [ ] Restore tab/filter/selection/scroll after ticker drilldown.
- [ ] Update navigation/Help.
- [ ] Run focused, boundary, and full tests when feasible.
- [ ] Fill completion record from evidence.

## Acceptance Criteria

- [ ] Universe browsing works independently of accumulation screening.
- [ ] Useful live accumulation inputs are available as friendly typed controls.
- [ ] No control change, focus, sort, or selection runs a screen.
- [ ] Explicit Run calls the accumulation workflow exactly once per requested
  operation (its internal multi-window calls remain application-owned).
- [ ] Candidate inclusion and canonical rank exactly match the returned
  projection.
- [ ] View sorting preserves a visible canonical rank.
- [ ] Candidate preview causes no repository/use-case call.
- [ ] Save writes exactly the displayed canonical projection after confirmation.
- [ ] Watchlist compare loads one snapshot and owns one fresh projection in one
  application result.
- [ ] Missing and valid-empty watchlists are distinguishable.
- [ ] Returning from Ticker preserves Discover context.
- [ ] No provider, corpus, journal, config, or tuning write is introduced.
- [ ] Focused tests, architecture tests, full suite when feasible, and
  `git diff --check` pass.

## Required Negative Tests

- Adapter cannot apply `min_*`, squeeze, VWAP, rank, or comparison policy.
- Presentation sort cannot overwrite canonical rank/order in the source DTO.
- Cursor movement cannot execute screening or ticker analysis.
- Save cannot persist a locally sorted/reconstructed list instead of the exact
  canonical projection.
- Compare cannot re-query or rerun after its application result returns.
- Missing watchlist cannot silently become empty comparison.
- TUI cannot import CLI compare factory/display or concrete repository.
- Multi-window context cannot invent signal/risk values for noncanonical
  windows.

## Do Not Interpret This As

- Do not clone each `screen` subcommand into a separate screen.
- Do not put filter logic in Textual widgets.
- Do not call the CLI accumulation function.
- Do not add inline provider refresh.
- Do not save automatically when opening a ticker.
- Do not treat local sort as canonical ranking.
- Do not add pre-open screening in this milestone.

## Verification

Run application list/compare tests, accumulation workflow/projection tests,
controller/presenter tests, headless Discover journeys at 80x24 and 120x40,
state-restoration tests, write-scope tests with disposable storage,
architecture/import guards, full suite when feasible, and `git diff --check`.

## Completion Record

- Completed date:
- Implementation commit:
- Files changed:
- Projection identity proof:
- Filter ownership proof:
- Watchlist read/save proof:
- Compare lineage/read-count proof:
- State restoration proof:
- Focused tests:
- Architecture tests:
- Full suite:
- `git diff --check`:
- Deferred items:
