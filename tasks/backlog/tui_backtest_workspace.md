# TUI Milestone D — Backtest Workspace

Status: `BACKLOG`

Roadmap: `docs/roadmap/roadmap_tui.md`

Depends on: TUI Milestone C

Blocks: TUI Milestone E

## Task Metadata

- Task type: Feature / historical validation workspace
- Priority: High
- Semantic classification: `NON_SEMANTIC`
- Chosen decision: add two explicitly separate Backtest modes—Setup Backtest and
  Strategy Backtest—with full input identity, deterministic results, and pinned
  side-by-side comparison. Implement this option only.

## Problem Statement

The application already has high-value historical testing commands, but the
personal user must remember many flags and compare outputs manually. The TUI
currently offers no way to answer whether a selected swing setup or custom
strategy has historical support.

“Setup” and “strategy” are different contracts. Combining them into a generic
backtest form would hide important differences in universe, parameters,
artifacts, and authority.

## Desired Outcome

The Backtest workspace lets the user:

- choose Setup Backtest or Strategy Backtest;
- configure a complete typed request with friendly controls;
- see defaults versus overrides before Run;
- validate inputs before expensive execution;
- inspect summary metrics, equity/trades, regime/attribution, skips, and warnings;
- pin multiple exact runs and compare them side by side;
- open a trade's ticker in the Ticker Workbench without changing the run.

Historical results are always labeled `BACKTEST — NOT A LIVE VERDICT`.

## Contract Map

### Setup Backtest

Reuse exactly:

```text
SwingBacktestUseCase.execute(
  SwingBacktestRequest
) -> SwingBacktestResponse
```

The form must transport every material request field, including:

- exact tickers resolved from selected universe or explicit list;
- start/end date;
- setup;
- capital and risk percentage;
- maximum positions;
- window/minimum flow/setup gate inputs surfaced by the chosen form mode;
- take-profit, stop-loss, maximum hold, costs;
- regime inclusion/allowed regimes/benchmark;
- configuration-derived setup targets/policy identity used by composition.

Do not expose every dataclass field as a raw input. Define a typed
`BuildSwingBacktestRequestUseCase` or equivalent application builder that
resolves configured defaults and returns:

```text
PreparedSwingBacktest
  request: SwingBacktestRequest
  defaults: typed displayable defaults
  overrides: tuple[named override, ...]
  warnings: tuple[str, ...]
```

The exact prepared request object is submitted to the backtest. The adapter
must not rebuild hidden config fields.

### Strategy catalog and validation

Add typed boundaries over `StrategyLoader`:

```text
ListStrategiesRequest
  include_invalid: bool = true

ListStrategiesResponse
  strategies: tuple[StrategyInfo, ...]

ValidateStrategyRequest
  strategy: str
  strict: bool = false

ValidateStrategyResponse
  strategy: StrategyInfo | None
  validation: ValidationResult
```

Listing/validation is read-only. Validation must not generate or rewrite skill
documentation as a side effect; the CLI's optional documentation generation is
not part of this query.

### Strategy Backtest

Reuse:

```text
BacktestUseCase.execute(BacktestRequest) -> BacktestResponse
```

The request contains exact ticker, resolved rules path/identity, dates, and
capital. The selected strategy must validate before Run. An invalid strategy
remains inspectable but cannot execute.

### Session run identity

Each completed run is retained as one immutable object:

```text
BacktestRun
  run_id: session-local monotonic ID
  kind: SETUP | STRATEGY
  submitted_request: exact typed request
  result: exact typed response
  completed_at: UI metadata
```

The response and request never travel separately. Pinning stores `BacktestRun` in
session state only; no new persistence is required.

## UX Contract

### Setup Backtest mode

Inputs are grouped by purpose:

- Scope: universe/explicit tickers, date range, setup.
- Portfolio: capital, risk, maximum positions.
- Exit/cost: TP, SL, hold, cost.
- Evidence: regime toggle, allowed regimes, benchmark.
- Advanced gates: collapsed and typed; current defaults visible.

Results:

- summary: return, drawdown, trades, win rate, average return, profit factor,
  exposure;
- equity: terminal graph/table from exact `equity_curve`;
- trades: entries/exits/P&L/reason/holding days;
- regimes: exact `regime_stats` when requested;
- attribution: exact application summary;
- skips/warnings: no cash, duplicate, no forward data, regime.

### Strategy Backtest mode

- Strategy selector with VALID/INVALID and description.
- Validation detail with errors/warnings.
- Ticker, date range, capital.
- Summary metrics and trade-by-trade result from `BacktestResponse.result`.

Do not expose internal filesystem paths as the primary label. A read-only
Advanced detail may show the resolved path.

### Compare pinned runs

- Compare runs of the same kind by default.
- Every column starts with request identity: setup/strategy, scope, dates,
  capital, risk, exits, cost, regime.
- Differing inputs are highlighted before metrics.
- Cross-kind comparison is blocked; setup portfolio backtests and single-ticker
  strategy backtests are not commensurate.
- No automatic winner, recommendation, or optimized parameter is generated.

## Non-Goals

- No strategy authoring, YAML editor, AI creation, or formula editor.
- No tuning proposal, tuning diff, patch validation/application, or promotion.
- No persistent run warehouse in this milestone.
- No statistical claim beyond existing response metrics.
- No adapter backtest math or hidden parameter defaulting.
- No live trade verdict from a historical result.

## Architecture Impact

- Domain: unchanged; reuse backtest entities/value objects
- Application: strategy catalog/validation queries and prepared setup-request
  builder; reuse backtest use cases
- Infrastructure: composition for rules/config/repositories only
- Adapter: Backtest state, forms, workers, presenters, result tabs/comparison
- Persistence: read cached market/broker data; no new writes
- Determinism: same prepared request/data produces same result
- AI: none

Layer plan:

```md
Layer plan:
- Domain: not touched
- Application: typed strategy queries and prepared setup request
- Infrastructure: existing config/rules/repository composition
- Adapter: Backtest controls, execution, presentation, session pinning
```

## Expected File Boundary

- application DTO/use-case modules for strategy list/validate and request prep;
- application tests for exact defaults/overrides/validation;
- TUI Backtest controllers/presenters/screen/widgets/state;
- composition for `SwingBacktestUseCase` and `BacktestUseCase`;
- headless execution/comparison/cancellation tests;
- Help/docs and this completion record.

If the only available setup composition lives in
`trade_swing_backtest_runner.py` or another CLI module, extract a shared
infrastructure composition boundary. Never import the CLI runner into TUI.

## Implementation Checklist

- [ ] Confirm all material fields/default sources for both backtest requests.
- [ ] Define and test prepared setup-request transport.
- [ ] Add typed strategy list and validation queries without write side effects.
- [ ] Wire both backtest use cases through non-CLI composition.
- [ ] Implement two separate typed forms and validation states.
- [ ] Implement result tabs from exact response objects.
- [ ] Implement immutable session `BacktestRun` and pin/unpin.
- [ ] Implement same-kind comparison with input identity first.
- [ ] Add cancellation/late-result/last-valid-result handling.
- [ ] Add authority labels and Help.
- [ ] Run focused, architecture, and full tests when feasible.
- [ ] Fill completion record from evidence.

## Acceptance Criteria

- [ ] Setup and Strategy modes are separate in labels, forms, requests, and
  results.
- [ ] Setup Run submits the exact application-prepared `SwingBacktestRequest`.
- [ ] Every material default and override is visible before execution.
- [ ] Strategy catalog shows valid and invalid entries with exact validation.
- [ ] Invalid strategy cannot run.
- [ ] Validation performs no documentation/config write.
- [ ] Every result visibly shows scope, dates, capital, costs, and parameters.
- [ ] Summary/trades/equity/regime/attribution values come from exact responses.
- [ ] Pinned run binds exact request and response in one immutable object.
- [ ] Compare shows differing inputs before metrics and blocks cross-kind runs.
- [ ] No backtest is labeled or styled as a live verdict.
- [ ] No winner, tuning proposal, or config change is inferred.
- [ ] Focused tests, architecture tests, full suite when feasible, and
  `git diff --check` pass.

## Required Negative Tests

- Adapter cannot create hidden `SwingBacktestRequest` config values.
- Changing a form after Run cannot mutate a completed/pinned `BacktestRun`.
- Selection/focus/tab change cannot start a backtest.
- Invalid/missing strategy cannot reach `BacktestUseCase`.
- Strategy validation cannot write skill docs or strategy files.
- Setup and strategy runs cannot be compared as equivalent.
- Presenter cannot calculate performance metrics absent from the response.
- Historical result cannot emit a live ENTER/WATCH/AVOID action.
- TUI cannot import CLI backtest runners/displays.

## Do Not Interpret This As

- Do not make one generic form with a “type” flag and shared loose dictionary.
- Do not expose a dataclass dump as UX.
- Do not silently use current config without displaying material defaults.
- Do not rank or recommend the “best” run.
- Do not add parameter search/optimization.
- Do not edit or generate strategies.
- Do not persist Backtest runs until a separate exact provenance task authorizes it.

## Verification

Run prepared-request and strategy-query tests; existing setup, SwingBacktest,
Backtest, rules, and validation tests; TUI controller/presenter/headless tests
at 80x24 and 120x40; exact-request and immutability tests; no-write and
authority-negative tests; architecture guards; full suite when feasible; and
`git diff --check`.

## Completion Record

- Completed date:
- Implementation commit:
- Files changed:
- Prepared setup request proof:
- Strategy validation/no-write proof:
- Exact result rendering proof:
- BacktestRun immutability proof:
- Comparison identity proof:
- Authority-separation proof:
- Focused tests:
- Architecture tests:
- Full suite:
- `git diff --check`:
- Deferred items:
