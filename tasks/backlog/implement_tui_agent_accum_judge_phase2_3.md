# Implement TUI Agent Phase 2.3 — Read-Only Accumulation Judge Tool

Status: `IMPLEMENTED` — verified on 2026-08-03

Source:

- [ADR-061](../../docs/adr/ADR-061-closed-read-tool-orchestration-for-context-agent.md)
- [`implement_tui_agent_read_tools_phase2.md`](implement_tui_agent_read_tools_phase2.md), Section 8.3

## 1. Task Metadata

- Task type: Feature / application read projection / infrastructure safety seam.
- Priority: Medium.
- Semantic classification: `NON_SEMANTIC` — the optional agent receives the
  existing deterministic single-ticker accumulation judgment through the same
  request builder, workflow, policy, and bounded `tui_agent.accum_judge.v1`
  projection. No scoring, Action, evidence authority, compatibility identity,
  persistence, observation, label, tuning, or promotion behavior changes.
- AI usage: optional, non-authoritative, and bypassable.
- Chosen decision: implement and register only `judge_accumulation_ticker` in
  addition to the completed Phase 2.1–2.2 tools.

## 2. Shared-Worktree Start Gate

Start from clean commit `d53fc25f`. Preserve unrelated changes and never run
destructive cleanup. Current workflow, request builder, composition roots, and
ADR-061 were re-vetted before activation.

## 3. Problem Statement

The closed registry cannot re-judge a ticker outside the currently visible
candidate. The canonical `RunAccumulationScreenWorkflowUseCase` does not record
observations, but its default screen composition records setup-phase memory
transitively and also constructs writable repositories, watchlist persistence,
and optional diagnostic/display callbacks. Merely sending `save_enabled=false`
does not prove the transitive no-write contract required for an agent tool.

## 4. Desired Outcome

The model may propose one canonical four-letter IDX ticker. Application policy
executes the existing single-ticker accumulation workflow using the exact shared
default request builder and a separately named read-only composition, then wraps
the existing `tui_agent.accum_judge.v1` projection and context reference in a
bounded typed result. No candidate is `UNAVAILABLE`; projection invariant
disagreement is `FAILED`; no raw exception details reach the model.

## 5. Non-Goals

- No scoring, signal, risk, setup, TradeSetup, threshold, or request-default change.
- No fetch, refresh, browser/API call, retry, CLI invocation, rendered-output parsing,
  arbitrary SQL, repository exposure, or generic analysis tool.
- No observation, setup-phase ledger, watchlist, cache, journal, snapshot, audit,
  label, corpus, access-time, or schema write.
- No diagnostic `--full` branches, display-only MCE evaluation, strategy overlay,
  save, multi-window run, provider date, or provider-supplied universe/default.
- No Telegram, Hermes, OpenClaw, broker-desk, or additional tool work.

## 6. Architecture Impact Assessment

- New dependency: No.
- Determinism affected: No canonical behavior; output is deterministic for the
  same local data, production config, request defaults, and effective session.
- Persistence affected: No runtime writes and no schema change.
- CLI behavior affected: No.
- Adapter-owned policy: No; adapters construct the canonical request and wire a
  narrow callable only.

```md
Layer plan:
- Domain: not touched.
- Application: canonical argument/result DTOs, bounded projection, status/error policy,
  and tool service around a narrow canonical-workflow callable.
- Infrastructure: schema-initialization-free/query-only repository and provider
  composition; closed-registry registration of the approved application tool.
- Adapter: shared request-builder runner and TUI dependency wiring only.
```

## 7. Exact Contracts and Invariants

- Argument schema: `agent_tool.accum_judge.args.v1`, exactly `ticker: str`.
- Canonical ticker: exact uppercase `[A-Z]{4}`; whitespace, lowercase, `.JK`,
  punctuation, benchmarks, warrants, and free-form values are rejected.
- Result schema: `agent_tool.accum_judge.result.v1`.
- Result data contains only `schema_id` and the frozen existing
  `AgentAccumulationContext` (`tui_agent.accum_judge.v1`, including its
  deterministic `context_reference`).
- Request is built only with `build_default_screen_accum_request`, one ticker,
  and the configured TUI analysis universe. No defaults are duplicated.
- Authority is `RunAccumulationScreenWorkflowUseCase`; exactly one projected
  candidate matching the requested ticker is required.
- Timeout: 12 seconds. Maximum serialized result: 32 KiB.
- Success may carry canonical workflow/context warnings. Zero candidates or a
  context missing required canonical branches is `UNAVAILABLE`. Multiple or
  mismatched candidates and ticker/snapshot invariant disagreement are `FAILED`.
- Provenance source is `accumulation-screen-read-only`; source reference is the
  bounded context reference. Result reference remains the Phase 2 canonical
  envelope hash.
- Registered composition requires an existing DB and explicitly uses:
  schema initialization disabled for market/broker/macro/provider caches;
  no learning-observation repository; a query-only setup-phase repository whose
  write method fails closed; no watchlist saver; no display-MCE evaluator; no
  diagnostic collector; no API client; no refresh or persistence callback.
- Normal CLI/TUI composition defaults remain writable where their existing
  explicit product workflows require it.

## 8. Exact File Boundary

New files:

- `src/application/services/agent_accumulation_judge_tool.py`
- `tests/application/services/test_agent_accumulation_judge_tool.py`
- `tests/infrastructure/composition/test_agent_accumulation_judge_composition.py`
- this task file

Existing files:

- `src/application/services/accumulation_candidate_signal_assessor.py`
- `src/application/services/accumulation_screen_factory.py`
- `src/application/use_case/accumulation_screen_use_case.py`
- `src/application/use_case/run_accumulation_screen_workflow_use_case.py`
- `src/infrastructure/browser/stockbit_provider_bundle.py`
- `src/infrastructure/composition/signal_engine_factory.py`
- `src/infrastructure/persistence/sqlite_setup_phase_ledger_repository.py`
- `src/adapters/composition/stock_analysis_workflow_dependencies.py`
- `src/adapters/composition/screen_accum_workflow_factory.py`
- `src/adapters/composition/screen_deps.py`
- `src/infrastructure/composition/agent_model.py`
- `src/adapters/tui/composition.py`
- `src/adapters/shared/multi_surface_inventory.py`
- relevant focused tests for the existing constructors, request parity, and
  agent composition, including the accumulation signal-assessor persistence seam
- parent Phase 2 epic completion record

Any domain contract, config value, provider query mapping, cache schema, CLI
rendering, or unrelated adapter file is out of scope.

## 9. AI Usage Declaration

AI proposes only the closed ticker argument and phrases commentary. Typed
validation, request defaults, deterministic judgment, missing-data semantics,
budgets, and registration remain application/composition policy. With AI or
tools disabled, every deterministic workflow continues unchanged.

## 10. Risk, Signal, and Evidence Authority Considerations

- SignalEngine, RiskEngine, TradeSetup, setup policy, Action, and risk profiles:
  unchanged; the tool projects their existing canonical output.
- Market context remains display-only and is omitted from the agent read-only
  composition because it never enters canonical screen scoring.
- Evidence authority, tuning eligibility, observations, labels, and
  ENTER/WATCH/AVOID producers: unchanged.

## 11. Data and Persistence

- Reads: existing local candles, broker/foreign flow, cached enrichment,
  macro-calendar rows, and prior setup-phase rows through existing ports.
- Writes: none at runtime; source, tests, and docs only during implementation.
- Schema: unchanged.
- Source swap: No. Existing repository/provider reads and field semantics are
  reused; only constructor schema initialization and write-capable collaborators
  are removed or replaced by explicit fail-closed read-only composition.

## 12. Negative Tests

- Noncanonical ticker and malformed/extra JSON cannot execute.
- Zero candidate is `UNAVAILABLE`; multiple/mismatched candidates and context
  invariant errors are `FAILED` without raw exception details.
- Projection cannot return raw workflow response/candidate, mappings, rendered
  adapter text, or more than 32 KiB.
- Missing DB cannot be created and the tool stays unregistered/fail-soft.
- Read-only construction and execution do not mutate DB bytes, schema version,
  or data version; setup ledger writes fail closed; API clients remain `None`.
- Request parity proves the exact shared builder/defaults and one-ticker shape.
- Existing normal constructor defaults and TUI `j` re-judge behavior remain green.

## 13. Acceptance Criteria

- [x] Exact contracts and negative tests above are implemented.
- [x] Registered set is exactly visible cockpit + ticker dashboard + accumulation
      judge when both read-only DB seams are available.
- [x] Canonical CLI/TUI request and workflow parity remain green.
- [x] No application import from infrastructure/adapter; adapter remains wiring-only.
- [x] Dedicated tests carry `pytest.mark.agent`.
- [x] Agent, parity, architecture, TUI, full suite, whole-repo Ruff, data-audit,
      DB immutability, and diff gates pass or existing warnings are recorded.
- [x] Implementation commit and completion evidence are recorded below.

## 14. Testing Expectations

```bash
.venv/bin/python -m pytest -m "agent and not tui" -q
.venv/bin/python -m pytest -m "agent and tui" -q
.venv/bin/python -m pytest tests/adapters/composition/test_screen_accum_request.py -q
.venv/bin/python -m pytest tests/adapters/shared/test_multi_surface_inventory.py -q
.venv/bin/python -m pytest tests/architecture/test_layer_boundaries.py -q
.venv/bin/python -m pytest -m tui -q
.venv/bin/python -m pytest -q
.venv/bin/ruff check src/ tests/
.venv/bin/ruff format --check src/ tests/
git diff --check
```

Run the three `saham audit data` commands required by the data-contract gate and
compare task-relevant findings to the Phase 2.2 baseline.

## 15. Documentation Impact

Update the parent Phase 2 epic. No README or config change is required; the
existing feature flags and user interactions remain unchanged.

## 16. Agent Execution Instructions

Stop rather than accepting constructor DDL, a write-capable registered seam,
duplicated request defaults/scoring, raw workflow transport, policy in the TUI
or infrastructure, or activation of another tool.

## 17. Completion Record

- Base commit: `d53fc25f`
- Implemented date: 2026-08-03
- Implementation commit: `a768f963`
- Verification:
  - `pytest -m "agent and not tui" -q`: 104 passed
  - `pytest -m "agent and tui" -q`: 4 passed
  - focused application/composition/parity/architecture checks: passed
  - `pytest -m tui -q`: 56 passed, 1 skipped
  - `pytest -q`: 6198 passed, 1 skipped
  - `ruff check src/ tests/`: passed
  - `ruff format --check src/ tests/`: passed
  - `git diff --check`: passed
- Transitive no-write proof:
  - construction and an execution attempt left temporary DB bytes,
    `schema_version`, and `data_version` unchanged;
  - the registered graph has no learning repository, no watchlist saver, no
    MCE/diagnostic callback, no API client, schema initialization disabled,
    query-only setup-phase history, and `record_setup_phase=false`;
  - live DB SHA-256 remained
    `7f2450968b3ceea8ad37f502a839d7b47f344927ec6aa9e190c80b1e0c4a8a30`
    before and after construction/execution.
- Live BBCA result: the canonical workflow returned one candidate, then the
  approved projection failed closed with `ACCUMULATION_JUDGMENT_INVARIANT`:
  Signal/TradeSetup/Accum were dated 2026-08-03 while Risk was dated
  2026-07-31. This is the required ADR-061 behavior; the agent path did not
  reinterpret or pin a different canonical date.
- Data-contract audit gate (all commands exit 0):
  - manifest: zero warnings; DB identity above;
  - source contracts: `WARN`, 62 warnings and 1 information finding, matching
    the Phase 2.2 optional-field coverage baseline;
  - reconciliation: `WARN`, 5 warnings and 3 information findings, all
    pre-existing partial-coverage/identity findings and unrelated to this
    read-only composition.
