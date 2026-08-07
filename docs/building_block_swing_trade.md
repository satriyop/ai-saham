# Building Block: Swing Judgment, Structure, and Paper Handoff

This document summarizes the current executable swing boundary. Code and live
CLI help remain authoritative when this summary drifts.

## Command ownership

| Command | Current job | Action authority |
|---|---|---|
| `saham screen accum --universe …` | Discover and rank candidates | Board/provisional output only |
| `saham screen accum TICKER` | Deep single-ticker judgment | Owns Signal, Risk, `TradeSetup`, and Action |
| `saham plan swing TICKER` | Build horizon, stop, target, sizing, and plan artifact | References screen judgment exactly; never recomputes Action |
| `saham trade accum log --ticker TICKER --from-plan` | Confirm paper-journal handoff | Accepts only a handoff-ready schema-2 plan |
| `saham backtest portfolio swing …` | Offline strategy simulation | No live Action |

## Current execution boundary

```text
cached market and broker data
  -> embedded accumulation screen evaluation
       -> exact screen Signal / Risk / TradeSetup / Action
       -> typed ScreenJudgmentReference
            AVAILABLE   -> exact TradeSetup retained
            UNAVAILABLE -> no Action, closed missing-state reason
  -> plan-owned structure
       -> ATR / entry / stop / target / lots
       -> optional diagnostic evidence and backtest views
       -> no Signal, Risk, TradeSetup, or Action production
  -> swing_trade_plan schema 2
       geometry_complete + AVAILABLE judgment -> handoff_ready
       otherwise                              -> structure/display only
```

`PlanSwingDecisionComposer` only resolves the screen reference. It has no
SignalEngine, RiskEngine, gate, MCE, or `AssessTradeSetupUseCase` dependency.
The canonical candidate builder remains responsible for composing the screen
pipeline and its deterministic judgment.

Optional setup, flow, phase, strategy, institutional, sector, company-quality,
corporate-calendar, backtest, and sentiment sections are diagnostic evidence.
They may explain the candidate or structure, but cannot create or replace the
screen Action.

## Unavailable judgment

The closed reasons are:

- `no_screen_candidate`
- `no_screen_signal_assessment`
- `no_screen_risk_assessment`
- `no_screen_trade_setup`

A present but inconsistent screen judgment is an invariant error. Ticker or
date mismatch, a setup without its screen signal/risk prerequisites, or an
unknown enum fails closed. Plan does not repair or downgrade malformed
authority.

## Artifact and handoff

Every completed plan workflow saves `swing_trade_plan` schema 2 to the latest
ticker path and an immutable plan-ID copy. The artifact separates:

- `geometry_complete`: entry, stop, target, and positive lots exist.
- `handoff_ready`: geometry is complete and judgment is `AVAILABLE`.

`trade accum --from-plan` requires both. Schema 1, unknown schemas, wrapped or
flat legacy payloads, malformed judgment identity, unavailable judgment, and
incomplete geometry are rejected. Historical schema-1 files are not migrated
or reinterpreted; rerun screen and plan to create schema 2.

## Layer ownership

- Domain: typed plan artifact, judgment enums, geometry/readiness invariants.
- Application: screen-reference resolution, structure orchestration, evidence assembly.
- Infrastructure: cached repositories and existing plan JSON filesystem.
- Adapter: CLI/TUI rendering, saving, and explicit paper-handoff invocation.

Adapters do not infer authority. AI remains optional, diagnostic, and unable to
alter scores, risk, Action, or handoff readiness.
