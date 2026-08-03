# ADR-061: Closed read-tool orchestration for the context agent

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted — architecture authorization only; runtime activation gated

**Date:** 2026-08-02

**Amends:** [ADR-060](ADR-060-read-only-tui-context-agent.md)

**Depends on:** [ADR-003](ADR-003-hexagonal-ports-adapters-architecture.md),
[ADR-013](ADR-013-ai-agent-governance.md),
[ADR-040](ADR-040-manual-dependency-injection-and-composition-roots.md),
[ADR-042](ADR-042-deterministic-champion-and-optional-model-challengers.md),
[ADR-045](ADR-045-view-browse-parity-cli-tui-json-table.md), and
[ADR-060](ADR-060-read-only-tui-context-agent.md)

**Implementation epic:**
[`tasks/backlog/implement_tui_agent_read_tools_phase2.md`](../../tasks/backlog/implement_tui_agent_read_tools_phase2.md)
(activated 2026-08-02)

## Context

ADR-060 authorizes one model call that explains the exact full accumulation
candidate already visible in the TUI Judge. It intentionally exposes no tools.
That slice proves the channel-neutral request/result seam, immutable context
projection, provider normalization, optional composition, and TUI stale-result
guard.

Some useful questions require another explicit local read, such as opening one
ticker dashboard or one broker desk. Letting the model call CLI commands,
repositories, SQL, arbitrary HTTP, or a generic analysis function would create
a second workflow path and let probabilistic output widen its own authority.
Calling an existing use case is also not automatically safe: construction may
open a repository, and a read-named workflow may refresh, cache, record an
observation, update a ledger, or otherwise write transitively.

Phase 2 therefore needs a binding closed registry, typed projections,
deterministic validation and budgets, explicit result lineage, and proof that
every registered composition is read-only before any provider can see the
tool. The model may propose a call; application policy alone decides whether
that proposal is valid and executable.

DeepSeek's official Tool Calls and Chat Completion contracts were re-verified
on 2026-08-02. The stable endpoint supports function tools, `tool_choice`, and
model-proposed JSON argument strings, and explicitly requires callers to
validate those arguments. Strict schema enforcement remains a beta endpoint,
so this decision does not depend on it:

- <https://api-docs.deepseek.com/guides/tool_calls>
- <https://api-docs.deepseek.com/api/create-chat-completion>

Provider capability is external and must be re-verified in the implementing
task. Provider acceptance never replaces application validation.

## Decision

### Authorization boundary

Authorize a channel-neutral application orchestrator to offer a closed set of
typed, read-only tools during one agent turn. This decision authorizes only the
maximum set and protocol below; it does not register or ship a tool by itself.

The initial closed set is:

1. `get_visible_cockpit_result`
2. `get_ticker_dashboard`
3. `judge_accumulation_ticker`
4. `get_broker_desk`

Each name remains absent from the runtime registry and provider request until
its own complete Task Template subtask proves its projection, lineage,
composition, transitive read-only behavior, failure mapping, and tests. An
inactive tool is invisible, not advertised as unavailable. Adding or renaming
a tool requires an ADR amendment; configuration and model output cannot extend
the set.

Phase 2 is `NON_SEMANTIC` only while every tool returns a read-only projection
of an existing deterministic result and nothing enters Signal, Risk, MCE,
`TradeSetup`, evidence authority, sizing, execution, observations, labels,
tuning, promotion, or persistence. Any exception requires its applicable
semantic classification and a separate decision before implementation.

### Layer ownership

```text
TUI / future authenticated channel adapter                 Adapter
  - user text and exact current-context handle
  - worker cancellation and stale-paint rejection
  - render deterministic trace separately from commentary
                         |
                         v
AgentTurnOrchestrator                                  Application
  - input validation and budgets
  - closed registry and permission checks
  - provider-call state machine
  - tool argument validation and sequential execution
  - typed result projections and turn status
             |                               |
             v                               v
AgentModelPort                      AgentReadToolPort implementations
             |                               |
             v                               v
provider adapter                  injected existing application use cases
Infrastructure                    Application/composition boundaries
```

- Domain remains untouched and knows nothing about agents or tools.
- Application owns the registry, schemas, validation, permissions, budgets,
  orchestration, status mapping, canonical serialization, and result lineage.
- Infrastructure translates provider tool-call messages and wires already
  approved read-only dependencies. It does not decide which tools are allowed.
- Adapters provide exact current context, dispatch work, cancel/invalidate
  lineage, and render. They never execute a tool or choose tool policy.
- Tools call application entry points directly. They never call CLI/TUI
  functions, presenters, formatters, or parse rendered output.

### Application contracts

All application DTOs are frozen dataclasses containing scalars, dates/enums,
other frozen DTOs, and tuples. Open-ended mutable mappings do not cross the
application model/tool ports. Provider JSON Schema and SDK dictionaries exist
only as infrastructure serialization details derived from the closed typed
definitions.

```text
AgentToolName =
  GET_VISIBLE_COCKPIT_RESULT |
  GET_TICKER_DASHBOARD |
  JUDGE_ACCUMULATION_TICKER |
  GET_BROKER_DESK

AgentToolSideEffect = NONE

AgentToolDefinition
  name: AgentToolName
  description: str
  argument_schema_id: str
  result_schema_id: str
  required_context: enum
  timeout_ms: int
  max_result_bytes: int
  side_effect: NONE

AgentModelToolCall
  call_id: str
  name: str
  arguments_json: str

AgentToolExecutionStatus = SUCCESS | PARTIAL | FAILED | UNAVAILABLE

AgentToolExecutionResult
  call_id: str
  name: AgentToolName
  status: AgentToolExecutionStatus
  data: one closed typed result projection | None
  warnings: tuple[str, ...]
  error_code: typed enum | None
  error_message: str | None
  freshness: typed facts | None
  provenance: typed facts
  source_reference: str | None
  result_reference: str
  retryable: bool
  side_effect: NONE

AgentModelResponseKind = ANSWER | TOOL_CALLS

AgentModelResponse
  kind: AgentModelResponseKind
  answer fields (valid only for ANSWER)
  tool_calls: tuple[AgentModelToolCall, ...] (valid only for TOOL_CALLS)

AgentTurnStatus =
  SUCCESS | PARTIAL | UNAVAILABLE | FAILED | CANCELLED
```

Contradictory states fail DTO construction. `ANSWER` requires non-empty answer
text and no tool calls. `TOOL_CALLS` requires one or two calls and no answer
text. A successful tool result requires typed data and no error. Failed or
unavailable results require no data and operator-safe error copy. `PARTIAL`
requires typed data plus explicit missing branches and warnings.

Provider-returned `name` and `arguments_json` are untrusted proposals. The
application resolves the name against the closed registry, parses strict JSON,
rejects duplicate keys, rejects unknown or extra fields, constructs the exact
tool-specific argument DTO, and runs its validation before any tool executes.
There is no generic `dict[str, Any]` execution entry point.

### Tool-specific v1 contracts

Every projection includes its schema ID, status, as-of/freshness where
applicable, warnings, provenance, source reference, and result reference. It
excludes secrets, unrestricted rows, arbitrary object representations, and
rendered adapter output.

#### `get_visible_cockpit_result`

- Argument schema: `agent_tool.visible_cockpit.args.v1` with exactly
  `visible_result_reference: str`.
- Result schema: `agent_tool.visible_cockpit.result.v1`.
- Required context: the adapter-supplied exact current result object; the
  application builds its bounded projection and reference before advertising
  the tool. The adapter never generates that reference.
- Execution: compare the proposed reference to the captured reference and
  project that same object. No recompute, repository, filesystem, or provider
  call.
- A missing, stale, or unequal reference is `UNAVAILABLE`; no equivalent
  result may be reconstructed.

#### `get_ticker_dashboard`

- Argument schema: `agent_tool.ticker_dashboard.args.v1` with exactly
  `ticker: str` in canonical application ticker form; suffixes, free-form
  queries, and extra fields are rejected.
- Result schema: `agent_tool.ticker_dashboard.result.v1`.
- Authority: `GetTickerDashboardUseCase` through the same composition contract
  as `saham view ticker show` and the TUI ticker view.
- Execution is cache-only. Missing cached branches produce `PARTIAL` or
  `UNAVAILABLE`; they never trigger refresh, fetch, or neutral fill.

#### `judge_accumulation_ticker`

- Argument schema: `agent_tool.accum_judge.args.v1` with exactly
  `ticker: str` in canonical application ticker form.
- Result schema: `agent_tool.accum_judge.result.v1`, wrapping the existing
  `tui_agent.accum_judge.v1` bounded projection and its context reference.
- Authority: the shared accumulation request builder and
  `RunAccumulationScreenWorkflowUseCase` with the same production defaults as
  CLI/TUI single-ticker judgment.
- The registered composition must explicitly disable every persistence and
  refresh seam. No observation, setup-phase ledger, cache, journal, snapshot,
  audit, label, or access-time write is allowed. If the current workflow cannot
  provide and prove that mode without changing canonical judgment semantics,
  this tool remains inactive.
- No candidate is `UNAVAILABLE`; invariant disagreement is `FAILED`.

#### `get_broker_desk`

- Argument schema: `agent_tool.broker_desk.args.v1` with exactly
  `broker_code: str` in canonical IDX broker-code form and
  `view: SHOW | TOP_STOCKS | TOP_MATRIX | FLOW | CALENDAR | HISTORY`.
- Result schema: `agent_tool.broker_desk.result.v1`.
- Authority: the matching existing `ViewBrokerDesk*UseCase`; one call requests
  exactly one named view.
- Execution is cache-only. It cannot scrape, fetch, widen to a generic desk
  query, or return adapter-formatted text.

The implementing subtasks must lock each projection's exact fields and
canonical ordering. This ADR does not authorize broad `to_dict()` transport.

### Result references and canonical serialization

Every execution result has a deterministic reference over the exact result
envelope excluding `result_reference` itself:

```text
json.dumps(
  payload,
  sort_keys=True,
  separators=(",", ":"),
  ensure_ascii=False,
  allow_nan=False,
)
UTF-8 -> SHA-256 -> "sha256:<lowercase hex>"
```

Dates and datetimes use ISO 8601, enums use `.value`, tuples serialize as
arrays, and absent optionals remain explicit `null`. `source_reference` points
to the exact originating visible result/context/application result when one
exists. `result_reference` identifies only this immutable projection; it does
not grant persistence authority or permission for a later call.

The orchestrator preserves ordered tool results in the final turn result.
Adapters display references but never generate or reinterpret them.

### Deterministic turn state machine and budgets

Phase 2 remains one user turn, not a persistent or multi-turn session:

1. Validate the user request and capture exact adapter context lineage.
2. Make at most one initial provider call with `tool_choice="auto"` and only
   currently registered definitions.
3. If the response is an answer, finish with zero tool calls.
4. If the response proposes tools, validate the entire proposed batch before
   executing anything.
5. Execute validated calls sequentially in response order.
6. Make exactly one final provider call with `tool_choice="none"`, supplying
   typed tool results and preserving the original authority policy.
7. The final provider response must be an answer. A second tool proposal is
   malformed and fails the turn without further execution.

Initial locked limits:

| Limit | Value |
|---|---:|
| Provider calls per turn | 2 maximum |
| Tool calls per turn | 2 maximum |
| Parallel tool calls | 0; sequential only |
| Retries | 0 for provider and tools |
| User question | 2,000 characters |
| Final model output | 500 tokens |
| Provider timeout | 10 seconds per call |
| Total tool-execution budget | 15 seconds |
| Total turn deadline | 35 seconds |
| Total serialized tool results | 64 KiB |

Per-tool limits:

| Tool | Timeout | Maximum result projection |
|---|---:|---:|
| `get_visible_cockpit_result` | 100 ms | 32 KiB |
| `get_ticker_dashboard` | 3 seconds | 32 KiB |
| `judge_accumulation_ticker` | 12 seconds | 32 KiB |
| `get_broker_desk` | 3 seconds | 32 KiB |

Timeout enforcement belongs to the application orchestrator around injected
calls; a provider SDK timeout is separately normalized by infrastructure.
Crossing any count, size, or deadline fails closed. Partial provider output
after an unknown timeout is not retried.

Calls are duplicates when tool name and canonical validated arguments match.
Duplicate calls, unknown names, malformed JSON, duplicate JSON object keys,
extra arguments, invalid values, too many calls, or an over-budget batch fail
the whole turn during preflight; no tool in that batch executes. Tool content
cannot request or authorize an additional call.

### Failure and partial-result semantics

- Expected absent cache/context is `UNAVAILABLE` for that tool.
- A typed result with explicitly named missing branches is `PARTIAL`.
- Tool timeout or an expected read failure is `FAILED` with
  `retryable=false`; Phase 2 never retries.
- Contract, invariant, projection, schema, or programmer errors are `FAILED`,
  never ordinary missing data.
- If all requested tools succeed and the final answer succeeds, the turn is
  `SUCCESS`.
- If at least one tool is `PARTIAL`, `FAILED`, or `UNAVAILABLE` but a safe final
  answer explains the exact result states, the turn is `PARTIAL`; it cannot be
  displayed as complete.
- Authentication/provider failure before tool execution leaves all
  deterministic UI results untouched and maps through the existing typed
  provider boundary.
- Adapter cancellation invalidates lineage immediately. No new tool starts
  after cancellation; a non-cancellable in-flight read may finish but its
  result is discarded. The turn is `CANCELLED` when the application boundary
  observes cancellation.

Tool errors, arguments, raw provider payloads, and results are not persisted or
logged in Phase 2. Operator-visible trace contains only stable tool name,
status, subject, as-of/reference, warnings, and safe error copy. Credentials,
full prompts, raw arguments, unrestricted data, and model answers never enter
status/sidebar notifications or logs.

### Transitive read-only proof

`side_effect=NONE` is a proven property, not a label inferred from a method
name. Before registration, each tool subtask must provide tests and a call-tree
audit demonstrating that:

- constructors perform no refresh, migration, repair, cache warming, journal
  creation, access-time update, or implicit write;
- every repository/provider method reachable on the tool path is read-only;
- no browser, market-data network provider, CLI, filesystem write, or shell is
  reachable;
- SQLite connections are opened in read-only mode when the existing repository
  contract permits it, or write methods are replaced by explicit failing test
  doubles and proven unreachable;
- the accumulation re-judge path disables observation, ledger, snapshot,
  journal, and other persistence callbacks explicitly;
- missing data returns typed absence instead of triggering a second source;
- cancellation and timeout cannot lead to a delayed write.

If any proof fails, the tool stays unregistered. The implementation may add a
narrow read-only application/composition seam, but it may not fork scoring or
copy policy into the agent layer.

### Configuration, provider, and rollback

- `ai.enabled` remains the global AI opt-in and defaults to `false`.
- Phase 2 adds `ai.tools_enabled`, default `false`, as an independent rollback
  switch. When false, Phase 1 remains exactly zero-tool.
- Tool definitions are supplied only when both flags are true, the provider
  capability is explicitly supported, and at least one approved tool is
  registered.
- Initial provider support remains DeepSeek. The first call uses non-thinking
  mode, the stable API endpoint, and `tool_choice="auto"`; the final call uses
  `tool_choice="none"`. The implementation must not depend on DeepSeek's beta
  strict-mode endpoint. Application validation remains mandatory even if a
  future provider offers schema enforcement.
- Unsupported tool capability is typed `UNAVAILABLE`; there is no provider,
  model, or tool fallback.
- Disabling tools requires no migration because Phase 2 has no persistence.

### Adapter and channel boundary

The TUI captures generation, stage, focused subject, exact source object or
result reference, and registered-tool policy identity before dispatch. A
newer submission, navigation, focus change, refresh, re-judge, or Escape
invalidates the turn. Completion requires the captured lineage and every
source reference still to match.

The adapter renders a compact ordered tool trace separately from deterministic
facts and model commentary. Tool results never overwrite the visible Judge,
ticker, broker, plan, or board state.

The orchestrator and registry are channel-neutral. A future Telegram adapter
may reuse them only after its own decision/task locks sender and chat
authentication, authorization, rate limits, delivery idempotency, transport,
and acquisition of exact application context. Telegram text cannot become a
result reference or tool permission. This ADR does not authorize Telegram
transport, sessions, persistence, or writes.

## Hard invariants

1. Deterministic `TradeSetup.action` remains the only Action.
2. Model output may propose a call but cannot register, authorize, configure,
   retry, sequence, or execute one.
3. The runtime registry is a subset of the four names in this ADR.
4. Every registered tool has `side_effect=NONE` proven transitively.
5. Tools return bounded typed projections, never adapter output, secrets,
   unrestricted rows, or arbitrary object serialization.
6. Tool results are context only and cannot enter deterministic workflows or
   persistence.
7. Missing/partial/stale data remains explicit and cannot trigger fallback.
8. Validation and budgets run before execution and fail closed.
9. At most two sequential tools and two provider calls occur in one turn.
10. Phase 2 creates no multi-turn memory, audit history, or write authority.
    Multi-turn process-local sessions are authorized only by
    [ADR-063](ADR-063-ephemeral-agent-session-and-context-budget.md), not by this
    ADR alone.

## Non-goals

- No fetch, refresh, browser, arbitrary HTTP, filesystem, SQL, shell, Python,
  CLI, MCP, or generic command tool.
- No paper, watchlist, preference, config, strategy, formula, tuning,
  observation, ledger, label, corpus, audit, promotion, or other write tool.
- No general `analyze_anything` or repository facade.
- No pre-open recomputation; visible pre-open context may only be projected by
  a separately activated visible-result tool.
- No parallel calls, retries, recursive tool loop, streaming tool execution,
  multi-turn session, transcript persistence, or beta strict-mode dependency.
- No additional provider or Telegram transport authorization.

## Consequences

### Positive

- Useful local reads can be reused without making model prose authoritative.
- Closed schemas, references, limits, and validation make tool behavior
  independently testable and channel-neutral.
- Separate tool activation prevents an unfinished or unsafe tool from being
  advertised merely because the epic exists.
- The independent tool flag provides immediate rollback to Phase 1.

### Costs

- The provider may need two calls for one user turn.
- Typed projections and transitive side-effect proofs add implementation work.
- The accumulation judgment workflow may need a narrow explicit read-only
  composition before it can be safely registered.
- Partial states and lineage increase TUI presentation and lifecycle testing.

## Rejected alternatives

- **Expose CLI commands:** rejected because rendered text and CLI orchestration
  are adapter contracts, not application tool contracts.
- **Give the model repository access:** rejected because read-named calls do
  not prove side-effect freedom and bypass use-case policy.
- **One generic cockpit/query tool:** rejected because open-ended arguments and
  results defeat the closed authority boundary.
- **Trust provider strict mode:** rejected because it is beta and cannot enforce
  application permissions, lineage, or transitive read-only behavior.
- **Retry timeouts:** rejected because completion state may be unknown and
  duplicate deterministic work still consumes budgets.
- **Implement all tools in one task:** rejected because each path needs an
  independent schema and side-effect audit.

## Implementation gates and status

This accepted ADR satisfies only the architectural-decision item in the Phase
2 activation checklist. Runtime work remains `PARKED` until all of the
following are complete on the exact implementation base commit:

1. Phase 1's repository-wide verification record is green.
2. The current multi-surface inventory and live TUI/CLI paths are reconciled.
3. Four complete tool subtasks lock exact fields and file boundaries.
4. Transitive read-only audits for all intended registrations pass.
5. Shared-worktree ownership is clear.

Implementation must add offline contract tests for invalid/extra/duplicate
arguments, unknown tools, injection-like data, budgets, timeout/cancellation,
partial results, canonical references, no retry, final-call no-tools behavior,
AI/tool-disabled behavior, stale lineage, and transitive no-write guarantees.
It must also pass focused agent tests, multi-surface parity/inventory tests,
architecture tests, TUI tests, the full suite, whole-repo Ruff gates, and
`git diff --check`.
