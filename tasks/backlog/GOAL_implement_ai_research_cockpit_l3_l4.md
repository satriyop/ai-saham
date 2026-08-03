# Goal Instruction — Implement AI Research Cockpit L3 then L4

**Status:** `READY FOR AGENT`  
**Audience:** Implementation agent (any coding agent in this repo)  
**Product term:** **AI Research Cockpit** (`/`) — use this name in code comments,
commits, UI strings, and docs. Prefer it over “agent stage/chat.”

**Binding architecture (read before coding):**

| Doc | Role |
|---|---|
| [ADR-064](../../docs/adr/ADR-064-ai-research-cockpit-bounded-multi-round-tools.md) | **L3** multi-round OUR tools |
| [ADR-065](../../docs/adr/ADR-065-ai-research-cockpit-external-and-ro-data-l4.md) | **L4** web_research + RO data ask + confirm |
| [ADR-061](../../docs/adr/ADR-061-closed-read-tool-orchestration-for-context-agent.md) | Closed registry L1 baseline |
| [ADR-063](../../docs/adr/ADR-063-ephemeral-agent-session-and-context-budget.md) | Session atomicity |
| Journey SSOT | [`docs/roadmap/tui_ai_agent_implementation_journey.md`](../../docs/roadmap/tui_ai_agent_implementation_journey.md) — vocabulary + UX locks U1–U13 |
| L3 task | [`implement_ai_research_cockpit_multi_round_tools_l3.md`](implement_ai_research_cockpit_multi_round_tools_l3.md) |
| L4 epic | [`implement_ai_research_cockpit_external_and_ro_data_l4.md`](implement_ai_research_cockpit_external_and_ro_data_l4.md) |

**Do not invent product behavior.** If ADR and code conflict, stop and ask.
If ADR is silent, choose the **safer, smaller** option and document it.

---

## 0. Mission

1. **First:** implement **L3** (ADR-064) fully — multi-round OUR tools under
   `ai.tools_multi_round`.
2. **Then:** implement **L4** (ADR-065) in slices — confirm seam, `web_research`,
   `ro_data_query`, tool-gap clues, fail-safe.

Hard rules:

- Model may **propose** only; application **registers, validates, budgets, executes**.
- **No model-invented tools.** Gaps → structured **TOOL_GAP** clues, not fake execution.
- Deterministic Action/scores remain champion; Research Cockpit is non-authoritative.
- Multi-commit, contextual commits; fix bugs found during implementation in separate
  `fix(...)` commits.
- Lint Gate: whole-repo `ruff check src/ tests/` and `ruff format --check src/ tests/`.
- Offline `pytest -m agent` must stay green without network.
- Live/network tests only if already established project markers; never default CI live.

---

## 1. Preflight (mandatory)

```md
Confirm:
- Hexagonal boundaries; adapters thin; workflow in application.
- Deterministic-first; AI optional non-authoritative.
- No guardrail bypass; no Phase 5 writes unless ADR-065 explicitly allows (it does not).
- Lint Gate as above.
- git status clean of unrelated work; do not destroy foreign dirty files.

Layer plan (L3):
- Domain: not touched
- Application: multi-round orchestrator, budgets/policy DTOs, session atomic commit
- Infrastructure: AiConfig.tools_multi_round; composition wiring
- Adapter: Research Cockpit progress (round/tool); no policy ownership

Layer plan (L4, after L3):
- Domain: not touched (unless pure value objects for gap clues)
- Application: side_effect + approval state machine; gap clues; fail-safe snapshot policy
- Infrastructure: DeepSeek web_research adapter; RO allowlisted query executor
- Adapter: light y/n confirm in Research Cockpit; restore last good turn UI
```

Read current orchestrator and composition before editing:

- `src/application/use_case/orchestrate_agent_turn_use_case.py`
- `src/application/use_case/session_aware_agent_turn_use_case.py`
- `src/application/services/agent_tool_registry.py`
- `src/infrastructure/composition/agent_model.py`
- `src/infrastructure/config/app_config.py` / `config/default.yaml`
- `src/adapters/tui/main.py` + `widgets/agent_commentary.py`
- Golden UX: `tests/adapters/tui/test_agent_stage_ux_golden.py` (must remain green)

---

## 2. Phase A — L3 multi-round (ADR-064) — do first

### 2.1 Config

| Flag | Default | Behavior |
|---|---|---|
| `ai.tools_multi_round` | **`false`** | When false + tools on → **exact ADR-061 L1** (1 tool batch, 2 tools, 2 provider calls) |
| | | When true + tools on → L3 budgets |

Add to `AiConfig` + `config/default.yaml` with comment pointing at ADR-064.

### 2.2 Locked budgets (do not freestyle)

| Limit | Value |
|---|---:|
| Provider rounds / user turn | **3** |
| Tool executions / turn | **4** |
| Tools / batch | **2** |
| Parallel | **0** |
| Retries | **0** |
| Provider timeout / call | **10 s** |
| Total tool budget | **20 s** |
| Turn deadline | **45 s** |
| Total tool result bytes | **64 KiB** |

### 2.3 State machine (must match ADR-064)

```text
START → capture context lineage
rounds_used=0; tools_used=0
while rounds_used < 3:
  forced_final = (rounds_used == 2) or (tools_used >= 4)  # adjust so last call is none when at cap
  provider_call(auto if tools remain and not forced_final else none)
  rounds_used += 1
  if ANSWER → SUCCESS/PARTIAL → session commit if applicable → END
  if TOOL_CALLS:
    validate batch (≤2, ≤ remaining tool slots, no dup name+canonical args in turn)
    execute sequential; tools_used += n
    if cancel → CANCELLED → END
    continue
  if malformed → FAILED detail → END
if no answer → FAILED exhausted → END
```

**Must:**

- Last allowed provider call uses **`tool_choice=none`**.
- Intermediate provider text is **not** painted as Turn OK answer (progress only).
- Duplicate tool name+canonical args **across the whole turn** fails closed.
- Invalid batch fails whole turn (no partial execute of that batch).
- Session (ADR-063): **atomic** — only SUCCESS/PARTIAL commits session; FAIL/CANCEL leaves session as before that Enter.

### 2.4 UX (Research Cockpit)

- Show progress: e.g. `round 2/3 · tool get_ticker_dashboard…`
- Keep U1–U13 UX locks (status strip, Esc restore Judge, auto agent, etc.).
- Do not claim “not wired” when AI path is live.

### 2.5 Tests (offline, `pytest.mark.agent`)

- Flag false → identical L1 ceilings (assert max 2 provider calls / 2 tools).
- Flag true → 3 rounds / 4 tools enforced; exhaustion FAILED; forced final none.
- Intermediate “planning” text not accepted as SUCCESS when tools still pending.
- Session: failed multi-round turn does not append commentary/tool memory.
- Existing agent suite still green.

### 2.6 L3 commits (contextual multi-commit)

| Order | Commit theme |
|---|---|
| 1 | `feat(agent): add ai.tools_multi_round config flag` |
| 2 | `feat(agent): multi-round orchestrator state machine (ADR-064)` |
| 3 | `feat(tui): Research Cockpit multi-round progress UX` |
| 4 | `test(agent): multi-round budgets and session atomicity` |
| 5 | `docs(agent): record L3 implementation completion` |
| *as needed* | `fix(agent): …` separate |

### 2.7 L3 done criteria

- [ ] ADR-064 acceptance checklist in implement task checked  
- [ ] Journey SSOT L3 row → implemented  
- [ ] Offline agent tests + golden UX pilots green  
- [ ] Ruff gate green  

**Stop and report** before starting L4 unless the user explicitly says continue.

---

## 3. Phase B — L4 external + RO data (ADR-065) — after L3

### 3.1 Config (all default **false**)

| Flag | Meaning |
|---|---|
| `ai.external_tools` | Master: elevated/external capabilities may register |
| `ai.web_research` | Enable `web_research` (requires master) |
| RO enable flag (name consistently, e.g. `ai.ro_data_query`) | Enable `ro_data_query` (requires master) |

### 3.2 Registry extensions

Extend tool definitions (application-owned) with:

- `side_effect`: at least `NONE` | `NETWORK_READ` | `LOCAL_READ_ELEVATED`
- `approval`: `NONE` | `PER_CALL`

Ordinary ADR-061 tools: `NONE` / no confirm.  
Elevated/external: **PER_CALL** confirm before execute.

### 3.3 Capabilities to implement

#### Slice B1 — Confirm seam (before any network)

- Orchestrator state `PENDING_APPROVAL`
- Research Cockpit light y/n: show capability name, arg summary, implication line
- **Default focus Yes**; **Enter** confirms; **No** denies
- Confirm is **not** free-text chat “yes”
- Deny → **skip** that tool; continue turn (local tools / final answer) — do not kill turn solely for deny

#### Slice B2 — `web_research`

- Closed args: `query` (bounded length), optional `max_results` with hard cap
- Side effect `NETWORK_READ`
- Implementation: **our** adapter wrapping **DeepSeek research / tool-call path**
  — re-verify provider docs at implement time; version the integration
- Result: frozen snippets + titles + URLs + timestamps + provider id; no raw dump authority
- Honesty note `EXTERNAL_RESEARCH` on success
- Counts toward **L3 tool budget** when multi-round on

#### Slice B3 — `ro_data_query`

- Allowlisted SELECT / prepared shapes only (no DDL/DML, multi-statement, attach)
- Hard limits: rows, bytes, timeout, schema allowlist (lock numbers in code + tests)
- Confirm y/n before execute
- Allowlist miss → **TOOL_GAP** clue, not execute
- Prefer ordinary named tools when they cover the need

#### Slice B4 — Tool-gap clues

When model proposes unregistered name or allowlist miss:

- Reject execute
- Emit structured clue: suggested tool id, purpose, why needed
- Show operator-visible `TOOL_GAP · …` in honesty/more notes
- Optional process-session retention (not durable audit)

#### Slice B5 — Fail-safe

- Keep **last successful** Research Cockpit turn snapshot (process memory)
- After **approve**, if elevated/external **fails**: no SUCCESS session commit; restore last successful UI; explicit error
- Optional: if OUR tools already succeeded earlier in same Enter, one final local-only answer PARTIAL allowed per ADR-065
- Cancel: CANCELLED, restore rules apply

### 3.4 Authority

- External/elevated results never enter Signal/Risk/MCE/TradeSetup/promotion/etc.
- No writes, fetch refresh, journal, trading.

### 3.5 Tests

- Confirm required before elevated/external execute
- Deny continues without external
- Post-approve fail restores last good; session not polluted
- Flags off → capabilities unregistered
- Budget: external counts toward 4 tools when multi-round on
- Gap clue emitted on unregistered tool name
- RO query rejects non-allowlisted SQL
- Offline suite: no network without opt-in live markers

### 3.6 L4 commits (contextual)

| Order | Commit theme |
|---|---|
| 1 | `feat(agent): tool side_effect and approval contracts` |
| 2 | `feat(agent): PENDING_APPROVAL orchestrator + Research Cockpit y/n` |
| 3 | `feat(agent): web_research DeepSeek adapter` |
| 4 | `feat(agent): ro_data_query allowlisted read` |
| 5 | `feat(agent): tool-gap clues and fail-safe restore` |
| 6 | `test(agent): L4 confirm deny fail-safe budget` |
| 7 | `docs(agent): record L4 slice completion` |
| *as needed* | `fix(agent): …` |

---

## 4. Bugs during implementation

1. Fix at correct layer; do not weaken ADRs or tests to greenwash.  
2. Separate `fix(...)` commit with clear message.  
3. Re-run offline agent + golden UX pilots after fixes.  

Forbidden “fixes”:

- Opening unbounded multi-round or inventing tools  
- Skipping confirm for network  
- Defaulting external flags to true in `default.yaml`  
- Putting workflow policy in TUI widgets  

---

## 5. Verification commands

### Offline (required before merge of each phase)

```bash
.venv/bin/python -m pytest -m "agent and not agent-live-call" -q
.venv/bin/python -m pytest tests/adapters/tui/test_agent_stage_ux_golden.py -q
.venv/bin/python -m pytest tests/architecture/test_layer_boundaries.py -q
ruff check src/ tests/
ruff format --check src/ tests/
git diff --check
```

### Live (optional, operator only)

Only if project already has `agent-live-call` or equivalent; never make live the CI correctness gate. Re-verify DeepSeek research contracts when implementing B2.

---

## 6. Documentation updates (with each phase complete)

Update journey SSOT:

- L3/L4 status rows → implemented when done  
- Changelog table  
- Flags table (`tools_multi_round`, `external_tools`, `web_research`, RO flag)  

Do not fork parallel smoke docs; keep
`docs/roadmap/tui_ai_agent_implementation_journey.md` as operator SSOT.

Fill completion records in:

- `implement_ai_research_cockpit_multi_round_tools_l3.md`
- `implement_ai_research_cockpit_external_and_ro_data_l4.md`

---

## 7. Explicit non-goals (both phases)

- Phase 4 durable audit SQLite  
- Phase 5 write tools (fetch/journal/watchlist/trade)  
- Hermes/OpenClaw/Telegram transport  
- Free browser agent / unrestricted SQL  
- Parallel tools, retries, unbounded loops  
- Weakening Action authority  

---

## 8. Copy-paste kickoff prompt

```text
Implement AI Research Cockpit L3 then L4 per
tasks/backlog/GOAL_implement_ai_research_cockpit_l3_l4.md.

Order: complete ADR-064 L3 fully and stop for report, unless I say continue to L4.
Then implement ADR-065 in slices (confirm → web_research → ro_data_query → gap clues → fail-safe).

Hard rules:
- Product term: AI Research Cockpit (/)
- Model proposes; app validates/executes; no invented tools
- L3: 3 rounds / 4 tools / 2 per batch; ai.tools_multi_round default false
- L4: y/n confirm default Yes; external counts in L3 budget; deny continues; post-approve fail restores last good turn; tool-gap clues
- Multi-commit contextual; fix bugs in separate fix commits
- AGENT_QUICKSTART lint gate; offline pytest -m agent green without network
- Do not implement durable audit or write tools

Read ADR-064, ADR-065, journey SSOT UX locks, and the two implement_*.md tasks first.
```

---

## 9. Success definition

| Phase | Success |
|---|---|
| L3 | Multi-round works under flag; L1 unchanged when off; progress UX; tests + docs |
| L4 | Confirm + web_research + allowlisted RO + gap clues + fail-safe; flags default false; tests + docs |
| Overall | Research Cockpit can multi-hop OUR tools and, when enabled, research externally under consent without becoming Action authority |
