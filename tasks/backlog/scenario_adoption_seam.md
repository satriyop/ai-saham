# Task: Scenario-Adoption Seam for Signal / Risk / Market-Context Engines

Governing decision: [ADR-047](../../docs/adr/ADR-047-scenario-adoption-seam-for-signal-risk-mce.md)

## 1. Task Metadata

**Task Title:** Unify engine adoption across screen scenarios via a shared assessment pipeline + per-scenario seam.

**Task Type:** Refactor (Phases 0–1) + Feature (Phase 2).

**Priority:** Medium.

## 2. Problem Statement

`SignalEngine`, `RiskEngine`, and `MCE` are single and generic, but each screen
adopts them differently. `screen accum` wires all three through two bespoke
wrappers; `screen pre-open` wires none in its core pipeline, exposing regime and
risk only as opt-in display overlays. There is no shared adoption abstraction, so
every new scenario re-decides whether to use the engines and can ship without
risk/regime context. This drifts parity and duplicates plumbing as scenarios grow
(pre-open today, a fundamental screen next).

## 3. Desired Outcome

* One shared `ScreenAssessmentPipeline` orchestrates `regime -> signal -> risk ->
  trade_setup` for any screen.
* Each scenario plugs in via three thin interfaces: `SignalInputsBuilder`, a
  risk-input choice (pre-built `GateContext` **or** self-fetch), and a
  `ScreenPolicy`.
* `screen accum` behaves identically to today, now implemented **through** the
  seam (its two wrappers refactored in; no dual path).
* `screen pre-open` gains **always-on** (not flag-gated) non-authoritative regime
  + risk context via the seam, with `signal_applicable = False`.
* The shared `SignalContext` builder is scenario-agnostic (optional
  `accum_score` / `foreign_flow_quality`).

Out of scope for this task: a pre-open-native canonical signal-evidence source;
any engine-internal or scoring change; a fundamental screen.

## 4. Non-Goals (Explicitly Out of Scope)

* No `SignalEngine` / `RiskEngine` / `MCE` internal or scoring-math changes.
* No new data providers.
* No fabricated canonical signal evidence for scenarios that lack setup/flow
  provenance — absence returns `None` (MISSING group), per ADR-041.
* No promotion of regime-adjusted risk to authoritative (stays preview, ADR-037).
* No change to accumulation canonical output (Phases 0–1 byte-identical).
* No AI / model authority changes.
* No new engine subclasses or per-scenario engine variants.

## 5. Architecture Impact Assessment

* Layers touched:
  * Domain — **not touched** (engines/value objects already generic).
  * Application — **Yes** (new seam + pipeline; generalize builder; refactor accum
    wrappers; pre-open Tier-1 adoption; per-scenario fetch-strategy policy).
  * Infrastructure — **Minimal** (reuse existing engine factories; at most a thin
    composition wiring so pre-open receives the pipeline — a factory, not policy).
  * Adapter — **Yes, thin** (pre-open CLI wires the seam-backed use case and
    renders; owns no policy).
* New dependency? No.
* Affects determinism? No (deterministic engines unchanged; same inputs ⇒ same
  outputs; pre-open adds deterministic risk/regime).
* Persistence changes? No schema change. Pre-open response gains risk/regime
  fields (in-memory DTO / CLI envelope only).
* Warm-up data? No new indicator.
* Orchestration/policy inside an adapter? **No.** All adoption policy lives in the
  application pipeline/seam. Adapter only wires and renders.

```md
Layer plan:
- Domain: not touched
- Application: ScreenAssessmentPipeline; SignalInputsBuilder / RiskInputsBuilder (Protocol) / ScreenPolicy interfaces; generalize build_signal_context_from_candidate; accum seam impls (refactor existing wrappers); pre-open Tier-1 seam impl + workflow wiring
- Infrastructure: reuse existing signal/risk/MCE factories; thin composition wiring for pre-open pipeline if needed
- Adapter: pre-open CLI wires the new use-case path and renders regime/risk; no policy added
```

## 6. AI Usage Declaration

No AI involved. Deterministic engines only; behavior is identical with AI
disabled.

## 7. Risk, Signal, and Evidence Authority Considerations

* Components affected: SignalEngine adoption, RiskEngine adoption, MCE adoption,
  TradeSetup composition point (reused, unchanged), ScreenPolicy interpretation.
* Behavior differences:
  * accum — **none** (same canonical output, now via the seam).
  * pre-open — gains non-authoritative regime + risk annotation, always-on;
    signal remains not-applicable (no canonical evidence).
* Does this change what can produce ENTER/WATCH/AVOID? For accum, no. For
  pre-open, it does not introduce a signal verdict; risk/regime remain preview /
  non-blocking per policy and ADR-037.
* Promote diagnostic evidence or change tuning eligibility? **No.** ADR-041
  provenance boundary and evidence authority are unchanged; no evidence is
  fabricated or promoted.

## 8. Data & Persistence

* Reads: existing candidate/enrichment data already loaded per scenario, plus
  self-fetched risk enrichment for pre-open (via `RiskEngine.assess`).
* Writes: none new to disk. Pre-open in-memory response/CLI envelope gains
  regime + risk fields.
* Schema change? No.
* Source equivalence: no data-source swap; accum consumes the same rows via the
  same builders. Pre-open self-fetch uses existing providers behind `RiskEngine`.

## 9. Acceptance Criteria

* [ ] `screen accum` output is byte-identical before/after (regression fixture).
* [ ] accum runs entirely through `ScreenAssessmentPipeline`; the two old wrappers
      exist only as seam implementations — grep confirms no parallel adoption path.
* [ ] `screen pre-open` shows regime + risk **without** `--with-regime` /
      `--risk-strategy` flags; risk is non-blocking; `signal_applicable = False`.
* [ ] Generalized `build_signal_context_from_candidate` accepts a candidate with
      no `accum_score` and yields `foreign_flow_quality = None`.
* [ ] Signal is a **hard guard**: when `signal_applicable = False` or canonical
      evidence is absent, the pipeline does **not** invoke the signal use case
      (which raises `NoProductionSignalEvidenceError`). Negative test asserts the
      use case is never called and no evidence is fabricated.
* [ ] Fetch-strategy choice (self-fetch vs pre-built `GateContext`) is set in the
      application seam, not the adapter.
* [ ] Works offline; deterministic for same inputs; complies with DoD; no
      non-goals violated; ADR-047 (+ 024/026/037/041) considered; adapter thinness
      reviewed.

## 10. Testing Expectations

* Unit: `ScreenAssessmentPipeline` orchestration order; `ScreenPolicy`
  block-vs-annotate and applicability flags; generalized enrichment builder
  (with and without `accum_score`).
* Negative: canonical evidence `None` ⇒ signal use case **not invoked** (hard
  guard), no fabrication; `signal_applicable = False` ⇒ signal step skipped;
  adapter carries no policy.
* Regression: accum canonical output fixture unchanged; accum repository read
  count unchanged (no new N+1 introduced by the refactor).
* Parity: pre-open regime/risk present without flags; risk does not drop
  candidates.
* Architecture: `tests/architecture/test_layer_boundaries.py` stays green.
* All tests run offline. No skips without justification.

## 11. Documentation Impact

* README / CLI docs: pre-open section update (regime/risk now always-on). Yes.
* New config options: possibly a pre-open risk/regime toggle default; document if
  added. TBD in Phase 2.
* Limitations to state: pre-open signal is intentionally not-applicable (no
  canonical evidence). Yes.
* On ADR acceptance: add ADR-047 to the `ARCHITECTURE_DECISIONS.md` index and the
  relevant task-matrix rows.

## 12. Phase Plan and Checkpoints

Per AGENT_QUICKSTART "split foundational contracts from broad integration":
each phase is independently reviewable; do not start a later phase until the
prior checkpoint passes.

* **Phase 0 — Generalize the enrichment builder + opportunistic docstring hygiene.**
  Make `build_signal_context_from_candidate` `accum_score`-optional. The
  `SignalContext` value-object docstrings were already corrected (retired
  "drives the score" / RiskLevel-Profile language); the remaining stale bit is
  `signal_context_builder.py` ("accumulation-style candidate"), which this
  generalization makes inaccurate anyway — fix it opportunistically, not a
  rewrite. Keep the name `SignalContext` (no rename).
  *Checkpoint:* accum output byte-identical; builder unit tests (with/without
  `accum_score`) pass.
* **Phase 1 — Extract the seam + refactor accum in (clean break).**
  **First:** move ADR-047 to Accepted and add it to `ARCHITECTURE_DECISIONS.md`
  index + matrix rows (this phase lands the structural signal/risk composition
  change — acceptance gates the merge). Then add `ScreenAssessmentPipeline` +
  `SignalInputsBuilder` + `RiskInputsBuilder` (Protocol: `candidate -> GateContext
  | None`; `None` ⇒ self-fetch) + `ScreenPolicy`. Move
  `AccumulationCandidateSignalAssessor` / `AccumulationRiskFunnel` logic into accum
  seam implementations. No dual path.
  *Checkpoint:* ADR-047 Accepted + indexed; accum regression fixture + read-count
  test green; grep confirms no parallel adoption route; layer-boundary tests green.
  **Stop for review here before Phase 2.**
* **Phase 2 — Route pre-open through the seam at Tier-1.**
  `PreOpenWorkflowUseCase._finish` invokes the pipeline: regime (always-on) + risk
  (self-fetch, annotate/non-blocking), `signal_applicable = False`,
  `trade_setup_applicable = False`. Update CLI wiring + envelope + docs. See the
  **Phase 2 execution contract** below for the exact risk/flag/failure/root
  decisions.
  *Checkpoint:* pre-open shows regime+risk with no opt-in flags; risk never drops a
  candidate; failures soft-warn; CLI/display + envelope tests; manual inspection.
* **Phase 3 — (Future, separate task)** fundamental scenario + any pre-open
  canonical-evidence source. Not in this task.

### Phase 2 execution contract

Resolved decisions (do not re-litigate at implementation time):

- **Risk default:** `RiskEngine.assess(ticker, as_of, market_context)` runs the
  engine's default structural+execution gate pipeline (no strategy YAML). Same
  canonical gates as `analyze risk` / accum.
- **Risk output:** the pipeline produces a full `RiskAssessment`; the pre-open
  workflow **projects it to a compact per-ticker summary** (`risk_level_name`,
  triggered gate, `is_structural`, confidence) on `PreOpenWorkflowResponse`,
  replacing today's `strategy_risk_statuses: dict[str,str]`. Do **not** mutate
  `ScreenerCandidate` (stays a pure domain VO); do **not** transport the full DTO
  per candidate.
- **`--risk-strategy`:** removed (clean break). The always-on default-gate
  assessment supersedes the YAML overlay. A deliberate `--risk-rules` override may
  be added later as a separate task if needed.
- **Flags:** remove opt-in `--with-regime`; add opt-out `--no-regime` / `--no-risk`
  (default on), matching the existing `--fast/--no-fast` convention. Opt-out is
  required because `MCE.evaluate` needs market data and pre-open must stay
  offline-capable.
- **Failure semantics:** soft. Regime failure ⇒ warning + `None` regime; per-ticker
  risk failure ⇒ warning + `None`/`?` for that ticker. **Candidates are never
  dropped** by risk/regime in pre-open (`ScreenPolicy = annotate`, not `block`).
- **`trade_setup_applicable = False`:** ADR-026 composes TradeSetup from Signal +
  Risk; with no `SignalAssessment` there is nothing to compose. Do not invoke
  `AssessTradeSetupUseCase` for pre-open.
- **Composition roots (adopt):** `PreOpenWorkflowUseCase._finish` (covers live and
  snapshot-fallback display — both route through `_finish`) and the `screen
  pre-open` CLI wiring (`create_pre_open_cli_workflow` /
  `screen_pre_open_commands.py`).
- **Composition roots (explicitly out of scope):** `opening_snapshot_use_case`
  (NCP 08:57 capture of *raw* screen candidates — risk/regime are applied at
  display time when a snapshot is replayed through `_finish`, so no seam there);
  `AccumulationScreenUseCase` (that is Phase 1). Verify no other production path
  renders pre-open candidates directly.

## Final Gate

Definition of Done compliance: deterministic, offline-capable, adapter-thin,
accum canonical output preserved, ADR-041 boundary intact, no non-goals violated.
If any checkpoint cannot be met (esp. accum byte-identity in Phases 0–1), stop and
report rather than weaken the contract.
