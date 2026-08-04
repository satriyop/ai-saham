# Goal Instruction — Implement `get_market_regime` (market-wide tape context)

**Status:** `IMPLEMENTED`
**Audience:** Implementation agent · **Product term:** AI Research Cockpit (`/`)
**Priority:** 2 of 5 (coverage row 10) — highest-leverage; cross-cutting on every stage.

**Binding architecture:**

| Doc | Role |
|---|---|
| [ADR-061](../../docs/adr/ADR-061-closed-read-tool-orchestration-for-context-agent.md) | **Binding** — closed read tool; `side_effect=NONE`, facts-only → task, no new ADR |
| Coverage matrix | [`ai_research_cockpit_tool_coverage.md`](../../docs/roadmap/ai_research_cockpit_tool_coverage.md) (row 10) + honesty policy |
| Regime source | ADR-029 / ADR-037 MarketContextEngine; `market_context_snapshots`; cohort via `build_mce_observation_identity` |

## Locked decisions (operator 2026-08-04 — all recommended)

| # | Decision |
|---|---|
| Read path | Cohort-scoped only: `get(as_of, semantic_compatibility_id=cohort_id)` / `get_recent(1, …)` |
| Cohort | Canonical MCE identity (`build_mce_observation_identity` + regime_universe + benchmark + MCE YAML) injected at composition |
| Confidence | Dual fields: always-present `conviction` + nullable `regime_confidence` (null → SUCCESS, not PARTIAL) |
| Factors | value / label / rationale only — **omit factor.score** |
| Multipliers | `signal_multiplier` + `gate_tightening` as stored descriptive readings (not enter directive) |
| Stability | Include `regime_stability` / `days_in_regime` when set |
| Compute | **Never** recompute via `BuildMarketContextUseCase` / engine evaluate; never fetch |

## Result (facts only)

- `as_of`, `regime`, `conviction`, `regime_confidence` (nullable)
- `factors[]` (name, enabled, value, label, rationale)
- `signal_multiplier`, `gate_tightening`
- `regime_stability`, `days_in_regime`
- `cohort_id`, `universe_name`, `benchmark_ticker`
- Optional `as_of` arg (default latest for cohort)
- PARTIAL on stale/coverage/transition/missing-factor warnings; UNAVAILABLE when no cohort snapshot

## Completion record

- Authorizing ADR: ADR-061
- Implemented date: 2026-08-04
- Code: `agent_market_regime_tool.py`, `AgentToolName.GET_MARKET_REGIME`, `build_read_only_market_regime_tool`, agent_model registration, gap clues
- Tests: `test_agent_market_regime_tool.py`, composition registration
- Coverage row: 10 → 🟢
- Commits: (fill on commit)
