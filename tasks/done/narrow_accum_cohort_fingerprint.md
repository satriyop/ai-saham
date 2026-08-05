# Narrow The Accum Cohort Fingerprint And Make Forks Visible

Status: `SUPERSEDED` — **do not implement this task as written.**

> **Why superseded (2026-08-04):** this task targets the wrong hash. It aims at
> `_CONFIG_HASH_FIELDS` in `accumulation_observation_fingerprint.py`, which is a
> field recorded inside the observation payload; its only consumer is an audit
> that checks it is non-empty (`audit_source_field_contracts_use_case.py:416-425`).
> It does not determine cohort membership.
>
> Cohort membership comes from `resolve_lean_semantic_compatibility_id`, which
> hashes the **raw text of twelve config files**
> (`research_accum_backfill_commands.py:76-115`). Editing a comment forks the
> cohort. Narrowing the field tuple would have changed nothing.
>
> The premise — unnecessary forks orphan the corpus — is correct and in fact
> understated. The replacement should (a) trim the identity file set to files
> that can actually change an accum decision, which requires ADR-067 to settle
> which those are, and (b) keep the fork warning, which was sound and is worth
> shipping on its own. Do **not** replace byte-hashing with semantic hashing:
> over-forking wastes data, under-forking silently corrupts conclusions.
>
> Retained as a record of the reasoning, not as work.

Sequence: ~~3 of 8~~ — see `tasks/backlog/00_SEQUENCE_accum_baseline_and_learning_loop.md`

## 1. Task Metadata

**Task Title**
Restrict `compatibility_id` material fields to scoring-material config only, and
alarm loudly when a fork orphans the corpus.

**Task Type**
Bugfix / Refactor (identity-material)

**Priority**
High — without it, task 4's rebuilt corpus is orphaned by the next config edit.

---

## 2. Problem Statement

`compute_accumulation_config_hash`
(`src/application/services/accumulation_observation_fingerprint.py:67-101`)
forks `compatibility_id` on any change to `_CONFIG_HASH_FIELDS`. That tuple
includes fields with **no effect on scoring**:

- `ex_date_warning_days` — a display/warning window
- `strategy_name` — a label

A change to either orphans the entire accumulated corpus, because
`ml-saham`'s `accum_path_v1` protocol requires 3 folds with a 20-session embargo
**within a single cohort** (`ml-saham/src/ml_saham/challenge/protocols.py:8-37`).

### Measured evidence (2026-08-04, `data/db/data.db`)

Four forks in ~2 months. No cohort can satisfy the protocol:

| compatibility_id | obs | sessions | policy snapshots | ml-saham verdict |
|---|---|---|---|---|
| `0053…` | 1,890 | **42** | **0 / 7** | ineligible (pre-ADR-059) |
| `5898…` | 349 | 1 | 6 / 7 | `BLOCKED_POLICY` |
| `8ba8…` | 304 | 1 | 7 / 7 | `INCONCLUSIVE` (1 fold) |
| `6493…` (live) | 45 | 1 | 7 / 7 | `BLOCKED_DATA`, n=0 |

Verified live: `ml-saham challenge health --scenario accum --compatibility-id 6493…`
returns `BLOCKED_DATA, n=0`.

Second defect: **nothing tells the operator a fork happened.** There is no
command reporting which `compatibility_id` is currently active or how many
observations a pending config edit will orphan. Discovery today requires
hand-written SQL against `learning_observations`.

---

## 3. Desired Outcome

- `_CONFIG_HASH_FIELDS` contains only fields that can change a score, a gate, or
  an action. Every field carries a written justification.
- A non-material config change does **not** fork the cohort.
- `saham research accum status` (or equivalent) reports the active
  `compatibility_id`, its observation count, and its session depth.
- Changing a material field produces a loud, explicit warning naming the count
  of observations about to be orphaned.

---

## 4. Non-Goals

- No change to the `ProductionPolicySnapshot` contract (ADR-059).
- No cryptographic reversal of `compatibility_id` — it stays an opaque producer
  fork stamp (locked decision, `grow_snapshot_bound_accum_challenge_corpus.md`).
- No auto-migration of observations between cohorts. Ever. A fork means a fork.
- No corpus purge/re-capture (task 4).
- No changes to `ml-saham`.

---

## 5. Architecture Impact Assessment

- **Domain:** not touched.
- **Application:** `accumulation_observation_fingerprint.py` (field tuple +
  justification); status use case gains cohort reporting; fork-warning logic.
- **Infrastructure:** read-only query for cohort counts.
- **Adapter:** render the cohort line and the fork warning. Thin.

New dependency: **No.**
Determinism: **No** change to scoring. Identity values change once, by design.
Persistence: **No schema change.**
Warm-up: **No.**
Policy in adapter: **No** — fork detection is an application concern.

```md
Layer plan:
- Domain: not touched
- Application: narrow _CONFIG_HASH_FIELDS with per-field justification; add
  active-cohort reporting and orphan-count warning to the accum status use case
- Infrastructure: read-only cohort aggregate query on the learning repository
- Adapter: display cohort identity + fork warning; no policy
```

---

## 6. AI Usage Declaration

**No AI involved.**

---

## 7. Risk, Signal, And Evidence Authority Considerations

No decision component changes behavior. This task changes only **corpus
identity** and **operator visibility**.

**Does this change what can produce ENTER/WATCH/AVOID?** No.

Caution: narrowing the tuple is itself a one-time identity change. It must land
**before** task 4's single rebuild so only one fork occurs, not two.

---

## 8. Data & Persistence

- **Read:** `learning_observations`, `learning_policy_snapshots`.
- **Written:** nothing.
- **Schema change:** No.
- **Semantic equivalence:** removing a field from the hash means the new
  identity is **not** comparable to any historical one. That is accepted and is
  precisely why task 4 follows.

---

## 9. Acceptance Criteria

- [ ] Every entry in `_CONFIG_HASH_FIELDS` has a written justification tying it
      to a score, gate, or action.
- [ ] `ex_date_warning_days` and `strategy_name` removed, or justified and kept.
- [ ] A test asserts that changing a non-material field does not change the hash.
- [ ] A test asserts that changing each material field **does** change the hash.
- [ ] Status output reports active `compatibility_id`, obs count, session depth.
- [ ] A config change that forks the cohort emits a warning naming the orphan count.
- [ ] Deterministic; offline; no non-goals violated.
- [ ] ADR-059 considered; `BOUNDARY.md` cohort contract respected.
- [ ] **Lint Gate** passes.

---

## 10. Slices (each slice = one commit)

**Slice 1 — Justify and pin the current tuple.**
Table of every field → what it changes. Tests pinning current hash sensitivity
per field. No behavior change.
Commit: `test(corpus): pin per-field sensitivity of accum config hash`

**Slice 2 — Narrow the tuple.**
Remove non-material fields. Invert the relevant pinned tests.
Commit: `fix(corpus): restrict accum cohort identity to scoring-material config`

**Slice 3 — Cohort visibility.**
Active cohort + depth in accum status output.
Commit: `feat(corpus): report active accum cohort identity and depth`

**Slice 4 — Fork alarm.**
Warn with orphan count when the computed hash differs from the active cohort.
Commit: `feat(corpus): warn when a config change orphans the accum corpus`

---

## 11. Testing Expectations

- Per-field hash sensitivity, positive and negative, for every field.
- Cohort reporting against a fixture DB with multiple cohorts.
- Fork warning fires with the correct orphan count; does not fire when identity
  is unchanged.
- Regression guard: a test that fails if a new field is added to
  `_CONFIG_HASH_FIELDS` without a justification entry — so this cannot silently
  re-rot.

Offline. `pytest -m "not tui"`. Ruff before close.

---

## 12. Documentation Impact

- README: **No.**
- New config options: **No.**
- Limitations: **Yes** — document that `compatibility_id` remains opaque and is
  producer attestation, not reversible proof.

---

## 13. Required Reading

- `AGENT_QUICKSTART.md`, `TASK_TEMPLATE.md`, `BOUNDARY.md`
- `docs/adr/ADR-059-*` (production policy snapshot)
- `tasks/backlog/grow_snapshot_bound_accum_challenge_corpus.md` — **related and
  overlapping**; read its locked decisions before editing identity code. This
  task must not contradict them.
- `~/dev/ml-saham/src/ml_saham/challenge/protocols.py`

---

## 14. Do Not Interpret This As

- **Not** permission to migrate or relabel existing observations into a new
  cohort. Forks are permanent.
- **Not** permission to remove a field merely because it is inconvenient. If a
  field can change an action, it stays.

---

## 15. Completion Record

- Completed date:
- Slice commits:
- Fields removed (with justification):
- Fields kept (with justification):
- New active `compatibility_id`:
- Test / Lint result:
