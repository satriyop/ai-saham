# Goal Instruction — `get_ticker_research_brief` (composed one-shot context)

**Status:** `READY FOR AGENT`
**Audience:** Implementation agent · **Product term:** AI Research Cockpit (`/`)
**Menu:** E (flagship synthesis) · Depth policy 2026-08-04.

**Binding architecture:**

| Doc | Role |
|---|---|
| [ADR-061](../../docs/adr/ADR-061-closed-read-tool-orchestration-for-context-agent.md) | Closed read tool; descriptive, read-only |
| [ADR-042](../../docs/adr/ADR-042-deterministic-champion-and-optional-model-challengers.md) | **Authority line** — the brief must not mint a verdict |
| Depth policy + READY gate | [`ai_research_cockpit_tool_coverage.md`](../../docs/roadmap/ai_research_cockpit_tool_coverage.md) |
| Composes (use cases, not agent tools) | judge/accumulation, `ViewTickerTopBrokersUseCase`, `ViewTickerForeignHistoryUseCase`, ownership source, corporate-action calendar read, `SQLiteMarketContextRepository.get` |

## 0. Mission

Turn "many small tools the model must chain" into **one coherent research brief**
for a ticker: accumulation Judge + broker flow + foreign flow + ownership +
corporate actions + market regime, composed as a **shared use case** powering an
agent tool, a CLI `brief` command, and a future TUI brief stage.

## 🚩 Authority guardrail (non-negotiable — ADR-042)

The brief is a **fact bundle that surfaces the deterministic Judge's existing
Action verbatim** with provenance. It **must NOT**:

- compute a new action/score/verdict, or a "brief conclusion" like "strong setup";
- re-rank, re-weight, or override any engine output.

The model narrates *around* the bundle; the only Action in the brief is the one the
deterministic engine already produced. If a synthesized verdict is ever wanted,
that is the **evidence-promotion lane (separate ADR)**, never this tool.

## 1. Layer plan

```md
- Domain: not touched
- Application: BuildTickerResearchBriefUseCase — orchestrates the underlying
  READ-ONLY use cases (not the agent tools), assembles a bundled descriptive
  result + the Judge's Action + per-section honesty; SHARED by CLI/TUI/agent
- Infrastructure: composition wiring (inject the sub-use-cases + repos it needs)
- Adapter: agent tool GET_TICKER_RESEARCH_BRIEF + CLI `brief` + TUI brief stage
  are thin projections of the same use case
```

## 2. Result (facts only)

Sections, each independently statused (honesty policy at section granularity):

- `judge`: the deterministic **Action** + key accum facts (surfaced, not recomputed)
- `broker_flow`: single-session top desks + bandar counts
- `foreign_flow`: net trend summary
- `ownership`: latest composition (+ history summary if available)
- `corporate_actions`: upcoming events
- `regime`: current market regime + confidence
- `as_of` per section + overall provenance

Bounded: each section capped (top-N / summary), overall result bytes capped. A
section that is missing is `UNAVAILABLE`/omitted with a note — the brief overall is
PARTIAL if any section is degraded (per the shared honesty policy). **No overall
verdict field.**

## 3. Slices

1. Contract: `AgentToolName.GET_TICKER_RESEARCH_BRIEF` + frozen bundled result DTO
   (each section a typed sub-DTO, reusing existing section shapes where possible).
2. Use case: `BuildTickerResearchBriefUseCase` — compose the read-only sub-use-cases
   PIT-aligned to one `as_of`; per-section try/degrade; surface Judge Action verbatim.
3. Tool: args `ticker` (required), optional `sections` (subset), optional caps.
4. Register in composition when `tools_enabled` + deps present.
5. Tests: composed happy path; **authority guard** — assert NO action/verdict/score
   field beyond the surfaced Judge Action; per-section PARTIAL/`UNAVAILABLE`;
   PIT alignment across sections; byte cap; no-fetch; frozen-result.
6. Docs: add a coverage "synthesis" row; journey changelog; note the CLI/TUI reuse.

## 4. Acceptance

- [ ] One call returns the composed brief with the deterministic Judge Action surfaced.
- [ ] **No** cockpit-minted verdict/score anywhere in the result (guard test passes).
- [ ] Sections degrade independently (honesty policy); PIT-aligned; read-only; no fetch.
- [ ] Shared use case usable by CLI/TUI adapters.
- [ ] Offline agent suite + golden UX pilot green; Ruff green.

## 5. Non-goals

- Any overall verdict / "brief conclusion" / composite score (ADR-042 line).
- Writes/fetch; external/elevated; re-ranking or overriding engine outputs.
- Duplicating section computation — compose the existing use cases.

## 6. Completion record

- Authorizing ADR: ADR-061 (composition; surfaces existing Action, no new authority)
- Implemented date: · Commits:
