# Fix — Risk Assessment Ignores The Historical Cutoff (PIT Look-Ahead)

Status: `READY`

Source: look-ahead audit 2026-07-31 (measured against `data/db/data.db`).

## Task Metadata

- Task type: Bugfix
- Priority: High — historical risk verdicts and the ml-saham risk challenge are
  currently untrustworthy; live behavior is unaffected.
- Semantic classification: `SEMANTIC_ENGINE` only.
  - `SEMANTIC_ENGINE`: deterministic decision behavior changes — historical risk
    gate verdicts differ (measured: 30 observations flip from blocked to
    allowed). Bump `SEMANTIC_ENGINE_VERSION` (section F).
  - **Not** `EVIDENCE_CONTRACT`. See "Why not EVIDENCE_CONTRACT" below; this was
    reclassified 2026-07-31 after checking precedent. Do not re-add it.
  - Not `OBSERVATION_SCHEMA`: payload shape and field names are unchanged. The
    corpus forks by cohort, not by schema version (see Cohort Fork).

### Why not `EVIDENCE_CONTRACT`

The rule is "evidence meaning, availability, authority, or derivation changes".
None of those apply here:

| Candidate reason | Verdict |
|---|---|
| Candle evidence feeding LiquidityGate | Same table, same rows, same meaning, same authority. Only **which window the engine selects** changes — that is engine behavior, not evidence semantics. |
| `RiskAssessment.snapshot_date` / `indicators` | Recorded, but not production evidence under ADR-057: no configured gate consumes them (TechnicalGate is opt-in and off), so they carry no Action authority. |
| New / removed / re-authorized evidence | None. No producer, no authority registration, and no evidence availability changes. |

Repo precedent agrees. `EVIDENCE_CONTRACT_VERSION` has been bumped five times,
always for evidence authority or composition changes (`c93363ab` removing
producer-config authority, `532135c6` swapping market_context for
sector_context, `4262ae34` removing flags-only assessment,
`654166e2` ATTACHED_REQUIRED authority). The closest analogue to this task is
`930c81db` — "wire market_context and availability into observation scoring",
a fix to data that was silently defaulting wrong on the way into scoring. It
bumped `SEMANTIC_ENGINE_VERSION` and the observation schema, and left
`EVIDENCE_CONTRACT_VERSION` alone. Same shape as this fix.

Counter-reading, recorded for honesty: if you treat "the 20-candle liquidity
window" as a derived evidence object, its derivation did change. That reading is
defensible but is not how this repo has used the constant, and the practical
stakes are nil — the lean hash forks on either bump, and the contaminated corpus
is purged regardless. The deciding factor is signal: bumping the evidence
version for a change that touches no evidence semantics erodes its meaning for
future readers.
- Chosen decision: thread an explicit `as_of_date` cutoff from
  `AssessRiskRequest` down through indicator aggregation and gate-candle
  enrichment. **Implement this option only.**

## Problem Statement

`AssessRiskGateEvaluator.evaluate` builds indicators through
`AggregateIndicatorsUseCase`, which has no cutoff parameter. The child
SMA/EMA/RSI use cases anchor on `latest_date` from
`MarketDataRepository.get_date_range(ticker)` — the newest row in the cache.
The evaluator then takes `latest_snapshot.date` and reuses it as the `end_date`
for LiquidityGate candle enrichment:

```python
# src/application/use_case/assess_risk_gate_evaluator.py
latest_snapshot = agg_response.snapshots[-1]
gate_ctx = self._build_gate_context(request, latest_snapshot.date, latest_snapshot)
...
# Use snapshot_date as end_date to prevent look-ahead in backtests.   <- false
candles = self._repository.get_candles(request.ticker.upper(), end_date=snapshot_date)
```

The comment claims look-ahead protection; the code does the opposite. The
correct session date is already available — `AccumRiskInputsBuilder` sets it on
`GateContext.snapshot_date` — but the evaluator never reads it for this purpose.

During historical replay the risk step therefore evaluates a past session using
data up to the newest cached candle.

### Measured evidence (2026-07-31, `data/db/data.db`)

| Fact | Value |
|---|---|
| `ACCUMULATION_DISCOVERY` observations | 1,890 (42 sessions, 2026-06-02 → 2026-07-30) |
| 7-day `risk.snapshot_date` later than session | 1,755 |
| `risk.snapshot_date` equal to session | 135 |
| Distinct `risk.snapshot_date` values in the whole corpus | 3 (`2026-07-28` ×1771, `2026-07-29` ×74, `2026-07-30` ×45) — i.e. the cache head on each backfill run |
| `risk.gate_context.snapshot_date` equal to session | 1,890 (the correct date is present but unused) |
| Observations where the LiquidityGate median-tx leg decided | 1,873 |
| Contaminated 20-candle window sharing **zero** candles with the correct window | 901 |
| **Blocked but would pass at the correct cutoff** | **30** (all GOTO) |
| Blocked at both cutoffs | 12 |
| Allowed but would block at the correct cutoff | 0 |

The 30 false blocks are real, not a rounding artifact: GOTO traded roughly
10–130B IDR/day in June and collapsed below 2B IDR/day in late July, so the
July window falls under the 5B floor while the actual June window is far above
it. Each false block is `BLOCKED_STRUCTURAL` and also short-circuited
BandarGate evaluation.

### Scope of contamination (verified)

| Component | Contaminated? | Why |
|---|---|---|
| `LiquidityGate` median-20d-tx leg | **Yes** | reads `ctx.recent_candles` |
| `TechnicalGate` | Yes when enabled | reads `ctx.latest_snapshot`; **not** in the default gate list (opt-in via swing `--with-technical-gate`) |
| `FundamentalGate`, `FreeFloatGate`, `BandarGate` | No | read pre-built PIT fields |
| `LiquidityGate` market-cap leg | No | pre-built field |
| `RiskAssessment.snapshot_date` / `indicators` | **Yes** (recorded) | set from the unbounded snapshot; no Action authority |
| `TradeSetup.action` | Indirectly | via `gate_triggered` / `gate_is_structural` only |
| Accum score components, signal, `TradeSetup.snapshot_date` | No | verified session-aligned on all 1,890 rows |
| Ownership / free float | No | `stockbit_shareholding._read_cache` filters `COALESCE(report_date, fetched_date) <= as_of`; all 854 late-`fetched_at` rows have `report_date <= session` |

## Desired Outcome

- A risk assessment carrying a cutoff can never read a candle dated after that
  cutoff, directly or transitively.
- `RiskAssessment.snapshot_date` equals the latest indicator date at or before
  the cutoff.
- Re-captured historical observations show `risk.snapshot_date <= session_date`
  for every row, and `risk.gate_context.snapshot_date` agrees with the session.
- Live behavior (no cutoff supplied) is byte-identical to today.
- The accumulation corpus contains exactly one cohort — the clean one.
  Contaminated rows are purged, not retained beside it.

## Non-Goals

- No change to gate thresholds, gate ordering, or the configured gate list.
- No new gates; no enabling TechnicalGate on the accum path.
- No provider, scraper, or fetch changes.
- No changes to accum scoring, signal scoring, MCE, or label math.
- No repair or rewrite of existing observation rows in place.
- No `research accum evaluate` revival (see `BOUNDARY.md`).
- No changes inside `~/dev/ml-saham` (separate repo, tracked below).

## Hard Invariants

1. When `as_of_date` is set, **no** repository read on the risk path may return
   or retain a candle with `date > as_of_date`.
2. When `as_of_date` is `None`, behavior is unchanged (live path).
3. `AssessRiskRequest.as_of_date` is the single cutoff authority for the risk
   path. `GateContext.snapshot_date` remains a domain audit/display field and
   must agree with it when both are present.
4. Insufficient data at the cutoff must fail explicitly. It must never fall back
   to unbounded reads.
5. Every production composition root listed below passes the cutoff. Component
   tests do not prove production wiring.
6. The fix must fork the learning cohort. A code-only change that leaves
   `compatibility_id` unchanged is a failed implementation. The fork is required
   even though contaminated rows are purged — it is the correct semantic signal
   and the safety net if a purge is ever partial.
7. Clean break on the corpus: after this task, exactly one accumulation cohort
   exists. No compatibility filter, alias, or "prefer newest" reader logic may
   be introduced to make two cohorts coexist.

## Architecture Impact

- New dependency: No
- Affects determinism: No (removes a hidden dependency on wall-clock cache state)
- Persistence schema change: No
- Warm-up data: Yes — indicator warm-up is already handled inside the child use
  cases and must continue to work relative to the bounded `end_date`
- Orchestration/policy in an adapter: No

```md
Layer plan:
- Domain: not touched (gate classes and GateContext are already correct)
- Application: add and thread the `as_of_date` cutoff through
  AssessRiskRequest → AssessRiskGateEvaluator → AggregateIndicatorsUseCase →
  Compute{SMA,EMA,RSI}UseCase, and through RiskEngine / pipeline call sites;
  bump SEMANTIC_ENGINE_VERSION
- Infrastructure: not touched (repository already supports `end_date`)
- Adapter: not touched (no new CLI flags; existing commands keep current behavior)
```

## Exact Contract

### A. Request DTOs

Add `as_of_date: date | None = None` to each, defaulting to `None`:

| DTO | File |
|---|---|
| `AssessRiskRequest` | `src/application/dto/assess_risk.py` |
| `AggregateIndicatorsRequest` | `src/application/use_case/aggregate_indicators_use_case.py` |
| `ComputeSMARequest` | `src/application/use_case/compute_sma_use_case.py` |
| `ComputeEMARequest` | `src/application/use_case/compute_ema_use_case.py` |
| `ComputeRSIRequest` | `src/application/use_case/compute_rsi_use_case.py` |

Semantics: `None` means "latest cached data" (live). A value means a hard
inclusive cutoff.

### B. Compute use cases (SMA / EMA / RSI)

Replace the unbounded end anchor. Current shape in
`compute_sma_use_case.py` (mirror exactly in EMA and RSI — verify each, do not
assume they are identical):

```python
earliest_date, latest_date = date_range
available_days = (latest_date - earliest_date).days + 1
days_back = min(request.days, available_days)
start_date = latest_date - timedelta(days=days_back - 1)
end_date = latest_date
```

Required shape:

```python
earliest_date, latest_date = date_range
end_date = latest_date if request.as_of_date is None else min(latest_date, request.as_of_date)
if end_date < earliest_date:
    return <the existing empty response for this use case>
available_days = (end_date - earliest_date).days + 1
days_back = min(request.days, available_days)
start_date = end_date - timedelta(days=days_back - 1)
```

- The coverage warning must be computed from the bounded `available_days`.
- The empty-response branch must reuse the existing no-data response construction
  in each use case, not a new shape.

### C. `AggregateIndicatorsUseCase`

Pass `as_of_date=request.as_of_date` into all three child requests. No other
change; the response DTO is unchanged.

### D. `AssessRiskGateEvaluator`

File: `src/application/use_case/assess_risk_gate_evaluator.py`

1. Validate first, before any repository read:

```python
if (
    request.as_of_date is not None
    and request.gate_context is not None
    and request.gate_context.snapshot_date != request.as_of_date
):
    raise ValueError(...)  # name both dates in the message
```

   Validate only when `as_of_date is not None`. When it is `None`, the existing
   `GateContext.snapshot_date` value is untouched and unvalidated.

2. Pass `as_of_date=request.as_of_date` into `AggregateIndicatorsRequest`.

3. Change the candle boundary in `_build_gate_context` to the cutoff:

```python
candle_end_date = request.as_of_date if request.as_of_date is not None else latest_snapshot.date
```

   Keep passing `latest_snapshot` itself for `ctx.latest_snapshot`; only the
   candle `end_date` changes.

4. When `as_of_date` is set and `agg_response.has_values` is false, raise a
   `ValueError` that names the cutoff. Do **not** retry unbounded and do **not**
   emit the current "run `saham fetch market`" message unchanged, which would be
   misleading at a historical cutoff.

5. Correct the stale comment on the `get_candles` call (it currently claims the
   opposite of what the code did).

### E. Production composition roots

All of these must be updated. This list is exhaustive; report anything else you
find rather than silently extending scope.

| # | Call site | Required change |
|---|---|---|
| 1 | `src/application/services/screen_assessment_pipeline.py` (~L150, pre-built GateContext path) | pass `as_of_date=as_of_date` — this is the accum capture/backfill path |
| 2 | `src/application/services/risk_engine.py` `assess()` (~L124) | pass its existing `as_of_date` parameter through |
| 3 | `src/application/services/risk_engine.py` `assess_with_context()` (~L148) | add `as_of_date: date \| None = None` parameter and pass it through |
| 4 | `src/application/services/swing_backtest_trade_setup_attributor.py` (~L38) | pass `as_of_date=signal_date` — **same bug, swing backtest path** |
| 5 | `src/application/services/plan_swing_risk_trade_setup.py` — all four branches of `assess_initial()` (~L115, ~L134, ~L142, ~L154) | pass `as_of_date=snapshot_date` |

**Correction to an earlier draft of this task**, which classified plan swing as a
purely live path and told the implementer to hardcode `None`. That was wrong.
`plan swing` exposes `--as-of YYYY-MM-DD` ("Point-in-time as-of date … pins
effective session; default: live today"), and
`plan_swing_commands.py` resolves `today = parse_as_of_option(as_of) or
date.today()`. That value becomes `request.today`, which
`PlanSwingDecisionComposer` passes as `snapshot_date` to both
`build_gate_context()` and `assess_initial()`.
`DailySetupLensImpactUseCase._build_request()` is a second caller that sets
`today=as_of_date`. So:

- Hardcoding `None` would leave `plan swing --as-of <past date>` reading
  indicators at the cache head while its GateContext is stamped at the
  requested session — the exact incoherence this task removes. The
  `as_of_date`/`snapshot_date` agreement check cannot catch it, because that
  check only fires when `as_of_date` is not `None`.
- The `with_technical_gate` branch is the worst case: TechnicalGate reads
  `latest_snapshot`, so it would be contaminated whenever it is enabled.
- Passing `snapshot_date` is a genuine no-op live, because the cutoff resolves
  as `min(latest_date, as_of_date)` and `date.today()` is never earlier than the
  cache head.

Because live callers now always supply a cutoff, the evaluator's
insufficient-data error keeps its `saham fetch market` hint instead of replacing
it — a past cutoff can also fail simply because the cache lacks that history.
Do not gate that message on a wall-clock comparison; the evaluator must stay
deterministic.

Deliberately left on the live (`None`) path — confirm each still behaves
identically:

- `src/application/use_case/run_risk_analysis_workflow_use_case.py` (~L110)
- `src/application/use_case/run_risk_compare_use_case.py` (~L87)
- `src/application/use_case/run_accumulation_screen_workflow_use_case.py` (~L283)
- `src/application/use_case/assess_risk_trend_use_case.py` (aggregation, live)
- `src/adapters/cli/indicator_snapshot_commands.py` (aggregation, live)

### F. Cohort fork

Bump **exactly one** constant in
`src/domain/value_objects/signal_semantic_contract.py`:

```python
SEMANTIC_ENGINE_VERSION = "1.4"   ->   "1.5"
```

Leave `EVIDENCE_CONTRACT_VERSION` at `"1.5"`. This is deliberate, not an
oversight — see "Why not EVIDENCE_CONTRACT" in Task Metadata. Do not bump it to
"be safe": the lean hash already forks on the engine bump alone, so a second
bump buys no isolation and only blurs what the constant signals.

The constant is folded into `resolve_lean_semantic_compatibility_id`
(`src/application/services/lean_observation_identity.py`) alongside
`CANDIDATE_OBSERVATION_SCHEMA_VERSION` and `EVIDENCE_CONTRACT_VERSION`, so
bumping the engine version alone forks `compatibility_id`. Verify the fork
empirically after re-capture; do not assume it.

Two tests pin the exact version strings and must be updated in the same commit:

| File | Assertion |
|---|---|
| `tests/domain/value_objects/test_signal_semantic_contract.py` (~L91–92) | `ACCUMULATION_DISCOVERY.semantic_engine_version == "1.4"` |
| `tests/application/services/test_dq001_missing_vs_zero_authority.py` (~L229–232) | `SEMANTIC_ENGINE_VERSION == "1.4"` |

Both also assert `EVIDENCE_CONTRACT_VERSION == "1.5"`; that line stays
unchanged. Update only the engine-version assertions and the surrounding
comment, which currently reads "(v8 / engine 1.4 / evidence 1.5)".

`ACCUMULATION_DISCOVERY` is the only `SemanticContractDefinition` instance, and
pre-open uses its own separate constant
(`PRE_OPEN_SIGNAL_EVIDENCE_CONTRACT = "pre_open_signal_evidence.v3"`), so this
bump has no pre-open blast radius.

## Corpus Clean Break (purge, then re-capture)

**Decision (user, 2026-07-31): clean break.** The contaminated rows are purged,
not retained alongside the clean cohort. Rationale: keeping two cohorts leaves
rot that every future consumer must remember to filter, and `ml-saham` queries
`learning_observations` by `purpose` only — it has no cohort filter — so mixed
cohorts would silently inflate its panels.

Existing rows are immutable (`_immutable_insert`) and cannot be repaired in
place. Re-capture alone would **not** replace them: `observation_id` is a hash
over an identity that includes `compatibility_id`, so the version bump gives
every re-captured row a new primary key and both sets would coexist.

### Blast radius (measured 2026-07-31)

| Table | Rows removed | Note |
|---|---|---|
| `learning_observations` (`ACCUMULATION_DISCOVERY`) | 1,890 | two cohorts: `sha256:47a5d243…` (45), `sha256:69d73d45…` (1,845) |
| `learning_outcome_labels` | 4,050 | 3d ×1,710, 10d ×1,395, 20d ×945 — all regenerable |
| `learning_evaluations` (`ACCUMULATION_DISCOVERY`) | 1 | legacy/inert per `BOUNDARY.md` |
| `learning_track_snapshots` | 0 | accum has none |
| `setup_phase_ledger` | 0 deleted | 1,789 rows keep a stale `observation_id`; the column has **no** FK, so nothing breaks, and `backfill-phase-ledger` re-links them |

Pre-open observations (12 rows) and their labels are untouched.

### Steps

Run only after the code fix lands and the full suite plus Lint Gate pass.

1. Back up first. `data/db/data.db` is ~1.3 GB and the accum payloads are
   ~269 MB. A backup directory already exists at `data/db/backups/`.
2. Harden `scripts/purge_accum_learning_corpus.py` before use — it already does
   the right deletes in the right order (labels → evaluations → observations,
   dry-run by default, `--execute` to commit), but it opens SQLite **without**
   `PRAGMA foreign_keys = ON`. Add the pragma and the same enforcement check
   used by `connect_learning_database`, so a future child table cannot be
   silently orphaned. Do not otherwise rewrite the script and do not port it
   into `saham audit data` (see the detection task below).
3. Dry-run, confirm the counts match the table above, then execute:

```bash
python scripts/purge_accum_learning_corpus.py --db data/db/data.db
python scripts/purge_accum_learning_corpus.py --db data/db/data.db --execute
```

4. Re-capture over the same range. Resolve the universe name from the original
   run; do not guess it (the stored `universe_id` is a hash, `3ef45d48…`):

```bash
saham research accum backfill --universe <name> --start 2026-06-02 --end 2026-07-30
saham research accum labels --all-label-contracts
saham research accum backfill-phase-ledger
saham research accum status
```

5. Verify: exactly one `compatibility_id` present for
   `ACCUMULATION_DISCOVERY`, and every row satisfies
   `risk.snapshot_date <= session_date` and
   `risk.gate_context.snapshot_date == session_date`.
6. Record how many rows changed verdict versus the pre-purge measurements in
   this file (expected: 30 previously-blocked GOTO rows now allowed). Take this
   comparison from the numbers already recorded above — the old rows are gone by
   then, so it cannot be re-derived later.

## Required Reading

- `AGENT_QUICKSTART.md`, `AGENTS.md` / `CLAUDE.md`, `TASK_TEMPLATE.md`
- `DEFINITION_OF_DONE.md`, relevant `AI_AGENT_CHECKLIST.md` sections
  (this task trips the Data Contract Audit Gate)
- `BOUNDARY.md` — corpus authority split with `ml-saham`
- `docs/adr/ADR-056-accum-corpus-session-observation-and-accum-path-labels.md`
- `config/risk_engine.yaml` — confirm the configured gate list before changing
  anything

## Implementation Checklist

- [ ] Restate hard invariants and forbidden interpretations before editing.
- [ ] Add `as_of_date` to the five request DTOs.
- [ ] Bound `end_date` in all three compute use cases; verify each separately.
- [ ] Thread the cutoff through `AggregateIndicatorsUseCase`.
- [ ] Update `AssessRiskGateEvaluator`: validation, aggregation cutoff, candle
      boundary, explicit failure, stale comment.
- [ ] Update all five production composition roots in section E.
- [ ] Bump `SEMANTIC_ENGINE_VERSION` to `"1.5"`; leave
      `EVIDENCE_CONTRACT_VERSION` at `"1.5"`.
- [ ] Update the two tests that pin the version strings (section F).
- [ ] Add the tests in Testing Expectations, including every negative test.
- [ ] Run focused tests, architecture boundary tests, and the full suite.
- [ ] Lint Gate: `ruff check src/ tests/` and `ruff format --check src/ tests/`.
- [ ] `git diff --check`.
- [ ] Back up `data/db/data.db`.
- [ ] Add the FK pragma to `scripts/purge_accum_learning_corpus.py`.
- [ ] Purge (dry-run, confirm counts, then `--execute`).
- [ ] Re-capture, relabel, re-link the phase ledger.
- [ ] Verify exactly one cohort and zero rows with `risk.snapshot_date > session_date`.

## Testing Expectations

Required positive tests:

- Compute SMA/EMA/RSI with `as_of_date` set mid-history return no value dated
  after the cutoff, and the last value equals the unbounded run truncated to
  that cutoff.
- `AggregateIndicatorsUseCase` with `as_of_date` returns
  `snapshots[-1].date <= as_of_date`.
- `AssessRiskGateEvaluator` with `as_of_date` produces
  `RiskAssessment.snapshot_date <= as_of_date`.
- Live path (`as_of_date=None`) output is unchanged — assert against the current
  expected values, not against a re-derived expectation.

Required negative tests (these prove the bug cannot return):

- **Recording repository fake**: assert that every `get_candles` call made
  during a cutoff-bearing risk assessment passes `end_date <= as_of_date`, and
  that no call is made with `end_date=None` or a later date. Asserting only on
  the returned values is insufficient — it would pass against the current buggy
  code whenever the cache happens to end on the session date.
- **Regression fixture for the measured flip**: a ticker liquid in the window
  ending at the cutoff and illiquid in the window ending later (the GOTO shape).
  Assert LiquidityGate does **not** fire at the cutoff and **does** fire
  unbounded. This test must fail on today's code.
- Mismatched `as_of_date` vs `gate_context.snapshot_date` raises `ValueError`.
- No candles at or before the cutoff raises `ValueError` naming the cutoff, and
  performs no unbounded retry.
- Cutoff after the cache head behaves exactly like the live path.
- Cohort test: the same resolved config produces a different
  `semantic_compatibility_id` after the version bump.

All tests run offline against fakes or a temp SQLite file.

## Acceptance Criteria

- [ ] Behavior matches Desired Outcome.
- [ ] Works with AI disabled; deterministic for identical inputs.
- [ ] No non-goal violated; gate thresholds and gate list unchanged.
- [ ] Adapter thinness preserved — no adapter gained cutoff policy.
- [ ] All five composition roots pass the cutoff; grep confirms no remaining
      risk-path aggregation call without one.
- [ ] Every negative test above exists and fails on pre-fix code.
- [ ] Focused + boundary + full test suite pass.
- [ ] Lint Gate passes whole-repo.
- [ ] Corpus holds exactly one `ACCUMULATION_DISCOVERY` cohort, with zero rows
      where `risk.snapshot_date > session_date`.
- [ ] Pre-open observations and labels are untouched by the purge.

## Do Not Interpret This As

- Do not derive the cutoff from `date.today()`, `datetime.now()`, or the cache
  head anywhere on the risk path.
- Do not make `as_of_date` required, and do not change live behavior to "safer"
  bounded defaults.
- Do not fix only `AssessRiskGateEvaluator` and leave the compute use cases
  unbounded. Clamping the candle `end_date` while indicators still read the cache
  head leaves `RiskAssessment.snapshot_date` wrong and leaves TechnicalGate
  contaminated whenever it is enabled.
- Do not add a cutoff to `GateContext` as a second mutable copy, and do not let
  the evaluator silently prefer one date when the two disagree — raise.
- Do not treat the ownership `fetched_at` observation as a bug and add filtering
  there; the PIT filter is already correct and verified.
- Do not enable TechnicalGate, adjust the 5B liquidity floor, or "compensate"
  for the 30 newly-unblocked rows.
- Do not rewrite, patch, or re-stamp existing observation rows so they look like
  they were produced under the fixed engine.
- Do not skip the version bump because tests pass — silent cohort mixing is the
  failure mode it prevents.
- Do not also bump `EVIDENCE_CONTRACT_VERSION`. No evidence meaning,
  availability, authority, or derivation changes here, and the cohort forks on
  the engine bump alone.
- Do not purge before the code fix is merged and green. Purging first destroys
  the only baseline for confirming the 30 expected verdict flips.
- Do not purge without a backup, and do not widen the purge beyond
  `ACCUMULATION_DISCOVERY` — pre-open observations, tracks, and labels stay.
- Do not add a purge subcommand to `saham audit data` or anywhere else in the
  `saham` CLI. Reuse the existing script.
- Do not edit anything under `~/dev/ml-saham` from this task.

## Out-Of-Repo Follow-Up (not this task)

`ml-saham`'s gate panel reads `trade_setup` from the top level of the
observation payload, but ai-saham writes it under
`features_by_window["<window>"]`. Its score panel already handles the nesting
via `_pick_window_blob`; `panel_gates.py` does not. Measured effect: the risk
gate challenge sees 0 blocked rows out of 1,890 when the true count is 631, so
`challenge run risk.accum.hard_gates --against gate_off` currently compares
allow-all against allow-all.

Consequence for sequencing: fixing ml-saham *before* the purge and re-capture
would turn a visibly empty result into a plausible-looking result built on
contaminated blocks. Purge and re-capture first. This work belongs in the
sibling repo per `BOUNDARY.md` and must not be done here.

The clean break also removes the need for any cohort filter on the ml-saham
side: after the purge there is exactly one cohort, so only the payload-nesting
bug remains to fix there.

## Related Task

`tasks/backlog/audit_learning_corpus_pit_invariants.md` — adds the missing
`reconcile-sources` check that would have caught this class of defect. Separate
and lower priority; it must not block this fix.

## Completion Record

- Completed date:
- Implementation commit:
- Files changed:
- Composition roots updated:
- Commands run:
- Test result:
- Lint result:
- Backup taken (path / size):
- Purge dry-run counts vs expected (1,890 / 4,050 / 1):
- Purge executed at:
- Re-capture run (range / universe / new compatibility_id):
- Post-fix verification (cohort count, rows with `risk.snapshot_date > session_date`):
- Rows that changed verdict vs the pre-purge measurements:
