# Goal Instruction — Implement `get_market_regime` (market-wide tape context)

**Status:** `READY FOR AGENT`
**Audience:** Implementation agent · **Product term:** AI Research Cockpit (`/`)
**Priority:** 2 of 5 (coverage row 10) — highest-leverage; cross-cutting on every stage.

**Binding architecture:**

| Doc | Role |
|---|---|
| [ADR-061](../../docs/adr/ADR-061-closed-read-tool-orchestration-for-context-agent.md) | **Binding** — closed read tool; `side_effect=NONE`, facts-only → task, no new ADR |
| Coverage matrix | [`ai_research_cockpit_tool_coverage.md`](../../docs/roadmap/ai_research_cockpit_tool_coverage.md) (row 10) + honesty policy |
| Regime source | ADR-029 / ADR-037 MarketContextEngine; `market_context_snapshots`, `regime_observations`; `BuildMarketContextUseCase` |

## 0. Mission

Give the model **market-wide tape context** — current regime (RISK_ON/OFF/VOLATILE),
confidence, and factor readings (breadth, idx_trend, foreign_flow, vix/eido/usd_idr)
— so it can reason about *the tape*, not just one candidate. Closes coverage **row 10**.

Hard rules:

- `side_effect=NONE`, `approval=NONE`; **cache-only** — read the **latest stored**
  `market_context_snapshots` for the as_of. **Do NOT recompute** via
  `BuildMarketContextUseCase` (that needs pre-loaded candles / would pull data) and
  **do NOT fetch**.
- **Facts, not a directive:** return the regime classification + confidence +
  factor values. **Never** a buy/sell/enter instruction; regime is context, not Action.
- PIT: read the snapshot at/for `as_of`, never a future snapshot.
- `UNAVAILABLE` when no stored snapshot; PARTIAL if some factors missing (honesty policy).
- Market-wide (not per-ticker). Offered on all stages.

## 1. Layer plan

```md
- Domain: not touched (MarketContext value objects exist)
- Application: AgentToolName.GET_MARKET_REGIME; result DTO
  (schema agent_tool.market_regime.v1); MarketRegimeTool reading the latest stored
  market context snapshot
- Infrastructure: reuse `SQLiteMarketContextRepository.get/get_recent` (cohort-
  scoped); composition injects the canonical `cohort_id` (reuse the MCE identity
  derivation, do not reimplement)
- Adapter: none
```

**Reader confirmed (verified):** `SQLiteMarketContextRepository.get(as_of_date,
semantic_compatibility_id=…)` → `MarketContext | None` and `get_recent(limit,
semantic_compatibility_id=…)` → `list[MarketContext]` already exist. No new reader,
no compute, no fetch.

**⚠️ Cohort scoping (decided) — never call `get()` cohort-less.** `get(as_of)`
without `semantic_compatibility_id` returns `None` when >1 cohort row exists for the
date — a **false UNAVAILABLE**. The tool MUST read a specific canonical cohort:

- Resolve the cohort id from the **same MCE identity production writes with** —
  `_mce_identity.cohort_id` (derived from the active `MarketContextConfig`:
  universe/benchmark/contract; see `market_context_engine._persist` :336). **Reuse
  that existing derivation; do not reimplement it.** Inject the cohort id at composition.
- `get(as_of, semantic_compatibility_id=cohort_id)`; default latest =
  `get_recent(1, semantic_compatibility_id=cohort_id)`.
- `None` for the **resolved** cohort → genuine `UNAVAILABLE`.

**⚠️ Confidence (decided) — expose BOTH, explicitly named.** `MarketContext` has two
distinct fields; the CLI already shows both. Do **not** collapse to a bare
"confidence": expose `conviction` (always-present composite 0–1) and
`regime_confidence` (boundary-distance; `float | None` — null is a true state →
SUCCESS with null, not PARTIAL). `signal_multiplier`/`gate_tightening` are
config-derived readings projected descriptively, not a directive from this tool.

Read first: `src/application/use_case/build_market_context_use_case.py` (result
shape: regime, confidence, factors), the persistence for `market_context_snapshots`
/ `regime_observations`, and the `agent_ticker_dashboard_tool.py` pattern.

## 2. Result (facts only)

`as_of`, `regime` (enum), `conviction` (0–1, always present),
`regime_confidence` (`float | None`), per-factor readings
(`idx_trend`, `idx_breadth`, `foreign_flow`, `vix`, `eido`, `usd_idr`,
optional `commodity_composite`) as raw values/labels, `cohort_id` provenance, and
snapshot provenance. **No** enter/size directive.

## 3. Slices

1. Contract: `AgentToolName.GET_MARKET_REGIME` + frozen result DTO.
2. Reader: `get(as_of, semantic_compatibility_id=cohort_id)`; default latest via
   `get_recent(1, semantic_compatibility_id=cohort_id)`.
3. Tool: `MarketRegimeTool` — arg optional `as_of` (default latest). No ticker arg.
   Cohort id injected at composition (canonical MCE identity).
4. Register in composition when `tools_enabled` + DB present.
5. Tests (offline `pytest.mark.agent`): happy path; PIT (no future snapshot);
   **cohort scoping** — a date with **>1 cohort** row resolves the canonical cohort
   (not false `UNAVAILABLE`); **both** `conviction` + `regime_confidence` exposed,
   `regime_confidence=None` → SUCCESS (not PARTIAL); missing snapshot → `UNAVAILABLE`;
   no-recompute / no-network; frozen-result; no-directive guard (no action field).
6. Docs: flip coverage row 10 → 🟢; journey changelog row.

## 4. Acceptance

- [ ] Returns stored regime + `conviction` + `regime_confidence` + factor readings
  for as_of (latest default), scoped to the canonical cohort.
- [ ] Cohort-scoped read; a multi-cohort date does not false-`UNAVAILABLE`.
- [ ] Cache-only: reads a stored snapshot, never recomputes or fetches.
- [ ] PIT respected; missing → `UNAVAILABLE`; partial factors → PARTIAL; no directive.
- [ ] Offline agent suite + golden UX pilot green; Ruff green.
- [ ] Coverage row 10 → 🟢; completion record filled.

## 5. Non-goals

- Recomputing regime; any enter/size/action directive; per-ticker regime override;
  new provider/fetch; external/elevated; writes.

## 6. Completion record (fill when done)

- Authorizing ADR: ADR-061 · Implemented date: · Commits: · Coverage row: 10
