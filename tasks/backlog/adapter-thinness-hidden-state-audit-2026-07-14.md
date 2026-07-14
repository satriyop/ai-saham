# Adapter Thinness And Hidden State Audit - 2026-07-14

Scope: current code only. This audit intentionally ignores retired findings and focuses on remaining adapter thinness, hidden session/config wiring, service-locator patterns, and tests that can hide those patterns.

Baseline checked:
- `tests/architecture/test_layer_boundaries.py` has an empty `BASELINE_ALLOWLIST`.
- No production module imports `APP_CFG`.
- No `load_app_config()` call is executed at module import time.
- `src/application` and `src/domain` have no `src.infrastructure` import hits.

## Findings

### 1. High: `src/adapters/cli/fetch_stockbit_commands.py` is still a Stockbit diagnostic workflow cluster — DONE (2026-07-14)

Resolution:
- `fetch_stockbit_commands.py` is now a thin router that only builds `stockbit_app` and registers imported commands.
- Split into `fetch_stockbit_session_commands.py` (`login`, `status`, `browse`), `fetch_stockbit_spy_commands.py` (`spy`), and `fetch_stockbit_diagnostic_commands.py` (`test`, `fetch-top5`).
- Added `fetch_stockbit_diagnostic_factory.py` with `create_authenticated_stockbit_provider()`; `test` and `fetch-top5` no longer call `get_stockbit_session()` directly.
- Added `fetch_stockbit_playwright_guard.py` with `require_playwright_cli()` so session and spy command modules no longer share a private helper across modules.
- Commit `870dca0` (split) and `1a783d4` (playwright guard extraction).
- Command names, options, exit codes, output text, and `DEFAULT_SPY_OUTPUT` preserved; tests updated to patch new canonical module paths.

Pointer:
- `src/adapters/cli/fetch_stockbit_commands.py:39-66` owns login command and local infrastructure import.
- `src/adapters/cli/fetch_stockbit_commands.py:68-128` owns session status formatting.
- `src/adapters/cli/fetch_stockbit_commands.py:133-243` owns API traffic spy execution plus result diagnosis/display.
- `src/adapters/cli/fetch_stockbit_commands.py:245-327` owns live adapter smoke workflow, provider construction, diagnostics, and display.
- `src/adapters/cli/fetch_stockbit_commands.py:358-420` owns top-IEV-plus-orderbook workflow and table rendering.

Rationale:
- One adapter file mixes session management, browser traffic capture, live API smoke tests, provider construction, diagnosis text, and result rendering.
- The direct `get_stockbit_session()` calls at lines 270 and 379 hide session resolution inside command bodies instead of explicit command wiring.
- AI agents must read the whole file to answer narrow questions like "how is status rendered?" or "how is fetch-top5 executed?".

Recommendation:
- Split by command responsibility:
  - `fetch_stockbit_session_commands.py`: `login`, `status`, `browse`.
  - `fetch_stockbit_spy_commands.py`: `spy` command and spy result display.
  - `fetch_stockbit_diagnostic_commands.py`: `test` and `fetch-top5` command wrappers.
  - Optional display helpers: `fetch_stockbit_status_display.py`, `fetch_stockbit_spy_display.py`, `fetch_stockbit_diagnostic_display.py`.
- Move direct provider/session construction behind adapter-level factory functions. Keep these factories in adapter/infrastructure composition, not application, because these commands are operational diagnostics around a concrete provider.
- Keep Typer command names, options, exit codes, and output text stable unless tests explicitly approve a text change.

Guardrails:
- Do not move browser/session concrete code into application use cases.
- Do not introduce module-level sessions or cached API clients.
- Do not add architecture allowlist entries.
- Patch tests at the new lookup paths; do not create facade re-export tricks for stale patch strings.

Risk and edge cases:
- Local imports are currently used so tests can monkeypatch the provider facade. Update tests to patch the new canonical modules.
- Preserve "session expired" error behavior for unauthenticated sessions.
- Preserve the `DEFAULT_SPY_OUTPUT` path and spy JSON output contract.

### 2. High: `src/adapters/cli/strategy_lifecycle_commands.py` mixes templates, filesystem writes, validation/list workflow, and skill generation wiring — DONE (2026-07-14)

Resolution:
- `strategy_lifecycle_commands.py` is now a thin Typer adapter: option parsing, request DTO construction, use-case/factory calls, exception-to-message mapping, and display invocation only.
- Templates moved to `src/application/services/strategy_package_templates.py` (`STRATEGY_TEMPLATE`, `README_TEMPLATE`), unchanged content.
- Added `src/application/dto/strategy_package.py` (`CreateStrategyPackageRequest`/`Response`) and `src/application/use_case/create_strategy_package_use_case.py` (`CreateStrategyPackageUseCase`) owning name validation, target-directory resolution, force/overwrite decisions, and warning-only README-write semantics behind an injected `StrategyPackageWriter` port.
- Added `src/domain/ports/strategy_package_writer.py` (protocol) and `src/infrastructure/persistence/strategy_package_file_writer.py` (filesystem implementation).
- Added `src/adapters/cli/strategy_lifecycle_factory.py` (wires `StrategyLoader`, `CreateStrategyPackageUseCase`, `SkillGeneratorService`) and `src/adapters/cli/strategy_lifecycle_display.py` (Rich/Typer output for created-package summary, validation result, and strategy list table).
- `_generate_skill_md()` moved to `src/adapters/cli/strategy_skill_generation.py` as `generate_skill_md_for_strategy()`, called explicitly from `validate`.
- Commit `b37d4c0`.
- CLI command names, options, exit codes, output text, generated file contents, and error messages (including the permission-denied vs. generic directory-error vs. strategy-write-error distinction) preserved exactly; 54 tests pass including new use-case tests, adapter tests for the README-warning path and skill-generation with/without sidecar, and a boundary test asserting no direct infrastructure imports/symbols in the command module.

Pointer:
- `src/adapters/cli/strategy_lifecycle_commands.py:22-119` stores large strategy and README templates.
- `src/adapters/cli/strategy_lifecycle_commands.py:126-213` validates names, chooses paths, creates directories, writes files, and prints next steps.
- `src/adapters/cli/strategy_lifecycle_commands.py:216-363` wires strategy loader dependencies and renders validation/list output.
- `src/adapters/cli/strategy_lifecycle_commands.py:365-405` wires `SkillGeneratorService` and infrastructure skill readers/writers from a private CLI helper.

Rationale:
- The filename says lifecycle commands, but the file owns strategy package generation, validation orchestration, tabular display, and skill generation composition.
- Embedded templates make the command file noisy and hard to scan.
- `_generate_skill_md()` is hidden side-effect workflow triggered by `validate`; agents must inspect the bottom of the command file to discover it.

Recommendation:
- Extract pure templates to `src/application/services/strategy_package_templates.py` or `src/application/dto/strategy_package_templates.py`.
- Add `CreateStrategyPackageUseCase` for name validation and package creation decisions. File writes should happen through an injected writer port or an infrastructure writer wired by the adapter factory.
- Add `strategy_lifecycle_display.py` for validation/list output.
- Add `strategy_lifecycle_factory.py` to build `StrategyLoader` and `SkillGeneratorService` dependencies.
- Keep `strategy_lifecycle_commands.py` as Typer option parsing, request construction, use-case invocation, and error mapping only.

Guardrails:
- Do not change strategy YAML template content except for intentional tests.
- Do not silently stop generating `SKILL.md` after successful validation when sidecar annotations exist.
- Do not make strategy validation depend on current working directory beyond the existing `strategies/` behavior.

Risk and edge cases:
- Existing tests may assert template text and overwrite behavior; preserve exact file content and `--force` semantics.
- Failed README write currently warns but does not fail the command. Preserve that behavior unless explicitly changed.

### 3. High: `src/adapters/cli/trade_intraday_confirm_commands.py` still owns confirmation workflow orchestration and live provider setup

Pointer:
- `src/adapters/cli/trade_intraday_confirm_commands.py:50-213` parses opening JSON, reads sidecar files, decides manual/track/live resolution, creates Stockbit providers, resolves prices, confirms candidates, renders, and writes the confirmation sidecar.
- `src/adapters/cli/trade_intraday_confirm_commands.py:135-153` imports concrete Stockbit providers and calls `get_stockbit_session()` inside the command.
- `src/adapters/cli/trade_intraday_confirm_commands.py:187-208` maps config and sidecar-derived regime into `ConfirmIntradayOpenRequest`.
- `src/adapters/cli/trade_intraday_confirm_commands.py:210-213` writes the confirmation sidecar from the command.

Rationale:
- The command is a workflow coordinator, not only an adapter.
- Provider fallback policy, sidecar loading, opening-price resolution, confirmation request assembly, and persistence are interleaved with console output.
- The direct session/provider construction makes the command hard to test without patching concrete infrastructure paths.

Recommendation:
- Create `RunIntradayConfirmationWorkflowUseCase` in application.
- Request fields should include sidecar path, optional opening JSON mapping already parsed by adapter, optional track file path, output path, max stop, and a boolean for live auto-resolution.
- Result fields should include observations, confirmations, confirmed date, max stop, extras, warnings, and output path.
- Move sidecar reading, track-file resolution, regime loading, opening-price resolution, confirmation request assembly, and sidecar writing into the workflow/use-case layer through existing services and injected ports.
- Keep only JSON string parsing, Typer error mapping, provider factory wiring, and display calls in the CLI.

Guardrails:
- Do not move Typer or Rich into application.
- Do not let application import Stockbit infrastructure. Inject optional running-trade/order-book providers from the adapter factory.
- Preserve manual `--opening-json` and `--track-file` behavior exactly.
- Preserve the unauthenticated Stockbit message and the instruction to use `--opening-json` or `--track-file`.

Risk and edge cases:
- `--track-file` currently disables live auto-resolution. Preserve this exact decision.
- `max_stop <= 0` is adapter validation today; keep the same error message unless tests are updated.
- `load_pre_open_market_regime()` can return a warning and then force `RISK_OFF`; preserve this fallback.

### 4. Medium: `src/adapters/cli/analyze_sentiment_commands.py` still embeds large Rich display rendering in the command module

Pointer:
- `src/adapters/cli/analyze_sentiment_commands.py:73-101` wires sentiment providers, classifier, group mapping, repository, and executes `FetchSentimentUseCase`.
- `src/adapters/cli/analyze_sentiment_commands.py:128-212` executes audit and renders audit tables inline.
- `src/adapters/cli/analyze_sentiment_commands.py:215-367` contains full/brief sentiment display rendering helpers.

Rationale:
- Workflow is already mostly delegated to use cases, so this is not a boundary violation.
- The remaining problem is scanability: command parsing, dependency wiring, error mapping, audit display, and sentiment panels live in one file.
- Display-only changes force agents to read command wiring and vice versa.

Recommendation:
- Extract display helpers to `src/adapters/cli/analyze_sentiment_display.py`.
- Extract sentiment/audit dependency construction to `src/adapters/cli/analyze_sentiment_workflow_factory.py`.
- Keep `analyze_sentiment_commands.py` as option parsing, request construction, factory call, use-case execution, and display invocation.

Guardrails:
- Do not move Rich rendering into application/domain.
- Do not change provider/model/no-ai behavior.
- Preserve offline keyword-classifier behavior and existing network-error message mapping.

Risk and edge cases:
- `_display_sentiment_brief()` may be imported by other CLI modules. Keep a temporary import-compatible alias only if a direct call site exists, and remove it after updating call sites.
- Preserve warning rendering semantics: full display returns early on warning.

### 5. Low: `tests/adapters/cli/test_fetch_broker_commands.py` manually patches session factory global state

Pointer:
- `tests/adapters/cli/test_fetch_broker_commands.py:39-55` assigns `session_factory.get_stockbit_session = lambda: None` and restores it manually.

Rationale:
- The test has a `finally`, so it is not currently broken.
- It still normalizes manual global mutation around the same hidden session factory pattern this audit is trying to eliminate.
- Future edits can leak the patched function if the restore block is disturbed.

Recommendation:
- Replace manual assignment with `monkeypatch.setattr(session_factory, "get_stockbit_session", lambda: None)`.
- If finding 1 removes direct hidden session lookup from provider factories, update this test to inject a fake session provider instead.

Guardrails:
- Keep the assertion on the exact missing-session message.
- Do not introduce autouse fixtures for session state.

Risk and edge cases:
- None beyond patch lookup path changes after the Stockbit diagnostic split.

## Clean Areas Not Reopened

- `src/adapters/cli/screen_accum_commands.py` now delegates workflow execution to `RunAccumulationScreenWorkflowUseCase`; remaining JSON/table rendering is acceptable adapter work.
- `src/adapters/cli/fetch_market_commands.py` delegates refresh workflow to `FetchMarketCommandWorkflowUseCase`; its remaining callbacks are progress rendering, not business policy.
- Architecture allowlist is empty and should stay empty.
- Runtime `load_app_config()` in command functions is acceptable; import-time config loading is not.

## Code Convention For Future Agents

- CLI command modules may parse options, map errors, construct request DTOs, call factories/use cases, and render output. They must not own multi-step workflow policy.
- Concrete provider/session construction belongs in adapter factories or infrastructure composition roots, not inside command bodies.
- Operational diagnostics may stay outside application use cases when they are provider-specific, but they still need thin command files and named diagnostic runners.
- Large Rich/Typer display blocks belong in `*_display.py`; command modules should not exceed readability limits because rendering code is embedded.
- Tests must patch injected collaborators or canonical module lookup paths. Do not use facade re-exports or manual global mutation to preserve stale patch paths.
