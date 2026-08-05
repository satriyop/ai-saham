# Implement ADR-068: Behavioral Engine Identity For Accum Cohorts

Status: `READY` — ADR-068 accepted 2026-08-04. No blockers.
Sequence: **1 of 8** — first task in the config-edit batch. See
`tasks/backlog/00_SEQUENCE_accum_baseline_and_learning_loop.md`.

## 1. Task Metadata

**Task Title**
Replace proxy-based cohort identity with a measured behavioural probe digest.

**Task Type**
Refactor (identity-material; forks the cohort; requires corpus clean break)

**Priority**
High — must land **before** ADR-067 implementation and before the corpus
accumulation window opens.

---

## 2. Problem Statement

See [ADR-068](../../docs/adr/ADR-068-behavioral-engine-identity-for-accum-cohorts.md)
§Context. Summary of the three proxies being replaced:

- **Config bytes over-fire.** `research_accum_backfill_commands.py:109-115`
  hashes the raw text of twelve config files; a comment forks the cohort, and
  half those files provably cannot change an accum decision.
- **Version constants under-fire.** `SEMANTIC_ENGINE_VERSION` and
  `EVIDENCE_CONTRACT_VERSION` (`signal_semantic_contract.py:25,31`) are string
  literals a human must remember to bump. Forget one and two engines' output
  merges silently.
- **`config_hash` does nothing.** One writer
  (`accumulation_candidate_observation_persister.py:170`), and its only reader is
  guarded on `candidate_observations` — a table dropped 2026-07-27.

Source-content hashing was measured and rejected: the 180-file import closure
saw 229 commits in 60 days (~27 forks/week) against a protocol needing 40+
sessions in one cohort.

---

## 3. Desired Outcome

- Cohort identity = digest of (behavioural probe outputs, ADR-059 snapshot
  payload digest, payload schema version). Nothing else.
- A rename, comment, or docs edit does **not** fork the cohort.
- A threshold or scoring-logic change **does** fork it, with no human action.
- Probe-set quality is a measured number (branch coverage + surviving mutants),
  not an assumption.
- Every observation records which build produced it, beside identity.

---

## 4. Non-Goals

- **No scoring, gate, threshold, or evidence-authority change.** If a probe
  reveals behaviour you dislike, that is a separate task.
- No change to population binding, label contracts, or calendar authority.
- No probe that reads a clock, network, database, or filesystem.
- No dual-identity path, fallback, or alias to the old mechanism.
- No pre-open identity change — ADR-068 is scoped to `ACCUMULATION_DISCOVERY`.
  Pre-open keeps its existing mechanism; purpose isolation applies.
- No corpus purge here — that is the rebuild task, and it happens **once** for
  the whole batch.
- No `ml-saham` code changes (documentation only).

---

## 5. Architecture Impact Assessment

- **Domain:** delete `SEMANTIC_ENGINE_VERSION` / `EVIDENCE_CONTRACT_VERSION`;
  keep `ACCUMULATION_OBSERVATION_PAYLOAD_SCHEMA_VERSION`.
- **Application:** new probe-set definition and identity resolver replacing
  `resolve_lean_semantic_compatibility_id`'s material; delete
  `compute_accumulation_config_hash` and `_CONFIG_HASH_FIELDS`.
- **Infrastructure:** none beyond removing the dead audit branch.
- **Adapter:** delete `_SCORING_CONFIG_PATH_ATTRS` and
  `_read_scoring_config_canonical`; the adapter stops reading config files for
  identity entirely.

New dependency: **No** (coverage/mutation tooling is dev-only; confirm before
adding, prefer what is already in the dev extras).
Determinism: **No behaviour change** — but determinism becomes a hard, tested
precondition.
Persistence: **No SQL migration.** Payload gains
`producer_source_revision`; schema version bumps.
Warm-up: **No.**
Policy in adapter: **removed** — identity material moves to application.

```md
Layer plan:
- Domain: remove the two engine version constants; keep payload schema version
- Application: probe-set definition, probe runner, behavioural identity
  resolver, snapshot-digest folding; delete config-hash service
- Infrastructure: remove dead candidate_observations audit branch
- Adapter: delete config-file reading for identity; pass through resolver output
```

---

## 6. AI Usage Declaration

**No AI involved.**

---

## 7. Risk, Signal, And Evidence Authority Considerations

No decision component changes behaviour. **Does this change what can produce
ENTER/WATCH/AVOID? No** — and the probe digest is the proof.

Evidence authority unchanged. The ADR-059 snapshot remains the record of declared
policy and now additionally contributes to identity via its payload digest.

**Trust ordering is mandatory:** the probe digest must not become authoritative
until slice 2 proves it detects deliberate scoring changes. Shipping identity on
an unproven probe set would be strictly worse than today.

---

## 8. Data & Persistence

- **Read:** nothing new for identity (config file reads for identity are removed).
- **Written:** observation payload gains `producer_source_revision`.
- **Schema change:** payload version bump. No SQL migration.
- **Semantic equivalence:** identity values are **not** comparable to historical
  ones. Accepted — no current cohort holds value (ADR-068 §9). The corpus is
  rebuilt once, by the rebuild task, after the whole batch lands.

`producer_source_revision` **must not** enter `observation_id` or
`artifact_digest`. Add a test asserting that re-capturing the same session under
a different build yields the same `observation_id`.

---

## 9. Acceptance Criteria

- [ ] Identity material is exactly the three ADR-068 parts; nothing else.
- [ ] Probe run is bit-identical across repeated runs in one process and across
      processes (determinism proof).
- [ ] Probe run performs no clock/network/DB/filesystem access (asserted).
- [ ] Branch-coverage floor over the accum decision path enforced in CI.
- [ ] Mutation suite: every planted mutant moves the digest, or is recorded as a
      named, accepted hole with rationale.
- [ ] Adding an **extended** probe does not change identity (test).
- [ ] Renaming a symbol does not change identity (test).
- [ ] Editing a config comment does not change identity (test).
- [ ] Changing a threshold **does** change identity (test).
- [ ] `SEMANTIC_ENGINE_VERSION`, `EVIDENCE_CONTRACT_VERSION`,
      `compute_accumulation_config_hash`, `_CONFIG_HASH_FIELDS`,
      `_SCORING_CONFIG_PATH_ATTRS`, and the dead audit branch are gone.
- [ ] `producer_source_revision` on the payload, outside identity (test).
- [ ] Pre-open identity provably unchanged.
- [ ] `BOUNDARY.md` updated in both repos.
- [ ] **Lint Gate:** `ruff check src/ tests/` and `ruff format --check src/ tests/`.

---

## 10. Slices (each slice = one commit)

**Slice 1 — Probe harness and core set v1.**
Deterministic offline probe runner plus the initial core probe set, generalising
`test_adr062_offline_golden.py`. Prove determinism (repeat-run equality, no IO).
Emit the digest but **do not wire it to identity**.
Commit: `feat(identity): add deterministic behavioural probe harness`

**Slice 2 — Prove the probe set is worth trusting.**
Branch coverage over the accum decision path with a CI floor, plus the mutation
suite. Record the coverage number and any surviving mutants. **Do not proceed to
slice 3 until this passes** — identity on an unproven probe set is worse than
what exists today.
Commit: `test(identity): coverage floor and mutation gate for the probe set`

**Slice 3 — Shadow the new identity.**
Compute behavioural identity alongside the existing one and log both. Confirm on
real backfill runs that it is stable across no-op commits and moves on a planted
threshold change. Old mechanism still authoritative.
Commit: `feat(identity): compute behavioural cohort identity in shadow`

**Slice 4 — Cut over and delete the proxies.**
Behavioural identity becomes authoritative. Delete both engine version constants,
the config-byte canonical reader, `compute_accumulation_config_hash`,
`_CONFIG_HASH_FIELDS`, `_SCORING_CONFIG_PATH_ATTRS`, and the dead
`candidate_observations` audit branch. No fallback path.
*Cohort identity forks here. Capture cron must be disabled.*
Commit: `refactor(identity)!: behavioural cohort identity replaces config and version proxies`

**Slice 5 — Provenance and operator visibility.**
`producer_source_revision` on the observation payload, beside identity. Cohort
build audit (informational: "this cohort was produced by N builds"). Fork warning
naming the orphan count before a forking action — salvaged from a deleted
identity-trimming draft, and valuable under any identity mechanism.
Commit: `feat(corpus): record producing build and warn before a cohort fork`

**Slice 6 — Documentation.**
`BOUNDARY.md` in both repos, `AGENT_QUICKSTART.md` if it references version
bumps, and the ADR-068 completion record. State plainly that probe coverage is a
measured floor, **not** a proof of behavioural equivalence.
Commit: `docs(identity): document behavioural cohort identity and its limits`

---

## 11. Testing Expectations

Positive:
- Repeat-run and cross-process digest equality.
- Extended-probe addition leaves identity unchanged.
- Snapshot payload change moves identity (declared-policy axis).
- Payload schema bump moves identity (record-shape axis).

Negative (these prove the mechanism works):
- Planted threshold change moves the digest.
- Planted comparison flip moves the digest.
- Symbol rename does **not** move the digest.
- Config comment edit does **not** move the digest.
- Probe run attempting clock/network/DB/filesystem access fails.
- Re-capture under a different build yields the same `observation_id`.

Offline. `pytest -m "not tui"` for the inner loop. Ruff before close.

---

## 12. Documentation Impact

- README: **No.**
- `BOUNDARY.md` (both repos): **Yes.**
- New config options: **No** — options are removed.
- Limitations: **Yes** — coverage is a floor, not a proof. Say so explicitly.

---

## 13. Required Reading

- `AGENT_QUICKSTART.md`, `CLAUDE.md`, `TASK_TEMPLATE.md`, `DEFINITION_OF_DONE.md`
- **ADR-068** (this task implements it), ADR-059, ADR-062 (golden precedent),
  ADR-067
- `BOUNDARY.md` — `ml-saham` reads cohorts and digest-checks snapshots
- `tests/application/services/test_adr062_offline_golden.py` — the pattern to
  generalise

---

## 14. Do Not Interpret This As

- permission to change any scoring rule, threshold, or gate;
- permission to make the probe digest authoritative before slice 2 passes;
- permission to let a probe touch a clock, network, database, or filesystem;
- permission to keep a fallback to the old identity "just in case";
- permission to lower the coverage floor or wave through a surviving mutant;
- permission to put `producer_source_revision` inside `observation_id` or
  `artifact_digest`;
- permission to touch pre-open identity;
- permission to purge the corpus here;
- a claim that probe coverage proves behavioural equivalence.

---

## 15. Completion Record

- Completed date:
- Slice commits:
- Core probe count / extended probe count:
- Branch coverage achieved (and the CI floor set):
- Mutants planted / caught / surviving (with rationale for each survivor):
- New `compatibility_id`:
- Cron disabled / re-enabled at:
- Test / Lint result:
