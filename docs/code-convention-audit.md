# Code Convention Audit: File Size, Naming Context, and AI-Agent Readability

Date: 2026-07-10
Last status update: 2026-07-11

Scope: source, tests, config, docs, scripts, plugins, and strategies. This document started as an audit report and is now also the tracking record for extraction status.

## Audit Standard

This repository already commits to deterministic-first, hexagonal architecture, thin adapters, and application-owned workflow/policy. This audit adds an AI-agent readability standard:

- Target Python module size: <= 400 LOC.
- Warning threshold: 401-700 LOC.
- Refactor threshold: > 700 LOC.
- Critical threshold: > 1000 LOC.
- Single file should answer one primary question from its filename.
- A file name must expose ownership before opening it: command tree, use case, engine, repository, provider, parser, renderer, validator, or DTO.
- Adapters may parse, wire, call use cases, format, and map errors only. Workflow, scoring, fetch policy, cache policy, persistence decisions, and business status calculation belong outside adapters.

## Executive Findings

The codebase has good high-level architecture documents, but several implementation files became too large for efficient AI-agent review. The biggest problems were not merely LOC. They were mixed responsibility modules where the filename hid multiple workflows, serialization contracts, display policy, and persistence/audit mechanics.

Most high-risk extraction targets have now been addressed. Remaining risk is concentrated in partially extracted use cases and follow-up parser/test refinements.

Status legend:
- Done: recommendation implemented and current file shape is acceptable.
- Partial: major recommendation implemented, but a follow-up remains useful.
- Retired: audit item removed manually because it is no longer needed.

| # | Finding | Status | Current note |
|---|---|---|---|
| 1 | `accumulation_screen_use_case.py` workflow warehouse | Partial | DTOs/fingerprints/evidence/risk/technical services extracted; use case still ~925 LOC and should not absorb new behavior. |
| 2 | `analyze_swing_display.py` too large | Done | Facade reduced to ~86 LOC; display responsibilities split. |
| 3 | `playwright_stockbit_provider.py` misleading | Done | Browser/provider/parser responsibilities split; compatibility facade remains ~270 LOC. |
| 4 | `swing_analysis_workflow_use_case.py` mixed DTOs/helpers | Partial | DTO/serialization/helpers extracted; use case still ~879 LOC and should be reduced further only with focused characterization. |
| 5 | `fetch_market_commands.py` not thin enough | Done | Command file reduced below adapter threshold at ~526 LOC. |
| 6 | `swing_tuning_patch_validator.py` misleading | Done | Validator facade reduced to ~46 LOC; validate/dry-run/apply/verify/report helpers split. |
| 7 | `screen_accum_display.py` display cluster | Done | Facade reduced to ~29 LOC; display split by mode/panel. |
| 8 | `institutional_accumulation_evidence_builder.py` dense metric engine | Done | Orchestrator reduced to ~298 LOC; metric tracks/config/counterparty math split. |
| 9 | `swing_backtest_use_case.py` mixed backtest engine | Done | Use case reduced to ~322 LOC; DTO/simulator/observation/position helpers split. |
| 10 | `bootstrap.py` engine factory cluster | Done | Compatibility facade reduced to ~59 LOC; `engine_bootstrap/` package owns factories/resolvers. |
| 11 | `intraday_backtest_use_case.py` too broad | Done | Use case reduced to ~120 LOC; simulator/report/execution/candidate services split. |
| 12 | CLI command modules exceed readability limits | Done | Large command groups split by command family. |
| 13 | `yaml_loader.py` name too generic | Partial | Generic file is now a compatibility facade; `rules_yaml_loader.py` owns parser. Parser internals are still broad and can be split later. |
| 14 | `strategy_translator.py` mixes providers/templates | Done | Facade reduced to ~201 LOC; provider clients, mock templates, output canonicalization split. |
| 15 | Documentation naming inconsistency | Retired | Removed manually; no longer tracked in this audit. |
| 17 | Oversized test files | Done | Target tests split by behavior; focused split suite has 211 tests. |
| 18 | Generated/local-state scan noise | Retired | Removed manually; no longer tracked in this audit. |

## Findings

### 1. Critical: `src/application/use_case/accumulation_screen_use_case.py` is a workflow warehouse

Status: Partial. Major extractions have been completed into DTO, fingerprint, evidence, technical feature, and risk funnel modules. The use case is much smaller but remains above the preferred threshold, so future changes should not add new responsibilities here.

Pointer: `src/application/use_case/accumulation_screen_use_case.py`, 2210 LOC. Mixed sections include request/response DTOs, candidate object, sorting, observation payloads, fingerprint serializers, evidence builders, risk funnel, ticker evaluation, indicator calculations, resistance calculation, percent plan, and multi-window classification.

Rationale: The filename says one use case, but the module contains multiple reusable responsibilities. AI agents must scan 2000+ lines to safely change one candidate field, one fingerprint, or one evidence builder. That increases accidental schema drift and look-ahead risk.

Recommendation:
- Keep `AccumulationScreenUseCase` as the orchestration entry point only.
- Extract request/response/candidate DTOs to `src/application/dto/accumulation_screen.py`.
- Extract observation/fingerprint builders to `src/application/services/accumulation_observation_fingerprint.py`.
- Extract candidate evidence assembly to `src/application/services/accumulation_candidate_evidence_builder.py`.
- Extract technical derived features to `src/application/services/accumulation_technical_features.py`.
- Extract risk funnel composition to `src/application/services/accumulation_risk_funnel.py` or a focused application service.

Guardrails:
- Do not move workflow policy into CLI.
- Preserve existing JSON keys and persisted observation fingerprints.
- Keep point-in-time enrichment and no-lookahead constraints intact.
- Add characterization tests before extraction.

Edge cases to watch:
- `candidate_observation_payload` schema stability.
- Historical replay fields and `as_of_date`.
- Existing watchlist/journal consumers expecting current `to_dict()` shape.

### 2. Critical: `src/adapters/cli/analyze_swing_display.py` is too large and partly policy-shaped

Status: Done. The file is now a small display facade and responsibility-specific display modules own overview, evidence, institutional, compare, and style concerns.

Pointer: `src/adapters/cli/analyze_swing_display.py`, 1911 LOC. It contains style helpers, labels, plan text, top findings, setup gate summaries, signal/risk/market/data panels, institutional accumulation panels, full text output, and swing-compare display.

Rationale: Display files can be large, but this one hides many independent rendering surfaces and label decisions. It is difficult for AI agents to update one panel without accidentally changing verdict wording elsewhere.

Recommendation:
- Split into:
  - `analyze_swing_style.py` for style/format primitives.
  - `analyze_swing_overview_display.py` for verdict-first overview.
  - `analyze_swing_evidence_display.py` for setup/signal/risk/market/evidence panels.
  - `analyze_swing_institutional_display.py` for institutional accumulation details.
  - `analyze_swing_compare_display.py` for compare output.
- Move any threshold-based label that is not pure presentation to application/display DTOs or config-backed application services.

Guardrails:
- Display may not decide business action.
- `TradeSetup.action` remains authoritative.
- Do not introduce new score thresholds in display defaults without config ownership.

Edge cases to watch:
- Rich formatting snapshots.
- JSON output must remain owned by response DTOs/use cases, not display helpers.
- ADR-037 market-context wording must remain accurate.

### 3. Critical: `src/infrastructure/browser/playwright_stockbit_provider.py` filename is misleading

Status: Done. Stockbit browser/provider/parser responsibilities have been split and the old file is now a small compatibility surface.

Pointer: `src/infrastructure/browser/playwright_stockbit_provider.py`, 1520 LOC. It contains `PlaywrightStockbitProvider`, `StockbitBrokerProvider`, broker summary fetch, foreign top stocks, daily flow fetch, IEV parsing, order book parsing, market detector parsing, and many raw JSON extraction helpers.

Rationale: The filename says Playwright provider, but much of the file is authenticated Stockbit HTTP provider/parsing logic. This violates filename/context clarity and makes infrastructure changes risky.

Recommendation:
- Rename/split by capability:
  - `stockbit_preopen_provider.py` for IEV/pre-open/orderbook provider behavior.
  - `stockbit_broker_provider.py` for broker summary/history/daily flow behavior.
  - `stockbit_broker_parsers.py` for broker/foreign-flow JSON parsing.
  - `stockbit_preopen_parsers.py` for IEV/orderbook JSON parsing.
- Keep Playwright browser lifecycle in `playwright_stockbit_browser.py`.

Guardrails:
- Infrastructure remains behind existing provider ports.
- Do not leak Stockbit payload shapes into application/domain.
- Keep offline/cache fallback behavior.

Edge cases to watch:
- Token refresh behavior from ADR-036.
- API pattern loading.
- Broken parser imports causing silent empty provider results.

### 4. Critical: `src/application/use_case/swing_analysis_workflow_use_case.py` mixes DTOs, serialization, helpers, and orchestration

Status: Partial. DTOs and serialization were extracted, and workflow helpers were reduced. The use case remains above the preferred threshold and should be kept orchestration-only.

Pointer: `src/application/use_case/swing_analysis_workflow_use_case.py`, 1342 LOC. It defines request/response DTOs, nested verdict/evidence/diagnostic DTOs, `to_dict()` serialization, return helpers, risk preview mapping, candidate mapping, orchestration, and ATR calculation.

Rationale: A workflow use case should be readable as a workflow. Current file forces agents to parse serialization and helper details before they can reason about the canonical swing decision path.

Recommendation:
- Move DTOs to `src/application/dto/swing_analysis.py`.
- Move response serialization mappers to `src/application/services/swing_analysis_serialization.py` or DTO methods in the DTO file.
- Move candidate/risk/signal preview mapping to focused mappers.
- Keep `SwingAnalysisWorkflowUseCase.execute()` as the visible orchestration path.

Guardrails:
- Preserve `analyze swing --format json` canonical grouping: `verdict`, `evidence`, `diagnostics`.
- Do not let optional evidence modules overwrite `TradeSetup.action`.
- Keep refresh/freshness policy in application services, not adapter.

Edge cases to watch:
- Market context canonical signal behavior from ADR-037.
- `market_context_risk_preview` vs canonical risk.
- `--full`, `--explain`, and setup-specific output parity.

### 5. Critical: `src/adapters/cli/fetch_market_commands.py` is not thin enough

Status: Done. Fetch command behavior was split into focused adapter/application-support modules and the command file is below the readability threshold.

Pointer: `src/adapters/cli/fetch_market_commands.py`, 1168 LOC. It includes status formatting, cache status calculation, broker provider construction, candle fetch, broker fetch, summary rendering, enrichment fetch, metadata fetch, global context ticker fetch, Typer command handling, callback progress, and enrichment PIT coverage rendering.

Rationale: This adapter contains workflow and fetch policy that should be application-owned. It is hard for agents to distinguish CLI formatting from business decisions around cache/fetch/no-new-data statuses.

Recommendation:
- Extract display helpers to `fetch_market_display.py`.
- Extract provider wiring to an adapter factory or infrastructure factory.
- Move global context ticker refresh into an application use case, e.g. `refresh_market_context_inputs_use_case.py`.
- Keep `fetch_market_commands.py` to Typer options, request construction, dependency wiring, use-case call, and rendering.

Guardrails:
- Adapter must not own cache freshness policy.
- Preserve local-first behavior and explicit `--refresh`.
- Keep global tickers from accidentally receiving `.JK` suffix.

Edge cases to watch:
- Progress callback behavior.
- Broker-only/candles-only combinations.
- Enrichment PIT history and coverage labels.

### 6. Critical: `src/application/services/swing_tuning_patch_validator.py` has a misleading name

Status: Done. Validation, dry-run, apply, verify, reports, path handling, and readiness behavior have been split; the original validator file is now a compatibility facade.

Pointer: `src/application/services/swing_tuning_patch_validator.py`, 1093 LOC. It contains patch validation, dry-run planning, apply logic, verify logic, report DTOs, YAML mutation helpers, attribution readiness validation, and document path setters.

Rationale: The filename says validator, but the module can plan, apply, and verify patches. This is dangerous because agents may import it expecting read-only validation while it also contains write-capable behavior.

Recommendation:
- Split into:
  - `swing_tuning_patch_validation.py`
  - `swing_tuning_patch_dry_run.py`
  - `swing_tuning_patch_apply.py`
  - `swing_tuning_patch_verify.py`
  - `swing_tuning_patch_reports.py`
  - `yaml_document_path.py`

Guardrails:
- Keep apply guarded by validation and clean-target checks.
- Never apply AI-generated changes without explicit human approval path.
- Preserve JSONL audit log behavior.

Edge cases to watch:
- Boolean vs numeric proposed values.
- Wildcard path rejection.
- YAML comment loss warning.

### 7. Critical: `src/adapters/cli/screen_accum_display.py` should be split by table/panel responsibility

Status: Done. Screen accumulation display was split by single result, multi-window, guide, enrichment, and facade responsibilities.

Pointer: `src/adapters/cli/screen_accum_display.py`, 1083 LOC. It contains score formatting, pattern classification, notation rendering, risk detail lines, data freshness display, scoring definition panel, evidence rows, primary results, multi-window table, and column guide.

Rationale: It is a display module, but it mixes multiple display modes and includes `classify_pattern`, which looks like business classification from the filename alone.

Recommendation:
- Split into:
  - `screen_accum_table_display.py`
  - `screen_accum_evidence_display.py`
  - `screen_accum_multi_display.py`
  - `screen_accum_guide_display.py`
  - `screen_accum_formatters.py`
- Rename display-only classification helpers to include `display_` or move actual classification to application.

Guardrails:
- Display cannot change candidate order, score, action, or gate results.
- Any user-facing threshold text must come from config/use-case response, not duplicated literals.

Edge cases to watch:
- `--guide` output.
- Multi-window sorting labels.
- Data freshness labels.

### 8. Critical: `src/application/services/institutional_accumulation_evidence_builder.py` is a dense metric engine

Status: Done. Institutional flow config, foreign/domestic tracks, counterparty/broker metrics, and math helpers have been extracted; the builder is now an orchestrator.

Pointer: `src/application/services/institutional_accumulation_evidence_builder.py`, 1017 LOC. It handles config, validation, foreign track scoring, domestic track scoring, counterparty metrics, VWAP distance, HHI, CNFB divergence, broker filtering, and unavailable evidence handling.

Rationale: The filename is contextual, but the file exceeds the cognitive limit. All institutional-flow metric details are coupled to one builder, so agents must scan the whole file for a single metric fix.

Recommendation:
- Keep `InstitutionalAccumulationEvidenceBuilder` as the public orchestrator.
- Extract:
  - `institutional_flow_foreign_track.py`
  - `institutional_flow_domestic_track.py`
  - `institutional_flow_counterparty_metrics.py`
  - `institutional_flow_vwap_metrics.py`
  - `institutional_flow_config.py`

Guardrails:
- Preserve deterministic score formulas.
- Do not promote diagnostic evidence authority without ADR/config change.
- Keep missing evidence as coverage issue, not conviction inflation.

Edge cases to watch:
- Asymmetric bullish/bearish windows.
- CR4/CR8 concentration.
- Broker code classification.

### 9. Critical: `src/application/use_case/swing_backtest_use_case.py` mixes simulation engine, DTOs, stats, and candidate observation building

Status: Done. DTOs, simulator, exit/position handling, observation building, and trade setup attribution have been extracted.

Pointer: `src/application/use_case/swing_backtest_use_case.py`, 1010 LOC.

Rationale: Backtest behavior is high-risk because small changes can alter historical results. The current file mixes request/response DTOs, open position state, signal generation, setup evaluation, risk composition, exit simulation, equity curve, regime stats, and utility math.

Recommendation:
- Move DTOs to `src/application/dto/swing_backtest.py`.
- Extract simulation state/position handling to `src/application/services/swing_backtest_simulator.py`.
- Extract candidate observation building to `src/application/services/swing_backtest_observation_builder.py`.
- Extract stats to `src/application/services/backtest_statistics.py`.

Guardrails:
- Preserve deterministic same-day stop/target priority.
- Preserve transaction cost assumptions.
- Do not fetch network data during tests/backtests.

Edge cases to watch:
- Regime filtering.
- Forward data eligibility.
- Position concurrency and mark-to-market.

### 10. Critical: `src/application/services/bootstrap.py` is an engine factory cluster

Status: Done. `bootstrap.py` is now a compatibility facade; `src/application/services/engine_bootstrap/` owns factories, config resolvers, and evidence authority validation.

Pointer: `src/application/services/bootstrap.py`, 1010 LOC. It loads engine config, resolves signal weights/config, validates evidence authority promotion, resolves decision policy, risk gates, indicators, technical gate config, indicator registry, risk engine, signal engine, and formula loading.

Rationale: `bootstrap.py` is too generic for a file that encodes several high-authority factory contracts. Agents changing one engine factory risk touching another engine by accident.

Recommendation:
- Split into:
  - `indicator_registry_factory.py`
  - `risk_engine_factory.py`
  - `signal_engine_factory.py`
  - `engine_config_resolvers.py`
  - `evidence_authority_validation.py`
- Keep stable re-export functions from `bootstrap.py` temporarily for compatibility.

Guardrails:
- Factories may load config and wire dependencies.
- Factories must not contain workflow policy.
- Do not change config path defaults incidentally.

Edge cases to watch:
- Evidence authority promotion validation.
- Weight normalization.
- Formula registry loading.

### 11. High: `src/application/use_case/intraday_backtest_use_case.py` is too broad

Status: Done. Intraday DTOs, candidate building, simulation, execution, and report construction have been extracted; the use case is now an orchestration entry point.

Pointer: `src/application/use_case/intraday_backtest_use_case.py`, 952 LOC.

Rationale: It mixes candidate construction, broker assessment, entry range computation, sizing, PnL, drawdown, bucket breakdowns, replay dates, and response construction.

Recommendation:
- Extract intraday simulation math to `intraday_backtest_simulator.py`.
- Extract report/statistics helpers to shared `backtest_statistics.py` where reusable.
- Keep the use case as request validation plus orchestration.

Guardrails:
- Keep daily-OHLC proxy assumptions explicit.
- Preserve stop-first behavior when stop and target both hit.

Edge cases to watch:
- Saved IEV/NCP snapshot fallback.
- Include-wait behavior.

### 12. High: CLI command modules exceed adapter readability limits

Status: Done. Command modules were split by sub-command family while preserving router registration and command compatibility.

Pointers:
- `src/adapters/cli/trade_swing_commands.py`, 917 LOC.
- `src/adapters/cli/trade_intraday_commands.py`, 869 LOC.
- `src/adapters/cli/strategy_commands.py`, 819 LOC.
- `src/adapters/cli/analyze_swing_commands.py`, 739 LOC.
- `src/adapters/cli/analyze_signal_commands.py`, 704 LOC.

Rationale: ADR-020 gives a naming convention, but large command files still slow AI-agent scanning. These modules often contain payload builders, export logic, sidecar writes, error hints, and command handlers together.

Recommendation:
- Split when a command group exceeds 700 LOC by sub-command family.
- Use names that preserve command tree context:
  - `trade_swing_backtest_commands.py`
  - `trade_swing_tuning_commands.py`
  - `trade_swing_size_commands.py`
  - `trade_intraday_confirm_commands.py`
  - `trade_intraday_backtest_commands.py`
  - `strategy_lifecycle_commands.py`
  - `strategy_backtest_commands.py`
  - `strategy_ai_create_commands.py`

Guardrails:
- Keep Typer registration explicit in group router files.
- Do not move business logic into newly split adapters.
- Payload builders that encode domain/application contract should move out of adapters.

Edge cases to watch:
- Backward-compatible command registration.
- Tests patching command module symbols.

### 13. High: `src/infrastructure/config/yaml_loader.py` name is too generic

Status: Partial. `yaml_loader.py` is now a compatibility facade and `rules_yaml_loader.py` is the contextual implementation. Condition/indicator parser internals remain a possible future split.

Pointer: `src/infrastructure/config/yaml_loader.py`, 761 LOC. It parses the custom rules DSL, indicators, signal mappings, conditions, compound conditions, and rule objects.

Rationale: The filename suggests a generic YAML loader, but the file owns rules DSL parsing. This confuses agents looking for general YAML config loading and creates a naming collision with other config loaders.

Recommendation:
- Rename or wrap as `rules_yaml_loader.py`.
- Extract condition parsing to `rules_condition_parser.py`.
- Extract indicator definition parsing to `rules_indicator_parser.py`.

Guardrails:
- Keep the `RulesLoader` port implementation stable.
- Provide compatibility import during transition.

Edge cases to watch:
- Strategy loading imports.
- Formula indicator validation.
- Error message compatibility.

### 14. High: `src/infrastructure/ai/strategy_translator.py` mixes provider clients and mock templates

Status: Done. `StrategyTranslatorAdapter` remains the facade; provider clients, mock templates, and YAML canonicalization were extracted.

Pointer: `src/infrastructure/ai/strategy_translator.py`, 746 LOC.

Rationale: It contains provider-specific LLM calls for Claude/OpenAI/Gemini/Ollama/mock plus canonicalization and large mock YAML templates. Filename is contextual but responsibility is too broad.

Recommendation:
- Keep `StrategyTranslatorAdapter` as facade.
- Extract provider callers to `strategy_translator_clients.py` or per-provider modules.
- Extract mock strategy templates to `strategy_translator_mock_templates.py`.
- Keep prompt construction separate from transport.

Guardrails:
- AI remains optional and non-authoritative.
- Generated YAML must still pass deterministic validation.

Edge cases to watch:
- Provider auth error messages.
- Mock tests expecting exact YAML.

### 17. Medium: Test files are too large for targeted review

Status: Done. The target tests were split by behavior, with contextual helper modules and no placeholder tests.

Pointers:
- `tests/application/use_case/test_accumulation_screen.py`, 2395 LOC.
- `tests/adapters/cli/test_swing_commands.py`, 1894 LOC.
- `tests/application/use_case/test_assess_signal_evidence_use_case.py`, 934 LOC.
- `tests/application/services/test_swing_tuning_guardrails.py`, 887 LOC.

Rationale: Oversized tests slow AI-agent validation. A failing test name should point to the responsibility being protected; these large files force broad scanning.

Recommendation:
- Split tests by behavior:
  - `test_accumulation_screen_observations.py`
  - `test_accumulation_screen_risk_funnel.py`
  - `test_accumulation_screen_sector_breadth.py`
  - `test_swing_commands_json.py`
  - `test_swing_commands_market_context.py`
  - `test_signal_evidence_alpha_trigger.py`
  - `test_signal_evidence_coverage.py`

Guardrails:
- Do not weaken characterization coverage during extraction.
- Keep test fixtures shared through local helper modules only when it reduces duplication.

Edge cases to watch:
- Test order dependencies.
- Monkeypatch paths after module splits.

## Future Code Convention for AI-Agent Optimization

Status: Moved to `AI_AGENT_CHECKLIST.md`.

The authoritative convention now lives under `AI_AGENT_CHECKLIST.md` section
`12. Code Convention`. Keep this audit focused on findings and extraction
status; update the checklist when changing future-agent rules.

## Recommended Refactor Order

1. Done: Extract DTOs/serialization from `accumulation_screen_use_case.py` and `swing_analysis_workflow_use_case.py`.
2. Done: Split pure parser/provider responsibilities from `playwright_stockbit_provider.py`.
3. Done: Split display modules: `analyze_swing_display.py` and `screen_accum_display.py`.
4. Done: Split `swing_tuning_patch_validator.py` by validate/dry-run/apply/verify.
5. Done: Thin `fetch_market_commands.py` by moving workflow/fetch policy into application services.
6. Done: Split `bootstrap.py` into explicit factory/config modules.
7. Done: Split oversized backtest use cases and target oversized tests.

Remaining cleanup candidates:
- Keep reducing `accumulation_screen_use_case.py` only when a concrete behavior change needs it; do not perform broad opportunistic churn.
- Keep reducing `swing_analysis_workflow_use_case.py` only around a focused workflow/helper boundary.
- Split `rules_yaml_loader.py` parser internals later if rules DSL work resumes.
- Split `test_swing_commands_tuning.py` if it grows beyond the current near-limit size.

## Definition of Done for Future Extraction PRs

- Behavior is unchanged unless the task explicitly says otherwise.
- Existing CLI commands still register under the same names.
- JSON/CSV/persisted contracts are unchanged or migrated explicitly.
- Tests cover moved responsibilities at their new boundaries.
- No adapter gains workflow/policy during extraction.
- AI can locate the edited responsibility from the filename alone.
