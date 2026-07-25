# ADR-047: Scenario-Adoption Seam for Signal / Risk / Market-Context Engines

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Proposed
**Date:** 2026-07-25
**Depends on:** [ADR-024](ADR-024-signal-engine-and-risk-engine-as-first-class-application-services.md), [ADR-029](ADR-029-market-context-engine-mce-third-first-class-application-service.md), [ADR-040](ADR-040-manual-dependency-injection-and-composition-roots.md), [ADR-003](ADR-003-hexagonal-ports-adapters-architecture.md)
**Related:** [ADR-025](ADR-025-signalengine-architecture.md), [ADR-026](ADR-026-risk-plus-signal-pipeline-composition.md), [ADR-030](ADR-030-accumulation-screener-evidence-split.md), [ADR-037](ADR-037-marketcontext-promotes-from-preview-only-to-canonical-signal-input.md), [ADR-041](ADR-041-canonical-signal-evidence-input-boundary.md), [ADR-033](ADR-033-workflow-composition-artifact-boundaries.md)
**Current implementation:** Not yet implemented. This ADR records the target design; landing is phased (see task `tasks/backlog/scenario_adoption_seam.md`). On acceptance, add the index row and the "Signal scoring" / "Risk" / "Market context" matrix references in `ARCHITECTURE_DECISIONS.md`.

### Context

`SignalEngine`, `RiskEngine`, and `MarketContextEngine` (MCE) are already single,
domain-generic application services (ADR-024, ADR-029). They consume generic
value objects (`SignalContext`, `GateContext`, `BuildMarketContextRequest`) and
hardcode no accumulation concepts.

The asymmetry is one layer above the engines, in how each **screen scenario
adopts** them:

* **`screen accum`** adopts all applicable engines through two bespoke wrapper
  services — `AccumulationCandidateSignalAssessor` (signal, with the ADR-041
  canonical-evidence boundary) and `AccumulationRiskFunnel` (risk + trade-setup
  composition). Signal is mandatory per candidate; risk blocks survivors.
* **`screen pre-open`** adopts **none of them** in its core pipeline
  (`PreOpenScreenUseCase`). It borrows only the `IndicatorRegistry` for ATR/RSI
  math. Regime and risk exist solely as **opt-in display overlays** behind the
  `--with-regime` and `--risk-strategy` flags in the workflow layer; neither is
  always-on, and risk never blocks.
* There is **no shared screening abstraction**. Each screen is an independent
  use-case pipeline, so adopting the engines is a per-screen decision a new
  scenario can silently skip — which is exactly what pre-open did.

This invites three problems as scenarios grow (pre-open, a future fundamental
screen, …):

1. **Parity drift** — every new screen re-litigates whether to wire the engines,
   and can quietly ship without risk/regime context.
2. **N-times-3 bespoke plumbing** — each scenario grows its own signal/risk
   wrappers instead of sharing one adoption seam.
3. **Conflating "runnable" with "meaningful"** — teams assume a screen must
   either replicate accum's full canonical-evidence machinery or omit the
   engines entirely, when the correct middle ground (regime + risk always-on,
   signal correctly declared not-applicable) is unavailable because there is no
   seam for it.

This ADR records a **scenario-adoption seam**: the engines stay single and
generic, and each scenario plugs into them through a thin, uniform
builder/policy interface — including the option to declare a channel
not-applicable.

### Key distinction that shapes the design

`SignalEngine.evaluate_with_context` takes **two separate evidence channels**
that do different jobs (see `signal_engine.py` and ADR-041):

| Channel | Type | Role |
|---|---|---|
| `canonical_evidence` | `CanonicalSignalEvidenceInput` (setup + flow groups) | **Authority — the entire weighted score.** The composite is Setup (0.60) + Flow (0.40), renormalized over present groups. ADR-041 provenance-bound; the sole setup/flow input. When a group is absent it is MISSING — excluded from the denominator. Cannot be fabricated. |
| `signal_context` | `SignalContext` | **Supplementary enrichment bundle, non-authoritative.** Pre-loaded per-ticker enrichment (bandar / seasonality / analyst / insider / forward-PE / foreign-flow-quality) consumed by several downstream computations: penalty flags in `SignalEvidenceGroupScorer._evaluate_flags`, company-quality sub-scores in `company_quality_scoring` / `company_quality_context_evidence_builder`, and presence checks in `signal_presence`. It is **not** the Setup/Flow weighted-score source — that is `canonical_evidence`. |

Consequences that this ADR encodes:

* The weighted signal score (Setup/Flow groups) is produced **entirely from
  `canonical_evidence`**. `SignalContext` feeds non-authoritative side channels
  (penalty flags, company-quality sub-scores, presence checks). Generalizing the
  shared enrichment builder lets a scenario that carries those enrichment fields
  populate them — it makes signal *runnable*, not *authoritative*.
* **Signal is a hard guard, not a graceful degrade.** `AssessSignalEvidenceUseCase`
  **raises `NoProductionSignalEvidenceError`** when neither setup nor flow evidence
  is present (`assess_signal_evidence_use_case.py:61-64`). A scenario without
  canonical evidence (e.g. pre-open) therefore must **not invoke the signal use
  case at all** — there is no low-authority fallback score to fall back to.
* Enrichment reuse and canonical-evidence supply are **two independent unlocks**
  and must be phased separately.

### Decision

#### 1. Engines stay single and generic; scenarios differ only in a thin seam

There is exactly one `SignalEngine`, one `RiskEngine`, and one
`MarketContextEngine`. No scenario introduces an engine subclass or variant.
Scenario differences live only in a small, uniform adoption seam.

#### 2. A shared `ScreenAssessmentPipeline` owns engine orchestration

Introduce an application service `ScreenAssessmentPipeline` that holds the three
engines plus `AssessTradeSetupUseCase` and orchestrates, per candidate:

```text
market_context (once per run)  ->  signal (if applicable)  ->  risk  ->  trade_setup (if applicable)
```

It owns the *order and composition*, not the scenario-specific input shapes.
`AssessTradeSetupUseCase` remains the single Signal+Risk composition point
(ADR-026).

Named **Assessment**, not Enrichment: in this codebase "enrichment" already means
attaching provider *input* data to candidates (`AccumulationCandidateEnricher`,
`RefreshStockbitEnrichmentUseCase`, ADR-038 point-in-time enrichment). This
pipeline *consumes* that enrichment and runs the assessment engines to produce
`SignalAssessment` / `RiskAssessment` / trade-setup outputs — do not rename it
back toward "enrichment."

#### 3. Scenarios provide inputs through three seam interfaces

Each scenario supplies:

* **`SignalInputsBuilder`** — `candidate -> (SignalContext, canonical_evidence | None, setup_family | None, setup_phase | None, authority_denominator_scope)`.
  Returning `canonical_evidence = None` is a **first-class, valid** result meaning
  "no setup/flow evidence available for this scenario." The pipeline reads that as
  a signal-not-applicable outcome and skips the signal use case (which would
  otherwise raise) — never a fabricated input.
* **Risk input choice** — either a pre-built `GateContext` (screener N+1
  avoidance via `RiskEngine.assess_with_context`, as accum does today) **or**
  self-fetch (`RiskEngine.assess`, for scenarios that do not pre-load
  fundamentals). This choice is **application policy**, selected per scenario,
  never decided in an adapter.
* **`ScreenPolicy`** — thresholds and interpretation: `signal_applicable`,
  `trade_setup_applicable`, block-vs-annotate for risk, and any min-score gates.

#### 4. Two-tier adoption

* **Tier-1 (regime + risk), universal and self-sufficient.** `MCE.evaluate` and
  `RiskEngine.assess` are self-fetching and already accept `market_context`. Any
  screen can adopt regime + risk with one call each and no provenance machinery.
  This is the always-on baseline every screen should have.
* **Tier-2 (signal), evidence-gated by a hard guard.** Requires the scenario's
  `SignalInputsBuilder` to supply canonical evidence. Absent that, the pipeline
  **must not call the signal use case** — it raises `NoProductionSignalEvidenceError`
  with no setup/flow evidence. `ScreenPolicy.signal_applicable` is therefore a
  correctness guard, not a display toggle: `False` (or absent canonical evidence)
  means the signal step is skipped entirely.

#### 5. Generalize the shared enrichment builder (foundational)

`build_signal_context_from_candidate` currently hard-depends on
`candidate.accum_score` to derive `foreign_flow_quality`. Generalize it so that
dependency is optional (absent `accum_score` ⇒ `foreign_flow_quality = None`),
keeping every other field `getattr`-driven. Accumulation output must be
**byte-identical** after this change.

Scope note: this builder feeds `SignalContext`, the enrichment bundle (bandar /
seasonality / analyst / insider / forward-PE). Generalizing it primarily benefits
a **future enrichment-rich scenario** (e.g. a fundamental screen that loads those
fields) and decouples the builder from accum; **pre-open populates none of those
fields and gains nothing here**, which is why pre-open stays Tier-1 (regime +
risk) only. Separately, `SignalContext`'s per-field docstrings are stale
(legacy flat-6-factor "drives the score" language) and should be corrected to the
current two-group reality as part of Phase 0 — a docstring fix, not a rename;
`SignalContext` is a defensible house name parallel to `GateContext` /
`MarketContext`.

#### 6. Pre-open adopts Tier-1 now; signal deferred

`screen pre-open` routes through the seam at Tier-1: **regime + risk always-on**
(not behind flags), risk **non-blocking / annotation** by policy, and
`signal_applicable = False`. For pre-open, `signal_applicable = False` is
**mandatory, not a preference**: it carries no setup/flow canonical evidence, so
invoking the signal use case would raise. A pre-open-native canonical evidence
source is a separate future decision, not part of this ADR.

#### 7. Clean break for accum

`AccumulationCandidateSignalAssessor` and `AccumulationRiskFunnel` are refactored
**into** the accum implementations of the seam interfaces. No dual old/new path,
no compatibility shim, no parallel adoption route survives (AGENT_QUICKSTART
clean-break policy).

### Invariants / Consequences

* One engine type each; scenarios differ only in `SignalInputsBuilder`,
  risk-input choice, and `ScreenPolicy`.
* **No fabricated evidence.** A scenario that cannot supply canonical setup/flow
  evidence returns `None` for that group; the engine treats it as MISSING. The
  ADR-041 provenance boundary is preserved end to end.
* **Signal is a hard guard, not a soft flag.** The pipeline MUST NOT invoke the
  signal use case when `signal_applicable` is False or canonical evidence is
  absent; `AssessSignalEvidenceUseCase` raises `NoProductionSignalEvidenceError`
  otherwise. There is no low-authority fallback score.
* **Regime-adjusted risk stays preview** (ADR-037). The seam does not promote the
  regime gate to authoritative for any scenario.
* **`SignalContext` never adds Setup/Flow authority.** Its enrichment fields feed
  penalty flags, company-quality sub-scores, and presence checks — never the
  weighted Setup/Flow groups, which come entirely from `canonical_evidence`. The
  seam must not treat `SignalContext` as the canonical scoring source.
* **Fetch strategy is application policy.** Self-fetch vs pre-built `GateContext`
  is chosen per scenario in the application layer; adapters never decide it.
* **Adapters stay thin.** CLI wires the seam-backed use case and renders; it owns
  no cache/fetch/risk/signal/composition policy.
* Accum canonical output is unchanged by Phases 0–1 (regression-proven).

### Rationale

* The single-engine goal is already met; the missing piece is a single
  *adoption* pattern, so unifying the seam — not the engines — is the right lever.
* Separating enrichment (generic builder) from authority (scenario canonical
  evidence) lets the cheap, universal win (regime + risk everywhere) ship without
  waiting on the hard, scenario-specific canonical-evidence work.
* Making "channel not applicable" a first-class seam result keeps ADR-041 honest:
  scenarios never fabricate evidence to look complete.

### Implications

* Pre-open gains always-on, non-authoritative regime + risk context; its output
  contract changes (a `screen`/CLI-envelope touch under ADR-046 adopt-on-touch).
* A future fundamental screen implements the same three seam interfaces; because
  it loads analyst/insider/valuation, the generalized enrichment builder populates
  its `SignalContext` side channels — though its authoritative signal still needs
  a canonical setup/flow evidence source of its own.
* Component tests of the pipeline do not prove production wiring; every screen
  composition root that adopts the seam must be named and covered.

### Explicit non-goals

* No change to `SignalEngine`, `RiskEngine`, or `MCE` internals or scoring math.
* No new data providers.
* No pre-open-native canonical (setup/flow) evidence source — deferred.
* No promotion of regime-adjusted risk to authoritative status.
* No change to accumulation canonical output (Phases 0–1 must be byte-identical).
* No AI/model authority changes.

### Agent one-liner

```text
Engines are already single + generic; unify their ADOPTION, not the engines.
Shared ScreenAssessmentPipeline (regime->signal->risk->trade_setup) + per-scenario
SignalInputsBuilder / risk-input choice / ScreenPolicy. Two channels: the weighted
score is 100% canonical_evidence (setup 0.60 + flow 0.40, ADR-041, never fabricated,
may be None); SignalContext is a non-authoritative enrichment bundle (feeds
penalty flags, company-quality sub-scores, presence — not the weighted score).
Signal is a HARD guard: no canonical evidence => do
NOT call the signal use case (it raises NoProductionSignalEvidenceError). Tier-1
regime+risk is self-fetching + universal; Tier-2 signal is evidence-gated. Pre-open
adopts Tier-1 now (signal_applicable=False, mandatory). Accum wrappers refactored
in, clean-break. Regime risk stays preview (ADR-037).
```
