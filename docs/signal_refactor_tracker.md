# Signal Engine Refactor Tracker

_Design rationale: `docs/signal_refactor.md`_
_Phase plan: `docs/signal_refactor_phases.md`_
_Current implementation target: Phase I readiness audit_
_Updated: 2026-07-07 — persistence tests + CLI Alpha/Trigger & Sector Context rendering complete_

This tracker records implementation state and the concrete checklist for the
SignalEngine refactor. Phases A1–H are closed. Phase I is the active target.

---

## Authority

- `docs/signal_refactor.md` remains the design rationale.
- `docs/signal_refactor_phases.md` remains the execution plan.
- This tracker records current state and the concrete implementation checklist.
- If this tracker conflicts with the design rationale or phase plan, pause and
  update the tracker before implementation continues.

---

## Non-Negotiable Boundaries

- RiskEngine remains the only hard trade-risk gate authority.
- SignalEngine emits evidence, coverage/conviction, setup phase, context, and
  decision constraints.
- DecisionPolicy combines SignalEngine output with regime constraints.
- TradeSetup owns final stop, target, and position size.
- Regime evidence must not mutate the raw stock score.
- `enter_allowed=false` remains the authoritative ENTER block.
- Setup-specific policy may tighten regime policy, not loosen it.
- CLI adapters render results only; no scoring, cache, persistence, or workflow
  policy belongs in adapters.
- Closed Phase C added `SetupPhaseState`, phase-history persistence, and
  continuous setup/trigger evidence without rewriting the Phase G Alpha/Trigger
  aggregate architecture.
- Closed Phase C keeps price confirmation thresholds as placeholders until
  setup/horizon calibration proves them.
- Closed Phase C did not change TradeSetup sizing math.
- Closed Phase C did not promote flow or trigger evidence into production
  authority without saved-label attribution proof.
- Closed Phase C does not require AI or network-dependent tests.
- IDX foreign-flow transition inputs stay diagnostic / low-authority until
  market-level labels prove lead-time value.
- Closed Phase D added `StrategyEvidenceBuilder`, diagnostic-only strategy rule
  evidence, and replay fingerprint fields without affecting SignalEngine group
  scoring or DecisionPolicy.
- Closed Phase E added `InstitutionalAccumulationEvidence` (two-track foreign +
  domestic flow evidence, counterparty HHI), 23 `ia_*` fingerprint fields, and
  the `InstitutionalAccumulationEvidenceBuilder` as DIAGNOSTIC-only without
  affecting `FlowConfirmationEvidence` group scoring, `DecisionPolicy`, or
  `AssessSignalEvidenceUseCase`.
- Closed Phase F added `TickerProfileSnapshot` (liquidity, broker concentration,
  foreign flow, ATR-style volatility, index membership dimensions, soft primary
  profile exposures, and separate market tier), replay fingerprint fields,
  `TickerProfileClassifier` (builds index reverse index from `universes.yaml`
  at construction; never fetches data), and wired into both use cases as
  DIAGNOSTIC-only without affecting SignalEngine group scoring,
  `DecisionPolicy`, or `AssessSignalEvidenceUseCase`.
- The Phase G `company_quality_context` producer (2026-07-07) added a shared
  extracted conviction-scorer module (`company_quality_scoring`) and
  `CompanyQualityContextEvidence` + `CompanyQualityContextEvidenceBuilder`
  WITHOUT changing the `AssessSignalUseCase` flat-composite breakdown (byte-
  identical, guarded by its existing tests), group scoring, `DecisionPolicy`, or
  `RiskEngine`, and WITHOUT duplicating Piotroski, liquidity, free-float, bandar
  distribution, or technical-gate logic (those remain RiskEngine authority).

---

## Phase Overview

| Phase | Name | Status | Notes |
|---|---|---|---|
| Legacy 0-8 | Staged Evidence Foundation | Done | Historical foundation. |
| A1 | Regime Eligibility Policy Quick Win | Done | Implemented and verified; decision constraints are explicit. |
| A2 | Full RegimeDetectionEvidence And Replay | Done | Implemented 2026-07-05; all checklist items complete, 2347 tests pass. |
| B | Minimal Forward Labels And Observation Fingerprints | Done | Implemented and verified; saved labels and fingerprint attribution are operational. |
| C | SetupPhaseState And Continuous Setup/Trigger Scoring | Done | Closed 2026-07-06; diagnostic setup phase, replay history, and data-quality volume trigger implemented. |
| D | Strategy Evidence Harness | Done (2026-07-06) | Diagnostic-only strategy evidence harness. 2424 tests pass. |
| E | Institutional Accumulation Evidence | Done (2026-07-06) | Two-track institutional flow evidence, diagnostic-only. 2457 tests pass. |
| F | Minimal Ticker Profile Diagnostics | Done (2026-07-06) | Deterministic ticker behavior classifier, diagnostic-only. 2489 tests pass. |
| G | Simplified Alpha/Trigger Split | Done (2026-07-06; producers completed 2026-07-07) | Four canonical Alpha/Trigger slots configured. Both `market_context` (Phase H sector-context) and `company_quality_context` now have DIAGNOSTIC producers with zero scoring authority (`effective_weight` resolves to 0.0). `company_quality_context` producer: valuation/analyst/insider/capped-seasonality axes, `alpha_fraction=1.00`. |
| H | Sector Context | Done (2026-07-06) | Local-universe sector-relative return, breadth, ticker-vs-sector RS; DIAGNOSTIC-only; 2564 tests pass. |
| I | Full Walk-Forward Calibration And Expanded Tunables | In Progress (readiness audit) | Audit-first opening; no tuning patches or evidence promotion until OOS readiness is proven. |

---

## Open Items Index

All open items across all phases. This is the canonical list — phase sections below contain prose context but do not repeat these bullets.

### Phase C
- [ ] Enforce pullback requirements: trend/context support plus support reclaim
      or pivot confirmation.
- [ ] Enforce mean-reversion requirements: support/reversal evidence and
      explicit risk controls.
- [ ] Add dedicated support reclaim and squeeze release trigger routing beyond
      the current positive close / VWAP reclaim / volume expansion path.
- [ ] Add explicit CLI adapter rendering regression tests for phase/evidence
      output.

### Phase D
- [ ] Config-driven mapping from strategy package/rule to setup family + phase
      evidence (multi-match coexistence and conflict reporting).
- [ ] Empirical readiness summary from existing backtests (min sample size,
      SWING_10D grouping).
- [ ] CLI adapter rendering regression tests for strategy evidence display.
- [x] Document Phase G as first phase allowed to consume strategy evidence in
      Alpha/Trigger aggregation. _(Documented in Phase G implemented contract:
      strategy evidence is not passed into the aggregator; the Alpha/Trigger
      architecture is the gate before any future promotion.)_

### Phase E
- [x] Persistence integration test: verify `ia_*`, `sc_*`, and `cq_*` fields land
      in saved observation payload via `AccumulationScreenUseCase` with a broker-repo
      stub. _(Implemented 2026-07-07: `tests/application/use_case/test_accumulation_screen_persistence.py`,
      13 tests. Covers CNFB wiring, sector peer path, company-quality `cq_*`
      key-presence (2026-07-07), and structural key-presence guard distinguishing
      "key absent" from "key present with None".)_
- [ ] CLI adapter rendering for `InstitutionalAccumulationEvidence` / `ia_*`
      foreign-vs-domestic track details. _(Alpha/Trigger and Sector Context
      panels added 2026-07-07 close Phase G and Phase H display items
      respectively; Phase E `ia_*` detail rendering remains unimplemented.)_

### Phase G
- [ ] Phase D/E/F/H and company-quality diagnostic evidence not yet promoted
      into production scoring (all remain DIAGNOSTIC, awaiting Phase I OOS proof).
- [ ] `market_context` slot now has Phase H sector-context as a diagnostic
      producer but remains DIAGNOSTIC with zero scoring authority; promotion
      pending Phase I OOS proof.
- [x] `company_quality_context` slot now has a DIAGNOSTIC producer.
      _(Implemented 2026-07-07: `CompanyQualityContextEvidenceBuilder` +
      `CompanyQualityContextEvidence` VO; axes = valuation (forward P/E), analyst
      consensus, insider net-buy, and CAPPED generic seasonality via a shared
      extracted scorer module. `alpha_fraction=1.00` (pure Alpha). Registration
      stays DIAGNOSTIC so `effective_weight` resolves to 0.0 — zero scoring
      authority, verified by a test asserting `final_exact_score` is unchanged
      vs. an empty slot. No Piotroski/ROE/liquidity/free-float logic duplicated;
      those remain RiskEngine. Event alpha (MSCI/FTSE, dividend-chase, calendar)
      explicitly deferred — no data source exists. `cq_*` replay fingerprint
      fields persisted. Promotion to PRODUCTION deferred to Phase I.
      `config/company_quality_context.yaml` cannot promote this producer;
      authority is forced to DIAGNOSTIC in code. Promotion must happen through
      the Alpha/Trigger EvidenceRegistration path after Phase I proof.)_
- [ ] Promote `company_quality_context` slot from DIAGNOSTIC when OOS proof
      justifies (Phase I).
- [x] CLI display formatting for Alpha/Trigger diagnostics implemented.
      _(ALPHA/TRIGGER DETAIL panel: per-group score, weight, alpha/trigger
      weighted contributions, flow_trigger status. DIAGNOSTIC groups labelled
      "— no weight". Gated by `--signal-detail`.)_
- [ ] ATR hint thresholds and size multipliers are placeholders; not
      Phase-I-calibrated production tunables.
- [ ] `company_quality_context` seasonality cap and per-axis aggregation weights
      (`config/company_quality_context.yaml`) are config-driven placeholders,
      same status class as the ATR-hint placeholders; not Phase-I-calibrated.
- [ ] `company_quality_context` event alpha (MSCI/FTSE inclusion, dividend-chase
      windows, market calendar) explicitly deferred — no event-window data source
      or computation exists in the codebase. The `earnings_trend` axis is likewise
      deferred (recorded as an unavailable axis, excluded from coverage).
- [ ] Phase I walk-forward calibration, promotion workflow, and empirical
      readiness gates remain out of scope.

### Phase H
- [x] CLI rendering for sector context evidence display. _(Implemented
      2026-07-07: SECTOR CONTEXT panel shows sector label, regime, peer count,
      signed-pct metrics table, coverage, and "DIAGNOSTIC — no scoring impact"
      footer. Unavailable evidence renders a single dim reason line. Gated by
      `--market-detail`. `sector_context_evidence` wired from `SwingEvidence`
      through `swing()` → `_print_swing_output()` → `print_swing_output()`.)_
- [ ] Promote `market_context` Alpha/Trigger slot from DIAGNOSTIC when sector
      evidence proves discriminative (Phase I).
- [ ] Promote `company_quality_context` Alpha/Trigger slot from DIAGNOSTIC when
      company-quality evidence proves discriminative (Phase I).

### Phase I (Active — see Phase I Tracker for detail)
- [ ] Filter target candidates (blocked: no SWING_10D labels yet).
- [ ] Produce readiness summary (blocked: no forward labels).
- [ ] Propose validator-bounded tuning patches after readiness passes.
- [ ] Label readiness blocked until enough future sessions exist.

---

## Current Assumptions

- Phase H (Sector Context) is complete; Phase I is the next implementation target.
- Phase H sector context evidence feeds the `market_context` Alpha/Trigger slot
  as DIAGNOSTIC-only evidence; it can improve coverage/metadata but has zero
  score authority until a future promotion.
- Company-quality evidence feeds the `company_quality_context` Alpha/Trigger slot
  as DIAGNOSTIC-only evidence; it can improve coverage/metadata but has zero
  score authority (`effective_weight` = 0.0) until a future promotion. Its
  seasonality cap and aggregation weights are Phase-I-calibratable placeholders;
  event alpha and the `earnings_trend` axis are deferred (no data source).
- Phase F profile snapshots remain DIAGNOSTIC-only; profiles do not feed into
  SignalEngine group scoring or DecisionPolicy.
- Phase E institutional accumulation evidence is DIAGNOSTIC-only; `FlowConfirmationEvidence`
  group scoring is unchanged.
- Phase D strategy evidence contract is preserved; strategy evidence remains
  diagnostic and cannot override canonical setup phase or SignalEngine decisions.
- Phase B labels remain the source for replay attribution; no recomputation of
  historical evidence.
- Phase I tuning/config patching remains out of scope until Phase I is opened.
- Network-dependent tests remain out of scope for refactor phases.
- `SWING_10D` remains the first calibrated ticker-signal horizon.

---

## Known Technical Debt (Explicitly Tracked)

### TD-1: Double Regime Effect — regime_conditioning + decision_policy both active

**Status:** Transitional — tracked, not a blocker for Phase C planning.

**Description:** `AssessSignalEvidenceUseCase._condition_group_scores()` (Phase 5 legacy) mutates
group scores before renormalization when regime is RISK_OFF/VOLATILE/NEUTRAL. A1/A2 then adds
explicit `decision_policy` constraints on top. This creates a compound effect: score is discounted
AND ENTER is blocked.

**Contract violation:** The A1/A2 contract states "regime controls constraints, not score."
`assessment.score` still reflects regime conditioning. `signal_score_raw` (added in A2) preserves
the regime-neutral score for comparability.

**Documented workaround:**
- `config/signal_engine.yaml` `regime_conditioning.*` block marked TRANSITIONAL — DO NOT TUNE.
- `_condition_group_scores()` docstring marks it as transitional Phase 5 legacy.
- `AssessSignalResponse.signal_score_raw` holds the regime-neutral score.

**Resolution path:** When walk-forward validation (Phase I) confirms `decision_policy` alone
provides equivalent or better regime gating, remove `_condition_group_scores()` from the canonical
path and promote `signal_score_raw` → `assessment.score`. Requires updating test expectations.

---

## Phase A1 Tracker

**Status:** Done

**Implemented contract:** Config-driven regime thresholds; `enter_allowed`,
`max_decision`, `regime_size_multiplier`; WATCH/diagnostic coverage-conviction
floors; setup-specific regime compatibility policy; decision constraints emitted
in application output.

**Verification:** RISK_ON/NEUTRAL/RISK_OFF/VOLATILE decisions deterministic;
`enter_allowed=false` blocks ENTER regardless of coverage/conviction floors;
setup-specific policy cannot re-enable ENTER under RISK_OFF/VOLATILE; CLI
adapters display constraints only.

**Output contract fields exposed in signal/swing workflow results:**
`decision_constraints.max_decision`, `.regime`, `.regime_enter_allowed`,
`.regime_size_multiplier`, `.setup_family`, `.setup_regime_action`,
`.effective_size_multiplier`, `.constraint_reasons`.

---

## Phase A2 Tracker

**Status:** Done (2026-07-05)

**Implemented contract:** Deterministic `RegimeDetectionEvidence` with
replayable `regime_observations`; persisted regime inputs, fingerprints,
confidence, stability, days-in-regime, transition warning, and IHSG forward
labels; regime confidence/stability exposed in signal and swing workflow output;
deterministic replay and market-label validation tests.

**Carry-forward notes:** Realized volatility / adverse market movement deferred
to Phase I. Foreign buy/sell streaks stored as equal-weight approximations.
`banking_sector_vs_ihsg` unavailable when no `banking_universe` configured.
IDX foreign-flow transition inputs remain diagnostic / low-authority until
market-level labels prove value.

---

## Phase B Tracker

**Status:** Done (2026-07-05)

**Implemented contract:** Deterministic `signal_forward_labels` for
ticker-level outcomes; `SWING_10D` as first calibrated horizon while
`TACTICAL_3D` and `ACCUM_20D` remain diagnostic; persisted `sub_signal_fingerprint`
records; `saham analyze signal-labels` command; saved-label attribution summary
reads persisted labels and fingerprints without recomputing historical evidence.

**Carry-forward notes:** Same-day target/stop collisions conservatively labeled
as `FAILURE` until intraday order is available. Coverage and conviction stored
separately in observation fingerprints.

---

## Phase C Tracker

**Status:** Done (2026-07-06)

**Implemented contract:** Immutable `SetupPhaseState`
(NONE/ACCUMULATION/COMPRESSION/BREAKOUT_CONFIRMATION/EXHAUSTION/DISTRIBUTION/FAILED)
with sequence enforcement per setup family; phase history, age, strength,
reasons, and `phase_sequence_valid` persisted; RS vs IHSG promoted to setup
eligibility/max-decision evidence with per-family configurable RS policy;
BB compression as `COMPRESSION` readiness only; `volume_dry_up_then_expansion`
as primary SWING_10D trigger for accumulation/foreign-bounce/breakout; volume
data quality checks (valid 20d sessions, suspended days, missing candles,
zero-volume distortion); `coverage_score` and `conviction_score` emitted
separately; phase state persisted into signal and candidate observation
fingerprints.

**Verification:** No Alpha/Trigger rewrite; no TradeSetup sizing changes; all
checklist items verified.

**Layer summary:** Domain added immutable setup phase state and phase history value
objects. Application owns deterministic phase detection, sequence policy, RS policy,
volume-trigger availability, coverage/conviction calculation, and observation
persistence orchestration. Infrastructure extended local persistence/replay paths.
Adapter remains render-only.

**Carry-forward:** Open items listed in the Open Items Index above.

---

## Phase D Tracker: Strategy Evidence Harness

**Status:** Done (2026-07-06)

**Implemented contract:** Frozen `StrategyEvidence`/`StrategyRuleEvidence`
domain value objects with coverage, conviction, freshness, rationale, and
outcome (MATCHED/NOT_MATCHED/UNAVAILABLE/INVALID); `StrategyEvidenceBuilder`
evaluates strategy YAMLs through existing `IndicatorRegistry`; never raises
(degrades to UNAVAILABLE/INVALID); wired into swing workflow and accumulation
screen observation fingerprints under `strategy_*` fields; zero impact on group
scores or ENTER/WATCH/AVOID decisions (verified by grep); Phase B label
attribution extended with strategy evidence buckets; 2424 tests pass.

**Carry-forward:** Open items listed in the Open Items Index above.

---

## Phase E Tracker: Institutional Accumulation Evidence

**Status:** Done (2026-07-06)

**Implemented contract:** `EvidenceStatus` enum (DIAGNOSTIC/LOW_WEIGHT/PRODUCTION)
and four frozen dataclasses (`ForeignInstitutionalTrack`, `DomesticBandarTrack`,
`CounterpartyTransferEvidence`, `InstitutionalAccumulationEvidence`);
`InstitutionalAccumulationEvidenceBuilder` with `from_yaml()` factory implementing
all foreign (participation, CR4/CR8, CNFB bullish/bearish windows, foreign VWAP)
and domestic (broker consistency, reversal, accumulation session ratio, domestic
VWAP, HHI divergence, bandar normalisation) metrics; 23 `ia_*` fingerprint
fields (all `None`-defaulted; `data.get()` in `from_dict()`); wired into swing
workflow and accumulation screen; `FlowConfirmationEvidence` group scoring
unchanged; zero references to `InstitutionalAccumulationEvidence` in
`AssessSignalEvidenceUseCase`, `DecisionPolicy`, or domain entity files.

**Post-closure fixes applied:**
1. CNFB metadata key mismatch (High): `_ia_evidence_fingerprint()` now reads from
   correct nested keys; `ia_cnfb_divergence_20d` is the raw 20d score.
2. Conviction renormalization (Medium): conviction now renormalizes over
   available-component weights so it reflects signal strength, not availability.
3. EvidenceStatus registry explicitly deferred to Phase G/I.

2457 tests pass after fixes.

**Carry-forward:** Open items listed in the Open Items Index above.

**Deferred to Phase I:** Empirical readiness summary, OOS attribution, promotion
from DIAGNOSTIC. **Deferred infrastructure:** Domestic bandar cost basis / VWAP
reclaim as Trigger evidence; BandarDetectorSnapshot historical caching;
EvidenceStatus registry / cap enforcement object (safe for Phase E because no
Phase E path feeds `InstitutionalAccumulationEvidence` into scoring).

---

## Phase F Tracker: Minimal Ticker Profile Diagnostics

**Status:** Done (2026-07-06)

**Implemented contract:** Deterministic `TickerProfileSnapshot` with dimension
scores, market tier, soft profile exposures, profile confidence, evidence
status, and backward-compatible serialization; `config/ticker_profile.yaml`
with validated index scores and exposure weights; `TickerProfileClassifier`
using local candles, broker flows/summaries, market cap, sector metadata, and
construction-time universe reverse index; conservative sparse-history fallback
(`primary_profile=unclassified`, `market_tier=unknown`, confidence 0.30,
FI 0.0, DB 0.5, RS 0.5); `tp_*` replay fingerprint fields persisted; DIAGNOSTIC-only;
no impact on `AssessSignalEvidenceUseCase`, `DecisionPolicy`, `SignalEngine`,
`TradeSetup`, or sizing.

**Carry-forward notes:** Profile snapshots remain diagnostic until a later phase
explicitly promotes or routes them. `ticker_profiles` SQLite table not
introduced; snapshots replayed through saved observation fingerprints.
Per-profile group weights, profile-driven max-decision overrides,
epoch-keyed SQLite table, and per-horizon profile tunables deferred to Phase I.

---

## Phase G Tracker: Simplified Alpha/Trigger Split

**Status:** Done (2026-07-06)

**Implemented contract:**
- Four canonical Alpha/Trigger group slots configured: `setup_quality`,
  `institutional_flow`, `market_context`, `company_quality_context`. Runtime
  producers populate `setup_quality` and `institutional_flow`; `market_context`
  has Phase H sector-context as a diagnostic producer and `company_quality_context`
  has a diagnostic producer (`CompanyQualityContextEvidenceBuilder`, added
  2026-07-07). Both context slots remain DIAGNOSTIC with zero scoring authority
  (`effective_weight` = 0.0); promotion pending Phase I OOS proof.
- `AlphaTriggerScore` domain value object: alpha/trigger/final exact scores,
  horizon, route contributions, coverage, authority coverage, conviction,
  flow-trigger gate state, reasons, unavailable reasons.
- `AlphaTriggerGroupContribution` serialization for per-group route metadata.
- `EvidenceRegistration` and `EvidenceAuthorityStatus` (`DIAGNOSTIC`,
  `LOW_WEIGHT`, `PRODUCTION`) with deterministic status caps.
- `SignalAssessment.score` remains `int`; optional exact fields
  `raw_exact_score` and `alpha_trigger_score` added.
- `AlphaTriggerAggregator` application service: normalizes Alpha and Trigger
  without neutral-filling missing groups into denominators; emits
  `authority_coverage` separately from `coverage`; applies DIAGNOSTIC/LOW_WEIGHT/
  PRODUCTION authority caps; enforces flow Trigger contribution only when
  `SetupPhaseState.BREAKOUT_CONFIRMATION` and confirmed `FlowConfirmationEvidence`
  are present.
- Alpha/Trigger exact scores, horizon, route metadata, and gating reasons
  persisted in accumulation candidate observation fingerprints; emitted through
  `SignalAssessment.to_dict()` and swing workflow verdict JSON.
- Diagnostic volatility context added to swing workflow output: ATR, ATR%,
  volatility bucket, ATR stop/target hints, size multiplier hint (all placeholders,
  not calibrated).
- 2515 passed; 3 pre-existing failures in
  `tests/adapters/cli/test_fetch_market_commands.py` unrelated to Phase G.

**Verification:** No second factor tree; no TradeSetup stop/target/sizing
authority change; no RiskEngine hard-gate change; no CLI policy logic; strategy
evidence not passed into aggregator; focused tests for projection formulas,
missing groups, coverage semantics, canonical unavailable groups,
flow-trigger blocking, and breakout-confirmed unlocking.

**Carry-forward:** Open items listed in the Open Items Index above.

---

## Phase H Tracker: Sector Context

**Status:** Done (2026-07-06)

**Implemented contract:**
- Frozen `SectorContextEvidence` domain value object: `sector`, `peer_count`,
  `peer_tickers`, `sector_20d_return`, `sector_vs_ihsg_20d`, `sector_breadth`,
  `ticker_vs_sector_rs`, `sector_regime` (BULLISH/NEUTRAL/BEARISH/UNKNOWN),
  `coverage_score`, `evidence_status` (always DIAGNOSTIC), `reasons`,
  `unavailable_reasons`; bounds validation; stable `to_dict`/`from_dict`.
- `SectorContextEvidenceBuilder` application service: `from_yaml()` factory;
  builds `sector_group → tickers` reverse index from non-index universe groups
  in `universes.yaml` at construction; `peers_for_ticker()` helper; pure
  helpers `_compute_return`, `_coverage`, `_classify_regime`; never fetches,
  never raises.
- `config/sector_context.yaml` with min/max peer counts, lookback sessions,
  min valid sessions per peer, and sector regime thresholds.
- Eight `sc_*` fingerprint fields in `SignalObservationFingerprint` (all
  `None`-defaulted; `data.get()` in `from_dict()`).
- `_sc_fingerprint()` helper in `accumulation_screen_use_case.py`; spread into
  `_sub_signal_fingerprint()`; `sector_context_evidence` field and build block
  in `swing_analysis_workflow_use_case.py`; wired into `SwingEvidence.to_dict()`.
- Sector context passed into `AssessSignalEvidenceUseCase` as the diagnostic
  Alpha/Trigger `market_context` group input when available.
- Accumulation-screen observation persistence builds sector context and persists
  non-empty `sc_*` fields when local peer/sector data is available.
- Two attribution buckets (`sc_sector`, `sc_sector_regime`) in forward label
  summarizer.
- 2564 tests pass.

**Carry-forward:** Open items listed in the Open Items Index above.

---

## Phase I Tracker: Full Walk-Forward Calibration And Expanded Tunables

**Status:** In Progress - Readiness/Audit Pass (2026-07-06)

**Goal:** Validate that the Phase B-H evidence and attribution surface is ready
for walk-forward calibration, then start empirical calibration on one target:
`foreign_institutional_accumulation_large_cap_SWING_10D`.

Phase I begins with audit/readiness, not tuning patches. New diagnostic evidence
from Phases D-H remains DIAGNOSTIC until saved-label attribution and
out-of-sample proof justify manual promotion through validator-bounded config.

### Non-Goals

- No automatic promotion from DIAGNOSTIC to LOW_WEIGHT or PRODUCTION.
- No tuning patches before readiness gates and persisted attribution are
  verified.
- No `TACTICAL_3D` or `ACCUM_20D` tuning surfaces before `SWING_10D` clears
  patch eligibility.
- No TradeSetup sizing authority change.
- No RiskEngine hard-gate change.
- No CLI policy logic.

### Readiness/Audit Checklist

- [x] Verify `SwingTuningPatchValidator` sample/OOS gates match canonical Phase
      I docs.
      - Updated patch validation to require `PATCH_ELIGIBLE`, 60 IS trades,
        30 OOS trades, OOS profit factor >= 1.15, OOS average return >= 0,
        drawdown regression <= 0, required regime/coverage/conviction
        attribution, and no hidden single-regime dependency unless explicitly
        scoped.
      - Diagnostic-ready findings remain report-only and cannot validate a
        config patch.
- [x] Verify validator bounds cover canonical tunable paths before any patch can
      target them.
      - Added bounds for market context thresholds/effects, decision-policy
        regime thresholds and size multipliers, swing target stop/target paths,
        swing backtest score buckets, smart-money setup gates, setup-phase
        thresholds, and RS policy numeric thresholds.
      - Container, categorical, and boolean paths are explicitly non-tunable.
      - Audit result: 54 bounded current target paths, 14 explicit non-tunable
        paths, 0 missing.
- [x] Confirm persisted observations include Phase B-H fingerprints:
      setup phase/history, strategy evidence, institutional accumulation,
      ticker profile, Alpha/Trigger, and sector context.
      - Historical local sample: 45 rows from 2026-07-04 have zero populated
        setup/IA/ticker-profile/AlphaTrigger/sector fingerprint fields.
      - Fresh `lq45` screen on 2026-07-06 generated 135 rows; all 135 have
        setup phase, institutional accumulation, ticker profile, Alpha/Trigger,
        and sector-context fingerprint fields populated.
      - Company-quality (`cq_*`) fingerprint fields (valuation/analyst/insider/
        seasonality axis scores, aggregate, coverage, present-axis count) added
        2026-07-07 as a new attribution dimension, wired end-to-end so forward-
        label attribution can use them: candidate observation payload
        (`_cq_fingerprint`) → `SignalObservationFingerprint` cq_* fields
        (`to_dict`/`from_dict`, backward-compatible `data.get()`) →
        `SummarizeSignalForwardLabelsUseCase` cq_* buckets. Persisted/parsed with
        None when the underlying enrichment is unavailable; missing fields bucket
        to UNKNOWN, never crash.
- [x] Confirm forward-label attribution groups include `sc_sector`,
      `sc_sector_regime`, `cq_*` company-quality axes, Alpha/Trigger buckets,
      coverage/conviction buckets, setup phase, and market regime.
      - Attribution cleanup added persisted-field-only groups for IA track
        coverage/conviction, ticker profile label/market-cap/tier/coverage,
        and retained existing Alpha/Trigger bucket names
        (`alpha_bucket`, `trigger_bucket`, `alpha_trigger_final_bucket`,
        `alpha_trigger_horizon`) to avoid duplicate aliases.
      - `ia_primary_track` intentionally skipped because it is not persisted in
        `SignalObservationFingerprint`; no evidence is recomputed.
- [x] Run attribution summaries for the required groups from persisted labels,
      or document the missing-label/data blocker explicitly.
      - `analyze signal-labels 2026-07-04 --horizon SWING_10D --format json
        --db data/db/data.db` returned `label_count: 0`; no persisted labels
        are available for attribution yet.
      - Re-run for 2026-07-06 after fresh observations also returned
        `label_count: 0`. Candle data currently ends on 2026-07-06, so
        SWING_10D forward labels must wait for future candles.
- [x] Confirm all Phase D-H diagnostic evidence registrations remain
      DIAGNOSTIC until OOS proof exists.
      - `market_context` and `company_quality_context` Alpha/Trigger
        registrations remain DIAGNOSTIC; no Phase D-H diagnostic evidence was
        promoted.
      - Clarification (2026-07-07): `company_quality_context` now has a
        DIAGNOSTIC producer (valuation/analyst/insider/capped-seasonality). The
        producer was added, but its `EvidenceRegistration` stays DIAGNOSTIC and
        `effective_weight` resolves to 0.0 — no scoring authority changed. A test
        asserts `final_exact_score` is identical with the slot filled vs. empty.

### First Calibration Target

- [x] Scope empirical calibration to
      `foreign_institutional_accumulation_large_cap_SWING_10D`.
- [ ] Filter target candidates by horizon `SWING_10D`, ticker profile
      foreign-institutional/large-cap path, setup family accumulation-style, and
      available forward labels.
      - Current state (2026-07-07): observation filter resolves — 120 rows
        matching `foreign_institutional` / `large` / `SWING_10D`; all 135 lq45
        observations have populated `tp_market_cap_bucket` (large=123, mid=12).
        Blocked on SWING_10D forward labels.
- [ ] Produce readiness summary: sample count, OOS count, success/failure
      balance, unavailable label count, and attribution bucket coverage.
      - Current state (2026-07-07): 135 observations, 0 forward labels, 0 future
        candle sessions after 2026-07-07; not patch-eligible. Blocked until
        enough future sessions accumulate for SWING_10D labels.
- [ ] Only after readiness passes: propose validator-bounded tuning patches for
      review; no auto-apply.

### Observation Automation

- [x] Add EOD cron entries for deterministic swing observation capture:
      `saham fetch market --universe lq45` at 18:30 WIB and
      `saham screen accum --universe lq45 --multi --format json` at 19:15 WIB.
- [x] Add idempotent batch forward-label generation:
      `saham analyze signal-labels DATE --horizon SWING_10D --generate-all`.
      Existing single-ticker `--generate --ticker` behavior is preserved.
- [x] Add eligible-date label generation for cron:
      `saham analyze signal-labels --eligible-dates --horizon SWING_10D
      --generate-all`; dates without enough forward candles are skipped
      deterministically.
- [x] Add nightly label cron at 19:45 WIB using eligible-date mode and logging
      to `logs/swing-labels.log`.
- [x] Update cron cleanup to remove old loose `saham screen` and
      `saham analyze` lines in addition to fetch/learn/trade lines.
- [x] Dedicated readiness report command implemented:
      `saham analyze signal-readiness --target
      foreign_institutional_accumulation_large_cap_SWING_10D` reports
      observation dates, latest per-ticker observation count, raw observation
      count, target-filter count, raw target rows, label counts, labeled target
      count, IS/OOS split, patch eligibility, and blockers without generating
      patches.
      - Local report after implementation: observation dates
        `2026-07-04`, `2026-07-06`, `2026-07-07`; latest per-ticker
        observation count 45; raw latest observation rows 135; latest-per-ticker
        target observations 40; raw target rows remain 120; label count 0;
        labeled target count 0; patch-eligible false because SWING_10D labels
        are not available yet.
- [ ] Label readiness remains blocked until enough future sessions exist for
      `SWING_10D`; no tuning patches or evidence promotion before
      patch-eligible OOS proof.

### Verification

- [x] `python -m py_compile` for changed application/domain/config files.
- [x] Focused pytest for validator, target-path bounds audit, attribution
      summary, and calibration-readiness guardrails: 99 passed.
- [x] Ticker-profile market-cap bucket readiness regression:
      classifier/domain/accumulation-screen/forward-label focused tests:
      101 passed.
- [x] Full pytest: 2572 passed after `tp_market_cap_bucket` readiness fix.
- [x] `git diff --check`.
