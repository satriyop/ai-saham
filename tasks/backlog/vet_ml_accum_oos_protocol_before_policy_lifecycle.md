# Vet The ACCUM OOS Protocol Before Policy-Lifecycle Unblock

Status: `VETTED FINDINGS / DESIGN FOLLOW-UP REQUIRED` — current code and the
live frozen cohort were inspected on 2026-08-09. The correctness defects below
are confirmed. Replacement statistical thresholds remain deliberately unlocked
and require an empirical protocol-design pass before implementation.

Sequence: must close before task 06 may treat an ml-saham `WIN` as sufficient
policy-proposal evidence. Corpus growth may continue in parallel.

## 1. Task Metadata

**Task title:** Make ACCUM fold construction session-native and separate
exploratory OOS evidence from policy-grade confirmation.

**Task type:** Spike / Research, followed by Bugfix and versioned protocol work.

**Priority:** High.

**Runtime owner:** `ml-saham`. `ai-saham` remains the deterministic corpus and
label producer and must not implement challenge folds or ML verdicts.

## 2. Problem Statement

`accum_path_v1` has useful fail-closed foundations: ordered walk-forward folds,
an embargo, train-only fitting, explicit cohort identity, and a rule preventing
one valid fold from becoming `WIN`. Those foundations are not yet a policy-grade
statistical contract.

Current executable facts:

- `n_folds=3`, `embargo_sessions=20`, `min_n_total=80`, `min_n_test=20`, and
  `min_folds_for_win=2`;
- the primary target is H10 excess return versus IHSG; H3/H20 are reported;
- split boundaries use unique observed dates on the normal path;
- fold eligibility uses ticker-row counts for minimum train/test size;
- IC is calculated by pooling ticker-session rows inside each fold;
- no final untouched confirmation holdout or multiple-trial correction is part
  of the `WIN` law;
- the live frozen cohort produces 585 H10-eligible rows across only 13 mature
  dates and currently forms zero folds (`BLOCKED_DATA`).

The headline row count therefore overstates temporal depth. LQ45 rows from one
session share market and regime exposure and must not be treated as independent
time evidence merely because they have different tickers.

## 3. Independently Vetted Findings

### ML-OOS-01 — the thin-calendar fallback does not implement a session embargo

Severity: **HIGH correctness defect**. Current active cohort impact: **not
triggered**, because it has at least four unique dates.

When `len(unique_dates) < n_folds + 1`, `time_purged_folds()` falls back to a
70/30 split over ordered rows and subtracts `embargo_sessions` from a row index.
Twenty rows are not twenty trading sessions. With a sufficiently broad
single-date panel, train and test may even contain the same session.

Required direction:

- remove the row-based fallback and fail closed, or implement a wholly
  session-native fallback;
- never convert session embargo units into ticker-row units;
- add mutation tests with many tickers but one to three dates.

### ML-OOS-02 — minimum N is row-based instead of session-based

Severity: **HIGH statistical-validity defect**.

Normal folds require only 15 train rows and 20 test rows. With roughly 45 LQ45
rows per session, a learned challenger can pass the mechanical gate with very
few independent train dates. The same weakness affects `min_n_total=80`.

Required direction:

- introduce explicit minimum unique train sessions and test sessions;
- retain row/ticker coverage as a separate cross-sectional gate;
- expose both row counts and session counts in fold artifacts and verdicts;
- fail closed when either temporal depth or cross-sectional coverage is absent.

Exact minimum-session values are **not locked by this task draft**. They must be
selected from fold-geometry simulations and the intended challenger complexity.

### ML-OOS-03 — two folds are a screening floor, not policy-grade confirmation

Severity: **HIGH authority/interpretation risk**.

The current `WIN` law permits two valid folds when both agree, the mean IC edge
exceeds 0.01, and the tail proxy passes. This is a good improvement over a
single-fold `WIN`, but two temporal blocks are too weak to establish regime
stability or support repeated model/challenger selection.

Required direction:

- label two-fold evidence explicitly exploratory/provisional for policy work;
- vet a stronger confirmation law, expected to require at least 3–5 usable
  temporal folds or an equivalently justified design;
- reserve a final chronological holdout that remains untouched during
  challenger, feature, threshold, and hyperparameter selection;
- do not weaken the current two-fold minimum while the replacement is vetted.

### ML-OOS-04 — pooled ticker-row IC lacks session-aware uncertainty

Severity: **MEDIUM-HIGH statistical-validity defect**.

Each fold computes one rank IC over all ticker-session rows. This can treat
cross-sectional rows exposed to the same session/regime as more independent
than they are. The verdict reports no confidence interval for the IC delta.

Required direction:

- vet daily cross-sectional IC followed by aggregation across sessions;
- add session-block uncertainty estimation, such as a date-block bootstrap or
  another explicitly justified dependence-aware method;
- report fold-wise session counts, IC delta, uncertainty, missingness, and
  ticker coverage;
- define fail-closed behavior for sessions with undefined or too-thin IC.

### ML-OOS-05 — embargo is safe but its target scope is ambiguous and inefficient

Severity: **MEDIUM protocol-design debt**, not permission to shorten the gap.

Twenty sessions conservatively cover the longest reported H20 horizon, while
the verdict and learned target use primary H10. The current contract does not
state whether H20 is selection-relevant or diagnostic-only. A fixed H20 embargo
is safe against leakage but delays usable folds and may discard more training
history than the primary target needs.

Required direction:

- inventory every label/metric that can affect model fitting, selection,
  verdict, or promotion eligibility;
- derive purge/embargo from the maximum outcome interval that can influence
  those decisions;
- make H3/H20 authority explicit; diagnostic reporting must not silently affect
  selection;
- prefer label-interval-aware purging over an unexplained global gap;
- do not reduce 20 to 10 without proving that no H20-derived result influences
  selection or authority.

### ML-OOS-06 — current corpus is operationally healthy but statistically shallow

Severity: **BLOCKED_DATA**, not a producer defect.

The frozen ai-saham cohort is `CHALLENGE_INPUT_READY`, but the current read-only
ml-saham panel has 585 H10-eligible rows across 13 mature dates and zero folds.
More ticker rows from the same sessions do not resolve this blocker.

Required direction:

- continue prospective growth under the exact frozen compatibility ID;
- monitor mature unique sessions, not only observation/label row totals;
- do not unlock task 06 merely when the current splitter first emits two folds;
  first close ML-OOS-01 through ML-OOS-05 and run the accepted versioned
  protocol on the grown cohort.

## 4. Desired Outcome

The accepted replacement protocol must:

1. construct every train, embargo, and test boundary from authoritative ordered
   sessions;
2. prove there is no label-interval overlap between train and OOS test data;
3. distinguish temporal sample depth from cross-sectional ticker coverage;
4. keep model fitting and all preprocessing inside train data for each fold;
5. separate exploratory model selection from final confirmation;
6. quantify uncertainty and stability using the session as the dependence unit;
7. keep exact cohort, population, policy snapshot, adapter, protocol, and
   artifact identities;
8. remain deterministic, offline, read-only toward ai-saham, and human-review
   only; and
9. fail closed when any required identity, coverage, fold, or uncertainty gate
   cannot be proven.

## 5. Non-Goals

- No ai-saham scoring, RiskEngine, SignalEngine, TradeSetup, or Action changes.
- No automatic YAML/config edits or automatic promotion.
- No relaxation of current fold/embargo gates to make the live cohort pass.
- No random row shuffle or IID K-fold over ticker-session rows.
- No historical corpus rewrite, compatibility alias, or mixed-cohort panel.
- No arbitrary universal claim that a fixed number of sessions is statistically
  ideal for every challenger.
- No implementation in ai-saham; only cross-repository sequencing lives here.

## 6. Architecture And Semantic Impact

Runtime boundaries expected in `ml-saham`:

- Data/read boundary: read exact ai-saham cohort and authoritative session/label
  interval data without writes.
- Challenge contracts: version the protocol and verdict law.
- Evaluation/statistics: own the session-native splitter, metrics, uncertainty,
  nested selection, and confirmation holdout.
- Artifacts: record the new protocol identity and complete fold geometry.
- CLI: thin rendering only; no split or verdict policy.
- Curriculum: not touched.

Expected semantic classification:

- `PROTOCOL_CONTRACT`;
- `VERDICT_SEMANTICS`;
- `ARTIFACT_SCHEMA` if existing artifacts cannot represent the new geometry and
  uncertainty fields.

This requires a versioned clean break such as a newly accepted protocol ID. Old
artifacts remain historical and must never reopen as eligible under the new
law.

New dependency: undecided. Prefer existing deterministic numerical tooling;
adding a statistics dependency requires explicit review and a reproducibility
lock.

Persistence changes: no upstream SQLite change. ml-saham artifact schema may
change after the design is accepted.

AI usage: no AI runtime. AI may assist review but is non-authoritative.

## 7. Required Design Vet Before Coding

Produce a fold-geometry report over synthetic and live-shaped calendars that
compares candidate contracts across:

- 13, 23, 44, 60, 84, 120, and 250 mature sessions;
- sparse/interior-missing session calendars;
- one ticker, LQ45-like coverage, and uneven ticker coverage;
- H10-only selection versus any selection involving H20;
- fixed-rule challengers versus learned ridge/LightGBM challengers;
- expanding versus bounded rolling train windows;
- candidate minimum train/test sessions and fold counts;
- a final untouched chronological holdout;
- multiple-challenger search and its correction/confirmation rule.

The report must recommend exact values separately for:

1. exploratory/provisional output;
2. policy-proposal eligibility;
3. promotion-review evidence.

Do not begin runtime implementation until those values and their failure states
are accepted.

## 8. Acceptance Criteria

- [ ] ML-OOS-01 row-based fallback is removed or replaced with session-native,
      fail-closed behavior.
- [ ] Split tests prove train/embargo/test session disjointness and correct
      label-interval purging.
- [ ] Minimum train/test temporal gates use unique sessions; row/ticker coverage
      is reported and gated separately.
- [ ] Many rows from one or two sessions cannot produce a valid fold.
- [ ] Every learned transform/model/hyperparameter is fit or selected only
      inside its permitted training boundary.
- [ ] Exploratory folds cannot be mistaken for final confirmation.
- [ ] A final untouched chronological holdout or an accepted equivalent is
      enforced for policy-grade evidence.
- [ ] Fold and aggregate metrics include session-aware uncertainty and explicit
      undefined/missing behavior.
- [ ] Multiple-trial/challenger selection cannot reuse the same OOS result as an
      unqualified confirmatory result.
- [ ] Costs, tail behavior, turnover where applicable, and regime stability are
      reported or explicitly block policy-grade eligibility.
- [ ] The protocol and any changed artifact schema receive new identities;
      historical artifacts remain historical only.
- [ ] Production-facing runs still require an explicit compatible cohort and
      verified production snapshots.
- [ ] Read-only tripwires prove ai-saham SQLite is unchanged.
- [ ] Focused splitter, verdict, runner, artifact round-trip, mutation, and live
      read-only tests pass.
- [ ] ml-saham's mandatory contract and CI gates pass on the final state.
- [ ] Task 06 is updated only after the accepted protocol produces qualifying
      evidence for the exact frozen cohort.

## 9. Testing Expectations

Tests must be offline and deterministic except for an explicitly marked
read-only maintainer-DB smoke test. Required cases include:

- one date with more than `min_n_total` rows;
- two/three dates with large cross-sections;
- exact embargo boundary at H10 and H20;
- missing/interior sessions;
- newest labels still immature;
- duplicate ticker/session rows;
- two folds with apparent edge but no confirmation holdout;
- challenger/hyperparameter selection followed by untouched confirmation;
- undefined daily IC, constant scores, sparse ticker coverage, and regime
  concentration;
- protocol/artifact identity mutation and historical reopen rejection.

## 10. Documentation And Completion Gate

Update ml-saham's protocol, data contract, challenge product documentation,
acceptance matrix, artifact contract, and operator output together with the
implementation. Update this cross-repository sequence and task 06 afterward.

This backlog item is not complete merely because the live corpus grows enough
for the current v1 splitter to emit folds. Completion requires an accepted
policy-grade design, versioned implementation, executable leakage/session
proof, and a fresh read-only result from the exact compatible cohort.
