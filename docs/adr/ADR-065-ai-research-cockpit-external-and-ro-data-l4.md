# ADR-065: AI Research Cockpit — external research, RO data ask, and confirm (L4)

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted — architecture authorization only; runtime activation gated

**Date:** 2026-08-03

**Amends:** [ADR-061](ADR-061-closed-read-tool-orchestration-for-context-agent.md),
[ADR-064](ADR-064-ai-research-cockpit-bounded-multi-round-tools.md)

**Depends on:** [ADR-003](ADR-003-hexagonal-ports-adapters-architecture.md),
[ADR-013](ADR-013-ai-agent-governance.md),
[ADR-040](ADR-040-manual-dependency-injection-and-composition-roots.md),
[ADR-042](ADR-042-deterministic-champion-and-optional-model-challengers.md),
[ADR-060](ADR-060-read-only-tui-context-agent.md),
[ADR-061](ADR-061-closed-read-tool-orchestration-for-context-agent.md),
[ADR-063](ADR-063-ephemeral-agent-session-and-context-budget.md),
[ADR-064](ADR-064-ai-research-cockpit-bounded-multi-round-tools.md)

**Product vocabulary:** **AI Research Cockpit** (`/`) —
[`docs/roadmap/tui_ai_agent_implementation_journey.md`](../roadmap/tui_ai_agent_implementation_journey.md)

**Implementation epic (gated):**
[`tasks/backlog/implement_ai_research_cockpit_external_and_ro_data_l4.md`](../../tasks/backlog/implement_ai_research_cockpit_external_and_ro_data_l4.md)

## Context

The AI Research Cockpit already explains Judge context (ADR-060), may call a
closed set of **OUR** local read tools (ADR-061), may retain process-local
session memory (ADR-063), and may use bounded multi-round OUR tools (ADR-064)
when enabled.

Operators also need:

1. **External research** when local cache and OUR tools are insufficient.
2. **Read-only data ask** beyond the four Phase-2 projections (still without
   freeform mutation or decision authority).
3. A way to learn which **OUR** tools to build next when the model wants a
   capability we do not register.

Allowing the model to invent tools, browse freely, or run unconstrained SQL
would break hexagonal boundaries, local-first defaults, and Action authority.
L4 therefore adds only **named, application-owned capabilities** with explicit
**side-effect class**, **confirm policy**, and **fail-safe** behavior.

## Decision

### Authorization boundary

Authorize the AI Research Cockpit tool registry and orchestrator to include
**elevated** capabilities beyond ADR-061 `side_effect=NONE` local tools, under
the rules below.

| Class | Examples | Confirm | Default ship |
|---|---|---|---|
| **OUR local read** (L1/L3) | ADR-061 four tools | None (beyond `tools_enabled`) | Opt-in flags |
| **Elevated RO data** | Allowlisted read-only SQL / prepared data ask | **y/n** before execute | Opt-in flags |
| **External research** | `web_research` via DeepSeek research/web tool path | **y/n** before execute | Opt-in flags |
| **Unregistered / model-invented** | Any name not in registry | **Never execute** | N/A |

Model-invented tools remain **forbidden**. When the model proposes or needs a
capability outside the registry, the application records a **tool-gap clue**
(stable code + suggested OUR tool name/purpose) for product design and may
answer honestly that the capability is unavailable. Gap clues are not Action
authority and are not silent “fake tool” execution.

This ADR does **not** authorize writes, fetch/refresh into SQLite, trading,
shell, free browser agent loops, or durable audit (separate Phase-4 style ADR).

### Named capabilities (v1 catalog authorization)

#### 1. `web_research`

- **Purpose:** External web/research grounded snippets for operator questions
  that local tools cannot answer.
- **Side effect:** `NETWORK_READ`.
- **Provider path:** DeepSeek tool-call / research capability as exposed by the
  DeepSeek API family used by this product; exact endpoint, model, and tool
  schema must be **re-verified at implementation** and versioned behind our
  port. Provider drift does not expand authority.
- **Args (locked intent):** closed schema, e.g. `query: str` (bounded length),
  optional `max_results` with a hard ceiling.
- **Result:** frozen typed projection: snippets, titles, URLs, as-of/fetch
  timestamp, provider identity — **no** unrestricted HTML, credentials, or raw
  provider dump as authority.
- **Honesty:** successful external use must surface a data note such as
  `EXTERNAL_RESEARCH` (non-reproducible; not Action authority).

#### 2. `ro_data_query` (allowlisted read-only data ask)

- **Purpose:** Let the operator ask structured questions of **local** data
  beyond fixed Phase-2 projections.
- **Side effect:** `LOCAL_READ_ELEVATED` (still no write; elevated vs ordinary
  OUR tools because of broader surface).
- **Access model:** **Allowlisted SELECT / prepared query shapes only** — not
  free multi-statement SQL, not DDL/DML, not arbitrary `PRAGMA`/attach.
- **Hard limits (implementation must lock numbers):** max rows, max bytes,
  statement timeout, fixed schema allowlist, no cross-db attach.
- **Confirm:** **y/n** before execute (same light confirm family as external).
- **Gap path:** If the model wants tables/columns outside the allowlist, emit a
  **tool-gap clue** describing the missing **OUR** projection tool to design
  next (so elevated SQL slowly shrinks in favor of named tools).

Ordinary ADR-061 tools remain preferred when they cover the need. Elevated RO
and external are for residual research needs.

### Confirm UX (Research Cockpit)

For every elevated/external capability execution:

1. Orchestrator pauses in application state `PENDING_APPROVAL` (not adapter
   policy).
2. Research Cockpit shows a **light confirm** (in-stage y/n control or equivalent
   light modal owned by the cockpit):
   - capability name;
   - human summary of args (e.g. research query or query shape);
   - implication line (network leaves machine / RO local only / does not change
     Action);
   - **Default focus = Yes** for research-class reads.
3. **Enter** on Yes → execute. **No** / deny → see fail/deny rules below.
4. Confirm is **not** satisfied by free-text chat alone (“yes” in the model
   transcript is not authorization).

Ordinary OUR `side_effect=NONE` tools do **not** use this confirm.

### Configuration (safe defaults)

| Flag | Default | Meaning |
|---|---|---|
| `ai.enabled` | `false` | Global AI |
| `ai.tools_enabled` | `false` | Ordinary OUR tools |
| `ai.tools_multi_round` | `false` | L3 multi-round (ADR-064) |
| `ai.external_tools` | `false` | Master: elevated/external capabilities may register |
| `ai.web_research` | `false` | Register/enable `web_research` (requires master true) |
| (implement) RO data flag | `false` | Register/enable `ro_data_query` (requires master true) |

Both **master + per-capability** flags are required for external/elevated paths
(decision **7C**). Defaults remain off for safe shipping; research dogfood turns
them on in local config.

### Interaction with L3 multi-round (decision **5B**)

When multi-round is enabled, **elevated and external executions count toward the
same L3 tool budget** (max 4 tool executions / turn, max 2 per batch, 3 provider
rounds). They do not get a separate unlimited budget.

Confirm blocks **before** an elevated/external execution and does not consume an
extra provider round by itself.

### Deny vs fail (decision **6** — locked recommendation)

| Event | Behavior |
|---|---|
| User **denies** confirm | **Skip** that capability; continue the turn with OUR tools and/or final answer without it. Do **not** fail the whole turn solely because of deny. Record a non-authoritative note that external/elevated was declined. |
| Capability **fails after approve** (transport, timeout, malformed, policy) | **Do not** commit this turn as SUCCESS into ADR-063 session memory. Restore Research Cockpit UI to the **last successful** turn content when one exists; if none, restore prior deterministic stage (Judge). Show explicit error detail (no secrets). |
| Optional partial | If OUR tools already succeeded earlier in the **same** Enter before the failed elevated/external call, the orchestrator **may** make one final `tool_choice=none` answer using only local results and mark PARTIAL; session commit still follows SUCCESS/PARTIAL rules only when a final answer is accepted. If no usable local path, turn is FAILED with fail-safe restore. |

### Fail-safe (decision **4A**)

- Research Cockpit keeps a **last successful turn snapshot** (answer, strip,
  tool trace, context reference) for the process session.
- On FAILED/CANCELLED elevated-heavy turns: restore that snapshot in the UI.
- Session pack (ADR-063) is updated only on completed SUCCESS/PARTIAL turns
  (atomic with ADR-064).

### Tool-gap clues (decision **1** learning loop)

When the model requests an unregistered tool or an allowlist miss:

1. Reject execution.
2. Emit a structured **gap clue**: suggested tool id, purpose, why needed,
   optional arg sketch.
3. Surface a short operator-visible line in Research Cockpit honesty/more notes
   (e.g. `TOOL_GAP · suggested our tool: …`).
4. Optionally retain clues in process memory for the session (not durable audit
   unless a later Phase-4 ADR says so).

Gap clues drive the product backlog for new **OUR** tools so elevated SQL and
external research shrink over time.

### Authority and honesty

- External and elevated RO results are **context only**.
- They must not enter Signal, Risk, MCE, `TradeSetup`, sizing, execution,
  observations, labels, tuning, or promotion.
- Data-honesty strip should rank `EXTERNAL_RESEARCH` and elevated-query notes
  appropriately (non-reproducible / broader local surface).

## Hard invariants

1. Registry remains closed; configuration and model output cannot invent tools.  
2. No elevated/external execute without confirm (except ordinary NONE tools).  
3. Confirm default Yes only for research-class **reads**; writes remain out of
   scope here.  
4. Deny ≠ total turn death; post-approve fail uses fail-safe restore.  
5. DeepSeek research is **our** adapter-shaped `web_research`, not free agent
   browser autonomy.  
6. RO data ask is allowlisted SELECT/prepared only.  
7. Action authority remains deterministic.  
8. Safe flags default false.  

## Non-goals

- Model-defined tools or unrestricted MCP.  
- Write/fetch/refresh/journal tools (Phase 5 / separate ADRs).  
- Durable transcript/audit store (parked Phase 4).  
- Trading, shell, filesystem write.  
- Silent background network.  
- Unlimited multi-round or multi-external spam (still L3 budgets).  

## Consequences

### Positive

- Research Cockpit can leave the machine for web research under consent.  
- Broader local ask without abandoning hexagonal ownership.  
- Tool-gap clues turn model “needs” into OUR product backlog.  
- Fail-safe protects session integrity.  

### Costs

- Confirm UX and approval state machine complexity.  
- Provider verification burden for DeepSeek research path.  
- Allowlist maintenance for RO queries.  
- Longer turns when multi-round + external combine.  

### Follow-up

- Prefer implementing **ADR-064 L3 runtime** before L4 runtime.  
- Implement epic
  `implement_ai_research_cockpit_external_and_ro_data_l4.md` in slices:
  (1) registry side-effect + confirm seam, (2) `web_research`,
  (3) `ro_data_query` allowlist, (4) gap clues.  
- Re-verify DeepSeek research/tool contracts at slice (2).  

## Operator freezes recorded (2026-08-03)

| # | Decision |
|---|---|
| 1 | RO data = named tools + allowlisted SELECT; y/n on non-ordinary tools; gap clues for OUR tool design |
| 2 | `web_research` in ADR; DeepSeek tool-call/research path |
| 3 | Light y/n, default Yes, Enter executes, show implication |
| 4 | Fail-safe A: no bad session commit + restore last successful Research Cockpit answer |
| 5 | Externals count toward L3 tool budget |
| 6 | Deny → continue without; post-approve fail → fail-safe (+ optional local-only final) |
| 7 | Flags: master `external_tools` + per-capability (`web_research`, RO) |
| 8 | ADR now; implement after L3 preferred |
