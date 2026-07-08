# Signal Engine Refactor Tracker

_Design rationale: `docs/signal_refactor.md`_
_Phase plan: `docs/signal_refactor_phases.md`_
_Current implementation target: Phase I readiness audit_
_Updated: 2026-07-07 — PIT replay cache audit expanded beyond fundamentals/shareholding; stock metadata, company profile, seasonality, earnings, and SignalEngine replay enrichment paths now guarded/converted where replay-relevant._

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
| A2 | Full RegimeDetectionEvidence And Replay | Done | Implemented 2026-07-05; all checklist items complete, 2347 tests pass at phase closure. |
| B | Minimal Forward Labels And Observation Fingerprints | Done | Implemented and verified; saved labels and fingerprint attribution are operational. |
| C | SetupPhaseState And Continuous Setup/Trigger Scoring | Done | Closed 2026-07-06; diagnostic setup phase, replay history, and data-quality volume trigger implemented. |
| D | Strategy Evidence Harness | Done (2026-07-06) | Diagnostic-only strategy evidence harness. 2424 tests pass at phase closure. |
| E | Institutional Accumulation Evidence | Done (2026-07-06) | Two-track institutional flow evidence, diagnostic-only. 2457 tests pass at phase closure. |
| F | Minimal Ticker Profile Diagnostics | Done (2026-07-06) | Deterministic ticker behavior classifier, diagnostic-only. 2489 tests pass at phase closure. |
| G | Simplified Alpha/Trigger Split | Done (2026-07-06; producers completed 2026-07-07) | Four canonical Alpha/Trigger slots configured. Both `market_context` (Phase H sector-context) and `company_quality_context` now have DIAGNOSTIC producers with zero scoring authority (`effective_weight` resolves to 0.0). `company_quality_context` producer: valuation/analyst/insider/capped-seasonality axes, `alpha_fraction=1.00`. |
| H | Sector Context | Done (2026-07-06) | Local-universe sector-relative return, breadth, ticker-vs-sector RS; DIAGNOSTIC-only; 2564 tests pass at phase closure. |
| I | Full Walk-Forward Calibration And Expanded Tunables | In Progress (readiness audit) | Audit-first opening; no tuning patches or evidence promotion until OOS readiness is proven. |

---

## Open Items Index

Reorganised into four working lists so "unfinished refactor" is not confused
with "future improvement". Nothing has been deleted; only reclassified.

---

## Active Blockers

These are the only items that block Phase I completion. Everything else below
is either safe to ignore for now or explicitly deferred.

> **Current blocker: 0 matching target labels available locally as of 2026-07-07.**
> 5,760 forward labels have been generated via historical backfill (Jan 1 to Jun 15, 2026).
> However, because historically derived fundamentals rows (60-day conservative lag)
> do not include `market_cap_idr`, `piotroski_f_score`, or PE/PBV, all backfilled
> observations still resolve to `tp_market_cap_bucket: UNKNOWN`.
> Consequently, 0 labeled target rows match the "large" market-cap bucket requirement.
>
> **Diagnostic target `foreign_institutional_accumulation_SWING_10D` added (2026-07-07).**
> Bug fix also applied (2026-07-07): `_fingerprint_matches_target()` previously returned `True`
> when `setup_family` was missing, making setup-specific targets act as wildcards. Fixed to
> return `False` — a missing setup_family never satisfies a setup-specific target.
>
> After the fix, running `saham analyze signal-readiness --target
> foreign_institutional_accumulation_SWING_10D` yields `labeled_target_count: 0` and
> `diagnostic_ready: false` — because all 5,760 backfilled labels have `setup_family=NONE`
> (backfilled fingerprints do not capture setup phase). The earlier incorrect reading of
> 5,672 matched labels was produced by the wildcard bug, not by genuine accumulation evidence.
>
> **Attribution highlights (all 5,760 backfilled labels):**
> - `tp_market_cap_bucket`: 100% UNKNOWN (derived historical fundamentals lack `market_cap_idr`)
> - `ticker_profile_label`: 98.5% `foreign_institutional`, 1.5% `retail_speculative`
> - `setup_family`: 100% NONE (backfilled fingerprints do not capture setup phase)
> - `alpha_bucket` / `trigger_bucket` / `alpha_trigger_final_bucket`: 100% NONE
> - `coverage_bucket` / `conviction_bucket`: 100% NONE
> - `ia_foreign_track_coverage`: 94.8% coverage=1.0, 5.2% coverage=0.75
> - `sc_sector_regime`: NEUTRAL 53.6%, BULLISH 24.3%, BEARISH 17.6%, UNKNOWN 4.4%
>
> The nightly EOD cron automatically accumulates live observations with full fundamentals
> going forward, which will naturally yield matching targets for both targets.

- [ ] **SWING_10D forward labels generated, but target matching is blocked.**
      5,760 labels generated from historical dates, but 0 match the target filter.
      Live observations captured by the EOD cron will accumulate matching targets
      as future candles deliver labels.
- [ ] **Labeled target attribution blocked.** 120 observation rows matching
      `foreign_institutional` / `large` / `SWING_10D` are ready, but labeled
      target count remains 0. Unblocks automatically as new live labels accumulate.
- [ ] **Patch eligibility blocked.** `saham analyze signal-readiness` is implemented
      and reports 5,760 total labels, 0 labeled targets, and patch-eligible: false.
      Unblocks automatically as live labels match the target filter.
- [ ] **Tuning patches blocked until readiness passes.** No tuning patches or config
      changes may be proposed until `patch_eligible: true` is reported.
- [ ] **Evidence promotion blocked until OOS proof exists.** All Phase D–H
      diagnostic evidence (strategy, institutional accumulation, sector context,
      company quality, ticker profile) remains DIAGNOSTIC, zero scoring authority,
      until walk-forward OOS attribution justifies a manual promotion.

---

## Safe While Waiting For Labels

Work that can proceed without touching signal authority, scoring, or tuning.

- [x] Diagnostic readiness target `foreign_institutional_accumulation_SWING_10D` added (2026-07-07):
      - `SignalReadinessTarget.parse()` extended to accept targets without `_cap` suffix;
        `is_diagnostic=True`, `market_cap_bucket=None` for this form.
      - `_fingerprint_matches_target()` skips market-cap check when `market_cap_bucket is None`.
      - Bug fix: `_fingerprint_matches_target()` previously returned `True` for missing
        `setup_family`, making it a wildcard. Now returns `False` — a missing setup_family
        never matches any setup-specific target (canonical or diagnostic).
      - `patch_eligible` is always `False` for diagnostic targets regardless of label counts.
      - Diagnostic note added to `notes` in `SignalReadinessReport`.
      - `is_diagnostic_target` field added to `to_dict()` output.
      - CLI display shows `cap=any (diagnostic — no cap filter)` and a `[DIAGNOSTIC]` header line.
      - 12 new focused tests (3 regression tests for setup_family wildcard); 2722 total pass.
      - Canonical target `foreign_institutional_accumulation_large_cap_SWING_10D` unchanged.
- [x] CLI adapter regression tests for strategy evidence display.
      _(Done 2026-07-07 — see Phase D open items below.)_
- [x] Deterministic historical signal-observation backfill implemented:
      `saham analyze signal-backfill-observations --universe lq45 --start
      YYYY-MM-DD --end YYYY-MM-DD --horizon SWING_10D --generate-labels
      --format table|json`.
      - Uses the application-layer accumulation screen pipeline with
        `AccumulationScreenRequest.as_of_date`.
      - Backfill/live observation parity is enforced through the shared
        application-layer `BuildSignalObservationScreenRequest` builder. Live
        observation capture remains the canonical policy; historical backfill
        replays the same policy with only `tickers`, `window_days`, and
        `as_of_date` varied per historical run.
      - Persists historical `candidate_observations` before optional label
        generation.
      - Optional label generation uses `GenerateSignalForwardLabelsUseCase` only
        for saved observation dates with enough future candles.
      - Reruns are safe; raw timestamped observation rows may append, and
        readiness/reporting paths continue to collapse to latest per ticker for
        ticker/day label readiness.
      - Point-in-time enrichment status (updated 2026-07-07):
        analyst consensus, forward estimates, and ticker notation use
        `date(fetched_date) <= date(as_of_date)` queries and were already
        multi-row PIT tables. SignalEngine self-fetch replay now passes
        `as_of_date` into analyst, forward-estimates, and seasonality providers;
        live calls still pass `None`, preserving live fetch behavior.
        Fundamentals (`company_fundamentals`) and shareholding
        (`shareholding_composition`) were converted earlier to multi-row
        `UNIQUE(ticker, fetched_date)` PIT caches. A new
        `saham fetch enrichment-history --universe lq45` command stores
        periodic snapshots with today's fetched_date.
        Additional replay-cache audit results:

        | Cache/table | Previous/current key | Used by replay? | Action | Reason |
        |---|---|---:|---|---|
        | `stock_meta` | was `ticker PRIMARY KEY`; now multi-row by `ticker`, `fetched_at` | Yes, sector/universe metadata can feed fingerprints and sector context | Converted | Historical reads use latest row with `fetched_at <= as_of_date`; future-only rows return `None`. |
        | `company_profile_cache` | was `ticker PRIMARY KEY`; now multi-row by `ticker`, `fetched_date` | Potentially, listing/profile fields can feed ticker-profile/readiness attribution | Converted | Historical reads use latest row with `fetched_date <= as_of_date`; future-only rows return `None`. |
        | `seasonality_cache` | was keyed by `ticker/year/month`; now snapshot rows include fetch metadata | Yes, seasonality can feed signal/company-quality diagnostics | Guarded PIT snapshot reads | Historical reads are cache-only and require a cached aggregate fetched on/before replay date; no prior snapshot returns unavailable. |
        | `earnings_cache` | was `PRIMARY KEY(ticker, year, quarter)`; now `UNIQUE(ticker, year, quarter, fetched_date)` | Yes, earnings history can feed quality diagnostics | Converted | Historical reads select the latest stored snapshot per quarter with `fetched_date <= as_of_date`; no reliable announcement date exists in cache. |
        | `valuation_metrics_cache` | `ticker PRIMARY KEY` | No current signal/risk/backfill/fingerprint/tuning usage | Left display-only | Forward valuation used by signals comes from PIT `forward_estimates_cache`; latest valuation metrics remain dashboard/fetch display data. |

        Signal factor coverage reporting now includes `sector_metadata`,
        `company_profile`, and `earnings_history`. Enrichment PIT snapshot
        coverage now includes `stock_meta`, `company_profile_cache`,
        `seasonality_cache`, and `earnings_cache` in addition to the earlier PIT
        enrichment tables. Display-only latest valuation metrics are not counted
        as replay coverage.
        PROVIDER LIMITATION: Stockbit returns current values only for several
        enrichment endpoints; no historical vendor API exists. Historical
        observations before the first locally stored snapshot will continue to
        return UNKNOWN/unavailable for those fields. Run `enrichment-history`
        regularly going forward to build a PIT history.
      - No SignalEngine authority, DecisionPolicy, RiskEngine, tuning patch, or
        diagnostic evidence promotion change.
- [x] CLI adapter rendering regression tests for setup phase / evidence output.
      _(Fulfilled by Phase D: test_swing_display_strategy.py covers setup_phase, evidence_route, rule fields. 64 display tests pass.)_
- [ ] Optional docs / README accuracy cleanup.
- [ ] Optional display-only polish that does not change scoring or decisions
      (e.g. formatting, label wording in CLI panels).

---

## Blocked Until OOS Proof

These items require walk-forward OOS attribution before they are actionable.
Do not implement until `patch_eligible: true` and explicit OOS evidence exist.

- [ ] Promote `market_context` Alpha/Trigger slot from DIAGNOSTIC, zero scoring
      authority, to LOW_WEIGHT or PRODUCTION. Blocked until sector-context
      evidence proves discriminative in OOS attribution.
- [ ] Promote `company_quality_context` Alpha/Trigger slot from DIAGNOSTIC, zero
      scoring authority, to LOW_WEIGHT or PRODUCTION. Blocked until
      company-quality evidence proves discriminative in OOS attribution.
- [ ] Promote any Phase D/E/F/H/company-quality diagnostic evidence into
      production scoring. All remain DIAGNOSTIC until labels/OOS proof exist.
- [ ] ATR hint thresholds and size multipliers calibration. Currently
      placeholders; not Phase-I-calibrated production tunables.
- [ ] `company_quality_context` seasonality cap and per-axis aggregation weights
      calibration. Currently config-driven placeholders, same status as ATR-hint
      placeholders; not Phase-I-calibrated.
- [ ] Phase I walk-forward calibration, promotion workflow, and empirical
      readiness gates. Out of scope until labels and OOS attribution are ready.
- [ ] Propose validator-bounded tuning patches. Blocked until readiness passes
      (patch-eligible: false as of 2026-07-07).

---

## Future Enhancement Backlog

Useful ideas that are non-blocking and have no current data source or are
explicitly deferred. Do not treat these as signals that the refactor is
unfinished.

- [ ] Enforce pullback requirements: trend/context support plus support reclaim
      or pivot confirmation. _(Phase C carry-forward. Future enhancement — no
      current calibration target.)_
- [ ] Enforce mean-reversion requirements: support/reversal evidence and explicit
      risk controls. _(Phase C carry-forward. Future enhancement.)_
- [ ] Dedicated support reclaim trigger routing beyond the current positive
      close / VWAP reclaim / volume expansion path. _(Phase C carry-forward.
      Future enhancement.)_
- [ ] Dedicated squeeze release trigger routing. _(Phase C carry-forward.
      Future enhancement.)_
- [ ] Config-driven mapping from strategy package/rule to setup family + phase
      evidence (multi-match coexistence and conflict reporting). _(Phase D
      carry-forward. Future enhancement — not required for Phase I.)_
- [ ] Empirical readiness summary from existing backtests (min sample size,
      SWING_10D grouping), if separate from the implemented `signal-readiness`
      command. _(Phase D carry-forward. May already be covered by
      `saham analyze signal-readiness`; evaluate before implementing.)_
- [ ] `company_quality_context` event alpha: MSCI/FTSE inclusion, dividend-chase
      windows, market calendar. Explicitly deferred — no event-window data
      source or computation exists in the codebase. _(Phase G carry-forward.)_
- [ ] `earnings_trend` axis producer. Deferred — recorded as an unavailable
      axis, excluded from coverage. _(Phase G carry-forward.)_

---

## Completed Since Tracker Compression

Short list of recently closed items for orientation. Full phase contracts are
in the phase tracker sections below.

- [x] Phase E IA persistence test: `ia_*`, `sc_*`, and `cq_*` fields verified
      in saved observation payload. _(2026-07-07)_
- [x] Phase E Institutional Accumulation display panel: `INSTITUTIONAL ACCUMULATION`
      panel in `analyze_swing_display.py`, gated by `--with-flow-detail`.
      _(2026-07-07)_
- [x] Broker classification moved to `config/institutional_accumulation.yaml`.
      Tunable without code edits. _(2026-07-07)_
- [x] Phase G Alpha/Trigger detail display: `ALPHA/TRIGGER DETAIL` panel, per-group
      score, weight, DIAGNOSTIC groups labelled "— no weight". _(2026-07-07)_
- [x] Phase H Sector Context display: `SECTOR CONTEXT` panel, signed-pct metrics
      table, "DIAGNOSTIC — no scoring impact" footer. _(2026-07-07)_
- [x] Phase G `company_quality_context` DIAGNOSTIC producer: valuation/analyst/
      insider/capped-seasonality axes, `alpha_fraction=1.00`, `effective_weight`
      resolves to 0.0, zero scoring authority. _(2026-07-07)_
- [x] Phase D CLI adapter regression tests for strategy evidence display:
      29 tests, all 4 outcomes, DIAGNOSTIC disclaimer, coexistence with backtest
      stats. _(2026-07-07)_
- [x] PIT enrichment schema fix: `company_fundamentals` and `shareholding_composition`
      converted from single-row (`ticker PRIMARY KEY`) to multi-row
      `UNIQUE(ticker, fetched_date)` schema (migrations squashed to single baseline
      migration 0). `_read_cache()` in both providers uses
      `date(fetched_date) <= date(as_of_date)` PIT query. Shareholding uses
      `COALESCE(report_date, fetched_date)` as boundary.
      `saham fetch market --universe lq45` and/or
      `saham fetch enrichment-history --universe lq45` commands store periodic
      snapshots to build a PIT history.
      Derived historical fundamentals (60-day conservative lag) are produced by the
      Stockbit fundamentals fetch path (`StockbitFundamentalsProvider._fetch()` →
      `_parse_historical_rows()` → `_write_historical_rows()`). Derived rows
      populate only `net_profit_margin` and `revenue_yoy_growth`; `market_cap_idr`,
      `piotroski_f_score`, PE/PBV, ROE, and dividend yield remain NULL. Derived rows
      use `INSERT OR IGNORE` so live snapshots are never overwritten. A freshness
      guard skips rows whose estimated availability date (`period_end + 60 days`) is
      within the live cache TTL window to prevent suppressing live API fetches.
      Governs data ingestion only; does not promote company-quality evidence or
      change SignalEngine scoring. See ADR-038.
      _(2026-07-07; squash 2026-07-08)_

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
- Phase I patch generation remains blocked until readiness reports
  `patch_eligible: true`. Phase I is the active target; the audit pass is
  underway but no tuning patches or config changes may be proposed until the
  readiness gate passes.
- Network-dependent tests remain out of scope for refactor phases.
- `SWING_10D` remains the first calibrated ticker-signal horizon.

---

## Known Technical Debt (Explicitly Tracked)

### TD-1: Double Regime Effect — regime_conditioning + decision_policy both active

**Status:** Resolved (double-regime effect fixed). Cleanup deferred pending live labels.

**What was the problem:** `_condition_group_scores()` (Phase 5 legacy) mutated group scores before
renormalization, causing `assessment.score` to reflect regime AND `decision_policy` to also gate
ENTER — a compound double effect.

**Current state (resolved):** Canonical `assessment.score` is now regime-neutral. Stage 2 calls
`_condition_group_scores()` but its output is stored only as `legacy_conditioned_score` (diagnostic).
`decision_policy` is the sole canonical regime gate. The contract "regime controls constraints, not
score" is now satisfied.

**What remains (deferred, not a blocker):**
- `_condition_group_scores()` still runs (output diagnostic only).
- `regime_conditioning.*` config block still exists, marked ARCHIVED DIAGNOSTIC.
- `legacy_conditioned_score` still appears in output JSON (no contract break if removed later).
- Removal is a clean-break change; defer until after live labels or explicit decision.

**Resolution path:** After live labels confirm decision_policy is sufficient, remove
`_condition_group_scores()`, `regime_conditioning` config, and `legacy_conditioned_score`.
Requires test expectation updates and JSON output contract bump.

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
- [x] Historical observation backfill command implemented for Phase I readiness:
      `saham analyze signal-backfill-observations --universe lq45 --start
      YYYY-MM-DD --end YYYY-MM-DD --horizon SWING_10D --generate-labels`.
      Backfill creates saved historical observations first, with the current
      Phase B-H fingerprint surface from the live accumulation screen path.
      Shared request-builder parity now prevents live/backfill request-policy
      drift; backfill only overrides `tickers`, `window_days`, and `as_of_date`
      for historical replay. Labels are generated second and only through the
      existing forward-label use case when enough future candles exist. The
      command does not generate tuning patches and does not promote diagnostic
      evidence.
      - Enrichment replay status: analyst consensus, forward estimates, and
        ticker notation use cached point-in-time reads (`fetched_date <=
        as_of_date`) and return unavailable if only future snapshots exist.
        Fundamentals and shareholding were already verified as point-in-time.
      - Backfill smoke test and readiness audit run (2026-07-07):
        - Backfilled LQ45 universe from 2026-01-01 to 2026-06-15 (102 dates).
        - Saved 13,770 historical observations and generated 4,590 SWING_10D labels.
        - Verified that point-in-time lookups functioned correctly; because the local
          cache contains derived historical fundamentals (60-day lag) but includes no
          `market_cap_idr`, `piotroski_f_score`, or PE/PBV; all historical observations
          resolved to `tp_market_cap_bucket: UNKNOWN`.
        - Labeled target count remains 0; patch eligibility remains false (not eligible).
- [x] Diagnostic readiness target `foreign_institutional_accumulation_SWING_10D` added (2026-07-07):
      - Same profile and setup-family filter as canonical target; no market-cap bucket filter.
      - `is_diagnostic_target: true` in JSON output; `patch_eligible` hardcoded `false`.
      - Diagnostic target readiness result after setup_family wildcard fix (2026-07-07):
        - `target_filter_count`: 0 (all backfilled obs have setup_family=NONE, correctly excluded)
        - `label_count`: 5,760; `labeled_target_count`: 0
        - `diagnostic_ready: false`; `patch_eligible: false`
        - Blockers: no rows matching target filter; no available labels match target filter
        - Prior incorrect reading (5,672 matched labels) was produced by the wildcard bug
      - Attribution summary for 5,760 backfilled labels:
        - `tp_market_cap_bucket`: 100% UNKNOWN (derived historical fundamentals lack `market_cap_idr`)
        - `ticker_profile_label`: 98.5% foreign_institutional, 1.5% retail_speculative
        - `setup_family`: 100% NONE (backfilled fingerprints do not capture setup phase)
        - `alpha/trigger/coverage/conviction` buckets: 100% NONE
        - `ia_foreign_track_coverage`: 94.8% full, 5.2% partial
        - `sc_sector_regime`: NEUTRAL 53.6%, BULLISH 24.3%, BEARISH 17.6%, UNKNOWN 4.4%
      - No tuning patches generated; no diagnostic evidence promoted.
      - Canonical `foreign_institutional_accumulation_large_cap_SWING_10D` is unchanged.
- [ ] Label readiness remains blocked until enough future sessions exist for
      live observations under `SWING_10D`; no tuning patches or evidence
      promotion before patch-eligible OOS proof.

### Evidence Authority Guard Coverage

All Phase D–H diagnostic evidence has zero scoring authority. Tests confirm this
at three layers — no new tests needed:

| Layer | Test file | What is asserted |
|---|---|---|
| Domain | `tests/domain/value_objects/test_alpha_trigger_score.py` | `EvidenceAuthorityStatus.DIAGNOSTIC.effective_weight(w) == 0.0` |
| Application | `tests/application/use_case/test_assess_signal_evidence_use_case.py` | `market.effective_weight == 0.0`, `cq.effective_weight == 0.0` |
| Application | `tests/application/services/test_alpha_trigger_aggregator.py` | `market.effective_weight == 0.0` |
| Display | `tests/adapters/cli/test_swing_display_alpha_sector.py` | DIAGNOSTIC groups labelled `— no weight` in output |
| Display | `tests/adapters/cli/test_swing_display_strategy.py` | Strategy evidence shows `DIAGNOSTIC` disclaimer |

Config source: `config/signal_engine.yaml` registers `market_context` and
`company_quality_context` as `status: DIAGNOSTIC`. `config/sector_context.yaml`
registers sector context as `evidence_status: DIAGNOSTIC`.

### PIT Schema Contract Coverage

All 9 replay-relevant enrichment tables are covered by offline deterministic tests:

| Table | Test file |
|---|---|
| `company_fundamentals` | `tests/infrastructure/browser/test_pit_enrichment.py` |
| `shareholding_composition` | `tests/infrastructure/browser/test_pit_enrichment.py` |
| `analyst_cache` | `tests/infrastructure/persistence/test_pit_schema_contracts.py` |
| `forward_estimates_cache` | `tests/infrastructure/persistence/test_pit_schema_contracts.py` |
| `ticker_notation_cache` | `tests/infrastructure/persistence/test_pit_schema_contracts.py` |
| `stock_meta` | `tests/infrastructure/persistence/test_pit_schema_contracts.py` |
| `company_profile_cache` | `tests/infrastructure/persistence/test_pit_schema_contracts.py` |
| `seasonality_cache` | `tests/infrastructure/persistence/test_pit_schema_contracts.py` |
| `earnings_cache` | `tests/infrastructure/persistence/test_pit_schema_contracts.py` |

Derived fundamentals constraints (60-day lag, INSERT OR IGNORE, freshness guard,
NULL fields) are covered by `tests/infrastructure/browser/test_historical_fundamentals_backfill.py`.
Coverage reporter is tested by `tests/infrastructure/persistence/test_sqlite_enrichment_pit_coverage.py`.

### Verification

- [x] `python -m py_compile` for changed application/domain/config files.
- [x] Focused pytest for validator, target-path bounds audit, attribution
      summary, and calibration-readiness guardrails: 99 passed.
- [x] Ticker-profile market-cap bucket readiness regression:
      classifier/domain/accumulation-screen/forward-label focused tests:
      101 passed.
- [x] Full pytest: 2572 passed after `tp_market_cap_bucket` readiness fix.
- [x] Diagnostic target focused pytest: 14 passed (12 new + 2 existing).
- [x] Full pytest: 2722 passed after diagnostic target + setup_family fix (2026-07-07).
- [x] Evidence authority guard coverage verified (2026-07-08) — see table above; no new tests needed.
- [x] PIT schema contract coverage verified (2026-07-08) — see table above.
- [x] `git diff --check`.
