# TUI Phase 3 — Candidate Browser And Ticker Drilldown

Status: `BACKLOG`

Roadmap: `docs/roadmap/roadmap_tui.md`

UX contract: `tasks/backlog/tui_ui_ux_design_spec.md`

Depends on: TUI Phases 0–2 and the completed UX contract/alignment task

Blocks: TUI Phase 5

## Task Metadata

- Task type: Feature
- Priority: High
- Semantic classification: `NON_SEMANTIC`
- Chosen decision: add an application-projection-owned accumulation browser
  and local-only swing research drilldown. Implement this option only.

## Problem Statement

Daily cannot inspect the full canonical accumulation projection or a ticker's
verdict/evidence/diagnostics. A naive implementation could rebuild candidate
order, query twice, refresh providers, merge preview/canonical verdicts, or
invent missing-data actions.

## Desired Outcome

The user can:

1. explicitly open Candidate Browser from Daily;
2. execute one `RunAccumulationScreenWorkflowUseCase` request;
3. browse the exact single/multi projection without recomputation;
4. select a ticker and execute one local-only `SwingAnalysisWorkflowUseCase`;
5. inspect canonical verdict, evidence, diagnostics, warnings, and separately
   labeled preview output.

## Non-Goals

- No V1 column sorting, provider refresh, sentiment, AI, save, recording, labels,
  charting, backtest orchestration, or trade logging.
- No new ranker/filter/scorer/action or application workflow.
- No CLI display reuse.

## End-To-End Ownership

### Accumulation

```text
RunAccumulationScreenWorkflowRequest
  -> RunAccumulationScreenWorkflowUseCase
  -> RunAccumulationScreenWorkflowResult
  -> exact ScreenAccumSingleProjection OR ScreenAccumMultiProjection
  -> AccumulationPresenter
  -> CandidateBrowserScreen
```

Transport the projection intact until presenter boundary. Do not extract
candidates early and discard filters, canonical window, warnings, counts, or
data-as-of metadata.

Opening Candidate Browser is the explicit call. Row navigation thereafter calls
nothing. Inclusion/order comes from this projection, not Daily rows.

### Ticker

```text
selected projection-row ticker
  -> SwingAnalysisWorkflowRequest
  -> SwingAnalysisWorkflowUseCase
  -> SwingAnalysisWorkflowResponse
  -> TickerResearchPresenter
  -> TickerResearchScreen
```

Phase 0 contracts (binding):

```text
accumulation default request:
  tickers=one exactly resolved configured-universe list
  universe_label=universe_name=app_config.analysis.universe
  window=7, min_streak=0, min_foreign_flow_score=None,
  min_signal_score=None, min_piotroski=0, strategy_name=None,
  include_strategy_overlay=False, multi=False, windows=[], top=20,
  save_name=None, save_enabled=False, vwap_only=False, squeeze_only=False,
  sort_by="vwap"
accumulation explicit multi request: same values except multi=True and
  windows=[7, 30, 90]; application canonical window is 7
ticker request:
  ticker=selected projection-row ticker verbatim, today=date.today(),
  strategy_name=None, setup_name=None, window=app_config.swing.window (7),
  flow_window=analyze_swing_config.flow_detail_window_sessions (30),
  capital=None, risk_pct=app_config.swing.risk_pct (1.0), entry_price=None,
  atr_mult=app_config.swing.atr_mult (1.5), rr=app_config.swing.rr (2.0),
  include_sentiment=False, include_flow_detail=False,
  include_signal_detail=False, include_risk_detail=False,
  include_market_detail=False, sentiment_verbose=False,
  auto_refresh=False, force_refresh=False, with_market_context=False,
  regime_universe=app_config.analysis.regime_universe ("idx80"),
  benchmark=app_config.analysis.benchmark ("IHSG"),
  db_path=resolved configured database path, with_technical_gate=False
composition dependencies: cached-only shared stock-analysis graph; configured
  accumulation/swing workflows, local repositories/config/factories/engines,
  session/calendar builders, gates, corporate-action risk, and typed evidence
  builders. Cached Stockbit providers retain api_client=None.
excluded dependencies: SQLiteWatchlistRepository/save use case, observation
  recorder, refresh/sentiment provider callables, labels, journal, tuning, and
  promotion. Inject `_forbid_tui_refresh` and `_forbid_tui_sentiment` from
  `composition.py`; each raises RuntimeError with the exact Phase 0 message if
  the fixed false flags are ever violated.
constructor/startup side effects: local repository/cache schemas may be
  created/migrated and broker initialization may remove superseded Stockbit
  summaries; product-read-only only.
expected accumulation ERROR: ScreenAccumProjectionError; plus startup/config/
  infrastructure ValueError, RulesError subclasses, sqlite3.Error,
  MarketDataRepositoryError, BrokerDataRepositoryError, and OSError
typed ticker UNAVAILABLE: SwingAnalysisDataUnavailable(ticker) only
expected ticker ERROR: startup/config/infrastructure ValueError, RulesError
  subclasses, CorporateActionPolicyConfigError, sqlite3.Error,
  MarketDataRepositoryError, BrokerDataRepositoryError, and OSError
invariants: TypeError, non-projection workflow/DTO ValueError, identity/
  provenance mismatch, missing/dual projection, and impossible state propagate
```

Ticker request must include:

```text
auto_refresh = False
force_refresh = False
include_sentiment = False
```

The exact response and exact projection remain the only presenter sources.
Ticker presentation consumes typed `verdict`, `evidence`, and `diagnostics`;
absence of optional detail under the false flags is displayed as unavailable,
not reconstructed. The optional `with_market_context` flag is semantic and is
not enabled merely to populate a panel.

## Display Contract

Candidate rows preserve projection order and show canonical window, signal
score/coverage, risk, setup phase, data state, next action, warnings, and
filter/count metadata where available.

Ticker groups remain separate:

- Canonical verdict: trade setup, canonical signal/risk/context.
- Supporting evidence: fields already present in `SwingEvidence`.
- Diagnostics: freshness, broker/flow detail, informational refresh actions,
  warnings.
- Preview: market-context preview labeled `NON-CANONICAL PREVIEW`.

When signal availability is unavailable, show no final-action fallback. Never
derive ENTER/WATCH/AVOID/BLOCKED wording in TUI code.

## Missing And Failure States

- Empty projection: `EMPTY`.
- Missing optional row fields: `READY` with unavailable cells.
- Workflow-declared ticker unavailable: `UNAVAILABLE` with exact reason.
- Phase 0 expected exceptions: `ERROR`.
- Invariant/programmer failures: outer boundary, never downgraded.
- Superseded results: ignored by generation.

## Exact File Boundary

Expected changes:

- `src/adapters/tui/composition.py`
- accumulation/ticker controllers and presenters
- candidate-browser/ticker-research screens
- minimal widgets/styles
- focused controller/presenter/composition/headless tests

No product-layer change is authorized. A missing application contract becomes a
separate reviewed, business-named application task.

## Architecture Impact

- Domain: not touched
- Application: reuse workflows/projections/DTOs
- Infrastructure: no implementation change; composition wiring only
- Adapter: accumulation/ticker UI paths
- New dependency/determinism/persistence impact: no
- Adapter-owned policy: no

Layer plan:

```md
Layer plan:
- Domain: not touched
- Application: reuse only
- Infrastructure: no implementation changes
- Adapter: accumulation and ticker UI paths
```

## AI And Authority Declaration

No AI involved. SignalEngine, RiskEngine, TradeSetup, setup, market context, and
evidence authority are displayed unchanged. Preview stays non-canonical. No
promotion/tuning change.

## Implementation Checklist

- [ ] Confirm prerequisites are `DONE`.
- [ ] Copy Phase 0 exact contracts.
- [ ] State projection transport/no-second-read proof.
- [ ] Wire both workflows.
- [ ] Add independent generation-safe controllers.
- [ ] Render single/multi metadata in canonical order.
- [ ] Add selection navigation with zero calls.
- [ ] Build local-only ticker request from selected projection ticker.
- [ ] Separate verdict/evidence/diagnostics/preview.
- [ ] Add unavailable/error states.
- [ ] Add lineage, call-count, no-network, and no-write tests.

## Acceptance Criteria

- [ ] One explicit load causes one accumulation call.
- [ ] Exact projection instance is preserved to presenter.
- [ ] No second read/reconstructed list controls rows.
- [ ] Row order matches projection.
- [ ] Navigation causes no call.
- [ ] Enter uses selected ticker exactly once.
- [ ] Ticker request records all local-only flags.
- [ ] No provider/AI/observation/label/watchlist/journal write is called.
- [ ] Canonical/preview outputs are separate.
- [ ] Unavailable signal produces no action fallback.
- [ ] TUI source defines no canonical action vocabulary.
- [ ] Late results cannot replace newer request.
- [ ] Focused, architecture, full tests when feasible, and `git diff --check` pass.
- [ ] Status becomes `DONE`; completion record is filled.

## Required Negative Tests

- Value-equivalent reconstructed projection fails lineage/identity assertion.
- Repository second read fails recording fake.
- Cursor movement leaves call counts unchanged.
- Any true local-only flag violation fails.
- Preview action cannot enter canonical region.
- Unavailable signal cannot render final action.
- Out-of-order ticker result cannot replace selection.

## Do Not Interpret This As

- Do not substitute Daily rows for workflow projection.
- Do not sort/filter/rank in presenter.
- Do not re-query value-equivalent rows.
- Do not call CLI factories/displays.
- Do not execute diagnostic refresh actions.
- Do not merge preview/canonical values.
- Do not persist browsing/analysis.

## Verification

Run focused UI tests, lineage/negative-authority tests, TUI/general architecture
tests, full suite when feasible, and `git diff --check`.

## Data, Persistence, And Documentation

- Reads cached accumulation and swing-analysis inputs through injected use cases.
- Performs no save, capture, label, journal, config, or schema write.
- Existing CLI and JSON contracts remain unchanged.
- User documentation is deferred to Phase 5; in-app Help must state local-only
  analysis and non-canonical preview meaning.

## Agent Execution Protocol

Before editing, confirm prerequisites, copy Phase 0 request/failure maps,
restate exact projection identity transport, and list files. Stop if code would
need a second read or adapter policy. Update completion only after call-count,
lineage, local-only, authority, and late-result tests pass.

## Completion Record

- Completed date:
- Implementation commit:
- Files changed:
- Accumulation request:
- Ticker request:
- Projection lineage proof:
- Provider/write proof:
- Focused tests:
- Architecture tests:
- Full suite:
- `git diff --check`:
- Deferred items:
