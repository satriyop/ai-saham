# Implement TUI Agent Phase 2.1 — Visible Cockpit Result Tool

Status: `IN PROGRESS`

Source:

- [ADR-061](../../docs/adr/ADR-061-closed-read-tool-orchestration-for-context-agent.md)
- [`implement_tui_agent_read_tools_phase2.md`](implement_tui_agent_read_tools_phase2.md), Section 8.1

## 1. Task Metadata

- Task type: Feature / application read projection / TUI integration.
- Priority: Medium.
- Semantic classification: `NON_SEMANTIC` — this optional tool returns the
  exact already-visible deterministic result as non-authoritative commentary
  context; it cannot affect scoring, Action, persistence, evidence, observation,
  label, tuning, or promotion behavior.
- AI usage: optional, non-authoritative, and bypassable.
- Chosen decision: implement and register only
  `get_visible_cockpit_result`. **Implement this option only.**

## 2. Shared-worktree Start Gate

Start from clean commit `ef4e9205` with Phase 2 foundation commits `825ce241`
and `5958a361` already present. Preserve unrelated changes and do not run
destructive cleanup.

## 3. Problem Statement

The Phase 2 foundation can validate and orchestrate closed read tools, but it
registers no production tool. The model therefore cannot request the exact
deterministic result already visible in the current TUI turn, and the TUI has no
operator-visible ordered tool trace.

## 4. Desired Outcome

When both AI and tool flags are enabled and DeepSeek is available, advertise
one tool. It accepts the current visible result reference, compares it to a
frozen turn-local context, and returns that same bounded accumulation context.
Any missing, malformed, stale, or unequal reference fails closed. Successful and
partial turns render a compact ordered trace without exposing arguments or raw
payloads.

## 5. Non-Goals

- No other Phase 2 tool, CLI, Telegram, Hermes, OpenClaw, or MCP exposure.
- No recomputation, repository, SQLite, filesystem, network, provider, refresh,
  fetch, write, persistence, session, transcript, audit, retry, or fallback.
- No generic context/query tool and no adapter-rendered result payload.
- No canonical engine, policy, evidence-authority, or config-identity change.

## 6. Architecture Impact Assessment

- New dependency: No.
- Determinism affected: No canonical behavior; exact reference equality is
  deterministic.
- Persistence/schema/CLI affected: No.
- Configuration: existing `ai.tools_enabled`; default remains `false`.

```md
Layer plan:
- Domain: not touched.
- Application: frozen turn-local tool context, exact argument/result DTOs, and
  read-only tool implementation; registry/orchestrator pass context explicitly.
- Infrastructure: register the one approved tool only when both flags and the
  supported provider are available.
- Adapter: render the stable ordered tool name/status/reference trace in the
  existing TUI commentary card.
```

## 7. Exact Contracts and Invariants

- Argument schema is `agent_tool.visible_cockpit.args.v1`, with exactly one
  lowercase canonical `sha256:<64 hex>` `visible_result_reference` string.
- Result schema is `agent_tool.visible_cockpit.result.v1`; data wraps the exact
  `AgentAccumulationContext` object captured for this turn.
- Tool execution context is frozen and passed per invocation; the registry and
  tool remain stateless across turns.
- Exact reference match returns `SUCCESS`, typed freshness/provenance, and the
  captured context. Unequal reference returns `UNAVAILABLE`, no data, no
  reconstruction.
- Tool timeout is 100 ms and result maximum is 32 KiB.
- Effective tools require `ai.enabled=true`, `ai.tools_enabled=true`, supported
  DeepSeek composition, valid credentials, and this registered tool.
- TUI trace preserves execution order and shows only stable tool name, status,
  and result reference. `PARTIAL` still shows the grounded answer and metadata.

## 8. Exact File Boundary

New files:

- `src/application/dto/agent_tool_context.py`
- `src/application/services/agent_visible_cockpit_tool.py`
- `tests/application/services/test_agent_visible_cockpit_tool.py`
- this task file

Existing files:

- `src/application/ports/agent_read_tool.py`
- `src/application/services/agent_tool_registry.py`
- `src/application/use_case/orchestrate_agent_turn_use_case.py`
- `src/infrastructure/composition/agent_model.py`
- `src/adapters/tui/widgets/agent_commentary.py`
- focused agent registry/orchestrator/composition/TUI tests
- Phase 2 epic completion record

Any domain, repository, persistence, provider transport, or unrelated adapter
file is out of scope.

## 9. AI Usage Declaration

The model may propose the one closed call and phrase an answer. Application
types, exact reference equality, and the immutable registry decide execution.
No model output becomes deterministic authority.

## 10. Risk, Signal, and Evidence Authority Considerations

- Decision components and ENTER/WATCH/AVOID producers: unchanged.
- Evidence authority and tuning eligibility: unchanged.
- Tool output is commentary context only and cannot re-enter canonical logic.

## 11. Data and Persistence

- Reads: exact frozen in-memory accumulation context for the current turn only.
- Runtime writes/schema: none.
- Source reference: the current context reference; no equivalence inference.

## 12. Negative Tests

- Malformed and unequal references cannot return data.
- Execution receives the exact current context rather than registry state.
- Disabled/missing-provider composition exposes no tool path.
- The tool has no repository/provider/filesystem dependency.
- TUI trace does not expose arguments/data and preserves result order.
- Partial tool turns display the answer, metadata, warning, and trace.

## 13. Acceptance Criteria

- [ ] Exact contracts and negative tests above are implemented.
- [ ] Only `get_visible_cockpit_result` is registered.
- [ ] Phase 1 behavior remains when tools are not effectively enabled.
- [ ] Application imports no infrastructure/adapter module.
- [ ] Dedicated tests carry `pytest.mark.agent`.
- [ ] Agent, TUI, architecture, full-suite, Ruff, and diff gates pass.
- [ ] Implementation commit and verification are recorded below.

## 14. Testing Expectations

```bash
.venv/bin/python -m pytest -m "agent and not tui" -q
.venv/bin/python -m pytest -m "agent and tui" -q
.venv/bin/python -m pytest tests/architecture/test_layer_boundaries.py -q
.venv/bin/python -m pytest -m tui -q
.venv/bin/python -m pytest -q
.venv/bin/ruff check src/ tests/
.venv/bin/ruff format --check src/ tests/
git diff --check
```

## 15. Documentation Impact

Update the Phase 2 epic status/completion record. No README change is needed;
the existing disabled-by-default config and TUI surface remain authoritative.

## 16. Agent Execution Instructions

Stop rather than adding a read/recompute seam, storing turn context on the tool
or registry, exposing raw payloads, weakening exact reference checks, or
activating another tool.

## 17. Completion Record

- Base commit: `ef4e9205`
- Implemented date:
- Commit:
- Verification:
