# S6 BCI Authority Spike

## Scope

Investigated whether BCI `CLUSTER` should retain full scoring authority
(`+12.5` points, `ScoreForeignFlowUseCase._score_bci`) when aggregate foreign
flow for the same observation window is negative. This is a read-only
evidence spike against the persisted `data/db/data.db` SQLite database. No
scoring, config, or runtime code was changed. No tests were added.

Not changed:
- `src/application/use_case/score_foreign_flow_use_case.py`
- `src/application/services/flow_confirmation_evidence_builder.py`
- `config/accumulation_screener.yaml`

`git diff --check` on those three files is empty (verified below).

## Code Paths Reviewed

- **BCI scoring**: `ScoreForeignFlowUseCase._score_bci()` in
  `src/application/use_case/score_foreign_flow_use_case.py:193-201`. Grants
  `cluster_points=12.5` for `bci_label == "CLUSTER"`, `stable_points=4.2` for
  `"STABLE"`, `0` otherwise. No dependency on aggregate flow direction,
  magnitude, or setup phase.
- **BCI source data**: `bci_label`/`bci_tier1_count` are computed in
  `src/application/services/accumulation_candidate_evaluator.py:175-211` —
  counts distinct Tier-1 broker codes (`config/accumulation_screener.yaml
  broker_quality.tier1.brokers`) with positive net-buy lots over the screen
  window, then thresholds against `cluster_min_count` (3) / `stable_min_count`
  (1). It only counts *how many* Tier-1 desks are net buyers — it has no
  awareness of whether the ticker's aggregate foreign flow for the same
  window is net positive or negative.
- **Persisted observation fields**: `AccumulationCandidate.to_dict()`
  (`src/application/dto/accumulation_screen.py:230-260`) — this is what lands
  in `candidate_observations.payload_json.candidate`.
- **Forward label source**: `src/application/use_case/
  generate_signal_forward_labels_use_case.py` writes
  `signal_forward_labels` rows keyed by `(ticker, signal_date, horizon,
  observation_captured_at)`; outcome/return fields come from
  `src/domain/value_objects/signal_forward_label.py`.

## Data Availability

- **DB path**: `data/db/data.db` (canonical — `saham.db` and
  `data/db/saham.db` have no `candidate_observations` / `signal_forward_labels`
  tables at all; `data/db/data.db` is the only populated DB found).
- **Observation count**: 19,317 total rows in `candidate_observations`; **0**
  have a non-empty `config_hash` (all rows predate the S1 canonical-identity
  fix — commit `bcbb3ac` — and carry the pre-S1 legacy identity: `workflow=''`,
  `config_hash=''`). This means the S1 multi-window duplication bug (3 rows
  per ticker/snapshot_date, one per `window_days` ∈ {7, 30, 90}) is present in
  100% of the available history. See "Data quality caveats" below.
- **Window filter field, exact path**: the `candidate_observations.window_sessions`
  *DB column* is `0` for every legacy row in this dataset (it was only ever
  populated by the post-S1 canonical writer) — filtering on that column
  returns zero rows and silently produces an empty result set. The window
  value actually lives inside `payload_json`. This spike filtered on
  `json_extract(payload_json, '$.candidate.window_days') = 7`. The sibling
  path `json_extract(payload_json, '$.request.window_days') = 7` returns the
  identical row set (verified: both give 6,983 rows for `=7`, 6,167 for
  `=30`, 6,167 for `=90`), since `candidate.window_days` is just the
  requested window echoed back on the result. Either JSON path works;
  **do not** filter on the `window_sessions` column for this legacy data.
- **Labeled observation count**: `signal_forward_labels` has 5,760 rows, all
  `horizon = SWING_10D` (no `TACTICAL_3D` / `ACCUM_20D` rows exist yet).
  5,760 have `outcome_label != UNAVAILABLE` and were used. 0 are
  `UNAVAILABLE`.
- **Date range**: `signal_date` from 2026-01-02 to 2026-06-15 (labels
  generated in a single backfill batch at `observation_captured_at =
  2026-07-07T20:29:33`, i.e. this is a retrospective backfill over one
  historical window, not a rolling walk-forward log — see caveats).
- **Horizon**: SWING_10D (10 trading days forward).
- **Universe/target filter**: all tickers with a `window_days=7` observation
  matching a labeled `(ticker, signal_date)` pair. No additional filtering.
- **Fields available** (all confirmed present via direct field inspection):
  - `bci_label`, `bci_tier1_count` — `candidate_observations.payload_json.candidate.{bci_label,bci_tier1_count}`
  - Aggregate foreign flow — closest persisted field is
    `candidate.total_net_value` (cumulative net foreign IDR value over the
    same `window_days` used to compute BCI). **This is a substitute, not the
    exact concept**: it is the raw cumulative net foreign value for the
    window, not a separately-labeled "aggregate flow direction" field. Sign
    of `total_net_value` was used as the positive/negative aggregate-flow
    split, per this task's instruction to use the closest persisted field
    when the exact concept is unavailable.
  - `net_buy_ratio`, `avg_flow_ratio` (foreign_flow_ratio) — present under
    `candidate.net_buy_ratio` / `candidate.avg_flow_ratio`.
  - Setup phase — present as `sub_signal_fingerprint.setup_phase_current`
    (values: `ACCUMULATION`, `COMPRESSION`, `BREAKOUT_CONFIRMATION`,
    `EXHAUSTION`, `DISTRIBUTION`, `FAILED`, `NONE`).
  - Forward return labels — `close_return`, `max_forward_return`,
    `max_adverse_excursion`, `outcome_label` in `signal_forward_labels`.
- **Fields missing**:
  - No dedicated "aggregate flow direction" or "aggregate flow ratio vs
    turnover/materiality" field distinct from `total_net_value` /
    `net_buy_ratio` exists in the persisted payload.
  - No `config_hash`-canonical identity for any row in this dataset — see
    caveats.
  - `signal_forward_labels.fingerprint_json` (the `SignalObservationFingerprint`)
    does **not** carry `bci_label`/`bci_tier1_count`/`total_net_value` at all
    — it was not usable as the join key content, only `(ticker, signal_date)`
    was usable for joining to `candidate_observations`.

### Data quality caveats (read before trusting the numbers below)

1. **No canonical join key.** Because every row in this dataset predates the
   S1 canonical-identity fix, `candidate_observations` has up to 3 rows per
   `(ticker, snapshot_date)` (one per `window_days`), and — even after fixing
   `window_days=7` — up to 18 duplicate rows per `(ticker, snapshot_date)`
   from repeated screen runs on the same day. `signal_forward_labels` has no
   `observation_captured_at` that matches any specific `candidate_observations
   .captured_at` (labels carry a single bulk-backfill timestamp
   `2026-07-07T20:29:33` for all 5,760 rows, unrelated to when each
   observation was originally captured). **The join used here is therefore
   `(ticker, snapshot_date)` only, with the *latest-captured-at* `window_days
   =7` row picked when duplicates exist.** This is a reasonable
   approximation, not an exact identity join.
2. **Duplicate-row disagreement is small but nonzero.** Across the 1,443
   `(ticker, snapshot_date)` groups with more than one `window_days=7` row,
   12 groups (0.8%) disagree on `bci_label` and 85 groups (5.9%) disagree on
   `total_net_value`'s sign/magnitude between duplicate rows. This adds small
   label noise to both bucket assignment and the outcome join; it does not
   change the buckets' order-of-magnitude conclusions below.
3. **Single historical window, not a walk-forward OOS test.** All 5,760
   labels come from one 5.5-month backfill batch (Jan–Jun 2026), generated in
   one run. This is a retrospective, single-period observational comparison
   — not the walk-forward, multi-period OOS validation referenced elsewhere
   in this project's tuning process. Treat the "material difference" finding
   below as directionally credible, not as full walk-forward OOS proof.
4. **`total_net_value` is a same-window proxy, not `net_buy_ratio`.** The
   task defines "aggregate foreign flow" generically; `total_net_value` (raw
   IDR) was used because it is the only field carrying signed aggregate
   magnitude for the same window BCI is computed over. `net_buy_ratio` (day-count
   ratio) is reported per-row in the underlying data script output but not
   used for bucketing, since it is a *day-count* ratio, not a flow-direction
   or flow-magnitude concept.

## Bucket Results

Only `window_days=7` observations were used (BCI computed over the same
7-session window as the live default `AccumulationScreenRequest.window_days`),
selected via `json_extract(payload_json, '$.candidate.window_days') = 7` per
the "Window filter field, exact path" note above — **not** the
`window_sessions` DB column, which is `0` for all legacy rows.
No CLUSTER-with-unknown-flow rows exist (`total_net_value` was populated for
every matched row), so that bucket is empty and omitted.

| Bucket | N | Positive close-return rate | Avg close return | Median close return | Avg max forward | Avg adverse | Profit factor |
|---|---:|---:|---:|---:|---:|---:|---:|
| CLUSTER + negative aggregate flow | 2780 | 0.360 | -3.53% | -3.07% | 7.69% | -11.44% | 0.462 |
| CLUSTER + positive aggregate flow | 2536 | 0.388 | -2.52% | -2.21% | 7.82% | -10.80% | 0.552 |
| non-CLUSTER + negative aggregate flow | 342 | 0.398 | -3.63% | -3.52% | 7.47% | -11.85% | 0.467 |
| non-CLUSTER + positive aggregate flow | 102 | 0.392 | -3.55% | -4.47% | 6.50% | -10.96% | 0.382 |

Overall base rate across all 5,760 matched rows (context: the whole labeled
period skews negative, likely a RISK_OFF/VOLATILE-heavy stretch consistent
with prior tuning findings): positive close-return rate 37.5%, avg close
return -3.09%.

**Welch's t-test, CLUSTER+positive vs CLUSTER+negative close_return**:
mean -2.52% (N=2536) vs mean -3.53% (N=2780), t = 3.06 — statistically
significant at the sample sizes involved, though the absolute effect size
(~1.0 percentage point) is modest relative to the period's overall -3.09%
average.

**Key pattern**: CLUSTER+negative-flow performs statistically indistinguishable
from (slightly worse than) non-CLUSTER+negative-flow (avg -3.53% vs -3.63%,
pos-rate 36.0% vs 39.8%). CLUSTER's incremental value over non-CLUSTER is
concentrated entirely in the positive-flow subset (avg -2.52% vs -3.55%,
a ~1 point gap). In other words: **when aggregate flow is negative, being
BCI CLUSTER carries no measurable positive signal over not being CLUSTER at
all** — yet it still receives full `+12.5` scoring authority.

## Contradiction Examples

CLUSTER + negative aggregate flow + `DISTRIBUTION`/`FAILED`/`EXHAUSTION` setup
phase + `FAILURE` forward outcome: 1,545 matching rows found (far more than
the 5 requested). First 8 shown:

| Date | Ticker | BCI | Tier1 Count | Aggregate Flow (total_net_value, IDR) | Setup Phase | Forward Return (close_return %) |
|---|---|---|---:|---:|---|---:|
| 2026-05-04 | AADI | CLUSTER | 5 | -23,635,430,000 | DISTRIBUTION | -25.97 |
| 2026-05-04 | ASII | CLUSTER | 3 | -263,523,685,000 | DISTRIBUTION | -1.65 |
| 2026-05-04 | HRTA | CLUSTER | 3 | -12,112,279,000 | DISTRIBUTION | -21.09 |
| 2026-05-04 | MBMA | CLUSTER | 4 | -47,914,693,500 | DISTRIBUTION | -31.85 |
| 2026-05-04 | PGAS | CLUSTER | 4 | -67,338,531,500 | DISTRIBUTION | -4.76 |
| 2026-05-04 | SCMA | CLUSTER | 3 | -1,835,976,800 | DISTRIBUTION | -14.39 |
| 2026-05-05 | AADI | CLUSTER | 5 | -28,126,542,500 | DISTRIBUTION | -26.13 |
| 2026-05-05 | AMMN | CLUSTER | 4 | -69,044,955,000 | DISTRIBUTION | -41.26 |

Setup-phase distribution across all 2,780 CLUSTER+negative-flow rows:
`DISTRIBUTION` 2,628 (94.5%), `FAILED` 108, `BREAKOUT_CONFIRMATION` 18,
`ACCUMULATION` 14, `COMPRESSION` 11, `NONE` 1. Outcome distribution:
`FAILURE` 1,574 (56.6%), `SUCCESS` 1,098 (39.5%), `NEUTRAL` 108.

## Conclusion

**CREATE FOLLOW-UP VALIDATION TASK — hypothesis supported; production
scoring change requires canonical/walk-forward confirmation**

Both required buckets clear the 30-observation evidence threshold by a wide
margin (CLUSTER+positive N=2536, CLUSTER+negative N=2780). The CLUSTER+negative
bucket shows a statistically significant (t=3.06) and directionally
consistent degradation vs CLUSTER+positive across every metric measured
(positive-return rate, avg/median close return, profit factor), and —
more importantly for scoring authority specifically — CLUSTER+negative-flow
outcomes are statistically indistinguishable from non-CLUSTER+negative-flow
outcomes. This means the CLUSTER label's entire measured incremental value is
concentrated in the positive-aggregate-flow subset; granting it full
scoring authority (+12.5, same as CLUSTER+positive) when flow is negative is
not supported by this data.

**This is a hypothesis-confirming result, not an approval to change
production scoring.** The evidence threshold in this task's own instructions
(≥30 per required bucket) is met, but sample-size adequacy is a necessary
condition, not a sufficient one, given the caveats above: single 5.5-month
retrospective backfill (one market period, not multiple), non-canonical
`(ticker, snapshot_date)` join with ~6% duplicate-row disagreement on the
flow-sign field, and no walk-forward train/test split. Per
`AGENT_QUICKSTART.md`'s evidence-promotion guardrail ("do not promote
diagnostic evidence or tune patch-eligible config without out-of-sample
proof and validator support"), this spike's own single-period backfill does
not itself constitute that proof. The next task must re-run this comparison
as a genuine walk-forward validation (see below) — only if that confirms the
pattern should scoring code change.

## Recommended Follow-Up

**Next task is a validation task, not an implementation task.** Its job is to
confirm or reject this spike's hypothesis under conditions that remove the
caveats above, before any scoring code changes:

1. Re-run this comparison as a genuine walk-forward split (train/test period
   boundaries across multiple market regimes, not a single-batch backfill
   over one 5.5-month stretch).
2. Once S1's canonical-identity fix has accumulated enough post-fix history,
   re-run the query against canonical (`config_hash != ''`) rows only, to
   remove the non-canonical-join / duplicate-row caveat entirely.
3. Confirm the pattern found here holds: CLUSTER+negative-flow ≈
   non-CLUSTER+negative-flow, CLUSTER+positive-flow materially better than
   both.

**Only if that validation confirms the pattern**, implement scoring change
as Option A — make BCI points conditional on positive aggregate flow
direction. Rationale for preferring Option A over the alternatives, based on
this spike's (unconfirmed) data: CLUSTER's value-add appears concentrated in
the positive-flow subset, so `ScoreForeignFlowUseCase._score_bci()` would
only award full `cluster_points`/`stable_points` when the same-window
aggregate flow (`total_net_value` or equivalent) is positive, and award 0
(or a small diagnostic-only fraction) when it is negative — behind the
existing `BciEvidencePolicy` dataclass with an explicit config-driven flag
(e.g. `require_positive_flow: bool` or a fractional
`negative_flow_multiplier`), plus unit tests proving CLUSTER+negative-flow
no longer receives full `cluster_points` while CLUSTER+positive-flow is
unchanged. This is preferred over:
- Option B (uniform authority reduction) — too blunt; CLUSTER+positive
  should keep full authority since it does show real incremental value.
- Option C (diagnostic-only) — throws away the positive-flow signal that
  this data shows is real and useful.
- Option D (materiality threshold) — addresses a different question
  (magnitude/turnover) than the one this spike investigated (direction);
  could be a *second*, separate follow-up but isn't the primary fix for the
  contradiction pattern found here.
