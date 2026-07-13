# Code Convention Audit - Production Code Only

Scope: fresh audit of production code under `src/**/*.py`, plus architecture/test harness checks where they can hide production boundary violations. Documentation content is excluded from audit targets.

Audit goals:
- Keep files small enough for AI agents and humans to scan quickly.
- Make filenames expose the dominant responsibility.
- Prefer single responsibility, composability, deduplication, simplification, and clear boundaries.
- Remove hidden service-locator/global wiring patterns.
- Remove application-to-infrastructure boundary allowlists.
- Keep CLI adapters thin: parse input, wire dependencies, call use cases, render output, map errors.

## Findings

Status legend:
- `OPEN`: not fixed.
- `PARTIAL`: guardrail exists, but production cleanup remains.
- `DONE`: only use after implementation is vetted.

### 1. Critical: application-layer bootstrap factories still import infrastructure

Status: DONE.

Vetted: 2026-07-13. Concrete engine/registry/session wiring has been moved out
of the application layer; the named application bootstrap/session files no
longer import `src.infrastructure`. The remaining concrete factories live in
adapter or infrastructure composition modules, and focused boundary tests pass.

Pointers:
- `src/application/services/engine_bootstrap/risk_engine_factory.py`
- `src/application/services/engine_bootstrap/signal_engine_factory.py`
- `src/application/services/engine_bootstrap/indicator_registry_factory.py`
- `src/application/services/stockbit_session.py`
- `tests/architecture/test_layer_boundaries.py`

Rationale: Application services are acting as composition roots and service locators. The architecture guard allowlists these imports, so the test passes while application still constructs SQLite repositories, Stockbit providers, plugin loaders, and infrastructure config.

Recommendation:
- Move concrete wiring to infrastructure or adapter composition modules.
- Keep application factories pure: accept ports/config objects/constructor callables, return application services.
- Delete the allowlist entries after each factory is moved.
- Replace `get_stockbit_session()` with an application port plus an infrastructure implementation.

Guardrails:
- Do not remove boundary allowlist entries until code no longer imports the forbidden module.
- Preserve public facade imports temporarily only as re-export/delegation shims.
- Do not move business policy into adapters during the migration.

Risks to maintain:
- RiskEngine, SignalEngine, and registry construction are broad shared paths. A silent wiring change can disable gates, enrichment, formulas, or plugins.

Edge cases to watch:
- `with_enrichment=False` neutral fallback.
- plugin discovery errors.
- formula storage load failures.
- missing Stockbit session behavior.

### 2. Critical: architecture boundary test normalizes legacy violations instead of forcing cleanup

Status: DONE.

Vetted: 2026-07-13. `BASELINE_ALLOWLIST` and
`ALLOWLISTED_PATHS_REQUIRE_BOUNDARY_CLEANUP` are empty. The architecture guard
passes with no application-to-infrastructure or domain-to-application
exceptions.

Pointer: `tests/architecture/test_layer_boundaries.py`, `BASELINE_ALLOWLIST`.

Rationale: The test is valuable, but the allowlist is now a permanent compatibility contract for application-to-infrastructure imports. It catches new drift but masks existing drift, and agents can mistake allowlisted architecture violations as acceptable patterns.

Recommendation:
- Split the allowlist into dated cleanup groups with one finding per group.
- Add a test that fails if an allowlisted path is touched without removing or reducing its entries.
- Add a dedicated assertion that no `src/application/services/engine_bootstrap/*factory.py` imports `src.infrastructure`.
- Remove entries incrementally after moving composition roots outward.

Guardrails:
- Do not weaken the current forbidden import scan.
- Do not add new allowlist entries for new code.
- Require a canonical owner path for each moved factory before deleting the old import path.

Risks to maintain:
- A too-broad cleanup can break many CLI commands at once.

Edge cases to watch:
- TYPE_CHECKING-only imports that AST sees.
- compatibility facades that re-export old names.
- tests patching old factory import paths.

### 3. Critical: `src/adapters/cli/screen_accum_commands.py` still owns workflow/policy branches

Status: OPEN.

Pointer: `src/adapters/cli/screen_accum_commands.py`, 467 LOC.

Rationale: The command parses CLI flags, resolves universes, builds request DTOs, runs multi-window orchestration, computes broker quality, runs strategy/risk checks for visible rows, emits JSON schema, and saves watchlists. This is still more than adapter work.

Recommendation:
- Move multi-window execution and broker-quality attachment to an application use case/service.
- Move strategy signal overlay into an application service that receives registry/rules loader ports.
- Move watchlist save continuation into an application command workflow.
- Keep the CLI file limited to options, request construction, use-case invocation, and display selection.

Guardrails:
- Preserve `saham screen accum` flags, defaults, JSON keys, and watchlist behavior.
- Do not recompute strategy/risk only for visible rows unless that behavior is explicitly preserved and tested.
- Do not move Typer parsing into application.

Risks to maintain:
- Screen output and saved watchlists are user-facing workflow contracts.

Edge cases to watch:
- `--multi --format json`.
- `--strategy` not found.
- `--save` with filtered/top candidates.
- `min_streak` post-filter currently mutates response candidates.

### 4. Critical: `src/adapters/cli/fetch_market_commands.py` still owns provider/status workflow

Status: OPEN.

Pointer: `src/adapters/cli/fetch_market_commands.py`, 478 LOC.

Rationale: The file still resolves tickers before the use case, validates provider preconditions, decides calendar skip status, fetches live market status, builds row coloring logic, injects per-ticker callbacks, calls calendar refresh, computes expected trading day, and refreshes global context tickers. This is too much workflow and policy for a CLI command module.

Recommendation:
- Introduce `FetchMarketCommandWorkflowUseCase` or an application coordinator that returns a display-ready progress event stream and final summary.
- Move provider precondition and calendar/context refresh sequencing into application.
- Move row coloring/status classification into display helpers that consume application status objects.
- Keep the CLI as flag parsing, dependency wiring, and rendering.

Guardrails:
- Preserve fail-fast behavior for missing Stockbit session.
- Preserve exact status strings unless tests are updated deliberately.
- Preserve one-calendar-sync-per-run behavior.

Risks to maintain:
- Daily cron depends on this command. Any status or exception behavior drift can break automation.

Edge cases to watch:
- `--broker-only`.
- `--no-enrichment` plus `--no-calendar`.
- benchmark ticker insertion.
- Stockbit-backed candle fetch path.

### 5. High: `src/adapters/cli/fetch_broker_commands.py` mixes command adapter, provider factory, direct provider calls, and persistence continuation

Status: OPEN.

Pointer: `src/adapters/cli/fetch_broker_commands.py`, 487 LOC.

Rationale: The file implements provider creation, auth handling, exact foreign-flow follow-up fetch, foreign-top scan persistence, broker-history persistence, CSV import mapping, and display. Several branches bypass use cases and call providers/repositories directly.

Recommendation:
- Extract provider construction to `fetch_broker_provider_factory.py`.
- Create application use cases for:
  - broker summary fetch plus optional exact Stockbit flow continuation,
  - top-foreign scan persistence,
  - broker-history fetch persistence.
- Keep CSV import command as a thin wrapper around `ImportBrokerDataUseCase`.

Guardrails:
- Preserve provider names: `idx`, `stockbit`.
- Preserve auth error text and exit codes.
- Preserve save/no-save behavior.

Risks to maintain:
- Broker data is consumed by accumulation, swing analysis, and market refresh.

Edge cases to watch:
- Stockbit provider unavailable.
- `response.from_cache` currently controls whether exact flow is fetched.
- `--on-error report` CSV behavior.

### 6. High: `src/adapters/cli/trade_accum_commands.py` is adapter plus workflow factory plus journal policy

Status: OPEN.

Pointer: `src/adapters/cli/trade_accum_commands.py`, 339 LOC.

Rationale: The command module loads swing/backtest config at import time, computes default TP/SL constants, constructs accumulation screen use cases, creates regime engine, wires journals, passes many policy fields into `LogSwingCandidateUseCase`, and formats results. Filename suggests CLI command ownership, but it contains workflow assembly and policy projection.

Recommendation:
- Move `_accumulation_log_impl` wiring to `trade_accum_workflow_factory.py`.
- Move setup target/default TP/SL resolution into application or a typed command config object.
- Keep `trade_accum_commands.py` as command registration and output only.

Guardrails:
- Preserve journal paths and row formats.
- Preserve duplicate-log behavior.
- Do not change setup gate inputs passed to `LogSwingCandidateUseCase`.

Risks to maintain:
- Journals are persistent user artifacts; schema drift is high cost.

Edge cases to watch:
- `from_analysis=False`.
- missing accumulation candidate.
- failed setup gates.
- regime unavailable warning.

### 7. High: import-time config loading creates hidden global state in CLI modules

Status: OPEN.

Pointers:
- `src/adapters/cli/screen_accum_commands.py`: `_SC`, `_ASC`
- `src/adapters/cli/trade_swing_backtest_runner.py`: `_SC`, `_BT`, `_ASC`
- `src/adapters/cli/trade_swing_tuning_commands.py`: `_SC`, `_BT`
- `src/adapters/cli/trade_accum_commands.py`: `_SC`, `_BT`, derived TP/SL constants
- `src/adapters/cli/analyze_swing_command_config.py`: `SWING_CONFIG`, `SWING_BACKTEST_CONFIG`, `ANALYZE_SWING_CONFIG`, `ACCUMULATION_SCREENER_CONFIG`
- `src/adapters/cli/screen_accum_*display.py` and `screen_accum_formatters.py`: `_ASC`/`_SC`
- `src/adapters/cli/today_commands.py`: `_ASC`

Rationale: These modules read config at import time and freeze values before command invocation. Tests then patch globals instead of passing explicit configs. This is hidden global state and makes config reload/order-dependent behavior hard to reason about.

Recommendation:
- Replace module-level loaded config objects with `load_*` calls inside factory functions or explicit `CommandConfig` objects passed to helpers.
- For display modules, pass display thresholds/config from command/use-case response instead of loading config inside display.
- Keep `APP_CFG` path constants only where Typer default values require them; avoid derived policy objects at import time.

Guardrails:
- Preserve CLI defaults.
- Do not repeatedly parse config inside tight ticker loops.
- Use one load per command invocation, then pass the object explicitly.

Risks to maintain:
- Existing tests may depend on import-time config. Update tests to pass config explicitly instead of monkeypatching globals.

Edge cases to watch:
- user config overrides.
- config file changed between command imports in long-lived test processes.
- display thresholds drifting from engine config.

### 8. High: duplicated config loading/wiring exists across swing and accumulation workflow factories

Status: OPEN.

Pointers:
- `src/adapters/cli/analyze_swing_workflow_factory.py`
- `src/adapters/cli/screen_accum_workflow_factory.py`
- `src/adapters/cli/trade_accum_commands.py`
- `src/adapters/cli/trade_swing_backtest_runner.py`

Rationale: The same provider bundle, ticker-profile factory, institutional accumulation config factory, sector builder factory, company-quality builder factory, risk gate resolution, and repository construction appear in multiple adapter modules. This is service-locator drift under different filenames.

Recommendation:
- Introduce a single infrastructure/adapter composition bundle for stock-analysis workflows, e.g. `StockAnalysisWorkflowDependencies`.
- Bundle repositories, Stockbit provider bundle, config factories, classifier factories, and risk/signal engines.
- Application use cases should receive ports/configs; adapter factories should receive a typed bundle instead of rebuilding the same graph.

Guardrails:
- Do not make the bundle a global singleton.
- Do not put business decisions inside the bundle.
- Keep tests able to provide fake bundles.

Risks to maintain:
- Dependency graph drift can produce different evidence between screen, analyze, trade log, and backtest.

Edge cases to watch:
- read-only Stockbit provider behavior.
- with/without risk.
- candidate observation repository path.
- custom db path.

### 9. High: `src/application/use_case/swing_analysis_workflow_use_case.py` remains a broad linear workflow

Status: OPEN.

Pointer: `src/application/use_case/swing_analysis_workflow_use_case.py`, 538 LOC.

Rationale: The use case still performs refresh, freshness, flow detail, accumulation candidate build, market context, risk, signal, ATR sizing, setup sizing, strategy backtest, sentiment, evidence build, signal re-score, trade setup recomposition, diagnostics assembly, and module flags in one `execute()`.

Recommendation:
- Extract orchestration phases into named application collaborators:
  - `SwingAnalysisInputCollector`
  - `SwingAnalysisDecisionComposer`
  - `SwingAnalysisOptionalEvidenceRunner`
  - `SwingAnalysisSizingService`
  - `SwingAnalysisResponseAssembler`
- Keep `execute()` as a phase pipeline with explicit intermediate DTOs.

Guardrails:
- Preserve warning order and wording unless tests are intentionally updated.
- Preserve canonical signal re-score after evidence build.
- Preserve market-context risk preview semantics.

Risks to maintain:
- This is the main single-ticker command. Small ordering changes can alter verdict consistency.

Edge cases to watch:
- no candles.
- accumulation unavailable.
- signal engine absent.
- evidence-enriched re-score failure.
- setup sizing with explicit entry.

### 10. High: `src/domain/value_objects/signal_observation_fingerprint_serialization.py` is a persisted-schema warehouse in domain

Status: OPEN.

Pointer: `src/domain/value_objects/signal_observation_fingerprint_serialization.py`, 565 LOC.

Rationale: The split reduced the original value-object file, but the serializer is still a huge flat persisted-schema map in the domain layer. It contains setup, strategy, flow, regime, institutional accumulation, ticker profile, sector, company quality, alpha/trigger, volatility, and legacy alias parsing in one file.

Recommendation:
- Move persisted JSON compatibility serialization into application/persistence-facing services unless domain locality is explicitly required.
- Split by schema section:
  - `signal_fingerprint_setup_serialization.py`
  - `signal_fingerprint_flow_serialization.py`
  - `signal_fingerprint_regime_serialization.py`
  - `signal_fingerprint_context_serialization.py`
  - `signal_fingerprint_alpha_trigger_serialization.py`
- Keep a small facade that composes section serializers.

Guardrails:
- Do not rename persisted keys.
- Preserve legacy aliases.
- Preserve missing-key versus explicit `None` behavior.

Risks to maintain:
- Observation replay, readiness, and tuning attribution depend on exact keys.

Edge cases to watch:
- legacy `*_at_signal` fields.
- nested `market_regime` reconstruction.
- tuple/list conversion.
- `phase_history` and route metadata lists.

### 11. Medium: Stockbit PIT providers still repeat cache/schema/read/write patterns

Status: OPEN.

Pointers:
- `src/infrastructure/browser/stockbit_insider.py`, 508 LOC.
- `src/infrastructure/browser/stockbit_earnings.py`, 447 LOC.

Rationale: Shared PIT cache helpers exist, but these providers still own schema rebuilds, sentinel rows, as-of SQL, freshness, row mapping, write loops, endpoint walk logic, and payload parsing in one file. Each file is understandable alone, but duplicated cache mechanics make future PIT changes risky.

Recommendation:
- Extract provider-specific cache stores:
  - `stockbit_insider_cache.py`
  - `stockbit_earnings_cache.py`
- Keep provider files focused on port method, API fetch orchestration, and parser calls.
- Keep parsers pure and separate from SQLite logic.

Guardrails:
- Preserve PIT as-of semantics.
- Preserve sentinel `__NONE__` behavior for insider.
- Preserve earnings current-quarter fallback walk.

Risks to maintain:
- Backtests rely on point-in-time enrichment correctness.

Edge cases to watch:
- date-only versus ISO datetime `fetched_date`.
- no-result snapshot.
- stale current quarter with latest reported quarter.
- migrated legacy schema.

### 12. Medium: `src/adapters/cli/trade_swing_tuning_display.py` is a display pack for unrelated panels

Status: OPEN.

Pointer: `src/adapters/cli/trade_swing_tuning_display.py`, 509 LOC.

Rationale: The module renders review history, loop status, comparison, post-apply measurement, validation, dry-run, apply, and verify panels. It is display-only, but the filename is too broad and the file is large enough that agents must scan unrelated panels for a small output edit.

Recommendation:
- Split by panel family:
  - `trade_swing_tuning_review_display.py`
  - `trade_swing_tuning_patch_display.py`
  - `trade_swing_tuning_loop_status_display.py`
  - `trade_swing_tuning_measurement_display.py`
- Keep formatting helpers local to the module that uses them, or move truly shared scalar formatters to a small private display utility.

Guardrails:
- Do not change rendered text unless display tests are updated.
- Keep Rich table/panel style consistent.
- Keep public function names re-exported temporarily if commands import them.

Risks to maintain:
- Tuning patch output is a safety review surface; unclear display changes can hide bad patch state.

Edge cases to watch:
- missing review.
- invalid patch.
- not-ready dry run.
- post-apply measurement unavailable.

### 13. Medium: `src/adapters/cli/analyze_swing_workflow_factory.py` is a mixed composition root and mini workflow

Status: OPEN.

Pointer: `src/adapters/cli/analyze_swing_workflow_factory.py`, 280+ LOC.

Rationale: The file is nominally a factory, but it also defines nested accumulation candidate building, setup evaluation, broker detail adaptation, auto-refresh wiring, and sentiment fetching. These are not all the same responsibility.

Recommendation:
- Split into:
  - `analyze_swing_dependency_factory.py` for repositories/providers/engines.
  - `analyze_swing_candidate_builder.py` for single-ticker accumulation candidate construction.
  - `analyze_swing_optional_fetchers.py` for auto-refresh and sentiment fetch wrappers.
- Keep `create_swing_analysis_workflow()` as a thin assembly function.

Guardrails:
- Preserve injected callables expected by `SwingAnalysisWorkflowUseCase`.
- Do not move CLI-only output suppression into application.
- Preserve default strategy/sentiment behavior.

Risks to maintain:
- The factory determines whether analyze-swing evidence matches screen-accum evidence.

Edge cases to watch:
- stderr/stdout suppression.
- missing sentiment provider.
- Stockbit providers cache-only mode.
- setup `None`.

### 14. Medium: `src/adapters/cli/screen_accum_workflow_factory.py` imports private bootstrap resolver and infrastructure config directly

Status: OPEN.

Pointer: `src/adapters/cli/screen_accum_workflow_factory.py`.

Rationale: The file imports `_resolve_risk_gates` from `src.application.services.bootstrap`, an underscored/private API, then reads infrastructure config directly to construct `AssessRiskUseCase`. This is brittle and duplicates risk-engine wiring outside the canonical engine factory path.

Recommendation:
- Replace private `_resolve_risk_gates` import with a public risk-use-case/risk-engine factory owned by the proper composition layer.
- Pass loaded risk config explicitly or create a typed `RiskWorkflowDependencies`.
- Keep private helper imports out of adapters.

Guardrails:
- Preserve current risk gates and missing-data behavior.
- Do not silently switch from `AssessRiskUseCase` to `RiskEngine` unless output compatibility is proven.

Risks to maintain:
- Accumulation screen final action depends on risk composition.

Edge cases to watch:
- `with_risk=False`.
- custom `db_path`.
- risk config disabled gates.

### 15. Medium: integration tests use production bootstrap fixtures that hide boundary coupling

Status: OPEN.

Pointer: `tests/integration/conftest.py`, especially `registry_with_formulas`.

Rationale: Integration fixtures call `create_indicator_registry()` from application bootstrap, which currently imports infrastructure plugin and formula storage implementations. That makes tests pass through the same allowlisted architecture violation instead of forcing explicit port wiring.

Recommendation:
- Change integration fixtures to construct `IndicatorRegistry` directly for pure tests.
- For formula-storage integration, instantiate `FormulaStorage` explicitly in the test and pass it through a composition-layer factory outside application.
- Add a test that application-layer fixture helpers do not import infrastructure bootstrap paths.

Guardrails:
- Do not remove integration coverage for plugin/formula loading.
- Keep offline deterministic test data.
- Avoid global fixtures that patch config for unrelated tests.

Risks to maintain:
- A too-pure fixture may stop testing real plugin/formula integration. Split pure and integration fixtures instead of deleting coverage.

Edge cases to watch:
- custom formula loading.
- plugin discovery in temp dirs.
- registry with broker/market repositories.

## Code Convention For Future Agents

Add or keep these rules in `AI_AGENT_CHECKLIST.md` or an ADR:

1. Application-layer modules must not be composition roots for concrete infrastructure. Composition belongs in adapters or infrastructure factories; application receives ports, typed configs, and callables.
2. Architecture allowlists are temporary debt, not accepted design. Each allowlist entry needs a cleanup owner, canonical replacement path, and a test that prevents new usage.
3. CLI command files over 300 LOC require proof they are still thin. If they resolve universes, run secondary use cases, save follow-up artifacts, or classify statuses, extract an application workflow.
4. No module-level loaded config objects in CLI/display modules. Load config once per command invocation or pass it through typed command config objects.
5. Display modules may be large only when every function renders one cohesive surface. Split display files by panel family once unrelated panels share only scalar formatting helpers.
6. Persisted-schema serializers must split by schema section and keep legacy aliases explicit. Domain value-object packages must not become flat JSON compatibility warehouses.
7. Provider files must separate endpoint orchestration, payload parsing, PIT cache store, and schema migration once any two of those responsibilities exceed one screen.
8. Tests must not hide architecture violations by relying on global bootstrap fixtures. Pure tests construct pure services; integration tests name the infrastructure they exercise.
9. Adapters must not import private application helpers. If a helper is needed outside its module, promote a public application service or move the composition outward.
10. Shared dependency graphs must be explicit typed bundles, not repeated ad hoc factory code or service-locator functions.

## Suggested Refactor Order

1. Remove application-to-infrastructure bootstrap allowlists by moving concrete factories out of `src/application`.
2. Purge import-time config globals from CLI/display modules.
3. Thin `screen_accum_commands.py` and `fetch_market_commands.py` by moving workflow branches into application coordinators.
4. Consolidate duplicated swing/accumulation dependency wiring into explicit composition bundles.
5. Split persisted fingerprint serialization by schema section.
6. Extract Stockbit PIT cache stores from insider and earnings providers.
7. Split large display-only tuning panels by responsibility.

## Acceptance Gate For Refactor PRs

- No production behavior changes unless explicitly requested.
- No CLI command names, option names, JSON keys, CSV keys, or persisted keys change without migration notes.
- No new application/domain import from infrastructure or adapters.
- No new architecture allowlist entry.
- Existing tests for moved responsibilities pass at their new boundaries.
- New filenames must answer "what responsibility lives here?"
- Facades may remain only as compatibility shims.
- No adapter gains workflow or policy.
- No module-level config object is introduced in CLI/display code.
- AI agents can locate the edited responsibility from filename alone.
