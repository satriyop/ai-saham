# ADR-067: Retire `setup_quality`; one evidence basis for accum judgment; plan does not judge

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted

**Date:** 2026-08-04

**Implementation task:**
[`tasks/done/02_implement_adr_067_retire_setup_quality.md`](../../tasks/done/02_implement_adr_067_retire_setup_quality.md)

**Ordering:** [ADR-068](ADR-068-behavioral-engine-identity-for-accum-cohorts.md)
lands first. It replaces cohort identity with measured behaviour, so this ADR
needs no hand-typed version bump — deleting the `setup_quality` config block
moves the ADR-059 snapshot payload digest and forks the cohort automatically.
The identity blast-radius concern in this ADR's Consequences is fully resolved
by ADR-068; no separate trimming task is needed.

**Amends:** [ADR-054](ADR-054-screen-judge-plan-structure-contract.md) (§1 verb
jobs, §7 phasing), [ADR-030](ADR-030-accumulation-screener-evidence-split.md)
(evidence group set)

**Depends on:** [ADR-041](ADR-041-canonical-signal-evidence-input-boundary.md),
[ADR-057](ADR-057-evidence-diagnostic-evidence-corpus-vocabulary.md),
[ADR-058](ADR-058-setup-phase-ledger-production-memory.md),
[ADR-059](ADR-059-production-policy-snapshot-for-ml-challenges.md),
[ADR-062](ADR-062-retire-accum-group-breadth-production-bonus.md) (precedent)

**Does not change:** RiskEngine gate thresholds, MarketContextEngine, the
evidence-promotion lifecycle, learning table contracts, pre-open paths.

---

## Context

ADR-054 froze the product slogan:

> **Screen finds and judges candidates.**
> **Plan designs the trade structure of a chosen candidate.**

The implementation does the opposite. Measured 2026-08-04 against
`data/db/data.db`:

| Surface | ADR-054 job | Attaches `setup_quality`? | Emits an action? |
|---|---|---|---|
| `screen accum --universe` (board) | find | No (`accumulation_candidate_signal_assessor.py:244`, `setup=None`) | Yes |
| `screen accum TICKER` (judgment) | **judge** | **No** — same assessor | Yes |
| `plan swing TICKER` | structure | **Yes** (`plan_swing_decision_composer.py:352`) | Yes |

The judgment surface judges on the flow group alone. The structure surface —
which ADR-054 says must not be "a second independent ENTER/WATCH/AVOID story" —
is the only surface carrying the 0.60-weight `setup_quality` group.

### Measured facts

- `setup_quality` is present in **0 of 7,764** accum window-observations.
  `institutional_flow` is present in 7,764/7,764. `sector_context` and
  `company_quality_context` are present in 0/7,764 (both DIAGNOSTIC).
- Observation purposes in the database are exactly `ACCUMULATION_DISCOVERY` and
  `PRE_OPEN_AUCTION_DIRECTION`. **There is no plan/swing observation purpose.**
  `plan_swing_workflow_use_case.py:108` takes a `LearningObservationRepository`
  as a reader only.
- Therefore `setup_quality` — the largest single weight in the signal engine —
  has never entered the corpus and **cannot be challenged, validated, or tuned
  by any mechanism that exists**.
- Its scoring rule is a three-value lookup: `MATCH → 100`, `PARTIAL → 60`,
  `NO_MATCH → 20`.
- `config/signal_engine.yaml` declares `setup_quality: 0.60` /
  `flow_confirmation: 0.40` and `classification.strong_min_score: 70` → ENTER.
  Because setup is never attached on screen, `_blend` renormalizes to the flow
  group alone, so a threshold calibrated for a blended score is applied to an
  unblended one. Observed result: ENTER on 23/7,764 (0.3%); only 206/7,764
  (2.7%) reach signal ≥ 70.
- The declared `0.60/0.40` split has no effect on any value the screen produces.
  It is decorative configuration, and it actively misleads readers of the config
  — including agents auditing this repository.

### The standard applied retroactively

`AGENT_QUICKSTART.md` requires point-in-time out-of-sample validation before
anything gains evidence authority. `setup_quality` has zero corpus presence, no
capture purpose, no challenge result, and no ablation. **Proposed today as a new
production evidence group, it would be rejected.** It survives only because it
predates the standard. That is grandfathering.

---

## Decision

### 1. Retire `setup_quality` as a production evidence group

Remove the group, its weight declaration, and the code that blends it:

- `config/signal_engine.yaml` — remove the `setup_quality` evidence-group
  weight, its `evidence_registrations` entry, `decision_policy.weak_setup_threshold`,
  and `decision_policy.weak_setup_discount`.
- `signal_evidence_group_scorer.py` — remove the two-name blend
  (`total_weight = g.setup_quality.weight + g.flow_confirmation.weight`), the
  absent-group renormalization it exists to support, and the hardcoded
  `name="setup_quality"` authority-fact entry.
- `plan_swing_decision_composer.py:352` — remove the only live attachment site
  (see decision 3).

`flow_confirmation` becomes the sole production evidence group on the accum
path. The signal score **is** the flow group score. No weights, no
renormalization, no absent-group handling remains.

**The blending abstraction is deleted, not preserved as a seam.** It is not
general machinery — it is hardcoded to two named groups. Keeping it would keep
the literal name `setup_quality` alive in scoring code with nothing behind it,
which is the precise failure mode this ADR exists to remove. A future
multi-evidence mechanism must be designed against real promoted evidence, not
guessed at now.

### 2. Board and ticker share one verdict; both may emit ENTER

`screen accum --universe` and `screen accum TICKER` compute the same production
evidence and the same action. `screen accum TICKER` deepens **display**, never
**evidence**.

This follows necessarily from decision 1: with `setup_quality` retired and every
deep flag (`--setup`, `--with-flow-detail`, `--with-sentiment`, `--full`)
already DIAGNOSTIC under ADR-057, the ticker path has no additional production
evidence over the board. A WATCH-max board would force a second command that
returns an identical answer.

### 3. `plan swing` does not judge

`plan swing` designs trade structure — horizon, invalidation, profit-taking,
R:R geometry, sizing. It does not build a `CanonicalSignalEvidenceInput`, does
not compute a signal score, and does not derive its own action. It **carries
forward** the verdict `screen` produced.

This completes ADR-054 §7's phased split rather than amending its intent.

### 4. Setup concepts that survive untouched

Retirement is surgical. `setup_quality` is one of four distinct concepts:

| Concept | Status | Authority |
|---|---|---|
| setup **phase** (`setup_phase_ledger`, ADR-058) | **survives** | production memory; DecisionPolicy phase caps unchanged |
| setup **family** | **survives** | board column, policy matrix |
| setup **phase readiness** — adverse branch (DISTRIBUTION/FAILED → AVOID, EXHAUSTION → WATCH cap) | **survives** | evidence-free by construction |
| setup **phase readiness** — remaining branches (READY / INCOMPLETE / phase-membership) | **already unreachable** | require `SetupEvidence`; see amendment below |
| setup **quality** (MATCH/PARTIAL/NO_MATCH → 100/60/20, weight 0.60) | **retired** | — |

`--setup` remains available as a **diagnostic** lens on explicit tickers, with
its existing `MATCH ≠ ENTER` semantics. Nothing about it changes.

#### Amendment 2026-08-04 — readiness precision

The original text of this section claimed setup phase readiness "survives —
phase-derived, not quality-derived." That was too strong and is corrected here.

`SetupPhaseReadinessEvaluator.evaluate`
(`setup_phase_readiness_evaluator.py:28-110`) takes `setup_evidence` as a
required input. Its precedence order splits cleanly:

- **Rules 1–3** — missing family → `None`; DISTRIBUTION/FAILED → INELIGIBLE;
  EXHAUSTION → INELIGIBLE. These run **before** the evidence check and are
  explicitly documented to dominate absent evidence. They are unaffected by this
  ADR, and they are what feeds the DecisionPolicy phase caps.
- **Rule 4** — `setup_evidence is None` → UNAVAILABLE.
- **Rules 5–13** — read `setup_evidence.can_enter_from_phases`, `setup_match`,
  and `entry_authority`. **Every path to READY or INCOMPLETE passes through
  them.**

Measured across all 7,764 accum window-observations: 7,379 `None` (no setup
family), 201 INELIGIBLE (rules 2–3), 184 UNAVAILABLE (rule 4), **0 READY, 0
INCOMPLETE**. READY has never occurred and is structurally unreachable while
setup evidence is absent on the screen path.

Therefore this ADR does not *cause* the collapse — it is already the status quo,
which is why the NON_SEMANTIC claim in §8 still holds. What the ADR does is make
it permanent and honest.

**Required resolution (revised).** The implementation must:

1. Stop rendering `setup readiness UNAVAILABLE (missing: setup_evidence)` — it
   leaks a code identifier and states an absence that is now by design.
2. Decide and record explicitly **whether the readiness evaluator continues to
   receive `SetupEvidence` at all**. If it does — from the diagnostic lens or
   any other path — then setup evidence retains a route to Action through
   readiness → DecisionPolicy caps, which would be production authority through
   a side door and contradicts §1. The default and recommended answer is **no**:
   readiness on the accum path resolves through rules 1–4 only.
3. Preserve rules 1–3 behavior bit-identically (test).

### 5. This is a code change, not a corpus clean break

**No purge. No re-capture. No backup dance.**

Because `setup_quality` is never attached on the screen path, no score, gate,
action, or ordering changes there. Existing observations are numerically
identical to what the post-change engine would produce. Purging them would
destroy sound data to fix nothing.

Old rows remain readable historical corpus under their existing cohorts.

### 6. The cohort fork is accepted, not avoided

Cohort identity is computed from the **raw text** of twelve config files
(`research_accum_backfill_commands.py:76-115`; the canonical string is
`Path(rel_path).read_text()` per file, hashed by
`resolve_lean_semantic_compatibility_id`). The mechanism has no semantic model:
editing a comment forks the cohort. There is no "prove nothing changed" path,
and this ADR does not invent one.

Editing `config/signal_engine.yaml` therefore mints a new `compatibility_id`.
That is accepted here because **no cohort currently holds value**: the largest
(1,890 obs / 42 sessions) has zero ADR-059 snapshots and is already ineligible;
the others hold 349, 304, and 45 observations from a single session each and
return `BLOCKED_POLICY` / `INCONCLUSIVE` / `BLOCKED_DATA`. Forking today costs
nothing.

The expensive fork is a future one, after real session depth accumulates.
Reducing that blast radius is out of scope here and is tracked separately
(see Consequences).

### 7. Identity and schema lock

**Historical decision record (as written at acceptance).** Current cohort
identity is **[ADR-068](ADR-068-behavioral-engine-identity-for-accum-cohorts.md)**
(behavioral probe digest + ADR-059 snapshot payload digest + payload schema
version). Current active snapshot producer is **ADR-059 v4**. Do not re-apply
config-byte / hand-typed version rules below as live eligibility law.

- `ACCUMULATION_OBSERVATION_PAYLOAD_SCHEMA_VERSION` **12 → 13**. Schema-12 rows
  stay historical and must not be claimed to share a cohort with schema-13.
- At decision time: `EVIDENCE_CONTRACT_VERSION` and `SEMANTIC_ENGINE_VERSION`
  bumps were planned as identity material; **ADR-068 deletes those hand-typed
  versions from cohort identity** in favour of measured behaviour.
- Lean contract ID remained `lean_accumulation_compatibility.v2` at decision.
  As in ADR-062, "contract unchanged" does **not** mean compatibility values
  stay equal.
- At decision time: `production_policy_snapshot.v2` was the closed seven-row set;
  weight payload retained `signal.accum.evidence_group_weights` with a single
  production evidence basis. **Active challenges now require ADR-059 v4** (still
  no reintroduction of retired groups; see ADR-059).

### 8. Golden equivalence gate

Screen-path scoring is claimed **NON_SEMANTIC**. That claim must be *proven*,
not asserted.

Use an offline deterministic synthetic fixture — not a live LQ45 run. Freeze
ordered tickers, inclusion/exclusion, Accum/Signal/Risk/Action/readiness
projections, and the final serialized projection excluding nondeterministic
timestamps. Before and after must be identical. A real dated screen may be
supplementary evidence only.

If the golden gate shows any screen-path movement, the NON_SEMANTIC claim is
false and decision 5 must be revisited before merge.

---

## Do Not Interpret This As

- permission to change `classification.strong_min_score`, `moderate_min_score`,
  or any RiskEngine threshold in this ADR;
- a claim that retirement improves the 0.3% ENTER rate — it does not; screen
  scoring is unchanged by construction (see Consequences);
- permission to retire setup **phase**, **family**, or phase-derived
  **readiness**;
- permission to remove `--setup` as a diagnostic lens;
- permission to promote `sector_context` or `company_quality_context` to fill
  the vacated slot — they remain DIAGNOSTIC and require the ADR-057 lifecycle;
- permission to purge, rebuild, or relabel any existing observation;
- permission to preserve a compatibility path, alias, or dual-profile mode for
  the retired group;
- a claim that schema-12 and schema-13 observations share one cohort;
- permission to weaken the ADR-059 closed snapshot set (then seven-row v2; now
  active **v4** per ADR-059 — still exact, still no retired-group resurrection).

---

## Consequences

**The 0.3% ENTER rate survives this ADR.** Retirement is NON_SEMANTIC on screen,
so no score moves. What changes is that the rate becomes *legible and fixable*:
every input the engine uses is then represented in the corpus, so
`strong_min_score` becomes tunable through a validated proposal path instead of
remaining a hand-set number defending a blended score that is never computed.
Recalibrating it is explicitly deferred and must not be hand-edited.

**The signal engine has one production evidence group.** This is honest rather
than diminished — it is already true in practice on both screen surfaces. Future
breadth comes from ADR-057 promotion of real, measured evidence.

**`plan swing` loses its signal panel as an independent verdict.** Operators who
read plan output as the deep judgment must run `screen accum TICKER` for
judgment and `plan swing` for structure. This is the ADR-054 workflow, now
actually enforced.

**Entry decisions remain outside the learning loop.** With one shared verdict,
board observations now faithfully represent what the engine decides — an
improvement. But no capture purpose records post-judgment operator behavior.
This ADR names the gap and does not close it.

**Cohort identity blast radius (pre-ADR-068 concern).** This section described
the config-byte identity problem that motivated trimming identity-material
files. **Resolved by ADR-068:** cohort identity is measured engine behaviour plus
snapshot payload digest, not raw config bytes. See ADR-068 for the current
identity stack; do not reintroduce config-hash cohort forking from this ADR.

**Config edits and corpus windows.** Operational caution remains: material
behaviour changes still fork cohorts under ADR-068 (probe outputs change). Batch
engine-affecting work deliberately relative to challenge windows; verify live
identity helpers rather than this historical blast-radius paragraph.

---

## Verification and implementation pointers

- `src/application/services/accumulation_candidate_signal_assessor.py:243-259`
- `src/application/services/signal_evidence_group_scorer.py:178-193, 240-275`
- `src/application/services/plan_swing_decision_composer.py:352`
- `src/application/services/accumulation_policy_snapshot_payloads.py:166-170`
- `src/domain/value_objects/signal_artifact_schema.py:57`
- `src/domain/value_objects/signal_semantic_contract.py:25,31`
- `src/adapters/cli/research_accum_backfill_commands.py:76-115`
- `config/signal_engine.yaml` — evidence groups, registrations, decision policy
- `docs/evidence_diagnostic_factor_accum.md` §5.2 — update to match

Implementation task:
[`tasks/done/02_implement_adr_067_retire_setup_quality.md`](../../tasks/done/02_implement_adr_067_retire_setup_quality.md)
(6 slices; golden fixture first). It replaces an earlier draft that was written
on the incorrect premise that the absence was a wiring defect; that draft has
been deleted and its reasoning is preserved in §Context above.

Ordering: this task is the first of a three-task **config-edit batch** that must
land before the corpus accumulation window opens. See
[`tasks/backlog/00_SEQUENCE_accum_baseline_and_learning_loop.md`](../../tasks/backlog/00_SEQUENCE_accum_baseline_and_learning_loop.md).
