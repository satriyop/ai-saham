# Accum corpus rebuild — 2026-08-08

Task: `tasks/backlog/04_rebuild_accum_corpus_single_deep_cohort.md`

## Identity (frozen)

| Axis | Value |
|------|--------|
| `compatibility_id` | `sha256:355e5b59600dbdc9f762f7b373e8879b7cda9a1e55e18bd590461315cfe1e091` |
| Observation schema | 15 |
| Snapshot contract | `production_policy_snapshot.v4` (9 policies) |
| Behavioural probe digest | `913ab690547eba19e95f509f281ce4d1afe15ffdaaae3d242795b18c2f5b4ad8` |
| Snapshot-set digest | `57bd394b345c118f0b9d932743cd1de2d37ac137d6ea3d1985c2d555d33602cc` |

## Corpus

- Range: 2026-07-08 → 2026-08-07 (23 calendar sessions, fundamentals floor)
- Observations: 1035 (`lq45@pit`)
- Labels AVAILABLE: H3=900, H10=585, H20=135
- PRE_OPEN untouched: 29
- Backup: `data/db/backups/data.db.pre-task04-purge-20260808_212307`

## ml-saham

```text
ml-saham challenge health --scenario accum \
  --compatibility-id sha256:355e5b59600dbdc9f762f7b373e8879b7cda9a1e55e18bd590461315cfe1e091
→ BLOCKED_DATA  n=585  (screener.accum.score_weights)
  not BLOCKED_POLICY

challenge run … score_weights / hard_gates
→ BLOCKED_DATA: could not form time folds
```

## Freeze

Do not change identity-moving policy/config until the next deliberate batch.
Accumulate nightly `research accum capture` under this id until folds/embargo
are satisfiable (~40+ sessions planning target).
