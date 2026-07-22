# DQ-010 lean implementation plan (DONE 2026-07-22)

**Status:** Done — forward-path close-out complete.

Companion to `tasks/done/audit_data_quality.md` → DQ-010.

## Guiding decision (final)

> Treat AUTHORITY-COVERAGE-READINESS + empty canonical as the **clean break**.
> Quarantine tables are **historical parking** — out of scope for this close-out.
> Close DQ-010 by confirming the **forward path** is locked: new writes and
> consumers require current contracts, so the next backfill/label/readiness/
> inspect/audit cycle cannot silently recreate legacy authority.

Live `data/db/data.db` (verified earlier 2026-07-22):
- `candidate_observations` = **0**
- `candidate_observations_quarantine` = **19,317** (parked history)
- `signal_forward_labels` = **0**
- `signal_forward_labels_quarantine` = **5,760** (parked history)

---

## Forward checklist (D10-V) — verified

| # | Guard | Verdict |
|---|-------|---------|
| F1 | Persister requires `accumulation-discovery` + lean `semantic_compatibility_id` | PASS |
| F2 | Lean identity + backfill stamps current schema | PASS |
| F3 | Label generation binds schema / config_hash; rejects incompatible | PASS |
| F4 | Labels `raw_market` / schema; readiness excludes wrong schema / missing lean id | PASS |
| F5 | Retrieve / verify / inspect refuse silent latest; surface contract fields | PASS |
| F6 | Accum-audit live screen + skip ledger + DESCRIPTIVE stamps | PASS |
| F7 | Authority consumers use canonical tables only (not quarantine) | PASS |

---

## D10-G — gap closed

**Hole found:** `_canonical_observation_skip_reason` allowed labels for rows with
schema+hash but `semantic_compatibility_id is None` (repo `save_many` bypass).

**Fix (NON_SEMANTIC fail-closed):** skip with `NON_CANONICAL_OBSERVATION_IDENTITY`
when lean id is missing; golden
`test_single_path_null_semantic_compatibility_id_rejected`.

**Residual (accepted, not a DQ-010 gate):**
- Repo `save_many` still accepts lean-incomplete rows (no DB CHECK) — application
  persister + label skip close the forward authority path.
- Optional ops: file backup/restore drill; quarantine deletion product.

---

## Slice map

| Slice | Status |
|-------|--------|
| D10-V | Done |
| D10-G | Done (one golden + fail-closed skip) |
| D10-C | Done — DQ-010 marked Done; DQ-011 unblocked for planning |

---

## Explicit non-goals (unchanged)

- Quarantine UX / leakage suites / mandatory backup drills
- Migration platform / dual-write / leftover inventory
- Full historical backfill as a gate
- Sentiment / CLI-002 / IDX-EXECUTION-LABELS / purged walk-forward

---

## Classification

D10-G fail-closed label skip: `NON_SEMANTIC` — does not change label math for
valid lean-stamped rows; only blocks minting labels from lean-incomplete
bypass rows. Empty canonical → no live cohort impact.
