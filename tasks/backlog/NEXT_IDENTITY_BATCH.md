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
| IB-1 | Demote the `setup_quality` Alpha/Trigger slot to `DIAGNOSTIC` | **READY** | Yes | nothing |
| IB-2 | Recalibrate `strong_min_score` | `BLOCKED` | Yes | task 06; needs ml-saham evidence, which needs corpus depth |
| IB-3 | Re-weight the accum sleeves | `BLOCKED` | Yes | task 06; source ablation not reproducible |
| IB-4 | Promote `sector_context` / `company_quality_context` to present evidence | `NEEDS DESIGN` | Yes | ADR-057 promotion guardrails; `parked_evidence_promotion_lane.md` |

---

### IB-1 — Demote the `setup_quality` Alpha/Trigger slot to `DIAGNOSTIC`

**State:** `READY`. Decision taken 2026-08-11.

ADR-067 retired `setup_quality` as an *evidence group* — `config/signal_engine.yaml`
`evidence_groups` now holds only `flow_confirmation`, and the resolver rejects a
re-added key. That part is complete and correct.

The Alpha/Trigger **projection slot** of the same name survives, and it is not
covered by that retirement. It declares `group_weights.setup_quality: 0.35`
(`config/signal_engine.yaml:131`) with **no `evidence_registrations` entry**, so
its status resolves from the typed default at
`src/application/services/signal_engine_config.py:354-357` — `PRODUCTION`.

A group that is `PRODUCTION` but never present holds production weight hostage.
Measured across all **3,375** window-observations of the live frozen cohort
`sha256:355e5b…` (25 sessions, 2026-07-08 → 2026-08-11):

| Measurement | Value |
|---|---|
| `coverage` | **0.30 on 3,375/3,375** — zero variance |
| `trigger_score` | **null on 3,375/3,375** |
| `unavailable_reasons` | `trigger:no_production_weight` on 3,375/3,375 |
| `setup_quality` present | **0/3,375** (weight 0.35, `PRODUCTION`) |
| `institutional_flow` present | 3,375/3,375 (weight 0.30, `PRODUCTION`) |
| `sector_context` present | 0/3,375 (weight 0.25, `DIAGNOSTIC`) |
| `company_quality_context` present | 0/3,375 (weight 0.10, `DIAGNOSTIC`) |
| `final_exact_score` | 4.96–80.00, μ 40.93, σ 15.64; ≥70 → 132/3,375 |

Two distinct consequences, worth separating:

1. **The trigger leg never resolves.** `trigger:no_production_weight` fires
   because the only other `PRODUCTION` group, `institutional_flow`, is
   `trigger_allowed: false` in the sampled rows. The emitted score is the alpha
   leg alone; `trigger_weight: 0.6` is declared and never applied.
2. **`coverage` carries zero information.** A feature constant at 0.30 across an
   entire corpus cannot discriminate anything downstream in ml-saham. It is
   payload width with no signal.

Note what is **not** claimed: the score itself still varies (σ 15.64), so
`institutional_flow` alone does discriminate. The cohort is not worthless — it
is a 1-of-4 evidence engine whose second scoring leg is switched off.

**Decided fix:** add an explicit `evidence_registrations.setup_quality` entry
with `status: DIAGNOSTIC`, so the slot stops claiming production weight and the
trigger leg resolves against the groups that are actually present. Preferred
over deleting the slot because it is the smallest change, it is reversible, and
it keeps the return path open if a producer is ever built.

**Task:** to be written against `TASK_TEMPLATE.md` before implementation.

**Verification required before the batch closes:**

- probe digest / `compatibility_id` recomputed and recorded;
- post-rebuild re-measurement of the table above — `trigger_score` must be
  non-null on a non-trivial fraction, and `coverage` must show variance;
- corpus continuity confirms the rebuild restored every session in
  2026-07-08 → rebuild date with no holes.

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
