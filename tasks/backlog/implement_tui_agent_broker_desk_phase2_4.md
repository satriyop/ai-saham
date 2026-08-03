# Implement TUI Agent Phase 2.4 — Cache-Only Broker Desk Tool

Status: `IMPLEMENTED` — verified on 2026-08-03

Source:

- [ADR-061](../../docs/adr/ADR-061-closed-read-tool-orchestration-for-context-agent.md)
- [`implement_tui_agent_read_tools_phase2.md`](implement_tui_agent_read_tools_phase2.md), Section 8.4

## 1. Task Metadata

- Task type: Feature / application read projection / infrastructure safety seam.
- Priority: Medium.
- Semantic classification: `NON_SEMANTIC` — optional commentary receives a
  bounded projection of existing local-cache broker desk use-case output; no
  scoring, Action, evidence authority, persistence meaning, observation, label,
  tuning, or promotion behavior changes.
- AI usage: optional, non-authoritative, and bypassable.
- Chosen decision: implement and register only `get_broker_desk` in addition to
  the completed Phase 2.1–2.3 tools. **Implement this option only.**

## 2. Shared-Worktree Start Gate

Start from clean commit `75a89881`. Preserve unrelated changes and do not run
destructive cleanup. Current desk use cases, composition roots, and ADR-061 were
re-vetted before activation.

## 3. Problem Statement

The closed registry has no way to read a tracked broker desk from local cache.
The six `ViewBrokerDesk*UseCase` entry points are network-free, but constructing
`SQLiteBrokerRepository` with default schema initialization can write DDL. Raw
use-case results also contain domain entities and unbounded history rows that
are not approved agent projections.

## 4. Desired Outcome

The model may propose one canonical two-letter IDX broker code and exactly one
named view (`SHOW | TOP_STOCKS | TOP_MATRIX | FLOW | CALENDAR | HISTORY`).
Application policy executes the matching existing use case over a
schema-initialization-free composition and returns a bounded typed summary.
Missing cache is `UNAVAILABLE`; truncated history / partial matrix windows are
`PARTIAL`; no scrape, fetch, generic widen, adapter text, or write occurs.

## 5. Non-Goals

- No other tool, provider, CLI, Telegram, Hermes, OpenClaw, or MCP work.
- No desk recomputation beyond existing application use cases.
- No API/browser call, fetch, refresh, retry, migration, schema creation,
  access-time write, persistence, or raw SQLite/repository exposure.
- No raw `BrokerDailyFlow` entity dump, generic mapping, adapter JSON/text, or
  commands in tool data.
- No change to normal CLI/TUI broker desk schema initialization defaults.

## 6. Architecture Impact Assessment

- New dependency: No.
- Determinism affected: No canonical behavior; projection is deterministic for
  the same cache, configuration, broker code, and view.
- Persistence affected: No runtime write or schema change. Infrastructure gains
  an opt-out composition; defaults stay on for normal CLI/TUI.
- CLI behavior affected: No.
- Adapter-owned policy: No.

```md
Layer plan:
- Domain: not touched.
- Application: canonical argument/result DTOs, projection/status policy, and
  BrokerDeskTool around ViewBrokerDesk*UseCase.
- Infrastructure: schema-initialization-free broker desk composition and
  closed-registry registration.
- Adapter: multi-surface inventory notes; TUI already passes db_path.
```

## 7. Exact Contracts and Invariants

- Argument schema: `agent_tool.broker_desk.args.v1` with exactly
  `broker_code: str` and `view: SHOW | TOP_STOCKS | TOP_MATRIX | FLOW | CALENDAR | HISTORY`.
- Canonical broker code: exact uppercase `[A-Z]{2}`; lowercase, whitespace, and
  free-form values are rejected before execution.
- Result schema: `agent_tool.broker_desk.result.v1`.
- One call → exactly one named view with production request defaults (no
  provider-supplied dates/limits/ticker pins).
- Timeout: 3 seconds. Maximum serialized result: 32 KiB.
- HISTORY projects newest-first rows with a 40-row display cap (same family as
  TUI history presentation); truncation is `PARTIAL` with a stable warning.
- TOP_MATRIX partial session windows are `PARTIAL` with a stable warning.
- No raw exception message enters tool data.
- Empty cache → `UNAVAILABLE`; otherwise `SUCCESS` or `PARTIAL`.
- Provenance source is `broker-desk-cache`, with as-of and
  `broker-desk:{code}:{view}:{as_of}` source reference.
- Agent-only composition requires an existing regular DB file and disables
  schema initialization.

## 8. Exact File Boundary

New files:

- `src/application/services/agent_broker_desk_tool.py`
- `src/infrastructure/composition/view_broker_deps.py`
- `tests/application/services/test_agent_broker_desk_tool.py`
- `tests/infrastructure/composition/test_agent_broker_desk_composition.py`
- this task file

Existing files:

- `src/infrastructure/composition/agent_model.py`
- `src/adapters/shared/multi_surface_inventory.py`
- `tests/infrastructure/composition/test_agent_model.py`
- `tests/adapters/shared/test_multi_surface_inventory.py`
- Phase 2 epic completion record

## 9. AI Usage Declaration

AI proposes only the closed broker_code + view arguments and phrases commentary.
Typed validation, cache execution, missing-data semantics, budgets, and
registration remain deterministic application/infrastructure policy.

## 10. Risk, Signal, and Evidence Authority Considerations

- SignalEngine, RiskEngine, TradeSetup, setup policy, and Action: unchanged.
- Evidence authority, tuning eligibility, and ENTER/WATCH/AVOID producers:
  unchanged.

## 11. Data and Persistence

- Reads: existing local `broker_daily_flow` through the same desk use cases.
- Writes: none at runtime.
- Schema: unchanged.

## 12. Negative Tests

- Noncanonical broker code / view cannot execute.
- Empty cache is `UNAVAILABLE`.
- Broken repository path fails without raw exception text.
- History truncation and partial matrix windows are honest `PARTIAL`.
- Missing DB cannot be created; tool registration stays fail-soft.
- Read-only composition does not mutate DB bytes, schema version, or data
  version.
- AI/tools disabled and absent DB preserve prior composition behavior.

## 13. Acceptance Criteria

- [x] Exact contracts and negative tests above are implemented.
- [x] Registered set includes `get_broker_desk` when the DB seam is available.
- [x] Existing CLI/TUI desk composition and behavior remain green.
- [x] Application imports no infrastructure/adapter module.
- [x] Dedicated tests carry `pytest.mark.agent`.
- [x] Agent suite, Ruff, and focused composition gates pass.
- [x] Implementation commit and verification are recorded below.

## 14. Testing Expectations

```bash
.venv/bin/python -m pytest -m agent -q
.venv/bin/python -m pytest tests/application/services/test_agent_broker_desk_tool.py -q
.venv/bin/python -m pytest tests/infrastructure/composition/test_agent_broker_desk_composition.py -q
.venv/bin/python -m pytest tests/infrastructure/composition/test_agent_model.py -q
.venv/bin/python -m pytest tests/adapters/shared/test_multi_surface_inventory.py -q
.venv/bin/python -m pytest tests/architecture/test_layer_boundaries.py -q
.venv/bin/ruff check src/ tests/
.venv/bin/ruff format --check src/ tests/
git diff --check
```

## 15. Documentation Impact

Update the parent Phase 2 epic. No README or config change is required.

## 16. Agent Execution Instructions

Stop rather than accepting constructor DDL, widening the argument/result schema
beyond the named views, returning raw entities/mappings/rendered text, moving
policy into TUI/infrastructure, or activating another tool.

## 17. Completion Record

- Base commit: `75a89881`
- Implemented date: 2026-08-03
- Commit: `813305b2`
- Verification:
  - `pytest -m agent -q`: 120 passed
  - focused broker desk tool/composition + agent_model + inventory: 32 passed
  - architecture layer boundaries: 4 passed
  - `ruff check src/ tests/`: passed
  - `ruff format --check src/ tests/`: passed
  - `git diff --check`: passed
