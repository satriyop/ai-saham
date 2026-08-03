# Implement AI Research Cockpit L4 — External Research, RO Data Ask, Confirm

Status: `IMPLEMENTED` — architecture ADR-065; runtime landed after L3 (2026-08-03)

Source:

- [ADR-065](../../docs/adr/ADR-065-ai-research-cockpit-external-and-ro-data-l4.md)
- Journey SSOT: AI Research Cockpit vocabulary

## 1. Slices (do not big-bang)

1. Registry `side_effect` + `approval` + `PENDING_APPROVAL` orchestrator seam +
   Research Cockpit light y/n (default Yes, Enter executes).  
2. `web_research` via DeepSeek research/tool path (re-verify provider).  
3. `ro_data_query` allowlisted SELECT + limits + confirm.  
4. Tool-gap clues (operator-visible + session optional).  
5. Fail-safe restore last successful Research Cockpit turn; deny vs fail rules.  

## 2. Flags (default false)

- `ai.external_tools`  
- `ai.web_research`  
- RO data enable flag (name at implement)  

## 3. Non-Goals

- Model-invented tools, writes, free SQL, durable audit, trading  

## 4. Acceptance (epic)

- [x] ADR-065 budgets/confirm/fail-safe/gap clues implemented per slice  
- [x] Ordinary NONE tools unchanged without elevated flags  
- [x] Elevated/external count toward L3 tool budget when multi-round on  
- [x] Offline agent tests green without network  
- [x] Live paths opt-in only  
- [x] Ruff gate  

## 5. Completion Record

- Activation ADR: ADR-065  
- Implemented date: 2026-08-03  
- Commit(s): see git log for L4 family after L3 `dcecaee3`
