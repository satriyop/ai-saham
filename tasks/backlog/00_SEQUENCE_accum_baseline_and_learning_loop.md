# Sequence: Accum Baseline, Learning Loop, And Operator Surface

Source: code-and-data vet, 2026-08-04, revised the same day after code review
overturned three drafts and produced ADR-067 and ADR-068. All numbers measured against `data/db/data.db` (1.34 GB)
and a live `ml-saham` run.

This file is an **ordering contract**, not a task. The tasks below have hard
dependencies and one operational constraint that makes order load-bearing.

---

## The constraint that drives everything

A cohort can only grow while its identity stays put. `ml-saham`'s `accum_path_v1`
needs 3 folds plus a 20-session embargo **inside one cohort**, so that window is
roughly two months long.

**Today identity is the SHA-256 of the raw text of twelve config files**
(`research_accum_backfill_commands.py:76-115`) plus two hand-typed version
constants. That mechanism over-fires on comments and under-fires on code — which
is why [ADR-068](../../docs/adr/ADR-068-behavioral-engine-identity-for-accum-cohorts.md)
replaces it with measured behaviour, and why its implementation is task 1.

Either way the ordering rule is the same:

> **Every identity-moving change lands first, in one batch. Then one purge and
> rebuild. Then the config freezes and the corpus accumulates.**

Doing this now is free: all four existing cohorts are already unusable (see
Measurements). Doing it two months from now costs two months.

---

## Order

| # | Task | Identity-moving? | Gate |
|---|---|---|---|
| 1 | `01_implement_adr_068_behavioral_engine_identity.md` (**DONE** → `tasks/done/`) | **Yes** | none — ADR-068 accepted 2026-08-04; implemented 2026-08-05 |
| 2 | `02_implement_adr_067_retire_setup_quality.md` (**DONE** → `tasks/done/`) | **Yes** (snapshot payload) | none — completed 2026-08-06, docs closeout 2026-08-07 |
| 3 | `03_fix_risk_gate_silent_skip_and_fundamentals_pit_hole.md` | **Yes** (snapshot payload) | needs 1 |
| 9 | `09_expose_unevaluable_gate_block_provenance.md` | **Yes** (snapshot payload binding) | needs 3; vetted 2026-08-08 |
| — | **── PURGE + REBUILD (task 4), then CONFIG FREEZE ──** | | |
| 4 | `04_rebuild_accum_corpus_single_deep_cohort.md` | No | needs 1, 2, 3, 9 — **mandatory; re-vet after 9** |
| 5 | `05_fix_preopen_directional_score_resolution.md` | pre-open only | independent — **vetted 2026-08-08**; ready when scheduled |
| 6 | `06_implement_accum_policy_proposal_lifecycle.md` | No | needs 4 + depth |
| 7 | `07_improve_screen_accum_progressive_disclosure.md` | No | independent — **vetted 2026-08-08**; safe under accum freeze |
| 8 | `08_fix_cli_error_taxonomy_and_exit_codes.md` | No | independent |

```
┌─ config-edit batch (one identity move, together) ──┐
│  1  ADR-068 behavioural identity  ← must be first  │
│  2  ADR-067 retire setup_quality                   │
│  3  risk gate skips + fundamentals PIT             │
│  9  bind persisted gate audit to snapshots + ML    │
└─────────────────────────┬──────────────────────────┘
                          │  ONE purge + rebuild (task 4)
                          │  then FREEZE CONFIG
                          ▼
                 accumulate ~40 sessions ──► 6 policy lifecycle

  5 pre-open score  ─── independent (pre-open purpose, own mechanism)
  7 compact output  ─── independent
  8 error taxonomy  ─── independent
```

**2026-08-08 task-05 re-vet.** Discrete six-value lookup is still the scorer;
live PRE_OPEN corpus (29 rows) shows confidence **always LOW** because
`iev_intensity` never reaches `min_normalized_iev_intensity=1.0` (100% of scored
rows). NCP “low fraction” is largely top-50 lock-window ops coverage, not only a
sticky-flag bug. ml-saham directional n=0 is multi-cause (explicit
`compatibility_id` + `--baseline static_reference` required). Continuous score
must not preserve the unreachable intensity boolean; PRE_OPEN clean-break is
cheap and must not touch the frozen accum cohort.

**2026-08-08 task-07 re-vet.** Single-window `display_results` still prints a
default nested panel wall; `--full`/`--detail` do **not** gate that wall
(`--detail` only adds Run Context; `--full` adds diagnostic bags). Multi-window
`display_multi` is already compact. Why-line `setup_evidence` leak is mostly
fixed in shared `decision_display`; residual identifier audit remains. Safe
adapter-only work under the accum freeze.

**Why ADR-068 goes first.** It deletes `SEMANTIC_ENGINE_VERSION` and
`EVIDENCE_CONTRACT_VERSION`, which task 2 would otherwise bump and then lose. It
builds the probe set task 2 needs as its gate. And it turns task 2's screen
NON_SEMANTIC claim from an assertion into a measurement — the probe digest
staying identical *is* the proof.

**One purge, not three.** ADR-067 alone needs none (NON_SEMANTIC on screen);
ADR-068 does. Task 4 is the single purge for the whole batch.

Tasks 5, 7, 8 do not move accum identity and may run at any time, including
during the freeze.

**2026-08-08 task-09 re-vet.** The original draft incorrectly said the risk
audit was absent from storage. Current canonical observations already persist
`risk.unevaluable_gates` and `risk.gate_evaluations`; the remaining fix binds
those paths into two ADR-059 snapshot payloads and teaches ml-saham to consume
them. Snapshot payload changes move the ADR-068 compatibility ID, so task 09 is
now part of the pre-rebuild identity batch.

**2026-08-08 task-04 executed.** Single deep cohort rebuilt under
`sha256:355e5b59600dbdc9f762f7b373e8879b7cda9a1e55e18bd590461315cfe1e091`
(schema **15**, `production_policy_snapshot.v4` ×9, task-09 risk-audit bindings).
Range `2026-07-08`→`2026-08-07`, 23 sessions, 1035 observations. ml-saham health
is **BLOCKED_DATA** (cannot form time folds / short embargo depth). **Config
freeze is now in effect** until a deliberate identity-moving batch.

**2026-08-09 corpus-growth re-vet and GROW-01/GROW-02 close.** ai-saham now
accepts the canonical writer's decimal-text `shared.current_price` through one
symmetric application contract. Read-only status recovered all 1,035 rows, 23
sessions, and the existing labels without schema/identity movement or row
rewriting; producer status is **`CHALLENGE_INPUT_READY`**. The application report
now owns an explicit operational-success predicate, and the cron wrapper uses
the CLI's `--require-operational-success` gate so `BLOCKED_POLICY` cannot emit
`COMPLETION_OK`. The contextual commit is complete and the corpus-growth task is
now `CODE_COMPLETE_AWAITING_DATA`. ml-saham's separate `BLOCKED_DATA` remains a
protocol-depth result and does not overrule the producer status.

**2026-08-09 OOS-protocol follow-up.** Task 06 must not unblock merely when the
current `accum_path_v1` first emits two folds. The cross-repository task
`vet_ml_accum_oos_protocol_before_policy_lifecycle.md` records a confirmed
row-based thin-calendar fallback, row-count rather than session-count
sufficiency gates, pooled ticker-row IC without session-aware uncertainty, and
the absence of a final confirmation holdout. Corpus growth continues in
parallel, but policy-proposal eligibility requires the vetted, versioned
ml-saham protocol follow-up first.

---

## Three drafts were retired — do not implement any of them

Two are archived in `tasks/done/` as reasoning records; one was deleted. None is
work. Do not recreate them.

| Retired draft | Where it is | Why it went | Reasoning now lives in |
|---|---|---|---|
| `reduce_accum_cohort_identity_blast_radius.md` | deleted | Obsoleted by ADR-068 — trimming which config files count as identity is moot once config files are not identity material. Its fork-warning slice was salvaged. | ADR-068 §Context; task 01 slice 5 |
| `fix_accum_setup_quality_evidence_gap.md` | `tasks/done/` | False premise: `setup=None` on discovery is intentional design (ADR-054; `--setup` is DIAGNOSTIC, `screen_accum_commands.py:170-178`). Attaching would have been an ADR-057 promotion. | ADR-067 §Context; task 1 |
| `narrow_accum_cohort_fingerprint.md` | `tasks/done/` | Targeted the wrong hash. `_CONFIG_HASH_FIELDS` is **write-only** — one writer, and its only reader is guarded on `candidate_observations`, a table dropped in the 2026-07-27 clean break. Real identity was `resolve_lean_semantic_compatibility_id` over raw file bytes — now replaced entirely. | ADR-068 §Context |

---

## Measurements

**Evidence group presence** (7,764 accum window-observations):
`setup_quality` **0/7,764** · `institutional_flow` 7,764/7,764 ·
`sector_context` 0/7,764 · `company_quality_context` 0/7,764.

**Action distribution:** AVOID 2,541 (32.7%) · BLOCKED_STRUCTURAL 1,854 (23.9%) ·
WATCH 1,801 (23.2%) · BLOCKED_EXECUTION 1,545 (19.9%) · **ENTER 23 (0.3%)**.
Only 206/7,764 (2.7%) reach signal ≥ 70.

**Gate skips:** FundamentalGate 4,299 (55.4%) · FreeFloatGate 2,280 (29.4%) ·
BandarGate 1,437 (18.5%). Root cause: `piotroski_f_score` and `market_cap_idr`
are NULL in 8,541/9,014 `company_fundamentals` rows (94.7%), present only from
2026-07-08. Blocks themselves are legitimate and numerically evidenced — the
defect is silent skips, not over-blocking.

**Cohorts — none holds value, which is why forking now is free:**

| compatibility_id | obs | sessions | snapshots | ml-saham verdict |
|---|---|---|---|---|
| `0053…` | 1,890 | 42 | 0/7 | ineligible |
| `5898…` | 349 | 1 | 6/7 | `BLOCKED_POLICY` |
| `8ba8…` | 304 | 1 | 7/7 | `INCONCLUSIVE` (1 fold) |
| `6493…` (live) | 45 | 1 | 7/7 | `BLOCKED_DATA`, n=0 |

**Learning loop:** `learning_policy_proposals`, `_validations`, `_applications`
hold **0 rows each, ever**. The swing lifecycle that would populate them is fully
built, rigorously gated, and in no cron entry.

**Market data is not the constraint:** `candles` 82,649 rows / 320 tickers /
2025-07-07 → 2026-08-03 — roughly 13 months against a 42-session corpus.

**Pre-open:** `directional_score` is a six-value lookup → mass ties → n=0 in
challenge, while continuous `iev_rank` returns n=695. Only 620/2,620
`iev_snapshot_history` rows are NCP-locked. Corpus is 19 observations; latest
evaluation n=17, `average_return_pct` +0.156%.

---

## Deferred — do not start yet

**Recalibrating `strong_min_score`.** ADR-067 retires `setup_quality` but is
NON_SEMANTIC on screen, so the 0.3% ENTER rate survives it. The threshold is a
hand-set number defending a blended score that is never computed. Fixing it is
the first real question for task 6, once task 4 gives the challenge lab
something to answer with. **Not a hand-edit.**

**Re-weighting the accum sleeves.** The only ablation on file
(`research/artifacts/factor_card_accum_components_2026-07-22.md`) suggests the
weights are mis-ordered — `consistency` carries the largest weight (33.3) at
corr +0.003, `vwap_discount` (16.7) at corr +0.242, `rsi_headroom` at corr
−0.207, opposite its weight sign. Not actionable: that artifact was built on
tables deleted in the 2026-07-27 clean break and is not reproducible. Second
question for task 6.

---

## Standing rules

- Clean break over compatibility shims. No aliases, no dual-scale support, no
  rotten code or decorative config left behind for old data.
- Each slice is one commit and leaves the repo green.
- Engine-material changes state in the commit message that they change what can
  produce ENTER/WATCH/AVOID.
- Lint Gate (`ruff check src/ tests/`, `ruff format --check src/ tests/`) before
  any task closes.
- No task loosens a threshold to make a metric look better. Route it through
  task 6 with evidence.
- **Trust code over docs.** Three separate claims in this effort — `--setup`
  being production, `_CONFIG_HASH_FIELDS` controlling cohorts, the evidence
  blender being general — were true in documentation and false in code.
