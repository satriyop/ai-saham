# Make Risk-Gate Skips Explicit And Close The Fundamentals PIT Coverage Hole

Status: `FIXED / VERIFIED` — RiskEngine unknown-gate handling and the
fundamentals PIT limit remain verified; the separately re-vetted accumulation
hard-filter defect now has a coordinated schema-15 producer/consumer fix.
Sequence: **3 of 8** — see `tasks/backlog/00_SEQUENCE_accum_baseline_and_learning_loop.md`

> **In the config-edit batch.** This task touches `config/risk_engine.yaml`,
> which is identity-material, so it must land **before the config freeze**
> alongside tasks 1 and 2 — not during the corpus accumulation window.

## Independent Re-vet — 2026-08-08

Vetted against current code at `081de41c`; documentation was treated as backup.
The five recorded slice commits exist, but the original task combined two different
decision paths and its completion record overstates closure.

### Verdict by scope

| Scope | Verdict | Current evidence |
|---|---|---|
| Risk-gate missing input | `FIXED / VERIFIED` | `GateOutcome.UNEVALUABLE` is typed in domain; every configured gate emits it deliberately; `AssessRiskGateEvaluator` records ordered unknown gates and applies the typed aggregate policy |
| Config-driven aggregate policy | `FIXED / VERIFIED` | `surface` and `block` are validated; invalid values fail closed; production composition roots inject the same resolved policy |
| Cohort identity | `FIXED / VERIFIED BY LATER WORK` | Contrary to the historical completion note and stale YAML comment, active snapshot v4 includes `risk.accum.unevaluable_policy`; mutating it forks `compatibility_id` |
| Operator visibility | `FIXED / VERIFIED` | Shared decision display feeds CLI and TUI; OPEN/BLOCKED output names unknown gates |
| Fundamentals PIT backfill | `HONESTLY UNAVAILABLE / VERIFIED` | Existing Stockbit path still exposes only a current F-score/current market cap; historical rows contain only derived NPM/revenue growth and no historical inputs needed to reconstruct either field safely |
| Accumulation hard filter | `FIXED / VERIFIED` | Active threshold without a provider raises an explicit configuration error; typed schema-15 provenance distinguishes disabled, passed, missing-value rejection, and below-threshold rejection |
| Aggregate-policy observation provenance | `OPEN / TRACKED AS TASK 09` | The raw risk audit preserves per-gate unknowns, but the aggregate policy declares no own `observation_result_fields`; an unevaluable-policy block is not directly distinguished in the canonical candidate/trade-setup fields |

### Live read-only evidence

`company_fundamentals` remains unchanged in the relevant dimensions:

- 9,014 rows; 8,541 rows have null `piotroski_f_score` and null
  `market_cap_idr`.
- 473 complete live-snapshot rows cover all 303 tickers.
- First honest complete coverage is 2026-07-08 for 273 tickers and 2026-07-09
  for the remaining 30.
- No shares-outstanding series or historical F-score component set exists in
  the current source tree. Re-fetching cannot create honest pre-cutoff values.

Current `--window all` risk-audit totals grew to 8,034 window-observations while
the historical missing-input counts stayed fixed:

| Gate | pass | triggered | skipped | not evaluated | unknown rate |
|---|---:|---:|---:|---:|---:|
| FundamentalGate | 3,606 | 129 | 4,299 | 0 | 53.5% |
| FreeFloatGate | 3,858 | 612 | 2,280 | 1,284 | 28.4% |
| BandarGate | 3,075 | 1,626 | 1,437 | 1,896 | 17.9% |
| LiquidityGate | 6,750 | 1,155 | 0 | 129 | 0.0% |

### Pre-fix hard-filter counterexamples

Current code and tests explicitly preserve both counterexamples:

1. `fundamentals_provider=None` plus `min_market_cap_idr > 0` returns
   `rejected=False`, `screen_result=None`, and no typed explanation. The active
   filter is silently not evaluated and the candidate is admitted.
2. A present provider returning no market cap or no Piotroski value returns the
   same `rejected_flow` as a genuine numeric threshold failure. The observation
   cannot tell data absence from an evaluated rejection.

This violates the task's acceptance criteria that no path turns missing data into
an unrecorded pass and that the structural filter record unknown separately. It
does not currently affect the shipped default because both hard-filter thresholds
are zero, but enabling either threshold activates the ambiguity.

### Vetted fix contract — implemented 2026-08-08

The implementation follows the vetted hard-filter contract and its
identity/persistence blast radius:

1. An active filter with no wired provider raises
   `StructuralFilterConfigurationError`; provider exceptions propagate. Neither
   becomes ticker-level missing data or an admitted candidate.
2. `StructuralFilterDecision` is the typed application contract. It distinguishes
   disabled, evaluated pass, missing-value rejection, and below-threshold
   rejection while retaining `screen_result` as the existing coarse inclusion
   result.
3. The exact decision is transported through the use case and persisted in every
   7/30/90 window pack. Accumulation observation schema 15 is a clean break;
   schema 14 remains immutable historical material.
4. `screener.accum.hard_filters` formula v2 declares the persisted result path and
   the provider-unavailable configuration-error posture. The active compatibility
   identity therefore forks through both snapshot material and observation schema.
5. ml-saham independently accepts only schema 15, validates the exact structural
   decision in every window, recomputes purpose-specific diagnostic IDs with
   schema 15, and gives schema 14 no alias or reinterpretation.

The structural-filter prerequisite for task 04 is settled. Task 09 remains a
separate aggregate-policy provenance change and should still land before the
one-time corpus rebuild.

### Re-vet verification

```text
focused risk/filter/identity/PIT/display suite: 115 passed
ruff check src/ tests/: passed
ruff format --check src/ tests/: 1769 files already formatted
git diff --check: passed before this documentation edit
data manifest: exit 0, no warnings
source contracts: exit 0, WARN (including the same optional fundamentals nulls)
source reconciliation: exit 0, WARN; company_fundamentals PIT coverage PASS
database SHA-256 before/after audits:
bbfb38d91ebcb9aa649389266dd67243baaf7cd27cd7ffabd5fc0105ba211c33
```

## 1. Task Metadata

**Task Title**
Stop treating "no data" as an implicit pass in RiskEngine gates, and close the
point-in-time fundamentals coverage hole that causes it.

**Task Type**
Bugfix (risk-material — forks cohort identity)

**Priority**
High

---

## 2. Problem Statement

A RiskEngine gate that cannot evaluate is recorded as `skipped` and the
candidate proceeds as if the gate had passed. Operators cannot distinguish
"this ticker was checked and is clean" from "this ticker was never checked."

### Measured evidence (2026-08-04, `data/db/data.db`, 7,764 accum window-observations)

Gate outcomes:

| Gate | pass | triggered | **skipped** | not_evaluated |
|---|---|---|---|---|
| FundamentalGate | 3,348 | 117 | **4,299 (55.4%)** | 0 |
| FreeFloatGate | 3,630 | 588 | **2,280 (29.4%)** | 1,266 |
| BandarGate | 2,928 | 1,545 | **1,437 (18.5%)** | 1,854 |
| LiquidityGate | 6,498 | 1,149 | 0 | 117 |

Skip reasons are uniform and data-driven:
`"no fundamental data — gate skipped"` (4,299),
`"Free float data unavailable — gate skipped"` (2,280),
`"no bandar flow data — gate skipped"` (1,437).

**The blocks themselves are legitimate** — `BLOCKED_STRUCTURAL` (1,854) decomposes
exactly as Liquidity 1,149 + FreeFloat 588 + Fundamental 117, and
`BLOCKED_EXECUTION` (1,545) as Bandar Big Dist 1,149 + Small Dist 396, all with
concrete numeric reasons. This task is **not** about loosening gates.

### Root cause of the fundamental skip rate

`company_fundamentals` holds 9,014 rows across 303 tickers, but:

- `piotroski_f_score` is **NULL in 8,541 / 9,014 rows (94.7%)**
- `market_cap_idr` is **NULL in 8,541 / 9,014 rows (94.7%)**
- Rows carrying those fields exist only from **2026-07-08** onward

The accum corpus spans 2026-06-02 → 2026-08-04. Under point-in-time lookup
(correctly bounded since `34fc4360`), every session before 2026-07-08 finds no
usable fundamentals, so FundamentalGate is skipped. `min_market_cap_idr` and
`min_piotroski` structural filters
(`accumulation_candidate_structural_filter.py:44-98`) are inert for the same
reason, and `risk_engine.yaml`'s 1T IDR market-cap floor cannot be applied.

**This directly constrains task 4:** any historical corpus rebuild deeper than
2026-07-08 will carry a permanently degraded risk assessment unless fundamentals
history is backfilled first.

---

## 3. Desired Outcome

- A gate that could not evaluate produces a **distinct, typed outcome** that is
  neither `pass` nor `triggered`, and it is visible in operator output and in
  the observation payload.
- Fundamental field coverage (`piotroski_f_score`, `market_cap_idr`) is
  backfilled to at least the depth the corpus rebuild needs, **or** the
  achievable depth is measured and recorded as a hard constraint on task 4.
- The screen makes an explicit, configured decision about what an unevaluable
  gate means. Default recommendation: **surface, do not block** — an unknown is
  not a reason to reject, but it must never be silently laundered into a pass.

Out of scope: changing any gate threshold.

---

## 4. Non-Goals

- No loosening of `market_cap_floor_idr`, `median_tx_floor_idr`,
  `min_free_float_pct`, `min_piotroski`, or the bandar distribution labels.
- No new risk gates.
- No blocking on unknown data by default (that would reject ~55% of the
  universe; if desired it must be an explicit config choice with its own review).
- No new data provider — use existing Stockbit fundamentals fetch paths.
- No corpus purge/re-capture (task 4).

---

## 5. Architecture Impact Assessment

- **Domain:** risk gate outcome value object gains an explicit
  unevaluable/unknown state. Pure change.
- **Application:** `AssessRiskGateEvaluator` and
  `accumulation_candidate_structural_filter.py` — decide and apply skip policy;
  aggregate an "unknown gate" count onto the assessment.
- **Infrastructure:** fundamentals repository/provider — backfill write path for
  historical `piotroski_f_score` / `market_cap_idr` if the provider exposes
  history.
- **Adapter:** display the unknown state (thin: formatting only).

New dependency: **No.**
Determinism: **No change** (same inputs → same outputs).
Persistence: **Possibly** — a backfill writes rows to `company_fundamentals`; no
schema change expected. Confirm before writing.
Warm-up data: **No.**
Policy in adapter: **No.**

```md
Layer plan:
- Domain: add explicit unevaluable outcome to the risk gate result VO
- Application: AssessRiskGateEvaluator skip policy + unknown-count aggregation;
  structural filter treats missing fundamentals explicitly
- Infrastructure: fundamentals backfill write path (existing provider only)
- Adapter: render the unknown state; no policy
```

---

## 6. AI Usage Declaration

**No AI involved.**

---

## 7. Risk, Signal, And Evidence Authority Considerations

Affected: **RiskEngine**, **TradeSetup** (via risk outcome), structural filter.
SignalEngine unaffected.

**Does this change what can produce ENTER/WATCH/AVOID?** Only if the configured
skip policy is set to block. Under the recommended default (surface, do not
block) the *action* distribution is unchanged and only the *explanation*
changes. Whichever is chosen must be stated in the commit message, because the
answer determines whether cohort identity forks.

**Evidence promotion:** none. Risk gates are not evidence groups.

---

## 8. Data & Persistence

- **Read:** `company_fundamentals`, `shareholding_composition`,
  `broker_daily_flow`, `candles`.
- **Written:** backfilled `company_fundamentals` rows only.
- **Schema change:** No (verify).
- **Old vs new source semantically equivalent?** The backfill must answer this
  explicitly. A `piotroski_f_score` computed today and stamped with a historical
  `fetched_date` is **not** point-in-time honest — it embeds look-ahead. If the
  provider cannot supply as-of-then values, **do not fake the date**: record the
  true fetch date and let PIT lookup correctly skip. State the finding and let
  task 4 absorb the reduced depth. This trips the Data Contract Audit Gate in
  `AI_AGENT_CHECKLIST.md`.

---

## 9. Acceptance Criteria

- [x] An unevaluable gate is a distinct outcome in the domain VO, the payload,
      and operator output.
- [x] No code path converts "no data" into `pass` without recording it.
- [x] Skip policy is config-driven with a documented default.
- [x] Fundamentals backfill either lands with honest PIT dates, or a written
      finding records why it cannot and what depth is achievable.
- [x] Gate skip rates re-measured after the backfill and recorded.
- [x] Deterministic; works without AI; no non-goals violated.
- [x] ADR-024 (signal/risk engines) considered.
- [x] **Lint Gate** passes.

---

## 10. Slices (each slice = one commit)

**Slice 1 — Measure and pin.**
Test asserting the current silent-skip behavior; a script/query that reports
per-gate skip rates so the improvement is measurable.
Commit: `test(risk): pin silent gate-skip behavior and record skip rates`

**Slice 2 — Explicit unevaluable outcome.**
Domain VO + evaluator + payload. No policy change; skips still do not block.
Commit: `fix(risk): make unevaluable gates an explicit outcome`

**Slice 3 — Configured skip policy.**
`risk_engine.yaml` key for skip handling, defaulting to current behavior.
Tests for each policy value.
Commit: `feat(risk): config-driven policy for unevaluable gates`

**Slice 4 — Fundamentals PIT investigation + backfill.**
Determine whether the provider exposes historical fundamentals. Backfill if PIT
honest; otherwise write the finding. Re-measure skip rates.
Commit: `feat(data): backfill point-in-time fundamentals coverage`
(or `docs(data): record fundamentals PIT depth limit`)

**Slice 5 — Surface it.**
Show unknown-gate count in `screen accum` output and the shared decision
display, so an operator sees "3 gates unknown" rather than an implied all-clear.
Commit: `feat(cli): surface unevaluable risk gates in accum output`

---

## 11. Testing Expectations

- Each gate: data present → pass/trigger; data absent → unevaluable, never pass.
- Structural filter with null `market_cap_idr` / `piotroski_f_score` records
  unknown rather than silently admitting.
- Skip policy config values each produce the documented behavior.
- PIT regression: a backfilled fundamental dated after a session must **not** be
  visible to that session's assessment (guards against re-introducing the
  `34fc4360` look-ahead class of bug).

Offline. `pytest -m "not tui"`. Ruff before close.

---

## 12. Documentation Impact

- README: **No.** New config option: **Yes** (skip policy).
- Limitations: **Yes** — record achievable fundamentals PIT depth; it bounds
  task 4.

---

## 13. Required Reading

- `AGENT_QUICKSTART.md`, `TASK_TEMPLATE.md`, `DEFINITION_OF_DONE.md`
- `AI_AGENT_CHECKLIST.md` — Data Contract Audit Gate (slice 4 trips it)
- `tasks/done/fix_risk_pit_cutoff_lookahead.md` — the PIT contract this must not break
- `config/risk_engine.yaml`

---

## 14. Do Not Interpret This As

- **Not** a mandate to loosen gates. Blocks are legitimate and evidenced.
- **Not** permission to stamp recomputed fundamentals with historical dates to
  manufacture coverage. That is look-ahead contamination.

---

## 15. Completion Record

The 2026-08-05 record below is the original five-slice completion record. Its
hard-filter closure and identity comment were superseded by the independent
2026-08-08 re-vet and completion amendment in section 16.

- **Completed date:** 2026-08-05

- **Slice commits:**
  - Slice 1 — `52f4d1b5` `test(risk): pin silent gate-skip behavior and record skip rates`
  - Slice 2 — `a2b7b8c8` `fix(risk): make unevaluable gates an explicit outcome`
  - Slice 3 — `68f1b60c` `feat(risk): config-driven policy for unevaluable gates`
  - Slice 4 — `41fbc401` `docs(data): record fundamentals PIT depth limit`
  - Slice 5 — `1babc705` `feat(cli): surface unevaluable risk gates in accum output`

- **Skip rates before → after:** unchanged, and correctly so — no backfill
  landed and no persisted observation was rewritten
  (`scripts/report_risk_gate_skip_rates.py --window all`, 7,764 accum
  window-observations):

  | Gate | before | after |
  |---|---|---|
  | FundamentalGate | 4,299 / 55.4% | 4,299 / 55.4% |
  | FreeFloatGate | 2,280 / 29.4% | 2,280 / 29.4% |
  | BandarGate | 1,437 / 18.5% | 1,437 / 18.5% |
  | LiquidityGate | 0 / 0.0% | 0 / 0.0% |

  The 55.4% is now *explained* rather than fixed: it is the exact consequence
  of fundamentals coverage starting 2026-07-08 against a corpus beginning
  2026-06-02. Future runs will re-measure differently because gates now emit a
  typed outcome, but the persisted vocabulary (`skipped` /
  `blocked_on_missing`) is unchanged, so old and new rows stay comparable.

- **Fundamentals PIT depth achieved (and hard limit for task 4):** no honest
  backfill was possible — see `docs/data_fundamentals_pit_depth.md`.
  `piotroski_f_score` and `market_cap_idr` are both single current scalars from
  the one endpoint the provider calls (`/keystats/ratio/v1`), the F-score is
  returned precomputed with no local calculator and no per-period components in
  the response, and no shares-outstanding value exists anywhere in `src/` to
  reconstruct historical market cap from. Faking the date was refused.

  **Hard limit:** honest coverage begins **2026-07-08** (273 tickers) /
  **2026-07-09** (30 tickers); all 303 tickers covered from then on. Nothing
  earlier is recoverable by re-fetching. A cohort spanning earlier sessions
  carries a permanently degraded fundamental risk assessment, so task 4 should
  start the deep cohort at 2026-07-08 or later, or treat pre-cutoff sessions as
  a separate cohort. Do not set `min_market_cap_idr` / `min_piotroski` above 0
  for any pre-cutoff session — the structural filter *rejects* on a missing
  value (unlike the gates, which go unevaluable), so it would empty the universe.

- **Skip policy default chosen + reasoning:** `risk_engine.gates.unevaluable_policy: surface`
  (record the unknown, never block). Chosen because `block` would reject ~55% of
  the universe on a data-coverage gap rather than on risk — an explicit non-goal
  — and because keeping the default at today's behaviour means cohort identity
  does not fork, so this task could land in the config-edit batch without
  invalidating the corpus. Anything other than `surface` / `block` fails closed
  at resolve time. `surface` is deliberately *not* part of the production policy
  snapshot identity; switching to `block` must add it there first (recorded in
  `config/risk_engine.yaml` next to the key).

- **Test / Lint result:** `pytest -m "not tui"` 6,525 passed / 31 skipped;
  `pytest -m tui` 73 passed / 10 skipped (TUI code was touched, so the fast
  selector alone was not treated as a close criterion). `ruff check src/ tests/`
  and `ruff format --check src/ tests/` both clean whole-repo. `git diff --check`
  clean. Data Contract Audit Gate run for slice 4: all three commands exit 0,
  `source-contracts` and `reconcile-sources` report WARN, every
  `company_fundamentals` finding is pre-existing `NULLS_IN_OPTIONAL_FIELD`, no
  FAIL, no schema change.

---

## 16. Completion Amendment — Structural Filter (2026-08-08)

Semantic classifications: `SEMANTIC_ENGINE`, `EVIDENCE_CONTRACT`,
`OBSERVATION_SCHEMA`, and `CONFIG_MATERIAL`. The live defaults remain disabled,
but enabling either fundamentals threshold can no longer silently admit a
candidate when composition omitted the provider.

The clean-break implementation is coordinated across ai-saham and ml-saham:

- ai-saham emits and strictly validates typed structural-filter provenance in
  accumulation observation schema 15, binds the policy posture in hard-filter
  snapshot formula v2, and preserves schema 14 as historical.
- ml-saham independently requires schema 15, validates every 7/30/90 structural
  decision, recomputes the purpose-specific diagnostic compatibility ID with
  schema 15, and keeps diagnostic artifacts report-only/non-promotable.
- No production SQLite row was inserted, migrated, rewritten, repaired, or
  backfilled. All test writes used temporary databases.
- Task 09 remains separate; this amendment does not claim aggregate
  unevaluable-policy observation provenance is fixed.

Final verification on the exact uncommitted implementation state:

```text
ai-saham focused structural/filter/identity/readiness suite: 247 passed
ai-saham readiness regression slice: 7 passed
ai-saham full pytest: 6644 passed, 41 skipped
ai-saham Ruff check: passed
ai-saham Ruff format check: 1771 files already formatted
ai-saham git diff --check: passed

ml-saham compileall with external pycache: passed
ml-saham focused diagnostic/payload/acceptance suite: 53 passed
ml-saham challenge contract gate: 39 passed
ml-saham git diff --check: passed
ml-saham broad suite: 417 passed, 11 failed; eight are the existing unrelated
  curriculum baseline failures, and three are sibling-workspace sandbox writes
  (two Numba cache attempts and one export). No changed challenge test failed.

data manifest: exit 0, no warnings
source contracts: exit 0, WARN (pre-existing optional-field coverage)
source reconciliation: exit 0, WARN (pre-existing partial-source and duplicate
  market-context/regime identity findings); company_fundamentals PIT PASS
database SHA-256 before/after audits:
bbfb38d91ebcb9aa649389266dd67243baaf7cd27cd7ffabd5fc0105ba211c33
```
