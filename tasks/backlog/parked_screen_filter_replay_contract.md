# Ready — Accumulation Screen Hard-Filter Replay Extract Contract Audit

Status: `COMPLETED` — audit/extract-contract slice (tournament still blocked)

Activated: 2026-07-31 for the expected near-term `ml-saham` hard-filter
tournament. The historical `parked_` filename is retained so existing backlog
links do not break.

Source: supersedes the filter/control-population half of
`parked_screen_rejected_controls_and_universe.md`.

## 1. Task Metadata

- Task type: Spike / Research with a bounded `ml-saham` extract-contract
  implementation
- Priority: Medium for this audit slice
- Semantic classification: `NON_SEMANTIC`; live screen/capture behavior and the
  canonical corpus are unchanged
- Primary owner: `ml-saham` — read-only extraction, conformance tests, and audit
  report
- Corpus authority: `ai-saham` — source predicates, observation contract, and
  any separately authorized future corpus extension
- AI usage: No AI involved

## 2. Chosen Decision

Audit exactly the four application gates that can classify an evaluated
accumulation candidate as non-pass, using ADR-056's canonical feature window
`features_by_window["7"]`:

1. Market-cap floor.
2. Piotroski F-Score floor.
3. Accumulation-score floor.
4. Signal-score floor.

Implement a read-only extractor and pure replay classifier in `ml-saham` for
these four gates only. The current live application predicates and their
first-match ordering are the semantic reference. Do not enable gates during
capture and do not persist replay results into `ai-saham` SQLite.

This audit decides whether ADR-056 is sufficient for a later tournament. It
does **not** choose the tournament threshold grid or publish precision/recall
results.

Implement this option only.

## 3. Exact Filter Scope

Current canonical order and semantics:

| Order | Replay gate ID | Application authority | Required captured input | Enabled condition | Reject condition / result |
|---:|---|---|---|---|---|
| 1 | `screen.accum.market_cap_floor` | `AccumulationCandidateStructuralFilter.apply` | `features_by_window.7.candidate.fundamentals.market_cap_idr` | threshold `> 0` | fundamentals absent, value missing, or value below floor → `rejected_flow` |
| 2 | `screen.accum.piotroski_floor` | `AccumulationCandidateStructuralFilter.apply` | `features_by_window.7.candidate.fundamentals.piotroski_f_score` | threshold `> 0` | fundamentals absent, value missing, or value below floor → `rejected_flow` |
| 3 | `screen.accum.accum_score_floor` | `AccumulationCandidateSignalAssessor.assess` | `features_by_window.7.candidate.accum_score` | explicit enabled flag | value below floor → `rejected_flow` |
| 4 | `screen.accum.signal_score_floor` | `AccumulationCandidateSignalAssessor.assess` | `features_by_window.7.signal.assessment.score` | explicit enabled flag | assessment absent or value below floor → `rejected_signal` |

Classification is first-match-wins in that order. A replay must preserve the
short circuit and return one of:

```text
pass | rejected_flow | rejected_signal | unextractable_contract
```

`unextractable_contract` is reserved for an unsupported/malformed observation
shape or an extraction-path failure. It is not ordinary provider/input
missingness.

### Explicitly outside this filter scope

- `min_net_buy_days` is not a positive-flow filter. In
  `AccumulationCandidateEvaluator.evaluate`, it checks
  `len(window_summaries) < min_net_buy_days` before candidate creation. With
  capture value `1`, it is the minimum usable-broker-summary observability
  boundary. It defines which names reach the four filters; it is not a fifth
  tournament gate.
- Resistance/setup/risk gates and final `TradeSetup.action` are not screen hard
  filters in this task.
- Display bands such as ENTER/WATCH/AVOID and coiled-spring presentation
  thresholds are not capture pass/reject filters.
- Sector breadth post-processing, sorting, rank, and top-N display are not in
  scope.
- Windows `30` and `90` may be checked for contract presence but must not become
  additional prediction/sample units in this slice. A later multi-window filter
  policy requires its own decision because ADR-056 stores one outcome unit per
  ticker/session.

The audit report must verify these source pointers against current code before
claiming completion. If ownership or ordering changed, update this task before
implementing a stale mirror.

## 4. Which Behavior Replay Must Match

Use interpretation **C**, grounded in **A**:

- **A — authority:** the live accumulation screener predicates and ordering are
  the canonical semantics, even while current configured floors are zero/off.
- **B — capture:** `disable_score_filters=True` plus zero structural floors is
  only the population/data producer. Matching its all-pass outcome is not the
  research objective.
- **C — replay:** apply explicitly supplied counterfactual non-zero policies to
  the capture-neutralized ADR-056 corpus using the exact A predicates,
  missing-input behavior, and first-match ordering.

The audit must prove that C can conform to A. It must not treat B as the filter
policy and must not claim that a handwritten `ml-saham` approximation is
verified production behavior.

## 5. Product And Dependency State

`ml-saham` currently marks screen hard filters as **SKIPPED** because production
floors are zero/off. That roadmap statement remains current.

This task is READY only as preparatory contract work requested before likely
retuning. Completing the audit does not ship or unskip the tournament. A later
decision checkpoint must update the `ml-saham` roadmap when exact policies are
approved.

Dependency on
`tasks/backlog/export_verified_policy_snapshot_for_ml_challenges.md`:

- This audit may map fields, implement the raw extractor, and prove pure
  predicate conformance before policy snapshots land.
- A tournament must not call a baseline `production`, publish WIN/LOSE, or
  support production-policy decisions until it selects the same compatibility
  cohort and verifies the required `production_policy_snapshot.v1` plus
  cross-repository golden vectors.
- There is no fallback to handwritten packaged policy JSON as production
  authority.

## 6. Intended Cohort Contract

The audit targets exactly:

```text
purpose              = ACCUMULATION_DISCOVERY
observation contract = learning_observation.accumulation_discovery.v2
compatibility_id      = explicit caller-selected value
unit                  = unique (ticker, session_date)
canonical feature     = features_by_window["7"] only
```

Current measured cohort on 2026-07-31, for reproducibility of the initial
audit only:

```text
compatibility_id = sha256:005363021f7f792071e43d12506aeefe474abf4fbd7d0a45f823b417e95e84c1
observations     = 1,890
sessions         = 42
tickers          = 45
```

The implementation must accept an explicit compatibility ID. If the database
contains multiple accumulation cohorts and none is supplied, this audit fails
closed; it must not auto-select the largest cohort. Wrong-purpose,
wrong-contract, untagged, mixed-cohort, legacy-shape, and duplicate
ticker/session rows are excluded with reconciled reason counts.

The measured ID is not a permanent default. A later clean-break cohort must be
selected explicitly and audited independently.

## 7. Denominator And Label Contract

Use three named populations; never call them all “the universe”:

1. **PIT membership set** — membership resolved by `ai-saham` for the capture
   session. This full set is not reconstructable from observation rows alone.
2. **Capture-evaluated set** — unique ticker/session ADR-056 observations in the
   selected compatibility cohort. This is PIT-tradable and broker-observable.
   Its canonical window-7 pack is the hard-filter replay denominator; windows
   30/90 do not create extra rows or predictions.
3. **Metric-evaluable set** — replay-denominator rows with an available primary
   challenge outcome at H=10. Only this later set enters precision/recall or
   false-block metrics.

For this audit:

- Reconcile the capture-evaluated set by unique ticker/session.
- Report extraction state for every row and every gate.
- Distinguish an explicit missing canonical input from a missing payload path:
  - explicit `null`/absent value inside a recognized ADR-056 candidate contract
    follows the application gate's missing behavior;
  - missing/invalid ADR-056 window or candidate contract is
    `unextractable_contract` and cannot be silently treated as a rejection.
- Report broker/source-unavailable names only when a persisted, joinable source
  supplies them. The current corpus alone cannot enumerate the complete PIT
  membership denominator.
- Do not claim full-universe recall. Future tournament metrics are explicitly
  conditional on the capture-evaluated broker-observable population.

The later tournament checkpoint must name:

- primary outcome: `ml-saham` protocol `accum_path_v1`, H=10 excess versus IHSG;
- the binary winner definition required for precision/recall;
- treatment of missing H=10 forward bars and incomplete horizons;
- whether corpus `price_path.accum_10d.v1` is a secondary diagnostic only;
- embargo/folds/min-N; and
- all denominator counts before and after label availability.

This audit may measure H=10 availability, but it must not invent the binary
winner threshold.

## 8. Exact Audit Deliverables

### `ml-saham` — owned implementation

Create or update exactly these work products:

1. `docs/challenge_screen_hard_filter_replay.md`
   - source-to-payload mapping table for all four gates;
   - missing-state truth table and first-match ordering;
   - canonical-window-7 lock and proof that windows 30/90 do not multiply N;
   - selected cohort and denominator reconciliation;
   - numeric/null/unextractable coverage per gate;
   - H=10 metric-availability counts;
   - `SUFFICIENT_FOR_REPLAY` or `INSUFFICIENT_NEEDS_CORPUS_EXTENSION` verdict;
   - no tournament WIN/LOSE verdict.
2. `data_contract.md`
   - add the screen-hard-filter row to Product challenge extract contracts.
3. `src/ml_saham/challenge/panel_screen_filters.py`
   - read selected observations through the existing read-only connection and
     single-cohort utilities;
   - extract the four raw inputs without threshold policy invention;
   - expose a pure first-match classifier receiving an explicit typed policy;
   - return typed extraction/reconciliation results; no writes or artifacts.
4. `tests/fixtures/golden/accum_screen_hard_filters.json`
   - live-shaped, redacted ADR-056 pass, each first-match rejection, explicit
     missing input, and malformed/unextractable examples.
5. `tests/test_challenge_payload_contracts.py`
   - call the shipped extractor/classifier against the golden fixture;
   - assert paths, missing semantics, order, boundary equality, disabled gates,
     and forbidden fallbacks.
6. `tests/test_challenge_live_smoke.py`
   - explicit compatibility ID;
   - reconcile selected, extracted, explicit-missing, unextractable, and H=10
     available counts against the maintainer DB;
   - fail on silent zero-hit or mixed-cohort extraction.
7. `tests/test_challenge_screen_filter_replay.py`
   - read-only/write-tripwire test;
   - no production row/page-count growth after a representative audit;
   - compact artifact boundary test if the audit command emits a report.
8. `scripts/check_challenge_contracts.sh`
   - include the new golden contract test in the existing CI ship gate.

No `ai-saham` Python file changes in this audit slice.

### `ai-saham` — source verification and close record

- Verify the four application pointers and current cohort through read-only
  inspection.
- Record the `ml-saham` implementation commit and audit verdict in this task's
  completion record.
- If the verdict is insufficient, create a separate proposed corpus-extension
  task. Do not implement that extension inside this audit.

## 9. Pass/Fail Definition For Corpus Sufficiency

Return `SUFFICIENT_FOR_REPLAY` only when all are true:

- Exactly one explicit compatibility cohort is selected.
- Every selected row declares `canonical_window=7` and supplies the recognized
  `features_by_window["7"]` contract; 30/90 are not additional sample units.
- Every selected unique ticker/session produces either four typed raw input
  states or an independently reconciled `unextractable_contract` reason.
- Recognized explicit missing inputs are distinguishable from extraction/schema
  failure.
- Numeric, explicit-missing, unextractable, duplicate, wrong-contract,
  wrong-purpose, wrong-cohort, and H=10 unavailable counts reconcile to their
  parent populations.
- The shipped pure classifier matches the four application predicates on
  golden boundary vectors, including equality, disabled gates, missing values,
  and first-match ordering.
- No fallback reads root/legacy fields for canonical v2 rows.
- The audit states that metrics are conditional on the broker-observable
  capture-evaluated denominator.
- Read-only and storage invariants pass.

Return `INSUFFICIENT_NEEDS_CORPUS_EXTENSION` when any required raw input state
cannot be distinguished from payload-contract failure, PIT provenance is
insufficient for the intended claim, or denominator reconciliation fails.

Numeric coverage below 100% is not automatically insufficient: market-cap or
Piotroski `null` is a replayable canonical missing state when the recognized
contract proves that meaning. Silent absence caused by the wrong payload path
is insufficient.

## 10. Storage Contract

The audit and replay design must not grow the production database.

Measured baseline on 2026-07-31 (informational, not stable acceptance values):

- `data/db/data.db`: 1.2 GiB physical file with about 682 MiB free SQLite pages.
- Mean `decision_payload_json + artifact_json`: about 175.3 KiB per observation.
- Selected cohort observation JSON: about 323.6 MiB total.
- `learning_observations` table: about 326.3 MiB.

Hard invariants:

- Use `ml_saham.data.aisaham_read.connect` (`mode=ro`) for the shared database.
- Do not insert or update any `ai-saham` production table.
- Do not create a row per filter, threshold, fold, policy, or tournament run.
- Row-level hypothetical pass/reject values are in-memory and ephemeral.
- If a report artifact is emitted, persist only compact mappings, counts,
  metrics, hashes, and summaries under gitignored `ml-saham/artifacts/`.
- Do not copy ADR-056 payloads into artifacts.
- A future corpus extension must report bytes added per observation and
  projected annual growth before authorization.
- A meaning-changing extension is a clean-break replacement, never a parallel
  old/new canonical population.

Expected `ai-saham` SQLite growth for this slice: exactly zero rows and zero
pages.

## 11. Architecture Impact

```md
Layer plan:
- Domain: ai-saham not touched; ml-saham typed replay policy/result only
- Application: ai-saham not touched; ml-saham pure extraction/classification and reconciliation
- Infrastructure: ai-saham not touched; ml-saham existing read-only SQLite connector only
- Adapter: no ai-saham surface; optional ml-saham audit command stays thin
- Documentation/governance: mapping report, data contract, CI extract gate, and task close record
```

- New dependency: No.
- Determinism: Same cohort + payload + explicit replay policy must produce the
  same classification and counts.
- Production persistence: Forbidden.
- Live SignalEngine/RiskEngine/TradeSetup/Action: unchanged.

## 12. Audit Close Criteria

- [x] Consumer, four-filter scope, metric family, and near-term need are named.
- [ ] Every deliverable in section 8 exists in its owning repository.
- [ ] The current application pointers and first-match order are reverified.
- [ ] An explicit compatibility ID is required and mixed cohorts fail closed.
- [ ] All population, extraction, missingness, and H=10 availability counts
      reconcile.
- [ ] The sufficiency verdict follows section 9 without subjective override.
- [ ] Golden and live-shaped tests call shipped extract/classifier code.
- [ ] Read-only tripwire and zero-row/zero-page-growth tests pass.
- [ ] `ml-saham` challenge extract CI gate passes.
- [ ] `ml-saham` full relevant tests and Ruff/lint gates pass under its own
      repository instructions.
- [ ] `ai-saham` documentation `git diff --check` passes; Ruff is required only
      if a separately authorized Python change occurs.
- [ ] Completion record contains both repository commits and the measured
      verdict.

## 13. Tournament Decision Checkpoint — Not Yet Authorized

After the audit closes, record all of these before changing the `ml-saham`
roadmap from SKIPPED or implementing tournament metrics:

1. Exact enabled filter combination(s).
2. Exact thresholds/grid and why each candidate exists.
3. Verified cohort-bound production policy snapshot IDs/digests.
4. Primary H=10 binary winner definition and secondary metrics.
5. Denominator/missing/unavailable rules.
6. Fold, embargo, min-N, and provisional/INCONCLUSIVE rules.
7. Baseline/challenger IDs and artifact contract.
8. Human decision that the production knobs are actually candidates for
   retuning.

Until then, the hard-filter tournament remains product-SKIPPED. The audit is
useful preparation, not permission to invent or tune thresholds.

## 14. Capture Follow-Up Boundary

Genuine capture-time `screen_result != "pass"` rows are **not implementable in
this ticket**.

If the audit verdict is `INSUFFICIENT_NEEDS_CORPUS_EXTENSION`:

- identify the exact missing input/state/provenance or denominator contract;
- propose the smallest separate `ai-saham` task with semantic classification,
  clean-break scope, storage estimate, and negative tests;
- require explicit user authorization before coding it.

The audit may recommend that follow-up. It may not enable capture gates, create
a second filtered capture mode, dual-write observations, or manufacture
`rejected_*` controls.

## 15. Do Not Interpret This As

- Do not equate `screen_result="pass"` with a positive forward outcome.
- Do not call the broker-observable corpus a full PIT-membership census.
- Do not treat `contains_control_population` as corpus-level recall authority.
- Do not replay the capture-neutralized all-pass policy as the research result.
- Do not include `min_net_buy_days` in the four hard-filter tournament.
- Do not include risk/setup/display/ranking behavior in this extractor.
- Do not auto-select the largest compatibility cohort.
- Do not treat a missing payload path as an ordinary null input.
- Do not write replay rows or artifacts into `ai-saham` SQLite.
- Do not claim `baseline=production` before verified policy snapshots and
  conformance vectors exist.
- Do not unskip the tournament roadmap before section 13 is approved.

## 16. Required Reading For Implementation

### `ai-saham`

- `AGENT_QUICKSTART.md`, `AGENTS.md`, `TASK_TEMPLATE.md`, `BOUNDARY.md`
- `docs/adr/ADR-056-accum-corpus-session-observation-and-accum-path-labels.md`
- `src/application/services/accumulation_candidate_structural_filter.py`
- `src/application/services/accumulation_candidate_signal_assessor.py`
- `src/application/services/accumulation_candidate_evaluator.py`
- `src/application/services/accumulation_observation_fingerprint.py`
- `tasks/backlog/export_verified_policy_snapshot_for_ml_challenges.md`

### `ml-saham`

- Repository agent instructions
- `BOUNDARY.md`, `data_contract.md`
- `docs/challenge_extract_contract.md`
- `docs/challenge_product.md`, `docs/challenge_product_roadmap.md`
- `src/ml_saham/data/aisaham_read.py`
- `src/ml_saham/data/observation_cohort.py`
- Current `challenge/panel*.py`, golden payload tests, live smoke, and CI
  contract script

## 17. Completion Record

- Audit completed date: 2026-07-31
- Selected compatibility ID: `sha256:005363021f7f792071e43d12506aeefe474abf4fbd7d0a45f823b417e95e84c1`
- `ai-saham` task/docs commit: (this commit — completion record only; no Python)
- `ml-saham` implementation commit: `7cc13b0d2d221ecc7f92ad70344649384671a329`
- Extracted / explicit-missing / unextractable counts by gate:
  - market_cap: numeric 765 / explicit_missing 1125 / unextractable 0
  - piotroski: numeric 765 / explicit_missing 1125 / unextractable 0
  - accum_score: numeric 1890 / missing 0
  - signal_score: numeric 1890 / missing 0
- Capture-evaluated / H=10 metric-evaluable counts: 1890 selected / 1485 H=10 AVAILABLE
- Storage before/after: zero production SQLite growth (read-only)
- Verdict: `SUFFICIENT_FOR_REPLAY`
- Separate follow-up task, if any: none required for extract sufficiency
- Tournament checkpoint status: `BLOCKED`
- Source pointers re-verified: structural filter + signal assessor first-match order matches §3
