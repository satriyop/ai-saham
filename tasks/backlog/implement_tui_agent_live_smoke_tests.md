# Goal Instruction — Implement TUI Agent Live Smoke Tests (Journey SSOT)

**Status:** `READY FOR AGENT`  
**Audience:** Implementation agent (any coding agent working in this repo)  
**Authority for checklist content:**  
[`docs/roadmap/tui_ai_agent_implementation_journey.md`](../../docs/roadmap/tui_ai_agent_implementation_journey.md)  
**Architecture:** ADR-060, ADR-061, ADR-063  
**Do not invent new product behavior** beyond making the documented journey
verifiable under an opt-in live marker.

---

## 0. Mission

Implement **opt-in live smoke tests** that exercise the **full TUI AI agent
journey as currently shipped (Phases 0–3)**, using real credentials / network
only when the operator intentionally enables them.

Hard requirements from the product owner:

1. **Every live test must be marked `agent-live-call`.**
2. **Coverage maps to the entire journey SSOT up to current tip** (through
   Phase 3 sessions), not a single happy-path only.
3. **If you find bugs while implementing or running tests, fix them and commit
   the fix** (separate from pure-test commits when possible).
4. **Use multiple contextual commits** (not one mega-commit).

Offline `pytest -m agent` suite remains the default CI gate. Live tests must
**never** run in default CI without an explicit opt-in.

---

## 1. Preflight (mandatory)

```md
Confirm:
- Architecture layer boundaries (hexagonal; adapters thin).
- Deterministic-first; AI non-authoritative.
- No guardrail bypass.
- Lint Gate: whole-repo `ruff check src/ tests/` and `ruff format --check src/ tests/`.

Layer plan (expected for this task):
- Domain: not touched (unless a real bug forces a pure domain fix — justify).
- Application: only if a journey bug or missing test seam is found.
- Infrastructure: only for safe live-test harness / marker / skip helpers if needed.
- Adapter: TUI test harness only; no new agent policy in TUI.
- Tests/docs: primary delivery surface.
```

Read before coding:

1. `AGENT_QUICKSTART.md` (lint, worktree, markers).
2. `docs/roadmap/tui_ai_agent_implementation_journey.md` (SSOT — §2 profiles, §4 checklist).
3. Existing agent tests under `tests/**` marked `agent` (do not duplicate offline
   contract tests; live suite is complementary).
4. `pyproject.toml` `[tool.pytest.ini_options] markers`.

Check `git status --short` and do not destroy unrelated dirty work.

---

## 2. Marker contract (`agent-live-call`)

### 2.1 Register the marker

In `pyproject.toml` markers list, add (wording may be tightened, meaning fixed):

```text
agent-live-call: Opt-in live network/provider tests for the TUI AI agent journey.
  Requires explicit selection (e.g. -m agent-live-call). Must skip by default when
  credentials, AI flags, or local data preconditions are missing. Never run in
  default CI. May also carry agent and/or tui when applicable.
```

### 2.2 Selection rules

| Command | Intent |
|---|---|
| `pytest -m agent` | Existing offline agent suite (**must stay green without live**) |
| `pytest -m agent-live-call` | Live smoke only |
| `pytest -m "agent and not agent-live-call"` | Offline agent only (CI-safe) |
| default full suite | **Must not** collect-and-run live calls |

### 2.3 Default skip policy (required)

Each live test (or a shared fixture) must **skip**, not fail, when any of these
are missing:

- `DEEPSEEK_API_KEY` (process env or the same local-env path composition already uses).
- Config path with `ai.enabled=true` and `ai.provider=deepseek` (or test-local
  AiConfig equivalent).
- For tool profiles: `ai.tools_enabled=true` where the test claims tools.
- For session profiles: `ai.session_enabled=true` where the test claims sessions.
- For data-dependent cases: existing local DB path with enough cache for the
  chosen ticker/desk (document the symbol assumptions; prefer env overrides
  like `AI_SAHAM_LIVE_TICKER`, `AI_SAHAM_LIVE_BROKER`).

Optional hard gate env (recommended):

```text
AI_SAHAM_AGENT_LIVE=1
```

If unset, all `agent-live-call` tests skip with a one-line reason.

### 2.4 Dual-marking

- Live application/orchestrator tests: `@pytest.mark.agent` +
  `@pytest.mark.agent-live-call`.
- Live Textual full-app mounts: also `@pytest.mark.tui` (or allow auto-tag under
  `tests/adapters/tui` if `run_test` is used).

---

## 3. Coverage matrix (must map 1:1 to journey SSOT)

Implement tests (or clearly named subtests/param cases) that cover **every
profile and checklist block** in
`tui_ai_agent_implementation_journey.md` §4. Use this matrix as the DoD.

### Profile A — Offline / AI off (live-marker optional)

These may remain offline under `agent` only **if** they never hit the network.
If you put them under `agent-live-call`, they must still not call the provider.

| ID | Behavior under test |
|---|---|
| A1–A4 | Cockpit usable without AI; no crash on prompt chrome; invalidate safe |

Minimum: one pilot or composition proof that with `enabled=false` **zero**
provider HTTP occurs (mock network or assert no client construct).

### Profile B — Phase 1 one-turn (live)

| ID | Behavior under test |
|---|---|
| B2–B4 | Real provider one-shot on full Judge candidate → SUCCESS/PARTIAL answer, non-empty text, `context_reference` present |
| B5 | With tools disabled: no tool_results required |
| B6 | Cancel / generation invalidate: late result must not paint wrong stage (TUI pilot with controlled timing if possible) |
| B7 | Limited row without full source: UNAVAILABLE path, no dispatch |

Live call: **at least one** real `DeepSeek` generate for a frozen
`AccumulationCandidate` built from live/local screen path **or** a recorded
full candidate loaded from local DB via existing use cases.

### Profile C — Phase 2 tools (live)

| ID | Behavior under test |
|---|---|
| C0 | Composition with tools_enabled + DB registers expected tool subset |
| C1–C4 | End-to-end turn **allowed** to invoke tools (model-driven); assert if any tool ran: only ADR-061 names, statuses legal, result_reference `sha256:…` |
| C5 | Tool trace fields present on `AgentTurnResult` |
| C6 | Deterministic Action on candidate unchanged by tool execution (identity of trade_setup.action before/after) |
| C7 | Missing DB / missing desk cache: fail-soft UNAVAILABLE, no schema create |
| C8 | tools off → no tool definitions path |

Do **not** hard-require the model to always call a specific tool (non-deterministic).
Instead:

- Prefer **direct live tool execution** tests for each of the four tools against
  real local cache (still `agent-live-call` if they touch real DB paths that are
  environment-specific; if pure offline RO composition already exists, do not
  re-litigate offline — add live only for end-to-end orchestrator+provider).
- For provider+tools: assert **schema safety** of any tools that did run; allow
  zero tools if model answered directly, and assert answer non-empty.

Required tool surface coverage (at least one live path each, skip if cache missing):

1. `get_visible_cockpit_result`  
2. `get_ticker_dashboard`  
3. `judge_accumulation_ticker`  
4. `get_broker_desk` (at least one view, prefer `SHOW`)

### Profile D — Phase 3 sessions (live)

| ID | Behavior under test |
|---|---|
| D1 | session_enabled wrap present when certified DeepSeek |
| D2–D3 | Two sequential live questions, same candidate: second turn has `session_id`, `turn_sequence>=2` |
| D4 | After context identity change (different context_reference), pack warnings / historical handling still produces safe status |
| D5–D6 | `reset_session()` then next turn sequence 1 with new session_id |
| D7 | Document-only or process-level note: in-memory only (optional unit; no live needed) |
| D8 | session_enabled false → no session_id continuity |
| D9 | Non-deepseek provider → no certified multi-turn pack |

TUI path: at least one pilot for prompt commands  
`/reset` · `session reset` · `reset session` invoking `reset_session` on runner.

### Profile N — Negatives / safety (live where meaningful)

| ID | Behavior under test |
|---|---|
| N1 | Missing key → UNAVAILABLE / safe error; no crash |
| N2 | Unsupported provider → no silent fallback |
| N3 | Cancel / wrong lineage paint rejection (TUI) |
| N4–N5 | Policy: no tool outside registry; answer may refuse trade advice (soft assert: no requirement to match exact prose) |
| N6–N7 | No audit table writes; Action authority unchanged offline without AI |

---

## 4. Suggested layout

```text
tests/agent_live/                          # preferred dedicated package
  __init__.py
  conftest.py                              # skip gates, fixtures, env
  test_live_profile_b_one_turn.py
  test_live_profile_c_tools.py
  test_live_profile_d_session.py
  test_live_profile_n_safety.py
  test_live_tui_journey.py                 # Textual pilots that need live runner

# OR under tests/adapters/tui/ + tests/application/… with clear live_ prefix
```

Prefer **one package** so `pytest -m agent-live-call` is easy to document.

`conftest.py` should provide:

- `live_ai_config` / `live_agent_composition`
- `live_candidate` (from local screen/judge path or skip)
- `require_live_env` fixture that skips with clear message
- Network/time budgets (hard timeouts; no hang)

---

## 5. Bugs found during implementation

If a live or pilot test exposes a product bug:

1. **Minimize fix** at the correct layer (application/policy vs thin adapter).  
2. **Do not** weaken tests or ADRs to greenwash.  
3. **Commit the fix** before or as its own commit (see §6).  
4. Note the bug + fix in the PR/completion record.  
5. Re-run offline `pytest -m agent` and affected live tests.

Forbidden “fixes”:

- Disabling lint or markers to pass CI  
- Broadening tool registry without ADR  
- Persisting sessions/audit “to make smoke easier”  
- Calling CLI presenters from tools  

---

## 6. Multi-commit plan (contextual)

Use **separate commits** with clear messages. Suggested sequence:

| Order | Commit theme | Contents |
|---|---|---|
| 1 | `test(agent): register agent-live-call marker` | `pyproject.toml` marker only |
| 2 | `test(agent): add live smoke harness and skip gates` | `conftest`, fixtures, env gate |
| 3 | `test(agent): live one-turn journey profile B` | Phase 1 live tests |
| 4 | `test(agent): live closed-tool journey profile C` | Four tools + orchestrator safety |
| 5 | `test(agent): live session journey profile D` | Multi-turn + reset |
| 6 | `test(agent): live TUI pilot for session reset and paint safety` | Textual |
| 7 | `docs(agent): map live smoke tests to journey SSOT` | Link test module paths in journey §4 or new § |
| *as needed* | `fix(agent): …` | **Bugfix only**, one concern per commit |

Rules:

- Do not mix large refactors with test-only commits.  
- Fix commits must pass Ruff + offline agent suite.  
- Live suite may remain skip-heavy on CI machines without secrets.

---

## 7. Verification gates

### Offline (must pass before merge)

```bash
.venv/bin/python -m pytest -m "agent and not agent-live-call" -q
.venv/bin/python -m pytest -m agent -q   # still green; live tests skipped
.venv/bin/ruff check src/ tests/
.venv/bin/ruff format --check src/ tests/
git diff --check
```

### Live (operator machine only)

```bash
export AI_SAHAM_AGENT_LIVE=1
export DEEPSEEK_API_KEY=…   # or local env file already supported
# ensure ai.enabled / tools_enabled / session_enabled as needed for profile

.venv/bin/python -m pytest -m agent-live-call -q --tb=short
```

Optional narrow:

```bash
.venv/bin/python -m pytest -m "agent-live-call and tui" -q
```

### Cost / safety

- Cap live provider calls (budget: prefer ≤ ~10–15 provider calls for full
  profile suite; reuse composition).  
- Timeouts on all HTTP.  
- Never log API keys or full raw provider payloads in assertions/output.  
- No production trading, no write tools, no fetch/scrape from agent path.

---

## 8. Documentation updates (same task)

Update
[`docs/roadmap/tui_ai_agent_implementation_journey.md`](../../docs/roadmap/tui_ai_agent_implementation_journey.md):

- Add a short **§ Automated live smoke** pointing to `pytest -m agent-live-call`
  and the new test package.
- Optionally annotate §4 checklist rows with test node ids once stable.
- Changelog row for this landing.

Do **not** fork a second smoke checklist.

---

## 9. Acceptance criteria

- [ ] Marker `agent-live-call` registered and documented.  
- [ ] Default / CI collection path does not execute live provider calls.  
- [ ] Journey Profiles **A–D** and **N** covered as specified in §3 (skip-only
      when preconditions missing; no silent pass).  
- [ ] All four ADR-061 tools have at least one live-or-local-cache smoke path.  
- [ ] Phase 3 session continuity + reset covered (app and at least one TUI
      entrypoint for reset commands).  
- [ ] Offline `pytest -m agent` remains green without credentials.  
- [ ] Ruff whole-repo gate green.  
- [ ] Multi-commit history is contextual (§6).  
- [ ] Any product bugs found are fixed and committed.  
- [ ] Journey SSOT updated with how to run live smoke.

---

## 10. Explicit non-goals

- Phase 4 audit persistence / Phase 5 write tools.  
- Hermes / OpenClaw / Telegram.  
- Making live tests mandatory in CI.  
- Recording/cassetting provider traffic as the only path (optional later).  
- Replacing the offline `agent` suite.  
- Expanding tool allowlist or raising ADR budgets.

---

## 11. Completion record (fill when done)

- Implemented date:  
- Commits:  
- Offline agent:  
- Live command used:  
- Live results (PASS/SKIP/FAIL by profile):  
- Bugs fixed (if any):  

---

## 12. Copy-paste agent kickoff prompt

Use the following as the user message to the implementing agent:

```text
Implement tasks/backlog/implement_tui_agent_live_smoke_tests.md.

Hard requirements:
1. Register and use pytest marker agent-live-call on every live test.
2. Cover the full journey SSOT in docs/roadmap/tui_ai_agent_implementation_journey.md
   through Phase 3 (profiles A–D + N).
3. If you find product bugs, fix them and commit the fix.
4. Use multiple contextual commits (marker → harness → B → C → D → TUI → docs;
   fix commits separate).

Follow AGENT_QUICKSTART.md and the task’s layer plan. Live tests must skip by
default without AI_SAHAM_AGENT_LIVE=1 and credentials. Offline pytest -m agent
must stay green without network. Whole-repo ruff check/format gates required.
Do not start Phase 4/5 or expand the tool registry.
```
