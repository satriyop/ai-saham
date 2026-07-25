# ADR-048: Pre-Open Signal Evidence and Observation Identity

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted (decision locked; implementation in phases)
**Date:** 2026-07-25
**Depends on:** [ADR-026](ADR-026-risk-plus-signal-pipeline-composition.md), [ADR-041](ADR-041-canonical-signal-evidence-input-boundary.md), [ADR-047](ADR-047-scenario-adoption-seam-for-signal-risk-mce.md), [ADR-024](ADR-024-signal-engine-and-risk-engine-as-first-class-application-services.md), [ADR-033](ADR-033-workflow-composition-artifact-boundaries.md)
**Related:** [ADR-027](ADR-027-risk-signal-learning-loop.md), [ADR-030](ADR-030-accumulation-screener-evidence-split.md), [ADR-037](ADR-037-marketcontext-promotes-from-preview-only-to-canonical-signal-input.md), [ADR-046](ADR-046-cli-response-envelope.md)
**Current implementation:** Phased. Pre-open uses always-on regime + annotate risk via `ScreenAssessmentPipeline`; signal + TradeSetup + observation capture land per task. This ADR locks the target signal, observation, capture, and grade-evolution contract for subsequent work.

### Context

`screen pre-open` is an IDX call-auction workflow:

* **IEV-first ranking** surfaces volatile / high-interest names before the open.
* **NCP lock** (~08:57 WIB in the opening learning ops model) is when indicative
  equilibrium (IEP/IEV) and book state are usable as a decision snapshot.
* Intended hold is **short**: open through at most ~30 minutes, flat by **09:30 WIB**.

Today the screen builds an **entry plan** (ATR range, stop, gap, trend heuristics,
broker tags) and, after ADR-047 Phase 2, attaches **non-blocking** regime + default
gate risk. It does **not** run `SignalEngine` and does **not** compose `TradeSetup`.
Display labels such as PRIME/WATCH/SKIP are heuristics, not ADR-026 actions.

The opening learning loop (`learn snapshot` / `track` / `grade`) joins NCP snapshot
files to 09:00–09:30 tracks and reports plan/trend accuracy, including strata by
`opening_setup` (PRIME/WATCH/SKIP). That loop must not remain the long-term
authority model once a real signal exists.

Without an explicit contract, implementers will:

1. treat IEV as signal score,
2. treat PRIME as ENTER,
3. invent multi-day flow “confirmation” for a 30-minute trade,
4. recompute historical scores at grade time and poison learning cohorts, or
5. bypass `ScreenAssessmentPipeline` / TradeSetup with a parallel verdict path.

### Decision

#### 1. Role split (non-negotiable)

| Concern | Owner |
|---------|--------|
| Universe / heat discovery | **IEV** (and top-N / iev_min policy) — **not** signal |
| Decision clock / auction truth time | **NCP_LOCKED** `decision_at` |
| Evidence → score / strength / `EntryQuality` | **SignalEngine** via canonical evidence (ADR-041) |
| Gates / risk assessment | **RiskEngine** |
| Action / stance ENTER·WATCH·AVOID·BLOCKED_* | **TradeSetup** only (`AssessTradeSetupUseCase`, ADR-026) |
| Conditional entry plan (range/stop) | Pre-open plan services — **not** signal authority |
| Engine adoption | **`ScreenAssessmentPipeline`** only (ADR-047) |

No new action enums for pre-open. Reuse `SignalStrength` and `EntryQuality` on
`SignalAssessment`. Same words on `EntryQuality` and `SetupAction` remain
**different layers** (evidence quality vs composed action).

#### 2. Horizon

* Product horizon id: **`open_30m`** (session open → flat by 09:30 WIB unless a
  later ADR changes label policy).
* Multi-day swing setup families, multi-day foreign accumulation scores, analyst,
  and AI narrative are **not** production signal authority for this horizon.

#### 3. Canonical evidence groups

Evidence contract id (initial): **`pre_open_signal_evidence.v1`**.

| Group id | Role | Production rule |
|----------|------|-----------------|
| **`auction_ncp`** | NCP-locked auction quality | **Required** for production signal |
| **`open_viability`** | 30m trap / friction / chaos quality | **Optional** initially (see §4) |

**`auction_ncp` (illustrative field set for the contract; scoring math is later work):**

* `iep`, `iev`, `gap_pct_vs_prev_close`
* optional then required when multi-snapshot lands: `delta_iev` (path into lock)
* bid pressure / imbalance, spread or bid/offer depth at NCP
* provenance: snapshot id, `capture_phase=NCP_LOCKED`, `decision_at`

**`open_viability`:**

* gap vs ATR band / gap-out flag
* tick-friction feasibility for a 30m trade
* IEV intensity / unusual-heat flag
* optional light RSI extension do-no-harm flag
* provenance: candle window, config periods

**Explicitly non-authority (badge / enrichment only if shown at all):**

* multi-day broker BACKED score, multi-day Foreign VWAP floor, swing named setups,
  fundamentals, AI text.

Absence of `auction_ncp` ⇒ **hard guard**: do not call the signal use case (same
spirit as ADR-047 / no fabrication). No confirmation-only production score.

#### 4. Composition hierarchy (shape locked; weights and rendering provisional)

**Locked (the rule shape — this is the decision):**

```text
if auction_ncp MISSING or auction_strength < auction_min:
    → no production signal            # hard guard
else:
    auction_ncp is the PRIMARY driver; open_viability is do-no-harm (veto/penalty) ONLY
    if open_viability MISSING (allowed initially):
        score on auction alone
        coverage reflects the missing group
        cap strength at MODERATE (do not claim full two-group authority)
    decision constraints (gap-out, friction fail, ...) may force EntryQuality caps
        (WATCH / AVOID) regardless of a mid-range score
```

**Not locked (implementation choice; provisional, not decisions):**

* **Rendering — composite vs cascade.** v1 MAY render strength as an **ordinal gate
  cascade** (auction-primary, viability veto-only) rather than a weighted composite.
  This is deliberate: the existing pre-open heuristic is already a weightless cascade,
  and continuous weights cannot be justified until the forward-only corpus can fit
  them against the `clean_trade` / `open_30m` outcome. A **weighted composite is the
  v2 form**, valid once tuning is possible. Production config activates **exactly
  one** champion rendering (cascade **XOR** composite) — never dual-path scores.

  Illustrative v1 cascade (intent, not exclusive factor list):
  1. `auction_ncp` MISSING or below floor → no production signal;
  2. auction OK but viability veto (e.g. GAP_OUT / friction) → cap `EntryQuality`;
  3. else strength from auction bands (viability does not boost).
* **Weights — only relevant if a composite is used.** Provisional, **unvalidated**
  starting values, *not* locked decisions:

  | Knob | Provisional v1 default (unvalidated) |
  |------|--------------------------------------|
  | `auction_weight` | 0.65 |
  | `viability_weight` | 0.35 |
  | `auction_min` | 50 |
  | `viability_required` | false initially |
  | confirmation-only score | **forbidden** (this one IS locked) |

This ADR locks the **hierarchy and guards** (auction-primary, viability-veto,
hard guard, MISSING → MODERATE cap, no confirmation-only). It does **not** lock
the specific weights or the composite-vs-cascade rendering — those are
**CONFIG_MATERIAL** / implementation decisions, changeable via config or material
without an ADR revision.

Optional setup family string when needed: `open_call_participation`.

#### 5. Screen policy when signal exists

On `ScreenAssessmentPipeline` for pre-open:

| Flag | Value |
|------|--------|
| `signal_applicable` | **True** when NCP builder can supply `auction_ncp` |
| `trade_setup_applicable` | **True as soon as signal exists** |
| `risk_mode` | **annotate** (non-blocking for this product) |

Composition remains ADR-026 only. Risk may annotate HIGH_RISK without dropping
candidates; TradeSetup still records risk composition when both assessments exist.

Until signal ships, keep current Phase 2 policy: signal off, trade_setup off,
risk annotate always-on.

#### 6. Observation identity (DB, accum-like)

Observations are first-class **DB** rows (not long-term files-only authority),
aligned with accumulation observation intent:

* Record **all** evaluated loop names (pass and reject), not only UI survivors.
* `screen_result` is a **funnel** label (`pass`, `rejected_filter`,
  `rejected_auction_missing`, `rejected_signal`, `rejected_plan`, …) — **not**
  `SetupAction`.
* Primary identity:

  ```text
  ticker + trade_date + decision_at (NCP) + horizon (open_30m)
  + evidence_contract_version + material scoring/policy identity
  ```

* Session fields: `auction_phase` (production cohort: `NCP_LOCKED`),
  `source_status` / snapshot ref, data_as_of for consumed candles/broker rows.
* Payload includes plan fields, optional `SignalAssessment`, risk, and
  `TradeSetup` when composed; plus provenance bindings (ADR-041).

Labels for 09:30 outcomes join on `(ticker, trade_date, horizon, label_policy_version)`
to tracks; participation (open ∈ entry range) is part of label policy, not
silently assumed.

#### 7. Capture-time saved observations are the champion (not grade-time recompute)

**Champion path:** at NCP `decision_at`, **save the decision** to the observation store:

* universe inputs, canonical evidence + provenance, signal, risk, TradeSetup
  (when applicable), plan, contract versions → DB observation (and optional
  file journal).

**Post-open tracks** record prices only; they do **not** rewrite the decision.

**`learn grade` / label jobs** join decisions saved at capture to tracks.

**Forbidden as production default:** re-running current scorer over historical
raw snapshots and treating the result as the original decision.

**Allowed exception:** explicit **rebuild** / backfill that creates a **new cohort**
with new contract/scoring versions; do not silently overwrite production rows
(clean-break spirit).

Until signal exists, `learn grade` **remains as-is** (plan/IEP/trend and current
opening_setup strata). After signal: evolve metrics (plan + signal bands +
funnel); **do not retire** the grade capability; demote PRIME strata from champion
KPI.

#### 8. UI

When signal + TradeSetup are ready:

* **Replace** PRIME/WATCH/SKIP as the authoritative setup column with
  **signal score / quality** and **TradeSetup.action**.
* PRIME must not survive as a parallel production authority.

#### 9. Adoption and non-dual-path

* Pre-open signal/risk/trade_setup run only through **`ScreenAssessmentPipeline`**.
* `learn snapshot` may capture raw movers/plan for ops, but learning authority is
  the **saved DB observation** once that path exists (`research pre-open capture`).
* Opening snapshot use case remains raw-screen capture where already scoped;
  assessment capture is a named composition root when implemented (do not leave
  dual silent paths). Live `screen pre-open` does not write observations.

### Invariants / Consequences

* IEV is never the weighted signal score.
* No production signal without `auction_ncp`.
* No production action except via TradeSetup when `trade_setup_applicable`.
* Risk annotate does not drop pre-open candidates.
* Capture-time saved observations are reproducible learning truth; recompute is rebuild-only.
* Observations in DB include rejects; `screen_result` ≠ action.
* `learn grade` evolves; capability is not deleted without replacement.
* PRIME is transitional UI only until signal+TradeSetup replace it.

### Explicit non-goals (this ADR)

* No scoring-formula implementation or factor point tables in this document.
* No change to accum signal groups or accum observation schema beyond shared
  patterns by analogy.
* No requirement to implement DB observations or signal in the same PR as this
  ADR acceptance.
* No promotion of multi-day flow to pre-open signal authority.
* No automated trading / execution.

### Implementation sequencing (guidance, not a task checklist)

1. This ADR (decision locked).
2. Evidence types + `SignalInputsBuilder` for pre-open + pipeline policy flip.
3. DB observation write path + identity + capture at NCP `decision_at`.
4. UI cutover from PRIME to signal + TradeSetup.
5. `learn grade` schema evolution over saved observations + tracks.

### Agent one-liner

```text
Pre-open: IEV=universe, NCP=decision_at, horizon=open_30m. Canonical groups
auction_ncp (required) + open_viability (optional). Auction PRIMARY, viability
veto-only; hard guard if auction missing; no confirmation-only. v1 MAY render an
ordinal gate cascade; weighted composite + weights (0.65/0.35, auction_min 50) are
PROVISIONAL/unvalidated v2, not locked. SignalAssessment only for
score/quality; TradeSetup owns action as soon as signal exists; risk annotate.
Save observations at NCP decision_at (champion); no silent grade-time recompute.
Replace PRIME UI when ready; keep learn grade until signal then evolve. Adoption
only via ScreenAssessmentPipeline (ADR-047) + ADR-026 composition.
```
