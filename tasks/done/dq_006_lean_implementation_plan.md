# DQ-006 lean implementation plan (amended 2026-07-22)

**Status:** DONE (D6-1 + D6-2 implemented 2026-07-22). Parked items unchanged.

Companion to `tasks/backlog/audit_data_quality.md` → DQ-006 and its "Lean
readiness amendment (2026-07-22)". Make readiness counts honest for
**deterministic calibration** first; do not pretend promotion or ML authority.

## Guiding decision

Implement this option only.

> Readiness must report **valid, independent, same-cohort** labeled samples with
> visible exclusions. `patch_eligible` must not overclaim. Ephemeral 70/30 OOS
> stays **diagnostic-only** until a later immutable-split task. Do not build a
> readiness platform, diversity warehouse, or tuning auto-wire in this task.

**Why (codebase-grounded):**

- `ReportSignalReadinessUseCase` is CLI-only today; `patch_eligible` is
  display-only (not consumed by SignalEngine or swing tuning).
- Labels can silently pool mixed `semantic_compatibility_id` cohorts.
- UNAVAILABLE is excluded from IS/OOS, but other exclusions lack a ledger.
- Multi-window/duplicate label rows can inflate IS/OOS independence claims.
- Full “immutable OOS after labels observed” needs a persisted assignment —
  over-engineered for the current consumer. Rename the claim instead.

---

## Vet findings → backlog revisions

| Current backlog ask | Verdict | Lean action |
|---|---|---|
| Independent reconciliation of every count | Keep | Slice D6-2 golden/SQL tests |
| Exclusion counts by reason | Keep (expand) | Slice D6-1 exclusion ledger |
| OOS immutable after labels observed | **Overscoped now** | Park; document ephemeral 70/30 as diagnostic-only; forbid production claim |
| `patch_eligible` impossible when gates fail | Keep, but **rename honesty** | Slice D6-1: never claim production eligibility; diagnostic targets stay false |
| Mixed semantic cohorts separated | Keep — **missing in code** | Slice D6-1 fail-closed / report-by-cohort |
| Diversity by ticker/sector/regime/liquidity/time | **Overscoped now** | Park behind diversity trigger; optional tiny unique-ticker/date counts only |
| Wire readiness into tuning/promotion | **Out of scope** | Park |

---

## What already exists (reuse)

| Piece | Location |
|---|---|
| Readiness reporter | `report_signal_readiness_use_case.py` |
| CLI | `analyze_signal_readiness_commands.py` |
| Canonical obs lists | `list_canonical_by_date` / `list_latest_canonical_by_date` |
| Label list + UNAVAILABLE exclude | already in readiness |
| Cohort field on observations | `semantic_compatibility_id` |
| Labels bind via `observation_captured_at` | DQ-004 |

---

## Slice D6-1 — Contract honesty: claims, exclusions, cohort isolation

**Status:** DONE

**Goal:** Stop lying about what readiness means. Close the “no production claim
from 70/30 alone” criterion and the cohort / exclusion-ledger halves.

**Layer plan:**
```md
- Domain: not touched (or tiny report DTO fields only if needed)
- Application: ReportSignalReadinessUseCase — exclusion ledger, cohort gate,
  claim/wording fields; patch_eligible semantics tightened
- Infrastructure: not touched
- Adapter: CLI display of exclusions / cohort / diagnostic-only OOS note
```

**Contracts (implement this option only):**

1. **Cohort isolation**
   - Require an explicit cohort input **or** default to the single dominant
     observation `semantic_compatibility_id` present in the corpus.
   - If multiple observation cohorts exist and no cohort is selected → fail
     closed with a blocker / structured reason (`mixed_semantic_cohorts`), do
     **not** pool them into IS/OOS.
   - Labels counted for readiness must bind to observations in that cohort
     (via `observation_captured_at` join, or equivalent explicit linkage). Do
     not invent a second cohort id on labels unless already present.

2. **Exclusion ledger (visible by reason)**
   Report counts (at least):
   - `excluded_schema_mismatch` (non-current label schema)
   - `excluded_unavailable`
   - `excluded_target_mismatch` (optional if cheap)
   - `excluded_wrong_cohort` / `excluded_unlinked_observation`
   - Keep existing `unavailable_label_count` consistent with the ledger

3. **Claim honesty**
   - Report must carry an explicit mode/note:
     `oos_split=EPHEMERAL_CHRONOLOGICAL_70_30` (diagnostic only).
   - CLI must **not** say “production eligible” / “patch gates passed” in a way
     that implies promotion authority.
   - Prefer renaming display to **“calibration floors passed”** (or keep
     `patch_eligible` but document it as Phase-I calibration floors only and
     always emit `promotion_eligible=false`).
   - Diagnostic targets remain never patch/calibration-eligible.

4. **Do not** persist OOS membership, build diversity dashboards, or wire
   tuning in D6-1.

**Negative-first tests:**
- Two observation cohorts present, no cohort selected → no pooled IS/OOS;
  blocker/reason visible.
- Schema-1 (or non-current) labels appear only in exclusion ledger, not IS/OOS.
- UNAVAILABLE appears in exclusion ledger and not in labeled_target.
- Diagnostic target → `patch_eligible` / calibration-eligible false.
- Report/CLI asserts diagnostic-only OOS wording / `promotion_eligible=false`.

**Semantic Change Classification:** likely `NON_SEMANTIC` for engine outputs;
readiness report contract change — state explicitly; no observation/label
schema bump unless a new persisted field is unavoidable (prefer not).

**Checkpoint:** stop for review after D6-1 before independence/reconciliation.

---

## Slice D6-2 — Sample independence + count reconciliation

**Status:** DONE

**Goal:** Independent samples and prove every displayed count. Closes
reconciliation + duplicate-inflation criteria.

**Layer plan:**
```md
- Domain: not touched
- Application: readiness independence policy for labeled targets
- Infrastructure: not touched (SQL only in tests if used)
- Adapter: thin display of unique ticker/date counts if added
```

**Contracts:**

1. **Independence policy for readiness IS/OOS bag**
   - After target+availability+cohort filters, collapse to **one row per
     `(ticker, signal_date, horizon)`** (deterministic pick: latest
     `observation_captured_at`, then stable tie-break).
   - Multi-window duplicates must not inflate IS/OOS.
   - Expose `raw_labeled_target_count` vs `independent_labeled_target_count`
     (mirror the existing raw vs collapsed observation pattern).

2. **Reconciliation fixture (independent of the reporter’s internal vars)**
   - Golden SQLite (or recording fakes + direct SQL) with known rows.
   - Hand-compute expected: raw labels, schema exclusions, unavailable,
     target matches, independent labeled targets, IS/OOS sizes.
   - Assert field-by-field match to the report.
   - Adversarial case: duplicate windows / duplicate captures → collapsed count.

3. **Minimal diversity (optional if free)**
   - `unique_tickers`, `unique_signal_dates` on the independent bag only.
   - Do **not** build sector/regime/liquidity dashboards in D6-2.

**Negative-first tests:**
- Two labels same ticker/date/horizon different `captured_at` → count as 1
  independent sample.
- Reconciliation golden matches every public count field.
- Exclusion ledger totals + independent counts are internally consistent.

**Close:** focused + related readiness tests green; `git diff --check`.

---

## Parked (explicit)

| Parked | Wake when |
|---|---|
| Persisted immutable OOS assignment (pre-outcome freeze) | Promotion / purged walk-forward needs it |
| Full diversity matrix (sector/regime/liquidity/time floors) | Calibration policy requires it |
| Wire `patch_eligible` into swing tuning validator | After D6-1/D6-2 + explicit product decision |
| Control-population / recall readiness | `CONTROL-POPULATION` task |
| Claiming promotion eligibility from readiness | Evidence promotion lane |

---

## After each slice — doc update

Mark closed DQ-006 criteria `[x]` with satisfied-notes; update this plan’s
slice `Status`. Do not mark parked criteria done. Do not unblock CLI
restructure until `DQ-BASELINE-GATE` owners agree readiness honesty is enough
for their gate (DQ-006 alone ≠ baseline freeze).
