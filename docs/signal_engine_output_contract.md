# SignalEngine Output Contract

This document extracts output and persistence guidance from the historical
[SignalEngine refactor rationale](archive/signal_refactor_full_rationale.md).
It is a design reference only. Current schemas, config, code, tests,
`ARCHITECTURE_DECISIONS.md`, and `AI_AGENT_CHECKLIST.md` are authoritative.

## Group Model

The canonical group model is:

```text
setup_quality
institutional_flow
market_context
company_quality_context
```

Each group should expose enough metadata for audit and replay:

```text
raw evidence values
normalized group score
coverage
conviction
configured weight
effective weight after evidence-authority enforcement
authority status
Alpha fraction by horizon
rationale and unavailable reasons
```

Component weights inside a configured group must satisfy validated totals.
`DIAGNOSTIC` evidence cannot contribute to score, `LOW_WEIGHT` evidence is
capped, and `PRODUCTION` evidence may use normal configured authority.

Alpha and Trigger are normalized routes over these canonical groups. They must
not become parallel scoring paths with duplicated evidence.

## Persisted Sub-Signal Fingerprints

Every saved signal/candidate observation should preserve evidence as it existed
at signal time. Recomputing later from current data risks look-ahead and prevents
reliable attribution.

The fingerprint may include:

```text
setup family and all matched families
current and previous setup phase
phase history/age and sequence validity
RSI and BB width percentile
VWAP position
relative strength versus IHSG
volume ratio and primary-trigger state
CNFB and valid-session coverage
foreign participation and concentration
domestic broker accumulation evidence
market/sector regime metadata
ticker profile and profile confidence
signal_authority_coverage
typed setup readiness
phase_input_coverage (diagnostic)
phase_detection_strength (diagnostic)
directional signal score
evidence authority statuses
```

Persist raw values alongside normalized values where attribution requires both.
Unavailable evidence remains explicitly unavailable; it must not be stored as a
fabricated zero.

Replay-relevant enrichment uses point-in-time data available on or before the
observation `as_of_date`. Derived historical fundamentals follow ADR-038 and
must not fabricate fields outside their admitted source contract.

Forward labels are separate outcome records with explicit success, failure,
neutral, and unavailable states per horizon. Tuning consumes saved observations
and their eligible forward labels.

## Output Contract

A complete response should make scoring and policy independently auditable.
The conceptual shape is:

```text
identity:
  ticker
  observation/as-of date
  horizon
  setup family and matched families

scores:
  canonical group scores
  alpha_score
  trigger_score
  exact/raw composite score
  display score where compatibility requires an integer
  signal_authority_coverage
  typed setup readiness
  phase_input_coverage (diagnostic)
  phase_detection_strength (diagnostic)
  directional signal score

state:
  SetupPhaseState
  phase history and sequence validity
  ticker profile
  market and sector context

policy:
  decision
  max_decision
  eligibility
  constraint reasons
  regime/volatility/liquidity size multipliers
  effective size multiplier

evidence:
  authority statuses
  sub-signal fingerprint
  main reasons
  unavailable reasons
  risk/warning reasons
```

Decision constraints are explicit outputs for TradeSetup and sizing policy to
consume. SignalEngine may emit volatility context and ATR hints, but it does not
own final stop price, target price, or position size.

RiskEngine remains the only hard-gate authority. SignalEngine eligibility or
`max_decision` must not be represented as RiskEngine `BLOCKED`.

Score precision migration must be deliberate. If compatibility requires an
integer `score`, preserve it for display and add an exact/raw float rather than
silently changing persisted or public types.

## Decision Contract

Decision policy should make constraint ordering visible. Conceptually:

```text
hard risk gate
 -> signal authority coverage floor
 -> typed setup readiness
 -> phase/regime constraints
 -> directional score threshold
 -> ENTER/WATCH/AVOID
```

Exact labels, ordering, thresholds, and exceptions come from current validated
config, application policy, and tests.

## Acceptance Criteria for Future Work

Future changes based on this design should satisfy these condensed gates:

- One canonical production signal path; no adapter-owned scoring policy.
- Fully deterministic and functional without AI.
- Pattern-specific calibration within a general, composable architecture.
- Explicit universe, profile, horizon, setup family, flow track, phase sequence,
  regime scope, and patch-eligibility gates for calibrated setups.
- Strategies/plugins/formulas produce evidence but do not override decisions.
- Coverage and conviction remain distinct and both constrain `ENTER`.
- Setup phases and phase sequence are persisted and replayable.
- Accumulation-style `ENTER` requires configured breakout confirmation after
  the required prior phases.
- Primary trigger patterns enforce data-quality availability rules.
- Regime affects explicit eligibility/threshold/size constraints, not hidden raw
  score multipliers.
- RiskEngine remains the only hard-gate authority.
- Evidence authority caps are config-backed and validator-enforced.
- Raw net-buy intensity never directly creates `ENTER`.
- Relative strength policy is setup-family-specific and validator-bounded.
- Indicator ownership prevents duplicate scoring across Setup and Trigger.
- Institutional flow tracks preserve raw, normalized, coverage, conviction, and
  authority metadata.
- Sparse data and zero denominators produce unavailable evidence, not guessed
  values.
- Seasonality and event evidence obey sample-size and no-lookahead rules.
- Saved observations contain point-in-time fingerprints and eligible forward
  labels for walk-forward attribution.
- Evidence remains diagnostic/low-authority until out-of-sample discrimination
  supports promotion.
- Tuning changes require sample floors, OOS performance, attribution, bounded
  config paths, and manual approval where required.
- Persisted schema/type changes include compatibility notes and explicit
  migration behavior.

The archived rationale contains the full historical acceptance list. It is
preserved as evidence, not an active checklist.

## Layer Plan for Future Work

```text
Domain:
- immutable evidence, setup-phase, regime, score, and result value objects
- no provider, repository, CLI, or AI dependencies

Application:
- evidence builders and setup-phase transition policy
- profile classification and Alpha/Trigger aggregation
- regime and decision policy orchestration
- replay labeling, attribution, and calibration use cases

Infrastructure:
- provider and repository implementations
- plugin loading and local persistence
- schema-versioned observation storage

Adapter:
- request parsing and dependency wiring
- display formatting and error mapping only
```

Workflow, cache freshness, scoring, tuning, and decision policy must not move
into CLI adapters.

## Related Documents

- [Design Overview](signal_engine_design_overview.md)
- [Evidence Model](signal_engine_evidence_model.md)
- [Documentation Index](signal_refactor.md)
- [Archived Full Rationale](archive/signal_refactor_full_rationale.md)
