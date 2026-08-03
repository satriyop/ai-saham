# ADR-063: Ephemeral agent session, reference invalidation, and context budget

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted — architecture authorization only; runtime activation gated

**Date:** 2026-08-03

**Amends:** [ADR-060](ADR-060-read-only-tui-context-agent.md),
[ADR-061](ADR-061-closed-read-tool-orchestration-for-context-agent.md)

**Depends on:** [ADR-003](ADR-003-hexagonal-ports-adapters-architecture.md),
[ADR-013](ADR-013-ai-agent-governance.md),
[ADR-040](ADR-040-manual-dependency-injection-and-composition-roots.md),
[ADR-042](ADR-042-deterministic-champion-and-optional-model-challengers.md),
[ADR-060](ADR-060-read-only-tui-context-agent.md),
[ADR-061](ADR-061-closed-read-tool-orchestration-for-context-agent.md)

**Implementation task:**
[`tasks/backlog/implement_tui_agent_ephemeral_sessions_phase3.md`](../../tasks/backlog/implement_tui_agent_ephemeral_sessions_phase3.md)

## Context

Phase 1 and Phase 2 deliver one independent turn: the model may explain the
exact visible accumulation Judge context and, when tools are enabled, may
propose up to two closed read-only tools. That design deliberately creates no
session memory.

Operators still need short follow-ups (“why is that gate blocking?”, “compare
that desk to the risk note”) during one `saham tui` process. Naively retaining
chat text risks:

- binding old BBCA facts to a later TLKM focus;
- treating an LLM paraphrase as Action, freshness, or provenance truth;
- overflowing the model context by dumping unlimited history;
- painting a late worker answer into the wrong stage or generation.

Phase 3 must therefore own **session identity, turn ordering, exact result
references, compatibility invalidation, deterministic context budgeting, and
optional commentary compression** in application policy. The TUI remains a thin
adapter for lineage capture, generation cancellation, and rendering.

This decision authorizes only **process-local, in-memory** sessions. It does not
authorize durable transcripts, audit rows, preferences, writes, new tools, or
Telegram transport.

## Decision

### Authorization boundary

Authorize one application-owned ephemeral session per TUI process (or future
channel process) that:

1. retains typed turn metadata and exact result/context references;
2. may retain bounded recent commentary and a deterministic compression of older
   commentary;
3. re-validates every prior reference against the current cockpit context before
   the next turn uses it as current fact;
4. disappears completely when the process exits.

Phase 3 remains `NON_SEMANTIC`. Session state may influence only agent
commentary assembly and which already-approved read tools may be proposed
again. It must never enter Signal, Risk, MCE, `TradeSetup`, evidence authority,
sizing, execution, observations, labels, tuning, promotion, or persistence.

No new tool names are authorized. ADR-061's closed four-tool set remains the
maximum; registration remains per-tool and fail-soft.

### Layer ownership

```text
TUI / future channel adapter                              Adapter
  - capture generation, stage, focus subject, source identity
  - create/reset session handle only via application API
  - cancel workers; reject stale paints by generation
  - render transcript + stale/overflow banners
                         |
                         v
AgentSessionOrchestrator / session port                   Application
  - session id, turn sequence, budgets, eviction
  - compatibility predicate for references
  - context pack P0–P4 assembly and compression policy
  - invoke existing one-turn orchestrator with packed context
             |                               |
             v                               v
AgentModelPort                         AgentToolRegistry
Infrastructure                         Application (unchanged Phase 2)
  - provider identity metadata only
  - no session persistence
```

Adapters must not invent session budgets, compatibility rules, or summary
semantics. Infrastructure must not store session rows.

### Identity and state

Immutable contracts the implementing task must realize as frozen DTOs:

| Type | Meaning |
|---|---|
| `AgentSessionId` | Opaque process-local id created by application policy on first session turn or explicit reset |
| `AgentTurnId` | Opaque id for one user question + orchestration attempt |
| `turn_sequence` | Monotonic integer starting at 1 within the session |
| `AgentSessionState` | Typed references + bounded commentary history; never unrestricted raw provider objects or SDK message dumps |
| `AgentResultReference` | Existing Phase 2 `result_reference` / `context_reference` plus subject, as-of, status, schema_id, provenance source |

A ticker string alone is never sufficient identity. Compatibility requires at
least matching:

- subject identity (ticker and/or broker_code as applicable);
- schema id of the authoritative context projection;
- `context_reference` (or successor reference after an explicit re-judge that
  the operator still treats as current focus);
- generation lineage for paint delivery remains TUI-owned and independent.

### Compatibility and invalidation

Before assembling context for turn *n*:

1. Capture the adapter's current exact visible accumulation context (or declare
   that no compatible Judge context exists).
2. Classify each prior tool/context reference as `FRESH`, `STALE`, or
   `INCOMPATIBLE`.
3. Only `FRESH` references may be presented as current facts.
4. `STALE` / `INCOMPATIBLE` references may appear only as historical notes with
   explicit status; they cannot authorize claims about the current Action.
5. Focus change, re-judge, refresh, navigation that changes the focused result,
   explicit session reset, or session eviction invalidates prior current-fact
   status before the next turn.

Cancellation and newer generation still discard in-flight answers for paint
even when ticker text matches (ADR-060 lineage rules).

### Context priorities and budgets

When packing provider context, the application uses fixed priorities:

| Priority | Content | May compress? |
|---|---|---|
| **P0** | Current Action, freshness, warnings, provenance, authority labels, exact current `context_reference` | **No** — omit whole turn if they cannot fit |
| **P1** | Current structured Judge projection (`tui_agent.accum_judge.v1` or successor) | **No** for Action/score/date/gate fields; omit optional sub-branches only by explicit field policy |
| **P2** | Fresh tool results from this session (bounded Phase 2 projections + references) | May drop oldest fresh tools first; never rewrite their typed fields |
| **P3** | Recent user questions + model answers as commentary | Yes, after the retention window |
| **P4** | Deterministic compressed summary of older commentary only | Yes; must not invent new scores/dates/Action |

Initial locked limits (implementation must not raise these without an ADR
amendment):

| Limit | Value |
|---|---:|
| Sessions per process | 1 active session |
| Maximum turns per session | 8 |
| Maximum retained full Q/A commentary turns | 3 most recent |
| Maximum retained fresh tool result projections | 4 |
| Maximum packed session context (serialized UTF-8) | 24 KiB |
| Maximum compressed older-commentary summary | 1,500 characters |
| Maximum concurrent in-flight agent turns | 1 |
| Process durability | none — no disk/SQLite write |

Overflow is explicit: status `FAILED` or `UNAVAILABLE` with a stable message
that context budget was exceeded. Silent truncation of P0/P1 is forbidden.

### Summarization boundary

Older conversation may be summarized **only as non-authoritative commentary**.
The summary input/output schema must preserve structurally:

- every pending failure code;
- every warning string from retained turns;
- every exact `context_reference` and tool `result_reference` still held;
- permission/tool-enabled flags relevant to the session.

Forbidden in any summary or model-facing paraphrase that is treated as fact:

- Action, scores, regimes, gate lists, as-of dates, freshness statuses,
  provenance sources, or tool payload fields not also present as typed
  structured objects in the same pack.

If compression cannot preserve those structural anchors, the session must
evict older turns rather than invent a lossy free-text stand-in.

### Configuration and capability certification

- `ai.enabled` remains the global AI opt-in (default `false`).
- `ai.tools_enabled` remains the independent tool switch (default `false`).
- Phase 3 adds `ai.session_enabled` (default `false`). When false, behavior is
  exactly Phase 1/2 one-turn: no retained session state across questions.
- When `ai.session_enabled` is true, the application may retain the in-memory
  session described above for follow-ups within the process.

Provider capability for multi-turn packing is identity-bound. A certification
record must include:

- provider name;
- exact model id;
- system-prompt version;
- tool-schema version (ADR-061 registry identity);
- evaluation-suite version;
- certification date;
- pass/fail result.

An uncertified model/provider may still run Phase 1 zero-tool one-shot answers
when otherwise enabled, but **must not** gain tool capability or multi-turn
session packing that assumes certified tool behavior. There is no silent
provider/model fallback.

Initial certified path remains DeepSeek non-thinking on the stable endpoint,
reusing ADR-061 tool-call rules per turn (at most two provider calls and two
tools per turn). Session follow-ups do not raise those per-turn ceilings.

### Adapter and UX contract

TUI designs must cover at least:

- follow-up on the same focused Judge result;
- stale-context banner when prior references no longer match focus;
- cancel / Escape / newer submission (existing generation pattern);
- overflow / eviction visible failure;
- explicit session reset (prompt command or documented chord);
- compact transcript at `80x24` and usable layout at `120x40`.

The adapter renders session id and turn sequence in meta copy only. It never
recomputes compatibility.

### Persistence and channels

- Zero durable writes: no transcript table, audit row, preference, cache
  access-time bump, or file under the session path.
- Process restart has empty session state by construction.
- Telegram/OpenClaw/Hermes reuse requires their own tasks; this ADR does not
  authorize those transports. If reused later, session identity remains
  application-owned and process/channel-scoped, not chat-history authority.

## Hard invariants

1. Deterministic `TradeSetup.action` remains the only Action.
2. Session state cannot feed canonical workflows or any persistence path.
3. Exact result/context references are the only way prior facts re-enter a turn
   as current facts; ticker text is insufficient.
4. P0/P1 authority-bearing fields are never sourced from LLM summaries.
5. Invalidation runs before context packing for every follow-up.
6. Cancellation/generation rules still prevent late paint into the wrong stage.
7. Overflow/eviction/reset are explicit statuses, never silent.
8. No new tools, writes, or providers are authorized by this ADR.
9. AI-disabled and `ai.session_enabled=false` paths have no session dependency.
10. Disabling sessions requires no migration because nothing is persisted.

## Non-goals

- No durable conversation, audit, export, or preference store (Phase 4).
- No consequential/write tools (Phase 5).
- No background/proactive agent, scheduler, or wake-up.
- No unlimited raw provider history in memory.
- No multi-session multi-user server design.
- No raising Phase 2 tool/turn ceilings.
- No Telegram/MCP transport authorization.

## Consequences

### Positive

- Operators can ask bounded follow-ups without rebuilding the entire rail.
- Stale-result confusion becomes a typed policy problem with tests.
- Compression is constrained so model prose cannot become authority.
- Rollback is a config flag with no schema migration.

### Costs

- Application session packing and TUI transcript UX add implementation work.
- Capability certification must be maintained when prompts/tools change.
- Follow-ups still cost provider tokens and remain optional.

### Follow-up

- Activate and implement
  `tasks/backlog/implement_tui_agent_ephemeral_sessions_phase3.md`.
- Phase 4 audit persistence remains separately parked and requires its own ADR.
