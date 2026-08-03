# Implement TUI Agent Phase 2.2 — Cache-Only Ticker Dashboard Tool

Status: `IMPLEMENTED` — verified on 2026-08-02

Source:

- [ADR-061](../../docs/adr/ADR-061-closed-read-tool-orchestration-for-context-agent.md)
- [`implement_tui_agent_read_tools_phase2.md`](implement_tui_agent_read_tools_phase2.md), Section 8.2

## 1. Task Metadata

- Task type: Feature / application read projection / infrastructure safety seam.
- Priority: Medium.
- Semantic classification: `NON_SEMANTIC` — optional commentary receives a
  bounded projection of existing local-cache dashboard output; no scoring,
  Action, evidence authority, persistence meaning, observation, label, tuning,
  or promotion behavior changes.
- AI usage: optional, non-authoritative, and bypassable.
- Chosen decision: implement and register only `get_ticker_dashboard` in
  addition to the completed visible-result tool. **Implement this option only.**

## 2. Shared-Worktree Start Gate

Start from clean commit `cc57d081`. Preserve unrelated changes and do not run
destructive cleanup. Current code, tests, CLI/TUI composition, and ADR-061 were
re-vetted before activation.

## 3. Problem Statement

The closed registry has no way to read another ticker's existing dashboard
cache. The shared `GetTickerDashboardUseCase` is network-free, but its current
infrastructure composition runs schema-initialization DDL while constructing
cache repositories/providers. Registering it unchanged would violate Phase 2's
transitive no-write contract. Its raw dashboard DTO also contains broad `Any`
branches and is not an approved agent projection.

## 4. Desired Outcome

The model may propose one canonical four-letter IDX ticker. Application policy
executes the existing full `GetTickerDashboardUseCase` over an explicitly
schema-initialization-free local composition and returns a bounded typed summary.
Missing caches remain missing, partial caches return `PARTIAL`, wholly absent
data returns `UNAVAILABLE`, and no branch fetches, refreshes, neutral-fills, or
writes. The generic TUI trace renders this tool without new adapter workflow.

## 5. Non-Goals

- No other Phase 2 tool, provider, CLI, Telegram, Hermes, OpenClaw, or MCP work.
- No dashboard recomputation beyond the existing application use case.
- No API/browser call, fetch, refresh, retry, migration, schema creation,
  access-time write, persistence, or raw SQLite/repository exposure.
- No raw `TickerDashboard`, generic mapping, adapter JSON/text, contact/profile
  prose, raw sentiment text, unrestricted candles, or commands in tool data.
- No change to normal CLI/TUI dashboard schema initialization defaults.

## 6. Architecture Impact Assessment

- New dependency: No.
- Determinism affected: No canonical behavior; projection is deterministic for
  the same cache, configuration, ticker, and application-owned date.
- Persistence affected: No runtime write or schema change. Infrastructure gains
  an opt-out from existing constructor schema initialization; defaults stay on.
- CLI behavior affected: No.
- Adapter-owned policy: No.

```md
Layer plan:
- Domain: not touched.
- Application: canonical argument DTO, explicit bounded dashboard DTOs,
  projection/status policy, and tool service around GetTickerDashboardUseCase.
- Infrastructure: schema-initialization-free construction mode for the same
  cache adapters, named read-only dashboard composition, and agent registration.
- Adapter: pass the configured DB path at the TUI composition root only; the
  existing generic trace renders the result.
```

## 7. Exact Contracts and Invariants

- Argument schema: `agent_tool.ticker_dashboard.args.v1`, exactly `ticker: str`.
- Canonical ticker: exact uppercase `[A-Z]{4}`; whitespace, lowercase, `.JK`,
  punctuation, benchmarks, warrants, and free-form values are rejected.
- Result schema: `agent_tool.ticker_dashboard.result.v1`.
- Use case request: `GetTickerDashboardRequest(ticker=ticker, brief=False)`;
  no provider-supplied date/mode/limit.
- Timeout: 3 seconds. Maximum serialized result: 32 KiB.
- Data contains only: ticker/mode/as-of/today; typed freshness rows; explicit
  identity, price structure, fundamentals, forward estimates, analyst,
  earnings (maximum four), ownership, bandar, and foreign-flow window summaries;
  bounded counts/statuses for corporate action, insider, IEV, sentiment, profile,
  seasonality, and diagnostic sector-macro branches; missing/error branch keys.
- No raw exception message enters tool data. Warnings name unavailable/stale/
  error branches using stable application keys only.
- No usable projected branch → `UNAVAILABLE`; any missing/empty/stale/error
  branch → `PARTIAL`; otherwise `SUCCESS`.
- Provenance source is `ticker-dashboard-cache`, with dashboard as-of and ticker
  source reference. Result reference remains the Phase 2 canonical envelope hash.
- Normal infrastructure constructors keep schema initialization enabled. The
  agent-only composition requires an existing regular DB file, disables schema
  initialization for every transitive cache adapter, and never creates a DB.
- Tests prove the DB bytes/schema/data version are unchanged before/after
  construction and execution.

## 8. Exact File Boundary

New files:

- `src/application/services/agent_ticker_dashboard_tool.py`
- `tests/application/services/test_agent_ticker_dashboard_tool.py`
- `tests/infrastructure/composition/test_agent_ticker_dashboard_composition.py`
- this task file

Existing files:

- `src/infrastructure/browser/stockbit_base_provider.py`
- `src/infrastructure/browser/stockbit_sqlite_connection_provider.py`
- `src/infrastructure/persistence/sqlite_market_repository.py`
- `src/infrastructure/persistence/sqlite_broker_repository.py`
- `src/infrastructure/persistence/sqlite_corporate_action_calendar_repository.py`
- `src/infrastructure/persistence/sqlite_iev_repository.py`
- `src/infrastructure/persistence/sentiment_repository.py`
- `src/infrastructure/persistence/sqlite_macro_calendar_repository.py`
- `src/infrastructure/persistence/sqlite_ticker_dashboard_source.py`
- `src/infrastructure/composition/view_ticker_deps.py`
- `src/infrastructure/composition/agent_model.py`
- `src/adapters/tui/composition.py`
- `src/adapters/shared/multi_surface_inventory.py`
- `tests/adapters/shared/test_multi_surface_inventory.py`
- focused infrastructure/composition tests needed for constructor defaults
- Phase 2 epic completion record

Any domain, provider query mapping, cache schema, CLI rendering, or unrelated
adapter file is out of scope.

## 9. AI Usage Declaration

AI proposes only one closed ticker argument and phrases commentary. Typed
validation, cache execution, missing-data semantics, budgets, and registration
remain deterministic application/infrastructure policy. With AI or tools off,
the dashboard and all deterministic workflows behave exactly as before.

## 10. Risk, Signal, and Evidence Authority Considerations

- SignalEngine, RiskEngine, TradeSetup, setup policy, and Action: unchanged.
- Sector-macro remains diagnostic in this browse projection.
- Evidence authority, tuning eligibility, and ENTER/WATCH/AVOID producers:
  unchanged.

## 11. Data and Persistence

- Reads: existing local ticker cache tables through the same source/use case.
- Writes: none at runtime; source, tests, and docs only during implementation.
- Schema: unchanged.
- Source swap: No. The same repository/provider read methods and field semantics
  are reused; only constructor schema initialization is disabled.
- Baseline data audits on 2026-08-02: manifest `PASS`; source contracts and
  reconciliation complete with existing coverage/provenance warnings to be
  reported in the completion record. No canonical/PIT promotion claim is made.

## 12. Negative Tests

- Noncanonical ticker and malformed/extra JSON cannot execute.
- Empty cache is `UNAVAILABLE`; missing/stale/error branches are `PARTIAL`.
- No raw exception/path/query text appears in data or warnings.
- Projection never returns raw dashboard objects, mappings, rendered text, or
  more than four earnings records.
- Missing DB cannot be created and dashboard tool stays unregistered/fail-soft.
- Read-only composition does not mutate DB bytes, schema version, or data
  version; provider API clients remain `None`.
- Existing constructor defaults still initialize schemas for normal workflows.
- AI/tools disabled and absent DB preserve prior composition behavior.

## 13. Acceptance Criteria

- [x] Exact contracts and negative tests above are implemented.
- [x] Registered set is exactly visible cockpit + ticker dashboard when the DB
      seam is available; other tools remain absent.
- [x] Existing CLI/TUI dashboard composition and behavior remain green.
- [x] Application imports no infrastructure/adapter module.
- [x] Dedicated tests carry `pytest.mark.agent`.
- [x] Data audits, agent, TUI, parity, architecture, full suite, Ruff, and diff
      gates pass or pre-existing data warnings are explicitly recorded.
- [x] Implementation commit and verification are recorded below.

## 14. Testing Expectations

```bash
.venv/bin/python -m pytest -m "agent and not tui" -q
.venv/bin/python -m pytest -m "agent and tui" -q
.venv/bin/python -m pytest tests/application/use_case/test_get_ticker_dashboard_use_case.py -q
.venv/bin/python -m pytest tests/adapters/shared/test_multi_surface_inventory.py -q
.venv/bin/python -m pytest tests/architecture/test_layer_boundaries.py -q
.venv/bin/python -m pytest -m tui -q
.venv/bin/python -m pytest -q
.venv/bin/ruff check src/ tests/
.venv/bin/ruff format --check src/ tests/
git diff --check
```

Run the three `saham audit data` commands required by the data-contract gate and
compare their task-relevant status to the recorded baseline.

## 15. Documentation Impact

Update the parent Phase 2 epic. No README or config change is required; the
existing flags, command, and TUI navigation remain unchanged.

## 16. Agent Execution Instructions

Stop rather than accepting constructor DDL, widening the argument/result schema,
duplicating SQL queries, returning raw dashboard branches, moving policy into
TUI/infrastructure, or activating another tool.

## 17. Completion Record

- Base commit: `cc57d081`
- Implemented date: 2026-08-02
- Commit: `e964f48f`
- Verification:
  - `pytest -m "agent and not tui" -q`: 83 passed
  - `pytest -m "agent and tui" -q`: 4 passed
  - `pytest -m agent -q`: 87 passed
  - architecture + multi-surface inventory: 10 passed
  - focused dashboard/composition/persistence checks: passed
  - `pytest -m tui -q`: 56 passed, 1 skipped
  - `pytest -q`: 6176 passed, 1 skipped
  - `ruff check src/ tests/`: passed
  - `ruff format --check src/ tests/`: passed
  - `git diff --check`: passed
- Live DB proof:
  - BBCA full cache dashboard loaded as-of 2026-07-31 with zero panel errors.
  - DB SHA-256 remained
    `7f2450968b3ceea8ad37f502a839d7b47f344927ec6aa9e190c80b1e0c4a8a30`
    before and after construction/execution.
  - Agent projection was `PARTIAL`, 3981 bytes, with four honest branch warnings.
- Data-contract audit gate (all commands exit 0):
  - manifest: zero warnings; DB identity above.
  - source contracts: `WARN`, 62 warnings and 1 info finding, all pre-existing
    optional-field coverage findings.
  - reconciliation: `WARN`, 5 warnings and 3 info findings. Task-relevant
    existing findings are partial cross-source foreign-flow coverage, 22
    all-null forward-estimate cache rows, and current-cache-only ticker notation.
  - No source swap, canonical/PIT promotion claim, schema change, or audit
    regression was introduced. All-null forward estimates explicitly project as
    missing rather than neutral facts.
