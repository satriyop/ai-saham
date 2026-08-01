# Parked — TUI Agent Phase 2 Read-Tool Orchestration

Status: `PARKED`

Activation trigger: Phase 1 is complete on a verified commit, its context and
failure contracts are re-vetted against current code, and a new/amending ADR
explicitly authorizes the exact read-tool closed set below.

Source:

- ADR-060
- `docs/roadmap/roadmap_tui_ai_agent_implementation.md`, Phase 2

## 1. Task Metadata

- Task type: Feature / architecture extension
- Priority: Medium after Phase 1
- Semantic classification: `NON_SEMANTIC` only if every tool remains a read-only
  projection of an existing application result and no canonical engine,
  evidence, Action, persistence, or configuration behavior changes.
- AI usage: optional, non-authoritative tool selection inside a deterministic
  execution envelope.
- Chosen decision: add a closed, typed read-tool registry after Phase 1. Do not
  expose generic commands or writes. Implement this option only.

## 2. Problem Statement

Phase 1 can explain only the full accumulation candidate already visible in the
Judge. It cannot answer a question requiring another explicitly named local
read without the operator navigating and resubmitting.

A free-form tool layer would create a second adapter/application path, invite
CLI scraping or direct SQLite access, and allow model output to choose its own
authority. Read tools therefore need stable schemas, shared use cases,
deterministic permission checks, bounded execution, and typed partial/failure
results before they are exposed.

## 3. Desired Outcome

The application orchestrator may execute an allowlisted read tool requested by
the model, return the typed result to the same model turn, and render a grounded
answer. Registration and execution permission remain deterministic application
policy; the model only proposes a call.

Initial closed set:

| Tool | Required shared authority | Side effect |
|---|---|---|
| `get_visible_cockpit_result` | Exact frozen visible-result reference | None; no recompute/read |
| `get_ticker_dashboard` | `GetTickerDashboardUseCase` | Cache-only read |
| `judge_accumulation_ticker` | Shared accumulation request builder and workflow | Local deterministic read/recompute; no persistence |
| `get_broker_desk` | Existing `ViewBrokerDesk*UseCase` contracts | Cache-only read |

Each tool must have a separate activated implementation subtask before the
phase epic can close.

## 4. Non-Goals

- No refresh/fetch or other network market-data tool.
- No paper, watchlist, preference, config, tuning, learning, or audit write.
- No arbitrary SQL, filesystem, browser, shell, Python, CLI, MCP, or HTTP tool.
- No `analyze_anything`, command string, CLI parser, or CLI-output scraping.
- No pre-open recomputation; visible frozen pre-open context requires its own
  present-only projection task.
- No model-selected provider fallback or authority escalation.
- No multi-turn memory; Phase 3 owns session continuity.

## 5. Hard Invariants

1. The registry is a closed application-owned mapping; model text cannot add,
   replace, or alter a tool descriptor.
2. Every tool calls the same application entry point and defaults used by its
   CLI/TUI sibling. Intentional presentation deltas remain inventoried.
3. Tools return typed data with status, freshness/as-of, warnings, provenance,
   and a stable result reference. They never return rendered CLI/TUI output.
4. A tool result is context, not new scoring/evidence authority.
5. Missing or failed reads remain explicit. No neutral fill, second query,
   reconstruction, or fallback substitution is allowed.
6. Invalid arguments, unknown tools, contract errors, timeouts, and duplicate
   calls cannot be reasoned around by the model.
7. Tool failure cannot alter or suppress an already available deterministic
   cockpit result.

## 6. Architecture Impact Assessment

```md
Layer plan:
- Domain: not touched
- Application: tool descriptors, registry, permission/budget policy, projections, orchestration
- Infrastructure: only existing repositories/providers reached through existing composition and ports
- Adapter: renders trace/status and supplies explicit current context; no tool policy
```

- New dependency: No by default.
- Determinism affected: No canonical behavior change.
- Persistence affected: No writes; existing cache reads only.
- CLI behavior affected: No.
- Multi-surface impact: Yes; every shared job must update/verify the durable
  inventory and parity tests.

## 7. Activation Checklist

Before changing runtime code:

- [ ] Phase 1 completion record is green on the exact current commit.
- [ ] Current `multi_surface_inventory.py`, application DTOs, composition roots,
      and live command contracts are re-vetted.
- [ ] A new/amending ADR locks the exact tool schemas, result references,
      budgets, timeouts, retry policy, and exception boundary.
- [ ] Each tool has a complete Task Template subtask with exact file boundaries.
- [ ] Read-only behavior is proven transitively, including constructors and
      repository initialization.
- [ ] Current shared-worktree ownership is clear.

## 8. Required Execution Contract

The activated ADR/tasks must lock:

- `AgentToolDefinition`: stable name, description, typed input schema, result
  schema version, `side_effect=NONE`, timeout, and required context.
- `AgentToolExecutionResult`: `SUCCESS | PARTIAL | FAILED | UNAVAILABLE`, data,
  warnings, errors, freshness, provenance, result reference, retryable flag,
  and `side_effect=NONE`.
- maximum calls per turn, maximum total time, maximum projection size, duplicate
  call behavior, and branch-stop rules;
- exact distinction between expected missing data and invariant/programmer
  errors;
- stable ordering and deterministic JSON projection;
- no retry by default; any safe retry must be explicitly approved per tool.

## 9. Negative Tests

- Unknown or model-invented tool names are rejected before execution.
- Extra/malformed arguments are rejected rather than ignored.
- A registered read tool cannot call write methods transitively.
- Equivalent second reads are rejected when an exact visible/reference result
  is required.
- Tool data containing instruction-like text cannot authorize another call.
- Duplicate calls do not bypass budgets.
- Partial results name missing branches and cannot render as complete.
- No tool result enters Signal/Risk/MCE/TradeSetup, observations, labels,
  tuning, or promotion.

## 10. Acceptance Criteria

- [ ] All four tools have activated subtasks and typed contract tests.
- [ ] The tool registry is closed, deterministic, and application-owned.
- [ ] Shared workflows/defaults are reused; adapters contain no business policy.
- [ ] Read-only behavior and result lineage are independently proven.
- [ ] Failure, partial, timeout, malformed, injection, and budget cases are green.
- [ ] AI-disabled operation and existing CLI/TUI journeys remain unchanged.
- [ ] Focused tests, parity/inventory tests, architecture tests, TUI tests, full
      suite, Ruff gates, and `git diff --check` pass.

## 11. Do Not Interpret This As

- Do not activate all tools in one unreviewed implementation sweep.
- Do not implement convenience wrappers around CLI commands.
- Do not expose repositories merely because their methods are read-named.
- Do not treat local recomputation as persistence permission.
- Do not begin Phase 3 session memory as part of tool implementation.

## 12. Completion Record

- Activation ADR:
- Tool subtasks:
- Completed date:
- Commits:
- Verification:

