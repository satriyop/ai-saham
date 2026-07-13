# Code Convention Audit - Fresh Code Audit

Scope: production code under `src/**/*.py`, plus tests only when they hide architecture violations. Documentation content is excluded from audit targets.

Audit date: 2026-07-14.

Audit goals:
- Keep files small enough for AI agents and humans to scan quickly.
- Make filenames expose the dominant responsibility.
- Prefer single responsibility, composability, deduplication, simplification, and clear boundaries.
- Remove hidden service-locator/global wiring patterns.
- Remove duplicated config loading and wiring.
- Keep CLI adapters thin: parse input, wire dependencies, call use cases, render output, map errors.

Status legend:
- `OPEN`: not fixed.
- `PARTIAL`: some extraction exists, but the finding still holds.
- `DONE`: use only after implementation is vetted.

## Findings

### 1. Critical: `src/adapters/cli/screen_pre_open_commands.py` still owns pre-open workflow policy

Status: OPEN.

Pointers:
- `src/adapters/cli/screen_pre_open_commands.py:47` defines `IntradayRunGuard` in the adapter.
- `src/adapters/cli/screen_pre_open_commands.py:73` builds market-session timing policy.
- `src/adapters/cli/screen_pre_open_commands.py:111` writes the pre-open sidecar artifact.
- `src/adapters/cli/screen_pre_open_commands.py:255` constructs browser providers, repositories, registry, notation provider, use cases, and workflow.

Rationale: The CLI module is not just a Typer adapter. It owns run eligibility, artifact persistence shape, JSON payload validation, provider fallback, AI initialization, repository construction, and workflow construction. That makes pre-open behavior hard for agents to discover because the real workflow is split between CLI code and application use cases.

Recommendation:
- Move run guard policy to an application service/use case, injected with a market-status provider function.
- Move sidecar serialization/write behavior to an application port plus infrastructure writer, or to an adapter artifact writer if it is purely CLI output; do not leave the schema inline in the command.
- Create an adapter factory for `PreOpenWorkflowUseCase` wiring. The command should call one factory and one use case.
- Keep CLI ownership limited to Typer option parsing, raw JSON string decoding, display calls, and `typer.Exit` error mapping.

Guardrails:
- Preserve CLI flags and output text unless a test is intentionally updated.
- Preserve non-trading-day behavior, pre-open-window warning behavior, and manual JSON mode.
- Do not import `src.infrastructure` from application code during extraction.

Risks to maintain:
- A misplaced guard can block legitimate dry-runs or allow accidental non-trading-day execution.
- Sidecar schema drift will break `saham trade confirm`.

Edge cases to watch:
- `--movers-json` without `--order-books-json`.
- Playwright installed but no session.
- `--allow-non-trading-day`.
- `--with-regime` and `--risk-strategy`.

### 2. Critical: `src/adapters/cli/analyze_commands.py` is a router, risk workflow, compare workflow, and renderer

Status: OPEN.

Pointers:
- `src/adapters/cli/analyze_commands.py:51` local display/error helpers.
- `src/adapters/cli/analyze_commands.py:143` builds the risk engine and optional sentiment workflow inside the command.
- `src/adapters/cli/analyze_commands.py:185` builds JSON response shape inline.
- `src/adapters/cli/analyze_commands.py:211` renders risk tables inline.
- `src/adapters/cli/analyze_commands.py:297` implements compare workflow and rendering inline.
- `src/adapters/cli/analyze_commands.py:358` also registers subcommands.

Rationale: This file violates adapter scanability. A reader looking for command registration must pass through risk execution policy, optional sentiment fetch, AI explanation display, JSON serialization, trend rendering, and compare logic. The filename is too broad for the responsibilities it still contains.

Recommendation:
- Split router registration from command implementations.
- Move `risk` execution into `src/application/use_case/run_risk_analysis_workflow_use_case.py` or equivalent, returning a structured result with assessment, optional sentiment, trend, warnings, and JSON-safe DTO data.
- Move compare execution into its own application use case or service.
- Move table rendering to a dedicated display module.
- Keep `analyze_commands.py` as a router/facade only.

Guardrails:
- Do not move Typer types or `typer.Exit` into application.
- Preserve JSON keys for `risk_assessment`.
- Preserve current no-data and rules-file error messages.
- Optional sentiment failure must remain a warning, not a hard failure.

Risks to maintain:
- Risk JSON is likely consumed by scripts. Schema changes are breaking changes.
- Trend rendering currently swallows trend failures; changing that can make `risk` brittle.

Edge cases to watch:
- `--format json --with-sentiment`.
- custom `--rules-file`.
- missing database table.
- `compare` with partial no-data tickers.

### 3. High: `src/adapters/cli/analyze_accum_commands.py` still resolves setup policy and use-case wiring in the CLI

Status: OPEN.

Pointers:
- `src/adapters/cli/analyze_accum_commands.py:206` loads audit and screen config directly.
- `src/adapters/cli/analyze_accum_commands.py:219` resolves setup presets into runtime option values.
- `src/adapters/cli/analyze_accum_commands.py:275` resolves universe through concrete loaders/repositories.
- `src/adapters/cli/analyze_accum_commands.py:329` constructs `AccumulationAuditUseCase` with concrete repositories, registry, rules loader, and derived feature policy.
- `src/adapters/cli/analyze_accum_commands.py:368` builds JSON output shape inline.

Rationale: The command still decides how setup presets override CLI inputs, how universe resolution is wired, and how application dependencies are composed. That is workflow/policy in the adapter.

Recommendation:
- Create an accumulation-audit workflow use case that accepts a request with raw CLI intent: explicit tickers, universe, setup, date range, filters, grids, output path intent.
- Move setup preset resolution and request normalization into that use case or a dedicated application service.
- Move concrete wiring to `src/adapters/cli/analyze_accum_workflow_factory.py`.
- Keep CSV writing either as an explicit output port or adapter-only artifact writing after receiving records.

Guardrails:
- Preserve setup preset precedence exactly: explicit CLI option wins over setup default.
- Preserve grid parsing errors and messages.
- Do not let the application depend on `YamlUniverseConfigLoader`, SQLite repositories, or config loaders.

Risks to maintain:
- Silent precedence changes alter audit result sets.
- Derived feature policy must remain the same as current screener config.

Edge cases to watch:
- setup with missing universe.
- explicit tickers plus `--universe`.
- `--simulate-exits` with custom grids.
- `--format json --output`.

### 4. High: `src/adapters/cli/trade_swing_tuning_commands.py` embeds tuning workflow, walk-forward split, and persistence policy

Status: OPEN.

Pointers:
- `src/adapters/cli/trade_swing_tuning_commands.py:43` builds tuning payloads in the adapter.
- `src/adapters/cli/trade_swing_tuning_commands.py:130` writes patch exports in the adapter.
- `src/adapters/cli/trade_swing_tuning_commands.py:259` computes IS/OOS split policy.
- `src/adapters/cli/trade_swing_tuning_commands.py:299` loads runner config and defaults.
- `src/adapters/cli/trade_swing_tuning_commands.py:320` runs backtests twice for walk-forward tuning.
- `src/adapters/cli/trade_swing_tuning_commands.py:384` writes tuning journal records.

Rationale: This CLI is doing more than adapting input/output. It owns tuning orchestration, walk-forward date partitioning, payload schema construction, journal persistence, and patch export. The command is difficult for agents to reason about because the tuning workflow is not a named application use case.

Recommendation:
- Create `RunSwingTuningReviewUseCase` with request/result DTOs.
- Move IS/OOS split validation, default resolution, backtest orchestration, tuning payload construction, and optional journal/patch result data into application.
- Keep filesystem journal/patch writing behind explicit ports or keep only final adapter writes with application-generated payloads.
- Leave the CLI responsible for Typer parsing, output format selection, display call, and error mapping.

Guardrails:
- Preserve `--is-ratio` validation and non-empty IS/OOS constraints.
- Preserve JSON payload keys and patch export shape.
- Do not import CLI runner helpers from application; extract runner behavior into application/composition if needed.

Risks to maintain:
- Walk-forward split drift can invalidate tuning review comparisons.
- Journal schema drift can break later review tooling.

Edge cases to watch:
- `--is-ratio` without `--end`.
- start date equal to or after end date.
- `--save` and `--export-patch` with `--format json`.
- universe-only runs with no explicit tickers.

### 5. High: `src/application/services/swing_broker_detail_builder.py` mixes flow detail, broker aggregation, tier policy, and setup note policy

Status: OPEN.

Pointers:
- `src/application/services/swing_broker_detail_builder.py:18` builds setup-facing broker quality notes.
- `src/application/services/swing_broker_detail_builder.py:59` builds aggregate `FlowDetail`.
- `src/application/services/swing_broker_detail_builder.py:137` builds broker detail from daily flow records.
- `src/application/services/swing_broker_detail_builder.py:259` builds broker detail from summary records with duplicated buyer/seller aggregation.

Rationale: The filename says one builder, but the file contains four different responsibilities: flow summary, broker-line aggregation, smart/noise weighting policy, and setup note messaging. Two data-source paths duplicate the same aggregation shape. This is hard for agents to safely change because changing one branch can leave the other branch semantically stale.

Recommendation:
- Extract broker-line aggregation into a pure `broker_detail_aggregation.py` service that accepts normalized signed broker flow rows.
- Extract `build_flow_detail` into `swing_flow_detail_builder.py`.
- Extract `build_broker_quality_note` into `swing_broker_quality_note_policy.py`.
- Keep `swing_broker_detail_builder.py` as a thin orchestrator or rename it to the exact remaining responsibility.

Guardrails:
- Preserve top buyer/seller ordering by absolute net value.
- Preserve source-specific fields: daily-flow path currently uses `source="stockbit"` and unknown broker type; summary path preserves `latest.source` and broker type.
- Preserve quality labels exactly unless tests are intentionally updated.

Risks to maintain:
- Broker quality is decision-support evidence. Small aggregation changes can alter setup confidence.
- Daily flow and summary fallback must stay behaviorally equivalent where their inputs overlap.

Edge cases to watch:
- no buyers.
- negative smart flow with positive latest net flow.
- broker appears across multiple sessions.
- top buyer/seller share when totals are zero.

### 6. High: `src/infrastructure/browser/stockbit_base_provider.py` hides SQLite connection state in a module global

Status: OPEN.

Pointer: `src/infrastructure/browser/stockbit_base_provider.py:26` defines `_conn_registry` and `_get_conn()` reuses one connection per resolved DB path.

Rationale: This is hidden global state. It couples all Stockbit providers in a process through connection identity, makes lifecycle and close behavior implicit, and can mask transaction/isolation problems in tests. The comment assumes short-lived CLI processes and unique test paths, but the code is a reusable infrastructure base class.

Recommendation:
- Introduce an explicit connection/session provider object, for example `SQLiteConnectionProvider`, owned by infrastructure composition.
- Inject the provider into Stockbit cache providers or into `StockbitCachingProvider`.
- Provide explicit close/reset behavior for tests and long-lived processes.
- If shared connections are still needed for performance, make sharing a named object, not a module-level registry.

Guardrails:
- Preserve row factory behavior.
- Preserve schema creation timing.
- Do not open a new connection for every query if existing providers rely on shared transaction visibility.

Risks to maintain:
- Connection lifecycle changes can break cache writes or create locked-database errors.
- Existing providers may rely on immediate visibility between cache writes and reads.

Edge cases to watch:
- multiple providers sharing the same `db_path`.
- test suites reusing a temp DB path.
- process shutdown after failed schema creation.
- concurrent reads/writes with `check_same_thread=False`.

### 7. High: Stockbit provider configuration is frozen at import time through `STOCKBIT_CFG`

Status: OPEN.

Pointers:
- `src/infrastructure/config/stockbit_config.py:223` loads `STOCKBIT_CFG` at import time.
- `src/infrastructure/browser/playwright_stockbit_provider.py:98` aliases `_sb = STOCKBIT_CFG`.
- `src/infrastructure/browser/stockbit_broker_requests.py:19` aliases `_sb = STOCKBIT_CFG`.
- Many Stockbit provider modules copy URL/TTL constants from `STOCKBIT_CFG` at import time.

Rationale: Import-time config loading creates hidden global state. Tests or commands that need a different config path cannot inject it cleanly; agents must know which modules cached values at import time. This also makes config changes in a long-running process invisible after module import.

Recommendation:
- Replace module-level URL/TTL constants with an explicit `StockbitConfig` dependency passed through provider factories.
- Keep `load_stockbit_config()` in infrastructure config, but call it from composition roots, not provider module imports.
- For constants that are truly static defaults, keep them on `StockbitConfig`; for runtime config, pass the object.

Guardrails:
- Do not make application code import `StockbitConfig`.
- Preserve default behavior when no explicit config is passed.
- Avoid a broad compatibility shim that reintroduces `STOCKBIT_CFG` as the canonical path.

Risks to maintain:
- Endpoint template changes are high blast-radius across browser/API providers.
- TTL changes can alter cache freshness behavior.

Edge cases to watch:
- tests that monkeypatch config paths.
- provider modules imported before CLI config setup.
- per-command override of config path.
- browser context timeout defaults.

### 8. Medium: `src/infrastructure/ai/formula_translator.py` repeats the old multi-provider adapter cluster pattern

Status: OPEN.

Pointers:
- `src/infrastructure/ai/formula_translator.py:110` defines one adapter class for all providers.
- `src/infrastructure/ai/formula_translator.py:241` dispatches by provider string.
- `src/infrastructure/ai/formula_translator.py:262` through `src/infrastructure/ai/formula_translator.py:424` embeds Claude, OpenAI, Gemini, Ollama, and mock clients in one file.
- `src/infrastructure/ai/formula_translator.py:42` also contains formula canonicalization.

Rationale: This file has the same shape that was previously cleaned up for strategy translation: output canonicalization, prompt flow, provider client implementations, provider dispatch, and mock templates live together. Adding or fixing one provider forces agents to scan unrelated providers and canonicalization logic.

Recommendation:
- Extract canonicalization to `formula_translator_output.py`.
- Extract provider clients to `formula_translator_clients.py`.
- Extract mock templates/keyword mapping to `formula_translator_mock_templates.py`.
- Keep `FormulaTranslatorAdapter` as orchestration only: validate provider, build prompts, call a client function, canonicalize output, retry once.

Guardrails:
- Preserve exception types and messages where tests assert them.
- Preserve supported provider names and environment variable fallback behavior.
- Do not move prompt text into client modules.

Risks to maintain:
- Auth/rate-limit/timeout error mapping differs per provider; careless consolidation can erase useful diagnostics.
- Mock behavior is used by tests and offline workflows.

Edge cases to watch:
- `provider=None` and `AI_PROVIDER` unset.
- Ollama host/model env vars.
- unsupported intent returning `UNSUPPORTED`.
- retry after unsupported output.

### 9. Medium: `src/adapters/cli/view_broker_commands.py` mixes broker query commands, provider status, and distribution rendering

Status: OPEN.

Pointers:
- `src/adapters/cli/view_broker_commands.py:41` creates provider instances.
- `src/adapters/cli/view_broker_commands.py:46` displays broker provider/session status.
- `src/adapters/cli/view_broker_commands.py:84` through `src/adapters/cli/view_broker_commands.py:309` implements flow/top/history/top-foreign commands.
- `src/adapters/cli/view_broker_commands.py:316` queries broker distribution.
- `src/adapters/cli/view_broker_commands.py:367` renders broker distribution tables inline.

Rationale: The filename is broad and the file is a mixed command surface: cache reads, provider/session status, direct infrastructure provider construction, JSON output, and table rendering. Agents looking for broker distribution display or provider status have to inspect the entire broker view command module.

Recommendation:
- Split distribution display into `view_broker_distribution_display.py`.
- Move provider/session status into a dedicated `view_broker_status_commands.py` or a workflow factory.
- Keep cache query commands in `view_broker_commands.py` only if they share a single read-only broker-view responsibility.
- Prefer a factory for concrete repository/provider construction.

Guardrails:
- Preserve command names and JSON output shape.
- Do not merge fetch behavior into view commands.
- Do not move Typer output into application use cases.

Risks to maintain:
- Broker distribution output is manually formatted and easy to regress visually.
- Provider status has session-path assumptions that should not leak into query commands.

Edge cases to watch:
- no cached distribution.
- unknown `--source`.
- `--format json`.
- missing Stockbit profile marker.

## Non-Findings From This Pass

These files are large, but I am not opening findings now because the current responsibility is cohesive enough or the split would be mostly cosmetic:

- `src/adapters/cli/screen_accum_single_display.py`: display-only surface for one accumulation screen result; large but contextual.
- `src/application/use_case/report_signal_readiness_use_case.py`: report DTOs plus one readiness-report workflow; broad, but still one use case.
- `src/application/use_case/generate_signal_forward_labels_use_case.py`: label generation policy is dense, but filename and responsibility match.
- `src/infrastructure/browser/stockbit_broker_parsers.py`: parser collection is contextual; no provider/network concern found in this pass.
- Test suite: I did not find a fresh, specific test fixture masking a current architecture violation beyond normal command monkeypatching. Do not create a test refactor task without a concrete boundary it hides.

## Code Convention For Future Agents

- CLI command modules must not own workflow policy. If a command computes run guards, default precedence, multi-step orchestration, persistence schema, or secondary use-case calls, extract an application workflow use case.
- Import-time config objects are hidden global state. Infrastructure providers should receive config from composition roots, not copy module-level values from loaded YAML.
- Shared mutable infrastructure state must be explicit and injectable. Module-level registries are allowed only for immutable constants.
- Builders should describe one output shape. If a builder also contains ranking policy, source normalization, note/message policy, and fallback aggregation, split by those responsibilities.
- Large display modules are not automatically violations. Split display code only when separate panels/tables are independently reusable or the filename no longer exposes what is rendered.
