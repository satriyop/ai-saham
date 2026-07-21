# DQ-003 lean implementation plan (amended 2026-07-21)

Companion to `tasks/backlog/audit_data_quality.md` → DQ-003 and its
"Lean identity amendment (2026-07-21)". This plan sequences the work into
reviewable slices. Implement in order; A→B→C are a dependency chain, D and E
may run in parallel after C.

## Guiding decision

Build the honesty guarantees and a lean identity; park the heavy
artifact-identity apparatus behind the deferral triggers in the amended doc.
Bias toward safe over-forking. Keep `universe_snapshot_id` out of every
idempotency key.

## Layer plan (whole task)

```md
- Domain: observation_contract constant reuse; config-content-hash value/helper (pure)
- Application: capture identity assembly service; response-count aggregation; reason taxonomy
- Infrastructure: reuse existing semantic_compatibility_id column + codec; golden truncated-DB fixture
- Adapter: pass universe-membership identity + limitation note through; render new counts
```

---

## Slice A — Wire lean identity into capture

**Status:** DONE — commit `e00b4aa` (full suite 5569 passing). Closed DQ-003
criteria 6 and 9.

**Goal:** every canonical `accumulation-discovery` row carries
`observation_contract` + a config-content-hash `semantic_compatibility_id`.
Closes acceptance criterion 6; satisfies criterion 9 via config-content hashing.

**Contracts:**

- New pure helper `resolve_lean_semantic_compatibility_id(...) ->
  SemanticCompatibilityId` computing
  `sha256(canonical(resolved_config_content) + CANDIDATE_OBSERVATION_SCHEMA_VERSION
  + SEMANTIC_ENGINE_VERSION + EVIDENCE_CONTRACT_VERSION)`, returned as the
  existing `SemanticCompatibilityId` wrapper (`sha256:<64hex>`).
- Capture path sets `CandidateObservation.artifact_identity` to a value that
  carries **only** `semantic_compatibility_id` populated and
  `observation_contract`; `artifact_id` and full `ArtifactProvenance` remain
  absent/parked. If the current `SignalArtifactIdentity` type forces all three,
  introduce a narrow `LeanObservationIdentity` value object rather than
  fabricating `artifact_id`/provenance.
- `AccumulationCandidateObservationPersister.persist(...)` receives the resolved
  id and the contract; it rejects any `observation_contract !=
  "accumulation-discovery"`.
- Wiring in `analyze_signal_backfill_commands.py` supplies the resolved config
  content; the adapter does not compute the hash (application owns it).

**Files:** `signal_semantic_contract.py` (reuse `ACCUMULATION_DISCOVERY_CONTRACT`,
`*_VERSION` constants), new `application/services/lean_observation_identity.py`,
`accumulation_candidate_observation_persister.py`,
`sqlite_candidate_observations_repository.py` (persist/read the tag — column
already exists), `analyze_signal_backfill_commands.py`.

**Do Not Interpret This As:** do not enumerate config paths; do not populate
`artifact_id`/provenance/`universe_snapshot_id`; do not add
`semantic_compatibility_id` to the upsert key.

**Tests (negative-first):**

- Same config, two runs → identical `semantic_compatibility_id`, one row.
- Change one config value → different `semantic_compatibility_id`.
- Writer rejects a non-`accumulation-discovery` contract.
- Upsert key unchanged: a differing `semantic_compatibility_id` alone does not
  create a duplicate when the canonical key matches (documents cohort-tag vs key).

**Close:** focused tests + architecture boundary test (adapter computes no hash)
+ `git diff --check`.

**Checkpoint:** stop for review after Slice A domain/application contracts and
negative tests pass, before B/C build on them.

---

## Slice B — Capture-boundary reporting

**Goal:** the response answers "who was in the universe, who was evaluated,
selected, unavailable, and by what universe identity." Closes criteria 12 and 13.

**MUST account for the Slice C finding (2026-07-21):** the production backfill
disables every reject gate (`disable_score_filters=True`; `min_market_cap_idr=0`;
`min_piotroski=0`), so the real path emits ONLY `screen_result="pass"`. There is
no screen-rejected subset. Therefore:

- `rejected_count` is **structurally 0** in the current production path. Keep the
  field for forward-compatibility, but document that it is 0 by construction and
  do NOT invent a reason taxonomy for a reject bucket that cannot occur.
- `selected_count == evaluated_count` under current config (all evaluated tickers
  are `pass`). Report both, but do not imply a screen was applied.
- The only real ticker-boundary split is **evaluated (`pass`)** vs **skipped/
  unavailable** (`eval_result is None`, missing candles/broker). The machine-
  readable reason taxonomy covers the skipped/unavailable side only.

**Contracts:**

- Extend `BackfillSignalObservationsResponse` with: `universe_size`,
  `evaluated_count`, `selected_count`, `rejected_count` (documented 0),
  `unavailable_count`, `universe_membership_source` (identity string, e.g.
  `lq45@current`), and a `survivorship_limitation` note when historical
  membership is unavailable.
- Add per-ticker machine-readable reasons for the skipped/unavailable side
  (map `eval_result is None` and missing-source states to a small typed reason
  set). Internal diagnostic warnings stay out of the taxonomy.
- Aggregate from `AccumulationScreenResponse.observation_candidates` +
  `total_tickers_checked`/`tickers_skipped`; do not re-query.

**Note for criterion 11 / Slice E:** because capture is universe-wide `pass`
with no screen applied, the dataset inherently cannot support screener
recall/precision claims — screening must be applied at analysis time. Slice E's
`contains_control_population` marker should reflect this reality (there is no
screen-rejected control today), and any recall claim must be blocked until the
open design question in the Slice C finding is resolved.

**Files:** `backfill_signal_observations_use_case.py`,
`accumulation_screen.py` (DTO rollup if needed),
`analyze_signal_backfill_commands.py` (render + `to_dict`).

**Tests:** counts reconcile (universe = evaluated + skipped-by-reason);
every excluded ticker has a reason; survivorship note present when membership
source is current-universe; JSON keys asserted present.

**Close:** focused use-case + command tests + `git diff --check`.

---

## Slice C — Golden truncated-DB fixture + reconciliation

**Status:** DONE — `tests/application/use_case/test_dq_003_truncated_backfill.py`
(full suite 5574 passing, test-only, no `src/` change). Closes criterion 1 and
marks criteria 2 and 10 satisfied. Surfaced a finding: the real backfill path
disables every reject gate so it can only emit `screen_result="pass"`, hence
the "control" is a second evaluated `pass` ticker and invariant 4 is proven as
distinct-identity non-overwrite (see the "Slice C finding (2026-07-21)"
subsection in `audit_data_quality.md`).

**Goal:** *prove* point-in-time correctness and idempotence. Closes criterion 1;
hardens 2 and 10.

**Contracts:**

- One compact SQLite fixture physically truncated at T, containing: ≥1 selected
  ticker, 1 rejected control, 1 missing/unavailable input, 1 planted future row
  (T+1).
- Test asserts: canonical semantic projection matches expected; indicator
  warm-up windows end at T; the planted future row is excluded; a rerun produces
  no duplicates/drift; candidate and control rows (same PIT cutoff) never
  overwrite each other. Volatile audit metadata (`captured_at`) validated
  separately, not byte-compared.

**Files:** `tests/fixtures/dq_003/…` (fixture builder + committed DB or
deterministic seed), `tests/.../test_dq_003_truncated_backfill.py`.

**Close:** the fixture test passes on a clean rebuilt DB + `git diff --check`.

---

## Slice D — Fail-closed + separation tests (parallel after C)

**Goal:** close criteria 4, 7, 8.

- Holiday/retry/partial-failure fixtures → fail-closed session handling with
  visible errors (not silent skips).
- Negative test: single-ticker inspection cannot write or count as canonical
  (guards criterion 7 even though no inspection writer exists yet).
- Test: explicit capture is idempotent independently of label generation
  (`generate_labels=False` then `True` does not duplicate observations).

**Files:** `tests/.../test_backfill_signal_observations_use_case.py` (+ new
holiday/retry fixtures).

---

## Slice E — Candidate-only eligibility guard (parallel after C)

**Goal:** close criterion 11. Candidate-only datasets are ineligible for
screener recall/filter-value claims.

- Coordinate with DQ-006 (readiness owns recall). Minimum here: a typed marker
  on the capture output (e.g. `contains_control_population: bool`) so a
  downstream consumer can refuse recall claims when it is false.

**Files:** capture response DTO + a guard/assertion consumed by readiness later.

---

## Doc obligations already applied

- `audit_data_quality.md` DQ-003 State, audit-requirement bullet, criterion 6,
  and the "Lean identity amendment (2026-07-21)" subsection with deferral
  triggers are amended to match this plan.

## Verification defaults for each slice

Per `AGENT_QUICKSTART.md`: focused tests for touched behavior, architecture
boundary tests for the adapter/application seam (Slice A), full suite after the
schema/identity-touching slices (A, C), and `git diff --check` every slice.
