# ADR-064: AI Research Cockpit — bounded multi-round OUR tools (L3)

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted — architecture authorization only; runtime activation gated

**Date:** 2026-08-03

**Amends:** [ADR-061](ADR-061-closed-read-tool-orchestration-for-context-agent.md)

**Depends on:** [ADR-003](ADR-003-hexagonal-ports-adapters-architecture.md),
[ADR-013](ADR-013-ai-agent-governance.md),
[ADR-040](ADR-040-manual-dependency-injection-and-composition-roots.md),
[ADR-042](ADR-042-deterministic-champion-and-optional-model-challengers.md),
[ADR-060](ADR-060-read-only-tui-context-agent.md),
[ADR-061](ADR-061-closed-read-tool-orchestration-for-context-agent.md),
[ADR-063](ADR-063-ephemeral-agent-session-and-context-budget.md)

**Product vocabulary:** **AI Research Cockpit** (`/`) —
[`docs/roadmap/tui_ai_agent_implementation_journey.md`](../roadmap/tui_ai_agent_implementation_journey.md)

**Implementation task:**
[`tasks/backlog/implement_ai_research_cockpit_multi_round_tools_l3.md`](../../tasks/backlog/implement_ai_research_cockpit_multi_round_tools_l3.md)

## Context

ADR-061 authorizes a closed registry of typed, read-only tools for one
Research Cockpit turn with a **single** tool batch:

1. At most one provider call with `tool_choice=auto` and registered definitions.
2. Validate and execute at most two sequential tools.
3. Exactly one final provider call with `tool_choice=none`.
4. No further tool proposals.

That protocol is safe and testable, but too tight for common research questions
that need **more than one hop** over **OUR** tools only (e.g. dashboard → desk →
synthesize, or judge re-read after a visible-result check). The model then
either answers under-informed or emits non-answers such as “I’ll check tools…”
after a single incomplete step.

Operators still must not get:

- unbounded “agent until done” loops;
- model-invented tools;
- network/write capabilities (L4 / later ADRs);
- mutation of deterministic Action authority.

The AI Research Cockpit is a **journey** of progressive improvement, not a
permanent capability ceiling. L3 is the next step: **bounded multi-round**
execution over the **same closed OUR tool catalog**, with hard budgets and
fail-closed exhaustion.

## Decision

### Authorization boundary

Authorize the application orchestrator of the AI Research Cockpit to run
**multiple provider↔tool rounds within one user turn**, subject to the budgets
and state machine below, **only** over tools that are already registered under
ADR-061 (or a later ADR that adds **OUR** tools to the closed registry).

This decision does **not**:

- register new tool names by itself;
- authorize external/network/write capabilities (L4);
- authorize model-defined tools;
- change Action, Signal, Risk, MCE, or evidence authority.

Capability layers for vocabulary (journey, not separate products):

| Layer | Meaning | Authority |
|---|---|---|
| L1 | One tool batch (ADR-061) | Shipped protocol |
| L3 (this ADR) | Bounded multi-round OUR tools | Authorized when activated |
| L4 | Named external + confirm | Separate ADR |

Raising L3 budgets later is an **ADR amendment**, not silent config.

### Configuration

- `ai.enabled` — global AI opt-in (unchanged; default `false`).
- `ai.tools_enabled` — closed tools visible to the model (unchanged; default `false`).
- **`ai.tools_multi_round`** — enables L3 budgets when tools are enabled
  (default **`false`**).

When `tools_enabled` is true and `tools_multi_round` is false, behavior remains
**exactly ADR-061 L1** (one batch, two tools, two provider calls).

When both are true (and a certified provider/path is available), the L3 state
machine and budgets apply.

Default false preserves rollback and matches other AI opt-ins. Research dogfood
profiles set `tools_multi_round: true` in local `user.yaml`. Coupling
“tools_enabled implies multi_round” is a later product config choice and does
not change this ADR’s independent flag.

### Locked budgets (initial L3)

| Limit | Value |
|---|---:|
| Provider rounds per user turn | **3** maximum |
| Tool executions per user turn | **4** maximum |
| Tools per batch | **2** maximum |
| Parallel tools | **0** (sequential only) |
| Retries | **0** |
| Provider timeout per call | **10 s** (same family as ADR-061) |
| Total tool-execution budget | **20 s** (sum across tools in the turn) |
| Total turn deadline | **45 s** |
| Total serialized tool results | **64 KiB** (unchanged) |
| Per-tool projection limits | Unchanged from ADR-061 per-tool tables |

**Provider round** means one `model.generate` call (auto or none).

Recommended shape when multi-round is on:

1. Round 1: `tool_choice=auto` (may answer with zero tools).  
2. If tools proposed → validate batch → execute (count toward 4).  
3. Round 2: `tool_choice=auto` with prior tool results (may answer or propose).  
4. If tools again → execute remaining budget.  
5. **Final round (at latest round 3):** `tool_choice=none` — must be an answer.  

The implementation may finish earlier if the model returns an answer before the
round cap. The **last** provider call of a multi-round turn that still has
unused tool budget **may** use auto only if rounds remain; when the next call
would be the last allowed provider call, it **must** use `tool_choice=none`.

### Deterministic turn state machine

```text
START
  → validate user request + capture Research Cockpit context lineage
  → rounds_used = 0; tools_used = 0
  → LOOP while rounds_used < 3:
        provider_call (auto if tools remain and not forced_final else none)
        rounds_used += 1
        if ANSWER → SUCCESS/PARTIAL (commit session if applicable) → END
        if TOOL_CALLS:
           if tools_used >= 4 or batch invalid or tools_used+batch > 4
              → FAIL closed (no further provider calls) → END
           execute sequential tools; tools_used += n
           if cancelled → CANCELLED → END
           continue LOOP
        if malformed → FAIL with detail → END
  → if no answer after last forced none → FAIL (exhausted) → END
```

Invariants of the loop:

1. Unknown tool names, extra args, duplicate keys, duplicate
   name+canonical-args in a batch → **fail whole turn** (no partial execute of
   that batch). Across rounds, a later round may call a tool already used with
   **different** canonical args; same name+args as any prior execution in the
   turn is a duplicate and fails closed.
2. Tool content cannot authorize an extra round beyond the budget.
3. Intermediate provider text that is not the final answer is **not** Turn OK
   content. Adapters may show progress (“round 2/3 · tool …”) only.
4. Cancellation discards in-flight work; no delayed write (tools remain RO).
5. Session (ADR-063): a turn is **atomic** for session commit — only a
   completed SUCCESS/PARTIAL turn updates session commentary/tool memory.
   FAIL/CANCELLED leaves session as before that Enter (fail-safe).

### Tool catalog

Unchanged by this ADR. Runtime tools remain a subset of ADR-061 names (and any
later ADR-registered OUR tools), each still `side_effect=NONE` with proven
read-only composition.

### AI Research Cockpit UX

- Progress must be visible under multi-round (round index and/or current tool
  name) so the surface does not look hung.
- Final status strip remains Turn OK/FAIL + data honesty notes (journey UX locks).
- Esc / generation invalidation still abandons the whole turn.
- No confirm modal for OUR read tools (L4 owns confirm for external).

### Failure and partial semantics

| Case | Status |
|---|---|
| Final answer with all tools SUCCESS | SUCCESS |
| Final answer with any tool PARTIAL/UNAVAILABLE/FAILED | PARTIAL if answer present |
| Budget exhausted without answer | FAILED (explicit message) |
| Invalid batch / malformed provider | FAILED (detail surfaced) |
| Cancel | CANCELLED |
| Provider empty/planning-only text on forced final none | FAILED or soft policy fail — not SUCCESS |

Provider error strings should remain operator-visible (detail, not secrets).

## Hard invariants

1. Deterministic `TradeSetup.action` remains the only Action.  
2. Only application-registered tool names execute.  
3. L3 never raises ADR-061 tool side effects above `NONE`.  
4. Budgets fail closed; no silent truncation of authority fields.  
5. Intermediate monologue is not a successful turn answer.  
6. Model cannot extend rounds, tools, or registry via text.  
7. `tools_multi_round=false` restores ADR-061 L1 exactly.  
8. External/network/write remains unauthorized except via
   [ADR-065](ADR-065-ai-research-cockpit-external-and-ro-data-l4.md) when
   activated; model-invented tools remain forbidden.  

## Non-goals

- Model-invented tools or MCP freeform.  
- Web research, browser, or RO-SQL freeform (L4).  
- Writes, fetch refresh, trading.  
- Unlimited multi-round or user-configurable unbounded loops.  
- Parallel tool execution.  
- Replacing Judge with Research Cockpit as authority.  

## Consequences

### Positive

- Research questions can take multiple local hops without opening foreign tools.  
- Clear rollback to L1 via one flag.  
- Aligns with AI Research Cockpit as a progressive journey.  

### Costs

- Longer turns and more provider spend when enabled.  
- Orchestrator and TUI progress UX more complex.  
- Tests must cover multi-round preflight, exhaustion, and atomic session commit.  

### Follow-up

- Implement
  `tasks/backlog/implement_ai_research_cockpit_multi_round_tools_l3.md`.  
- L4 ADR (named external + y/n confirm) remains separate.  
- Multi-stage Research Cockpit entry (beyond Judge) remains journey work with
  per-stage context contracts.  
