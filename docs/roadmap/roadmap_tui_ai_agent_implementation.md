# TUI AI Agent Implementation Roadmap

**Status:** Active implementation roadmap — ADR-060/061/063 accepted; Phases 1–3
implemented (Phase 3 runtime `afb9d677`, 2026-08-03)

**Re-vetted against:** Phase 3 implementation through `afb9d677` on 2026-08-03

**Supersedes implementation sequencing in:**
[`roadmap_conversational_agent_architecture.md`](roadmap_conversational_agent_architecture.md)

**AI Research Cockpit + journey smoke + v1 UX locks (SSOT):**
[`tui_ai_agent_implementation_journey.md`](tui_ai_agent_implementation_journey.md)
(`/` = **AI Research Cockpit**; UX locks; golden pilot
`tests/adapters/tui/test_agent_stage_ux_golden.py`)

**Depends on:** ADR-002, ADR-003, ADR-013, ADR-014, ADR-040, ADR-042, ADR-045,
ADR-051, ADR-054, ADR-057, ADR-060, ADR-061, and ADR-063

## Operational tracking

| Phase | Backlog contract | Status / activation |
|---|---|---|
| 0 — Architecture and UX contract | ADR-060 + this roadmap | Complete for the first accumulation-Judge slice |
| 1 — One-turn visible-result assistant | [`implement_tui_agent_accum_judge_phase1.md`](../../tasks/backlog/implement_tui_agent_accum_judge_phase1.md) | Implemented; owned slices green, unrelated repository baseline exceptions recorded |
| 2 — Allowlisted read tools | [`implement_tui_agent_read_tools_phase2.md`](../../tasks/backlog/implement_tui_agent_read_tools_phase2.md) | Implemented 2026-08-03 (foundation + tools 8.1–8.4) |
| 3 — Ephemeral sessions | [`implement_tui_agent_ephemeral_sessions_phase3.md`](../../tasks/backlog/implement_tui_agent_ephemeral_sessions_phase3.md) | Implemented 2026-08-03 (ADR-063; `ai.session_enabled` default false) |
| L3 — Multi-round OUR tools | [`implement_ai_research_cockpit_multi_round_tools_l3.md`](../../tasks/backlog/implement_ai_research_cockpit_multi_round_tools_l3.md) | ADR-064 accepted 2026-08-03; runtime not started |
| L4 — External + RO data | [`implement_ai_research_cockpit_external_and_ro_data_l4.md`](../../tasks/backlog/implement_ai_research_cockpit_external_and_ro_data_l4.md) | ADR-065 accepted 2026-08-03; runtime not started (after L3) |
| 4 — Audit persistence | [`parked_tui_agent_audit_persistence_phase4.md`](../../tasks/backlog/parked_tui_agent_audit_persistence_phase4.md) | Parked; requires explicit persistence ADR |
| 5 — Consequential writes | [`parked_tui_agent_consequential_tools_phase5.md`](../../tasks/backlog/parked_tui_agent_consequential_tools_phase5.md) | Parked; writes remain separate from L4 research reads |

## Decision

Implement the first AI capability in the existing Textual prompt rail as an
**optional, read-only, context-aware assistant**. It may explain already
computed cockpit results and invoke a small allowlist of typed read-only
application tools. It cannot produce or change canonical Action, signal, risk,
`TradeSetup`, evidence authority, configuration, learning artifacts, or
persisted operator state.

Implement this option only for the first release. Do not combine it with CLI
passthrough, arbitrary commands, refresh, journal writes, configuration edits,
or external-agent/MCP exposure.

The deterministic application remains complete and usable when AI is disabled,
unconfigured, offline, slow, malformed, or unavailable.

## Why a new roadmap is needed

The cockpit is no longer hypothetical:

- ADR-051 Phases 0–5 are implemented.
- `CockpitApp` has an OpenCode-style prompt rail, `idle | agent | cli` display
  state, Textual worker support, generation-safe screen state, and injected
  loader seams.
- Prompt submission is intentionally non-functional today:
  `on_input_submitted()` clears the input and shows `not wired yet`.
- The composition root already shares real application workflows with CLI
  surfaces for accumulation, pre-open, ticker, broker, plan, fetch, and paper
  views.
- `multi_surface_inventory.py` is the anti-drift authority for dual-surface
  jobs.

What does **not** exist yet:

- a conversational application use case;
- a provider-neutral agent model port;
- a typed agent tool registry;
- deterministic permission and tool-execution policy;
- context projections and stable result references for agent use;
- a transcript/turn UI;
- agent audit records or session persistence;
- provider/model capability certification.

Existing AI modules are not a drop-in agent framework. `AIExplainer` and
`ExplainRiskUseCase` are narrow explanation contracts. Strategy/formula
translators are artifact-authoring flows. `ClaudeTickerResearcher` currently
contains a concrete provider client in the application layer and must not be
copied as the new architecture.

## Product contract for v1

The first useful flow is:

```text
operator focuses a cockpit result
        -> types a question in the prompt rail
        -> TUI captures explicit visible context
        -> application orchestrator may call allowlisted read tools
        -> infrastructure model returns grounded commentary
        -> TUI renders answer + source/freshness/warning footer
```

Representative questions:

- “Why is BBCA WATCH?”
- “What is missing from this setup?”
- “Summarize the current accumulation candidates.”
- “Explain this pre-open result in simple Indonesian.”
- “What changed between the visible signal, accumulation, and gate fields?”

The assistant may answer only from the explicit context and successful tool
results supplied to it. If the required current result is absent, stale,
limited, incompatible, or unavailable, it must say so rather than reconstruct
or guess it.

## Authority boundary

```text
Textual prompt/transcript adapter
              |
              v
ExplainAccumulationCandidateUseCase    Application
  - validate request/session context
  - choose permitted tool loop
  - enforce budgets and stop rules
  - preserve authoritative fields
  - compose grounded turn result
       |                         |
       v                         v
AgentModelPort              AgentToolRegistry
       |                         |
       v                         v
provider adapter            typed read-tool adapters
Infrastructure              -> existing application use cases

Deterministic champion result --------------------> canonical Action
Agent answer -------------------------------------> commentary only
```

The agent path is parallel commentary. No object returned by the agent path may
be accepted by `SignalEngine`, `RiskEngine`, `MarketContextEngine`,
`AssessTradeSetupUseCase`, sizing, execution, observation selection, label
generation, tuning, or evidence promotion.

## Exact ownership plan

### Domain

Not touched in v1. Conversation, model, and tool-loop contracts are application
concerns. Do not add LLM messages, provider types, chat sessions, or tool calls
to the pure domain.

### Application

Own the provider-neutral and UI-neutral behavior:

- `ExplainAccumulationCandidateUseCase`, channel-neutral and reusable only
  after another adapter independently acquires an exact permitted candidate;
- immutable request/result DTOs;
- `AgentModelPort` under `src/application/ports/`;
- typed tool descriptors and execution results;
- allowlist, permission, retry, timeout, tool-count, and context-budget policy;
- grounded response rules and partial/failure semantics;
- explicit context projections built from application DTOs.

Application code must not import Textual, provider SDKs, SQLite, CLI modules,
or infrastructure factories.

### Infrastructure

Own concrete model transport and optional persistence:

- provider adapters for the exact initially approved provider(s);
- credential resolution and provider/model identity;
- HTTP/SDK calls, normalized errors, timeouts, usage metadata, and redaction;
- later, a local conversation/audit repository implementing an application
  port.

Do not generalize the current risk-explainer interface into an agent by adding
tool calling to `AIExplainer`. Add a separate agent-model adapter contract.

### Adapter

The TUI owns only interaction and presentation:

- capture submitted text and the explicit current cockpit selection;
- dispatch the injected agent-turn callable in a Textual worker;
- render user turn, assistant turn, loading, cancel, partial, unavailable, and
  error states;
- ignore late results using the existing generation-safe lifecycle pattern;
- keep keyboard focus, scroll, and board state stable;
- never parse model text into commands or business actions.

The TUI composition root calls the channel-neutral infrastructure provider
factory and injects the application use case. It must not own tool policy,
fallback selection, freshness decisions, or grounding rules.

### Future channel reuse boundary

The application explanation seam is intentionally channel-neutral so a future
Telegram adapter can reuse it. That adapter is not part of this roadmap's Phase
1 implementation. Before calling `ExplainAccumulationCandidateUseCase`, it must
authenticate/allowlist the sender and obtain an exact full candidate through an
approved application workflow or allowlisted read tool. It may not reconstruct
context from chat text, ticker strings, board scalars, CLI output, or direct
SQLite/provider reads.

Telegram transport mode, delivery retries/idempotency, sender and chat identity,
rate limits, message-size formatting, sessions, audit, commands, and any write
authority require a separate roadmap/backlog and applicable ADR decisions.

## Required contracts before UI wiring

Names are proposed to remove implementation ambiguity; the ADR may refine names
without weakening their semantics.

```text
AgentTurnRequest
  session_id
  user_text
  locale
  cockpit_context
  prior_turn_references

CockpitContext
  active_stage
  focused_subject_kind
  focused_subject_id
  visible_result_reference
  visible_result_status
  visible_as_of

AgentToolExecutionResult
  tool_call_id
  tool_name
  status: SUCCESS | PARTIAL | FAILED | UNAVAILABLE
  data
  warnings
  freshness
  provenance
  result_reference
  retryable
  side_effect: NONE

AgentTurnResult
  status: SUCCESS | PARTIAL | FAILED | UNAVAILABLE | CANCELLED
  answer
  provider
  model
  model_response_id
  tool_results
  warnings
  usage
```

Rules:

1. `user_text` must be non-empty and bounded.
2. A result reference identifies the exact stored/in-memory application result;
   it is not a CLI command or a reconstructed database query.
3. `PARTIAL` names every missing branch. It is never silently rendered as a
   complete answer.
4. `UNAVAILABLE` is a normal typed state when AI is disabled, credentials are
   absent, or the selected model is not available.
5. Contract/invariant/programmer errors must propagate to a failed turn; they
   must not be converted into ordinary missing market data.
6. Tool output and model commentary remain separate fields through the render
   boundary.
7. Provider output cannot create a tool definition, raise its permission, or
   approve another call.

## V1 tool allowlist

Start narrower than the set of cockpit jobs. A tool is eligible only after its
application result has a compact projection with status, as-of/freshness,
warnings, and provenance.

| Tool | Existing authority to reuse | V1 behavior |
|---|---|---|
| `get_visible_cockpit_result` | Exact result already selected in the TUI | Read the frozen referenced result; no recompute or DB query. |
| `get_ticker_dashboard` | `GetTickerDashboardUseCase` | Cache-only read for one explicit ticker. |
| `judge_accumulation_ticker` | Shared accumulation request builder + `RunAccumulationScreenWorkflowUseCase` | Local single-ticker re-judge with the same defaults as CLI/TUI; label result as live/local vs snapshot/limited. |
| `get_broker_desk` | Existing `ViewBrokerDesk*UseCase` contracts | Read only the explicit desk and named job requested. |

Do not expose in v1:

- fetch/refresh tools;
- paper log or any journal write;
- watchlist/preference writes;
- strategy/formula/config/tuning authoring or application;
- learning observation/label/evaluation/promotion tools;
- arbitrary SQL, filesystem, network retrieval, shell, CLI execution, Python,
  MCP, or browser tools;
- a generic `analyze_anything` tool;
- a tool that returns current secrets, raw credentials, or unrestricted raw DB
  rows.

Pre-open should initially use `get_visible_cockpit_result` only. Do not make a
new pre-open network or recomputation path merely to answer a question about the
visible frozen snapshot.

## Context and grounding rules

- P0: system authority policy, allowed tools, and current user request are never
  summarized away.
- P1: selected ticker/desk, Action, Signal, Risk/Gate, as-of, freshness,
  warnings, limited/partial state, and provenance remain exact typed fields.
- P2: compact panel values may be projected with explicit field names.
- P3: verbose/raw rows remain outside model context behind a result reference.
- P4: older conversation may be summarized, but exact engine outputs are
  referenced rather than paraphrased as memory.
- Retrieved news, filings, provider text, and persisted free text are untrusted
  data. They cannot provide instructions, permissions, or tool arguments.
- The final answer must visibly distinguish deterministic result from agent
  commentary. Never label model prose `Action`, `Signal`, `Risk`, `Gate`,
  `TradeSetup`, or production evidence.

## Delivery phases

### Phase 0 — Architecture and UX contract

Outcome: the repository has a binding decision and testable TUI design before
agent code exists.

- Add a new ADR amending ADR-051’s “AI chat” non-goal for this bounded scope.
- Lock v1 as read-only and AI-optional.
- Lock the exact request/result/model/tool contracts and failure states.
- Add the agent transcript/loading/error frames to the TUI design source.
- Decide whether v1 is ephemeral-session only. Recommended: **ephemeral only**;
  no conversation or audit persistence until the data/redaction contract is
  separately approved.
- Inventory every v1 tool’s existing application entry point and exact context
  projection.

Close gate: ADR accepted; no unresolved authority, persistence, provider, or UI
ownership decisions; design covers `80x24` and `120x40`, AI-disabled, timeout,
partial-tool, and long-answer states.

### Phase 1 — One-turn visible-result assistant

Outcome: the prompt can explain the exact currently visible full accumulation
Judge result without an agent tool loop. This is intentionally one vertical
surface before context projection expands to pre-open, ticker, or broker views.

- Add immutable application DTOs and `AgentModelPort`.
- Build the visible-result projection and
  `ExplainAccumulationCandidateUseCase` in one-turn,
  zero-tool mode.
- Implement one provider adapter plus a deterministic fake adapter for tests.
- Wire an optional `agent_turn_runner` into `CockpitApp` through the composition
  root.
- Replace toast-only submission in `agent` mode with worker-backed transcript
  rendering. Keep `idle` behavior explicit; leave `cli` mode unwired or remove
  its selectable affordance until separately approved.
- Render provider/model, as-of, result status, and warnings with the answer.

Close gate: asking about the focused full accumulation Judge produces grounded
commentary; a limited Judge or wrong/no focus produces an honest unavailable
response; the cockpit remains unchanged when AI is disabled. Expansion to
pre-open, ticker, and broker contexts requires follow-up tasks after this
vertical slice passes.

### Phase 2 — Allowlisted read-tool orchestration

Outcome: the assistant may obtain missing read-only context through typed tools.

- Add `AgentToolRegistry` and the four v1 tool adapters.
- Add deterministic limits: maximum tool calls/turn, timeout budget, argument
  validation, no parallel duplicate calls, and no retries for contract errors.
- Tool selection comes from the model, but registration and execution
  permission come only from application policy.
- Reuse shared application requests and result DTOs; do not call CLI functions
  or TUI presenters.
- Preserve result references so follow-up turns can point to the exact output.

Close gate: invalid ticker/desk/tool names, invented arguments, unavailable
data, tool timeout, malformed model output, and prompt-injected tool requests
all fail safely and visibly.

### Phase 3 — Ephemeral multi-turn session and hardening

Outcome: users can ask follow-ups during one cockpit process without confusing
old and current results.

- Add bounded in-memory session state owned by the application use case or an
  injected session port.
- Invalidate or mark references stale when the focused result changes.
- Add cancellation and late-result rejection using the established TUI worker
  generation pattern.
- Add provider capability checks tied to exact provider, model, prompt version,
  tool-schema version, and evaluation-suite version.
- Add deterministic context budgeting and conversation summarization that
  cannot rewrite authoritative fields.

Close gate: rapid submit/cancel/navigation cannot paint an answer into the
wrong ticker or stage; context pressure cannot remove Action, freshness,
warnings, provenance, or authority labels.

### Phase 4 — Audit persistence (separate approval)

Outcome: optional local audit history exists only after its schema, retention,
redaction, and read-only inspection contracts are approved.

- Add an application audit repository port and SQLite implementation.
- Persist normalized request metadata, provider/model identity, tool calls,
  result references/hashes, timing/usage, failure state, and redacted answer.
- Do not persist secrets or unrestricted raw provider/tool payloads.
- Define retention, deletion, export, and schema-version behavior before the
  first write.

This phase is not implied by approval of Phases 0–3.

### Phase 5 — Consequential tools (future roadmap, not v1)

Refresh, paper journal, preferences, watchlists, config proposals, or other
writes require a new task/roadmap with:

- per-tool side-effect classification;
- deterministic approval state and confirmation UI;
- idempotency keys and `UNKNOWN_COMPLETION_STATE` handling;
- exact write audit and recovery semantics;
- negative tests proving the model cannot self-approve or retry an uncertain
  write.

No tool in this phase may trade or bypass validation/promotion guardrails.

## Do Not Interpret This As

- Do not embed an agent inside `SignalEngine`, `RiskEngine`, MCE, or
  `AssessTradeSetupUseCase`.
- Do not feed model output back into canonical scoring, Action, sizing,
  persistence selection, or evidence authority.
- Do not execute text as a `saham` command or parse CLI output.
- Do not let the TUI adapter choose workflow, freshness, retry, or permission
  policy.
- Do not give the model direct SQLite, filesystem, shell, browser, provider, or
  network access.
- Do not turn existing provider-specific explainers into a broad tool-capable
  interface by weakening their contracts.
- Do not copy the concrete Anthropic dependency from
  `src/application/services/ai_research.py` into new application code.
- Do not silently fall back to another provider or model.
- Do not persist inferred financial preferences or conversation history in v1.
- Do not show agent prose with canonical verdict styling or vocabulary.
- Do not make TUI, AI dependencies, credentials, or network access mandatory
  for deterministic CLI/application operation.

## Test strategy and close criteria

All tests must run offline with recording fakes; provider smoke tests, if any,
are opt-in and cannot be the correctness gate.

### Application tests

- exact visible-context projection and no hidden second read;
- zero-tool Phase 1 behavior;
- tool allowlist and argument validation;
- tool-call/time/context budgets;
- partial, unavailable, malformed, timeout, auth, rate-limit, and unexpected
  contract failure semantics;
- authoritative fields survive projection and history compression unchanged;
- agent answer is never consumed by canonical engines or persistence paths;
- prompt injection in tool data cannot authorize or define calls.

### Infrastructure tests

- normalized provider request/response and exact model identity;
- SDK/HTTP errors map to typed failures;
- credentials and untrusted content are redacted;
- no silent provider fallback;
- fake provider supports deterministic offline tests.

### TUI tests

- submit, loading, cancel, success, partial, unavailable, and error states;
- navigation during a turn rejects late results;
- answer remains bound to the originating subject/result reference;
- keyboard focus and `Esc` behavior remain usable;
- transcript does not unmask or replace the current cockpit instrument;
- deterministic rendered acceptance at `80x24` and `120x40`, including a
  non-happy state;
- AI-disabled startup and all existing cockpit journeys remain green.

### Repository gates for every implementation phase

- focused unit/integration tests for the phase;
- `pytest -m tui` for TUI changes and the full suite before final phase close;
- `ruff check src/ tests/`;
- `ruff format --check src/ tests/`;
- `git diff --check`;
- architecture boundary tests;
- multi-surface inventory/parity tests when a shared job or projection changes;
- exact code/config/doc state reported, with unrelated worktree changes left
  untouched.

## Definition of v1 done

V1 is complete only when a user can ask a question about the current cockpit
context, receive a visibly non-authoritative answer grounded in exact typed
results, optionally let the agent call only the approved read tools, cancel or
navigate without stale UI delivery, and continue using every deterministic
workflow with AI fully absent.

V1 is not complete merely because a provider can return chat text in the prompt
rail.
