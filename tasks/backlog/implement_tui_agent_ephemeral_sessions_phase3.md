# Implement TUI Agent Phase 3 — Ephemeral Sessions and Hardening

Status: `IMPLEMENTED` — verified on 2026-08-03

Source:

- [ADR-063](../../docs/adr/ADR-063-ephemeral-agent-session-and-context-budget.md)
  (binding contract authority)
- [ADR-060](../../docs/adr/ADR-060-read-only-tui-context-agent.md),
  [ADR-061](../../docs/adr/ADR-061-closed-read-tool-orchestration-for-context-agent.md)
- [`docs/roadmap/roadmap_tui_ai_agent_implementation.md`](../../docs/roadmap/roadmap_tui_ai_agent_implementation.md),
  Phase 3
- Supersedes parked
  [`parked_tui_agent_ephemeral_sessions_phase3.md`](parked_tui_agent_ephemeral_sessions_phase3.md)

## 1. Task Metadata

- Task type: Feature / hardening
- Priority: Medium after Phase 2 close
- Semantic classification: `NON_SEMANTIC` — session state may influence only
  agent commentary/context retrieval, never deterministic analysis or persisted
  market/learning state.
- AI usage: optional multi-turn commentary over exact result references.
- Chosen decision: add bounded in-memory sessions only, per ADR-063. **Implement
  this option only.**

## 2. Shared-Worktree Start Gate

Start from a clean commit after Phase 2 epic close (`2f1fa01d` lineage or later).
Re-vet Phase 1/2 orchestrator, registry, TUI generation lineage, and ADR-063
before coding. Preserve unrelated worktree changes; no destructive cleanup.

## 3. Problem Statement

Independent one-turn requests cannot safely answer follow-ups without resending
context. Naively retaining chat history risks binding old facts to a new ticker,
summarizing away authoritative fields, exceeding model context, or painting a
late answer into the wrong cockpit stage.

## 4. Desired Outcome

During one `saham tui` process, with `ai.enabled` and `ai.session_enabled`, an
operator may ask bounded follow-up questions. The application session retains
typed turn metadata and exact result references; older conversational prose may
be summarized under ADR-063 P0–P4 budgets. Session state disappears on process
exit. Stale, cancelled, overflow, evicted, and reset states are explicit.

## 5. Non-Goals

- No durable conversation or audit persistence (Phase 4).
- No cross-device/user synchronization.
- No autonomous preference inference or storage.
- No background/proactive agent, scheduler, notification, or wake-up.
- No new read/write tools (Phase 5).
- No provider fallback or authority change.
- No model-authored summary replacing exact Action/freshness/provenance fields.
- No raising ADR-061 per-turn tool/provider ceilings.

## 6. Architecture Impact Assessment

```md
Layer plan:
- Domain: not touched.
- Application: session DTOs/port, in-memory session store, compatibility
  predicate, P0–P4 packing, compression policy, session-aware turn entry that
  reuses the existing one-turn orchestrator + closed tool registry.
- Infrastructure: config flag + optional provider capability certification
  metadata only; no persistence.
- Adapter: session reset UX, transcript/stale banners, generation cancellation
  (existing), meta display of session/turn ids; no policy ownership.
```

- New dependency: No by default.
- Persistence affected: No.
- CLI behavior affected: No.
- Deterministic authority affected: No.

## 7. Exact Contracts (ADR-063)

Implement frozen equivalents of:

- `AgentSessionId`, `AgentTurnId`, monotonic `turn_sequence`
- `AgentSessionState` (typed references + bounded commentary; no raw SDK dumps)
- compatibility → `FRESH | STALE | INCOMPATIBLE`
- P0–P4 packing with locked budgets:

| Limit | Value |
|---|---:|
| Active sessions / process | 1 |
| Max turns / session | 8 |
| Full Q/A turns retained | 3 |
| Fresh tool projections retained | 4 |
| Packed context | 24 KiB |
| Older-commentary summary | 1,500 chars |
| In-flight turns | 1 |

- `ai.session_enabled` default `false` (exact Phase 1/2 when false)
- capability certification identity (provider, model, prompt version, tool-schema
  version, eval-suite version, date, pass/fail)
- statuses: success/partial/failed/unavailable/cancelled plus explicit overflow,
  eviction, reset, and stale-reference messaging

## 8. Exact File Boundary (expected)

Likely new:

- `src/application/dto/agent_session.py` (or extend accumulation_agent DTOs)
- `src/application/services/agent_session_*.py` / session port + in-memory impl
- `src/application/use_case/*session*` or session-aware wrapper around
  `AgentTurnOrchestrator`
- focused `pytest.mark.agent` tests
- this task file

Likely touched:

- `src/infrastructure/composition/agent_model.py`
- `src/infrastructure/config/app_config.py` (and loader) for `ai.session_enabled`
- `src/adapters/tui/` prompt/commentary/generation wiring only
- `docs/roadmap/roadmap_tui_ai_agent_implementation.md` status row

Out of scope: domain engines, SQLite schemas, new tools, audit tables.

## 9. Negative Tests

- Older generation cannot paint after focus/navigation/reset.
- Same ticker with different context digest/as-of cannot reuse stale facts.
- Different ticker cannot inherit candidate facts or tool results.
- Summarization cannot change Action, scores, dates, warnings, freshness, or
  provenance.
- Overflow cannot silently drop P0/P1 facts.
- Uncertified model cannot gain tool capability.
- Process restart has no prior session rows/files/directories.
- Session state never feeds canonical workflows or persistence.
- `ai.session_enabled=false` is bit-identical one-turn Phase 2 behavior for
  identical inputs (no retained state across questions).

## 10. Acceptance Criteria

- [x] Follow-ups work within one process using exact compatible references.
- [x] Stale, cancelled, overflow, evicted, and reset states are explicit.
- [x] Context compression preserves authority-bearing fields in typed form.
- [x] No persistent side effect occurs.
- [x] Provider capability is identity-bound and does not grant authority.
- [x] Offline/AI-disabled cockpit behavior is unchanged.
- [x] Dedicated tests use `pytest.mark.agent`.
- [x] Focused, architecture, TUI, agent, Ruff, and `git diff --check` gates pass.
- [x] Completion record filled below.

## 11. Testing Expectations

```bash
.venv/bin/python -m pytest -m agent -q
.venv/bin/python -m pytest -m "agent and tui" -q
.venv/bin/python -m pytest tests/architecture/test_layer_boundaries.py -q
.venv/bin/python -m pytest -m tui -q
.venv/bin/ruff check src/ tests/
.venv/bin/ruff format --check src/ tests/
git diff --check
```

## 12. Do Not Interpret This As

- Do not add SQLite “just for convenience.”
- Do not treat an LLM-generated summary as session truth.
- Do not keep unlimited raw history in memory.
- Do not add proactive/background operation.
- Do not begin audit persistence from this task.
- Do not register new tools.

## 13. Completion Record

- Activation ADR: ADR-063 (2026-08-03)
- Implemented date: 2026-08-03
- Commit(s): see git history after `e5587381` (implementation + docs)
- Verification:
  - `pytest -m agent -q`: 130 passed
  - focused session pack/use-case/composition/orchestrator/explain/commentary: 44 passed
  - `ruff check src/ tests/`: passed
  - `ruff format --check src/ tests/`: passed
  - `git diff --check`: passed
  - Runtime: `ai.session_enabled` default false; certified DeepSeek path only;
    TUI `/reset` / `session reset`; pack includes non-authoritative history +
    exact references only
