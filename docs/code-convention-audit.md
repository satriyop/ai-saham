# Code Convention Audit - Production Code Only

Scope: fresh audit of `src/**/*.py` only. Documentation and tests are intentionally excluded.

Audit goals:
- Keep files small enough for AI agents and humans to scan quickly.
- Make filenames expose the dominant responsibility.
- Prefer single responsibility, composability, deduplication, simplification, and clear boundaries.
- Preserve deterministic-first behavior and current public contracts during extraction.

## Findings

### 1. Critical: `src/domain/value_objects/signal_forward_label.py` is a schema warehouse

Pointer: `src/domain/value_objects/signal_forward_label.py`, 625 LOC. `SignalObservationFingerprint` alone spans setup, strategy, flow, market regime, institutional accumulation, ticker profile, sector context, company quality, alpha/trigger, volatility fields, plus `to_dict()` and `from_dict()` compatibility parsing.

Rationale: This is too dense for the domain layer. One persisted fingerprint change forces agents to scan hundreds of unrelated keys and compatibility aliases.

Recommendation:
- Extract `SignalObservationFingerprint` into `src/domain/value_objects/signal_observation_fingerprint.py`.
- Extract serialization/parsing into `src/application/services/signal_observation_fingerprint_serializer.py` or a clearly named domain-safe serializer if existing persistence requires domain locality.
- Split field groups into named helpers: setup, strategy, flow, regime, institutional accumulation, ticker profile, sector, company quality, alpha/trigger, volatility.
- Keep `signal_forward_label.py` focused on `SignalLabelHorizon`, `SignalForwardOutcome`, and `SignalForwardLabel`.

Guardrails:
- Do not rename persisted keys.
- Preserve legacy aliases in `from_dict()`.
- Preserve `None` versus missing-key semantics.

Risks to maintain:
- Signal label generation, readiness reporting, observation persistence, and tuning attribution depend on exact fingerprint keys.

Edge cases to watch:
- `market_regime` fallback reconstruction.
- Legacy `*_at_signal` aliases.
- Tuple/list conversion for JSON fields.

### 2. Critical: `src/adapters/cli/analyze_swing_broker_display.py` is not display-only

Pointer: `src/adapters/cli/analyze_swing_broker_display.py`, 606 LOC. Despite the `_display.py` name, it defines DTOs, broker-quality policy notes, repository-derived flow detail builders, broker weighting math, and formatting helpers.

Rationale: A display module should render facts. This file decides broker quality and derives facts from repositories, which makes the adapter heavier than its filename implies.

Recommendation:
- Move `BrokerQualityNote`, `FlowDetail`, `BrokerDetailLine`, and `BrokerDetail` to `src/application/dto/swing_broker_detail.py`.
- Move `build_flow_detail`, `build_broker_detail_from_daily_flows`, `build_broker_detail`, broker tier/weight/share calculations, and `build_broker_quality_note` to `src/application/services/swing_broker_detail_builder.py`.
- Keep this file as `analyze_swing_broker_display.py` with money formatters and Rich rendering only.

Guardrails:
- Do not change terminal output text without explicit approval.
- Do not change JSON payloads built from these DTOs.
- Do not fetch new data; builders must use already supplied repositories/data exactly as today.

Risks to maintain:
- Swing analysis output and setup review rely on broker-quality note wording.

Edge cases to watch:
- Empty broker summaries.
- Smart-money net selling warning.
- Noise-led accumulation warning.

### 3. Critical: `src/adapters/cli/learn_commands.py` is a multi-command workflow module

Pointer: `src/adapters/cli/learn_commands.py`, 578 LOC. It owns `snapshot`, `track`, `grade`, `tune`, `prompt`, date/path helpers, session checks, infrastructure wiring, and output formatting.

Rationale: The file is a command family cluster. Agents changing one command must scan unrelated opening-session workflows.

Recommendation:
- Keep `learn_commands.py` as router only.
- Extract:
  - `learn_snapshot_commands.py`
  - `learn_track_commands.py`
  - `learn_grade_commands.py`
  - `learn_tune_commands.py`
  - `learn_prompt_commands.py`
  - `learn_command_paths.py` for `_today_dir`, date parsing, and shared storage paths.
- Move repeated Stockbit session construction into an application/adapter wiring helper with an explicit name.

Guardrails:
- Preserve command names under `saham learn`.
- Preserve option names, defaults, and exit codes.
- Do not move CLI parsing into use cases.

Risks to maintain:
- Cron jobs and daily workflow depend on exact command names and sidecar file locations.

Edge cases to watch:
- `--force` behavior.
- Retrospective `--date`.
- Missing Playwright session handling.

### 4. Critical: `src/infrastructure/browser/playwright_stockbit_browser.py` mixes browser session, token extraction, HTTP, and CLI actions

Pointer: `src/infrastructure/browser/playwright_stockbit_browser.py`, 572 LOC. It handles Playwright context creation, token interception, localStorage fallback, direct Exodus HTTP GET, login/session saving, browse, spy, token extraction, and status.

Rationale: The filename says browser utilities, but the file also owns token and authenticated HTTP behavior. Browser lifecycle and token/API concerns change for different reasons.

Recommendation:
- Extract Playwright context helpers to `stockbit_browser_context.py`.
- Extract token interception/extraction to `stockbit_token_extractor.py`.
- Move `_exodus_get` into `stockbit_api_client.py` or `stockbit_exodus_http.py`.
- Move login/browse/spy/status action functions to `stockbit_session_actions.py`.
- Keep `playwright_stockbit_browser.py` as a compatibility facade only if imports require it.

Guardrails:
- Preserve session file/profile behavior.
- Preserve auth error messages.
- Do not reintroduce cookie-file auth.

Risks to maintain:
- Stockbit login, spy, and API token refresh are fragile integration surfaces.

Edge cases to watch:
- No captured request token.
- LocalStorage token fallback.
- 401 session expiry.

### 5. High: `src/application/services/ticker_profile_classifier.py` violates classifier purity with config loading

Pointer: `src/application/services/ticker_profile_classifier.py`, 586 LOC. The file defines request/config DTOs, YAML loading, universe/index membership loading, numeric helpers, exposure scoring, and the classifier.

Rationale: The docstring says the classifier never fetches data, but it reads YAML/config internally. That makes the application service harder to test and couples profile classification to file layout.

Recommendation:
- Extract config loading to `src/infrastructure/config/ticker_profile_config_loader.py`.
- Extract universe/index membership resolution to `src/application/services/ticker_index_membership_resolver.py` with data injected from infrastructure.
- Keep `TickerProfileClassifier` focused on pure classification from `TickerProfileRequest`, `TickerProfileConfig`, and explicit memberships.
- Move `TickerProfileRequest` and `TickerProfileConfig` to `src/application/dto/ticker_profile.py` if reused outside this service.

Guardrails:
- Preserve default config values.
- Preserve `EvidenceStatus.DIAGNOSTIC`.
- Preserve "never raises" fallback behavior.

Risks to maintain:
- Observation fingerprints depend on stable profile labels and exposure scores.

Edge cases to watch:
- Sparse history fallback.
- Unknown market cap.
- Missing universes config.

### 6. High: `src/application/services/swing_tuning_diff_policy.py` has too many policy axes

Pointer: `src/application/services/swing_tuning_diff_policy.py`, 569 LOC. It classifies target paths, suggests values, builds summaries/checklists, interprets rows, prioritizes rows, parses evidence buckets, and counts dimensions.

Rationale: The filename is generic; the file contains several independently changeable policies. This increases tuning-risk because a small value-selection edit requires scanning interpretation and reporting logic.

Recommendation:
- Extract `swing_tuning_target_classification.py`.
- Extract `swing_tuning_value_suggestion_policy.py`.
- Extract `swing_tuning_diff_summary_policy.py`.
- Extract `swing_tuning_diff_interpretation.py`.
- Keep `swing_tuning_diff_policy.py` as a compatibility facade if imports are broad.

Guardrails:
- Do not change proposed values.
- Do not change priority ordering.
- Do not change interpretation strings without updating CLI snapshots/tests.

Risks to maintain:
- Tuning review is safety-critical; accidental proposal widening can bypass human review intent.

Edge cases to watch:
- Weight-grid snapping.
- Custom step paths.
- Evidence bucket parsing.

### 7. High: `src/application/use_case/assess_signal_evidence_use_case.py` still does aggregation, policy, projection, and response assembly

Pointer: `src/application/use_case/assess_signal_evidence_use_case.py`, 562 LOC. `execute()` scores groups, computes legacy regime-conditioned diagnostics, renormalizes, applies flags, resolves decision policy, builds alpha/trigger projection, builds breakdown, and builds rationale.

Rationale: A use case should orchestrate. This file owns several reusable scoring/reporting sub-policies that agents need to reason about independently.

Recommendation:
- Extract group scoring and renormalization to `signal_evidence_group_scorer.py`.
- Extract legacy regime diagnostic conditioning to `signal_legacy_regime_conditioning.py`.
- Extract breakdown/rationale assembly to `signal_evidence_response_builder.py`.
- Keep `AssessSignalEvidenceUseCase.execute()` as orchestration across these collaborators.

Guardrails:
- Preserve canonical regime-neutral score behavior.
- Preserve `legacy_conditioned_score` as diagnostic only.
- Preserve decision policy ordering and alpha/trigger inputs.

Risks to maintain:
- Signal scores, entry quality, and tuning labels are central contracts.

Edge cases to watch:
- Missing setup evidence.
- Missing flow evidence.
- Gate tightening from market context.

### 8. High: `src/adapters/cli/trade_commands.py` is a router plus tuning command implementation cluster

Pointer: `src/adapters/cli/trade_commands.py`, 536 LOC. The top registers commands, but the file also implements tuning status, tuning review, patch validation, patch apply, dirty-git checks, journal migration, and log routing.

Rationale: The router filename suggests command aggregation, but it still owns several full command bodies. Agents changing tuning patch behavior scan unrelated trade log and migration code.

Recommendation:
- Keep `trade_commands.py` as router only.
- Extract:
  - `trade_tuning_status_commands.py`
  - `trade_tuning_patch_commands.py`
  - `trade_log_router_commands.py`
  - `trade_journal_migration_commands.py`
- Keep existing subcommand names by registering extracted functions.

Guardrails:
- Preserve `saham trade ...` command paths.
- Preserve JSON schemas for tuning outputs.
- Preserve dirty-git guard behavior.

Risks to maintain:
- Tuning patch apply is a guarded manual action; regressions are high cost.

Edge cases to watch:
- `--format json`.
- dirty config file detection.
- dry-run versus explicit apply.

### 9. High: `src/adapters/cli/fetch_market_commands.py` still contains status policy and provider precondition logic

Pointer: `src/adapters/cli/fetch_market_commands.py`, 526 LOC. It has Typer parsing plus cache status formatters, row-span status policy, missing Stockbit-session precondition logic, universe resolution, provider wiring, and output coordination.

Rationale: Previous extraction improved fetch internals, but this adapter still decides statuses and validates provider policy. Those are application-level concerns or display helpers.

Recommendation:
- Move `_cached_status`, `_no_new_data_status`, `_broker_update_status`, and `_range_update_status` to `src/application/services/fetch_market_status_policy.py`.
- Move `_find_missing_stockbit_session_error` into `FetchMarketRefreshUseCase` or a named application precondition service.
- Keep `fetch_market_commands.py` focused on options, request construction, dependency wiring, use-case call, and rendering.

Guardrails:
- Preserve fail-fast missing Stockbit session behavior.
- Preserve status strings used by tests and scripts.
- Do not change provider selection semantics.

Risks to maintain:
- Fetch command is daily workflow critical.

Edge cases to watch:
- benchmark ticker aliases.
- explicit non-IDX tickers.
- broker-only and candles-only combinations.

### 10. High: `src/application/use_case/assess_risk_use_case.py` mixes custom rule evaluation, configured gates, trend response DTOs, and infrastructure fallback

Pointer: `src/application/use_case/assess_risk_use_case.py`, 517 LOC. It contains request/response DTOs, custom YAML rule evaluation, standard gate evaluation, indicator snapshot building, trend response type, and a fallback import of `RulesYamlLoader` from infrastructure.

Rationale: Risk assessment has two modes with different dependencies. The infrastructure fallback also weakens the application boundary.

Recommendation:
- Move DTOs to `src/application/dto/assess_risk.py`.
- Extract custom rules path to `assess_risk_custom_rules_evaluator.py`.
- Extract configured gate path to `assess_risk_gate_evaluator.py`.
- Move trend behavior to `assess_risk_trend_use_case.py` if still used.
- Require `RulesLoader` injection from an adapter/factory; do not import `RulesYamlLoader` inside the use case.

Guardrails:
- Preserve custom-rule behavior when `rules_file` is provided.
- Preserve gate ordering: structural before execution.
- Preserve `RiskAssessment` fields and display aliases.

Risks to maintain:
- Risk gates are blocking policy, not bullish scoring.

Edge cases to watch:
- Sentiment extras in custom rules.
- Missing `gate_context`.
- insufficient candle coverage warnings.

### 11. High: `src/infrastructure/config/swing_config_loader.py` is a nested parser cluster

Pointer: `src/infrastructure/config/swing_config_loader.py`, 514 LOC. One loader parses broker quality, four setup families, verdict thresholds, resistance, corporate actions, setup targets, setup phase requirements, RS policy, volume trigger policy, and split-config composition.

Rationale: The file is infrastructure, but it has too many independently changeable config sections. The nested parser functions make diffs hard to review and hard for agents to target.

Recommendation:
- Extract:
  - `swing_broker_quality_config_parser.py`
  - `swing_setup_family_config_parser.py`
  - `swing_setup_phase_config_parser.py`
  - `swing_targets_config_parser.py`
  - `swing_config_composer.py`
- Keep `load_swing_config()` as the public entry point.

Guardrails:
- Preserve fail-soft defaults except the existing invalid setup phase hard failure.
- Preserve split-config precedence.
- Preserve hyphen/underscore setup-family aliases.

Risks to maintain:
- Swing workflow gates and setup phase entry authority depend on exact config parsing.

Edge cases to watch:
- invalid setup phase names.
- missing split files.
- list parsing for allowed phases and broker codes.

### 12. High: `src/application/services/engine_bootstrap/signal_config_resolvers.py` is too broad and crosses infrastructure boundaries

Pointer: `src/application/services/engine_bootstrap/signal_config_resolvers.py`, 497 LOC. It loads config via `APP_CFG`, resolves weights, signal scoring config, decision policy, alpha/trigger config, evidence authority promotion, and archived-config warnings.

Rationale: The filename says config resolving, but it resolves every signal-engine section. It also imports infrastructure config from application service code.

Recommendation:
- Move file-loading wrappers that depend on `APP_CFG` to infrastructure or adapter wiring.
- Split section resolvers:
  - `signal_scoring_config_resolver.py`
  - `signal_decision_policy_config_resolver.py`
  - `signal_alpha_trigger_config_resolver.py`
  - `signal_weight_config_resolver.py`
  - `signal_archived_config_warnings.py`
- Keep pure mapping functions in application; inject raw dicts from infrastructure.

Guardrails:
- Preserve archived-config warnings.
- Preserve evidence authority validation.
- Preserve default values exactly.

Risks to maintain:
- Signal engine construction controls scoring authority and decision constraints.

Edge cases to watch:
- missing config file.
- invalid evidence promotion record.
- raw versus renormalized weight tables.

### 13. Medium: `src/application/rules/schema.py` combines every DSL schema type and validation rule

Pointer: `src/application/rules/schema.py`, 524 LOC. It defines indicator schema, operators, outcomes, signal mapping, condition types, rule, ruleset, validation, and required-indicator collection.

Rationale: The file is conceptually cohesive but too broad for targeted DSL changes. Indicator schema changes are unrelated to rule ordering or condition validation.

Recommendation:
- Split into:
  - `rules/indicator_schema.py`
  - `rules/condition_schema.py`
  - `rules/rule_schema.py`
  - `rules/outcome_schema.py`
- Keep `rules/schema.py` as a compatibility re-export facade.

Guardrails:
- Preserve public imports from `src.application.rules.schema`.
- Preserve dataclass immutability.
- Preserve validation messages unless tests are updated deliberately.

Risks to maintain:
- YAML loader and interpreter import these symbols broadly.

Edge cases to watch:
- backward-compatible `Indicator` alias.
- duplicate rule/indicator name validation.
- required indicator traversal.

### 14. Medium: `src/application/formula/evaluator.py` mixes AST walking, series math, and registry adapter

Pointer: `src/application/formula/evaluator.py`, 490 LOC. It defines `SeriesProvider`, AST evaluator, SMA/EMA-on-series math, binary alignment/broadcasting, and `RegistrySeriesProvider`.

Rationale: Formula behavior is easier to audit when expression traversal is separate from series arithmetic and registry adaptation.

Recommendation:
- Extract series operations to `formula/series_ops.py`.
- Extract indicator-on-series functions to `formula/series_indicators.py`.
- Move `RegistrySeriesProvider` to `formula/registry_series_provider.py`.
- Keep `FormulaEvaluator` focused on AST traversal and error context.

Guardrails:
- Preserve index alignment from the end.
- Preserve scalar broadcasting.
- Preserve division-by-zero behavior.
- Preserve SMA-seeded EMA behavior.

Risks to maintain:
- Strategy formulas and rule indicators depend on exact output length.

Edge cases to watch:
- empty series.
- scalar versus series operations.
- nested formulas like `SMA(RSI(14), 10)`.

### 15. Medium: Stockbit PIT provider cache logic is duplicated across provider files

Pointers:
- `src/infrastructure/browser/stockbit_insider.py`, 502 LOC.
- `src/infrastructure/browser/stockbit_earnings.py`, 426 LOC.
- `src/infrastructure/browser/stockbit_shareholding.py`, 325 LOC.
- `src/infrastructure/browser/stockbit_forward_estimates.py`, 272 LOC.
- `src/infrastructure/browser/stockbit_company_profile.py`, 239 LOC.
- `src/infrastructure/browser/stockbit_seasonality.py`, 315 LOC.
- `src/infrastructure/browser/stockbit_fundamentals.py`, 222 LOC.

Rationale: These files repeat schema creation, freshness checks, PIT cache reads, row writes, API fetch, and cache fallback patterns. The base class only centralizes connection/schema entry, not PIT row lifecycle.

Recommendation:
- Introduce `src/infrastructure/browser/stockbit_pit_cache.py` with small primitives:
  - table schema migration runner wrapper.
  - latest-as-of query builder.
  - fetched-date freshness check.
  - safe read/write exception handling.
- Keep endpoint-specific parsing and value-object mapping in each provider.

Guardrails:
- Do not change table names or primary keys.
- Do not change TTLs.
- Do not change point-in-time `as_of_date` semantics.

Risks to maintain:
- Historical replay correctness depends on latest row at or before `as_of_date`.

Edge cases to watch:
- old schema rebuilds.
- multiple rows per fetched date.
- live cache miss versus historical cache-only replay.

### 16. Medium: `src/infrastructure/browser/stockbit_broker_provider.py` still owns endpoint period mapping and request construction

Pointer: `src/infrastructure/browser/stockbit_broker_provider.py`, 475 LOC. The provider owns broker-summary period mapping, foreign-top period mapping, request URL construction, historical summary fallback, pagination, and provider orchestration.

Rationale: The provider is below the hard threshold, but period mapping and URL construction are pure, testable responsibilities that are easy to accidentally duplicate.

Recommendation:
- Extract period mapping to `stockbit_broker_periods.py`.
- Extract request URL builders to `stockbit_broker_requests.py`.
- Keep `StockbitBrokerProvider` focused on calling `api_client`, passing responses to parsers, and returning domain entities.

Guardrails:
- Preserve confirmed Stockbit enum strings.
- Preserve fallback to historical summary totals.
- Preserve warning behavior when endpoints return no data.

Risks to maintain:
- Stockbit endpoint enum drift is likely; keeping mappings isolated improves repair speed.

Edge cases to watch:
- 1D/3D/7D/1M/3M/1Y period cutoffs.
- `limit` and pagination.
- synthetic total value fallback.

### 17. Medium: `src/infrastructure/browser/stockbit_preopen_parsers.py` contains two parser strategies in one file

Pointer: `src/infrastructure/browser/stockbit_preopen_parsers.py`, 416 LOC. It contains confirmed-shape pre-open parsing plus generic recursive JSON discovery helpers for movers, best bid, order book, price, and volume.

Rationale: Confirmed API-shape parsers and exploratory fallback scanners have different stability and review expectations.

Recommendation:
- Extract recursive fallback scanners to `stockbit_preopen_json_search.py`.
- Keep confirmed response parsers in `stockbit_preopen_parsers.py`.
- Name fallback functions as fallback/search behavior, not canonical parser behavior.

Guardrails:
- Preserve parsing results for current live payloads.
- Preserve fallback behavior for unknown response shapes.
- Do not make fallback scanner authoritative over confirmed parser fields.

Risks to maintain:
- Pre-open data is session-time sensitive; parser regressions can break morning workflow.

Edge cases to watch:
- nested list depth.
- missing IEV/IEP.
- lots versus shares conversion.

### 18. Medium: `src/infrastructure/browser/stockbit_corporate_action_calendar.py` repeats event-specific parser boilerplate

Pointer: `src/infrastructure/browser/stockbit_corporate_action_calendar.py`, 401 LOC. It defines separate parse methods for dividend, stock split, reverse split, rights issue, bonus, tender offer, RUPS, pubex, and IPO, with shared date/note/id mechanics.

Rationale: The file is close to the preferred limit and event parser repetition makes new corporate action types expensive to add safely.

Recommendation:
- Extract event-type mapping and shared parse helpers to `stockbit_corporate_action_event_parsers.py`.
- Represent event-specific field extraction with small strategy functions or a table-driven parser.
- Keep provider class responsible for endpoint routing and API calls only.

Guardrails:
- Preserve fallback ID generation.
- Preserve event date semantics.
- Preserve unsupported-event behavior.

Risks to maintain:
- Corporate-action warnings affect risk display and swing workflow context.

Edge cases to watch:
- missing dates.
- multiple date fields per event.
- RUPS meeting date stored as event date.

### 19. Medium: Application services directly parse YAML in several places

Pointers:
- `src/application/services/ticker_profile_classifier.py`
- `src/application/services/company_quality_context_evidence_builder.py`
- `src/application/services/sector_context_evidence_builder.py`
- `src/application/services/group_mapping.py`
- `src/application/services/swing_tuning_config_paths.py`
- `src/application/services/swing_tuning_patch_apply.py`
- `src/application/services/institutional_flow_config.py`

Rationale: YAML parsing is infrastructure/config concern. Application services should consume typed config or explicit dictionaries. Direct YAML reads make tests filesystem-dependent and duplicate `_read_yaml` patterns.

Recommendation:
- Move YAML file reads into `src/infrastructure/config/*_loader.py`.
- Keep application services accepting typed config dataclasses or raw mappings passed in.
- Keep pure path parsing or patch application logic separate from file IO.

Guardrails:
- Preserve default config behavior.
- Preserve local-first file locations through adapters/factories.
- Do not introduce mandatory remote or global config dependencies.

Risks to maintain:
- Config loading failures currently often degrade to defaults; changing that can alter live workflow.

Edge cases to watch:
- missing files.
- malformed YAML.
- partial config with defaults.

### 20. Medium: Compatibility facades are accumulating and need explicit expiry discipline

Pointers:
- `src/application/services/bootstrap.py`
- `src/infrastructure/config/yaml_loader.py`
- `src/infrastructure/config/swing_config.py`
- `src/infrastructure/config/user_config.py`
- `src/infrastructure/browser/playwright_stockbit_provider.py`
- `src/infrastructure/ai/strategy_translator.py`
- `src/application/services/setup_phase_detector.py`
- `src/application/use_case/assess_signal_use_case.py`

Rationale: Facades are useful during extraction, but many now live indefinitely. Future agents cannot tell which import path is canonical and may add implementation back into the facade.

Recommendation:
- Add a `COMPATIBILITY_FACADE.md` or inline module comment standard with:
  - canonical replacement import.
  - allowed contents: re-export/delegation only.
  - expiry condition or "permanent public API" label.
- Audit each facade so it contains no implementation logic beyond re-export/delegation.

Guardrails:
- Do not remove compatibility imports without checking all call sites and tests.
- Do not move implementation back into facades.

Risks to maintain:
- Broad import rewrites can break monkeypatch paths and external scripts.

Edge cases to watch:
- private names re-exported for tests.
- Typer command registration modules.
- external user scripts importing old paths.

## Code Convention For Future Agents

Add or keep these rules in `AI_AGENT_CHECKLIST.md` or an ADR:

1. Production Python files above 400 LOC require a single dominant responsibility stated by filename.
2. Production Python files above 550 LOC require extraction before adding new behavior, even if below the 700 LOC hard threshold.
3. Domain value objects must not become persisted-schema warehouses. Split large fingerprints by schema section and centralize serialization compatibility.
4. Display modules render facts only. Builders that query repositories, derive quality labels, or apply thresholds belong in application services.
5. CLI command modules may parse options, build request DTOs, wire dependencies, call use cases, render output, and map errors. They must not own status policy, provider preconditions, scoring policy, or persistence workflow.
6. Config file IO belongs in infrastructure/config loaders. Application services consume typed configs, raw mappings, or explicit constructor arguments.
7. Browser/provider files split by capability: browser lifecycle, token extraction, HTTP client, endpoint request builder, parser, cache store, and provider orchestration.
8. PIT cache providers must share cache primitives instead of copying schema/read/write/freshness loops across endpoint providers.
9. Compatibility facades must be re-export/delegation only and must name the canonical import path.
10. Parser files must distinguish confirmed payload parsers from exploratory recursive fallback scanners.
11. Tuning and signal policy files must split value selection, target classification, interpretation, and report assembly once they exceed 400 LOC.
12. Use cases orchestrate. Extract group scoring, rationale/breakdown builders, serializers, calculators, and policy helpers when they become independently reviewable.

## Suggested Refactor Order

1. Fix `signal_forward_label.py` first because persisted fingerprint scan burden is highest and affects many workflows.
2. Move broker-detail builders out of `analyze_swing_broker_display.py` so display modules become trustworthy again.
3. Split `learn_commands.py` and `trade_commands.py` routers to reduce adapter scan cost.
4. Split `playwright_stockbit_browser.py` by browser/token/session action.
5. Extract `swing_config_loader.py` section parsers.
6. Split `assess_signal_evidence_use_case.py` and `assess_risk_use_case.py` into orchestration plus collaborators.
7. Introduce shared Stockbit PIT cache primitives, then simplify the largest endpoint providers.
8. Clean up compatibility facades and application YAML-loading boundaries.

## Acceptance Gate For Refactor PRs

- No production behavior changes unless explicitly requested.
- No CLI command names, option names, JSON keys, CSV keys, or persisted keys change without migration notes.
- Existing tests for moved responsibilities pass at their new boundaries.
- New filenames must answer "what responsibility lives here?"
- Facades may remain only as compatibility shims.
- No adapter gains workflow or policy.
- No application service gains infrastructure config/file IO.
- AI agents can locate the edited responsibility from filename alone.
