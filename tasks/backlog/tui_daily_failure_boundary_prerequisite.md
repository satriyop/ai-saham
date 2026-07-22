# TUI Prerequisite — Fail-Closed Daily Exception Boundaries

Status: `DONE`

Blocks: `tasks/backlog/tui_phase_0_inventory_and_contract.md`

## Task Metadata

- Task type: Bugfix / Refactor
- Priority: High
- Semantic classification: `NON_SEMANTIC`
- Chosen decision: narrow Daily and setup-lens exception handling so only the
  existing typed candle-data absence becomes a warning cell. Implement this
  option only.

## Problem Statement

`DailyBriefingUseCase` and `DailySetupLensImpactUseCase` catch broad
`Exception`. Contract, configuration, repository, invariant, and programmer
failures can therefore be converted into apparently valid warnings, missing
freshness, or setup-lens cells. That violates the fail-closed TUI contract and
prevents an outer boundary from retaining the original error class.

## Desired Outcome

- Universe, session/repository freshness, regime, accumulation, and outer
  setup-lens failures propagate unchanged.
- `DailySetupLensImpactUseCase` converts only
  `SwingAnalysisDataUnavailable` into one unavailable warning cell.
- Opening-snapshot file/JSON absence remains a warning through explicit
  filesystem/decoding exception types; malformed parsed structures propagate.
- Successful Daily and setup-lens outputs are unchanged.

## Non-Goals

- No TUI, adapter, infrastructure, config, schema, provider, persistence, score,
  risk, setup, evidence-authority, observation, label, or CLI rendering change.
- No generic application exception wrapper or compatibility fallback.
- No retry or provider-refresh behavior.

## Hard Invariants

- Empty/`None`/readiness values remain the ordinary absence contract.
- `SwingAnalysisDataUnavailable` is the only workflow exception translated to
  a setup-lens warning cell.
- `RuntimeError`, `TypeError`, invariant `ValueError`, repository/config errors,
  and malformed canonical DTOs propagate with identity and message unchanged.
- `TradeSetup` remains the only final swing action wording.

## Exact File Boundary

Expected changes:

- this task document;
- `src/application/use_case/daily_briefing_use_case.py`;
- `src/application/use_case/daily_setup_lens_impact_use_case.py`;
- `tests/application/use_case/test_daily_briefing.py`;
- `tests/application/use_case/test_daily_setup_lens_impact_use_case.py`;
- Phase 0/2 TUI task documents after verified completion.

No other production file is authorized.

## Architecture Impact

- Domain: not touched
- Application: narrow workflow exception policy
- Infrastructure: not touched
- Adapter: not touched
- New dependency: no
- Determinism impact: no
- Persistence/schema/config impact: no
- Adapter-owned policy: no

Layer plan:

```md
Layer plan:
- Domain: not touched
- Application: narrow Daily and setup-lens exception boundaries
- Infrastructure: not touched
- Adapter: not touched
```

## Exact Contract

`DailyBriefingUseCase.execute` must not catch dependency failures from:

- `load_universe`;
- `EffectiveMarketSessionResolver` or repository freshness reads;
- regime evaluation;
- accumulation execution/projection;
- `DailySetupLensImpactUseCase.execute`.

`DailyBriefingUseCase._opening_snapshot` may catch only `OSError`,
`UnicodeError`, and `json.JSONDecodeError` while reading/decoding the optional
snapshot. Its existing invalid `captured_at` warning remains. Parsed root/row
shape errors propagate.

`DailySetupLensImpactUseCase._evaluate_cell` catches only
`SwingAnalysisDataUnavailable`. Its warning is exactly:

```text
No local candle data for <TICKER>
```

All other exceptions propagate unchanged and abort the call.

## Required Tests

- Existing successful/empty/read-only tests remain green.
- Typed candle absence creates one warning cell and other setups continue.
- Generic `RuntimeError`, `TypeError`, and `ValueError` from a setup workflow
  propagate unchanged.
- Universe, freshness repository, regime, accumulation, and outer setup-lens
  exceptions propagate unchanged through `DailyBriefingUseCase`.
- Opening snapshot read/decode failures remain warnings; malformed decoded root
  propagates.

## Do Not Interpret This As

- Do not catch repository/config exceptions under a new broad base class.
- Do not convert `ValueError`/`TypeError` into missing data.
- Do not preserve the old generic-exception warning test.
- Do not change successful response fields, action wording, or authority policy.

## Acceptance Criteria

- [x] Broad catches are absent from the two scoped application boundaries.
- [x] Only typed candle absence becomes a setup-lens warning.
- [x] Negative propagation tests pass.
- [x] Existing focused tests pass offline.
- [x] Architecture boundary tests pass.
- [x] Full suite was executed in the project environment; scoped tests pass and
  three unrelated out-of-scope failures remain recorded below.
- [x] `git diff --check` passes.
- [x] Phase 0 failure matrix becomes binding and Phase 0 status becomes `DONE`.
- [x] Completion record is filled.

## Completion Record

- Completed date: 2026-07-22
- Implementation commit: not created; working-tree delivery
- Files changed: the two scoped application use cases, their two focused test
  files, this prerequisite, and the Phase 0/1/2 TUI task contracts
- Focused tests: `.venv/bin/pytest -q` coverage included all focused tests;
  direct system-interpreter run: `41 passed`
- Architecture tests: `4 passed`
- Full suite: `5682 passed, 3 failed` in 107.04s. The unrelated failures are
  two stale `_FakeScreenerConfig` fixtures in
  `test_analyze_accum_workflow_factory.py` and one existing label-generation
  expectation in `test_backfill_signal_observations_use_case.py`; none imports
  or exercises a changed file.
- `git diff --check`: passed
- Phase 0 result: failure matrix is enforceable; Phase 0 is `DONE`
- Deferred items: the three unrelated full-suite failures are outside this
  task's exact file boundary
