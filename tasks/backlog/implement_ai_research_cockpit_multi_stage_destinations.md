# Goal Instruction — Implement AI Research Cockpit Multi-Stage Destinations

**Status:** `READY FOR AGENT`
**Audience:** Implementation agent (any coding agent in this repo)
**Product term:** **AI Research Cockpit** (`/`) — use this name in code, commits, docs.

**Binding architecture (read before coding):**

| Doc | Role |
|---|---|
| [ADR-066](../../docs/adr/ADR-066-ai-research-cockpit-multi-stage-destinations.md) | **Binding** — per-stage context contract, catalog, gating, rollout flag |
| [ADR-060](../../docs/adr/ADR-060-read-only-tui-context-agent.md) | Read-only cockpit baseline |
| [ADR-061](../../docs/adr/ADR-061-closed-read-tool-orchestration-for-context-agent.md) | Closed tool registry |
| [ADR-064](../../docs/adr/ADR-064-ai-research-cockpit-bounded-multi-round-tools.md) / [ADR-065](../../docs/adr/ADR-065-ai-research-cockpit-external-and-ro-data-l4.md) | L3/L4 machinery (reuse, do not change) |
| Journey SSOT | [`docs/roadmap/tui_ai_agent_implementation_journey.md`](../../docs/roadmap/tui_ai_agent_implementation_journey.md) — UX locks U1–U13 |
| Reference contract | `src/application/services/agent_accumulation_context.py` (`tui_agent.accum_judge.v1`) — copy its discipline |

**Do not invent product behavior.** If ADR and code conflict, stop and ask. If ADR
is silent, choose the **safer, smaller** option and document it.

---

## 0. Mission

Open the AI Research Cockpit from more cockpit stages by giving each stage its own
**pure, identity-validated, content-hashed context projection** and gating, reusing
the hardened L1–L4 machinery unchanged. Ship **five destinations in priority order**,
stopping for review after each:

1. **Accumulation screen board** (`accum_screen`)
2. **View ticker** dashboard (`view_ticker`)
3. **View broker** desk (`view_broker`)
4. **Pre-open screen** board (`preopen_screen`)
5. **Plan swing** (`plan_swing`)

Hard rules:

- **No new tools, no new authority, no writes/external** beyond ADR-061/065.
- Every stage context is a **pure application projection**: allow-listed fields,
  identity validation, `sha256:` `context_reference`, versioned `schema_id`.
- Missing/partial focused context → **notify + refuse** (never fabricate; U5 general).
- **Accumulation Judge path stays bit-identical** (same behavior + `tui_agent.accum_judge.v1`
  hash for the same input) — prove it with a regression test.
- Cohort stages (1, 4) project a **bounded top-N summary**, never full boards, never
  a per-candidate Judge.
- Rollout behind **`ai.cockpit_multi_stage`** (default `false`); when off, `/` stays
  Judge-only exactly as today.
- Multi-commit contextual commits; fix bugs found in separate `fix(...)` commits.
- Lint Gate: `ruff check src/ tests/` + `ruff format --check src/ tests/`.
- Offline `pytest -m "agent and not agent-live-call"` green without network; golden
  UX pilot green.

---

## 1. Preflight (mandatory)

```md
Confirm:
- Hexagonal boundaries; adapter stays thin (stage detection + wiring + render; no policy).
- Context builders + gating policy live in application; TUI only calls them.
- Deterministic-first; cockpit output non-authoritative on every stage.
- No guardrail bypass; no new tools/flags beyond ai.cockpit_multi_stage.

Layer plan:
- Domain: not touched (unless a pure value object for a stage projection)
- Application: per-stage build_agent_<stage>_context + build_agent_stage_context facade
  (only dispatch site); AgentStageContext base + AgentTurnRequest/AgentToolExecutionContext
  generalization; refactor orchestrate + session_aware + explain (phase-1) to consume the
  built context (none build internally); get_visible_cockpit_result polymorphic result
- Infrastructure: ai.cockpit_multi_stage config flag; composition wiring per stage
- Adapter (TUI): stage detection + gating (notify/refuse), context build call, / open on new stages
```

Read before editing:

- `src/application/services/agent_accumulation_context.py` (the reference contract)
- `src/application/dto/accumulation_agent.py` (`AgentTurnRequest`, projection DTOs)
- `src/application/dto/agent_tool_context.py` (`AgentToolExecutionContext`)
- `src/application/use_case/orchestrate_agent_turn_use_case.py` (stage-agnostic already)
- `src/application/services/agent_tool_registry.py` + `get_visible_cockpit_result` tool
- `src/adapters/tui/main.py` (`_stage`/`_status_note` model, `_enter_agent_stage`,
  `/` open path, U5 refuse behavior) and the per-stage desks
- `src/infrastructure/config/app_config.py` + `config/default.yaml`

---

## 2. Slice 0 — Generalization foundation (do first, no new destination yet)

Refactor the request/execution-context to be **stage-tagged** and **built once at
open**, without changing Judge behavior. Resolved design calls (ADR-066 D1/D2):

**Build ownership (D1 — build once at open, carry the projection):**
- Add `AgentStageKind` enum (`accum_judge`, `accum_screen`, `view_ticker`,
  `view_broker`, `preopen_screen`, `plan_swing`).
- `AgentStageContext` = a common **frozen base** discriminated by `stage_kind` +
  `schema_id`; `AgentAccumulationContext` becomes the `accum_judge` member.
- Add an application facade `build_agent_stage_context(stage_kind, raw_stage_input)
  -> AgentStageContext` that dispatches to the per-stage builder. **This is the
  only dispatch site.**
- `AgentTurnRequest` carries the **already-built** `stage_context: AgentStageContext`
  (not raw input). The adapter calls the facade **once at cockpit open** (which
  also serves gating), maps `AgentContextUnavailableError` → notify+refuse, and
  passes the built context.
- **All three consumers stop building context** and accept the built context:
  `orchestrate_agent_turn_use_case` (:107), `session_aware_agent_turn_use_case`
  (:104, also feeds `build_session_pack` from the passed context), and
  `explain_accumulation_candidate_use_case` (:91, phase-1, wired as
  `phase_one_use_case` in `composition/agent_model.py:95`). **Finding 2:** the
  phase-1 consumer is explicitly in scope — do not leave it building.

**Visible-result tool (D2 — one polymorphic result):**
- `VisibleCockpitResultData.context` (`agent_visible_cockpit_tool.py:39`) becomes
  the `AgentStageContext` union, discriminated by `stage_kind`/`schema_id`. One
  tool, one result envelope; frozen-dataclass validator branches on `schema_id`.
  Do **not** create N per-stage result types. Tools a stage can't serve →
  `UNAVAILABLE`.

**Config:**
- Add `ai.cockpit_multi_stage` flag (default false) to `AiConfig` + `default.yaml`
  with a comment pointing at ADR-066.

**Acceptance:**
- [ ] Accum Judge turn is **bit-identical**: same painted answer, same
  `tui_agent.accum_judge.v1` `context_reference` for the same candidate.
- [ ] **Finding 5:** the prior internal double-build (session_aware + orchestrate)
  collapses to a **single canonical build**; assert the context is built exactly
  once per turn and the hash is unchanged. This collapse is required, not a
  regression.
- [ ] Phase-1 (`explain`) path still works via the built context (no internal build).
- [ ] Flag false → `/` opens only on Judge (all other stages notify + refuse).
- [ ] Existing agent suite + golden UX pilot green.

Commit: `refactor(agent): stage-tagged cockpit context built once at open (ADR-066)`

---

## 3. Slices 1–5 — Destinations (one per slice, in priority order)

For **each** destination, do the same disciplined steps:

1. **Context builder** `build_agent_<stage>_context(...)` in application:
   - allow-listed fields only; identity validation (single-subject: ticker+snapshot;
     cohort: as-of + filter/policy signature + cohort size);
   - `AgentContextUnavailableError` when the stage lacks full focused context;
   - `AgentContextInvariantError` on identity disagreement;
   - `context_reference = sha256:…`; `schema_id = tui_agent.<stage>.vN`.
2. **Gating** in TUI: `/` (and auto-agent U2) opens the cockpit on that stage only
   when the builder succeeds; else notify + refuse with a stage-appropriate hint.
3. **Wiring**: build the stage context on open; pass through `AgentTurnRequest`;
   register the stage under `ai.cockpit_multi_stage`.
4. **Tests** (offline, `pytest.mark.agent`): builder unit tests (happy + unavailable
   + invariant), gating refuse test, and a golden UX pilot for the stage.
5. **Docs**: journey SSOT §1 map row + generalize U5 note for the stage.

### Per-stage specifics

| # | Stage | `stage_kind` | Subject / bound | Notes |
|---|---|---|---|---|
| 1 | Accum screen board | `accum_screen` | Cohort: as-of, filter/policy signature, regime, **top-20** candidate summaries | See cohort bound below; not per-candidate Judge |
| 2 | View ticker | `view_ticker` | Single ticker **cache-only** dashboard facts | Reuse existing ticker dashboard projection shape where possible |
| 3 | View broker | `view_broker` | Broker desk view facts (desk code + shown view: top/flow/matrix) | Cache-only; no scrape |
| 4 | Pre-open screen | `preopen_screen` | Pre-open cohort: as-of, IEV/calendar/regime, **top-20** summaries | See cohort bound below; respect IDX NCP/pre-open semantics |
| 5 | Plan swing | `plan_swing` | Swing plan facts: setup, sizing inputs, evidence availability | Non-authoritative; plan stays deterministic |

**Cohort bound (D3) — stages 1 & 4, locked:**
- **N = 20**, ordered by the **screen's own existing deterministic rank** (never a
  cockpit-invented sort). Always emit `cohort_total` and `shown = min(20, cohort_total)`.
- **Cohort identity** = `canonical_reference(...)` (reuse `agent_tools.py` helper)
  over `(as_of_date, screen_kind, effective filter/policy params, universe
  reference, ranked member tickers)`. No new identity subsystem.
- **Invariant test:** per-candidate `as_of` == cohort `as_of`;
  `shown == min(20, cohort_total)`; members are the real screened output;
  disagreement → `AgentContextInvariantError`.

Commit theme per slice, e.g.:
`feat(agent): accum_screen cockpit destination + context contract (ADR-066)` ·
`feat(tui): open Research Cockpit on accum screen board` ·
`test(agent): accum_screen context + gating + golden pilot`

**Stop and report after each slice** unless told to continue.

---

## 4. Cross-cutting acceptance (every slice)

- [ ] Builder is pure, allow-listed, identity-validated, content-hashed, versioned schema.
- [ ] Missing/partial context → notify + refuse; never fabricated context.
- [ ] Cohort stages bounded (top-N); no full-board or per-candidate Judge leakage.
- [ ] No new tools/authority; L4 confirm + fail-safe unchanged; deterministic champion intact.
- [ ] `ai.cockpit_multi_stage=false` keeps `/` Judge-only.
- [ ] Offline agent suite + golden UX pilot + layer-boundary test green; Ruff green.

---

## 5. Verification commands

```bash
.venv/bin/python -m pytest -m "agent and not agent-live-call" -q
.venv/bin/python -m pytest tests/adapters/tui/test_agent_stage_ux_golden.py -q
.venv/bin/python -m pytest tests/architecture/test_layer_boundaries.py -q
ruff check src/ tests/
ruff format --check src/ tests/
git diff --check
```

---

## 6. Non-goals

- New tools, writes, fetch/refresh, external beyond ADR-065.
- Model-invented tools; cross-stage autonomous navigation (operator picks stage).
- Durable audit (Phase 4) / consequential tools (Phase 5).
- Changing L3/L4 budgets or state machine.
- Unbounded cohort projection or turning a board into a per-candidate Judge.

---

## 7. Completion record (fill when done)

- Activation ADR: ADR-066
- Implemented date:
- Slices landed (commits):
- Verification:

---

## 8. Copy-paste kickoff prompt

```text
Implement AI Research Cockpit multi-stage destinations per
tasks/backlog/implement_ai_research_cockpit_multi_stage_destinations.md and ADR-066.

Order: Slice 0 foundation (prove Judge bit-identical), then destinations in priority:
accum_screen → view_ticker → view_broker → preopen_screen → plan_swing.
Stop for review after each slice.

Hard rules:
- Per-stage context = pure, allow-listed, identity-validated, sha256 context_reference,
  versioned schema_id (copy agent_accumulation_context.py discipline).
- Missing context → notify + refuse; never fabricate. Cohort stages = bounded top-N.
- No new tools/authority; reuse L1–L4 unchanged; deterministic champion intact.
- Gate behind ai.cockpit_multi_stage (default false); Judge path stays bit-identical.
- Multi-commit contextual; AGENT_QUICKSTART lint gate; offline agent + golden UX green.

Read ADR-066 and the reference contract first.
```
