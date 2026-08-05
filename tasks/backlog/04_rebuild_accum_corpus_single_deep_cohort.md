# Rebuild The Accum Corpus As One Deep, Snapshot-Bound Cohort

Status: `BLOCKED` — requires the whole config-edit batch merged first
(ADR-068 identity, ADR-067 retirement, risk-gate task).

> **Mandatory, not optional (2026-08-04).** ADR-067 alone needs no purge — it is
> NON_SEMANTIC on screen. **ADR-068 does**: cohort identity changes mechanism
> entirely, so every existing observation belongs to a superseded identity
> scheme. This task is now the single purge for the whole batch.
>
> **Purge exactly once.** Do not purge after ADR-068 and again after ADR-067.

Sequence: **4 of 8** — see `tasks/backlog/00_SEQUENCE_accum_baseline_and_learning_loop.md`

## 1. Task Metadata

**Task Title**
Clean-break the accum learning corpus and rebuild it as a single cohort with
enough session depth for `ml-saham` to return a real verdict.

**Task Type**
Ops / clean break (no scoring logic changes)

**Priority**
High — this is the task that makes the learning loop capable of closing.

---

## 2. Problem Statement

The accum learning loop has **never closed once**. `learning_policy_proposals`,
`learning_policy_validations`, and `learning_policy_applications` each hold
**0 rows**, ever.

The proximate cause is corpus shape, not missing machinery. `ml-saham`'s
`accum_path_v1` needs 3 folds with a 20-session embargo inside one cohort; the
deepest cohort with valid ADR-059 snapshots holds **304 observations from a
single calendar date**, which structurally caps it at `INCONCLUSIVE` forever.
The current production cohort holds 45 observations and returns `BLOCKED_DATA`.

Measured 2026-08-04 — **no cohort holds value, which is why ADR-067 and ADR-068
both accept a fork rather than avoiding one**:

| compatibility_id | obs | sessions | snapshots | ml-saham verdict |
|---|---|---|---|---|
| `0053…` | 1,890 | 42 | 0/7 | ineligible (pre-ADR-059) |
| `5898…` | 349 | 1 | 6/7 | `BLOCKED_POLICY` |
| `8ba8…` | 304 | 1 | 7/7 | `INCONCLUSIVE` (1 fold) |
| `6493…` (live) | 45 | 1 | 7/7 | `BLOCKED_DATA`, n=0 |

After the config-edit batch, **every existing accum observation is an artifact
of a superseded engine and a superseded identity scheme** — flow-only scoring,
silently skipped risk gates, proxy-based cohort identity, and a
proxy identity material. They are not comparable to post-batch observations and
must not be mixed with them.

Meanwhile the underlying market data is **not** the constraint:

| Table | rows | tickers | date range |
|---|---|---|---|
| `candles` | 82,649 | 320 | 2025-07-07 → 2026-08-03 |
| `broker_summaries` | 65,453 | 306 | 2025-07-07 → 2026-08-03 |
| `broker_daily_flow` | 513,662 | 303 | 2025-07-07 → 2026-08-03 |

That is roughly **13 months** of history against a corpus currently spanning
42 sessions at best.

---

## 3. Desired Outcome

- Exactly **one** accum `compatibility_id` exists after this task.
- It carries the full 7-row `production_policy_snapshot.v2` set.
- Its session depth is the maximum the data honestly supports, and is
  **≥ 3 folds + 20-session embargo** so `ml-saham` can return WIN/LOSE rather
  than `INCONCLUSIVE`/`BLOCKED_DATA`.
- `ml-saham challenge health --scenario accum --compatibility-id <new>` returns
  a real verdict.
- Zero observations from the pre-fix engine remain.

---

## 4. Non-Goals

- No scoring, gate, or identity logic changes. Those belong to the config-edit
  batch (ADR-068 task, ADR-067 task, risk-gate task). If this task needs a logic
  change, it is a defect in a prior task — go back and fix it there.
- No re-weighting of accum sleeves (deferred; see `SEQUENCE_*.md`).
- No promotion of anything into production config
  (`06_implement_accum_policy_proposal_lifecycle.md`).
- No pre-open corpus changes (`05_fix_preopen_directional_score_resolution.md` —
  different purpose, isolated per the purpose-isolation rule in
  `grow_snapshot_bound_accum_challenge_corpus.md`).
- No changes to `ml-saham`.

---

## 5. Architecture Impact Assessment

- **Domain / Application / Infrastructure / Adapter:** ideally **none**. This is
  an ops task run through existing commands.
- Expected exception: `scripts/purge_accum_learning_corpus.py` may need a range
  or dry-run refinement, and the backfill command may need a depth guard.

New dependency: **No.**
Determinism: **No** logic change.
Persistence: **Yes — destructive.** Rows are deleted. Backup is mandatory.
Warm-up: **Yes** — indicator warm-up bounds how early the backfill can start.
Measure it; do not assume.
Policy in adapter: **No.**

```md
Layer plan:
- Domain: not touched
- Application: not touched (unless a backfill depth guard is required)
- Infrastructure: not touched
- Adapter: not touched
- Ops: purge script + documented command sequence
```

---

## 6. AI Usage Declaration

**No AI involved.**

---

## 7. Risk, Signal, And Evidence Authority Considerations

No decision component changes. The corpus this produces becomes the evidence
base for every later tuning decision, so its integrity is the whole point.

**Does this change what can produce ENTER/WATCH/AVOID?** No.

---

## 8. Data & Persistence

- **Read:** `candles`, `broker_summaries`, `broker_daily_flow`,
  `company_fundamentals`, `shareholding_composition`,
  `trading_session_calendar_snapshots`.
- **Deleted:** all accum-purpose `learning_observations`,
  `learning_outcome_labels`, `setup_phase_ledger` entries, and orphaned
  `learning_policy_snapshots`.
- **Written:** fresh observations, labels, phase-ledger rows, and one snapshot set.
- **Schema change:** No.

### Depth is bounded by three limits — measure all three before purging

1. **Market data:** 2025-07-07 (`candles`, `broker_daily_flow`).
2. **Indicator warm-up:** the longest lookback on the screen path
   (`sma_period`, `rsi_period`, 20d liquidity median, 7d canonical window).
3. **Fundamentals PIT depth:** confirmed by implementing
   `03_fix_risk_gate_silent_skip_and_fundamentals_pit_hole.md` (2026-08-05) — see
   `docs/data_fundamentals_pit_depth.md` for the full measurement. Honest
   `piotroski_f_score` / `market_cap_idr` coverage starts **2026-07-08** (273
   tickers) / **2026-07-09** (30 tickers). This is a **hard, non-recoverable**
   limit, not a backfill-later gap: `piotroski_f_score` arrives from Stockbit
   precomputed with no local F-score calculator to rebuild it from, and
   `market_cap_idr` has no stored shares-outstanding to reconstruct a historical
   value from. Nothing before 2026-07-08 can ever be filled in.

   **Sharper than "FundamentalGate goes unevaluable": the structural filter
   rejects, it does not go unevaluable.** `AccumulationCandidateStructuralFilter`
   and the risk gates handle the same missing data differently — `FundamentalGate`
   / the LiquidityGate market-cap leg record `GateOutcome.UNEVALUABLE` (safe,
   asserts nothing), but `min_market_cap_idr` / `min_piotroski` in the
   *structural filter* **reject** candidates outright on a missing value. Setting
   either above 0 for any pre-2026-07-08 session **empties the universe**, not
   "degrades it." Verify both filter thresholds are 0 (or the rebuild window
   starts at 2026-07-08+) before running anything against an earlier session.

Limit 3 is the sharp one. **Decide explicitly and record the decision** (see
`docs/data_fundamentals_pit_depth.md` §5 for the ranked options):

1. **Start the deep cohort at 2026-07-08 or later (recommended).** Every
   session then has honest fundamentals for all 303 tickers and both gates are
   genuinely live — no permanently-degraded window in the cohort.
2. **Go deeper and accept the degradation explicitly**, but pre-2026-07-08 rows
   must then be a *separate* cohort — pooling them with post-cutoff rows mixes
   observations where the gate was live with observations where it was
   structurally blind, which is not one population.
3. Either way: **do not** set `min_market_cap_idr` or `min_piotroski` above 0
   for any pre-cutoff session (see the structural-filter note above) — a known
   evaluable-vs-unevaluable gate is analysable; an emptied universe is not.

**Label maturity:** the 20d horizon needs 20 sessions after each signal date.
Observations in the final 20 sessions will have `UNAVAILABLE` 20d labels until
they mature. This is expected — do not backfill labels forward to fill them.

---

## 9. Acceptance Criteria

- [ ] DB backed up before any destructive command; path and size recorded.
- [ ] Purge dry-run counts reviewed and matched against expectation before `--execute`.
- [ ] `SELECT COUNT(DISTINCT compatibility_id)` for accum purpose = **1**.
- [ ] That cohort has 7 `production_policy_snapshot.v2` rows.
- [ ] The cohort id is the ADR-068 behavioural identity (probe digest + snapshot
      payload digest + payload schema version), not a legacy proxy value.
- [ ] Session depth recorded and ≥ protocol minimum.
- [ ] Zero rows with `risk.snapshot_date > session_date` (PIT guard from `34fc4360`).
- [ ] Label maturity distribution recorded per horizon.
- [ ] `ml-saham challenge health --scenario accum --compatibility-id <new>`
      returns a non-`BLOCKED` verdict; output pasted into the Completion Record.
- [ ] Cron scripts still reference the correct commands after the rebuild.

---

## 10. Slices (each slice = one commit)

**Slice 1 — Measure and plan.**
Report all three depth limits, the achievable start date, expected observation
count, and the exact purge blast radius. **No destructive action.** Land the
numbers first so the purge is reviewable.
Commit: `docs(corpus): measure accum rebuild depth limits and purge blast radius`

**Slice 2 — Harden the purge script.**
Backup verification, FK pragma, dry-run/execute parity, purpose isolation so
PRE_OPEN rows are provably untouched.
Commit: `chore(corpus): harden accum purge script for the rebuild`

**Slice 3 — Execute the clean break.**
Backup → dry-run → confirm → `--execute`. Nothing else in this commit.
Commit: `chore(corpus)!: purge superseded accum learning corpus`

**Slice 4 — Rebuild.**
Session-calendar sync → backfill over the chosen range → labels → phase ledger →
status. Record counts at each step.
Commit: `chore(corpus): rebuild accum corpus as single deep cohort`

**Slice 5 — Verify against ml-saham.**
Run `challenge health` / `challenge run` against the new cohort. Record the
verdict. If still `INCONCLUSIVE`, diagnose and record why — do **not** adjust
protocol parameters to force a verdict.
Commit: `docs(corpus): record ml-saham verdict on rebuilt accum cohort`

---

## 11. Testing Expectations

- Purge script unit tests: purpose isolation (PRE_OPEN untouched), FK integrity,
  dry-run counts equal execute counts.
- Post-rebuild invariant queries as listed in Acceptance Criteria, run and pasted.
- Ruff applies only if Python changes (slice 2 will).

---

## 12. Documentation Impact

- README: **No.**
- New config options: **No.**
- Limitations: **Yes** — record the fundamentals-horizon decision and its effect
  on early-session risk assessment.

---

## 13. Required Reading

- `AGENT_QUICKSTART.md`, `TASK_TEMPLATE.md`, `DEFINITION_OF_DONE.md`
- `BOUNDARY.md` — corpus authority split with `ml-saham`
- `tasks/done/fix_risk_pit_cutoff_lookahead.md` — the prior clean break; reuse
  its command sequence and Completion Record shape
- `tasks/backlog/grow_snapshot_bound_accum_challenge_corpus.md` — locked
  decisions on calendar authority, label integrity, purpose isolation
- `docs/adr/ADR-056-*`, `docs/adr/ADR-059-*`

---

## 14. Do Not Interpret This As

- **Not** permission to relax `ml-saham` protocol parameters (`n_folds`,
  `embargo_sessions`, `min_n_total`) to obtain a verdict. If depth is
  insufficient, the answer is more depth or an honest `INCONCLUSIVE`.
- **Not** permission to run the purge before tasks 1–3 are merged. A rebuild on
  a half-fixed engine wastes the whole exercise.
- **Not** permission to skip the backup.

---

## 15. Completion Record

- Completed date:
- Slice commits:
- Backup path / size:
- Purge dry-run counts vs expected:
- Rebuild range + session depth:
- Final observation / label counts per horizon:
- Single `compatibility_id`:
- Fundamentals-horizon decision + reasoning:
- `ml-saham challenge health` output:
- Test / Lint result:
