# Goal Instruction — Fix AI Research Cockpit L4 Confirm Fail-Open + Budget Drift

## Completion record (2026-08-03)

**Status:** `DONE` — branch `fix/ai-research-cockpit-l4-confirm-failopen`.

| Finding | Resolution | Layer |
|---|---|---|
| F1 | Removed the fail-open TypeError retry ladders in `tui/main.py` and `SessionAwareAgentTurnUseCase._call_inner`; both now probe the callable signature once and invoke exactly once (no turn re-run, approval never dropped). | Adapter + Application |
| F2 | `AgentTurnOrchestrator._run_batch`: a PER_CALL tool with `approval is None` fails closed with a distinct `TOOL_NO_APPROVER` skip; never executes. | Application |
| F3 | Denied / no-approver consent skips no longer seed `seen_identities` (re-proposal allowed) nor count toward `tools_used`. | Application |
| F4 | Cross-round `_l3_path` byte accounting now excludes consent skips, matching the in-batch rule (only executed results count). | Application |
| F5 | `_looks_like_planning_only` documented as a best-effort soft guard (comment only). | Application |
| F6 | ADR-065 notes `PENDING_APPROVAL` is a synchronous approval-callback seam, not an `AgentTurnStatus` value. | Docs |

Commits: `d3498908` (F2/F3/F4/F5), `07a79984` (F1), `c803bd64` (tests),
docs commit (F6 + journey changelog). New offline regression tests:
`test_no_approver_fails_closed_and_continues`, `test_side_effect_none_tool_runs_without_approver`,
`test_typeerror_midturn_fails_once_without_rerun`, `test_deny_then_different_tool_continues_and_executes`,
`test_deny_then_repropose_same_tool_is_not_duplicate` (orchestrator);
`test_typeerror_in_inner_runs_exactly_once`, `test_inner_without_callback_kwargs_still_invoked_once` (session-aware).

Verification: `pytest -m "agent and not agent-live-call"` (166 passed), golden UX
pilot green, `ruff check`/`ruff format --check` clean, `git diff --check` clean.
Pre-existing unrelated arch violation (`agent_ro_data_query_tool.py` imports
sqlite3) confirmed at baseline HEAD `785247b8` and left untouched.

---

**Status:** `READY FOR AGENT`
**Audience:** Implementation agent (any coding agent in this repo)
**Product term:** **AI Research Cockpit** (`/`) — use this name in code, commits, docs.
**Source review:** L3/L4 conformance review against ADR-064/ADR-065 (2026-08-03).

**Binding architecture (read before coding):**

| Doc | Role |
|---|---|
| [ADR-064](../../docs/adr/ADR-064-ai-research-cockpit-bounded-multi-round-tools.md) | L3 multi-round budgets + state machine |
| [ADR-065](../../docs/adr/ADR-065-ai-research-cockpit-external-and-ro-data-l4.md) | L4 confirm, deny/fail rules, fail-safe |
| Journey SSOT | [`docs/roadmap/tui_ai_agent_implementation_journey.md`](../../docs/roadmap/tui_ai_agent_implementation_journey.md) |
| Completed L3/L4 records | `tasks/done/implement_ai_research_cockpit_*.md` |

**Do not invent product behavior.** If ADR and code conflict, stop and ask. If ADR
is silent, choose the **safer, smaller** (fail-closed) option and document it.

---

## 0. Mission

The L3/L4 runtime landed and is largely faithful to ADR-064/065, but a review
found a **consent fail-open path** and some **budget-accounting drift**. Fix them
so the cockpit is lockable. **No new capabilities. No ADR changes** (except the
one-line documentation note in F6). Deterministic Action authority is untouched.

Hard rules:

- Consent is a **fail-closed** gate. When an elevated/external (`side_effect != NONE`,
  `approval=PER_CALL`) tool cannot obtain an explicit operator approval, it is
  **skipped/denied**, never executed.
- **Never re-run a turn** that has already started executing (no double provider
  spend, no duplicate tool calls, no second network egress).
- Deny ≠ turn death (ADR-065 decision 6): a denied tool skips and the turn continues.
- Multi-commit, contextual commits; one `fix(...)`/`test(...)` per slice.
- Lint Gate: whole-repo `ruff check src/ tests/` and `ruff format --check src/ tests/`.
- Offline `pytest -m "agent and not agent-live-call"` must stay green without network.
- Golden UX pilot `tests/adapters/tui/test_agent_stage_ux_golden.py` stays green.

---

## 1. Preflight (mandatory)

```md
Confirm:
- Hexagonal boundaries; adapter stays thin (renders y/n, returns bool; no policy).
- Consent policy (what to confirm, implication text, deny semantics) stays in application.
- No guardrail bypass; no Phase 4/5 scope; no new tools.
- git status clean of unrelated work.

Layer plan:
- Domain: not touched
- Application: fail-closed approval default; deny budget/identity accounting; byte parity
- Infrastructure: not touched (composition wiring already gates elevated registration)
- Adapter (TUI): remove unsafe runner-retry ladder; keep y/n confirm + restore
```

Read before editing:

- `src/application/use_case/orchestrate_agent_turn_use_case.py`
- `src/application/use_case/session_aware_agent_turn_use_case.py`
- `src/adapters/tui/main.py` (`_run_agent_turn` runner call, `_approval`,
  `_ask_elevated_tool_confirm`, `_restore_agent_last_good`)
- `src/adapters/tui/composition.py` (runner injection)
- L4 tests under `tests/` (`test_orchestrate_*`, agent live/offline suites)

---

## 2. Findings to fix (blocking first)

### 🔴 F1 — Remove the fail-open runner retry ladder (BLOCKING)

**Where:** `src/adapters/tui/main.py` ~L2060–2065.

**Defect:** The `try/except TypeError` ladder re-invokes the runner dropping
`on_approval` (then `on_progress`). The injected runner
(`composition.py` → `agent_composition.use_case.execute`) already accepts both
kwargs, so this never fires for signature reasons — it only fires on a **genuine
`TypeError` raised during execution**, and then re-runs the whole turn **without
the approval callback**. Combined with F2 this executes elevated/network tools
**without confirm** and double-executes the turn. Violates ADR-065 invariant 2.

**Fix (choose the smaller safe option):**

- Call the runner **once** with `on_progress` and `on_approval`. Do **not** catch
  `TypeError` to retry with fewer args.
- If backward-compat signature probing is truly needed, detect support **once**
  before calling (e.g. `inspect.signature`), never by catching an execution error,
  and never re-run after any tool/provider call may have run.
- A real exception during the turn must map to a FAILED `AgentTurnResult`
  (existing behavior), not a silent re-run.

**Acceptance:**
- [ ] Single runner invocation path; no retry-without-approval.
- [ ] A `TypeError` raised inside the runner surfaces as FAILED, turn runs **once**.

### 🔴 F2 — Fail closed when approval callback is absent (BLOCKING)

**Where:** `src/application/use_case/orchestrate_agent_turn_use_case.py` `_run_batch`,
the line `approved = True if approval is None else bool(approval(req))`.

**Defect:** A missing approval handler is treated as consent. For a
`PER_CALL` tool this must fail closed regardless of caller.

**Fix:** When `definition.approval is AgentToolApproval.PER_CALL` and `approval is None`,
do **not** execute. Produce the same skip result as an explicit deny
(`UNAVAILABLE`, `error_code="TOOL_DENIED"`, warning `EXTERNAL_OR_ELEVATED_DECLINED`
or a distinct `TOOL_NO_APPROVER` code — pick one, document it) and continue the
turn (deny semantics). Ordinary `side_effect=NONE` tools are unaffected.

**Acceptance:**
- [ ] Elevated tool + `on_approval=None` → **not executed**; turn continues.
- [ ] `side_effect=NONE` tools still run with no approval callback (unchanged).

### 🟡 F3 — Denies must not consume tool budget or block re-proposal

**Where:** `orchestrate…_use_case.py` `_run_batch` (denied result appended before
`continue`) and `_l3_path` (`tools_used += len(batch_results)`,
`seen_identities` seeded before deny).

**Defect:** A denied tool is counted in `tools_used` and its identity is added to
`seen_identities`, so denies prematurely exhaust the 4-tool budget and a
re-proposed denied tool fails the whole turn as a duplicate. ADR-065 decision 5
counts **executions**; decision 6 wants deny → continue.

**Fix:**
- Do not count denied/no-approver results toward `tools_used` (only executed tools).
- Do not add a denied tool's identity to `seen_identities` (allow the model to
  re-propose; still count a genuine same-name+args **execution** as a duplicate).
- Keep the denied result in the trace/warnings for honesty (non-authoritative note).

**Acceptance:**
- [ ] Deny then a different tool: budget reflects only executed tools.
- [ ] Deny then re-propose same tool: turn does **not** fail as duplicate.

### 🟡 F4 — Byte-budget parity for denied results

**Where:** `_run_batch` excludes denied results from `running_bytes`; `_l3_path`
adds every result's `serialized_size()` (incl. denies) to `total_bytes`.

**Fix:** Make both paths agree — either count denied-result bytes in both or
neither (prefer: count only executed results in both, consistent with F3).

**Acceptance:**
- [ ] In-batch and cross-round byte accounting use the same rule for denies.

### 🟢 F5 — Document planning-only heuristic limits (no behavior change)

`_looks_like_planning_only` is EN/ID prefix-match, capped at 280 chars — a soft
policy per ADR-064 §Failure. **No code change required.** Add a short code comment
noting it is a best-effort soft guard, not a guarantee, so it is not mistaken for
an invariant. (Optional; skip if it invites scope creep.)

### 🟢 F6 — Note PENDING_APPROVAL is a callback, not an enum (docs only)

ADR-065 names an application state `PENDING_APPROVAL`. It is realized as a
synchronous blocking approval callback with application-owned policy
(`_implication`, `_arg_summary`) and a thin adapter y/n. Add one clarifying line
to `docs/adr/ADR-065-*.md` (or the journey SSOT) that the pause is a callback
seam, not an `AgentTurnStatus` value, so future readers don't hunt for a state.

---

## 3. Required tests (offline, `pytest.mark.agent`, no network)

Add/extend under the existing agent test modules:

- [ ] **F2:** orchestrator with an elevated (`PER_CALL`) tool registered and
  `on_approval=None` → tool is **not executed**, result is skip/deny, turn continues
  to a final answer (or FAILED via normal rules), **no provider tool execution**.
- [ ] **F1:** a runner/fake that raises `TypeError` mid-turn → exactly **one**
  turn attempt, result FAILED; assert the provider/tool fake was **not** re-invoked
  (call counter == first attempt).
- [ ] **F3:** deny an elevated tool, then propose (a) a different OUR tool and
  (b) the same elevated tool again → budget counts only executed tools; the
  re-proposal is **not** a duplicate failure; turn continues.
- [ ] **F4:** deny + subsequent executed tools stay within the 64 KiB rule with
  consistent accounting across rounds.
- [ ] Existing L4 confirm/deny/fail-safe/gap tests still green.
- [ ] Golden UX pilot green.

Do **not** weaken existing assertions to greenwash. If an existing test encodes
the old fail-open behavior (e.g. asserts auto-approve when `approval is None`),
update it to the fail-closed contract and note the change in the commit.

---

## 4. Verification (required before marking done)

```bash
.venv/bin/python -m pytest -m "agent and not agent-live-call" -q
.venv/bin/python -m pytest tests/adapters/tui/test_agent_stage_ux_golden.py -q
.venv/bin/python -m pytest tests/architecture/test_layer_boundaries.py -q
ruff check src/ tests/
ruff format --check src/ tests/
git diff --check
```

Live paths (optional, operator only): unchanged; do not make live the CI gate.

---

## 5. Commit plan (contextual multi-commit)

| Order | Commit theme |
|---|---|
| 1 | `fix(agent): fail closed when no approval callback for elevated tools (F2)` |
| 2 | `fix(tui): remove fail-open runner retry that dropped approval (F1)` |
| 3 | `fix(agent): denies do not consume tool budget or block re-proposal (F3)` |
| 4 | `fix(agent): consistent byte accounting for denied results (F4)` |
| 5 | `test(agent): fail-closed confirm, single-run, deny-continue coverage` |
| 6 | `docs(agent): note PENDING_APPROVAL callback seam + planning-only guard (F5/F6)` |

Bundle F1+F2 first (they are the blocking consent path). F5/F6 are docs/comments.

---

## 6. Explicit non-goals

- New tools, capabilities, or flags.
- Changing L3 budgets or the state machine shape.
- Phase 4 durable audit / Phase 5 write tools.
- Weakening Action, Signal, Risk, MCE, or TradeSetup authority.
- Any change that makes elevated/external execution possible without explicit consent.

---

## 7. Done criteria

- [ ] F1–F4 fixed at the correct layer; F5/F6 addressed (or F5 consciously skipped).
- [ ] New regression tests green; existing agent suite + golden UX green.
- [ ] Ruff whole-repo gate green.
- [ ] Journey SSOT changelog row added (confirm fail-closed hardening).
- [ ] This file moved to `tasks/done/` with a completion record (date + commits).

---

## 8. Copy-paste kickoff prompt

```text
Fix AI Research Cockpit L4 confirm fail-open + budget drift per
tasks/backlog/fix_ai_research_cockpit_l4_confirm_failopen.md.

Order: F1+F2 first (consent fail-open is blocking), then F3, F4, tests, docs.

Hard rules:
- Consent is fail-closed: elevated/PER_CALL tool with no approver = skip/deny, never execute.
- Never re-run a turn that has started executing (no double spend / double egress).
- Deny continues the turn; denies do not consume tool budget or block re-proposal.
- No new tools/flags; no ADR budget changes; Action authority untouched.
- Multi-commit contextual fix(...) commits; AGENT_QUICKSTART lint gate.
- Offline `pytest -m "agent and not agent-live-call"` green; golden UX pilot green.

Read ADR-064, ADR-065, and the review findings in the task file first.
```
