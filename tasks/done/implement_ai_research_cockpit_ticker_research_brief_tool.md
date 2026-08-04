# Goal Instruction — `get_ticker_research_brief` (composed one-shot context)

**Status:** `IMPLEMENTED`
**Audience:** Implementation agent · **Product term:** AI Research Cockpit (`/`)
**Menu:** E (flagship synthesis) · Depth policy 2026-08-04.

**Binding architecture:**

| Doc | Role |
|---|---|
| [ADR-061](../../docs/adr/ADR-061-closed-read-tool-orchestration-for-context-agent.md) | Closed read tool; descriptive, read-only |
| [ADR-042](../../docs/adr/ADR-042-deterministic-champion-and-optional-model-challengers.md) | **Authority line** — the brief must not mint a verdict |

## Locked decisions (operator 2026-08-04 — recommended defaults)

| # | Decision |
|---|---|
| Scope this slice | Shared `BuildTickerResearchBriefUseCase` + agent tool; CLI/TUI thin adapters **deferred** (use case is the reuse surface) |
| Default sections | `judge`, `broker_flow`, `foreign_flow`, `ownership`, `corporate_actions`, `regime` |
| Optional args | `ticker` required; `as_of`; `sections` CSV subset |
| Judge | Same runner as `AccumulationJudgeTool`; Action + key engine facts **surfaced**, not recomputed as a new verdict |
| Missing section | Independent UNAVAILABLE/PARTIAL; overall PARTIAL when any section degrades |
| Not in v1 brief | desk_flow_history, sector_context, fundamentals_trend, full ownership history series |
| Authority | **No** `verdict` / `brief_conclusion` / `recommendation` / overall composite |

## Result (facts only)

Per-section meta + thin facts:

- `judge.action` (deterministic TradeSetup action) + signal/accum/phase key fields
- `broker_flow` tops + bandar counts/labels
- `foreign_flow` net trend summary
- `ownership` latest composition
- `corporate_actions` upcoming (capped)
- `regime` cohort-scoped snapshot

## Completion record

- Authorizing ADR: ADR-061 (composition; surfaces existing Action, no new authority) + ADR-042 guard
- Implemented date: 2026-08-04
- Code: `build_ticker_research_brief_use_case.py`, `agent_ticker_research_brief_tool.py`, composition wiring
- Tests: `test_build_ticker_research_brief_use_case.py`, `test_agent_ticker_research_brief_tool.py`
- Commits: `e0b87f84`
