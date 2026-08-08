# Rebuild The Accum Corpus As One Deep, Snapshot-Bound Cohort

Status: `IMPLEMENTED` — re-vetted and executed **2026-08-08** after task 09
(`ai-saham@6d9099af`, `ml-saham@e1a5fac`). Slices 1–5 complete; config freeze
applies until a deliberate identity-moving change.

> **Mandatory, not optional.** The config-edit batch (ADR-068, ADR-067, task 03
> risk/PIT, task 09 snapshot binding) is identity-moving. Every existing accum
> observation belongs to a superseded identity and/or schema. This task is the
> **single** purge + rebuild for the whole batch.
>
> **Purge exactly once.** Do not execute a destructive purge during re-vet
> (this document). Destructive work starts only at slice 3 after backup +
> dry-run review.

Sequence: **4 of 8** — see `tasks/backlog/00_SEQUENCE_accum_baseline_and_learning_loop.md`
Prerequisites: tasks **1, 2, 3, 9** (all implemented/verified as of this re-vet).

---

## 1. Task Metadata

**Task Title**
Clean-break the accum learning corpus and rebuild it as a single cohort under
the **current** ADR-068 identity (schema **15**, snapshot contract
**production_policy_snapshot.v4**, nine policy rows including task-09 risk-audit
bindings).

**Task Type**
Ops / clean break (no scoring logic changes)

**Priority**
High — unblocks a learnable single-cohort challenge lab.

---

## 2. Re-Vet Summary (2026-08-08)

### 2.1 What was stale in the prior draft

| Prior draft claim | Current truth (code + live DB) |
|---|---|
| Expects `production_policy_snapshot.v2` **7** rows | Active contract is **`production_policy_snapshot.v4`** with **exactly 9** rows |
| Silent about observation schema | Writer/reader current = **schema 15**; DB has **0** schema-15 accum rows |
| Predates task 09 | Task 09 binds `risk.gate_evaluations` / `unevaluable_gates` into snapshot payloads; that **moves** the ADR-068 snapshot-set digest / `compatibility_id` |
| Four cohorts measured 2026-08-04 | Live DB now has **six** accum cohorts (see §3) |
| Purge deletes phase ledger + orphaned snapshots | Current `scripts/purge_accum_learning_corpus.py` deletes **only** accum observations, their labels, and accum evaluations — **not** snapshots or phase ledger |
| Implies WIN/LOSE immediately after rebuild | Fundamentals honest floor is **2026-07-08**; only **26** candle sessions through **2026-08-07** — below a comfortable `accum_path_v1` multi-fold + 20-session embargo WIN path |

### 2.2 Prerequisite batch status

| # | Task | Status |
|---|---|---|
| 1 | ADR-068 behavioural identity | **DONE** (`tasks/done/`) |
| 2 | ADR-067 retire setup_quality | **DONE** (`tasks/done/`) |
| 3 | Risk-gate skips + fundamentals PIT | **FIXED / VERIFIED** (backlog file) |
| 9 | Bind risk audit into snapshots + ml-saham v2 | **IMPLEMENTED** (2026-08-08) |

### 2.3 Current production identity (computed from live config, post–task 09)

Measured 2026-08-08 via `resolve_accumulation_production_policy_bundle` +
`resolve_accumulation_cohort_identity` (no DB write):

| Axis | Value |
|---|---|
| Observation schema | **15** |
| Snapshot contract (target) | **production_policy_snapshot.v4** (9 policies) |
| `compatibility_id` | `sha256:355e5b59600dbdc9f762f7b373e8879b7cda9a1e55e18bd590461315cfe1e091` |
| Behavioural probe digest | `913ab690547eba19e95f509f281ce4d1afe15ffdaaae3d242795b18c2f5b4ad8` |
| Policy snapshot-set digest | `57bd394b345c118f0b9d932743cd1de2d37ac137d6ea3d1985c2d555d33602cc` |

Hard filters currently: `min_market_cap_idr=0`, `min_piotroski=0`,
`min_accum_score=0` enabled, `min_signal_score` disabled. Unevaluable aggregate
policy: **surface**.

**None of the six stored accum cohorts match this `compatibility_id`.** The
newest stored cohort (`d213…`) is schema **13** with v4 snapshots that still
lack task-09 `observation_result_fields` on
`risk.accum.unevaluable_policy` and still declare only coarse
`trade_setup.blocking_gates` / `candidate.risk_status` on
`risk.accum.hard_gates`.

### 2.4 ml-saham protocol (unchanged, still binding)

`accum_path_v1` (`ml-saham` `src/ml_saham/challenge/protocols.py`):

- `min_n_total=80`, `min_n_test=20`
- `n_folds=3`, `embargo_sessions=20`
- `min_folds_for_win=2`
- Primary metric horizon H=10 (report 3/10/20)

Do **not** relax these parameters to force a verdict.

---

## 3. Live Corpus Measurements (read-only, 2026-08-08)

Source: `data/db/data.db` (~1.34 GB), measured with SQLite SELECT only.
Purge dry-run: `python scripts/purge_accum_learning_corpus.py --db data/db/data.db`.

### 3.1 Observation purposes

| purpose | n | cohorts |
|---|---:|---:|
| `ACCUMULATION_DISCOVERY` | **2,678** | **6** |
| `PRE_OPEN_AUCTION_DIRECTION` | **29** | 1 |

### 3.2 Accum cohorts (all superseded)

| compatibility_id (prefix) | obs | schema | session_date span | distinct sessions | snapshots | notes |
|---|---:|---:|---|---:|---|---|
| `0053…` | 1,890 | 9 | 2026-06-02 → 2026-07-30 | **42** | 0 | Pre–ADR-059; deepest calendar |
| `5898…` | 349 | 9 | 2026-07-31 | 1 | 6 × **v1** | Incomplete set |
| `8ba8…` | 304 | 9 | 2026-06-30 | 1 | 7 × **v2** | Single day |
| `6493…` | 45 | 12 | 2026-08-03 | 1 | 7 × **v2** | |
| `0fa0…` | 45 | 13 | 2026-08-05 | 1 | 7 × **v2** | |
| `d213…` | 45 | 13 | 2026-08-07 | 1 | **9 × v4** | Newest; still pre–schema 15 / pre–task 09 payload binding |

**Schema-15 accum rows in DB: 0.**
**Learning loop tables:** proposals / validations / applications = **0** each.

Risk audit note: even schema-9 rows often contain
`features_by_window.7.risk.gate_evaluations` arrays (persister enrichment is
older than task 09). Task 09’s defect was **snapshot declaration + ML
extraction**, not missing raw audit storage. Post-rebuild writers must still
emit schema **15** with structural-filter + diagnostic binding contracts.

Labels attached to accum observations: **5,232** rows (join on
`observation_id`).

### 3.3 Market data (not the soft limit; fundamentals are)

| Table | rows | tickers | date range |
|---|---:|---:|---|
| `candles` | 83,917 | 320 | 2025-07-07 → **2026-08-07** |
| `broker_summaries` | 65,604 | 306 | 2025-07-07 → 2026-08-07 |
| `broker_daily_flow` | 515,645 | 303 | 2025-07-07 → 2026-08-07 |

Candle sessions with `date >= 2026-07-08` (fundamentals floor): **26**
(`2026-07-08` … `2026-08-07`). Broker summary sessions in that window: **23**.

### 3.4 Fundamentals PIT floor (unchanged, still hard)

From `docs/data_fundamentals_pit_depth.md` + live re-count 2026-08-08:

| | |
|---|---|
| `company_fundamentals` rows | 9,014 |
| With `piotroski_f_score` / `market_cap_idr` | **473** each |
| First honest non-null | **2026-07-08** |
| Latest fundamentals fetch | 2026-08-03 |

**Decision (locked for this rebuild):** start the deep cohort at
**2026-07-08 or later**. Do not mix pre-cutoff sessions into the same
compatibility cohort. Keep `min_market_cap_idr` and `min_piotroski` at **0**
(current production) so structural filters do not empty the universe on residual
missingness.

### 3.5 ml-saham health (live DB, 2026-08-08)

`ml-saham challenge health --scenario accum` against this DB returned
**BLOCKED_POLICY** for `screener.accum.score_weights` (n=0 without an explicit
eligible post–task-09 cohort). Confirms no usable production baseline cohort
exists today.

### 3.6 Session-calendar authority gap

`trading_session_calendar_snapshots` currently covers only
**2026-08-05 → 2026-08-07** (Stockbit IHSG history snapshot). A deep backfill
from 2026-07-08 **must** expand calendar coverage first
(`saham research accum sync-session-calendar`), or capture/backfill will
fail-closed / under-count sessions.

---

## 4. Desired Outcome

- Exactly **one** accum `compatibility_id` after rebuild, equal to the live
  ADR-068 triple (probe + snapshot-set digest + schema 15). Recompute at execute
  time; the §2.3 value is the re-vet baseline and will change if config moves.
- That cohort carries the full **9-row `production_policy_snapshot.v4`** set,
  including task-09 paths:
  - `risk.accum.hard_gates` → `features_by_window.7.risk.gate_evaluations` (+ coarse companions)
  - `risk.accum.unevaluable_policy` → `unevaluable_gates` + `gate_evaluations`
- Observation payloads are **schema 15** only.
- Session depth is the maximum the data honestly supports **from 2026-07-08**,
  then grows under config freeze. **Do not claim WIN/LOSE** until protocol
  depth is actually met (see §8).
- Zero pre-batch accum observations remain.
- `PRE_OPEN_AUCTION_DIRECTION` rows remain untouched (29 today).
- `ml-saham challenge health --scenario accum --compatibility-id <new>` runs
  against the new id (honest BLOCKED_DATA / INCONCLUSIVE is acceptable if depth
  is short; **BLOCKED_POLICY** from wrong snapshot binding is not).

---

## 5. Non-Goals

- No scoring, gate, threshold, or identity-algorithm changes (those were the
  config-edit batch). If rebuild needs a logic fix, stop and fix upstream.
- No re-weighting of accum sleeves; no policy proposal promotion (task 06).
- No pre-open corpus purge/rebuild (purpose isolation).
- No relaxing `ml-saham` `accum_path_v1` fold/embargo/min_n parameters.
- No purge during documentation-only slices.

---

## 6. Architecture Impact Assessment

```md
Layer plan:
- Domain: not touched
- Application: not touched unless backfill depth/calendar guard is required
- Infrastructure: not touched (unless purge script completeness is extended)
- Adapter: not touched
- Ops: purge script hardening + documented command sequence
```

- Determinism: no engine logic change.
- Persistence: **yes — destructive** after slice 3.
- Policy in adapter: no.

---

## 7. Data & Persistence

### 7.1 Read

`candles`, `broker_summaries`, `broker_daily_flow`, `company_fundamentals`,
`shareholding_composition`, `trading_session_calendar_snapshots`, config YAMLs.

### 7.2 Exact purge blast radius (measured dry-run)

**Current script** (`scripts/purge_accum_learning_corpus.py`) dry-run on
`data/db/data.db` (2026-08-08):

| Target | Count | Action today |
|---|---:|---|
| `learning_observations` purpose=`ACCUMULATION_DISCOVERY` | **2,678** | DELETE |
| `learning_outcome_labels` for those observation_ids | **5,232** | DELETE (must precede obs because `ON DELETE RESTRICT`) |
| `learning_evaluations` purpose=`ACCUMULATION_DISCOVERY` | **0** | DELETE (no-op) |
| Non-accum observations (PRE_OPEN etc.) | **29** | **UNTOUCHED** (verified by script) |

**Not handled by the current script — must be addressed before/with purge
(slice 2 hardening):**

| Residue | Count (2026-08-08) | Risk if left behind |
|---|---:|---|
| `learning_policy_snapshots` (all contracts, all cohorts) | **36** | Orphaned superseded identities; ml-saham may still see wrong sets if selection is sloppy |
| `setup_phase_ledger` | **2,713** | Stale production memory from pre-batch screens; not FK-bound to observations |
| `learning_track_snapshots` | 1,230 total; **0** linked to current accum obs ids | Low today; still enforce purpose isolation / FK order |
| `learning_diagnostic_producer_snapshots` | **0** | OK |
| Policy lifecycle tables | 0 / 0 / 0 | OK |

**FK constraint:** labels and track snapshots use
`FOREIGN KEY (observation_id) … ON DELETE RESTRICT`. Purge **must** delete
dependent rows first (script already deletes labels first). Extend the same
pattern for any other RESTRICT children discovered at execute time.

**Explicit non-deletes:** market data tables, PRE_OPEN observations and their
labels, app config, candles, fundamentals.

### 7.3 Written after rebuild

- Fresh schema-15 `ACCUMULATION_DISCOVERY` observations under the single new
  `compatibility_id`
- Full **v4** nine-row snapshot set for that id
- Labels for mature horizons; phase-ledger backfill from new observations
- Expanded trading-session calendar coverage for the rebuild range

### 7.4 Depth limits (all three still apply)

1. **Market data:** from 2025-07-07, but not usable alone.
2. **Indicator warm-up:** longest screen lookbacks (SMA/RSI, liquidity median,
   7d window) — measure at execute; do not guess.
3. **Fundamentals PIT:** hard floor **2026-07-08** (recommended rebuild start).

**Honest post-rebuild expectation (2026-08-08):**

- Rebuild range ≈ **2026-07-08 → latest completed session** (~26 candle
  sessions today).
- That can seed a **single deep cohort** and clear BLOCKED_POLICY identity
  debt.
- It is **unlikely** to satisfy a promotion-grade WIN (`min_folds_for_win=2`
  with `embargo_sessions=20`) until the freeze accumulates more sessions
  (~40+ calendar sessions of same identity is the planning target from
  SEQUENCE).
- Final ~10 / ~20 sessions will have UNAVAILABLE H10 / H20 labels until
  maturity — expected; do not forward-fill labels.

---

## 8. Acceptance Criteria

### Pre-execute (slice 1–2)

- [x] This re-vet document is the execution brief (stale v2/seven-row language gone).
- [x] Purge script extended or companion cleanup covers **policy snapshots** for
      accum-related superseded cohorts and documents phase-ledger handling.
- [x] Dry-run counts re-measured on the execute-day DB and pasted.
- [x] Backup path + byte size recorded **before** `--execute`.
- [x] Trading-session calendar coverage plan for 2026-07-08 → end documented.

### Post-execute

- [x] `SELECT COUNT(DISTINCT compatibility_id) FROM learning_observations WHERE purpose='ACCUMULATION_DISCOVERY'` = **1**.
- [x] That id matches live ADR-068 identity at rebuild time (schema **15**).
- [x] Exactly **9** `learning_policy_snapshots` rows for that id with
      `contract_id='production_policy_snapshot.v4'`.
- [x] Snapshot payloads for `risk.accum.hard_gates` and
      `risk.accum.unevaluable_policy` include task-09
      `observation_result_fields` paths.
- [x] Zero accum observations with `schema_version != 15`.
- [x] PRE_OPEN observation count unchanged across purge (29 → 29, or execute-day baseline).
- [x] Zero rows with risk PIT violation `risk.snapshot_date > session_date` (guard from prior clean break).
- [x] Label maturity distribution recorded per horizon.
- [x] `ml-saham challenge health --scenario accum --compatibility-id <new>`
      output pasted; not BLOCKED_POLICY for missing/wrong snapshot set.
- [x] Cron scripts still correct; config freeze called out in SEQUENCE/ops notes.

---

## 9. Slices (each slice = one commit)

**Slice 1 — Measure and plan (this re-vet is the draft; refresh counts on execute day).**
Commit: `docs(corpus): re-vet accum rebuild depth, identity, purge blast radius`

**Slice 2 — Harden purge / cleanup for full blast radius.**
Must cover: labels-first FK order (already), accum observations, evaluations,
**orphaned/superseded `learning_policy_snapshots`**, phase-ledger policy
(delete-all-for-rebuild vs rebuild-from-obs only — pick one and test), dry-run
parity, PRE_OPEN isolation tests.
Commit: `chore(corpus): harden accum purge for snapshots and phase ledger`

**Slice 3 — Execute clean break only.**
Backup → dry-run → human confirm → `--execute`. No backfill in this commit.
Commit: `chore(corpus)!: purge superseded accum learning corpus`

**Slice 4 — Rebuild.**
Calendar sync → backfill from **2026-07-08** (or later) → ensure v4 snapshots →
labels → phase ledger → status. Record counts each step.
Commit: `chore(corpus): rebuild accum corpus as single schema-15 v4 cohort`

**Slice 5 — Verify with ml-saham.**
Health + representative `challenge run` with explicit `--compatibility-id`.
Honest short-depth BLOCKED_DATA/INCONCLUSIVE is fine; record the gap.
Commit: `docs(corpus): record ml-saham verdict on rebuilt accum cohort`

---

## 10. Testing Expectations

- Purge unit tests: PRE_OPEN untouched; label-before-obs FK order; snapshot
  cleanup; dry-run == execute counts for each table.
- Post-rebuild invariant SQL from Acceptance Criteria, pasted into Completion
  Record.
- Ruff if Python changes (slice 2).
- No full-suite requirement beyond touched scripts + existing purge tests.

---

## 11. Documentation Impact

- This task file + SEQUENCE note.
- Record fundamentals start decision and post-rebuild depth honesty in
  Completion Record (and optionally a short ops note under `docs/` if execute
  discovers new calendar constraints).
- README: no.

---

## 12. Required Reading

- `AGENT_QUICKSTART.md`, `TASK_TEMPLATE.md`, `DEFINITION_OF_DONE.md`
- `BOUNDARY.md` — corpus authority split with ml-saham
- `docs/adr/ADR-059-*` (v4 nine-row closed set + task-09 field bindings)
- `docs/adr/ADR-068-*` (identity triple)
- `docs/data_fundamentals_pit_depth.md`
- `tasks/backlog/09_expose_unevaluable_gate_block_provenance.md` (IMPLEMENTED)
- `tasks/backlog/00_SEQUENCE_accum_baseline_and_learning_loop.md`
- `tasks/done/fix_risk_pit_cutoff_lookahead.md` — prior clean-break shape
- `scripts/purge_accum_learning_corpus.py` — current incomplete blast radius
- ml-saham `src/ml_saham/challenge/protocols.py` (`accum_path_v1`)

---

## 13. Do Not Interpret This As

- Permission to purge during re-vet or slice 1.
- Permission to rebuild before slices 1–2 hardening if snapshot/phase residues
  would leave a mixed-authority lab.
- Permission to start before 2026-07-08 without a **separate** cohort decision.
- Permission to relax ml-saham protocol parameters.
- Permission to skip backup.

---

## 14. Completion Record

- Completed date: **2026-08-08**
- Re-vet commits: `831d5659`
- Slice commits:
  - Slice 1: `831d5659` docs re-vet
  - Slice 2: `788786ff` purge harden + tests
  - Slice 3: `c54cc91a` purge executed
  - Slice 4: rebuild ops (this series)
  - Slice 5: ml-saham verify + closeout
- Backup path / size:
  - `data/db/backups/data.db.pre-task04-purge-20260808_212307`
  - 1.2G; sha256 `bbfb38d91ebcb9aa649389266dd67243baaf7cd27cd7ffabd5fc0105ba211c33`
  - dry-run JSON: `data/db/backups/purge-dry-run-20260808_212307.json`
- Execute-day dry-run counts vs §7.2:

  | Target | Count | After purge |
  |---|---:|---:|
  | accum observations | 2678 | 0 |
  | labels (accum) | 5232 | 0 |
  | track snapshots | 0 | 0 |
  | evaluations | 0 | 0 |
  | policy snapshots | 36 | 0 |
  | phase ledger | 2713 | 0 |
  | PRE_OPEN observations | 29 | **29** |
  | non-accum labels | 22 | **22** |

- Rebuild range + session depth:
  - Calendar sync: `2026-07-08` → `2026-08-07`, **23** sessions inserted
  - Backfill: `saham research accum backfill --universe lq45 --start 2026-07-08 --end 2026-08-07`
  - Processed dates: 23; saved observations: **1035**; universe size 45 (`lq45@pit`)
- Final observation / label counts per horizon (post `labels --all-label-contracts`):

  | contract | AVAILABLE |
  |---|---:|
  | `price_path.accum_3d.v1` | 900 |
  | `price_path.accum_10d.v1` | 585 |
  | `price_path.accum_20d.v1` | 135 |
  | total label rows | 1620 |

  Phase ledger backfill: observations_seen=1035, rows_identical=1026, skipped=9.
- Single `compatibility_id`:
  `sha256:355e5b59600dbdc9f762f7b373e8879b7cda9a1e55e18bd590461315cfe1e091`
  (matches live ADR-068 triple at rebuild: probe
  `913ab690…`, snapshot digest `57bd394b…`, schema **15**)
- Snapshot contract + policy count: **production_policy_snapshot.v4**, **9** rows;
  task-09 `observation_result_fields` present on `risk.accum.hard_gates` and
  `risk.accum.unevaluable_policy`
- Fundamentals-horizon decision + reasoning: start **2026-07-08** (honest
  piotroski/market_cap floor); do not mix pre-cutoff sessions
- Risk PIT violations (`risk.snapshot_date > session_date`): **0**
- Schema ≠ 15 accum rows: **0**
- `ml-saham challenge health --scenario accum --compatibility-id <id>`:
  - **BLOCKED_DATA** for `screener.accum.score_weights`, **n=585** (not
    BLOCKED_POLICY — snapshot set verified)
  - Artifact: `ml-saham/artifacts/challenge/health/20260808_213341`
- Representative challenge runs (same id, `--no-artifact`):
  - `screener.accum.score_weights --against equal_sleeves` → `BLOCKED_DATA: could not form time folds`
  - `risk.accum.hard_gates --against gate_off` → `BLOCKED_DATA: could not form time folds`
- Known depth gap vs WIN criteria: **23 sessions** with `embargo_sessions=20` and
  `min_folds_for_win=2` cannot form multi-fold time splits yet. Keep identity
  frozen and accumulate nightly captures until ~40+ sessions.
- ai-saham `research accum status` note: reports
  `observation_contract_corruption` / `BLOCKED_POLICY` on
  `shared.current_price` string validation for many rows even though payload
  schema is 15 and snapshots are complete. Labels and ml-saham panel extraction
  still work (n=585). Treat as a **status-readiness follow-up**, not a rebuild
  identity failure; do not re-purge solely for that flag.
- Config freeze: no further identity-moving config/payload changes until a new
  deliberate batch + purge is planned.
- Test / Lint result:
  - `tests/infrastructure/persistence/test_purge_accum_learning_corpus.py` 4 passed
  - ruff check/format on purge module + tests: pass
