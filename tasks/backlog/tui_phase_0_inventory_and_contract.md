# TUI Phase 0 — Inventory And Binding Implementation Contract

Status: `BLOCKED_BY_FAILURE_BOUNDARY_DECISION`

Roadmap: `docs/roadmap/roadmap_tui.md`

Blocks: TUI Phases 1–5

## Task Metadata

- Task type: Spike / Research
- Priority: High
- Semantic classification: `NON_SEMANTIC`
- Chosen decision: produce the binding implementation inventory for the
  read-only TUI. Implement this option only.

## Problem Statement

The roadmap fixes the architecture, but implementation still depends on facts
that must be resolved from current code: exact composition dependencies,
constructor side effects, network-capable callables, request defaults, DTO
fields, and exception behavior. Letting later agents rediscover these facts
would invite inconsistent wiring and adapter-owned policy.

## Desired Outcome

This document contains a completed, source-cited resolution record identifying:

- one producer and transport path for every displayed result;
- every concrete dependency required by the four planned screens;
- exact local-only request values;
- startup or constructor writes;
- absence, validation, infrastructure, and invariant failure behavior;
- the dependency range and lazy-launch failure contract;
- the files each later phase may change.

This phase changes no product code.

## Non-Goals

- No TUI, dependency, CLI, product, test, config, or persistence implementation.
- No redesign of current use cases or composition roots.
- No new application DTO or policy proposal unless a proven blocker is first
  escalated for separate approval.
- No agent, write-capable UI, provider, or broader command-tree planning.

## Hard Invariants

- Current code and tests outrank roadmap prose.
- CLI display functions and JSON are never TUI data sources.
- Ordinary screen/analyze workflows remain read-only.
- Interactive use never determines the learning population.
- Missing evidence is not neutral evidence.
- `TradeSetup` remains the only final swing-action wording.
- Diagnostic readiness and patch eligibility do not imply promotion.
- Missing business orchestration is assigned to a business-named application
  use case before UI implementation proceeds.

## Exact Work Boundary

Expected files changed:

- this task document;
- dependent TUI phase task documents when a resolved fact replaces a placeholder.

Forbidden changes:

- `src/**`
- `tests/**`
- `config/**`
- `pyproject.toml`
- `uv.lock`

If inventory reveals a product decision not fixed by the roadmap, stop and ask
instead of selecting a broader architecture.

## Required Reading

- `AGENT_QUICKSTART.md`, `AGENTS.md`, and `TASK_TEMPLATE.md`
- `docs/roadmap/roadmap_tui.md`
- ADRs 003, 004, 011, 021, 033, and 040
- Current source and focused tests for:
  - `DailyBriefingUseCase`
  - `RunAccumulationScreenWorkflowUseCase`
  - `SwingAnalysisWorkflowUseCase`
  - `ReportSignalReadinessUseCase`
  - their production composition roots
  - SQLite repositories constructed by those roots

Do not inspect unrelated backlog-task formatting.

## Architecture Impact

- Domain: not touched
- Application: not touched
- Infrastructure: not touched
- Adapter: not touched
- Documentation/governance: this task and dependent TUI tasks
- New dependency: no
- Determinism impact: no
- Persistence/schema impact: no
- Adapter-owned policy: no

Layer plan:

```md
Layer plan:
- Domain: not touched
- Application: not touched
- Infrastructure: not touched
- Adapter: not touched
```

## AI And Authority Declaration

- AI usage: no AI involved.
- SignalEngine, RiskEngine, TradeSetup, market context, setup policy, evidence
  authority, tuning, observations, and labels are unchanged.

## Required Resolution Record

Complete every cell with a source path and symbol. Never write “same as CLI,”
“reuse existing,” or “wire as needed.”

### A. Producer and transport map

| Screen | Request owner | Result owner | Composition root | Presenter input | Second reads? |
|---|---|---|---|---|---|
| Daily | `DailyBriefingRequest` | `DailyBriefingResponse` | Current evidence: `src/adapters/cli/today_commands.py::today`; TUI owner: `src.adapters.tui.composition` | The exact response object. Presenter fields: `live_session_date`, `latest_completed_eod_date`, `opening_snapshot_date`, `is_historical`, `universe`, `universe_count`, `data_freshness`, `stale_count`, `readiness_items`, `overall_authority`, `regime`, `opening_candidates`, `market_wide_opening_observations`, `accumulation_summary`, `daily_accumulation_candidates`, `setup_lens_impact`, and `warnings`. Do not use the CLI's render helpers or raw `accumulation_candidates` as a second candidate contract. (`src/application/use_case/daily_briefing_use_case.py::DailyBriefingResponse`) | No |
| Accumulation | `RunAccumulationScreenWorkflowRequest` | `RunAccumulationScreenWorkflowResult` | Current evidence: `src/adapters/cli/screen_accum_workflow_factory.py::create_run_accumulation_screen_workflow_use_case`; TUI owner: `src.adapters.tui.composition` | Preserve the result and its exact non-`None` `single_projection` or `multi_projection` to the presenter. Single fields: `candidates`, `applied_filters`, before/after counts, `window_days`, `screened_at`, `data_as_of`, plus result `warnings`. Multi fields: `rows`, `applied_filters`, requested/resolved windows, before/after counts, `screened_at`, `canonical_window`, projection/result warnings; each row uses its existing ticker/window candidates, pattern, trend, tracked flow, canonical candidate, signal score/coverage, risk, setup phase, data status, and next action. (`src/application/services/screen_accum_result_projector.py::ScreenAccumSingleProjection`, `ScreenAccumMultiProjection`, `ScreenAccumMultiRow`) | No |
| Ticker | `SwingAnalysisWorkflowRequest` | `SwingAnalysisWorkflowResponse` | Current evidence: `src/adapters/cli/analyze_swing_workflow_factory.py::create_swing_analysis_workflow`; TUI owner: `src.adapters.tui.composition` | The exact response object, using `ticker`, `today`, `modules`, `warnings`, and the typed `verdict`, `evidence`, and `diagnostics` groups. Verdict: trade setup, signal assessment, risk response, market regime, signal availability/reason, and the three separately labeled preview fields. Evidence: accumulation, setup/backtest/sentiment values and warning, TP/SL/regime label, setup/flow/phase/strategy/institutional/profile/sector/company-quality/corporate-action evidence. Diagnostics: freshness, flow detail, broker detail/quality note, informational refresh actions, warnings. Never fall back to mirrored legacy fields to repair a malformed typed group. (`src/application/dto/swing_analysis.py::SwingVerdict`, `SwingEvidence`, `SwingDiagnostics`, `SwingAnalysisWorkflowResponse`) | No |
| Corpus health | `ReportSignalReadinessRequest` | `SignalReadinessReport` | Current evidence: `src/adapters/cli/analyze_signal_readiness_commands.py::signal_readiness`; TUI owner: `src.adapters.tui.composition` | The exact report object: parsed target components/diagnostic flag; observation dates/latest and raw/deduplicated target counts; label/raw/available target counts; IS/OOS counts and metrics; diagnostic, patch, and promotion flags; split mode; selected/available cohorts; unique tickers/signal dates; all six exclusion-ledger counts; notes and blockers. (`src/application/use_case/report_signal_readiness_use_case.py::SignalReadinessReport`, `SignalReadinessExclusionLedger`) | No |

### B. Dependency and side-effect inventory

| Capability | Concrete dependencies | Network-capable dependency | Constructor/startup write | Exclusion/mitigation |
|---|---|---|---|---|
| Daily | `SQLiteMarketRepository`, `SQLiteBrokerRepository`, `EffectiveMarketSessionResolver`, `MarketContextEngine`, `AccumulationScreenUseCase`, indicator registry, `RulesYamlLoader`, configured risk/signal engines, `YamlUniverseConfigLoader`, cached-only Stockbit enrichment providers, and `DailySetupLensImpactUseCase` with four setup-bound swing workflows and typed `SwingLensRequestDefaults`. (`src/adapters/cli/today_commands.py::today`, `_build_setup_lens_impact_use_case`; `src/application/use_case/daily_briefing_use_case.py::DailyBriefingUseCase`) | The current setup-lens composition injects `auto_refresh_swing_data` and `fetch_swing_sentiment`, although `DailySetupLensImpactUseCase._build_request` disables both paths. | Market/broker repositories ensure or migrate schema; broker startup can remove superseded Stockbit summary rows. The shared swing dependency bundle also initializes candidate-observation and cached Stockbit-provider schemas; corporate-action repositories initialize their tables. | Never compose `GetSystemStatusUseCase`. TUI composition must replace refresh and sentiment callables with fail-closed local-only callables and retain the existing false request flags. Cached Stockbit providers must have `api_client=None`. No save/capture/label dependency. |
| Accumulation | Shared `StockAnalysisWorkflowDependencies`: market/broker/candidate-observation repositories, cached-only Stockbit provider bundle, rules/indicator/profile/institutional/sector/company-quality factories, configured signal/risk engines; plus accumulation config, swing config, `AccumulationScreenUseCase`, `BuildLiveSignalEvidenceExecutionContextUseCase`, `EffectiveMarketSessionResolver`, `SignalEvidenceExecutionContextBuilder`, and `IHSGTradingSessionCalendarProvider`. (`src/adapters/cli/stock_analysis_workflow_dependencies.py::StockAnalysisWorkflowDependencies`; `src/adapters/cli/screen_accum_workflow_factory.py::create_run_accumulation_screen_workflow_use_case`) | None in the required graph: `create_readonly_stockbit_providers` constructs every cache provider with `api_client=None`. | Market, broker, candidate-observation, and cached Stockbit provider constructors create/migrate schemas; broker startup may migrate tables and delete superseded Stockbit summaries. The current CLI factory additionally constructs `SQLiteWatchlistRepository`, which creates `screen_snapshots`. | TUI composition must construct `RunAccumulationScreenWorkflowUseCase` with `save_watchlist_use_case=None`; do not call the CLI factory unchanged. Never construct an observation recorder. Keep the cached-only provider bundle. |
| Ticker | The shared dependency bundle above; workflow registry and gates; local freshness/flow/broker builders; single-ticker accumulation builder; setup evaluator; configured signal/risk engines; rules/config loaders; corporate-action risk use case/repository; session resolver/calendar loader; profile/institutional/sector/company-quality factories; local market-context evaluator. (`src/adapters/cli/analyze_swing_workflow_factory.py::create_swing_analysis_workflow`; `src/adapters/cli/analyze_swing_dependency_factory.py::create_corporate_action_risk_use_case`, `create_workflow_registry`, `create_structural_gates`, `create_execution_gates`, `create_broker_detail_builder`, `create_setup_evaluator`; `src/adapters/cli/analyze_swing_candidate_builder.py::create_accumulation_candidate_builder`) | Current root injects `auto_refresh_swing_data` and `fetch_swing_sentiment`. | All shared SQLite/cache effects above plus corporate-action calendar schema initialization. | TUI composition must not inject the network-capable CLI callables: inject fail-closed local-only refresh/sentiment callables, and enforce `auto_refresh=False`, `force_refresh=False`, `include_sentiment=False`. No observation writer is present; the injected observation repository is read-only evidence input. |
| Corpus health | `SQLiteCandidateObservationsRepository`, `SQLiteSignalForwardLabelsRepository`, then `ReportSignalReadinessUseCase`. (`src/adapters/cli/analyze_signal_readiness_commands.py::signal_readiness`) | None. | Both repository constructors run `SqliteMigrationRunner`, which creates `_schema_migrations`, tables, indexes, and missing columns and records migration versions. | Compose only these two repository ports and the report use case; no capture, label-generation, tuning, patch, repair, or promotion use case. Disclose schema initialization. |

V1 is **product-read-only only**. It cannot guarantee byte-for-byte database
immutability. `SQLiteMarketRepository.__init__`, `SQLiteBrokerRepository.__init__`,
`SQLiteCandidateObservationsRepository.__init__`,
`SQLiteSignalForwardLabelsRepository.__init__`,
`SQLiteCorporateActionCalendarRepository.__init__`, the cached Stockbit provider
constructors, and (in the excluded CLI accumulation graph)
`SQLiteWatchlistRepository.__init__` initialize or migrate storage. In addition,
`ensure_sqlite_broker_schema` invokes
`_cleanup_stockbit_summaries_superseded_by_idx`, which can delete redundant
Stockbit rows when an IDX row exists. Evidence:
`src/infrastructure/persistence/sqlite_market_repository.py::SQLiteMarketRepository`,
`src/infrastructure/persistence/sqlite_broker_repository.py::SQLiteBrokerRepository`,
`src/infrastructure/persistence/sqlite_broker_schema.py::ensure_sqlite_broker_schema`,
`src/infrastructure/persistence/sqlite_candidate_observations_repository.py::SQLiteCandidateObservationsRepository`,
`src/infrastructure/persistence/sqlite_signal_forward_labels_repository.py::SQLiteSignalForwardLabelsRepository`,
`src/infrastructure/persistence/sqlite_corporate_action_calendar_repository.py::SQLiteCorporateActionCalendarRepository`,
`src/infrastructure/browser/stockbit_base_provider.py::StockbitCachingProvider`, and
`src/infrastructure/persistence/sqlite_migration_runner.py::SqliteMigrationRunner`.

### C. Exact request defaults

#### Daily

`DailyBriefingRequest(universe=app_config.analysis.universe, top=3,
as_of_date=None, opening_data_dir=Path("data/opening"),
universe_config_path=Path("config/universes.yaml"))`. The shipped/default
universe is `lq45`. The request factory reads config once in composition; Reload
rebuilds the same values and performs local recomputation only. Evidence:
`src/application/use_case/daily_briefing_use_case.py::DailyBriefingRequest` and
`src/infrastructure/config/app_config.py::AnalysisConfig`.

#### Accumulation

The default browser call is single-window. An explicit multi-window UI action
changes only `multi` and `windows`; it does not change filtering or authority.

```text
tickers = exact list resolved once from app_config.analysis.universe
universe_label = app_config.analysis.universe
universe_name = app_config.analysis.universe       # shipped/default: "lq45"
window = 7                                         # canonical single window
min_streak = 0
min_foreign_flow_score = None                      # config policy resolves it
min_signal_score = None                            # config policy resolves/keeps disabled
min_piotroski = 0
strategy_name = None
include_strategy_overlay = False
multi = False                                      # default action
windows = []                                       # default action
top = 20
save_name = None
save_enabled = False
vwap_only = False
squeeze_only = False
sort_by = "vwap"
```

For the explicit multi action: `multi=True`, `windows=[7, 30, 90]`; all other
values remain above. The use case selects canonical window `7` when present and
otherwise the first requested window. Evidence:
`src/adapters/cli/screen_accum_commands.py::accumulation_run`,
`src/application/use_case/run_accumulation_screen_workflow_use_case.py::RunAccumulationScreenWorkflowRequest`,
`_DEFAULT_MULTI_CANONICAL_WINDOW`, and
`src/application/services/screen_accum_result_projector.py::validate_multi_window_request`.

#### Ticker

Build the request from the selected projection-row ticker without a second
lookup. Numeric values come from the loaded typed app/analyze-swing config; the
values below are the shipped defaults.

```text
ticker = selected projection-row ticker verbatim
today = date.today()
strategy_name = None
setup_name = None
window = app_config.swing.window                         # 7
flow_window = analyze_swing_config.flow_detail_window_sessions  # 30
capital = None
risk_pct = app_config.swing.risk_pct                     # 1.0
entry_price = None
atr_mult = app_config.swing.atr_mult                     # 1.5
rr = app_config.swing.rr                                 # 2.0
include_sentiment = False
include_flow_detail = False
include_signal_detail = False
include_risk_detail = False
include_market_detail = False
sentiment_verbose = False
auto_refresh = False
force_refresh = False
with_market_context = False
regime_universe = app_config.analysis.regime_universe    # "idx80"
benchmark = app_config.analysis.benchmark                # "IHSG"
db_path = resolved configured database path
with_technical_gate = False
```

The optional detail booleans are presentation/module selectors except
`include_flow_detail`, which performs another local broker read; V1 leaves all
off. `with_market_context` is semantic, not a display-detail switch, and stays
off. The presenter still consumes the typed verdict/evidence/diagnostics groups
and renders absent optional content honestly. Evidence:
`src/application/dto/swing_analysis.py::SwingAnalysisWorkflowRequest`,
`src/adapters/cli/analyze_swing_commands.py::swing`,
`src/infrastructure/config/app_config.py::SwingDefaults`, and
`src/infrastructure/config/analyze_swing_config.py::AnalyzeSwingConfig`.

#### Readiness

The adapter rejects a blank target before calling the use case. Otherwise it
passes `ReportSignalReadinessRequest(target=<user text>,
semantic_compatibility_id=<optional user text or None>)` unchanged. The use case
strips the target, requires a `SignalLabelHorizon` suffix, parses canonical
`<profile>_<setup>_<bucket>_cap_<horizon>` or diagnostic
`<profile>_<setup>_<horizon>` shapes, and raises `ValueError` for malformed
targets. A supplied cohort is stripped and must be present. With no supplied
cohort, zero available cohorts yields blocker
`no semantic_compatibility_id on canonical observations`, one selects itself,
and multiple yield blocker `mixed_semantic_cohorts`; unresolved cohorts return a
valid fail-closed report with no pooled IS/OOS rows. Evidence:
`src/application/use_case/report_signal_readiness_use_case.py::SignalReadinessTarget.parse`,
`ReportSignalReadinessRequest`, and `_resolve_cohort`.

### D. Failure matrix

| Capability | Valid empty | Typed unavailable | Expected ERROR exceptions | Invariant/programmer failure |
|---|---|---|---|---|
| Daily | `DailyBriefingResponse` with `universe_count == 0`, no regime/opening/accumulation rows, and warnings. `PARTIAL`/`NOT_READY` are valid non-empty/usable business responses, not errors. | No top-level typed-unavailable result. Dataset `DataReadiness.status == "UNAVAILABLE"`, absent optional sections, and warnings remain inside a valid response. | Composition/startup: `ValueError` from malformed typed/YAML config, `RulesError` subclasses, `CorporateActionPolicyConfigError`, `sqlite3.Error`, `MarketDataRepositoryError`, `BrokerDataRepositoryError`, and `OSError`; map to `ERROR` preserving class/message. Execution best-effort failures are currently converted by broad catches in `DailyBriefingUseCase` and `DailySetupLensImpactUseCase` to warnings/unavailable sections. | Required contract: malformed response/field types and impossible states reach the central outer boundary. Current code cannot guarantee this because its broad catches also swallow contract/programmer exceptions; see blocking finding below. |
| Accumulation | Exact single projection with zero `candidates`, or exact multi projection with zero `rows`. | None; missing optional candidate/row fields are `READY` with unavailable cells. | `ScreenAccumProjectionError` for invalid sort/windows; composition/startup `ValueError`, `RulesError` subclasses, `sqlite3.Error`, `MarketDataRepositoryError`, `BrokerDataRepositoryError`, and `OSError`, preserving class/message. The fixed V1 request should make projection validation errors unreachable but still visible if they occur. | `TypeError`, non-projection `ValueError`, missing/dual projections, malformed DTOs, identity/provenance failures, and impossible canonical-window state propagate to the outer boundary. |
| Ticker | Not applicable after a successful call: candle absence is typed unavailable; optional evidence may be absent in a `READY` response. | `SwingAnalysisDataUnavailable(ticker)` only; map to `UNAVAILABLE` and retain the ticker/reason. Signal evidence unavailability is `READY` with `verdict.signal_assessment_availability` and no fabricated action. | Composition/startup `ValueError`, `RulesError` subclasses, `CorporateActionPolicyConfigError`, `sqlite3.Error`, `MarketDataRepositoryError`, `BrokerDataRepositoryError`, and `OSError`; map to `ERROR` preserving class/message. | `TypeError`, workflow/DTO invariant `ValueError` (including selected candidate without matching evaluation result), incompatible identity/provenance, and response-assembler impossible state propagate to the outer boundary. |
| Corpus health | A valid report with zero observations/labels; show target, split, blockers, and diagnostic-only limitation while screen status is `EMPTY`. A valid report with blockers or unresolved cohort but nonzero corpus is `READY`. | None; unresolved/missing cohorts are blocker-bearing valid reports, never pooled. | Blank target: adapter `ValueError("target must not be blank")` with zero calls. Parse failures: exact `ValueError` message from `SignalReadinessTarget.parse`. Repository/startup: `sqlite3.Error` or `OSError`; map to `ERROR` preserving class/message. | Malformed labels/observations, incompatible identity/cohort objects, type errors, and impossible report state propagate to the outer boundary. |

Exception evidence:
`src/application/use_case/daily_briefing_use_case.py::DailyBriefingUseCase.execute`,
`src/application/services/screen_accum_result_projector.py::ScreenAccumProjectionError`,
`src/application/services/swing_analysis_input_collector.py::SwingAnalysisDataUnavailable`,
`src/application/services/swing_analysis_response_assembler.py::SwingAnalysisResponseAssembler`,
`src/application/use_case/report_signal_readiness_use_case.py::SignalReadinessTarget.parse`,
`src/domain/ports/market_data_repository.py::MarketDataRepositoryError`,
`src/domain/ports/broker_data_repository.py::BrokerDataRepositoryError`, and
`src/application/rules/exceptions.py::RulesError`.

Malformed canonical DTOs, incompatible identity/cohort state, and impossible
states must not become ordinary missing data.

### Blocking finding — application failure boundary

The required invariant above conflicts with current application behavior:

- `DailyBriefingUseCase.execute` catches `Exception` around universe loading,
  regime evaluation, accumulation execution, and setup-lens execution and turns
  failures into warnings (`src/application/use_case/daily_briefing_use_case.py::DailyBriefingUseCase.execute`).
- `DailyBriefingUseCase._data_freshness` catches `Exception` around repository
  reads and turns every failure into missing dates
  (`src/application/use_case/daily_briefing_use_case.py::DailyBriefingUseCase._data_freshness`).
- `DailySetupLensImpactUseCase._evaluate_cell` catches `Exception` from each
  swing workflow and fabricates a warning cell with no action/score. The current
  characterization test explicitly preserves this for a generic `RuntimeError`
  (`src/application/use_case/daily_setup_lens_impact_use_case.py::DailySetupLensImpactUseCase._evaluate_cell`;
  `tests/application/use_case/test_daily_setup_lens_impact_use_case.py::test_one_setup_exception_produces_warning_cell_others_populate`).

Those boundaries cannot distinguish expected operational absence from
`TypeError`, invariant `ValueError`, malformed canonical DTOs, or programmer
errors. Once downgraded, a TUI controller cannot retain the original exception
class or route it to the central outer boundary. Phase 2 therefore cannot meet
the roadmap/task failure contract without an application-layer prerequisite;
changing that behavior is forbidden by this Phase 0 documentation-only task.

Required decision: authorize a separate application task that defines typed
operational/unavailability exceptions for Daily/setup-lens dependencies,
narrows the catches to those exact types, and proves `TypeError`, invariant
`ValueError`, and malformed DTOs propagate. The alternative is an explicit
roadmap/task amendment allowing broad warning downgrade, which weakens the
stated fail-closed invariant.

### E. Packaging and launcher

Confirm or amend with evidence:

```text
extra name: tui
candidate requirement: textual>=8.2,<9
base CLI imports Textual: never
missing-extra exit code: 1
missing-extra message:
TUI support is not installed. Install this checkout with: pip install -e '.[tui]'
```

Confirmed on 2026-07-22. PyPI's current release is Textual 8.2.8 and requires
Python `>=3.9,<4`; the repository requires Python `>=3.11`. Keep the closed
range `textual>=8.2,<9`. Evidence: `pyproject.toml::project.requires-python` and
[Textual 8.2.8 package metadata](https://pypi.org/project/textual/8.2.8/).

The launcher catches `ModuleNotFoundError` only when `exc.name == "textual"`,
prints the exact message above to stderr, and raises `typer.Exit(code=1)`.
Every other `ModuleNotFoundError` or TUI startup/import failure propagates.

The local-only composition guard is also exact. Define these private callables
in `src/adapters/tui/composition.py` and inject them anywhere the existing swing
constructor requires the otherwise network-capable seams:

```python
def _forbid_tui_refresh(**_kwargs):
    raise RuntimeError("TUI local-only contract forbids provider refresh")

def _forbid_tui_sentiment(**_kwargs):
    raise RuntimeError("TUI local-only contract forbids sentiment fetch")
```

They are tripwires, not unavailable-result producers: the fixed false request
flags mean neither is called. A call is a contract failure and must remain
`ERROR`, with no retry or fallback.

## Implementation Checklist

- [x] Protect unrelated worktree changes.
- [x] Inventory all four use cases and DTOs.
- [x] Trace production composition roots and narrow callables.
- [x] Identify network-capable dependencies.
- [x] Identify constructor/startup writes.
- [x] Complete producer/transport map.
- [x] Complete dependency/side-effect inventory.
- [x] Complete exact request defaults.
- [ ] Complete the binding failure matrix after the application failure-boundary decision.
- [x] Resolve dependency and lazy-launch contract.
- [x] Copy resolved facts and the blocker into dependent phase tasks.
- [x] Replace every unresolved placeholder in this task.

## Acceptance Criteria

- [ ] Resolution tables are binding and complete; Daily failure handling is blocked.
- [x] Every later phase has exact request values and transport ownership.
- [x] No second-read or reconstructed-result option remains.
- [ ] Absence, expected exceptions, and invariants are enforceably distinguished.
- [x] Network/mutation-capable dependencies have explicit exclusions.
- [x] Packaging and missing-extra behavior are exact.
- [x] No product, test, config, dependency, or lock file changed.
- [x] `git diff --check` passes.
- [ ] Status becomes `DONE`; completion record is filled.

## Do Not Interpret This As

- Do not implement the TUI or add Textual.
- Do not refactor CLI factories.
- Do not create `GetTui*UseCase` types.
- Do not use CLI rendering/JSON as an intermediate.
- Do not weaken authority, cohort, provenance, or failure behavior.
- Do not leave later agents a choice between transport paths.

## Data, Testing, And Documentation

- Data read: repository source, tests, dependency metadata, and ADRs only.
- Data written: this and dependent task documents only.
- Schema/config/CLI behavior change: none.
- Tests: product tests are not required because no product contract changes;
  every cited claim must be verified through source inspection.
- Documentation impact: resolution tables and dependent task contracts are the
  deliverable.

## Agent Execution Protocol

Before editing, restate hard invariants, exact file boundary, unresolved facts,
and layer plan. During work, update checklist items only after evidence exists.
Before marking done, show that every placeholder is resolved, run `git diff --check`, fill
the completion record, and change status to `DONE`.

## Completion Record

- Completed date: pending failure-boundary decision
- Implementation commit: not created; documentation-only worktree delivery
- Verified source revision: `d7a42875804716600f676620a24c587655d5fc65`
- Files changed: this task and TUI Phase 1–4 backlog contracts
- Key resolved decisions: exact one-owner transports; local-only request values;
  single-window default plus explicit canonical 7/30/90 multi request; fail-closed
  network callable exclusion; product-read-only constructor caveat; cohort and
  exception behavior; Textual `>=8.2,<9` and exact lazy-launch failure
- Commands run: required-doc/source/test inspection with `rg`/`sed`; PyPI Textual
  metadata lookup; placeholder scan; `git diff --check`
- Verification result: documentation boundary preserved; placeholders resolved;
  source citations present; dependent contracts copied; diff check passed; task
  blocked because current Daily/setup-lens broad catches violate the required
  invariant/programmer-error boundary
- Deferred items and owner: user decision required on a separate application
  failure-boundary prerequisite. Byte-for-byte read-only persistence would also
  require a separately approved application/infrastructure task, but is not
  required for V1.
