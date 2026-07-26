# Learning Pipeline Clean-Break Audit — 2026-07-27

The authorized clean break was applied to `data/db/data.db` in one
`BEGIN IMMEDIATE` transaction.

## Before

| Retired table | Rows |
|---|---:|
| `candidate_observations` | 0 |
| `candidate_observations_quarantine` | 19,317 |
| `observation_risk_assessments` | 0 |
| `signal_forward_labels` | 0 |
| `signal_forward_labels_quarantine` | 5,760 |

The retired swing review journal contained 6 JSONL records. The pre-open
directory contained no files and nine empty session directories.

## After

- All five retired tables are absent.
- 32 retired migration records were deleted.
- The seven `learning_*` tables exist and each contains zero rows.
- `PRAGMA foreign_key_check` returned no violations.
- Migration `database_owned_learning` version 1 is present.
- `journals/swing_tuning_reviews.jsonl` and the empty `data/opening/` tree
  were deleted without import or reinterpretation.
- The other two named swing tuning files were already absent.

The source-field audit reports `PASS` for each of the seven learning tables.
Its overall database result remains `FAIL` because of unrelated, pre-existing
source-contract findings outside this clean-break scope.
