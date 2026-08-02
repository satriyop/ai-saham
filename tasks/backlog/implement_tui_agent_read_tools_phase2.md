# Implement TUI Agent Phase 2 — Allowlisted Read-Tool Orchestration

Status: `READY — EPIC (activation triggers met; runtime gated per §7 and §13)`

Activated on 2026-08-02 from `parked_tui_agent_read_tools_phase2.md`. The two
activation triggers are now satisfied:

1. **Phase 1 complete on a verified commit** —
   `implement_tui_agent_accum_judge_phase1.md` is `IMPLEMENTED` (2026-08-02),
   owned slices green.
2. **Binding ADR authorizes the exact closed read-tool set** —
   [ADR-061](../../docs/adr/ADR-061-closed-read-tool-orchestration-for-context-agent.md)
   accepted 2026-08-02, amends ADR-060, locks the four tool names, typed
   contracts, state machine, and budgets.

This is the **epic**. No tool ships from this file. Each of the four tools has
its own Task Template subtask (§8) that must independently prove projection,
lineage, composition, transitive read-only behavior, failure mapping, and tests
before that tool is registered. Activating the epic does **not** activate any
subtask.

Source of truth for all contracts is ADR-061. This file adds the implementation
ordering, subtask decomposition, and the gates that must close before runtime
code lands. Where this file and ADR-061 differ, **ADR-061 wins** — fix this file.

Source:

- [ADR-061](../../docs/adr/ADR-061-closed-read-tool-orchestration-for-context-agent.md) (binding contract authority)
- [ADR-060](../../docs/adr/ADR-060-read-only-tui-context-agent.md)
- [`docs/roadmap/roadmap_tui_ai_agent_implementation.md`](../../docs/roadmap/roadmap_tui_ai_agent_implementation.md), Phase 2

## 1. Task Metadata

- Task type: Feature / architecture extension (epic).
- Priority: Medium, after Phase 1.
- Semantic classification: `NON_SEMANTIC` — valid **only** while every tool
  returns a read-only projection of an existing deterministic result and nothing
  enters Signal, Risk, MCE, `TradeSetup`, evidence authority, sizing, execution,
  observations, labels, tuning, promotion, or persistence. Any exception voids
  `NON_SEMANTIC`, requires its own classification per `AGENT_QUICKSTART.md`, and
  a separate decision before that tool proceeds.
- AI usage: AI-assisted, optional, non-authoritative. The model only *proposes*
  a tool call; application policy alone decides whether the proposal is valid and
  executable. Gated by `ai.enabled` and the new `ai.tools_enabled`, both default
  `false`. With `ai.tools_enabled=false` the runtime is exactly Phase 1 zero-tool.
- Chosen decision: add a closed, typed, application-owned read-tool registry and
  a deterministic single-turn orchestrator. **Implement this option only.** Do
  not expose generic commands, repositories, or writes.

## 2. Shared-worktree start gate

Per-run ownership check is mandatory. Before any edit, run `git status --short`;
preserve unrelated changes and report overlap with the file boundary in the
active subtask. Never clean, restore, stash, or overwrite shared worktree
changes. At activation (2026-08-02) unrelated accum group-breadth work
(ADR-059/ADR-062, `config/*.yaml`, `ARCHITECTURE_DECISIONS.md`, group-breadth
backlog files) was dirty — it is out of scope and must remain untouched.

## 3. Problem Statement

Phase 1 can explain only the full accumulation candidate already visible in the
Judge. It cannot answer a question that requires another explicitly named local
read (open one ticker dashboard, read one broker desk, re-judge one ticker)
without the operator navigating and resubmitting.

A free-form tool layer would create a second adapter/application path, invite
CLI scraping or direct SQLite access, and let probabilistic model output widen
its own authority. Calling an existing use case is also not automatically safe:
construction may open a repository, and a read-named workflow may refresh,
cache, record an observation, update a ledger, or otherwise write transitively.
Read tools therefore need stable typed schemas, shared use cases, deterministic
permission and budget policy, bounded execution, typed partial/failure results,
and a proven transitive read-only property before any provider can see them.

## 4. Desired Outcome

Within one user turn, the application orchestrator may execute an allowlisted
read tool that the model proposed, return the typed result to the same turn, and
render grounded commentary with a compact tool trace. Registration and execution
permission remain deterministic application policy. The deterministic cockpit
result stays visible and authoritative; a tool result is context only.

Closed set (ADR-061 §Decision; each requires its own activated subtask):

| Tool | Required shared authority | Side effect |
|---|---|---|
| `get_visible_cockpit_result` | Exact adapter-supplied frozen visible-result reference | None; no recompute/repo/provider read |
| `get_ticker_dashboard` | `GetTickerDashboardUseCase` (same composition as `saham view ticker show`) | Cache-only read |
| `judge_accumulation_ticker` | Shared accum request builder + `RunAccumulationScreenWorkflowUseCase`, persistence/refresh seams explicitly disabled | Local deterministic re-judge; **no** persistence |
| `get_broker_desk` | Existing `ViewBrokerDesk*UseCase`; one named view per call | Cache-only read |

## 5. Non-Goals (Explicitly Out of Scope)

- No fetch/refresh, browser, arbitrary HTTP, SQL, filesystem, shell, Python,
  CLI, MCP, or generic command/`analyze_anything` tool.
- No paper, watchlist, preference, config, strategy, formula, tuning,
  observation, ledger, label, corpus, audit, or promotion write tool.
- No repository facade or broad `to_dict()` transport.
- No pre-open recomputation; visible frozen pre-open context is projected only
  through `get_visible_cockpit_result`.
- No parallel calls, retries, recursive tool loop, streaming tool execution,
  multi-turn session, transcript/audit persistence, or beta strict-mode
  dependency.
- No additional provider, model fallback, or Telegram transport authorization.
- No Phase 3 session continuity (owned by
  `parked_tui_agent_ephemeral_sessions_phase3.md`).

## 6. Architecture Impact Assessment (epic-level; ADR-061 §Layer ownership)

```md
Layer plan:
- Domain: not touched — knows nothing about agents or tools.
- Application: AgentToolName/Definition/ExecutionResult DTOs, closed
  AgentToolRegistry, AgentReadToolPort, permission + budget + validation policy,
  single-turn orchestrator state machine, canonical result-reference
  serialization, typed status mapping.
- Infrastructure: translate provider tool-call messages (DeepSeek: stable
  endpoint, non-thinking, tool_choice auto→none); wire already-approved
  read-only dependencies. Never decides which tools are allowed.
- Adapter (TUI): capture exact current-context lineage + registered-tool policy
  identity; dispatch in a worker; cancel/invalidate lineage; render an ordered
  tool trace separately from deterministic facts and commentary. Never executes
  a tool or chooses tool policy.
```

- New dependency: No by default (reuses existing provider adapter + use cases).
- Determinism affected: No canonical behavior change while `NON_SEMANTIC` holds.
- Persistence affected: No writes; existing cache reads only.
- CLI behavior affected: No.
- Adapter policy: No — orchestration, freshness, permission, and budget policy
  live in application; the TUI stays thin.
- Multi-surface impact: Yes — every reused shared job must keep
  `multi_surface_inventory.py` and parity tests green; the accum re-judge tool
  may require a narrow read-only composition seam without forking scoring.

## 7. Activation Checklist (must be green on the exact base commit before runtime code)

- [x] Phase 1 completion record is `IMPLEMENTED` (2026-08-02).
- [x] A binding ADR (ADR-061) locks tool schemas, result references, budgets,
      timeouts, retry policy, and the exception boundary.
- [x] Re-vet, on base `b449d9f7`, that current `multi_surface_inventory.py`,
      application DTOs, composition roots, and live CLI/TUI command contracts
      still match ADR-061's assumed entry points
      (`GetTickerDashboardUseCase`, `RunAccumulationScreenWorkflowUseCase` +
      `build_screen_accum_request`, `ViewBrokerDesk*UseCase`).
- [ ] Each of the four tools has a complete Task Template subtask with exact
      file boundaries (§8).
- [ ] Transitive read-only audits for every intended registration pass
      (ADR-061 §Transitive read-only proof).
- [ ] Shared-worktree ownership is clear.

## 8. Subtask decomposition (each is its own Task Template file before its code)

Implement in dependency order. **Do not activate all tools in one sweep.** The
registry/orchestrator foundation (8.0) must pass negative contract tests before
any tool adapter registers. An unfinished or unproven tool stays unregistered
and invisible (not advertised as unavailable).

### 8.0 Foundation — registry, orchestrator, budgets (prerequisite)

Status: `IMPLEMENTED` on 2026-08-02; verified in the local worktree, commit
pending. No production read tool is registered. Executable contract:
[`implement_tui_agent_read_tools_phase2_foundation.md`](implement_tui_agent_read_tools_phase2_foundation.md).

- Add frozen application DTOs from ADR-061 §Application contracts:
  `AgentToolName`, `AgentToolSideEffect=NONE`, `AgentToolDefinition`,
  `AgentModelToolCall`, `AgentToolExecutionStatus`, `AgentToolExecutionResult`,
  `AgentModelResponse(Kind)`, extended `AgentTurnStatus`.
- Add `AgentToolRegistry` (closed, application-owned; model text cannot add,
  replace, or alter a descriptor) and `AgentReadToolPort`.
- Add the deterministic single-turn state machine (ADR-061 §state machine):
  validate request/lineage → ≤1 provider call `tool_choice="auto"` → validate
  the entire proposed batch before executing → sequential execution in response
  order → exactly one final `tool_choice="none"` call → final response must be an
  answer (a second tool proposal fails the turn).
- Enforce the locked budgets (fail closed on any breach):

  | Limit | Value |
  |---|---:|
  | Provider calls / turn | 2 max |
  | Tool calls / turn | 2 max |
  | Parallel tool calls | 0 (sequential only) |
  | Retries (provider + tools) | 0 |
  | User question | 2,000 chars |
  | Final model output | 500 tokens |
  | Provider timeout | 10 s / call |
  | Total tool-execution budget | 15 s |
  | Total turn deadline | 35 s |
  | Total serialized tool results | 64 KiB |

- Canonical `result_reference` per ADR-061 §Result references
  (`sha256:<hex>` over the sorted, compact envelope excluding `result_reference`).
- Argument handling: provider `name`/`arguments_json` are untrusted proposals;
  resolve against the closed registry, strict-parse JSON, reject duplicate keys,
  reject unknown/extra fields, construct the tool-specific argument DTO, validate,
  then execute. **No generic `dict[str, Any]` execution entry point.**
- File boundary (subtask fills exact paths): `src/application/` agent DTOs/port/
  registry/orchestrator + `src/infrastructure/ai/` provider tool-call translation
  + `src/infrastructure/composition/` wiring; tests under
  `tests/application/`, `tests/infrastructure/ai/`, `tests/architecture/`.
- Config: add `ai.tools_enabled` (default `false`) as an independent rollback
  switch; tools are supplied only when `ai.enabled` **and** `ai.tools_enabled`
  are true, the provider capability is supported, and ≥1 approved tool is
  registered.

### 8.1 Tool — `get_visible_cockpit_result`

- Schemas: `agent_tool.visible_cockpit.args.v1` (`visible_result_reference: str`
  only) → `agent_tool.visible_cockpit.result.v1`.
- Execution: compare proposed reference to the adapter-captured reference and
  project that same object. No recompute/repo/filesystem/provider call. Missing,
  stale, or unequal reference → `UNAVAILABLE`; no reconstruction.
- Lock exact projected fields + canonical ordering in the subtask.

### 8.2 Tool — `get_ticker_dashboard`

- Schemas: `agent_tool.ticker_dashboard.args.v1` (`ticker: str`, canonical
  application form; suffixes/free-form/extra fields rejected) →
  `agent_tool.ticker_dashboard.result.v1`.
- Authority: `GetTickerDashboardUseCase`, same composition contract as
  `saham view ticker show` / TUI ticker view. Cache-only; missing branches →
  `PARTIAL`/`UNAVAILABLE`, never refresh/fetch/neutral-fill.

### 8.3 Tool — `judge_accumulation_ticker`

- Schemas: `agent_tool.accum_judge.args.v1` (`ticker: str`, canonical form) →
  `agent_tool.accum_judge.result.v1` wrapping the existing
  `tui_agent.accum_judge.v1` projection + context reference.
- Authority: shared accum request builder + `RunAccumulationScreenWorkflowUseCase`
  with the **same production defaults** as CLI/TUI single-ticker judgment.
- **Hard gate:** the registered composition must explicitly disable every
  persistence and refresh seam — no observation, setup-phase ledger, cache,
  journal, snapshot, audit, label, or access-time write. If the current workflow
  cannot provide and *prove* that mode without changing canonical judgment
  semantics, this tool stays inactive. No candidate → `UNAVAILABLE`; invariant
  disagreement → `FAILED`. This tool is the highest-risk registration; expect it
  to need a narrow explicit read-only composition seam.

### 8.4 Tool — `get_broker_desk`

- Schemas: `agent_tool.broker_desk.args.v1` (`broker_code: str` canonical IDX
  form + `view: SHOW | TOP_STOCKS | TOP_MATRIX | FLOW | CALENDAR | HISTORY`) →
  `agent_tool.broker_desk.result.v1`.
- Authority: matching existing `ViewBrokerDesk*UseCase`; one call → exactly one
  named view. Cache-only; no scrape/fetch/generic-widen/adapter text.

## 9. AI Usage Declaration

AI-assisted, optional, bypassable. AI is needed only to translate a natural
question into a *proposed* tool call and to phrase grounded commentary. When AI
is disabled or `ai.tools_enabled=false`, the cockpit is unchanged and no provider
call occurs. AI output is constrained by: closed registry, strict argument
validation, budgets, transitive read-only tools, and the rule that tool content
(including injection-like text) can never authorize or define a call.

## 10. Risk, Signal, and Evidence Authority Considerations

- Affected decision components: **none.** Deterministic `TradeSetup.action`
  remains the only Action. No tool result may enter `SignalEngine`, `RiskEngine`,
  `MarketContextEngine`, `AssessTradeSetupUseCase`, sizing, execution,
  observation selection, label generation, tuning, or evidence promotion.
- Does not change what can produce ENTER/WATCH/AVOID.
- Does not promote diagnostic evidence or change tuning eligibility.

## 11. Data & Persistence

- Reads: exact visible result (in-memory), ticker dashboard cache, accum
  workflow inputs (read-only mode), broker desk cache.
- Writes: **none.** Phase 2 persists nothing — not errors, arguments, raw
  provider payloads, results, transcript, or audit. Disabling tools needs no
  migration.
- Schema change: No.
- Operator trace contains only stable tool name, status, subject,
  as-of/reference, warnings, and safe error copy. Credentials, full prompts, raw
  arguments, unrestricted data, and model answers never enter logs/notifications.

## 12. Negative Tests (offline, recording fakes; mark modules `pytest.mark.agent`)

- Unknown or model-invented tool names rejected before execution.
- Extra/malformed arguments and duplicate JSON keys rejected, not ignored.
- A registered read tool cannot call write methods transitively (constructors,
  connection factories, lazy init, schema ensures, migrations, repair hooks).
- Equivalent second read rejected when an exact visible/reference result is
  required; stale/unequal reference → `UNAVAILABLE`, no reconstruction.
- Tool data containing instruction-like text cannot authorize another call.
- Duplicate calls (same name + canonical args) fail the batch; do not bypass
  budgets; over-budget batch fails whole turn in preflight, executing no tool.
- Provider proposing a second tool batch on the final call fails the turn.
- Partial results name every missing branch and cannot render as complete.
- Timeout/cancellation cannot lead to a delayed write; cancelled turn discards
  in-flight result and is `CANCELLED`.
- AI-disabled and `ai.tools_enabled=false` paths make zero provider calls and
  leave Phase 1 behavior identical.
- No tool result enters Signal/Risk/MCE/TradeSetup, observations, labels,
  tuning, or promotion.

## 13. Acceptance Criteria (epic close)

- [ ] All four tools have activated subtasks and typed contract tests; each was
      registered only after its transitive read-only audit passed.
- [ ] The tool registry is closed, deterministic, and application-owned; the
      runtime set is a subset of the four ADR-061 names.
- [ ] Shared workflows/defaults are reused; adapters contain no business policy;
      tools call application entry points, never CLI/TUI presenters or output.
- [ ] Read-only behavior and result lineage are independently proven (call-tree
      audit + tests: nonexistent paths stay nonexistent, no create/alter/insert/
      update/delete/migration, row/metadata counts unchanged).
- [ ] Failure, partial, timeout, malformed, injection, budget, stale-lineage, and
      no-retry cases are green.
- [ ] AI-disabled and tools-disabled operation and all existing CLI/TUI journeys
      are unchanged.
- [ ] `NON_SEMANTIC` still holds (no canonical/persistence/authority change).
- [ ] **Lint Gate** (`AGENT_QUICKSTART.md`): whole-repo `ruff check src/ tests/`
      and `ruff format --check src/ tests/` pass. No rule weakening or blanket
      ignores.

## 14. Testing Expectations & Verification

Run after the final edit on the exact commit claimed complete (earlier green
evidence is invalidated by any later edit). Provider calls mocked/recorded
offline; a live DeepSeek smoke test is opt-in and never the correctness gate.

```bash
.venv/bin/python -m pytest -m "agent and not tui"
.venv/bin/python -m pytest -m "agent and tui"
.venv/bin/python -m pytest -m agent
.venv/bin/python -m pytest tests/architecture/test_layer_boundaries.py -q
.venv/bin/python -m pytest tests/adapters/shared/test_multi_surface_inventory.py -q
.venv/bin/python -m pytest -m tui
.venv/bin/python -m pytest
ruff check src/ tests/
ruff format --check src/ tests/
git diff --check
```

## 15. Documentation Impact

- README/CLI docs: only if a user-visible `ai.tools_enabled` flag is documented.
- New config option to document: `ai.tools_enabled` (Yes).
- Limitations to state: read-only, single-turn, no persistence, DeepSeek-only,
  no fallback.
- Update `multi_surface_inventory.py` notes if a reused job gains a new surface.

## 16. Do Not Interpret This As

- Do not activate all four tools in one unreviewed implementation sweep.
- Do not implement convenience wrappers around CLI commands or parse CLI output.
- Do not expose repositories merely because their methods are read-named.
- Do not treat local recomputation as persistence permission.
- Do not feed any tool result back into canonical scoring, Action, sizing,
  persistence selection, or evidence authority.
- Do not add a generic `analyze_anything`/query tool "for later."
- Do not begin Phase 3 session memory or Phase 4 audit persistence here.
- Do not weaken any ADR-061 limit, schema, or the transitive read-only proof to
  land a tool. An unproven tool stays unregistered.

## 17. Completion Record

- Activation ADR: ADR-061 (accepted 2026-08-02).
- Base commit re-vet: `b449d9f7` plus the shared worktree; architecture and
  multi-surface inventory checks passed.
- Foundation (8.0) commit: pending; implementation and full verification green
  in the local worktree on 2026-08-02.
- Tool subtasks (8.1–8.4):
- Completed date:
- Commits:
- Verification:
