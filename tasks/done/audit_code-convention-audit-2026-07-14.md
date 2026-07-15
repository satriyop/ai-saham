# Code Convention Audit - Closed

Scope: production code under `src/**/*.py`; tests only when they hide architecture
violations. Documentation content is excluded from audit targets.

Audit date: 2026-07-14.

Closure date: 2026-07-14.

Outcome: all findings in this audit batch are resolved. This file is retained
as the completed audit history, not as an active work queue.

Status legend: `RESOLVED` = implemented and vetted during this audit batch.

## Findings

### 1. Critical: import-time `APP_CFG` still acts as hidden global config

Status: `RESOLVED` (2026-07-14) — `APP_CFG` module-level binding removed from
`src/infrastructure/config/app_config.py`; all `src/**` call sites now resolve
via `load_app_config()` at command/composition execution time. Verified by
`tests/architecture/test_app_config_no_import_time_load.py` (no `src/**`
module imports `APP_CFG`; no CLI module calls `load_app_config()` at import
time) and `tests/architecture/test_layer_boundaries.py`. Full suite green
(3828 passed).

Pointer:
- `src/infrastructure/config/app_config.py:163` loads YAML through `load_app_config()`.
- `src/infrastructure/config/app_config.py:182` binds `APP_CFG = load_app_config()` at import time.
- `src/adapters/cli/fetch_broker_commands.py:47` imports `APP_CFG`.
- `src/adapters/cli/fetch_broker_commands.py:49` through `src/adapters/cli/fetch_broker_commands.py:56` derive Typer defaults from imported config.
- `src/infrastructure/sentiment/ai_classifier.py:16` imports `APP_CFG`.
- `src/infrastructure/sentiment/ai_classifier.py:20` captures `_DEFAULT_AI_PROVIDER` at import time.
- Current scan shows many adapter/config modules still read `APP_CFG` directly; this is broader than one command file.

Rationale:
- Importing a module should not read user YAML or freeze runtime defaults.
- Typer option defaults are evaluated at import time, so config changes after import are ignored.
- This hides wiring from AI agents and makes tests pass by module import order instead of explicit dependency construction.

Recommendation:
- Keep `load_app_config()` as the explicit loader, but stop using `APP_CFG` as a runtime singleton in CLI, composition, and provider-selection code.
- Add small typed command/composition config loaders where needed, for example `load_fetch_broker_command_config()` or `load_ai_provider_config()`.
- For Typer options whose default comes from config, use `None` as the function default and resolve inside the command from the loaded config.
- Add/extend architecture tests so `src/adapters/cli/**` cannot import `APP_CFG`, and runtime provider factories cannot capture `APP_CFG` values at module import.

Guardrails:
- Do not replace `APP_CFG` with another module-level loaded object.
- Do not add compatibility aliases like `APP_CFG = load_app_config()` in a different module.
- Preserve CLI flag names, env override behavior, and existing config file keys.
- Migrate by command/provider group; do not do a risky repo-wide mechanical rewrite without focused tests.

Risk to maintain:
- If left as-is, future agents will keep adding global config defaults because the pattern looks sanctioned.
- Tests can become order-dependent because imported modules freeze config before monkeypatches or temp config files run.

Edge cases to watch:
- Typer help output may stop showing dynamic config defaults when defaults become `None`; if exact help text matters, document resolved defaults in help text without freezing config at import.
- Provider factories must preserve env-var precedence over config values where that precedence already exists.

### 2. High: `src/infrastructure/sentiment/ai_classifier.py` is a multi-provider adapter cluster

Status: `RESOLVED` (2026-07-14) — `AIClassifier` is now a thin orchestrator only
(resolve provider, lazy-create client, build prompt, call provider, parse
response, fallback to `NEUTRAL|GENERAL`). Prompts moved to
`ai_classifier_prompts.py`, response parsing to
`ai_classifier_response_parser.py`, and provider client creation/calls to
`ai_classifier_providers.py` (`SUPPORTED_AI_CLASSIFIER_PROVIDERS`,
`create_ai_classifier_client`, `call_ai_classifier_provider`,
`AIClassifierProviderClientFactory`). Provider names, fallback behavior, and
`AI_PROVIDER` env/config precedence unchanged; `AIClassifier` remains
import-compatible. Verified by
`tests/infrastructure/sentiment/test_ai_classifier.py`,
`test_ai_classifier_prompts.py`, `test_ai_classifier_response_parser.py`,
`test_ai_classifier_providers.py`, plus `tests/architecture` and
`tests/integration/test_command_smoke_matrix.py` (all green).

Pointer (pre-refactor, kept for history):
- `src/infrastructure/sentiment/ai_classifier.py:20` captures provider config globally.
- `src/infrastructure/sentiment/ai_classifier.py:27` through `src/infrastructure/sentiment/ai_classifier.py:48` own prompt templates.
- `src/infrastructure/sentiment/ai_classifier.py:117` through `src/infrastructure/sentiment/ai_classifier.py:139` dispatch provider selection.
- `src/infrastructure/sentiment/ai_classifier.py:143` through `src/infrastructure/sentiment/ai_classifier.py:208` create provider clients.
- `src/infrastructure/sentiment/ai_classifier.py:210` through `src/infrastructure/sentiment/ai_classifier.py:306` call provider-specific APIs.
- `src/infrastructure/sentiment/ai_classifier.py:308` through `src/infrastructure/sentiment/ai_classifier.py:333` parse/canonicalize output.

Rationale:
- One filename hides prompt policy, provider transport, provider factory, retry/error mapping, and response parsing.
- The structure repeats the same multi-provider smell already cleaned up in other AI adapter areas.
- A future agent cannot safely update one provider without scanning every classification concern in the file.

Recommendation:
- Keep `AIClassifier` as the thin orchestrator that implements the domain port.
- Extract prompts to `src/infrastructure/sentiment/ai_classifier_prompts.py`.
- Extract response parsing to `src/infrastructure/sentiment/ai_classifier_response_parser.py`.
- Extract provider clients/calls to provider-specific modules under `src/infrastructure/sentiment/providers/`.
- Add a factory that receives explicit provider/model config instead of reading `APP_CFG` at import.

Guardrails:
- Preserve fallback behavior: any classification failure returns `NEUTRAL | GENERAL`.
- Preserve existing provider names: `deepseek`, `claude`, `openai`, `gemini`, `ollama`.
- Do not move domain `Classification`, `Sentiment`, or `CatalystType` into infrastructure.
- Do not add network calls in tests; provider clients must be fakeable.

Risk to maintain:
- Adding one provider today touches global selection, client creation, call shape, parser expectations, and defaults in one file.
- Provider-specific import errors are easy to break because they are embedded in one large class.

Edge cases to watch:
- Gemini and Ollama response shapes differ from OpenAI-compatible chat responses.
- The parser currently accepts loose output containing `POSITIVE` or `NEGATIVE`; preserve this tolerant parsing unless a dedicated behavior task changes it.

### 3. High: evidence builders are duplicated multi-concern orchestration hubs

Status: `RESOLVED` (2026-07-14)

Resolution:
- Extracted `src/application/services/candidate_evidence_data_loader.py` (`CandidateEvidenceDataLoader`) for shared point-in-time candle/broker-flow/peer-candle/benchmark-return loading, used by both coordinators.
- Extracted per-family assemblers: `candidate_institutional_accumulation_evidence_assembler.py`, `candidate_ticker_profile_evidence_assembler.py`, `candidate_sector_context_evidence_assembler.py`, `candidate_company_quality_context_evidence_assembler.py`, `candidate_setup_phase_evidence_assembler.py`.
- `SwingAnalysisEvidenceBuilder.build()` and `AccumulationCandidateEvidenceBuilder`'s public `build_candidate_*`/`detect_candidate_setup_phase` methods now delegate to the data loader and assemblers instead of duplicating repository fetches and request construction inline.
- Fallback builder factories are normalized once at `__init__` time (no method-level lazy default construction), preserving the existing constructor-level factory-override contract.
- Warning strings, best-effort `None`-on-failure behavior, 45-day broker windows, and `end_date=snapshot_date` point-in-time boundaries are unchanged; verified via `tests/application/services/test_candidate_evidence_data_loader.py`, `tests/application/services/test_swing_analysis_evidence_builder.py`, `tests/application/services/test_accumulation_candidate_evidence_builder.py`, plus the existing fallback/regression suites, `tests/architecture`, and `tests/integration/test_command_smoke_matrix.py`.

Pointer:
- `src/application/services/swing_analysis_evidence_builder.py:151` through `src/application/services/swing_analysis_evidence_builder.py:455` builds setup, flow, phase, strategy, institutional accumulation, ticker profile, sector, company quality, and corporate-action evidence in one method.
- `src/application/services/swing_analysis_evidence_builder.py:120` through `src/application/services/swing_analysis_evidence_builder.py:149` lazy-construct fallback builders.
- `src/application/services/accumulation_candidate_evidence_builder.py:100` through `src/application/services/accumulation_candidate_evidence_builder.py:129` repeats fallback builder construction.
- `src/application/services/accumulation_candidate_evidence_builder.py:140` through `src/application/services/accumulation_candidate_evidence_builder.py:455` repeats per-evidence data loading and best-effort assembly.

Rationale:
- These files are not just long; they duplicate the same evidence-family wiring and repository data gathering in two places.
- Lazy imports and broad best-effort catches make the dependency graph hard for AI agents to discover.
- The filenames imply one builder each, but each file owns several independent evidence families.

Recommendation:
- Extract shared data loading into a small application collaborator, for example `CandidateEvidenceDataLoader`, responsible for point-in-time candles, 45-day broker flow windows, broker summaries, foreign-flow points, peer candles, and benchmark return inputs.
- Extract evidence-family assemblers for institutional accumulation, ticker profile, sector context, company quality context, and setup phase.
- Keep `SwingAnalysisEvidenceBuilder` and `AccumulationCandidateEvidenceBuilder` as thin coordinators that assemble their existing result shapes.
- Make fallback builders explicit constructor dependencies or factory dependencies; no hidden default construction inside evidence methods.

Guardrails:
- Preserve best-effort behavior exactly: swing analysis should keep warning strings where warnings currently exist; accumulation candidate observation building should keep returning `None` for unavailable diagnostic evidence.
- Preserve point-in-time boundaries: all repository calls must keep `end_date=snapshot_date` and existing 45-day windows.
- Do not move infrastructure imports into application.
- Do not change scoring authority; diagnostic evidence must remain diagnostic where it is currently diagnostic.

Risk to maintain:
- A future evidence-family change can easily diverge between swing analysis and accumulation screening.
- Hidden fallback builders make it unclear which config path is active in production.

Edge cases to watch:
- Empty candle collections must not crash setup phase or volatility context.
- Peer candle failures are intentionally non-fatal; preserve per-peer isolation.
- Institutional accumulation needs the same broker summaries/foreign-flow data shape in both callers.

### 4. Medium: `src/application/services/swing_tuning_review_journal.py` mixes store, DTOs, comparison, and measurement

Status: `RESOLVED` (2026-07-14)

Resolution:
- Extracted `src/application/dto/swing_tuning_review.py` holding all report/DTO dataclasses (`SwingTuningReviewSaveResult`, `SwingTuningReviewSummary`, `SwingTuningReviewReport`, `SwingTuningMetricDelta`, `SwingTuningReviewComparison`, `SwingTuningAppliedPatchSummary`, `SwingTuningPostApplyMeasurement`) and their `to_dict()` bodies verbatim.
- Extracted `src/application/services/swing_tuning_review_summary.py` (`summarize_review_record`, formerly private `_summarize_record`, plus its parsing helpers `_dict`/`_str`/`_int`/`_float`/`_list` and the shared `_metric_deltas`/`_delta` helpers).
- Extracted `src/application/services/swing_tuning_review_comparison.py` (`compare_latest_review`, a new pure function taking already-sorted records; the `len(records) < 2` early return moved into this function as comparison policy).
- Extracted `src/application/services/swing_tuning_post_apply_measurement.py` (`measure_post_apply`, a new pure function taking already-sorted apply/review records).
- `SwingTuningReviewJournal` is now a thin facade over `SwingTuningReviewStore`: `append_review`, `review`, `compare_latest`, `measure_latest_apply` each read/sort via the store and delegate to the extracted functions.
- No JSON key, status string (`INSUFFICIENT_HISTORY`, `READY`, `NO_APPLY_LOG`, `APPLY_LOG_INVALID`, `INSUFFICIENT_REVIEW_HISTORY`), note string, or metric name changed. Sort order unchanged (`compare_latest` descending, `measure_latest_apply` ascending by `recorded_at`).
- No compatibility re-export left behind; every call site (`src/adapters/cli/trade_swing_tuning_measurement_display.py`, `src/adapters/cli/trade_swing_tuning_review_display.py`, `src/application/services/swing_tuning_loop_status.py`, and the affected test files) imports moved symbols from their new location.
- Verified by `tests/application/services/test_swing_tuning_review_journal.py` (facade, unchanged), new `test_swing_tuning_review_summary.py`, `test_swing_tuning_review_comparison.py`, `test_swing_tuning_post_apply_measurement.py`, plus `test_swing_tuning_performance.py`, `test_swing_tuning_walk_forward_guards.py`, `test_run_swing_tuning_review_use_case.py`, `test_trade_swing_tuning_workflow_factory.py`, `tests/architecture`, `tests/integration/test_command_smoke_matrix.py`, and the full suite (3888 passed).

Pointer (pre-refactor, kept for history):
- `src/application/services/swing_tuning_review_journal.py:19` through `src/application/services/swing_tuning_review_journal.py:163` defined DTOs and `to_dict()` serialization.
- `src/application/services/swing_tuning_review_journal.py:165` through `src/application/services/swing_tuning_review_journal.py:303` performed journal append/review, latest comparison, and post-apply measurement.
- `src/application/services/swing_tuning_review_journal.py:306` through `src/application/services/swing_tuning_review_journal.py:475` parsed raw records, summarized apply logs, and computed metric deltas.

Rationale:
- The filename says journal, but the file also owns report DTOs, comparison policy, post-apply attribution, and raw dict parsing.
- JSON contracts are embedded beside persistence orchestration, increasing risk when changing display/API shape.
- AI agents must scan the full file to answer simple questions like “where is metric delta computed?”

Recommendation:
- Move DTOs and `to_dict()` methods to `src/application/dto/swing_tuning_review.py`.
- Move raw record summarization helpers to `src/application/services/swing_tuning_review_summary.py`.
- Move latest-review comparison to `src/application/services/swing_tuning_review_comparison.py`.
- Move post-apply measurement to `src/application/services/swing_tuning_post_apply_measurement.py`.
- Keep `SwingTuningReviewJournal` as the persistence-facing facade: append, read/sort records, delegate comparison and measurement.

Guardrails:
- Preserve all JSON keys, status strings, note strings, and metric names.
- Preserve current sorting semantics by string timestamp unless a behavior task explicitly changes it.
- Keep `SwingTuningReviewStore` as the only persistence port dependency.

Risk to maintain:
- Report contract changes are currently easy to mix with storage behavior changes.
- The next tuning-report feature will likely grow this file instead of composing a targeted service.

Edge cases to watch:
- Missing or malformed review records currently produce `None` fields rather than exceptions; keep tolerant parsing.
- `measure_latest_apply()` depends on before/after timestamp ordering; preserve exact boundary behavior.

### 5. Medium: `src/adapters/cli/fetch_broker_commands.py` is still a broad command cluster

Status: `RESOLVED`

Resolution:
- Split into `fetch_broker_summary_commands.py` (`broker_fetch`), `fetch_broker_foreign_top_commands.py` (`broker_top_foreign`), `fetch_broker_history_commands.py` (`broker_history`), and `fetch_broker_import_commands.py` (`broker_import`).
- Extracted shared adapter-only helpers into `fetch_broker_error_display.py` (provider/auth/value/unexpected error rendering) and `fetch_broker_market_status_display.py` (market-status echo).
- `fetch_broker_commands.py` is now a router/import facade only (`__all__` re-export of the four command functions); it holds no workflow factory imports, no `load_app_config`, and no Typer command bodies.
- `fetch_commands.py` now imports command functions from the canonical contextual modules rather than the facade.
- Command names, option names, output wording, and exit codes are unchanged. Verified via `ruff check`, `pytest tests/adapters/cli/test_fetch_broker_commands.py`, `pytest tests/integration/test_command_smoke_matrix.py`, and `pytest tests/architecture`.
- Fixed a pre-existing bug surfaced during split review: `broker_fetch`'s success line used the unresolved `provider_name` argument instead of `resolved_provider`, printing `Loaded N days from None` when `--provider` was omitted. Now uses `resolved_provider`; regression test `test_broker_fetch_default_provider_shown_when_no_provider_flag` covers the no-flag path.

Pointer:
- `src/adapters/cli/fetch_broker_commands.py:47` through `src/adapters/cli/fetch_broker_commands.py:56` hold config-derived defaults.
- `src/adapters/cli/fetch_broker_commands.py:59` through `src/adapters/cli/fetch_broker_commands.py:176` implement broker summary fetch.
- `src/adapters/cli/fetch_broker_commands.py:178` through `src/adapters/cli/fetch_broker_commands.py:280` implement foreign-top scan.
- `src/adapters/cli/fetch_broker_commands.py:282` through `src/adapters/cli/fetch_broker_commands.py:349` implement broker history.
- `src/adapters/cli/fetch_broker_commands.py:351` through `src/adapters/cli/fetch_broker_commands.py:500` implement CSV import.
- `src/adapters/cli/fetch_broker_commands.py:128` and `src/adapters/cli/fetch_broker_commands.py:218` import market-status display helpers inside commands.
- Error mapping for provider/auth/general failures is repeated across fetch/top/history paths.

Rationale:
- The command file is adapter code, but it now owns four independently searchable command surfaces plus repeated status/error rendering policy.
- Existing application workflows are already extracted; the remaining problem is adapter discoverability and repeated command plumbing.
- A future agent looking for broker import behavior must scan unrelated broker fetch/top/history command logic.

Recommendation:
- Split command implementations into contextual modules:
  - `fetch_broker_summary_commands.py`
  - `fetch_broker_foreign_top_commands.py`
  - `fetch_broker_history_commands.py`
  - `fetch_broker_import_commands.py`
- Keep a small router module if Typer registration needs a single import path.
- Extract shared adapter-only helpers for provider validation, market-status echo, and broker provider error rendering.
- Resolve config defaults through the config cleanup from finding 1; do not keep module-level `APP_CFG` defaults in the split files.

Guardrails:
- Preserve public Typer command names, option names, default behavior, exit codes, and output wording unless a test explicitly approves a wording change.
- Do not move Typer objects or echo rendering into application use cases.
- Do not collapse import behavior into fetch behavior; CSV import has a separate responsibility and should stay separately named.

Risk to maintain:
- Repeated auth/error handling will drift between broker fetch commands.
- Adding another broker command will make this file a second command router instead of a readable adapter.

Edge cases to watch:
- Stockbit auth failures currently print login guidance; preserve that exact user-facing path.
- `--preview`, `--on-error report`, and mapping-file errors in CSV import must stay isolated from live provider fetch errors.

## Non-Findings From This Pass

- `src/adapters/cli/screen_accum_single_display.py`, `src/adapters/cli/screen_pre_open_display.py`, and `src/adapters/cli/analyze_swing_overview_display.py` are large, but currently read as display-only modules. Do not split them unless a table/panel becomes independently reusable or the filename stops exposing the rendered surface.
- `src/application/use_case/evaluate_swing_setup_use_case.py` is sizable, but it is still a cohesive setup evaluator. Extract setup config DTOs only if they become shared outside this use case.
- No fresh application-to-infrastructure import violation was found under `src/application` or `src/domain`; the current boundary scan only found architecture-test strings.
- No fresh test finding is opened in this pass. Large integration tests exist, but this audit did not find a current test fixture masking an architecture violation.

## Code Convention For Future Agents

- Runtime config must be explicit. Do not use import-time loaded config objects for CLI defaults, provider defaults, or composition defaults.
- Multi-provider adapters must split provider transport, prompt/template policy, response parsing, and orchestration.
- Evidence assembly must be composable by evidence family. Shared data collection belongs in a data-loader collaborator, not repeated inside each evidence builder.
- Journal/store services should not own report comparison, attribution measurement, DTO serialization, and raw-record parsing in the same file.
- CLI command files above roughly 350 lines need a split unless they are pure routers or pure display. Split by public command responsibility first, then extract shared adapter-only error/status helpers.
