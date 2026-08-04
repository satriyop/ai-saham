# Goal Instruction — Implement `get_ticker_sector_context` (sector strength / rotation)

**Status:** `IMPLEMENTED`
**Audience:** Implementation agent · **Product term:** AI Research Cockpit (`/`)
**Priority:** 5 of 5 (coverage row 13).

## Locked decisions (operator 2026-08-04 — C + recommended)

| # | Decision |
|---|---|
| Content | **L2a peer + L2b macro** (nested); either missing → PARTIAL |
| Scores | Project **value/label/rationale** and regime **labels**; **omit** composite_score and factor.score |
| Shape | `BuildTickerSectorContextUseCase` loads cache + reuses ADR-053 builders/assemblers |
| Adapters this task | Agent tool + composition only (CLI/TUI later) |
| Args | `ticker` required; `as_of` optional (latest candle); `peers_limit` default/cap 10 |

## Mission

Descriptive sector context (peer strength/rotation + routed macros). Closes row 13.
`side_effect=NONE`, cache-only, facts-not-score, no buy/avoid verdict.

## Completion record

- Authorizing ADR: ADR-061
- Implemented date: 2026-08-04
- Code: `build_ticker_sector_context_use_case.py`, `agent_ticker_sector_context_tool.py`,
  `build_read_only_ticker_sector_context_use_case`
- Tests: `test_build_ticker_sector_context_use_case.py`, `test_agent_ticker_sector_context_tool.py`
- Coverage row: 13
- Commits: (fill after commit)
