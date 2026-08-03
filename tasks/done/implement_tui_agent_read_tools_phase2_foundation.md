# Implement TUI Agent Phase 2 Foundation — Closed Registry and Orchestrator

Status: `IMPLEMENTED` — foundation verified on 2026-08-02; no production read
tool is registered

Source:

- [ADR-061](../../docs/adr/ADR-061-closed-read-tool-orchestration-for-context-agent.md)
- [`implement_tui_agent_read_tools_phase2.md`](implement_tui_agent_read_tools_phase2.md), Section 8.0

## 1. Task Metadata

- Task type: Feature / architecture foundation.
- Priority: Medium.
- Semantic classification: `NON_SEMANTIC` — optional agent orchestration and
  provider transport only; no canonical engine, Action, evidence authority,
  persistence, observation, label, tuning, or promotion behavior changes.
- AI usage: AI-assisted, optional, non-authoritative, and bypassable.
- Chosen decision: implement the closed Phase 2 contracts, registry, strict
  validation, deterministic state machine, canonical references, provider
  translation, and disabled-by-default config. **Implement this option only.**

## 2. Shared-worktree Start Gate

The 2026-08-02 start check found concurrent documentation changes in ADR-061,
the TUI AI roadmap, the Phase 2 epic, and the Hermes/OpenClaw roadmaps. Preserve
them and edit only the paths listed in Section 8. Do not clean, restore, stash,
or overwrite shared worktree changes.

Base re-vet: `b449d9f7` plus the local worktree. Phase 1 contracts, current TUI
composition, DeepSeek adapter, config loader, multi-surface inventory, and the
official DeepSeek tool-call contract were inspected before activation.

## 3. Problem Statement

Phase 1 has a provider-neutral one-call model boundary, but it cannot safely
accept a model-proposed tool call. There is no closed application registry,
typed call/result protocol, strict batch validation, deterministic two-call
state machine, tool-result reference, or independent tool rollback flag.

Adding a concrete read tool before those controls exist would let provider JSON
define execution behavior and would make it difficult to prove that malformed,
duplicate, unknown, over-budget, or second-round calls fail before execution.

## 4. Desired Outcome

The application can execute a one-turn Phase 2 state machine using recording
fake read tools:

1. validate the question and exact Phase 1 accumulation context;
2. make one provider call with `tool_choice=auto` and only registered tools;
3. accept either a final answer or one complete batch of at most two calls;
4. strictly validate the whole batch before executing any call;
5. execute valid calls sequentially under count, time, and byte budgets;
6. make exactly one final provider call with `tool_choice=none`;
7. reject any second tool proposal and return a typed failure.

Phase 1 remains byte-for-behavior compatible when tools are disabled or the
registry is empty. No production read tool is registered in this task.

## 5. Non-Goals

- No implementation or registration of `get_visible_cockpit_result`,
  `get_ticker_dashboard`, `judge_accumulation_ticker`, or `get_broker_desk`.
- No TUI tool trace or cancellation wiring; those follow after a real tool is
  independently activated.
- No CLI, Telegram, Hermes, OpenClaw, MCP, repository, SQLite, filesystem,
  browser, generic HTTP, shell, or Python tool.
- No fetch, refresh, write, persistence, session, transcript, audit, retry,
  parallel call, recursive loop, or provider fallback.
- No DeepSeek beta strict-mode dependency.
- No change to canonical signal, risk, MCE, TradeSetup, Action, evidence,
  observations, labels, tuning, or promotion.

## 6. Architecture Impact Assessment

- New dependency: No.
- Determinism affected: No canonical behavior; registry validation and state
  transitions are deterministic for the same inputs.
- Persistence affected: No.
- Schema change: No.
- CLI behavior affected: No.
- Adapter-owned orchestration/policy: No.
- Configuration: add `ai.tools_enabled`, default `false`; it is an operational
  rollback flag, not material scoring configuration.

```md
Layer plan:
- Domain: not touched.
- Application: frozen tool/model DTOs, read-tool port, closed registry, strict
  argument decoder, canonical result reference, and turn orchestrator.
- Infrastructure: translate typed definitions/tool calls/tool results through
  the existing DeepSeek adapter; expose disabled-by-default composition state.
- Adapter: not touched in this foundation.
```

## 7. Exact Contracts and Invariants

- Closed `AgentToolName` maximum set is exactly the four ADR-061 names.
- `AgentToolSideEffect` has only `NONE`.
- Tool definitions use frozen typed argument-field descriptors; provider JSON
  Schema dictionaries are infrastructure serialization only.
- Provider name and `arguments_json` are untrusted strings.
- Strict JSON rejects non-objects, duplicate keys, missing/extra fields,
  non-string values, unknown/unregistered tools, duplicate call IDs, duplicate
  canonical calls, and batches outside one-to-two calls.
- The registry is immutable after construction; it cannot register from model
  output or configuration.
- Execution receives a frozen typed argument object, never a generic mapping.
- Tool results use frozen typed payload/freshness/provenance DTOs and a canonical
  `sha256:` reference over the sorted compact envelope excluding the reference.
- Initial and final model responses are contradictory-state checked. The final
  call cannot return tools.
- Limits remain ADR-061 values: 2 provider calls, 2 sequential tools, no retry,
  2,000 question characters, 500 output tokens, 10 seconds per provider call,
  15 seconds total tool execution, 35 seconds total turn, 64 KiB total tool
  results.
- `ai.tools_enabled=false` or an empty registry supplies no tools and preserves
  Phase 1 zero-tool behavior.

## 8. Exact File Boundary

New files:

- `src/application/dto/agent_tools.py`
- `src/application/ports/agent_read_tool.py`
- `src/application/services/agent_tool_registry.py`
- `src/application/use_case/orchestrate_agent_turn_use_case.py`
- `tests/application/dto/test_agent_tools.py`
- `tests/application/services/test_agent_tool_registry.py`
- `tests/application/use_case/test_orchestrate_agent_turn_use_case.py`

Existing files:

- `src/application/dto/accumulation_agent.py`
- `src/application/ports/agent_model.py`
- `src/application/ports/__init__.py`
- `src/infrastructure/ai/deepseek_agent_model.py`
- `src/infrastructure/composition/agent_model.py`
- `src/infrastructure/config/app_config.py`
- `config/default.yaml`
- `tests/infrastructure/ai/test_deepseek_agent_model.py`
- `tests/infrastructure/composition/test_agent_model.py`
- focused config/architecture tests only if required
- this task and the Phase 2 epic completion/activation records

Any TUI, domain, repository, provider, persistence, or additional documentation
file is out of scope and requires a separately reported task amendment.

## 9. AI Usage Declaration

AI is used only to propose one closed read-tool batch and phrase a final answer.
Application validation and the immutable registry decide what executes. With AI
or tools disabled, no tool definition is supplied and no deterministic workflow
depends on the model.

## 10. Risk, Signal, and Evidence Authority Considerations

- Affected decision components: none.
- ENTER/WATCH/AVOID producers: unchanged.
- Evidence authority and tuning eligibility: unchanged.
- Tool output is commentary context only and cannot enter a deterministic
  engine, persistence selector, corpus, label, or promotion path.

## 11. Data and Persistence

- Reads: the exact in-memory accumulation context and recording fake tool data
  in tests.
- Writes: none, except source/config/docs changed by implementation.
- Runtime persistence/schema: none.
- No source-equivalence claim is introduced because no production tool is
  registered.

## 12. Negative Tests

- Unknown/unregistered names and invented definitions cannot execute.
- Malformed/non-object/duplicate-key JSON and missing/extra/non-string fields
  fail the complete batch before any fake records execution.
- Duplicate IDs and duplicate canonical calls fail preflight.
- Over-count and over-byte batches fail closed.
- Calls execute sequentially in provider order.
- Provider proposing tools on the final call fails without a third call.
- Tool-result instruction text cannot authorize another call.
- Timeout/cancellation stops new calls and discards late results.
- AI-disabled, tools-disabled, and empty-registry paths make no tool-enabled
  request and preserve Phase 1 behavior.
- Provider transport never relies on beta strict mode and validates malformed
  tool response shapes.

## 13. Acceptance Criteria

- [x] All Section 7 contracts and Section 12 negative tests are implemented.
- [x] No production read tool is registered.
- [x] Phase 1 tests remain green and tools are disabled by default.
- [x] Application imports no infrastructure or adapter module.
- [x] Provider dictionaries remain inside infrastructure.
- [x] Dedicated tests are marked `pytest.mark.agent`.
- [x] Focused agent, provider, composition, config, and architecture tests pass.
- [x] Full agent, TUI, full-suite, and whole-repo Ruff gates pass before close.
- [x] `git diff --check` passes; implementation commit is recorded below.

## 14. Testing Expectations

All correctness tests run offline with recording models/tools and an injected
clock/executor seam where needed. A live DeepSeek call is optional and never a
completion gate.

```bash
.venv/bin/python -m pytest -m "agent and not tui"
.venv/bin/python -m pytest -m "agent and tui"
.venv/bin/python -m pytest -m agent
.venv/bin/python -m pytest tests/architecture/test_layer_boundaries.py -q
.venv/bin/python -m pytest tests/adapters/shared/test_multi_surface_inventory.py -q
.venv/bin/python -m pytest -m tui
.venv/bin/python -m pytest
ruff check src/ tests/
ruff format --check src/ tests/
git diff --check
```

## 15. Documentation Impact

- README: not required until the tool runtime is user-visible.
- New config option: `ai.tools_enabled` in shipped default config.
- Limitation: foundation only; zero production tools registered.

## 16. Agent Execution Instructions

Implement this foundation only. Stop rather than registering a production tool,
moving policy into infrastructure/TUI, weakening a budget, adding a retry, or
accepting a generic mapping at execution. Protect all concurrent worktree
changes and stage only owned files if committing is later requested.

## 17. Completion Record

- Base commit: `b449d9f7`
- Implemented date: 2026-08-02
- Commit: `825ce241`
- Focused verification:
  - `pytest -m "agent and not tui" -q`: 53 passed
  - architecture + multi-surface inventory: 9 passed
  - `pytest -m "agent and tui" -q`: 3 passed
  - `pytest -m agent -q`: 56 passed
- Full verification:
  - `pytest -m tui -q`: 55 passed, 1 skipped
  - `pytest -q`: 6144 passed, 1 skipped
  - `ruff check src/ tests/`: passed
  - `ruff format --check src/ tests/`: passed
  - `git diff --check`: passed
- Notes:
  - Effective tool enablement remains false because the foundation registers no
    production tool, even when the independent config flag is requested.
  - Whole-repo Ruff format found and mechanically repaired pre-existing
    committed drift in
    `tests/application/services/test_lean_observation_identity.py`; no behavior
    changed.
