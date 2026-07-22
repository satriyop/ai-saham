# TUI Milestone C — Ticker Decision Workbench

Status: `BACKLOG`

Roadmap: `docs/roadmap/roadmap_tui.md`

Depends on: TUI Milestone B

Blocks: TUI Milestone D

## Task Metadata

- Task type: Feature / decision workspace
- Priority: High
- Semantic classification: `NON_SEMANTIC`
- Chosen decision: replace the narrow ticker drilldown with a searchable,
  tabbed decision workbench covering verdict, setup, charts, broker flow,
  signal/risk evidence, position planning, and explicit paper-trade logging.
  Implement this option only.

## Problem Statement

The current ticker screen renders one fixed cached swing response. The personal
user still has to leave the TUI to search an arbitrary ticker, choose a setup,
inspect chart structure, inspect broker flow, calculate position size, and log
a decision. Those are the central steps between discovery and action.

A larger evidence dump is not enough. The screen must support the decision
sequence while keeping canonical action, setup fit, historical/context panels,
and user-entered planning values distinct.

## Desired Outcome

From a candidate row or global ticker search, the user can:

1. choose cached-only, update-if-stale, or force-refresh analysis;
2. choose a named setup and optional evidence/detail panels;
3. explicitly run `SwingAnalysisWorkflowUseCase`;
4. read canonical verdict and blockers first;
5. inspect Setup, Chart, Flow, and Signal & Risk tabs;
6. calculate a typed position plan from capital/risk/entry parameters;
7. review an exact paper-trade record preview and explicitly confirm Log;
8. return to the originating Discover context unchanged.

## Contract Map

### Canonical live analysis

```text
SwingAnalysisWorkflowUseCase.execute(
  SwingAnalysisWorkflowRequest
) -> SwingAnalysisWorkflowResponse
```

The request mode maps exactly:

| UI label | `auto_refresh` | `force_refresh` |
|---|---:|---:|
| Cached only | false | false |
| Update if stale | true | false |
| Force update | true | true |

Sentiment and optional detail flags are explicit controls. They are not enabled
merely by opening a tab. `TradeSetup.action` remains the only live swing action.
Setup `MATCH/PARTIAL/NO_MATCH` remains pattern-fit evidence.

### Required ticker snapshot extraction

The current `view TICKER` path is adapter/display-oriented. Add:

```text
GetTickerSnapshotRequest
  ticker: str
  as_of_date: date | None

GetTickerSnapshotResponse
  ticker identity and source dates
  latest candle/price summary
  notation/company/sector/profile context
  valuation/consensus/ownership when available
  corporate-action/insider/seasonality context when available
  availability and warnings per section
```

Use typed nested DTOs rather than a dictionary copied from a Rich display. This
query is independently useful to any read-only adapter.

### Required chart-series query

```text
GetTickerChartSeriesRequest
  ticker: str
  chart: PRICE | RSI | VOLUME
  start_date: date | None
  end_date: date | None
  periods: typed indicator options

GetTickerChartSeriesResponse
  ticker: str
  chart: enum
  points: tuple[typed point, ...]
  source_start/source_end: date | None
  warmup_count: int
  warnings: tuple[str, ...]
```

The application query computes/returns chart values; the presenter only maps
points to terminal geometry. Do not parse CLI ASCII charts.

### Broker flow

Reuse `GetBrokerDataUseCase` for daily flow. Add typed application queries for
top brokers, history, or distribution only where current code lacks a reusable
boundary. Exact broker/session/date availability must travel with each result.

### Position plan

Wrap the existing position-sizing service:

```text
CalculatePositionPlanRequest
  ticker: str
  capital: Decimal
  risk_pct: Decimal
  entry_price: Decimal | None
  atr_period: int
  atr_multiplier: Decimal
  reward_risk: Decimal
  setup: str | None

CalculatePositionPlanResponse
  entry, stop, target, risk_per_share
  lots, shares, position_value, capital_at_risk
  calculation_mode and source dates
  warnings
```

Configured setup targets/policy are injected into the use case, not transported
from the TUI. Application validation owns tick size, insufficient data, invalid
numeric inputs, and setup-versus-ATR mode. The presenter performs no financial
math.

### Paper-trade log

Reuse `LogAccumulationTradeWorkflowUseCase` and its exact typed result. The
screen creates a read-only preview from the exact request, then confirmation
submits that same request object. It must not rebuild the request from rendered
text.

## UX Contract

### Persistent header

Always show ticker, latest price/change/source date, data state, selected setup,
and analysis mode. Verdict and blockers stay visible above tabs after a valid
analysis.

### Tabs

- Overview: canonical action, signal/risk summary, freshness, primary warnings,
  ticker snapshot.
- Setup: selected setup, entry authority, every passed/failed/unavailable gate.
- Chart: Price, RSI, Volume sub-tabs with range/period controls.
- Flow: daily flow/VWAP, broker history, top brokers, distribution.
- Signal & Risk: score components, coverage, unavailable evidence, gates,
  diagnostics, and clearly isolated preview.
- Position Plan: calculation inputs/result and Log preview/action.

Tab changes preserve results and never start provider, analysis, chart, sizing,
or persistence work.

### Search and context

- `/` opens a ticker input with validation/autocomplete from configured or
  cached tickers.
- Opening search does not query providers.
- Valid selection opens the same workbench used by Discover drilldown.
- Back returns to the exact originating route state; direct search returns to
  the prior route.

### Visual treatment

- The persistent header is a compact decision strip: ticker and freshness,
  canonical action, blockers, selected setup, and explicit Run. It remains
  visually separate from historical, preview, and supporting evidence.
- Tabs use consistent labels and one active indicator. Avoid placing every
  evidence category into simultaneous bordered panels.
- Overview uses progressive disclosure: primary decision and blockers first,
  then the minimum supporting metrics, then deeper evidence.
- Chart views use terminal-safe series, labeled axes/ranges, a visible cursor or
  selected point when interactive, and a table fallback at compact width.
- Flow and Signal & Risk align comparable numeric values and use explicit
  `UNAVAILABLE` cells; missing panels never look like zero-valued evidence.
- At `120x40`, supporting detail may sit beside the primary panel. At `80x24`,
  the canonical action/header remains fixed while tab content scrolls or stacks.

## Non-Goals

- No order placement or broker execution.
- No invented combined “confidence” score.
- No adapter calculation of charts, indicators, sizing, setup fit, or verdict.
- No automatic sentiment/AI call.
- No automatic logging.
- No strategy/setup backtest UI; Milestone D owns it.
- No config/setup editing or tuning apply.
- No direct reuse of CLI display functions.

## Architecture Impact

- Domain: reuse canonical values; add pure chart point/value types only if needed
- Application: ticker snapshot query, chart-series query, position-plan use case,
  and typed broker queries where absent
- Infrastructure: repository/provider implementations behind existing/new ports
- Adapter: workbench tabs, search, explicit controls/actions, renderers
- Persistence: only confirmed journal log and explicitly selected refresh mode
- Determinism: calculations deterministic for exact data/request
- AI: optional sentiment remains non-authoritative and off by default

Layer plan:

```md
Layer plan:
- Domain: pure values only if required
- Application: typed snapshot/chart/position/broker boundaries
- Infrastructure: port implementations and composition
- Adapter: interaction and presentation only
```

## Expected File Boundary

- application DTO/use-case modules for missing boundaries plus unit tests;
- TUI ticker controller(s), presenter(s), screen, tab widgets;
- TUI app global search/context state and composition;
- ticker/chart/flow/sizing/log headless tests;
- Help/documentation and this completion record.

Any need to import `view_ticker_display.py`, `analyze_chart_commands.py`,
`trade_swing_size_commands.py`, or other CLI module is a stop condition: extract
the application contract instead.

## Implementation Checklist

- [ ] Confirm exact Swing request/response and setup catalog values.
- [ ] Inventory ticker view, chart, broker, sizing, and log source ownership.
- [ ] Add typed snapshot query and tests.
- [ ] Add typed chart-series query and warm-up tests.
- [ ] Add missing typed broker queries and date/availability tests.
- [ ] Add position-plan use case and independent calculation tests.
- [ ] Build global ticker search and return-context state.
- [ ] Build workbench header, analysis controls, and tabs.
- [ ] Add exact request mode mapping tests.
- [ ] Add log preview/confirmation with same-object transport proof.
- [ ] Add cancellation, last-valid-result, and partial/error behavior.
- [ ] Apply the shared decision strip, tabs, metric/table, chart, status, and
  responsive components; capture wide/compact visual baselines.
- [ ] Run focused, architecture, and full tests when feasible.
- [ ] Fill completion record from executed evidence.

## Acceptance Criteria

- [ ] Any valid cached/configured ticker can open through `/` search.
- [ ] Discover drilldown and global search use the same workbench.
- [ ] Analysis mode maps exactly to refresh flags and runs only on explicit Run.
- [ ] Canonical `TradeSetup.action` and blockers remain visible across tabs.
- [ ] Setup fit never replaces the canonical action.
- [ ] Price, RSI, volume, and flow views use typed application results.
- [ ] Presenter/widget performs no indicator or position-sizing calculation.
- [ ] Position result exposes exact inputs, source date, mode, lots, and risk.
- [ ] Log preview and submission share the exact request object.
- [ ] No tab/focus/selection change triggers work.
- [ ] Back restores originating Discover state.
- [ ] Canonical action and blockers have the strongest hierarchy and cannot be
  visually confused with setup match, backtest evidence, or optional preview.
- [ ] At `80x24`, the persistent decision strip and focused tab/action remain
  visible; content does not force horizontal scrolling for primary fields.
- [ ] Chart meaning survives compact/table fallback and monochrome rendering.
- [ ] Section-level loading, PARTIAL, UNAVAILABLE, and ERROR states preserve
  usable successful sections and do not collapse the layout.
- [ ] Missing data is section-specific UNAVAILABLE, not neutral or fabricated.
- [ ] Optional AI/sentiment is off by default and cannot alter canonical action.
- [ ] Focused tests, architecture tests, full suite when feasible, and
  `git diff --check` pass.

## Required Negative Tests

- Setup MATCH cannot create ENTER independently.
- Historical/strategy evidence cannot override `TradeSetup.action`.
- Cached-only mode cannot invoke any provider.
- Force/update mode cannot run before explicit Run.
- Tab changes cannot call application capabilities.
- Chart presenter cannot compute SMA/EMA/RSI values.
- Position presenter cannot calculate stop, target, lots, or capital risk.
- Log cannot submit altered/reconstructed values after preview.
- Missing evidence cannot become zero/neutral.
- TUI cannot import CLI displays, commands, direct SQLite, or providers outside
  composition.

## Do Not Interpret This As

- Do not build a generic ticker JSON viewer.
- Do not put every field on Overview.
- Do not auto-run all tabs for convenience.
- Do not merge setup, signal, risk, strategy, and preview into one score.
- Do not duplicate chart/sizing formulas in widgets.
- Do not authorize real trading.
- Do not broaden into backtest comparison or strategy editing.

## Verification

Run application snapshot/chart/broker/position tests; existing Swing workflow,
setup, risk, signal, and log tests; TUI controller/presenter/headless tests at
80x24 and 120x40; deterministic Overview, Chart, and unavailable/error rendered-
screen baselines; monochrome authority-separation checks; cached-only strict
no-provider tests; log tests with disposable journals/databases; architecture
guards; full suite when feasible; and `git diff --check`.

## Completion Record

- Completed date:
- Implementation commit:
- Files changed:
- Swing request mapping proof:
- Canonical/setup separation proof:
- Snapshot/chart/flow contract proof:
- Position calculation ownership proof:
- Log exact-request proof:
- Return-context proof:
- Visual baseline paths/proof:
- Responsive/monochrome proof:
- Focused tests:
- Architecture tests:
- Full suite:
- `git diff --check`:
- Deferred items:
