# Register — Next ACCUM Identity Batch

Status: `OPEN REGISTER` — this is a **coordination artifact**, not a task.
Opened 2026-08-11.

Sequence contract: [`00_SEQUENCE_accum_baseline_and_learning_loop.md`](00_SEQUENCE_accum_baseline_and_learning_loop.md)

---

## Why this file exists

The sequence contract's standing rule is:

> **Every identity-moving change lands first, in one batch. Then one purge and
> rebuild. Then the config freezes and the corpus accumulates.**

Until now nothing collected the *candidates* for that batch. They arrived
ad-hoc, which is how the 2026-08-08 rebuild ended up needing tasks 1, 2, 3 and 9
to be discovered one at a time. This register is the queue: an identity-moving
change is added here when it is identified, and the batch executes when the
`READY` set justifies one purge.

**Nothing in this file is implemented by editing this file.** Each entry names
its own task.

---

## The economics, measured

An identity move costs **one backfill run, not lost calendar time.**

`saham research accum signal-backfill-observations --universe lq45 --start … --end …`
(`src/adapters/cli/research_accum_backfill_commands.py:327`) regenerates
observations from stored market data. It rebuilt 23 sessions on 2026-08-08.

So the accum corpus is **replayable back to 2026-07-08** — the honest
point-in-time fundamentals floor (`docs/data_fundamentals_pit_depth.md` §4).
That floor, not the freeze, is the real depth ceiling.

Consequence for scheduling: the freeze is **batching discipline, not a calendar
lock**. Waiting does not preserve depth; it only accumulates more sessions under
whatever engine is current. Batch when the `READY` set is worth a rebuild, and
do not defer a `READY` identity fix on the mistaken belief that it costs
sessions.

---

## Register

| # | Change | State | Identity-moving | Blocked by |
|---|---|---|---|---|
| IB-0 | Extend the ADR-068 probe projection to cover the Alpha/Trigger surface | **READY** | Yes | nothing |
| IB-1 | ~~Demote the `setup_quality` Alpha/Trigger slot to `DIAGNOSTIC`~~ | **WITHDRAWN — measured inert** | No | — |
| IB-1b | Remove permanently-absent groups from `alpha_trigger.group_weights` | `NEEDS IB-0` | Yes, but **invisible** to the current mechanism | IB-0 |
| IB-2 | Recalibrate `strong_min_score` | `BLOCKED` | Yes | task 06; needs ml-saham evidence, which needs corpus depth |
| IB-3 | Re-weight the accum sleeves | `BLOCKED` | Yes | task 06; source ablation not reproducible |
| IB-4 | Promote `sector_context` / `company_quality_context` to present evidence | `NEEDS DESIGN` | Yes | ADR-057 promotion guardrails; `parked_evidence_promotion_lane.md` |

---

### IB-0 — Extend the ADR-068 probe projection to the Alpha/Trigger surface

**State:** `READY`. Identified 2026-08-12 while attempting IB-1.

The cohort identity's code axis is `compute_behavioral_probe_digest()`, which
digests `{probe_id -> canonical output projection}`. That projection
(`behavioral_probe_runner._project_candidate`) carries `accum_score`,
`signal_score`, `signal_breakdown`, `signal_authority_coverage`, the decision
constraints, setup phase/readiness, and the risk gates.

It carries **no Alpha/Trigger field at all** — measured by running the probe set
and searching the projection: `alpha_trigger` absent, `evidence_status` absent,
`group_contributions` absent, `trigger_score` absent. (`coverage` matches only
`signal_authority_coverage`, a different quantity.)

Persisted observations **do** carry that surface:
`decision_payload.features_by_window.*.signal.alpha_trigger_score` holds
`coverage`, `trigger_score`, `authority_coverage`, and per-group
`evidence_status` / `configured_weight` / `effective_weight`.

So there is a class of change that alters **every recorded observation** while
leaving `compatibility_id` fixed. Old and new rows would pool under one cohort
with different feature semantics, which is exactly the contamination ADR-068
exists to prevent. ADR-068 anticipated this — "probe coverage remains a measured
floor, not a proof of behavioural equivalence" — and this is a concrete instance.

**IB-1b must not land before this.** Extending the projection is itself
identity-moving (the probe digest changes), so it belongs in a batch.

Open design question: whether the whole `alpha_trigger_score` belongs in the
projection, or only the fields ml-saham consumes as features. The projection's
docstring says it deliberately excludes "diagnostic-only enrichment", and
Alpha/Trigger *is* a diagnostic projection — so a blanket include would
contradict that principle. The narrower question is which diagnostic fields
are corpus features, because those are the ones whose drift must fork a cohort.

---

### IB-1 — Demote the `setup_quality` Alpha/Trigger slot to `DIAGNOSTIC`

**State:** `WITHDRAWN`. Attempted 2026-08-12, measured inert, config reverted.
No purge was performed.

The original entry claimed the slot's `PRODUCTION` status held production weight
hostage and was the cause of the null trigger leg. **Both claims were wrong**,
established by running the real `AlphaTriggerAggregator` over the production
group shape (institutional_flow present at 49.83, other three absent) under both
statuses:

| | `PRODUCTION` | `DIAGNOSTIC` |
|---|---|---|
| `final_exact_score` | 49.83 | 49.83 |
| `alpha_score` | 49.83 | 49.83 |
| `trigger_score` | `None` | `None` |
| `coverage` | 0.30 | 0.30 |
| `authority_coverage` | 0.24 | 0.24 |
| `unavailable_reasons` | incl. `trigger:no_production_weight` | identical |
| `effective_weight` | 0.0 | 0.0 |
| `evidence_status` | `PRODUCTION` | `DIAGNOSTIC` |

Only the recorded label changes. The mechanism is
`alpha_trigger_aggregator.py:110-130`: a group that is not `present` takes an
early branch that hardcodes `effective_weight=0.0` and `continue`s, so it never
reaches `alpha_den` / `trigger_den`. A never-present group cannot hold weight
hostage because it never contributes weight in the first place.

The cohort identity correctly did **not** move (`sha256:355e5b…` before and
after, all three parts identical). The decision surface genuinely did not change.

Landing it anyway would have written `evidence_status: DIAGNOSTIC` rows into a
cohort whose existing rows say `PRODUCTION`, with no identity move to separate
them — a within-cohort inconsistency for no benefit.

**Why the trigger leg is actually null.** It is phase-gated by design, not
broken. `AlphaTriggerAggregator`'s own contract: the institutional-flow trigger
contribution is routed "only when setup phase is BREAKOUT_CONFIRMATION and flow
confirmation status is CONFIRMED". An accumulation *discovery* screen sits
pre-breakout by construction — measured across the frozen cohort, setup phase is
`DISTRIBUTION` 2,796 · `ACCUMULATION` 376 · `COMPRESSION` 327 · `FAILED` 287 ·
`EXHAUSTION` 12 · `NONE` 29 · **`BREAKOUT_CONFIRMATION` 8**. A near-always-null
trigger score on this corpus is the design working, not a defect.

---

### IB-1b — Remove permanently-absent groups from `alpha_trigger.group_weights`

**State:** `NEEDS IB-0`.

The surviving real finding from the 2026-08-11 measurement: `coverage` is
**0.30 on 3,375/3,375 window-observations, with zero variance**. A feature
constant across an entire corpus carries no information for ml-saham.

The cause is not evidence status. `coverage` is
`configured_available_weight / configured_required_weight`, and
`configured_required_weight` sums the `group_weights` of **all four** groups
(1.00) while only `institutional_flow` (0.30) is ever available. Registration
status never enters that formula — only `configured_weight` does.

Measured with the real aggregator:

| `group_weights` contents | `coverage` | `final_exact_score` |
|---|---|---|
| all four groups (today) | 0.30 | 49.83 |
| without `setup_quality` | 0.4615 | 49.83 |
| `institutional_flow` only | 1.00 | 49.83 |

Note the score is unchanged in every case — this moves the recorded coverage
feature, not the decision.

**And that is precisely why it is dangerous today.** The change is invisible to
the cohort identity (see IB-0), so it would silently repoint a recorded feature
inside a live cohort. Sequence: IB-0, then this, then one purge + rebuild.

Open question before it becomes `READY`: whether a permanently-absent group
*should* count toward required coverage. Keeping it means "we know we are
missing 70% of designed evidence"; removing it means "coverage measures what we
actually attempt". Those are different claims and only one can be true at a time.

---

### IB-2 — Recalibrate `strong_min_score`

**State:** `BLOCKED` — do not hand-edit.

Carried over from the sequence contract's Deferred section. `strong_min_score`
is a hand-set threshold defending a blended score that is never computed. The
0.3% ENTER rate measured on the pre-purge corpus survived ADR-067 because that
ADR is NON_SEMANTIC on screen.

Blocked on task 06 (`06_implement_accum_policy_proposal_lifecycle.md`), which is
itself blocked on corpus depth and on the ml-saham OOS protocol follow-up. The
sequence contract's standing rule applies: **no task loosens a threshold to make
a metric look better.** Route it through task 06 with evidence.

Note IB-1 changes the score's composition, so any IB-2 measurement taken before
IB-1 lands is void.

---

### IB-3 — Re-weight the accum sleeves

**State:** `BLOCKED`.

The only ablation on file
(`research/artifacts/factor_card_accum_components_2026-07-22.md`) suggests the
weights are mis-ordered: `consistency` carries the largest weight (33.3) at
corr +0.003, `vwap_discount` (16.7) at corr +0.242, and `rsi_headroom` sits at
corr −0.207, opposite its weight sign.

**Not actionable as evidence** — that artifact was built on tables deleted in
the 2026-07-27 clean break and is not reproducible. It is a hypothesis to
re-derive under task 06, not a finding to act on.

---

### IB-4 — Promote `sector_context` / `company_quality_context`

**State:** `NEEDS DESIGN`.

Both groups are configured slots at `DIAGNOSTIC` with weights 0.25 and 0.10, and
both are present in **0/3,375** window-observations.

Correcting a likely misreading: **the producers already exist and already emit.**
The frozen cohort's `decision_payload.diagnostic_bindings` carries
`diagnostic.company_quality_context` and the sector `peer_context` binding, each
with a real `payload_digest` and `snapshot_id`. The data is being produced and
persisted; it is simply not wired into the Alpha/Trigger evidence path as
`present`.

So this is **not** a data-acquisition problem. It is an evidence-promotion
decision, and promotion is exactly what ADR-057 and the parked evidence
promotion lane (`parked_evidence_promotion_lane.md`) govern. Diagnostic evidence
must not become authoritative without those guardrails —
`CLAUDE.md` §5 states this as non-negotiable.

Design questions to answer before this can become `READY`:

- what promotion evidence justifies moving either group to `PRODUCTION`;
- whether promotion happens per-group or as a set;
- how the 0.35 freed by IB-1 is reallocated, if at all.

This is the highest-upside entry in the register — it is the difference between
a 1-of-4 and a 3-of-4 evidence engine — and the one most likely to be got wrong
by acting before the guardrails are designed.

---

## Batch execution rule

When the batch runs:

1. Land every `READY` entry as its own commit, config changes together.
2. Record the new `compatibility_id` in `00_SEQUENCE`.
3. **One** purge + backfill rebuild covering 2026-07-08 → today.
4. Verify continuity has no holes before declaring the batch closed.
5. Re-freeze; move closed entries out of this register.
