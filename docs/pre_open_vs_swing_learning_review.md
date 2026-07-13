# Pre-Open/Intraday vs Swing Learning and Tuning Review

**Review date:** 2026-07-13  
**Scope:** The pre-open/intraday `snapshot → track → grade → tune` workflow compared with the swing backtest, attribution, review, and guarded tuning workflow.  
**Purpose:** Determine which path is stronger, which parts are worth maintaining, and which design elements should be shared without incorrectly forcing two different trading horizons into one learner.

## Executive verdict

The two learning paths should remain **domain-specific**, because opening-auction behavior and multi-day swing behavior have different inputs, execution constraints, labels, and sources of uncertainty. They should not, however, maintain different standards for statistical evidence or configuration promotion.

The current relative strengths are:

- **Better live observation collection:** pre-open/intraday.
- **Better tuning governance:** swing.
- **Safer tuning workflow today:** swing, but still diagnostic rather than proven predictive learning.
- **Worth retaining:** pre-open snapshot, tracking, deterministic grading, journaling, and manual outcomes.
- **Not trustworthy for config decisions:** session-by-session AI `learn tune` recommendations.

The recommended direction is to preserve the pre-open event-time observation pipeline, replace its current tuner authority with swing-style deterministic attribution and patch validation, and bring pre-open's timestamp/data-quality discipline into the swing workflow.

## What was reviewed

The review treated current working-tree code as behavior and documentation as intent. Main surfaces included:

- `src/application/use_case/opening_snapshot_use_case.py`
- `src/application/use_case/opening_track_use_case.py`
- `src/application/use_case/opening_grade_use_case.py`
- `src/application/use_case/opening_tune_use_case.py`
- `src/application/use_case/opening_prompt_use_case.py`
- the intraday confirmation journal and daily-OHLC backtest
- the swing backtest, attribution, tuning review, config-diff, patch validation, apply, and post-apply measurement services
- `config/pre_open_screener.yaml` and the swing-related engine/tuning configs
- persisted artifacts under `data/opening/`

`opening_grade_use_case.py` was already modified in the shared working tree during this audit. This report describes the inspected working-tree behavior and does not alter that file.

## Direct comparison

| Dimension | Pre-open/intraday | Swing |
|---|---|---|
| Observation quality | Stronger: timestamped NCP and post-open observations | Mostly historical daily replay and forward labels |
| Match to live workflow | Strong: captures the actual auction/session environment | Moderate: daily-bar replay approximates execution |
| Current sample | Extremely small: 17 valid tracked candidates across seven recent sessions | More rows, but correlated and historically narrow |
| Outcome definition | Ambiguous in some important path-order cases | More complete portfolio and candidate attribution |
| Counterfactual coverage | Weak: mainly selected mover candidates | Better: candidate observations include non-executed candidates |
| Deterministic grading | Present | Present |
| Statistical readiness gates | Essentially absent from opening tuning | Stronger and fail-closed |
| OOS/walk-forward controls | Absent from opening tuner | Explicit, though not yet sufficient to prove alpha |
| Config target allowlist | Absent | Explicit |
| Parameter bounds/shift caps | Absent | Explicit |
| Patch validation/audit | Absent | Strong |
| AI authority | AI directly invents recommendations from one session | AI/recommendation artifacts are downstream of deterministic attribution and constrained contracts |
| Current usefulness | Valuable observational research | Safer tuning architecture, still empirically immature |

## What is particularly good in the pre-open path

### 1. The observation sequence is correct in principle

The `snapshot → track → grade` structure is the strongest part of the workflow.

It captures an immutable prediction state before the outcome and then observes the market after the opening auction. This is closer to a valid event-time experiment than reconstructing a call auction solely from daily OHLC.

Useful persisted fields include:

- capture phase, confidence, and NCP-lock status;
- IEP and IEV;
- pre-open bid pressure;
- post-open order-book pressure and depth;
- explicit price source and price confidence;
- optional running-trade/broker confirmation;
- subsequent T0/T5/T15/T30-like observations.

The tuner normally refuses invalid OPEN, POST_OPEN, out-of-session, or low-confidence capture artifacts. That is a good anti-leakage/data-quality guard.

### 2. It observes the mechanism the strategy actually trades

An opening strategy depends on auction-specific behavior:

- changing IEV and IEP;
- NCP imbalance;
- opening clearing price;
- the change in pressure from NCP to executable post-open liquidity;
- spread, tick friction, and early absorption;
- momentum persistence or immediate opening fade.

Those mechanisms cannot be adequately learned from the swing path's daily forward-return labels.

The stored sessions already expose a plausible research hypothesis: extremely high pre-open bid pressure sometimes collapses immediately after the open. The **change** from NCP pressure to T0/T5 pressure may be more informative than the absolute NCP pressure. This is a hypothesis to validate across many sessions, not yet a production rule.

### 3. It records execution failure, not only direction

IEP error, entry-range error, tick friction, pressure decay, stop feasibility, and momentum persistence are appropriate opening-workflow diagnostics. A directional forecast can be correct while an opening trade remains unprofitable due to spread, gap, stop placement, or failure to fill.

### 4. It is worth collecting even if the strategy fails

The observation dataset has independent value. With enough valid sessions it can determine whether IEV/IEP, bid pressure, broker absorption, or opening setup labels add value—or demonstrate that they do not. That makes snapshot and tracking infrastructure worth maintaining regardless of the eventual strategy verdict.

## What is weak in the current pre-open learning path

### 1. The sample is far too small for tuning

Across seven recent high-confidence/NCP-locked graded sessions, the stored sample contains only 17 tracked candidates. Descriptively:

- 14/17 opening prices were inside the predicted entry range;
- 7/17 matched the direction label at the second available observation (intended T+5);
- 9/17 matched at the seventh available observation (intended T+30);
- 2/17 met the current `clean_trade` definition.

These are **not strategy-performance estimates**. The sample includes SKIP candidates, legacy/schema-incomplete records, highly correlated names from the same session, and imperfect execution proxies. Seventeen candidates from seven mornings provide seven primary market-condition clusters, not 17 independent trials.

Despite this, the current tuner produces config recommendations from a single day and sometimes a single ticker.

### 2. The generated recommendations are unstable and contradictory

Persisted tune artifacts recommend, on successive small samples:

- `atr_range_cap_max`: 5% → 8%, then 3%, then 8%, 3.5%, 3%, and 7%;
- `min_target_ticks`: 3 → 5, then 2, then 4;
- disabling tick friction for mutually inconsistent reasons;
- lowering the IEV unusual-volume threshold on the unsupported assumption that it necessarily controls candidate inclusion.

This is small-sample narrative fitting. The recommendations respond to the latest session rather than estimating a stable conditional effect.

### 3. It proposes invalid or nonexistent config targets

Observed AI suggestions include:

- `bid_pressure_preopen_threshold`;
- `bp_preopen_min`;
- `bp_T0_min`;
- `bp_momentum_min`;
- `clean_trade_confirmation_window`.

Some may be reasonable feature proposals, but they are not automatically valid patchable paths. Unlike swing tuning, the opening tuner lacks a target catalog, schema/path resolution, type checks, numeric bounds, quantization, maximum-shift rules, and semantic validation.

One persisted tune artifact contains recommendation objects with no `suggested` value. The output parser still accepts and stores the artifact.

### 4. AI explanations sometimes misunderstand parameter semantics

Examples include treating a wider ATR entry-range cap as giving a position more room before its stop, or treating `min_target_ticks` as a direct measure of initial momentum strength. These are persuasive narratives, but the claimed causal relationship does not necessarily follow from the implementation.

The AI currently receives a summarized session and current values, then invents both diagnosis and parameter action. It does not receive deterministic marginal-effect attribution or a validator result.

### 5. The clean-trade metric cannot resolve path ordering

The opening grade takes the maximum and minimum of sampled prices and defines a clean trade as target available with no stop observation. Five-minute snapshots cannot reliably determine whether target or stop occurred first within an interval. They may also miss both excursions.

This differs from the daily intraday backtest, which assumes stop first when both the daily high and low cross their barriers. The live grade and backtest therefore do not measure exactly the same outcome.

The grade can be conservative in one case—target first followed by a later stop still fails `clean_trade`—and optimistic in another when an intra-interval stop is not sampled.

### 6. Intended horizons depend on array position rather than elapsed time

The second, fourth, and seventh available observations are interpreted as T+5, T+15, and T+30. If a capture is late, duplicated, or missing, those labels can be incorrect. Grading should select by timestamp distance with explicit tolerance and report unavailable horizons when no qualifying observation exists.

### 7. Selected candidates do not provide sufficient counterfactuals

The learning snapshot mainly grades selected/top mover candidates. It cannot reliably determine:

- whether excluded candidates performed better;
- whether the top-N rule discarded winners;
- whether low-IEV eligible names were superior;
- whether PRIME/WATCH/SKIP adds value over the full eligible mover set;
- whether a gate improves expected outcomes or simply changes the observed sample.

This selection bias prevents safe tuning of discovery filters and verdict gates.

### 8. Schema drift limits aggregation

Among the 17 recent valid tracked candidates, many older grade rows do not contain a comparable `opening_setup`; the remaining sample is mostly SKIP with only one WATCH and no useful PRIME sample. This makes setup-level comparison and tuning impossible today.

### 9. Daily-OHLC intraday backtesting remains a coarse proxy

The intraday backtest appropriately uses d-1 features and the next candle open, but daily high/low cannot provide event ordering, fill quality, auction queues, partial fills, spread, or intra-session liquidity. The implementation correctly warns about same-day ambiguity, missing IEV-history coverage, and disabled replay of some gates. Its results should remain a baseline/sensitivity tool, not the final authority for an opening strategy.

## What is better in the swing tuning path

### 1. Deterministic attribution precedes recommendations

Swing tuning works from structured attribution dimensions rather than passing one session directly to an LLM. It distinguishes completed trades from candidate observations and carries sample-quality/readiness information.

### 2. Diagnostic-ready and patch-eligible are distinct

The swing validator fails closed when source evidence lacks required in-sample/OOS summaries, minimum samples, regime attribution, and declared walk-forward provenance. Although the existing statistical thresholds still need improvement, the separation of “interesting observation” from “allowed configuration mutation” is correct.

### 3. Configuration mutation is constrained

The swing path provides:

- an allowlisted target catalog;
- current-value resolution;
- path/type validation;
- numeric bounds and step sizes;
- maximum parameter movement per cycle;
- dry-run/review artifacts;
- explicit confirmation before application;
- application audit logs;
- post-apply measurement.

The opening path lacks these controls.

### 4. It records counterfactual candidate outcomes

Candidate observations help estimate the behavior of screened but unexecuted names. This is not a complete solution to survivorship or universe bias, but it is better than learning only from executed winners/losers.

## What remains weak in swing learning

Swing is better governed, not proven statistically superior.

- Its market history is still narrow.
- Forward-label rows overlap and are correlated across ticker, sector, and date.
- Declaring `walk_forward_enforced: true` is not proof that the upstream experiment was properly purged and embargoed.
- Minimum OOS trade counts remain too small for a high-dimensional parameter surface.
- Attribution strength relies heavily on count and bucket return spread without adequate clustered uncertainty or multiple-testing control.
- The daily-bar execution model and current-universe survivorship limitations remain material.

The swing path should therefore be the **governance template**, not treated as validated alpha.

## Is the pre-open path worth maintaining and using?

Yes, but its components should have explicit authority levels.

### Maintain and use operationally

- `learn snapshot`;
- `learn track`;
- capture-phase and data-confidence classification;
- immutable raw observation persistence;
- deterministic per-session grade as a diagnostic;
- intraday confirmation journal;
- manual actual-entry/exit outcome recording;
- daily-OHLC backtest as a conservative baseline and sensitivity check.

### Maintain as experimental research

- order-book pressure and pressure-change analysis;
- broker absorption analysis;
- IEP and entry-range accuracy;
- timestamp-correct momentum persistence;
- prompt generation for human investigation.

### Do not use for configuration authority

- one-session DeepSeek recommendations;
- any change supported by a single morning or ticker;
- recommendations targeting unregistered config paths;
- recommendations without a proposed value, bounds, and deterministic effect comparison;
- manually copied config edits without chronological OOS proof.

The command would be more honestly named `learn research-session` or its output should explicitly state `NON_ACTIONABLE_SESSION_HYPOTHESIS`. The name `tune` currently grants the artifact more authority than its evidence supports.

## What pre-open should adopt from swing

### P0 — Shared promotion and patch safety

Adopt the swing governance pipeline:

1. Aggregate many sessions before producing a tuning proposal.
2. Count independent trading days as the primary sample unit.
3. Separate `INSUFFICIENT`, `DIAGNOSTIC_READY`, and `PATCH_ELIGIBLE` states.
4. Define a deterministic tuning-target catalog.
5. Resolve current config values programmatically.
6. Reject unknown paths, missing suggested values, wrong types, and unbounded targets.
7. Enforce quantization and a maximum shift per tuning cycle.
8. Require chronological OOS comparison against the current production config.
9. Save immutable review, patch, apply, and post-apply artifacts.
10. Keep AI limited to explaining deterministic attribution and proposing only within an allowlist.
11. Require explicit human confirmation for application.
12. Automatically roll back or flag regression after a defined post-apply observation window.

Suggested initial evidence floors—not claims of statistical sufficiency—are:

- diagnostic review: at least 20 valid independent sessions;
- initial model comparison: 60–100 valid sessions;
- patch eligibility: multiple chronological folds and at least 20–30 untouched OOS sessions;
- minimum setup coverage for any PRIME/WATCH/SKIP change;
- minimum session counts within relevant liquidity and market-regime buckets.

These floors should be strengthened based on variance and the number of tested parameters. Candidate count alone must never replace independent-session count.

### P0 — Deterministic attribution before AI

For each registered parameter or feature, produce an attribution report with:

- eligible, selected, confirmed, filled, and completed counts;
- outcome difference versus the production baseline;
- distribution by session rather than pooled ticker rows only;
- confidence interval using session/block bootstrap;
- sensitivity across adjacent threshold values;
- turnover, spread, slippage, and capacity effect;
- stability across chronological folds;
- explicit data-quality exclusions.

Only this summary should reach an AI explanation layer.

### P0 — Correct the outcome contract

Define distinct labels:

- opening-price/IEP error;
- entry-range eligibility;
- actual fill status and price;
- target-before-stop outcome;
- close return after costs;
- MFE/MAE;
- time to target/stop;
- pressure persistence/decay;
- data confidence and unresolved ordering.

Use event/tick or sufficiently granular interval data for target-before-stop. When ordering cannot be established, label it `AMBIGUOUS` instead of forcing WIN/LOSS.

### P1 — Capture counterfactuals

Persist the full eligible pre-open mover set before top-N and verdict gates, including rejection reasons. Grade all eligible candidates observationally without pretending rejected names were tradable executions. This enables gate attribution without conflating selection and outcome.

### P1 — Use timestamp-based horizons

Resolve T+5/T+15/T+30 by elapsed time from the recorded opening timestamp with a tolerance window. Persist the selected observation timestamp and delay. Missing data should stay missing.

## What swing should adopt from pre-open

### 1. Observation timing and confidence

Swing observations should consistently persist:

- decision timestamp, not only date;
- input availability/cutoff time;
- source and confidence for entry price;
- whether the observation was live, historical replay, or derived;
- data freshness and capture validity.

### 2. Immutable pre-outcome snapshots

The exact feature/evidence/config snapshot used for a decision should be immutable. Outcome updates should be separate linked records rather than silently rewriting the original observation.

### 3. Path checkpoints

In addition to a final D10 label, swing should track D1/D3/D5/D10/D20, MFE, MAE, time-to-target, time-to-stop, gap behavior, and modeled-versus-realized execution. This helps distinguish bad selection from bad entry or exit policy.

### 4. Actual execution feedback

Manual or imported fill/exit records should measure the gap between backtest assumptions and realized results. A model with good paper ranking but poor fills, slippage, or stop execution is not operationally accurate.

## Recommended shared learning architecture

Keep domain-specific observation and grading, but share a single evidence and promotion kernel:

```text
Domain-specific immutable observation
    pre-open: NCP → T0/T5/T15/T30
    swing: signal → D1/D3/D5/D10/D20
                    ↓
Domain-specific deterministic outcomes
                    ↓
Counterfactual candidate attribution
                    ↓
Independent-session/sample readiness
                    ↓
Purged chronological OOS comparison
                    ↓
Validated target catalog + bounded diff
                    ↓
Optional AI explanation of deterministic evidence
                    ↓
Human-reviewed apply + post-apply measurement
```

The shared kernel should own:

- sample/readiness policy;
- chronological split and leakage rules;
- clustered uncertainty;
- baseline/champion comparison;
- target allowlists and bounds;
- patch review/application contracts;
- audit and rollback status.

The pre-open and swing applications should own their own observation schemas, outcome labels, execution models, feature attribution, and economically appropriate horizons.

## `saham today` as the primary daily integration point

The primary daily command should consume all three decision horizons consistently:

1. pre-open assessment;
2. accumulation discovery and canonical assessment;
3. bounded swing analysis for the strongest eligible candidates.

The current briefing is asymmetric. It shows a pre-open verdict, but its accumulation section displays only foreign-flow score, streak, and trend. It does not show canonical SignalEngine, RiskEngine, setup, or TradeSetup results, and it does not perform swing analysis.

This is a P0 product gap. A first daily command should not require the user to infer that a high foreign-flow score is merely a discovery signal and then manually guess which ticker deserves complete analysis.

### Current accumulation score is not a swing verdict

The `Score` currently displayed by `saham today` is `foreign_flow_score`. It is not:

- the canonical SignalEngine score;
- a calibrated success probability;
- a setup-quality result;
- a RiskEngine decision;
- a TradeSetup action;
- proof of sufficient data coverage;
- a recommendation to enter.

For example, a ticker with foreign-flow score 77.3 may still have:

- missing or low-coverage signal evidence;
- no valid swing setup;
- exhaustion/distribution phase;
- structural or execution risk gates;
- stale candle or broker data;
- an AVOID or BLOCKED TradeSetup action.

The section should therefore be called **Foreign-Flow Discovery** unless the full canonical assessment has been composed.

### Required daily composition

The desired deterministic pipeline is:

```text
Selected universe
    ↓
Per-dataset readiness and completed-session cutoff
    ↓
Structural eligibility
    ↓
Accumulation discovery across the full ready universe
    ↓
Canonical signal assessment for survivors
    ↓
Risk funnel
    ↓
TradeSetup composition
    ↓
Canonical ranking
    ↓
Compact swing analysis for the top eligible candidates
```

The final top set must not be selected solely by foreign-flow score before signal, risk, and setup composition. Otherwise the command can miss a lower-flow candidate with substantially better setup quality, evidence coverage, and risk status.

### Canonical ranking policy

Recommended ranking priority:

1. data readiness and minimum evidence coverage;
2. structural eligibility;
3. TradeSetup action rank: ENTER, WATCH, AVOID, BLOCKED_EXECUTION, BLOCKED_STRUCTURAL;
4. setup match and setup phase;
5. canonical signal coverage/conviction;
6. canonical SignalEngine score;
7. foreign-flow score;
8. liquidity/capacity;
9. sector diversification for the final shortlist.

Raw numerical score must not override a structural block, insufficient evidence, or absence of a valid setup.

### Required accumulation assessment

The daily briefing should first summarize the funnel:

```text
ACCUMULATION SCREEN
Universe checked: 45
Data-ready:        41
Structural pass:   12
Flow candidates:    6
Canonical WATCH:    2
Canonical ENTER:    0
Blocked:            3
Insufficient data:  1
```

Then show the best survivors with comparable decision fields:

```text
Ticker  Flow  Phase         Signal  Coverage  Risk       Action  Primary reason
INDF    60.6  ACCUMULATION  72      82%       OPEN       WATCH   Setup not confirmed
BBTN    56.9  COMPRESSION   68      76%       OPEN       WATCH   Await breakout
GOTO    77.3  EXHAUSTION    61      64%       EXECUTION  AVOID   Distribution risk
```

These values are illustrative layout examples, not audited current assessments for the named tickers.

The table must include candle and broker-data as-of dates when they differ from the briefing session.

### Required bounded swing assessment

After canonical accumulation ranking, the command should run a compact swing assessment for a bounded top set—three candidates by default. The summary should include:

- setup family and match status;
- setup phase;
- canonical signal score and evidence coverage;
- RiskEngine status and blocking gate;
- canonical TradeSetup action;
- market-context regime and optional preview effect;
- freshest candle and broker dates;
- primary supporting evidence;
- primary invalidation, blocker, or missing confirmation;
- the detailed follow-up command.

Example:

```text
SWING SHORTLIST
1. INDF — WATCH
   Setup: foreign-bounce, partial match
   Signal: 72, coverage 82% | Risk: OPEN
   Positive: persistent foreign accumulation
   Missing: breakout confirmation
   Next: saham analyze swing INDF

2. BBTN — WATCH
   Setup: coiled-spring, partial match
   Signal: 68, coverage 76% | Risk: OPEN
   Positive: compression with improving flow
   Risk: resistance headroom limited
   Next: saham analyze swing BBTN
```

When nothing qualifies, `NO ENTER CANDIDATES` or `NO ACTIONABLE SWING SETUPS` is the correct primary result. The command must not fill the table with weak names merely to show a fixed top count.

### Data readiness must control assessment authority

The inspected daily output combined a live session with incomplete current-day EOD candles and continued to display rankings. The briefing needs separate clocks:

```text
Live session date
Latest completed EOD analysis date
Opening snapshot date
```

It also needs per-dataset readiness rather than one candle count:

```text
Dataset                 Required as-of  Coverage  Status
Completed candles       YYYY-MM-DD      41/45     PARTIAL
Broker/foreign flow     YYYY-MM-DD      45/45     READY
Market context          YYYY-MM-DD      6/6       READY
Opening snapshot        YYYY-MM-DD      valid NCP READY
Point-in-time enrichment YYYY-MM-DD     37/45     PARTIAL
```

If required readiness falls below policy, candidate rankings should be suppressed or explicitly marked non-authoritative. A warning below a normal-looking green/yellow ranking is not sufficient.

### Universe scope must remain explicit

The opening snapshot may contain market-wide movers that are not members of the requested briefing universe. The command must either:

- filter opening rows to the selected universe; or
- label them explicitly as `Market-Wide Pre-Open Movers` and separately report that no requested-universe setup qualified.

A briefing titled LQ45 must not silently present non-LQ45 names as its top candidates.

### Phase-aware daily action

The final next action should depend on the IDX session:

- before pre-open: refresh required data and capture IEV;
- NCP window: run the snapshot/pre-open assessment;
- opening window: confirm actionable opening setups;
- regular session: track opening outcomes and inspect the swing shortlist;
- after close: refresh completed candles, grade the opening session, and prepare the next-session list;
- historical mode: show replay/review actions, not the current live market status.

Return one primary next command and then optional alternatives. Do not end with a generic command chain containing an unresolved `TICKER` placeholder.

### Architecture boundary

`saham today` must not invoke other CLI commands or parse their display output. The application layer should compose reusable use cases and return a daily briefing DTO. The adapter should remain responsible only for flags, dependency wiring, rendering, and error mapping.

A suitable application composition is conceptually:

```text
DailyBriefingUseCase
  ├── MarketDataReadinessService
  ├── MarketContextEngine
  ├── OpeningSnapshotReader
  ├── AccumulationScreenUseCase
  └── DailySwingShortlistUseCase
```

`DailySwingShortlistUseCase` should consume already-built accumulation candidates and their evidence rather than rescanning each ticker. It should return a compact summary DTO rather than the full verbose swing-analysis display model.

### Performance and provider policy

The default daily command should remain deterministic, local, and read-only:

- run accumulation discovery once;
- reuse candidate evidence for SignalEngine and setup assessment;
- run RiskEngine only for survivors;
- produce full compact swing summaries only for the final bounded set;
- perform no implicit network refresh;
- target completion within approximately 5–8 seconds.

An optional deeper mode may enable more cached enrichment, but network refresh should remain an explicit separate command.

### Recommended target layout

```text
Daily Briefing — 13 Jul 2026
Universe: LQ45

STATUS
Data readiness: NOT READY / PARTIAL / READY
Live session:   REGULAR
Analysis date:  latest completed IDX session

MARKET POSTURE
RISK_ON — low confidence
Local trend stressed | Breadth neutral | No gate tightening

PRE-OPEN ASSESSMENT
No actionable LQ45 setup
Market-wide movers: RBMS SKIP | BNBR SKIP

ACCUMULATION SCREEN
45 checked | 6 flow candidates | 2 WATCH | 0 ENTER | 3 blocked

Ticker  Flow  Phase         Signal/Coverage  Risk  Action
INDF    60.6  ACCUMULATION  72 / 82%         OPEN  WATCH
BBTN    56.9  COMPRESSION   68 / 76%         OPEN  WATCH
GOTO    77.3  EXHAUSTION    61 / 64%         BLOCK AVOID

SWING SHORTLIST
1. INDF — WATCH — wait for breakout confirmation
2. BBTN — WATCH — resistance headroom limited

NO ENTER CANDIDATES TODAY

NEXT ACTION
Review INDF: saham analyze swing INDF
```

### Revised P0 priority for the primary command

1. Restore CLI startup reliability.
2. Separate live-session, completed-EOD, and opening-snapshot dates.
3. Add fail-closed per-dataset readiness.
4. Enforce or clearly label universe scope.
5. Add canonical accumulation assessment.
6. Add bounded top-three swing assessment.
7. Rank by TradeSetup, setup match, coverage, and risk—not raw flow score.
8. Present pre-open, accumulation, and swing verdicts with equal authority semantics.
9. Emit a phase-aware primary next action.

## Recommended implementation sequence

### Phase 1 — Stop authority leakage

- Mark opening `tune` output non-actionable.
- Reject malformed recommendations and unknown paths even for display.
- Do not copy existing one-session recommendations into config.
- Preserve raw snapshots, tracks, grades, and manual outcomes.

### Phase 2 — Stabilize the opening dataset

- Version observation and grade schemas.
- Resolve timestamp-based horizons.
- add `AMBIGUOUS` path-order outcomes;
- capture the full eligible/counterfactual set;
- add config/version fingerprints and data-source confidence;
- report independent valid sessions and schema coverage.

### Phase 3 — Reuse swing governance

- Introduce opening tuning target catalog and bounds.
- Add deterministic aggregate attribution.
- Add diagnostic and patch-readiness states.
- Add chronological OOS review artifacts.
- Reuse guarded diff, apply, audit, and post-apply concepts.

### Phase 4 — Validate before promotion

- Collect at least several months of valid sessions before first serious comparison.
- Compare the current policy against simple baselines.
- Evaluate each proposed feature by ablation and adjacent-threshold stability.
- Promote only improvements that survive untouched OOS sessions and stressed execution costs.

## Bottom line

The pre-open path is worth maintaining because its timestamped auction/session data is difficult to reconstruct later and is the right raw material for an opening strategy. Its current AI tuner, however, is materially weaker and less safe than the swing tuning framework. It should not guide config changes.

The strongest combined design is:

- **pre-open's event-time capture and execution diagnostics**;
- **swing's deterministic attribution, sample gates, config allowlist, bounded patching, human approval, and post-apply measurement**.

Keep different domain learners, but enforce one standard of evidence and one guarded promotion mechanism.
