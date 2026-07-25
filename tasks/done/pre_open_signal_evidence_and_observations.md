# Task: Pre-Open Signal Evidence, TradeSetup, and DB Observations

Governing decision: [ADR-048](../../docs/adr/ADR-048-pre-open-signal-evidence-and-observation-identity.md)

Related: [ADR-047](../../docs/adr/ADR-047-scenario-adoption-seam-for-signal-risk-mce.md) (seam — already landed),
[ADR-041](../../docs/adr/ADR-041-canonical-signal-evidence-input-boundary.md),
[ADR-026](../../docs/adr/ADR-026-risk-plus-signal-pipeline-composition.md),
[ADR-027](../../docs/adr/ADR-027-risk-signal-learning-loop.md)

Prerequisite: ADR-047 Phases 0–2 complete (`ScreenAssessmentPipeline`; pre-open
Tier-1 regime + annotate risk; `signal_applicable=False` today).

## 1. Task Metadata

**Task Title:** Land pre-open canonical signal (NCP auction + open viability), compose TradeSetup, save DB observations at NCP, cut over UI and grade.

**Task Type:** Feature (phased) + persistence.

**Priority:** Medium.

## 2. Problem Statement

Pre-open discovers names via IEV and builds an auction entry plan, but has no
production signal evidence channel and no TradeSetup. Display labels (PRIME /
WATCH / SKIP) and `learn grade` strata on `opening_setup` act as a shadow
verdict language outside ADR-026. Opening learning lives in day files under
`data/opening/` without DB observation identity, capture-at-NCP semantics, or
joinable `open_30m` labels. Without a governed path, implementers will treat IEV
as score, PRIME as ENTER, multi-day flow as 30m confirmation, or recompute
history at grade time.

## 3. Desired Outcome

* Pre-open supplies canonical groups **`auction_ncp`** (required) and
  **`open_viability`** (optional) under contract `pre_open_signal_evidence.v1`.
* Signal runs only through **`ScreenAssessmentPipeline`** with hard guard when
  auction evidence is absent; **auction is the primary driver and `open_viability`
  is veto-only** per ADR-048 §4. v1 MAY render an ordinal gate cascade; a weighted
  composite (weights `0.65 / 0.35` **provisional/unvalidated**, config-driven) is the
  v2 form, not required here. **Exactly one champion rendering** is active in
  production config (cascade **XOR** composite) — never both dual-path scores.
* Illustrative **v1 cascade** (not the only legal factor set; documents intent):
  1. `auction_ncp` MISSING or below floor → **no production signal** (hard guard);
  2. auction OK but `open_viability` veto (e.g. GAP_OUT / friction fail) → signal
     may exist but **cap** `EntryQuality` ≤ WATCH or AVOID via constraints;
  3. else strength/quality from **auction bands** (viability does not boost score).
* When signal exists: **`trade_setup_applicable=True`**, **`risk_mode=annotate`**;
  action only via **TradeSetup** (ADR-026).
* **DB observations** for all evaluated names (pass + reject), identity =
  ticker + trade_date + NCP `decision_at` + horizon `open_30m` + contract versions;
  **capture-time saved observations** are champion (no silent grade-time recompute).
* UI replaces PRIME authority with **signal score/quality + TradeSetup.action**.
* **`learn grade` stays as-is until signal ships**, then evolves metrics over
  saved decisions + tracks (capability not retired).

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
* Do not run cascade and weighted composite as parallel production scores.

## 5. Architecture Impact Assessment

* Layers touched:
  * Domain — **Yes** (pre-open evidence VOs / group payloads; observation identity
    fields as needed; no engine subclass).
  * Application — **Yes** (pre-open `SignalInputsBuilder`, group scorers or
    mapping into existing assess path, policy flip, observation write use case,
    NCP capture orchestration).
  * Infrastructure — **Yes** (DB schema/repo for open observations; snapshot
    wiring if needed).
  * Adapter — **Yes, thin** (CLI/TUI display cutover; learn snapshot/grade wiring;
    factories only).
* New dependency? No (unless an existing migration tool pattern requires none).
* Affects determinism? No when saved inputs + config are fixed; scoring is
  deterministic. Preflight **must** classify: at minimum **EVIDENCE_CONTRACT**
  (new groups) and **OBSERVATION_SCHEMA** (DB rows); add **SEMANTIC_ENGINE**
  and/or **CONFIG_MATERIAL** when strength bands, cascade rules, or composite
  weights can change canonical signal output.
* Persistence changes? **Yes** — DB observation store for pre-open decisions.
* Warm-up data? No new indicator family required beyond existing ATR/RSI candles.
* Orchestration/policy inside an adapter? **No.**

```md
Layer plan:
- Domain: pre-open canonical evidence group types; observation identity VOs if needed
- Application: PreOpen SignalInputsBuilder; scoring wiring; ScreenPolicy.pre_open() flip; capture + Record* observation use case; grade evolution later
- Infrastructure: observation repository + migrations; composition roots for NCP capture
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
* Writes: **DB observations** at NCP capture; optional retention of
  `data/opening/` journals as non-authority ops artifacts.
* Schema change? **Yes** (observation tables or extension of existing candidate
  observation patterns — prefer reuse/analogy to accum, not a one-off dump).
* Source equivalence: NCP-locked auction state is a **new** authority concept for
  pre-open signal (not equivalent to multi-day flow). Name it `auction_ncp` /
  `open_viability` explicitly.

## 9. Acceptance Criteria

* [ ] ADR-048 invariants held in code and tests.
* [ ] `auction_ncp` missing ⇒ signal use case **never** called; no fabricated evidence.
* [ ] Hierarchy: auction primary, `open_viability` veto-only, hard guard, MISSING ⇒
      MODERATE cap; no confirmation-only score. Production uses **exactly one**
      rendering (cascade XOR composite). If a composite is used, weights are
      config-driven **provisional** defaults (0.65/0.35, auction_min 50), never hardcoded.
* [ ] When signal present: pipeline sets `trade_setup_applicable=True`,
      `risk_mode=annotate`; TradeSetup composed via `AssessTradeSetupUseCase` only.
* [ ] Risk never drops pre-open candidates (annotate).
* [ ] DB observations written for **all** evaluated names with
      `screen_result` funnel strings; identity includes NCP `decision_at` +
      `open_30m` + contract versions.
* [ ] Capture-time save: re-running grade does not rewrite decision scores;
      rebuild is explicit new cohort only.
* [ ] UI: no PRIME-as-authority after cutover; signal + TradeSetup shown.
* [ ] `learn grade` unchanged until signal phase lands; post-signal evolution
      documented/tests for new metrics path.
* [ ] Adoption only via `ScreenAssessmentPipeline`; architecture boundary tests green.
* [ ] Offline deterministic tests; DoD; adapter thinness reviewed.

## 10. Testing Expectations

* Unit: evidence builders; hard guard; hierarchy/veto edge cases (viability
  missing ⇒ auction-only + MODERATE cap; veto caps quality); TradeSetup with
  annotate risk. If composite exists: config weights not hardcoded.
* Unit: observation identity uniqueness; reject paths still recorded.
* Negative: confirmation-only path impossible; dual PRIME authority gone after
  cutover; dual cascade+composite production scores impossible; grade-time
  recompute not used as champion.
* Integration: NCP capture → DB row → join track fixture → metrics (when grade evolves).
* Architecture: `tests/architecture/test_layer_boundaries.py` green.
* All tests offline. No skips without justification.

## 11. Documentation Impact

* README / CLI docs: pre-open signal + TradeSetup; PRIME removed from authority language.
* Opening workflow docs: NCP capture, horizon `open_30m`, observation/grade notes.
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
* Group scoring: deterministic and config-driven. v1 MAY be an ordinal gate cascade
  (auction-primary, `open_viability` veto-only — see Desired Outcome example); a
  weighted composite with provisional weights is an acceptable alternative but
  **not required**. Champion path is singular (cascade XOR composite).
* *Checkpoint:* hard-guard + hierarchy/veto tests (auction-only / MODERATE cap;
  veto caps EntryQuality); if composite path is implemented, config-driven
  weights tests; TradeSetup only via AssessTradeSetupUseCase; layer boundaries
  green. **Review stop.**

### Phase 2 — DB observations + NCP capture

* Persistence schema + repository port/impl.
* Write observations for all loop names at NCP `decision_at` (save signal, risk,
  TradeSetup, plan, identity, contract versions).
* Explicit rebuild path design (new cohort) — may stub but must not overwrite.
* *Checkpoint:* identity uniqueness tests; save-vs-recompute negative test;
  rejects recorded. **Review stop.**

### Phase 3 — UI cutover

* Replace PRIME authority column with signal score/quality + TradeSetup.action.
* Envelope/JSON fields under ADR-046 adopt-on-touch as needed.
* *Checkpoint:* CLI/TUI/display tests; no production PRIME authority. **Review stop.**

### Phase 4 — `learn grade` evolution (session scorecard only)

**Status:** Phases 1–4 landed in code (see git history).

**Locked scope (do not expand without a new task):**

* **Keep** the `saham learn grade` command and day-report UX (`grade.json` /
  `grade.md` for `learn tune` / `prompt` compatibility; bump schema/version
  notes if fields change).
* **Prefer saved DB observations** (`workflow=screen_pre_open`,
  `observation_contract=pre-open-open-30m`) joined to `learn track` files when
  observations exist for that date; fall back to `snapshot.json` plan fields
  when no DB rows (graceful, documented).
* **Champion metrics:** plan (entry range hit, IEP error, stop path) + **signal
  score bands** + `screen_result` / TradeSetup action slices.
* **Demote PRIME / `opening_setup` strata** to legacy/secondary only — not the
  champion KPI.
* Deterministic, offline; no grade-time recompute of signal (read saved observations only).

**Explicit non-goals for Phase 4 (follow-up tasks):**

* Do **not** implement `research signal labels` / readiness for
  `pre-open-open-30m` here (that is the accum-style **corpus label** path —
  closest architectural twin, separate product surface).
* Do **not** retire `learn grade` or fold it into `research signal`.
* Do **not** change swing label horizons or accumulation-discovery contracts.

**Analogy (for implementers):** accum’s long-term equivalent of “outcomes on
saved decisions” is `saham research signal labels` + `readiness` on
`candidate_observations`. Pre-open Phase 4 is only the **opening session
scorecard** over saved observations + tracks — not full research-corpus parity.

* *Checkpoint:* grade tests with fixtures (saved observations present / absent fallback);
  PRIME not champion KPI; tune/prompt still consumable. **Final gate.**

## Locked execution contract (do not re-litigate)

From ADR-048 acceptance discussion + Phase 4 scope lock:

| Topic | Value |
|-------|--------|
| Horizon | `open_30m` (flat 09:30) |
| Groups | `auction_ncp` required; `open_viability` optional initially |
| Hierarchy | Auction primary; `open_viability` veto-only; hard guard; MISSING ⇒ MODERATE cap |
| Weights / rendering | v1 cascade OR composite (**XOR**, one champion); weights **provisional** CONFIG_MATERIAL (0.65/0.35, auction_min 50), not locked |
| Confirmation-only score | Forbidden |
| TradeSetup | On when signal exists |
| Risk | Annotate (non-blocking) |
| Observations | DB, all screened candidates, funnel `screen_result` (Phase 2) |
| Capture | Save at NCP decision_at (champion) |
| PRIME | Remove as authority at UI cutover (Phase 3) |
| learn grade (Phase 4) | **Evolve session scorecard** over saved observations + tracks; keep command; PRIME secondary |
| research open labels | **Out of this task** — future research-family work |
| Adoption | `ScreenAssessmentPipeline` only |

## Final Gate

Definition of Done: deterministic, offline-capable, adapter-thin, ADR-041/026/047/048
intact, no dual verdict path, capture-time saved observations champion, no non-goals violated.
If a checkpoint cannot be met, stop and report rather than weaken the contract.
