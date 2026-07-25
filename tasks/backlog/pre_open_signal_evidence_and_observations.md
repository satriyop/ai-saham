# Task: Pre-Open Signal Evidence, TradeSetup, and DB Observations

Governing decision: [ADR-048](../../docs/adr/ADR-048-pre-open-signal-evidence-and-observation-identity.md)

Related: [ADR-047](../../docs/adr/ADR-047-scenario-adoption-seam-for-signal-risk-mce.md) (seam — already landed),
[ADR-041](../../docs/adr/ADR-041-canonical-signal-evidence-input-boundary.md),
[ADR-026](../../docs/adr/ADR-026-risk-plus-signal-pipeline-composition.md),
[ADR-027](../../docs/adr/ADR-027-risk-signal-learning-loop.md)

Prerequisite: ADR-047 Phases 0–2 complete (`ScreenAssessmentPipeline`; pre-open
Tier-1 regime + annotate risk; `signal_applicable=False` today).

## 1. Task Metadata

**Task Title:** Land pre-open canonical signal (NCP auction + open viability), compose TradeSetup, freeze DB observations at NCP, cut over UI and grade.

**Task Type:** Feature (phased) + persistence.

**Priority:** Medium.

## 2. Problem Statement

Pre-open discovers names via IEV and builds an auction entry plan, but has no
production signal evidence channel and no TradeSetup. Display labels (PRIME /
WATCH / SKIP) and `learn grade` strata on `opening_setup` act as a shadow
verdict language outside ADR-026. Opening learning lives in day files under
`data/opening/` without DB observation identity, NCP freeze semantics, or
joinable `open_30m` labels. Without a governed path, implementers will treat IEV
as score, PRIME as ENTER, multi-day flow as 30m confirmation, or recompute
history at grade time.

## 3. Desired Outcome

* Pre-open supplies canonical groups **`auction_ncp`** (required) and
  **`open_viability`** (optional) under contract `pre_open_signal_evidence.v1`.
* Signal runs only through **`ScreenAssessmentPipeline`** with hard guard when
  auction evidence is absent; composite uses **0.65 / 0.35** hierarchy rules from
  ADR-048.
* When signal exists: **`trade_setup_applicable=True`**, **`risk_mode=annotate`**;
  action only via **TradeSetup** (ADR-026).
* **DB observations** for all evaluated names (pass + reject), identity =
  ticker + trade_date + NCP `decision_at` + horizon `open_30m` + contract versions;
  **capture-time freeze** is champion (no silent grade-time recompute).
* UI replaces PRIME authority with **signal score/quality + TradeSetup.action**.
* **`learn grade` stays as-is until signal ships**, then evolves metrics over
  frozen decisions + tracks (capability not retired).

Out of scope for this task: automated execution/trading; accum schema rewrite;
fundamental screen; multi-day flow as pre-open signal authority.

## 4. Non-Goals (Explicitly Out of Scope)

* No new action enums (no PRIME/OPEN_LONG as production `SetupAction`).
* No confirmation-only / viability-only production signal score.
* No treating IEV rank as the weighted signal score.
* No multi-day broker BACKED / FVWAP as canonical authority for `open_30m`.
* No silent overwrite of historical decisions when scoring changes (rebuild =
  new cohort only).
* No dual adoption path outside `ScreenAssessmentPipeline`.
* No retiring `learn grade` without a replacement report path.
* No AI authority over score, risk, TradeSetup, or labels.

### Do Not Interpret This As

* Do not keep PRIME as a parallel production authority after UI cutover.
* Do not put ENTER/AVOID composition in the CLI, plan services, or grade.
* Do not call signal with fabricated `auction_ncp`.
* Do not enable `trade_setup_applicable` without a real signal path.
* Do not use grade-time recompute as the production learning path.
* Do not store observations only for PRIME/UI survivors.
* Do not reintroduce `--with-regime` / strategy-YAML risk as the Tier-1 model.

## 5. Architecture Impact Assessment

* Layers touched:
  * Domain — **Yes** (pre-open evidence VOs / group payloads; observation identity
    fields as needed; no engine subclass).
  * Application — **Yes** (pre-open `SignalInputsBuilder`, group scorers or
    mapping into existing assess path, policy flip, observation write use case,
    NCP freeze orchestration).
  * Infrastructure — **Yes** (DB schema/repo for open observations; snapshot
    wiring if needed).
  * Adapter — **Yes, thin** (CLI/TUI display cutover; learn snapshot/grade wiring;
    factories only).
* New dependency? No (unless an existing migration tool pattern requires none).
* Affects determinism? No when frozen inputs + config are fixed; scoring is
  deterministic. **SEMANTIC_ENGINE** / **EVIDENCE_CONTRACT** / **OBSERVATION_SCHEMA**
  bumps apply when signal and observation contracts land (classify in preflight).
* Persistence changes? **Yes** — DB observation store for pre-open decisions.
* Warm-up data? No new indicator family required beyond existing ATR/RSI candles.
* Orchestration/policy inside an adapter? **No.**

```md
Layer plan:
- Domain: pre-open canonical evidence group types; observation identity VOs if needed
- Application: PreOpen SignalInputsBuilder; scoring wiring; ScreenPolicy.pre_open() flip; freeze + Record* observation use case; grade evolution later
- Infrastructure: observation repository + migrations; composition roots for NCP freeze
- Adapter: thin CLI/display/learn wiring; no policy
```

## 6. AI Usage Declaration

No AI involved for authority. Optional AI research on pre-open remains
non-authoritative. `learn tune` stays non-authoritative challenger (ADR-027 /
ADR-042 posture).

## 7. Risk, Signal, and Evidence Authority Considerations

* Components affected: SignalEngine adoption (pre-open), RiskEngine (annotate),
  TradeSetup composition, MCE (already always-on annotate path), observation
  persistence, learn grade metrics.
* Behavior differences:
  * Pre-open gains production **SignalAssessment** when NCP evidence present.
  * Pre-open gains **TradeSetup** when signal exists; risk remains non-blocking.
  * UI action column becomes TradeSetup, not PRIME.
* ENTER/WATCH/AVOID production source: **TradeSetup only** once signal is on.
* Promote diagnostic evidence? **No** without later OOS/validator work; this task
  lands the **contract and producers**, not promotion of diagnostic scrapes.

## 8. Data & Persistence

* Reads: IEV/NCP snapshot data, candles, broker rows as needed for viability,
  existing risk/MCE paths.
* Writes: **DB observations** at NCP freeze; optional retention of
  `data/opening/` journals as non-authority ops artifacts.
* Schema change? **Yes** (observation tables or extension of existing candidate
  observation patterns — prefer reuse/analogy to accum, not a one-off dump).
* Source equivalence: NCP-locked auction state is a **new** authority concept for
  pre-open signal (not equivalent to multi-day flow). Name it `auction_ncp` /
  `open_viability` explicitly.

## 9. Acceptance Criteria

* [ ] ADR-048 invariants held in code and tests.
* [ ] `auction_ncp` missing ⇒ signal use case **never** called; no fabricated evidence.
* [ ] Weights/hierarchy: 0.65/0.35; auction_min default 50; no confirmation-only score.
* [ ] When signal present: pipeline sets `trade_setup_applicable=True`,
      `risk_mode=annotate`; TradeSetup composed via `AssessTradeSetupUseCase` only.
* [ ] Risk never drops pre-open candidates (annotate).
* [ ] DB observations written for **all** evaluated names with
      `screen_result` funnel strings; identity includes NCP `decision_at` +
      `open_30m` + contract versions.
* [ ] Capture-time freeze: re-running grade does not rewrite decision scores;
      rebuild is explicit new cohort only.
* [ ] UI: no PRIME-as-authority after cutover; signal + TradeSetup shown.
* [ ] `learn grade` unchanged until signal phase lands; post-signal evolution
      documented/tests for new metrics path.
* [ ] Adoption only via `ScreenAssessmentPipeline`; architecture boundary tests green.
* [ ] Offline deterministic tests; DoD; adapter thinness reviewed.

## 10. Testing Expectations

* Unit: evidence builders; hard guard; weight/hierarchy edge cases (viability
  missing ⇒ auction-only + MODERATE cap); TradeSetup composition with annotate risk.
* Unit: observation identity uniqueness; reject paths still recorded.
* Negative: confirmation-only path impossible; dual PRIME authority gone after cutover;
  grade-time recompute not used as champion.
* Integration: NCP freeze → DB row → join track fixture → metrics (when grade evolves).
* Architecture: `tests/architecture/test_layer_boundaries.py` green.
* All tests offline. No skips without justification.

## 11. Documentation Impact

* README / CLI docs: pre-open signal + TradeSetup; PRIME removed from authority language.
* Opening workflow docs: NCP freeze, horizon `open_30m`, observation/grade notes.
* `learn grade` docs: evolve after signal; keep command.
* New config: weights, auction_min, evidence contract version — document when added.
* Limitations: multi-day flow not pre-open signal authority; risk non-blocking.

## 12. Phase Plan and Checkpoints

Per AGENT_QUICKSTART: split foundational contracts from broad integration. Do not
start a later phase until the prior checkpoint passes. **Stop for review** at
each phase gate.

### Phase 0 — Contracts only (may be mostly done by ADR-048)

* Confirm ADR-048 Accepted + index row (done at task creation time if already
  merged).
* Optional: task-local glossary / material config key list for open signal.
* *Checkpoint:* ADR-048 linked; no code required if ADR already landed.

### Phase 1 — Evidence types + SignalInputsBuilder + policy flip

* Domain/application types for `auction_ncp` and `open_viability` with provenance.
* Pre-open `SignalInputsBuilder` feeding `ScreenAssessmentPipeline`.
* Flip `ScreenPolicy.pre_open()`: `signal_applicable=True` when builder can
  supply auction; **`trade_setup_applicable=True` when signal runs**; risk annotate.
* Group scoring sufficient for a deterministic composite (formula may start simple
  but must be config-driven and tested).
* *Checkpoint:* hard-guard tests; weights tests; TradeSetup composed only via
  AssessTradeSetupUseCase; layer boundaries green. **Review stop.**

### Phase 2 — DB observations + NCP freeze

* Persistence schema + repository port/impl.
* Write observations for all loop names at NCP `decision_at` (freeze signal, risk,
  TradeSetup, plan, identity, contract versions).
* Explicit rebuild path design (new cohort) — may stub but must not overwrite.
* *Checkpoint:* identity uniqueness tests; freeze vs recompute negative test;
  rejects recorded. **Review stop.**

### Phase 3 — UI cutover

* Replace PRIME authority column with signal score/quality + TradeSetup.action.
* Envelope/JSON fields under ADR-046 adopt-on-touch as needed.
* *Checkpoint:* CLI/TUI/display tests; no production PRIME authority. **Review stop.**

### Phase 4 — `learn grade` evolution

* Keep command; extend metrics over frozen observations + tracks
  (plan + signal bands + `screen_result` slices).
* Demote PRIME strata from champion KPI.
* *Checkpoint:* grade tests with fixtures; tune/prompt consumers still feed or are
  updated deliberately. **Final gate.**

## Frozen execution contract (do not re-litigate)

From ADR-048 acceptance discussion:

| Topic | Value |
|-------|--------|
| Horizon | `open_30m` (flat 09:30) |
| Groups | `auction_ncp` required; `open_viability` optional initially |
| Weights | 0.65 / 0.35; `auction_min` default 50 |
| Confirmation-only score | Forbidden |
| TradeSetup | On when signal exists |
| Risk | Annotate (non-blocking) |
| Observations | DB, all names, funnel `screen_result` |
| Capture | NCP freeze champion |
| PRIME | Remove as authority at UI cutover |
| learn grade | Unchanged until signal; then evolve, do not retire |
| Adoption | `ScreenAssessmentPipeline` only |

## Final Gate

Definition of Done: deterministic, offline-capable, adapter-thin, ADR-041/026/047/048
intact, no dual verdict path, NCP freeze champion, no non-goals violated.
If a checkpoint cannot be met, stop and report rather than weaken the contract.
