# Code Convention Audit: File Size, Naming Context, and AI-Agent Readability

Date: 2026-07-10

Scope: source, tests, config, docs, scripts, plugins, and strategies. This is an audit report only. No production code was changed.

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

The codebase has good high-level architecture documents, but several implementation files are now too large for efficient AI-agent review. The biggest problems are not merely LOC. They are mixed responsibility modules where the filename hides multiple workflows, serialization contracts, display policy, and persistence/audit mechanics.

Highest-risk extraction targets:

1. `src/application/use_case/accumulation_screen_use_case.py` - 2210 LOC.
2. `src/adapters/cli/analyze_swing_display.py` - 1911 LOC.
3. `src/infrastructure/browser/playwright_stockbit_provider.py` - 1520 LOC.
4. `src/application/use_case/swing_analysis_workflow_use_case.py` - 1342 LOC.
5. `src/adapters/cli/fetch_market_commands.py` - 1168 LOC.
6. `src/application/services/swing_tuning_patch_validator.py` - 1093 LOC.
7. `src/adapters/cli/screen_accum_display.py` - 1083 LOC.
8. `src/application/services/institutional_accumulation_evidence_builder.py` - 1017 LOC.
9. `src/application/use_case/swing_backtest_use_case.py` - 1010 LOC.
10. `src/application/services/bootstrap.py` - 1010 LOC.

## Findings

### 1. Critical: `src/application/use_case/accumulation_screen_use_case.py` is a workflow warehouse

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

### 15. Medium: Documentation naming is inconsistent and not responsibility-first

Pointers:
- `docs/codex_recomendation_190626.md` has a typo: `recomendation`.
- Agent/vendor-prefixed files such as `docs/claude_rearchitecture_recommendation_240626.md`, `docs/deepseek_preopen_recommendation_170626.md`, `docs/gemini_preopen_recommendation170626.md`, and `docs/agy_*` are source-oriented, not topic/responsibility-oriented.
- `docs/signal_refactor.md` is 2826 LOC and `docs/signal_refactor_tracker.md` is 915 LOC.

Rationale: AI agents search by feature/responsibility. Vendor/date names hide the domain topic and bury current guidance among historical recommendations.

Recommendation:
- Move historical agent recommendation documents under `docs/archive/<agent>/<yyyy-mm-dd>-<topic>.md`.
- Keep active docs responsibility-first: `signal-engine-refactor.md`, `pre-open-tuning.md`, `stockbit-data-quality.md`.
- Split long active docs into index + phase/topic files.

Guardrails:
- Do not rewrite historical content casually.
- Add redirect/index links if docs are referenced from README or ADRs.

Edge cases to watch:
- Links from ADRs and trackers.
- Existing task references to old filenames.



### 17. Medium: Test files are too large for targeted review

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

### 18. Medium: Generated/local-state files pollute scan results

Pointers:
- `.DS_Store` appears in multiple directories.
- `__pycache__` files are present under `src/` and `tests/`.
- Root/local data files include `saham.db`, `stockbit_session.json`, `.market_status.json`, and database files under `data/`.

Rationale: AI agents use file search heavily. Generated and local-state files create noise and can mislead audits or code search.

Recommendation:
- Ensure generated artifacts are ignored and cleaned from tracked files if tracked.
- Keep persistent local app state under ADR-023 paths: `data/db/`, `data/session/`, `data/debug/`.

Guardrails:
- Do not delete user data without explicit approval.
- Audit git tracking before cleanup.

Edge cases to watch:
- Existing scripts expecting root-level database/session paths.

## Future Code Convention for AI-Agent Optimization

Add the following to `AI_AGENT_CHECKLIST.md` or a dedicated ADR/code convention document.

### File Size Rules

- Python files <= 400 LOC are preferred.
- 401-700 LOC requires a clear single responsibility.
- > 700 LOC requires an extraction plan before adding more behavior.
- > 1000 LOC is a merge blocker unless the task is explicitly a temporary characterization/test fixture file.
- Tests follow the same thresholds; split by behavior, not by arbitrary line count.

### Filename Responsibility Rules

- File name must answer: "What responsibility lives here?"
- Use suffixes consistently:
  - `_use_case.py` for application use-case entry points.
  - `_engine.py` for first-class reusable decision engines.
  - `_builder.py` for assembling immutable evidence/DTOs from inputs.
  - `_calculator.py` or `_metrics.py` for pure computations.
  - `_parser.py` for external payload/string parsing.
  - `_repository.py` for persistence implementations.
  - `_provider.py` for external/live/cached data provider implementations.
  - `_display.py` for CLI rendering only.
  - `_commands.py` for CLI command registration only.
  - `_factory.py` for dependency construction/wiring.
  - `_validator.py`, `_applier.py`, `_verifier.py` only when the file does exactly that role.
- Avoid generic names such as `bootstrap.py`, `utils.py`, `helpers.py`, `workflow.py`, `loader.py`, or `commands.py` when the module has a more specific responsibility.
- Historical docs should be topic-first, not agent/vendor-first.

### Extraction Rules

- Extract by stable responsibility, not by private helper grouping.
- Preserve public request/response contracts during extraction.
- Keep compatibility imports temporarily when renaming widely imported modules.
- First extraction target in a large use case should be DTOs and serialization, because they reduce scan burden without altering behavior.
- Second extraction target should be pure calculators/parsers, because they are easiest to characterize with tests.
- Do not extract a new abstraction unless the filename and public API make the next change easier to locate.

### Adapter Rules

- Adapter files must not own:
  - cache freshness policy
  - fetch/backfill/refresh/retry decisions
  - persistence orchestration beyond dependency wiring
  - scoring thresholds
  - business status calculation
  - provider-specific behavior beyond choosing the adapter/provider
- Adapter files may own:
  - Typer command definitions
  - option parsing
  - request DTO construction
  - dependency wiring
  - use-case invocation
  - output rendering
  - exception-to-user-message mapping

### Display Rules

- Display modules render facts; they do not decide facts.
- Any label derived from thresholds must either:
  - consume a label already computed by application/domain, or
  - clearly be named as presentation-only and backed by config/response metadata.
- Display defaults must not drift from engine/use-case config.

### DTO and Serialization Rules

- DTOs used by multiple functions/classes in a large workflow belong in `src/application/dto/`.
- `to_dict()` schema methods should live near DTO definitions unless they are adapter-specific.
- Persisted JSON/CSV/schema fields require compatibility notes before rename.
- New machine-facing outputs must include explicit names; avoid generic `score`, `status`, or `verdict` unless the artifact contract defines them.

### Infrastructure Provider Rules

- Provider files split by external capability, not by vendor alone once they exceed 700 LOC.
- Raw payload parsers should be separate from network/browser clients.
- Browser lifecycle must not share a file with HTTP payload parsers unless the file is small and strictly cohesive.
- Provider class names and filenames must match the dominant mechanism: `playwright_*` for browser, `stockbit_api_*` or `stockbit_http_*` for HTTP/token API.

### Test Organization Rules

- Split tests by behavior contract.
- Test file name must map to the production responsibility being protected.
- Prefer focused fixtures over one global mega-fixture.
- Characterization tests are required before extracting files above 1000 LOC.

## Recommended Refactor Order

1. Extract DTOs/serialization from `accumulation_screen_use_case.py` and `swing_analysis_workflow_use_case.py`.
2. Split pure parser/provider responsibilities from `playwright_stockbit_provider.py`.
3. Split display modules: `analyze_swing_display.py` and `screen_accum_display.py`.
4. Split `swing_tuning_patch_validator.py` by validate/dry-run/apply/verify.
5. Thin `fetch_market_commands.py` by moving workflow/fetch policy into application services.
6. Split `bootstrap.py` into explicit factory/config modules.
7. Split oversized backtest use cases and tests after characterization coverage is in place.

## Definition of Done for Future Extraction PRs

- Behavior is unchanged unless the task explicitly says otherwise.
- Existing CLI commands still register under the same names.
- JSON/CSV/persisted contracts are unchanged or migrated explicitly.
- Tests cover moved responsibilities at their new boundaries.
- No adapter gains workflow/policy during extraction.
- AI can locate the edited responsibility from the filename alone.
