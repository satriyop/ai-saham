# Config And Persistence Audit - 2026-07-15

Scope: code only. This audit targets duplicated config loading/wiring, hidden config defaults, application-to-infrastructure leaks, persistence files mixing schema/query/read-model policy, and test patterns that mask those issues.

Baseline checked:
- `rg -n "from src\.adapters|import src\.adapters|from src\.infrastructure|import src\.infrastructure" src/application src/domain` has no matches.
- `pytest tests/architecture -q` passed before this report.
- `src/application/services/universe_loader.py` and `src/application/use_case/daily_briefing_use_case.py` keep explicit path defaults behind injected loaders/request DTOs; do not treat them as layer leaks.
- `src/infrastructure/persistence/sqlite_corporate_action_calendar_repository.py` and `src/infrastructure/persistence/sqlite_iev_repository.py` are large but still repository-cohesive; do not split them without a behavior-driven reason.

## Findings

### 1. High: Stockbit providers hide config loading across constructors and request helpers

Status: RESOLVED (commit `11d28b9`)

Resolution:
- Added `src/infrastructure/browser/stockbit_config_bundle.py` (`load_stockbit_provider_config`) as
  the single Stockbit config composition entry point.
- `create_readonly_stockbit_providers` now loads `StockbitConfig` once and passes the same instance
  into every provider it constructs.
- `get_stockbit_session` and `create_stockbit_api_client` now accept an explicit `stockbit_config`
  and thread it through instead of loading independently.
- All active Stockbit composition roots now load config once per call and pass it explicitly into
  every provider/client/session constructed there, including:
  `fetch_market_provider_factory.create_broker_provider`,
  `fetch_broker_provider_factory.create_broker_data_provider`,
  `risk_engine_factory.create_risk_engine`, `signal_engine_factory.create_signal_engine`,
  `fetch_market_enrichment_refresh.fetch_enrichment`, `view_ticker_display.show_ticker_view`,
  `learn_snapshot_commands.snapshot`, `learn_track_commands.track`,
  `fetch_calendar_commands.fetch_calendar`, `fetch_iev_commands.collect_iev`,
  `screen_pre_open_workflow_factory.resolve_pre_open_browser_plan` /
  `create_pre_open_cli_workflow`, `fetch_universe_factories.create_provider_adapter`, and
  `trade_intraday_confirm_factory._build_live_providers`.
- Existing `stockbit_config: StockbitConfig | None = None` fallback parameters were kept on provider
  constructors and request helpers as compatibility shims; no active composition path relies on the
  fallback anymore.
- Added tests in `tests/infrastructure/browser/test_stockbit_provider_bundle.py` and
  `tests/adapters/cli/test_fetch_provider_factories_stockbit_config.py` proving config is loaded
  once and shared across constructed providers; updated existing CLI tests whose fakes/monkeypatches
  needed the new `stockbit_config` parameter.

Pointer:
- `src/infrastructure/browser/stockbit_provider_bundle.py` constructs read-only providers without passing `StockbitConfig`.
- `src/adapters/cli/fetch_market_provider_factory.py` and `src/adapters/cli/fetch_broker_provider_factory.py` construct `StockbitBrokerProvider` without passing `StockbitConfig`.
- Hidden fallbacks exist in many provider/request modules, including `src/infrastructure/browser/playwright_stockbit_provider.py:118`, `src/infrastructure/browser/stockbit_api_client.py:159`, `src/infrastructure/browser/stockbit_broker_provider.py:78`, `src/infrastructure/browser/stockbit_broker_requests.py:31`, `src/infrastructure/browser/stockbit_analyst.py:125`, `src/infrastructure/browser/stockbit_order_book.py:164`, `src/infrastructure/browser/stockbit_fundamentals.py:62`, `src/infrastructure/browser/stockbit_shareholding.py:193`.

Rationale:
- Config ownership is scattered. A future agent cannot tell whether Stockbit settings are loaded once by composition or implicitly per provider.
- Hidden defaults make tests pass without exercising real adapter wiring.
- Provider constructors look pure but may read config from disk, which is hostile to deterministic review.

Recommendation:
- Create one infrastructure composition entry point for Stockbit config loading, for example `src/infrastructure/browser/stockbit_config_bundle.py` or extend `stockbit_provider_bundle.py`.
- Load `StockbitConfig` exactly once in the adapter/composition layer and pass it explicitly to every Stockbit provider/request helper constructed there.
- Update `create_readonly_stockbit_providers`, `create_broker_provider`, `create_broker_data_provider`, and session/API-client factories to thread the same config instance.
- Keep temporary optional constructor parameters only as compatibility shims while migrating call sites; do not add new call sites that rely on `stockbit_config or load_stockbit_config()`.
- Add a targeted test that patches `load_stockbit_config` and proves the provider bundle/factories load once and pass the config through.

Guardrails and edge cases:
- Preserve exact URL/header/session behavior from `StockbitConfig`.
- Do not import `load_app_config` or `load_stockbit_config` into application/domain.
- Do not convert this into a global singleton or service locator.
- Watch browser/session providers separately from HTTP-only providers; both must receive the same config source.
- Do not change provider availability behavior when Stockbit config/session is missing.

### 2. High: `sqlite_data_update_status.py` mixes table catalog, SQL reader, and freshness policy

Status: TODO

Pointer:
- `src/infrastructure/persistence/sqlite_data_update_status.py:17` defines `_TableSpec`.
- `src/infrastructure/persistence/sqlite_data_update_status.py:54` embeds the whole fetch-market table catalog.
- `src/infrastructure/persistence/sqlite_data_update_status.py:199` builds SQL status rows.
- `src/infrastructure/persistence/sqlite_data_update_status.py:309` implements freshness/status policy.

Rationale:
- A single 411-line persistence file now owns three concerns: what tables exist, how SQLite is queried, and how statuses/impacts/issues are classified.
- This makes future table additions risky because agents must scan the entire file to know whether they are editing catalog data, SQL plumbing, or user-facing policy strings.

Recommendation:
- Extract the table catalog to `src/infrastructure/persistence/data_update_status_catalog.py`.
- Extract pure freshness/range helpers to `src/infrastructure/persistence/data_update_status_freshness.py`.
- Keep `sqlite_data_update_status.py` as the SQLite reader/orchestrator only: connect, check table existence, aggregate rows, map to `DataUpdateTableStatus`.
- Add unit tests for the pure freshness module covering `range`, `today`, `month`, `ttl30`, `ttl7`, partial ticker counts, and `pending-eod`.
- Keep existing integration/CLI status tests passing unchanged.

Guardrails and edge cases:
- Preserve every existing status string, impact text, issue text, and range label exactly unless tests explicitly approve a wording change.
- Preserve `pending-eod` when the market is open and latest date is within three days of expected trading day.
- Preserve skipped/missing-db behavior.
- Do not move `DataUpdateTableStatus` out of the application use-case contract.
- Do not add ORM abstractions; this is a read-model split, not a persistence rewrite.

### 3. High: `sqlite_data_quality_audit.py` mixes snapshot orchestration, SQL probes, and rule/catalog definitions

Status: TODO

Pointer:
- `src/infrastructure/persistence/sqlite_data_quality_audit.py:29` orchestrates the full snapshot.
- `src/infrastructure/persistence/sqlite_data_quality_audit.py:153` contains generic table snapshot SQL.
- `src/infrastructure/persistence/sqlite_data_quality_audit.py:291` starts quality-rule probes.
- `src/infrastructure/persistence/sqlite_data_quality_audit.py:334` embeds enrichment table/date-column catalog.

Rationale:
- The reader is doing too much: selecting audit subjects, composing SQL, defining rule predicates, and assembling the raw snapshot.
- Future agents must read the whole file to add one audit rule or one enrichment table, which is exactly the scanability problem this repo has been trying to remove.

Recommendation:
- Extract enrichment/table catalog constants to `src/infrastructure/persistence/data_quality_audit_catalog.py`.
- Extract low-level SQLite helpers/probes to `src/infrastructure/persistence/data_quality_audit_sql.py`.
- Keep `SQLiteDataQualityAuditReader.load_snapshot()` as a short orchestration method that calls named probe functions.
- Add targeted tests for the new SQL/probe module using in-memory SQLite for:
  - missing table returns safe zero/`None`;
  - stale ticker count;
  - unsafe broker summary rows;
  - bad candle rows;
  - unknown candle provenance rows;
  - enrichment snapshot catalog iteration.

Guardrails and edge cases:
- Preserve `DataQualityRawSnapshot` and `DataQualityTableSnapshot` field values exactly.
- Preserve IHSG fallback order: canonical benchmark, Yahoo benchmark, any candle date.
- Preserve current SQL predicates, including `source='stockbit'` and candle provenance columns.
- Do not move audit decision scoring into infrastructure; infrastructure should only return raw facts.

### 4. Medium: AI provider default resolution is duplicated across AI and sentiment infrastructure

Status: RESOLVED (commit `bb2afb0`)

Pointer:
- `src/infrastructure/ai/factory.py:26` defines `_default_provider()`.
- `src/infrastructure/ai/formula_translator.py:49` defines `_default_provider()`.
- `src/infrastructure/ai/strategy_translator.py:46` defines `_default_provider()`.
- `src/infrastructure/sentiment/ai_classifier.py:28` defines `_default_ai_provider()`.

Rationale:
- Four modules independently resolve the same default provider from `AI_PROVIDER`/`load_app_config().ai.provider`.
- If provider precedence or config source changes, agents must update several files and can easily miss one.

Recommendation:
- Create a single helper in infrastructure, for example `src/infrastructure/ai/provider_config.py`.
- Expose `resolve_ai_provider(explicit_provider: str | None = None) -> str` with current precedence: explicit provider, `AI_PROVIDER`, then `load_app_config().ai.provider`.
- Update the four modules to call the helper.
- Keep provider-specific validation/client construction inside the existing modules; the helper should only resolve the provider name.
- Add tests for explicit override, env override, app-config fallback, and no import-time config loading.

Guardrails and edge cases:
- Do not instantiate clients at import time.
- Do not move sentiment code into `src/infrastructure/ai` unless imports stay one-way and simple.
- Preserve lowercasing/normalization behavior used by each caller.
- Preserve current error messages for unsupported providers unless a test explicitly changes them.

### 5. Medium: Evidence-context config loaders bypass `AppConfig.config_paths`

Status: RESOLVED (commit `d41b3ed`)

Pointer:
- `src/infrastructure/config/company_quality_context_config_loader.py:14` hardcodes `config/company_quality_context.yaml`.
- `src/infrastructure/config/sector_context_config_loader.py:13` hardcodes `config/sector_context.yaml`; `src/infrastructure/config/sector_context_config_loader.py:14` hardcodes `config/universes.yaml`.
- `src/infrastructure/config/ticker_profile_config_loader.py:15` hardcodes `config/ticker_profile.yaml`; `src/infrastructure/config/ticker_profile_config_loader.py:16` hardcodes `config/universes.yaml`.
- `src/infrastructure/config/institutional_accumulation_config_loader.py:14` hardcodes `config/institutional_accumulation.yaml`.
- `src/adapters/cli/stock_analysis_workflow_dependencies.py:121` wires these factories/loaders without passing paths.
- `src/infrastructure/config/app_config.py:52` and `config/default.yaml:43` do not expose these paths in `config_paths`.

Rationale:
- The repo has an application-wide config path mechanism, but several evidence/context loaders keep separate hardcoded defaults.
- User overrides in `config/user.yaml` cannot redirect these files, so config behavior is split across two conventions.

Recommendation:
- Add explicit fields to `ConfigPathsConfig` and `config/default.yaml` for:
  - `company_quality_context`
  - `sector_context`
  - `ticker_profile`
  - `institutional_accumulation`
  - `universes` if loaders need a shared universe config path.
- Update `stock_analysis_workflow_dependencies.py` to load `app_config = load_app_config()` once and pass those paths into the evidence/context factories.
- Keep loader function parameters as explicit `path` arguments for tests and direct use.
- Add tests proving `config/user.yaml` overrides or a mocked `AppConfig` path is honored by the stock-analysis dependency bundle.

Guardrails and edge cases:
- Do not remove explicit path parameters from loader functions.
- Do not break existing default file names.
- Do not read app config from application services.
- Watch missing-file semantics: `company_quality_context` currently falls back to defaults if missing; `sector_context` and `ticker_profile` currently raise for missing config files; `institutional_accumulation` falls back only when default path is missing.

## Code Convention For Future Agents

- Config must be loaded at adapter/composition boundaries and passed explicitly into providers, repositories, engines, and use cases. A constructor must not silently read config from disk unless it is a documented compatibility shim and all new call sites avoid it.
- If a config file path is user-overridable, it belongs in `AppConfig.config_paths` and `config/default.yaml`; do not add independent `Path("config/...")` defaults in new infrastructure loaders.
- Persistence read models must keep table catalogs, SQL helpers, and status/policy classification in separate named modules once a file crosses multiple review concerns.
- Test architecture by patching config loaders to fail: provider/composition tests should prove wiring passes explicit config instead of hiding global fallback behavior.
- Do not add application/domain imports from infrastructure or adapters to solve config problems. Thread dependency values from the adapter/composition layer instead.
