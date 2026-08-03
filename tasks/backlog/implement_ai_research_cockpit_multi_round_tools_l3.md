# Implement AI Research Cockpit L3 — Bounded Multi-Round OUR Tools

Status: `ACTIVATED` — architecture authorized by ADR-064 (2026-08-03); runtime
not started

Source:

- [ADR-064](../../docs/adr/ADR-064-ai-research-cockpit-bounded-multi-round-tools.md)
  (binding)
- [ADR-061](../../docs/adr/ADR-061-closed-read-tool-orchestration-for-context-agent.md)
- Journey SSOT: AI Research Cockpit vocabulary + UX locks

## 1. Task Metadata

- Task type: Feature / orchestrator extension  
- Priority: Medium after v1 Research Cockpit UX locks  
- Semantic classification: `NON_SEMANTIC` while tools remain read-only projections  
- AI usage: optional multi-round tool use inside one Research Cockpit turn  
- Chosen decision: implement ADR-064 budgets and state machine only  

## 2. Desired Outcome

When `ai.tools_enabled` and `ai.tools_multi_round` are true, one user question in
the AI Research Cockpit may run up to **3 provider rounds** and **4 tool
executions** (max **2** per batch) over the existing closed OUR registry. Final
provider call uses `tool_choice=none`. Progress is visible. FAIL/CANCEL does not
commit ADR-063 session state. With multi_round false, ADR-061 L1 is unchanged.

## 3. Non-Goals

- New tool names, external/web, writes, RO free SQL  
- Unlimited loops, parallel tools, retries  
- Changing UX locks U1–U13 except progress line for multi-round  
- Default-true multi_round (flag default false per ADR-064)  

## 4. Layer plan

```md
- Domain: not touched
- Application: multi-round orchestrator state machine, budgets, policy DTO
- Infrastructure: config flag; provider already supports tool rounds
- Adapter: Research Cockpit progress (round/tool); fail detail; no policy
```

## 5. Acceptance Criteria

- [ ] `ai.tools_multi_round` in config (default false)  
- [ ] L1 path bit-identical when flag false  
- [ ] L3 path enforces 3 rounds / 4 tools / 2 per batch / sequential / no retry  
- [ ] Last provider call forced `tool_choice=none` when at round cap  
- [ ] Intermediate provider text is not Turn OK answer  
- [ ] Invalid batch / exhaustion → FAILED with detail  
- [ ] Session atomic commit (ADR-063 + ADR-064)  
- [ ] Offline `pytest -m agent` green; multi-round unit tests with fakes  
- [ ] Ruff whole-repo gate  
- [ ] Journey SSOT L3 row updated on completion  

## 6. Completion Record

- Activation ADR: ADR-064  
- Implemented date:  
- Commit(s):  
- Verification:  
