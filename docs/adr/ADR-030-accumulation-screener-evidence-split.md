# ADR-030: Accumulation Screener Evidence Split

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted — score scale amended by ADR-039; naming by ADR-043;
production evidence groups by ADR-067
**Date:** 2026-06-25
**Current implementation:** Accumulation screening separates accum/flow evidence,
signal assessment, risk assessment, final action, and data availability.
Composite accum score is 0–100 as **`accum_score`** (ADR-039 scale, ADR-043 name).
Production signal evidence group for accum is **`flow_confirmation` only** after
ADR-067 (`setup_quality` retired).

## Decision

Screening remains an application workflow, not a fourth first-class engine. It
selects, enriches, filters, sorts, and presents candidates by composing reusable
evidence and the existing engines.

The workflow must keep these questions distinct:

| Concern | Authority |
|---|---|
| Accumulation / broker-flow composite evidence | `ScoreAccumUseCase` / `AccumScoreBreakdown` (ADR-043; was foreign-flow naming) |
| Canonical signal assessment | `SignalEngine` |
| Risk blockers | `RiskEngine` |
| Final action | `AssessTradeSetupUseCase` / `TradeSetup` |
| Data availability and freshness | Typed application evidence metadata |

Public fields and filters use explicit names such as **`accum_score`** and
`signal_score` (ADR-043); generic `score` aliases are not new contracts. Scale
remains ADR-039 0–100. Profile participation metric may still use
`TickerProfileSnapshot.foreign_flow_score` (0–1) — different metric, keep name.

## Boundaries

- Screener-specific selection/setup policy belongs to the application workflow
  and its dedicated config, not SignalEngine or CLI rendering.
- The CLI parses options and renders the separate concerns; it does not merge or
  reinterpret their scores.
- Learning must correlate outcomes with the explicit evidence artifact, not an
  ambiguous aggregate screen score.

## Current implementation pointers

- `src/application/use_case/accumulation_screen_use_case.py` (or current screen workflow entry)
- `src/application/use_case/score_accum_use_case.py` (ADR-043 rename)
- `src/domain/value_objects/accum_score_breakdown.py` (ADR-043 rename)
- `config/accumulation_screener.yaml`

The retired 0–120 wording is preserved in ADR-039 and git history only. Retired
`setup_quality` production group is ADR-067; retired foreign-flow public field
names are ADR-043.
