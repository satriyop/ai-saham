# ADR-066: AI Research Cockpit — multi-stage destinations & per-stage context contract

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted — architecture authorization only; runtime activation gated

**Date:** 2026-08-03

**Amends:** [ADR-060](ADR-060-read-only-tui-context-agent.md),
[ADR-061](ADR-061-closed-read-tool-orchestration-for-context-agent.md)

**Depends on:** [ADR-003](ADR-003-hexagonal-ports-adapters-architecture.md),
[ADR-042](ADR-042-deterministic-champion-and-optional-model-challengers.md),
[ADR-060](ADR-060-read-only-tui-context-agent.md),
[ADR-061](ADR-061-closed-read-tool-orchestration-for-context-agent.md),
[ADR-063](ADR-063-ephemeral-agent-session-and-context-budget.md),
[ADR-064](ADR-064-ai-research-cockpit-bounded-multi-round-tools.md),
[ADR-065](ADR-065-ai-research-cockpit-external-and-ro-data-l4.md)

**Product vocabulary:** **AI Research Cockpit** (`/`) —
[`docs/roadmap/tui_ai_agent_implementation_journey.md`](../roadmap/tui_ai_agent_implementation_journey.md)

**Implementation epic (gated):**
[`tasks/backlog/implement_ai_research_cockpit_multi_stage_destinations.md`](../../tasks/backlog/implement_ai_research_cockpit_multi_stage_destinations.md)

## Context

The AI Research Cockpit is fully wired on exactly **one** stage: the accumulation
**Judge** (single-candidate drilldown). U5 of the journey SSOT deliberately makes
every other stage **notify and refuse** rather than invent context. The L1–L4
machinery (closed tools, multi-round budgets, sessions, L4 confirm/fail-safe) is
already **stage-agnostic** — the only accumulation coupling is in two DTOs and one
projection builder:

- `AgentTurnRequest.candidate: AccumulationCandidate` (request is candidate-typed).
- `AgentToolExecutionContext.visible_accumulation_context` (tools read one shape).
- `build_agent_accumulation_context(...)` → `AgentAccumulationContext`
  (schema `tui_agent.accum_judge.v1`): a pure, allow-listed projection with
  **ticker + snapshot identity validation** and a **content-hash
  `context_reference`** (the lineage the cockpit paints and tools cite).

Operators want `/` to open from the stages where they actually work. Each such
stage exposes different focused data, so each needs its **own** context contract
before the cockpit may open there — without loosening identity discipline,
read-only authority, or the deterministic champion.

ADR-064 and ADR-065 both name this as follow-up journey work: *"Multi-stage
Research Cockpit entry (beyond Judge) remains journey work with per-stage context
contracts."* This ADR provides that contract.

## Decision

### Authorization boundary

Authorize the AI Research Cockpit to open from **multiple named cockpit stages**,
each via a **per-stage context contract** that follows the same discipline as the
accumulation Judge contract. This ADR does **not** add tools, capabilities,
writes, external access, or any new authority. It only defines **where** `/` may
open and **what typed context** each stage projects.

Deterministic engines remain champion. Cockpit output stays non-authoritative
commentary + tool projections. L4 confirm still governs any elevated/external
tool regardless of stage.

### The per-stage context contract (the pattern)

Every destination stage MUST provide a pure application projection
`build_agent_<stage>_context(...)` that:

1. **Allow-lists** only the fields the model may see (no raw repositories, no
   superset dumps, no framework objects).
2. **Validates identity** — for single-subject stages, ticker + snapshot/as-of
   agreement across the canonical objects it draws from; for cohort/list stages,
   the screen identity (as-of date, filter/policy signature, cohort size) must be
   internally consistent. Disagreement → `AgentContextInvariantError`.
3. **Fails available-or-not honestly** — when the stage lacks a full focused
   context, raise `AgentContextUnavailableError` (→ notify + refuse; never
   fabricate). This is the generalization of U5.
4. **Emits a content-hash `context_reference`** (`sha256:…` of the canonical
   facts) so painted answers and tool citations are reproducible.
5. **Carries a stable `schema_id`** `tui_agent.<stage>.vN` (versioned; changing
   fields bumps the version).

These builders live in **application** (`src/application/services/`), are pure,
and are unit-tested independently of the TUI.

### Request / execution-context generalization

- `AgentTurnRequest` carries a **stage-tagged context** instead of a raw
  `AccumulationCandidate`. Recommended shape: a `stage_kind` enum +
  a typed `stage_context` (a common `AgentStageContext` supertype or a tagged
  union of the per-stage projection types). The accumulation Judge becomes one
  member; no behavior change for it.
- `AgentToolExecutionContext` holds the **active stage context**.
  `get_visible_cockpit_result` returns the projection for whichever stage is
  active. Other OUR tools remain closed and typed; a tool that a stage cannot
  serve returns `UNAVAILABLE` (not a fabricated result).
- Backward compatibility: the accumulation Judge path must remain **bit-identical**
  in behavior and lineage (same `tui_agent.accum_judge.v1` hash for the same
  input).

### Stage catalog (destination priority order)

Each row is an independent implementation slice with its own context schema,
gating, tests, and golden pilot. Ship order is the operator's priority:

| # | Stage | `stage_kind` | Context subject | Schema id |
|---|---|---|---|---|
| 1 | Accumulation **screen** board | `accum_screen` | Cohort: as-of, filter/policy signature, regime, ranked candidate summaries (bounded top-N) | `tui_agent.accum_screen.v1` |
| 2 | **View ticker** dashboard | `view_ticker` | Single ticker cache-only dashboard facts (price/indicator/flow summary) | `tui_agent.view_ticker.v1` |
| 3 | **View broker** desk | `view_broker` | Broker desk view facts (desk code, top stocks / flow / matrix as shown) | `tui_agent.view_broker.v1` |
| 4 | **Pre-open screen** board | `preopen_screen` | Pre-open cohort: as-of, IEV/calendar/regime context, candidate summaries | `tui_agent.preopen_screen.v1` |
| 5 | **Plan swing** | `plan_swing` | Swing plan facts (setup, sizing inputs, evidence availability) | `tui_agent.plan_swing.v1` |

Cohort/list stages (1, 4) project a **bounded** summary (top-N candidates +
screen identity), never the full unbounded board, and never a per-candidate Judge
(that remains the Judge stage). If the operator wants candidate depth, they drill
into the Judge/ticker stage — the cockpit does not silently expand scope.

### Gating (per stage)

`/` (and free-text auto-agent, U2) opens the cockpit on a stage **only** when that
stage's `build_agent_<stage>_context` succeeds. On `AgentContextUnavailableError`,
notify + refuse with the stage-appropriate hint (e.g. "press j to judge", "open a
ticker") — the current Judge-only refuse behavior, generalized. Esc still restores
the prior deterministic stage.

### Rollout flag (safe default)

A single master flag **`ai.cockpit_multi_stage`** (default **`false`**) gates the
expansion. When false, `/` remains Judge-only exactly as today. When true (and
`ai.enabled`), the additional destinations open per their shipped slices. Slices
may land dark under this flag and be enabled together. Per-stage sub-flags are a
later product choice, not required by this ADR.

### Authority and honesty (unchanged)

- No new authority: stage contexts are read-only projections of existing
  deterministic/cache results.
- Cockpit answers never enter Signal, Risk, MCE, `TradeSetup`, sizing,
  observations, labels, tuning, or promotion — on any stage.
- Data-honesty strip, session dedupe, L4 confirm, and fail-safe restore behave
  identically regardless of stage.

## Hard invariants

1. Registry stays closed; adding stages adds **context**, not tools or authority.
2. Every stage context is a pure, allow-listed, identity-validated projection with
   a content-hash `context_reference` and a versioned `schema_id`.
3. Missing/partial focused context → notify + refuse; never fabricate (U5 general).
4. Accumulation Judge behavior + lineage remain bit-identical.
5. Deterministic Action authority is untouched on every stage.
6. `ai.cockpit_multi_stage=false` restores Judge-only exactly.
7. Cohort stages project bounded summaries, not full boards or per-candidate Judges.

## Non-goals

- New tools, write/fetch/refresh, external access beyond ADR-065.
- Model-invented tools or MCP freeform.
- Durable audit (parked Phase 4) / consequential tools (parked Phase 5).
- Cross-stage autonomous navigation (the model does not drive the TUI between
  stages; the operator chooses the stage, the cockpit reads that stage).
- Changing L3/L4 budgets or the state machine.

## Consequences

### Positive

- The cockpit opens where operators actually work; reuses hardened L1–L4 machinery.
- One disciplined contract pattern replicated per stage keeps identity/lineage safe.
- Clean rollback via one flag; slices ship independently.

### Costs

- One projection builder + schema + gating + golden pilot per stage.
- `AgentTurnRequest`/`AgentToolExecutionContext` generalization touches the Judge
  path (must prove bit-identical).
- Cohort projections need a bounding policy (top-N) locked per stage.

### Follow-up

- Implement `implement_ai_research_cockpit_multi_stage_destinations.md` in the
  five slices above, in priority order, each stopping for review.
- Update journey SSOT §1 map + UX locks (generalize U5) as each stage lands.
