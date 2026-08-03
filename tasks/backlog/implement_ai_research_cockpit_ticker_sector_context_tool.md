# Goal Instruction — Implement `get_ticker_sector_context` (sector strength / rotation)

**Status:** `READY FOR AGENT`
**Audience:** Implementation agent · **Product term:** AI Research Cockpit (`/`)
**Priority:** 5 of 5 (coverage row 13).

**Binding architecture:**

| Doc | Role |
|---|---|
| [ADR-061](../../docs/adr/ADR-061-closed-read-tool-orchestration-for-context-agent.md) | **Binding** — closed read tool; `side_effect=NONE`, facts-only → task, no new ADR |
| [ADR-053](../../docs/adr/ADR-053-sector-macro-context-evidence.md) | Sector macro context evidence (source of the data) |
| Coverage matrix | [`ai_research_cockpit_tool_coverage.md`](../../docs/roadmap/ai_research_cockpit_tool_coverage.md) (row 13) + honesty policy |
| Reuse | `candidate_sector_macro_context_evidence_assembler` and its inputs |

## 0. Mission

Give the model a ticker's **sector context** — sector identity, sector
strength/rotation reading, and peer positioning — so accumulation is judged
relative to a rotating-in vs falling sector. Closes coverage **row 13**.

Hard rules:

- `side_effect=NONE`, `approval=NONE`; cache-only over existing sector-macro evidence; no fetch/write.
- **Facts, not a score/verdict:** sector name, sector strength/trend readings, peer
  relative values as raw facts; **not** a sector buy/avoid call.
- Reuse the **existing** `candidate_sector_macro_context_evidence_assembler` (ADR-053);
  do not build a parallel sector engine.
- `UNAVAILABLE` when sector context is not derivable for the ticker; PARTIAL when
  some dimensions (e.g. peers) are missing (honesty policy). All stages (most useful
  on `accum_screen` / ticker stages).

## 1. Layer plan

```md
- Domain: not touched
- Application: AgentToolName.GET_TICKER_SECTOR_CONTEXT; result DTO
  (schema agent_tool.ticker_sector_context.v1); TickerSectorContextTool wrapping the
  sector-macro-context evidence assembler (read-only)
- Infrastructure: composition wiring (register when tools_enabled + inputs available)
- Adapter: none
```

**Verify first:** the inputs the assembler needs (sector mapping + macro/sector
series) are available cache-only in composition. If the assembler requires
pre-loaded inputs, wire a thin read-only provider — no fetch, no compute beyond the
existing assembler.

Read first: `src/application/services/candidate_sector_macro_context_evidence_assembler.py`,
ADR-053, the sector-macro DTOs in `accumulation_screen.py` / `plan_swing.py`,
`agent_ticker_dashboard_tool.py` pattern.

## 2. Result (facts only)

`ticker`, `sector` (and sub-sector if available), sector strength/trend reading(s),
peer relative positioning (bounded top-N peers with a raw relative metric), `as_of`,
provenance. **No** sector buy/avoid verdict.

## 3. Slices

1. Contract: `AgentToolName.GET_TICKER_SECTOR_CONTEXT` + frozen result DTO.
2. Tool: `TickerSectorContextTool` — arg `ticker` (required), optional `peers_limit`
   (cap, e.g. ≤ 10). Wrap the assembler read-only; bound peers + bytes.
3. Register in composition when `tools_enabled` + inputs available.
4. Tests (offline `pytest.mark.agent`): happy path; peers cap; missing sector →
   `UNAVAILABLE`; partial dimensions → PARTIAL; no-fetch; frozen-result validation;
   no-verdict guard.
5. Docs: flip coverage row 13 → 🟢; journey changelog row.

## 4. Acceptance

- [ ] Returns sector identity + strength/trend + bounded peer positioning for a ticker.
- [ ] Reuses the ADR-053 assembler; cache-only, no fetch; no verdict/score.
- [ ] Caps enforced; missing → `UNAVAILABLE`; partial → PARTIAL.
- [ ] Offline agent suite + golden UX pilot green; Ruff green.
- [ ] Coverage row 13 → 🟢; completion record filled.

## 5. Non-goals

- Any sector buy/avoid verdict or score; a new sector engine parallel to ADR-053;
  new provider/fetch; external/elevated; writes.

## 6. Completion record (fill when done)

- Authorizing ADR: ADR-061 · Implemented date: · Commits: · Coverage row: 13
