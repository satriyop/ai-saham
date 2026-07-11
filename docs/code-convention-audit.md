# Code Convention Audit: File Size, Naming Context, and AI-Agent Readability

Date: 2026-07-11

Scope: `src/`, `tests/`, `docs/`, `config/`, and scripts. This is a fresh audit after the previous refactor wave. Old completed status rows were intentionally removed; this file now tracks only current findings.

## Audit Standard

- Preferred Python module size: <= 400 LOC.
- 401-700 LOC: allowed only when one filename maps to one responsibility.
- > 700 LOC: extraction plan required before adding behavior.
- > 1000 LOC: merge blocker unless it is generated data or a temporary characterization fixture.
- A filename must answer: "what responsibility lives here?"
- A use case should read as orchestration, not as DTO/schema/parser/scorer/repository/display implementation.
- Adapters may parse input, wire dependencies, call use cases, render output, and map errors only.
- Tests must be split by behavior contract. A failing test filename should point directly to the behavior under review.

## Executive Findings

The largest remaining risks are no longer the old DTO/facade files. Current risk is concentrated in:

- orchestration use cases that still own calculators, evidence builders, and simulation/statistics logic;
- infrastructure files that combine schema migration, row mapping, and multiple repository families;
- config/parser modules whose filenames are contextual but whose internals still span several parsers;
- CLI adapters that still own file/session/journal workflows instead of only command registration and rendering;
- oversized tests that slow targeted AI-agent review.

## Findings

### 1. Critical: `src/application/use_case/swing_analysis_workflow_use_case.py` is still a workflow warehouse

Pointer: `src/application/use_case/swing_analysis_workflow_use_case.py`, 904 LOC. `execute()` owns refresh, freshness, broker detail, accumulation candidate loading, market context, risk, signal, sizing, backtest, sentiment, trade setup, setup evidence, flow evidence, setup phase, strategy evidence, institutional accumulation evidence, ticker profile, sector context, company quality, corporate action risk, and final re-score/recomposition.

Rationale: The filename says one workflow use case, but the method is a full workflow engine. AI agents must scan most of the file to understand one evidence addition, one preview change, or one warning path.

Recommendation:
- Keep `SwingAnalysisWorkflowUseCase.execute()` as visible orchestration only.
- Extract risk/trade setup composition to `swing_analysis_risk_trade_setup.py`.
- Extract optional evidence assembly to `swing_analysis_evidence_builder.py`.
- Extract market-context preview/recomposition to `swing_analysis_market_context_preview.py`.
- Extract sizing/backtest/sentiment side modules only if touched after the evidence split.

Guardrails:
- Preserve `SwingAnalysisWorkflowResponse` and JSON groups: `verdict`, `evidence`, `diagnostics`.
- Do not let optional evidence overwrite canonical `TradeSetup.action` except through the existing re-score path.
- Keep refresh/freshness policy in application, never CLI.

Risks to maintain:
- Evidence-enriched signal re-score must keep `trade_setup` and MCE preview internally consistent.
- Warning strings are user-facing diagnostics; do not silently rename them.

Edge cases to watch:
- `with_market_context`, `with_technical_gate`, `include_signal_detail`, `include_market_detail`.
- Missing candles must still raise `SwingAnalysisDataUnavailable`.
- Optional evidence builders must remain best-effort and append warnings, not abort the workflow.

### 2. Critical: `src/application/use_case/accumulation_audit_use_case.py` mixes replay orchestration, DTOs, exit simulation, bucketing, and broker quality

Pointer: `src/application/use_case/accumulation_audit_use_case.py`, 861 LOC. It defines policy DTOs, record/response DTOs, replay loop, strict filters, forward return building, TP/SL/max-hold simulation, group stats, broker quality classification, and bucket helpers.

Rationale: Historical audit logic is high-risk because small changes alter learning output. Current filename hides three responsibilities: replay, simulation, and attribution/statistics.

Recommendation:
- Move DTOs/policies to `src/application/dto/accumulation_audit.py`.
- Extract exit simulation to `src/application/services/accumulation_audit_exit_simulator.py`.
- Extract group stats/buckets to `src/application/services/accumulation_audit_statistics.py`.
- Extract broker quality classification to `src/application/services/accumulation_broker_quality_classifier.py`.
- Keep `AccumulationAuditUseCase` as validation + replay orchestration.

Guardrails:
- Preserve same-day stop/target priority semantics.
- Preserve output keys from every `to_dict()`.
- Do not fetch network data; replay must stay local and deterministic.

Risks to maintain:
- Current-universe replay warning must remain visible.
- Custom `forward_return_horizons` must keep dynamic `return_{horizon}d_pct` fields.

Edge cases to watch:
- No forward candles, floor price candidates, empty group stats, and exit grids with zero outcomes.

### 3. Critical: `src/infrastructure/persistence/sqlite_broker_repository.py` combines schema migrator, row mapper, and three repository families

Pointer: `src/infrastructure/persistence/sqlite_broker_repository.py`, 832 LOC. It owns schema creation, three migrations, cleanup policy, transaction serialization, summary CRUD, foreign-flow point CRUD, foreign-flow snapshot CRUD, and broker-daily-flow CRUD.

Rationale: The filename is contextual but too broad. A repository change forces agents to inspect migrations and unrelated table families. Migration risk and query behavior are coupled in one file.

Recommendation:
- Extract schema/migrations to `sqlite_broker_schema.py`.
- Extract row mapping to `sqlite_broker_row_mappers.py`.
- Split storage helpers by table family:
  - `sqlite_broker_summary_store.py`
  - `sqlite_foreign_flow_store.py`
  - `sqlite_broker_daily_flow_store.py`
- Keep `SQLiteBrokerRepository` as the port-facing facade/delegator.

Guardrails:
- Do not change table names, primary keys, indexes, or source-preference behavior.
- Preserve IDX-over-Stockbit preference for broker summaries and Stockbit preference for foreign flow points.
- Migration must remain idempotent.

Risks to maintain:
- Existing DB files must open without manual migration.
- `BrokerDataRepositoryError` wrapping must remain consistent.

Edge cases to watch:
- Legacy `broker_flow_points` rename, duplicate IDX/Stockbit same-date rows, empty batch saves, broker code filters.

### 4. Critical: `src/application/services/swing_tuning_contracts.py` is not just contracts

Pointer: `src/application/services/swing_tuning_contracts.py`, 795 LOC. It contains DTO contracts, default tuning target catalog, readiness planning, proposal draft selection, config diff draft building, value resolution orchestration, dedupe, evidence strength, and bucket formatting.

Rationale: The filename says contracts, but the file performs deterministic proposal orchestration. Agents looking for passive DTOs can accidentally alter tuning behavior.

Recommendation:
- Keep DTOs and constants in `swing_tuning_contracts.py`.
- Move `DEFAULT_TUNING_TARGETS` to `swing_tuning_target_catalog.py`.
- Move readiness/proposal builders to `swing_tuning_proposal_builder.py`.
- Move config-diff draft construction/dedupe to `swing_tuning_config_diff_draft_builder.py`.
- Move evidence strength helpers to `swing_tuning_evidence_strength.py`.

Guardrails:
- Keep `TUNING_CONFIG_DIFF_NO_APPLY_INTENT` and apply-block guarantees unchanged.
- No YAML mutation or AI call may be introduced.
- Preserve `to_dict()` output keys.

Risks to maintain:
- Tests may import public names from `swing_tuning_contracts`; keep compatibility re-exports temporarily.

Edge cases to watch:
- Active setup wildcard expansion, unresolved config paths, duplicate target paths, candidate-only readiness.

### 5. High: `src/infrastructure/config/rules_yaml_loader.py` still combines file loading, YAML parsing, schema construction, and DSL parsers

Pointer: `src/infrastructure/config/rules_yaml_loader.py`, 767 LOC. It loads files, parses YAML, builds rule sets, parses indicators, signal mappings, rules, compound conditions, indicator-vs-value, indicator-vs-indicator, and validates indicator references.

Rationale: The filename is now contextual, but the implementation is a parser cluster. A formula indicator change requires reading condition parser and file-loader code.

Recommendation:
- Keep `RulesYamlLoader` as the `RulesLoader` adapter facade.
- Extract condition parsing to `rules_condition_parser.py`.
- Extract indicator parsing/reference validation to `rules_indicator_parser.py`.
- Extract signal mapping parsing to `rules_signal_mapping_parser.py`.
- Keep file resolution/YAML syntax parsing in the loader.

Guardrails:
- Preserve exception classes and error message context prefixes (`rules[i]`, `when.all[i]`, etc.).
- Preserve `YamlConfigLoader = RulesYamlLoader` compatibility alias.
- Do not move application schema objects into infrastructure.

Risks to maintain:
- AI-generated strategy validation depends on exact validation behavior.

Edge cases to watch:
- Formula indicators, plugin indicators, registry-backed references, string literals vs decimal values.

### 6. High: `src/application/use_case/build_market_context_use_case.py` violates application/infrastructure boundary and mixes factor scoring with fingerprint helpers

Pointer: `src/application/use_case/build_market_context_use_case.py`, 732 LOC. It imports `MarketContextConfig` and `ScoreLabelThresholds` from `src.infrastructure.config`, scores every factor, computes regime confidence, detection fingerprints, staleness/coverage warnings, and banking-vs-IHSG diagnostics.

Rationale: Application use cases should not import infrastructure config classes directly. The file is also too broad: factor scoring and replay fingerprint construction are separate responsibilities.

Recommendation:
- Move config DTOs used by the use case to application or domain config models; infrastructure YAML loader should only instantiate them.
- Extract factor scoring to `market_context_factor_scorers.py`.
- Extract regime confidence and detection inputs to `market_context_detection_inputs.py`.
- Extract staleness/coverage warning helpers to `market_context_quality_warnings.py`.

Guardrails:
- Preserve deterministic score formulas and regime labels.
- Do not change persisted `regime_detection_inputs` keys.
- Do not add repository/provider access to this use case.

Risks to maintain:
- MarketContextEngine callers may expect current config class shape.

Edge cases to watch:
- Missing VIX/EIDO/USD-IDR candles, insufficient SMA history, volatile VIX override, zero foreign-flow baseline.

### 7. High: `src/application/services/setup_phase_detector.py` mixes config models, phase detection, sequence policy, and volume-trigger evidence

Pointer: `src/application/services/setup_phase_detector.py`, 707 LOC. It contains config dataclasses, phase detector, terminal/constructive phase logic, sequence validation, volume trigger quality checks, RS policy reasons, and snapshot assembly.

Rationale: The detector name is contextual, but the module is at the extraction threshold and combines several policy families. Volume trigger evidence is complex enough to deserve its own file.

Recommendation:
- Move config dataclasses to `setup_phase_config.py`.
- Extract volume dry-up/expansion logic to `setup_phase_volume_trigger.py`.
- Extract sequence policy to `setup_phase_sequence_policy.py`.
- Keep `SetupPhaseDetector` focused on selecting terminal vs constructive phase.

Guardrails:
- Preserve `SetupPhaseSnapshot` fields exactly.
- `volume_trigger_confirmed` must remain the only trigger-authoritative volume flag.
- Do not loosen RS hard-exclude/warning behavior.

Risks to maintain:
- Setup family aliases (`foreign-bounce`, `foreign_bounce`, etc.) must continue resolving.

Edge cases to watch:
- Benchmark ticker volume source trust, zero-volume tolerance, insufficient reference sessions, ordered sequence validation.

### 8. High: `src/application/services/swing_backtest_attribution.py` mixes DTO contracts, target catalog, bucketing, and statistic aggregation

Pointer: `src/application/services/swing_backtest_attribution.py`, 700 LOC. It defines attribution DTOs, default tuning target catalog, sample quality, summary builder, trade/candidate bucket extraction, score bucketing, and stat builders.

Rationale: This file sits exactly at the extraction threshold and is a tuning authority. The filename says attribution, but it also owns the tuning target catalog.

Recommendation:
- Move DTOs to `src/application/dto/swing_backtest_attribution.py`.
- Move `DEFAULT_TUNING_TARGETS` to `swing_tuning_target_catalog.py` shared with tuning contracts.
- Move bucket extraction to `swing_backtest_attribution_buckets.py`.
- Keep `summarize_swing_backtest_attribution` as the public orchestrator.

Guardrails:
- Preserve `intent="learning_summary_only_not_entry_logic"`.
- Do not let attribution output influence live entry logic.
- Preserve bucket labels; tuning consumers may depend on them.

Risks to maintain:
- Candidate and trade attribution scopes must not be merged incorrectly.

Edge cases to watch:
- Empty trades with candidate observations, missing signal breakdown, score bucket thresholds.

### 9. High: `src/application/use_case/pre_open_screen_use_case.py` remains too broad for a time-sensitive workflow

Pointer: `src/application/use_case/pre_open_screen_use_case.py`, 672 LOC. It owns config parsing, mover filtering, technical context, ATR entry range, order book gap/spread/imbalance, stop calculation, trend classification, broker backing, foreign VWAP, notation, optional AI research, and candidate construction.

Rationale: This is below the hard threshold but violates single responsibility. Pre-open behavior is operationally sensitive; changes to one gate should not require scanning AI research and broker VWAP code.

Recommendation:
- Move config parsing to `pre_open_screen_config.py`.
- Extract technical context to `pre_open_technical_context.py`.
- Extract entry/stop/range logic to `pre_open_entry_plan.py`.
- Extract broker backing/FVWAP to `pre_open_broker_signals.py`.
- Extract candidate assembly to `pre_open_candidate_builder.py`.

Guardrails:
- Keep browser/provider calls behind ports.
- AI research remains optional and non-authoritative.
- Preserve floor-price and speculative-symbol filters.

Risks to maintain:
- Call auction entry assumptions must remain explicit.

Edge cases to watch:
- Fast mode without order book, missing IEP, floor price 50, insufficient history, ATR unavailable.

### 10. High: `src/adapters/cli/trade_intraday_confirm_commands.py` is not thin enough

Pointer: `src/adapters/cli/trade_intraday_confirm_commands.py`, 648 LOC. It loads confirmation candidates, parses session files, writes sidecars, confirms opening entries, logs journal entries, reviews confirmation, and records outcomes.

Rationale: This adapter owns file/session workflow and journal orchestration. Command files should not own non-trivial confirmation policy or sidecar persistence behavior.

Recommendation:
- Extract session/sidecar file I/O to `intraday_confirmation_session_store.py` in application or infrastructure depending on path ownership.
- Extract confirm/log workflow to `ConfirmIntradayOpenUseCase` / `LogIntradayConfirmationUseCase`.
- Keep CLI file to Typer command definitions, request DTO construction, use-case invocation, rendering, and exception mapping.

Guardrails:
- Preserve command names and JSON/table output.
- Do not move policy into display helpers.
- Keep local-first files explicit.

Risks to maintain:
- Tests patching command module symbols may need compatibility wrappers.

Edge cases to watch:
- Missing session file, malformed sidecar JSON, duplicate journal log, confirmation/outcome date mismatch.

### 11. High: `src/infrastructure/csv/broker_csv_adapter.py` is a parser cluster hidden behind an adapter name

Pointer: `src/infrastructure/csv/broker_csv_adapter.py`, 640 LOC. It detects format, previews, parses simple rows, parses detailed rows, handles encodings, aggregates transactions, maps headers, parses dates/decimals/ints, and maps broker types.

Rationale: The filename says adapter, but most risk is parser logic. Simple and detailed CSV formats are separate contracts and should be independently testable.

Recommendation:
- Keep `BrokerCsvAdapter` as facade implementing `CsvBrokerParser`.
- Extract `simple_broker_csv_parser.py`.
- Extract `detailed_broker_csv_parser.py`.
- Extract shared parsing primitives to `broker_csv_fields.py`.
- Extract transaction aggregation to `broker_transaction_aggregator.py`.

Guardrails:
- Preserve accepted CSV column aliases and encoding fallback behavior.
- Do not change aggregation semantics for top buyers/sellers.

Risks to maintain:
- Real broker CSVs are messy; parser error messages must stay actionable.

Edge cases to watch:
- Decimal separators, missing headers, empty rows, unknown broker type, mixed encodings.

### 12. High: `src/application/use_case/assess_signal_use_case.py` mixes signal config schema with legacy scorer implementation

Pointer: `src/application/use_case/assess_signal_use_case.py`, 618 LOC. It defines many config dataclasses, request/response DTOs, computed response properties, `AssessSignalUseCase`, scoring methods, classification helpers, coverage warning, and rationale construction.

Rationale: The file name says use case, but the first half is signal-engine configuration schema. Agents editing config contracts must scan scoring logic, and agents editing scoring must scan schema models.

Recommendation:
- Move config dataclasses to `src/application/dto/signal_engine_config.py` or `src/application/services/signal_engine_config.py`.
- Move request/response DTOs to `src/application/dto/assess_signal.py`.
- Keep `AssessSignalUseCase` as legacy scorer only, or rename to `legacy_assess_signal_use_case.py` if `SignalEngine` is now canonical.

Guardrails:
- Preserve public imports with compatibility re-exports during transition.
- Do not change scoring thresholds or response properties.

Risks to maintain:
- Many factories/loaders likely import these config classes.

Edge cases to watch:
- Missing enrichment coverage, bandar/foreign scoring, regime conditioning config compatibility.

### 13. High: `src/adapters/cli/trade_swing_display.py` mixes backtest, tuning plan, config diff, and attribution rendering

Pointer: `src/adapters/cli/trade_swing_display.py`, 618 LOC. It renders swing backtest output, tuning plan, tuning proposal, config diff, attribution summary, and formatting helpers.

Rationale: The filename is too broad for multiple display surfaces. Display changes for attribution should not risk tuning diff wording.

Recommendation:
- Split into:
  - `trade_swing_backtest_display.py`
  - `trade_swing_tuning_plan_display.py`
  - `trade_swing_tuning_diff_display.py`
  - `trade_swing_attribution_display.py`
  - `trade_swing_display_formatters.py`
- Keep a small `trade_swing_display.py` facade only if import compatibility is needed.

Guardrails:
- Display must not decide tuning eligibility or evidence strength.
- Display must consume DTO fields, not recompute policy.

Risks to maintain:
- Rich table snapshots and JSON output parity.

Edge cases to watch:
- Empty attribution, rejected diff items, unavailable proposal values, zero trades.

### 14. High: `src/adapters/cli/fetch_universe_commands.py` owns provider payload parsing and universe persistence workflow

Pointer: `src/adapters/cli/fetch_universe_commands.py`, 616 LOC. It extracts lists from provider bodies, lists universes, updates universes, inspects universes, creates universes, writes config, and renders output.

Rationale: The command module is doing adapter parsing plus persistence workflow. Universe creation/update is application behavior and should be testable outside Typer.

Recommendation:
- Extract provider payload normalization to `universe_payload_parser.py`.
- Create application use cases for update/inspect/create universe.
- Keep CLI to Typer options, request construction, use-case calls, and rendering.

Guardrails:
- Preserve command names and config file output shape.
- Do not introduce network calls in application use cases; provider access stays infrastructure/adapter-wired.

Risks to maintain:
- User-created universes are persistent config; accidental key changes are user-visible.

Edge cases to watch:
- Empty provider lists, duplicate tickers, invalid universe names, manual YAML comments.

### 15. High: `src/adapters/cli/indicator_commands.py` mixes indicator compute/snapshot with formula lifecycle commands

Pointer: `src/adapters/cli/indicator_commands.py`, 602 LOC. It owns compute, snapshot, create, list, show, delete, field validation, RSI signal text, and error display.

Rationale: The command group spans two responsibilities: calculating indicators and managing formula artifacts. The filename is contextual but too broad for scan efficiency.

Recommendation:
- Split command modules:
  - `indicator_compute_commands.py`
  - `indicator_snapshot_commands.py`
  - `indicator_formula_commands.py`
- Move reusable CLI formatting/errors to `indicator_display.py`.

Guardrails:
- Keep Typer registration explicit in the group router.
- Formula creation validation remains deterministic; AI is not involved here.

Risks to maintain:
- Tests may patch command symbols; provide route-level compatibility imports if necessary.

Edge cases to watch:
- Missing local data, invalid field names, formula overwrite/delete behavior.

### 16. Medium: `src/adapters/cli/view_ticker_display.py` is a dashboard panel cluster

Pointer: `src/adapters/cli/view_ticker_display.py`, 558 LOC. It renders identity, valuation, analyst, ownership, bandar, profile, candles, corporate actions, insider, seasonality, IEV, sentiment, and the top-level ticker view.

Rationale: Display modules can be larger, but this one has many independent panels. A change to seasonality display should not require scanning valuation and ownership panels.

Recommendation:
- Split by panel family:
  - `view_ticker_identity_display.py`
  - `view_ticker_valuation_display.py`
  - `view_ticker_flow_display.py`
  - `view_ticker_events_display.py`
  - `view_ticker_market_activity_display.py`
- Keep `show_ticker_view()` as facade/composer.

Guardrails:
- No business policy in panel helpers.
- Display missing data as facts, not inferred conclusions.

Risks to maintain:
- Rich layout should remain stable for terminal width.

Edge cases to watch:
- Missing cached data, empty corporate action list, unavailable sentiment logs.

### 17. Medium: `src/adapters/cli/screen_accum_commands.py` still mixes command handling, display wrappers, and watchlist persistence

Pointer: `src/adapters/cli/screen_accum_commands.py`, 541 LOC. It formats values, notation labels, result display wrappers, multi-window execution, command handler, save watchlist, and compare use-case construction.

Rationale: Previous display modules were split, but the command file still owns non-command concerns. Watchlist save behavior is persistence workflow, not CLI command registration.

Recommendation:
- Move `_save_watchlist` to an application service or use case.
- Move compare use-case construction to an adapter factory.
- Keep display wrappers only if they delegate to display modules.

Guardrails:
- Preserve `saham screen accum` command behavior and saved watchlist schema.
- Do not duplicate thresholds from config.

Risks to maintain:
- Save/compare paths are likely used in daily workflow.

Edge cases to watch:
- `--multi`, `--guide`, empty candidates, missing notation provider.

### 18. Medium: `src/infrastructure/config/swing_config.py` hides split-config loading behind one generic config module

Pointer: `src/infrastructure/config/swing_config.py`, 539 LOC. It defines config DTOs, loads merged swing config, reads single/split config files, and merges sections.

Rationale: The filename is contextual but broad. Config schema and config source composition are separate responsibilities.

Recommendation:
- Move dataclasses to `src/application/dto/swing_config.py` or `src/application/services/swing_config_model.py`.
- Keep YAML reading/merge in `src/infrastructure/config/swing_config_loader.py`.
- Keep `swing_config.py` as compatibility facade temporarily.

Guardrails:
- Do not change default paths or merge precedence.
- Application must not depend on infrastructure config models after extraction.

Risks to maintain:
- Many factories likely import `load_swing_config`.

Edge cases to watch:
- Missing split file, partial overrides, invalid nested setup targets.

### 19. Medium: `src/infrastructure/browser/stockbit_fundamentals.py` mixes parser, cache repository, schema, and live provider

Pointer: `src/infrastructure/browser/stockbit_fundamentals.py`, 528 LOC. It parses financial values, market cap, fundamentals, historical rows, ensures cache schema, checks freshness, reads/writes cache, writes historical rows, and fetches Stockbit payloads.

Rationale: Provider, parser, and cache store are separate infrastructure responsibilities. The filename suggests provider behavior, but parser/cache internals dominate.

Recommendation:
- Extract payload parsing to `stockbit_fundamentals_parser.py`.
- Extract SQLite cache to `stockbit_fundamentals_cache.py`.
- Keep `StockbitFundamentalsProvider` as orchestration facade.

Guardrails:
- Preserve TTL/cache freshness behavior.
- Do not leak raw Stockbit payloads outside infrastructure.
- Preserve conservative publication lag for historical rows.

Risks to maintain:
- Fundamentals feed into risk gates and point-in-time replay.

Edge cases to watch:
- Missing keystats fields, non-numeric financial strings, historical rows with publication lag.

### 20. Medium: `src/application/services/accumulation_observation_fingerprint.py` is a dense persisted-schema builder

Pointer: `src/application/services/accumulation_observation_fingerprint.py`, 522 LOC. It builds candidate observation payloads and many nested fingerprint sections for signal, setup, institutional, profile, sector, company quality, volatility, and request/config metadata.

Rationale: The file is contextual, but persisted schemas are high blast-radius. Multiple schema families in one builder make small changes risky.

Recommendation:
- Split by payload section:
  - `accumulation_observation_signal_fingerprint.py`
  - `accumulation_observation_setup_fingerprint.py`
  - `accumulation_observation_institutional_fingerprint.py`
  - `accumulation_observation_profile_fingerprint.py`
  - `accumulation_observation_metadata.py`
- Keep `build_candidate_observation_payload()` as facade.

Guardrails:
- No key rename without explicit migration/compatibility note.
- Preserve missing-data semantics: missing evidence lowers coverage, not conviction.

Risks to maintain:
- Backfill, signal labels, and tuning attribution depend on exact payload keys.

Edge cases to watch:
- `as_of_date`, `captured_at`, diagnostic evidence with unavailable reasons, `None` vs absent keys.

### 21. Medium: `src/application/use_case/accumulation_screen_use_case.py` still has an extractable per-ticker pipeline

Pointer: `src/application/use_case/accumulation_screen_use_case.py`, 570 LOC. The old warehouse was reduced, but `execute()` still owns a long per-ticker pipeline: early fundamentals pruning, foreign-flow score assignment, corporate action enrichment, seasonality, insider activity, analyst/shareholding/bandar/fundamentals/notation/forward-estimate enrichment, signal assessment, flow evidence, setup phase, and pass/reject classification.

Rationale: The file is below the 700 LOC extraction threshold, so it is not urgent. The remaining issue is scan locality: agents changing one enrichment source or one rejection rule still need to inspect a broad per-ticker block.

Recommendation:
- Extract structural pruning to `accumulation_candidate_structural_filter.py`.
- Extract provider-backed enrichment to `accumulation_candidate_enricher.py`.
- Extract foreign-flow score, signal assessment, flow evidence, setup phase, and pass/reject result to `accumulation_candidate_signal_assessor.py`.
- Keep `AccumulationScreenUseCase` as ticker loop, survivor collection, sector breadth, risk funnel, sort, persistence, and response construction.

Guardrails:
- Preserve early-pruning behavior; do not fetch all enrichment providers before market-cap/Piotroski rejection.
- Preserve `all_results` rejected samples for observation learning.
- Preserve `screen_result` values: `pass`, `rejected_flow`, `rejected_signal`.
- Preserve setup phase computed once before persistence.
- Do not move provider calls or screening policy to CLI.

Risks to maintain:
- Moving enrichment too early can slow full-universe screens and change skipped ticker counts.
- Moving pass/reject classification without tests can break signal-label learning samples.

Edge cases to watch:
- Missing fundamentals with active market-cap/Piotroski gates.
- Forward estimates where `forward_pe` is absent and current price must derive it.
- Flow evidence builder failure must remain best-effort.

### 22. Medium: Oversized test files slow targeted review

Pointers:
- `tests/application/use_case/test_swing_backtest.py`, 892 LOC.
- `tests/domain/test_backtest_engine.py`, 802 LOC.
- `tests/application/rules/test_interpreter.py`, 774 LOC.
- `tests/application/use_case/test_swing_analysis_workflow.py`, 741 LOC.
- `tests/adapters/cli/test_swing_commands_tuning.py`, 686 LOC.
- `tests/application/use_case/test_intraday_backtest.py`, 687 LOC.
- `tests/adapters/cli/test_swing_display_alpha_sector.py`, 680 LOC.
- `tests/adapters/cli/test_fetch_market_commands.py`, 661 LOC.

Rationale: Tests are now the biggest AI-agent scanning burden. Many are organized by old module name instead of behavior contract.

Recommendation:
- Split `test_swing_backtest.py` into entry/exit, attribution, regime-provider, forward-data, and portfolio-cap files.
- Split `test_backtest_engine.py` by entity/value-object vs engine-run behavior.
- Split `test_interpreter.py` into condition types, rule ordering, required indicators, and rationale.
- Split `test_swing_analysis_workflow.py` by refresh, optional evidence, market context, serialization.
- Split CLI tests by command family and output contract.

Guardrails:
- No placeholder tests.
- Do not weaken characterization coverage during splits.
- Shared fixtures may move to local `*_fixtures.py` files only when they reduce duplication.

Risks to maintain:
- Monkeypatch paths often break after production module splits.

Edge cases to watch:
- Test order independence, fixture mutation leakage, CLI runner state.

### 23. Medium: Large documentation files are not reviewable as active working specs

Pointers:
- `docs/signal_refactor.md`, 2826 LOC.
- `docs/stockbit_api_probe_response.md`, 1784 LOC.
- `docs/how_to_intraday_trading.md`, 1261 LOC.
- `docs/workflow_swing_foreign_accumulation.md`, 1019 LOC.
- `docs/signal_refactor_tracker.md`, 915 LOC.

Rationale: These are not source modules, but they are too large for future agents to use as active guidance. Large historical docs blur current rules, old plans, and raw probe data.

Recommendation:
- Mark raw probe/old tracker docs as archival at the top, or move under `docs/archive/`.
- Split active workflow docs into quick-reference, operational checklist, and design notes.
- Keep `AI_AGENT_CHECKLIST.md`, ADRs, and README as the authoritative current guidance.

Guardrails:
- Do not delete historical evidence without user approval.
- Do not let archived docs override ADR/checklist instructions.

Risks to maintain:
- Agents may follow stale plans if active vs archival status is unclear.

Edge cases to watch:
- Links from README and ADRs to moved docs.

## Refactor Order

1. Split `swing_analysis_workflow_use_case.py` evidence/risk/recomposition first.
2. Split `accumulation_audit_use_case.py` DTOs, exit simulator, and stats.
3. Split `sqlite_broker_repository.py` schema/migrations and table-family stores.
4. Split `swing_tuning_contracts.py` and `swing_backtest_attribution.py` target catalog/builders.
5. Split `rules_yaml_loader.py` parser internals.
6. Fix `build_market_context_use_case.py` boundary violation and factor helpers.
7. Split `setup_phase_detector.py` volume/sequence/config.
8. Extract the remaining `accumulation_screen_use_case.py` per-ticker pipeline when touching enrichment or rejection behavior.
9. Thin CLI command modules: intraday confirm, universe, indicator, screen accumulation.
10. Split high-value tests after each production extraction.

## Code Convention for Future Agents

These rules should be kept in `AI_AGENT_CHECKLIST.md` and followed in review:

- Files above 700 LOC require an extraction plan before adding behavior.
- Files above 1000 LOC are merge blockers unless generated or temporary characterization fixtures.
- A filename must expose one dominant responsibility: use case, DTO, parser, provider, repository, display, command, factory, validator, simulator, statistics, or config loader.
- Compatibility facades may re-export or delegate only; they must not keep implementation logic.
- Use cases own workflow orchestration only. Extract calculators, parsers, serializers, evidence builders, simulators, statistics, and persistence stores.
- Application must not import infrastructure config classes directly. Infrastructure loads/parses config; application consumes application/domain config models.
- CLI command modules must stay thin: parse options, build request DTOs, wire dependencies, call use cases, render output, map exceptions.
- Display modules render facts only; they must not decide scores, thresholds, actions, or business status.
- Persisted schema builders must be split by schema section once they exceed 400 LOC; no key rename without compatibility notes.
- Repository modules above 700 LOC must split schema/migration, row mapping, and table-family stores.
- Tests follow the same size rules. Split by behavior contract, not by arbitrary line count.
- Placeholder tests are forbidden. Every collected test must assert real behavior or a real contract.

## Acceptance Gate for Extraction PRs

- Behavior is unchanged unless the task explicitly says otherwise.
- Existing CLI commands still register under the same names.
- JSON/CSV/persisted contracts are unchanged or migrated explicitly.
- Tests cover moved responsibilities at their new boundaries.
- No adapter gains workflow/policy during extraction.
- No application use case gains infrastructure imports.
- AI can locate the edited responsibility from the filename alone.
