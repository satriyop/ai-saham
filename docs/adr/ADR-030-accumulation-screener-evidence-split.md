# ADR-030: Accumulation Screener Evidence Split

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted — score scale amended by ADR-039
**Date:** 2026-06-25
**Current implementation:** Accumulation screening separates flow evidence, signal assessment, risk assessment, final action, and data availability. Foreign-flow score uses 0–100.

## Decision

Screening remains an application workflow, not a fourth first-class engine. It
selects, enriches, filters, sorts, and presents candidates by composing reusable
evidence and the existing engines.

The workflow must keep these questions distinct:

| Concern | Authority |
|---|---|
| Foreign-flow accumulation evidence | `ScoreForeignFlowUseCase` / `ForeignFlowScoreBreakdown` |
| Canonical signal assessment | `SignalEngine` |
| Risk blockers | `RiskEngine` |
| Final action | `AssessTradeSetupUseCase` / `TradeSetup` |
| Data availability and freshness | Typed application evidence metadata |

Public fields and filters use explicit names such as `foreign_flow_score` and
`signal_score`; generic `score` aliases are not new contracts. Current
foreign-flow values and thresholds use the ADR-039 0–100 scale.

## Boundaries

- Screener-specific selection/setup policy belongs to the application workflow
  and its dedicated config, not SignalEngine or CLI rendering.
- The CLI parses options and renders the separate concerns; it does not merge or
  reinterpret their scores.
- Learning must correlate outcomes with the explicit evidence artifact, not an
  ambiguous aggregate screen score.

## Current implementation pointers

- `src/application/use_case/accumulation_screen_use_case.py`
- `src/application/use_case/score_foreign_flow_use_case.py`
- `src/domain/value_objects/foreign_flow_score_breakdown.py`
- `config/accumulation_screener.yaml`

The retired 0–120 wording is preserved in ADR-039 and git history only.
