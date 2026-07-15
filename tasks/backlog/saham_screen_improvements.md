# Backlog: `saham screen` Improvements

**Source thought doc:** `tasks/thought/saham_screen_improvement.md`
**Code-verified:** 2026-07-14 10:20 WIB — all findings confirmed open against current working tree.

Files verified:
- `src/application/use_case/accumulation_screen_use_case.py`
- `src/application/use_case/run_accumulation_screen_workflow_use_case.py`
- `src/application/services/accumulation_candidate_observation_persister.py`
- `src/infrastructure/persistence/sqlite_candidate_observations_repository.py`
- `src/infrastructure/persistence/sqlite_watchlist_repository.py`
- `src/adapters/cli/screen_accum_commands.py`
- `src/adapters/cli/screen_accum_compare_factory.py`
- `src/adapters/cli/screen_accum_guide_display.py`
- `src/adapters/cli/fetch_status_commands.py`

---

> [!IMPORTANT]
> Before starting any task: read `AGENT_QUICKSTART.md`, confirm `AGENTS.md` / `GEMINI.md` compliance, and state the layer plan.
> P0 tasks affect learning-data integrity and output correctness. Do not implement without an explicit owner decision on the observation identity contract (S1).

---

## Status Summary

| # | Task ID | Priority | Finding | Status |
|---|---------|----------|---------|--------|
| 1 | `S1` | P0 | Multi-window screening corrupts observation identity | ❌ Open |
| 2 | `S2` | P0 | Table and JSON output apply different filters | ❌ Open |
| 3 | `S3` | P0 | Freshness is source alignment, not actual calendar freshness | ❌ Open |
| 4 | `S4` | P0 | Pre-open provider failure looks like valid empty result | ❌ Open |
| 5 | `S5` | P1 | Unsupported 65–70% prediction claim in guide | ❌ Open |
| 6 | `S6` | P1 | BCI grants full points despite negative aggregate flow | ❌ Open |
| 7 | `S7` | P1 | Multi-window output discards Signal/Risk/Phase already computed | ❌ Open |
| 8 | `S8` | P1 | Watchlist `list` reports wrong ticker count | ❌ Open |
| 9 | `S9` | P1 | `screen compare` missing weakening bucket; still persists observations | ❌ Open |
| 10 | `S10` | P2 | `saham fetch status` uses wrong default DB path | ❌ Open |

---

## Execution Order

Execute in this order. S1 must come first — all later calibration accuracy depends on observation identity integrity.

| Order | Task ID | Rationale |
|-------|---------|-----------|
| 1 | `S1` | Blocks S2/S9; corrupts learning data if left open |
| 2 | `S2` | Unblocked after S1 establishes projection contract |
| 3 | `S3` | Independent; improves data quality trust |
| 4 | `S4` | Independent; improves pre-open decision safety |
| 5 | `S5` | Doc-only; fast, independent |
| 6 | `S10` | Infra bugfix; small, independent |
| 7 | `S8` | Infra bugfix; depends on watchlist schema |
| 8 | `S9` | Depends on S1 (no-persistence path) |
| 9 | `S7` | Depends on S1/S2 (shared projection) |
| 10 | `S6` | Scoring change; requires OOS evidence first |

---

## Task S1 — Canonical Observation Identity; No Persistence from Diagnostic/Compare Paths

### Metadata

- **Type:** Refactor / Bugfix
- **Priority:** P0 — **highest impact** — corrupts forward-label calibration data
- **Effort:** Large — touches use case, persister, repository schema, and compare factory
- **Status:** RESOLVED (commit `bcbb3ac`)

### Problem

**`AccumulationScreenUseCase.execute()` always persists, even in multi-window and compare contexts.**

Key location: `src/application/use_case/accumulation_screen_use_case.py:373`

```python
self._observation_persister.persist(all_results, today, request)
```

This line runs unconditionally. Callers that are logically read-only (multi-window diagnostic passes, `screen compare`) trigger persistence anyway.

**Multi-window observation drift:**
`run_accumulation_screen_workflow_use_case.py:182-188` calls `self._screen_use_case.execute()` once per window (7, 30, 90). Each call persists. The live audit produced `3.07 rows/ticker` for 2026-07-14. For BBCA the sequence was:

```
7 sessions  -> score 42.5
7 sessions  -> score 42.5 (repeat from earlier standalone run)
30 sessions -> score 31.6
90 sessions -> score 27.1
```

Current readiness/reporting code mitigates some damage by collapsing rows to
the latest-per-ticker observation. That is not a real fix: raw duplicate rows
still exist, read-only views still write learning data, and the repository
identity is still timestamp-driven rather than canonical-observation-driven.

`src/infrastructure/persistence/sqlite_candidate_observations_repository.py` schema has no UNIQUE constraint on `(ticker, snapshot_date, window_days, workflow)`. `save_many()` always INSERTs.

**Compare corruption:**
`src/adapters/cli/screen_accum_compare_factory.py:52` calls `use_case.execute()` directly, which persists a fresh screen run merely to produce a comparison view.

### Decision

Adopt **Option A: screen execution is read-only by default; persistence is explicit.**

- `AccumulationScreenUseCase.execute()` must not write candidate observations.
- Add an explicit canonical observation recording path, e.g.
  `RecordAccumulationObservationsUseCase`.
- Only the canonical learning/observation workflow should call the recording
  path.
- Diagnostic/read-only paths must never persist observations:
  - `saham screen accum --multi`
  - `saham screen compare`
  - `DailyBriefingUseCase`
  - replay/diagnostic compare views unless explicitly named as recording jobs
- Multi-window output remains diagnostic. Do not write one row per window into
  canonical `candidate_observations`.

> [!CAUTION]
> Do not partially fix this by adding `UNIQUE(ticker, snapshot_date)` while
> leaving diagnostic calls on the persistence path. That would merely make the
> last diagnostic caller overwrite the canonical observation.

### Required Canonical Observation Identity

Minimum identity for the explicit canonical writer:

```text
ticker
snapshot_date
workflow          (e.g. "screen_accum", "daily_briefing")
window_sessions   (7 / 30 / 90)
data_as_of_date   (latest candle/broker date used)
config_hash       (fingerprint of scoring config version)
```

These fields may also remain in the JSON payload, but the canonical writer must
enforce idempotency using database identity or explicit UPSERT logic. JSON-only
identity is not enough.

### Non-Goals

- No change to scoring formula or evidence.
- No new data providers.
- No tuning patch or evidence promotion.
- No behavior change to visible screen ranking except removal of accidental
  observation writes from diagnostic/read-only paths.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain:
  CandidateObservationsRepository contract distinguishes canonical upsert from
  raw append, or documents a single canonical save contract if raw append is
  retired.
- Application:
  accumulation_screen_use_case.py becomes read-only; extract recording into
  RecordAccumulationObservationsUseCase or equivalent explicit writer. Preserve
  rejected candidates as learnable negative samples in the canonical recording
  path.
- Infrastructure:
  sqlite_candidate_observations_repository.py adds canonical identity columns
  and UNIQUE/UPSERT for canonical observations. Raw diagnostic append, if still
  needed, must use a separate table or explicit artifact type.
- Adapter:
  screen_accum_commands.py calls the recording path only for the canonical
  observation workflow. screen_accum_compare_factory.py and multi-window display
  paths stay read-only.
```

### Acceptance Criteria

- [x] `AccumulationScreenUseCase.execute()` does not call observation persistence directly
- [x] Canonical observation recording is explicit and named
- [x] `saham screen accum --multi` produces zero diagnostic-window observation rows
- [x] `screen compare` does not write any observation rows
- [x] `DailyBriefingUseCase` calling `AccumulationScreenUseCase` does not write observation rows
- [x] Canonical recording produces one row per `(ticker, snapshot_date, workflow, window_sessions, data_as_of_date, config_hash)`
- [x] Duplicate canonical recording runs are idempotent (second run updates/replaces; it does not append duplicates)
- [x] Schema has a unique constraint or explicit UPSERT for the canonical identity key
- [x] Tests: multi-window run writes 0 observations; compare writes 0 observations; canonical recording writes 1 idempotent observation per identity
- [x] Full test suite passes
- [x] `git diff --check` clean

**Resolution notes:**
- `AccumulationScreenUseCase.execute()` is read-only; evaluated candidates (pass + rejected) are exposed via `response.observation_candidates` (typed `AccumulationScreenObservationCandidate`, not a raw tuple).
- `RecordAccumulationObservationsUseCase` is the sole persistence entrypoint, built via `create_accumulation_screen_use_case_bundle()` / `create_accumulation_screen_workflow_bundle()` and wired only into `signal-backfill-observations`. `AccumulationScreenUseCase` does not construct or expose the recorder or its persister.
- `candidate_observations` gained `workflow`, `window_sessions`, `data_as_of_date`, `config_hash` columns with a partial UNIQUE index (`WHERE config_hash != ''`) so pre-migration legacy rows stay excluded/readable while new canonical writes UPSERT in place.
- Follow-up fix during review: label generation (`GenerateSignalForwardLabelsUseCase`, `BackfillSignalObservationsUseCase`) was still collapsing to latest-per-ticker via `list_by_date()`, silently dropping all but one recorded window. Added `list_canonical_by_date()` and switched label generation to it — verified live: a 3-window backfill now saves 135 observations and generates 135 labels (previously would have generated 45).
- Verified live against a copy of the production DB (45-ticker lq45 universe, 19k+ existing rows): ordinary `screen accum`, `--multi`, `screen compare`, and `saham today` all write zero rows; `signal-backfill-observations` writes/labels correctly and is idempotent on rerun; legacy rows remain readable throughout.

---

## Task S2 — Unified Application Projection for Table and JSON Output

### Metadata

- **Type:** Bugfix / Refactor
- **Priority:** P0 — table and JSON return different candidate sets for the same command
- **Pre-condition:** S1 must be resolved first (to establish the clean result contract)

### Problem

**Single-window mode:**
`src/adapters/cli/screen_accum_commands.py:_render_single()`:
- JSON path (line 384): `[c.to_dict() for c in response.candidates[:top]]` — no `vwap_only` or `squeeze_only` filtering applied.
- Table path (line 389–400): passes `vwap_only=vwap_only, squeeze_only=squeeze_only` to `display_results()`.

**Multi-window mode:**
`_render_multi()` JSON path (line 322–343): serializes all candidates from every window, ignores `--top`, `--sort-by`, `--squeeze-only`.
Table path (line 345–355): passes `top_n=top, sort_by=sort_by, squeeze_only=squeeze_only` to `display_multi()`.

**Strategy overlay and watchlist saving** are silently disabled for JSON or multi mode via `include_strategy_overlay = bool(strategy and output_format != "json" and not multi)` (line 236–237) rather than being rejected or documented as unsupported.

**Result:** a script consuming `--format json` cannot reliably reproduce what the human saw in the table.

### Desired Outcome

One application-owned result projection that:
- applies `vwap_only`, `squeeze_only`, `min_streak`, `top`, `sort_by` filters/limits exactly once
- returns a `ScreenProjectedResult` DTO (or enriches `RunAccumulationScreenWorkflowResult`)
- is consumed by both table and JSON renderers

JSON output also includes:
- `applied_filters` (vwap_only, squeeze_only, sort_by, top)
- `universe` and requested vs resolved windows
- counts before/after filtering
- per-source data-as-of dates and freshness state
- warnings and partial-result status

Invalid `--sort-by` values, duplicate windows, and unsupported combinations fail explicitly (not silently disabled).

### Non-Goals

- No change to scoring formula.
- No new CLI flags.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: not touched
- Application: RunAccumulationScreenWorkflowUseCase or a new ScreenResultProjector service — apply all filters/ranking/limiting before returning to adapter
- Infrastructure: not touched
- Adapter: screen_accum_commands.py — both _render_single and _render_multi consume the projected result; JSON path uses same projected candidates as table
```

### Acceptance Criteria

- [ ] `saham screen accum --vwap-only --format json` returns the same candidate set as the table view
- [ ] `saham screen accum --squeeze-only --format json` returns the same candidate set as table view
- [ ] `saham screen accum --multi --top 5 --sort-by 30s --format json` respects all three options
- [ ] JSON output includes `applied_filters`, `universe`, `counts_before_filter`, `counts_after_filter`
- [ ] Invalid `--sort-by` value exits with a clear error message
- [ ] Full test suite passes
- [ ] `git diff --check` clean

---

## Task S3 — Market-Calendar-Aware Freshness and Typed Source Status

### Metadata

- **Type:** Feature / Refactor
- **Priority:** P0 — "Fresh: OK" currently means sources agree with each other, not that data is current

### Problem

The accumulation display shows a `Fresh` status derived from comparing candle date against broker date only:
- `MISSING`: candle or broker date absent
- `OK`: candle date equals broker date
- `LAG`: dates differ

During the live audit at 09:26 WIB on 2026-07-14, the screen subtitle was `2026-07-14`, candle and broker data both ended `2026-07-13`, and the display showed `Fresh: OK`. The data was plausibly current (regular session was open, so prior-day EOD is correct), but "OK" cannot prove it. The same dates could be stale several sessions later and still show OK.

The Data Coverage `Missing` column only checks six enrichment objects, not the actual SignalEngine evidence coverage (which was 40% in the audit due to absent setup-quality evidence).

### Desired Outcome

One application-owned `DataFreshnessStatus` value object used consistently across `screen`, `today`, `status`, and `analyze` workflows, reporting:

```text
candle_as_of: date
broker_as_of: date
expected_latest_eod: date   # from IDX trading calendar
candle_state: READY | PENDING_EOD | STALE | PARTIAL | MISSING | UNKNOWN
broker_state: READY | PENDING_EOD | STALE | PARTIAL | MISSING | UNKNOWN
sources_aligned: bool
signal_evidence_coverage: float  # from SignalEngine, not just enrichment presence
```

Display changes:
- Replace `OK` with `ALIGNED` for source-equality and add a separate readiness state
- Show `PENDING_EOD` when data is from prior session during an open session (not `STALE`)
- Show actual signal evidence coverage percentage, not only enrichment object presence

### Non-Goals

- No network calls for calendar lookup — use local IDX holiday table or conservative Friday-rollback.
- No change to how scoring data is fetched.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: DataFreshnessStatus value object
- Application: freshness calculation service (shared across screen/today/analyze); AccumulationScreenResponse carries freshness per ticker
- Infrastructure: not touched (reuse existing market/broker repos)
- Adapter: screen_accum_enrichment_display.py — render new freshness states; replace OK/LAG labels
```

### Acceptance Criteria

- [ ] `Fresh: OK` replaced by `Aligned` (source equality) + separate readiness state
- [ ] `PENDING_EOD` shown when data is prior-session during an open market, not `STALE`
- [ ] Signal evidence coverage percentage shown (not only enrichment object count)
- [ ] Same `DataFreshnessStatus` value object reusable by `today` briefing (S3 and T3/T4 from `saham_today_improvements.md` can share this)
- [ ] Tests: prior-session data during open market → `PENDING_EOD` not `STALE`
- [ ] Full test suite passes
- [ ] `git diff --check` clean

---

## Task S4 — Pre-Open Typed Source Status (Empty vs Unavailable vs Out-of-Window)

### Metadata

- **Type:** Feature / Bugfix
- **Priority:** P0 — provider failure currently looks identical to a valid zero-mover result

### Problem

At 09:26 WIB the live audit ran `saham screen pre-open --fast --top 5`. The command:
- warned it was outside the 08:45–09:00 window
- announced "Playwright session found — running autonomously"
- returned zero movers and zero candidates
- displayed "No candidates passed the IEV filter"
- exited successfully

A July 14 IEV snapshot with 50 movers was already on disk. The output did not distinguish between:
- A live fetch that returned a genuinely empty mover list
- An empty or unavailable live provider response
- Running outside the time window where live data is no longer available
- A saved snapshot that was not selected

`"No candidates"` is semantically indistinguishable from provider unavailability.

### Desired Outcome

The pre-open workflow use case returns a typed source status:

```python
class PreOpenSourceStatus(Enum):
    LIVE_SUCCESS = "LIVE_SUCCESS"          # live fetch succeeded, result valid
    SNAPSHOT_SUCCESS = "SNAPSHOT_SUCCESS"  # loaded from saved snapshot
    EMPTY_CONFIRMED = "EMPTY_CONFIRMED"    # provider confirmed genuine zero movers
    UNAVAILABLE = "UNAVAILABLE"            # provider unreachable or returned invalid payload
    OUTSIDE_WINDOW = "OUTSIDE_WINDOW"      # called outside pre-open window with no fallback
```

Outside the live window, default behavior should either:
- Load the latest dated snapshot and label it clearly as `SNAPSHOT_SUCCESS`; or
- Exit with `OUTSIDE_WINDOW` result if no snapshot available

A zero-mover result must carry `EMPTY_CONFIRMED` status with evidence that the provider returned a valid (but empty) payload — not just that no candidates survived filtering.

The pre-open adapter writes a sidecar only when `source_status in (LIVE_SUCCESS, EMPTY_CONFIRMED)` — not for `UNAVAILABLE` or `OUTSIDE_WINDOW`.

### Non-Goals

- No change to IEV scoring or pre-open filtering logic.
- No change to what triggers the sidecar write (path/format), only when.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: PreOpenSourceStatus enum (or in application layer is also acceptable)
- Application: pre-open workflow use case — derive and return source_status; sidecar write conditioned on valid statuses
- Infrastructure: not touched (Playwright/IEV fetch result already returned)
- Adapter: screen_pre_open_commands.py — render source_status in output; suppress sidecar for UNAVAILABLE/OUTSIDE_WINDOW
```

### Acceptance Criteria

- [ ] `PreOpenSourceStatus` enum exists with at least 5 values above
- [ ] "No candidates" is never shown without an explicit `source_status` field in the response
- [ ] Zero-mover result requires `EMPTY_CONFIRMED` (provider returned valid empty payload)
- [ ] Sidecar is only written for `LIVE_SUCCESS` or `EMPTY_CONFIRMED`
- [ ] Outside the window: loads snapshot or returns `OUTSIDE_WINDOW`, does not silently attempt live fetch
- [ ] Tests: unavailable provider → `UNAVAILABLE`; genuine zero → `EMPTY_CONFIRMED`; snapshot load → `SNAPSHOT_SUCCESS`
- [ ] Full test suite passes
- [ ] `git diff --check` clean

---

## Task S5 — Remove or Qualify Unsupported 65–70% Performance Claim

### Metadata

- **Type:** Documentation / Bugfix
- **Priority:** P1 — misleads users into false confidence

### Problem

`src/adapters/cli/screen_accum_guide_display.py:22`:

```python
intro = Text(
    "Detects stocks being quietly bought by foreign institutions over\n"
    "multiple days. When foreigners accumulate consistently AND are\n"
    "'underwater' (bought higher than today's price), IHSG stocks\n"
    "resolve upward 65–70% of the time within 10–20 trading days.\n"
    ...
)
```

No source, sample definition, sample count, date range, regime split, universe, cost assumption, or reproducible local audit accompanies this claim. The same number appears in `docs/screener-foreign-accumulation.md` (if that file exists).

This is the strongest claim shown to users and is especially problematic because the observation identity issue (S1) can bias any local evidence intended to validate it.

### Desired Outcome

Remove the numeric claim until it is backed by a versioned local audit.

Replace the claim with a scoped statement such as:

```text
Performance evidence: not yet independently validated.
Run `saham learn grade` after accumulating observations to measure local resolution rates.
```

When local evidence exists, the display should show a scoped statement:

```text
LQ45, 2024-01-01..2026-06-30, N=___ observations,
10-session positive-return rate ___%, as of [date], config hash ___
```

### Non-Goals

- No code change to scoring.
- No new features.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: not touched
- Application: not touched
- Infrastructure: not touched
- Adapter: screen_accum_guide_display.py:18-25 — replace claim text
- Documentation: docs/screener-foreign-accumulation.md — same replacement if file exists
```

### Acceptance Criteria

- [ ] `65–70%` text is removed from `screen_accum_guide_display.py`
- [ ] Replacement text directs users to `saham learn grade` for local evidence
- [ ] Equivalent claim removed from docs if it exists
- [ ] `git diff --check` clean

---

## Task S6 — Revalidate BCI Authority Under Contradictory or Immaterial Flow

### Metadata

- **Type:** Spike / Scoring Refactor
- **Priority:** P1 — requires OOS evidence before scoring change; do not tune blindly

### Problem

All three audited bank tickers received the full BCI `CLUSTER` score contribution despite contradictory evidence. BBRI specifically showed:
- Only 2/7 net-buy sessions
- `Flow% = -18.0%` (aggregate foreign flow is negative)
- Distribution setup phase
- Named bandar detail showing distribution
- Full CLUSTER BCI contribution (12.5 points)

BCI counts how many configured Tier-1 broker codes have positive net lots over the window — without requiring positive aggregate flow, minimum absolute value, concentration relative to others, or agreement with the domestic bandar track.

**This is a scoring policy question, not a simple threshold change.** The exact change must come from OOS evidence.

### Recommended Investigation Steps

1. Run a replay of historical observations with BCI contribution isolated.
2. Split by cases where BCI is CLUSTER but aggregate flow is negative.
3. Measure forward return rate difference between those cases and positive-aggregate-flow CLUSTER.
4. Only if negative-flow CLUSTER shows materially lower resolution → proceed with scoring change.

Candidate options (do not implement without step 4):
- Make BCI conditional on positive aggregate direction
- Weight by net-value/turnover materiality
- Treat contradiction as mixed/neutral evidence (not CLUSTER)
- Keep named-broker composition as DIAGNOSTIC until out-of-sample attribution proves incremental value

### Non-Goals

- Do not change BCI scoring without OOS evidence.
- Do not remove BCI display — visibility is correct; authority is the question.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan (Spike only):
- Domain: not touched
- Application: not touched (analysis only)
- Infrastructure: not touched
- Adapter: not touched
Documentation: record findings in a new thought doc or spike report
```

### Acceptance Criteria for Spike

- [ ] Analysis compares forward return rates for CLUSTER+positive-flow vs CLUSTER+negative-flow
- [ ] Sample size and date range documented
- [ ] Conclusion: whether to proceed with scoring change and which option
- [ ] If scoring change approved: separate implementation task created with test coverage

---

## Task S7 — Multi-Window Output Shows Signal/Risk/Phase Already Computed

### Metadata

- **Type:** Feature / Refactor
- **Priority:** P1 — expensive work is silently discarded
- **Pre-condition:** S1 (single canonical persistence pass); S2 (shared projection)

### Problem

`run_accumulation_screen_workflow_use_case.py:_execute_multi()` (lines 174–203) calls the full screen pipeline for each window, which includes SignalEngine assessment, setup-phase detection, risk funnel, and observation fingerprint construction. These results are discarded — only `multi_results` (foreign-flow scores) and `broker_quality` are returned.

The multi table only shows: 7s score, 30s score, 90s score, pattern, trend, broker flow label.
During the live audit `Broker Flow: n/a` appeared for every row despite BCI data being available for the same tickers via the single-window path.

### Desired Outcome

Multi-window output becomes a genuine shortlist table:

```text
Ticker | 7s | 30s | 90s | Pattern | Signal/Coverage | Risk | Phase | Data | Next
```

Only one explicitly selected canonical window (configurable, default: 7) owns Signal/Risk/Action.
Other windows provide supporting flow context.

Broker composition reuses the `broker_daily_flow` source (already used by BCI in the single-window path) rather than the named-broker summary path that returns `n/a`.

The expensive enrichment/Signal/Risk work runs only once per ticker, not per window. Compute 7/30/90 metrics from one shared 90-session in-memory series.

### Non-Goals

- No new data fetches.
- No change to what the canonical window's Signal/Risk output means.
- The multi JSON format updates separately in S2.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: not touched
- Application: run_accumulation_screen_workflow_use_case.py — single shared data-load pass; compute all windows from one series; run Signal/Risk once for canonical window; return enriched multi result DTO
- Infrastructure: batch repository methods keyed by ticker + date range (if not already present)
- Adapter: screen_accum_multi_display.py — render new Signal/Coverage/Risk/Phase columns
```

### Acceptance Criteria

- [ ] Multi run computes 7/30/90 metrics from one shared in-memory series (not three full pipeline runs)
- [ ] Canonical window (7 by default) shows Signal score, coverage %, Risk status
- [ ] Broker flow column shows data (not `n/a`) when broker_daily_flow is available
- [ ] Wall time for LQ45 multi run is materially lower than 28.48s baseline
- [ ] Full test suite passes
- [ ] `git diff --check` clean

---

## Task S8 — Fix Watchlist `list` Ticker Count Query

### Metadata

- **Type:** Bugfix
- **Priority:** P1 — displayed ticker count is wrong (counts all historical rows, not latest snapshot)

### Problem

`src/infrastructure/persistence/sqlite_watchlist_repository.py:list_snapshots()` (lines 111–126):

```sql
SELECT name,
       COUNT(*) as ticker_count,
       MAX(saved_at) as latest_saved_at,
       universe,
       window_days
FROM screen_snapshots
GROUP BY name
```

`COUNT(*)` counts all rows across every historical snapshot for that name. If a watchlist "morning-watch" was saved 5 times with 10 tickers each, it shows `ticker_count = 50` instead of `10`.

`universe` and `window_days` are selected from an unspecified row in the group (SQLite picks any row — undefined behavior when these differ across snapshots for the same name).

### Desired Outcome

Use a latest-run subquery to show the ticker count from the most recent snapshot only:

```sql
SELECT s.name,
       sub.ticker_count,
       sub.latest_saved_at,
       s.universe,
       s.window_days
FROM screen_snapshots s
JOIN (
    SELECT name,
           MAX(saved_at) as latest_saved_at,
           COUNT(*) as ticker_count
    FROM screen_snapshots
    WHERE saved_at = (SELECT MAX(saved_at) FROM screen_snapshots s2 WHERE s2.name = screen_snapshots.name)
    GROUP BY name
) sub ON s.name = sub.name AND s.saved_at = sub.latest_saved_at
GROUP BY s.name
```

Or simpler — use `get_latest_snapshot()` which already does the MAX(saved_at) lookup correctly.

### Non-Goals

- No change to watchlist save logic.
- No schema migration needed (query fix only).

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: not touched
- Application: not touched
- Infrastructure: sqlite_watchlist_repository.py — fix list_snapshots() query
- Adapter: not touched
```

### Acceptance Criteria

- [ ] `list_snapshots()` returns the ticker count from the most recent snapshot only
- [ ] `universe` and `window_days` are from the most recent snapshot row only
- [ ] Test: watchlist saved 3 times with 10 tickers each → `ticker_count = 10`
- [ ] Full test suite passes
- [ ] `git diff --check` clean

---

## Task S9 — Fix `screen compare`: Add Weakening Bucket and Make It Read-Only

### Metadata

- **Type:** Bugfix / Refactor
- **Priority:** P1
- **Pre-condition:** S1 must be resolved first (so compare cannot accidentally persist)

### Problem

**Missing weakening bucket:**
The compare command shows new tickers, dropped tickers, and strengthening rows. Weakening rows (tickers whose score decreased since the saved snapshot) and ordinary score/flow changes are silently omitted. Users see only positive changes.

**Persistence side-effect:**
`src/adapters/cli/screen_accum_compare_factory.py:52` calls `use_case.execute()` directly, which currently always persists via `self._observation_persister.persist()` (resolved by S1). After S1, this will be safe — but the compare factory should explicitly use a no-persistence path.

**Exception swallowing:**
Line 68: `except Exception: return None` — every failure returns `None` with no diagnostic. The adapter then shows "Could not run fresh screen — check data." with no actionable details.

**ADR-039 score scale conflict:**
Historical watchlist snapshots may have been saved with the old 0–120 scale, while current scores use 0–100. A comparison without schema version checking will show false deltas.

### Desired Outcome

- Compare shows four delta buckets: **new**, **dropped**, **strengthening**, **weakening**, **unchanged**
- Both flow-score and signal-score deltas are shown, not a single generic `cmp` value
- Compare calls are explicitly read-only (no observation persistence), either via S1 or by using a separate read-only use case
- Provider failures report specific errors (not silent `None`)
- Schema/version check: if a stored snapshot used the old 0–120 scale, normalize before comparing or show a warning

### Non-Goals

- No change to scoring formula.
- No new watchlist save features.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: not touched
- Application: compare logic (new or extended use case) — produce 4-bucket delta; verify score schema version before comparing
- Infrastructure: not touched
- Adapter: screen_accum_compare_factory.py — use no-persistence path (after S1); propagate specific errors instead of returning None
- Adapter: compare display — render weakening and unchanged buckets
```

### Acceptance Criteria

- [ ] Compare shows new, dropped, strengthening, weakening, and unchanged buckets
- [ ] Both flow-score delta and signal-score delta displayed per ticker
- [ ] Compare run produces zero observation rows (after S1)
- [ ] Provider failures show specific error text, not generic "Could not run fresh screen"
- [ ] Old 0–120 scale snapshots either normalized or flagged with a warning
- [ ] Tests: weakening ticker appears in weakening bucket (not silently dropped)
- [ ] Full test suite passes
- [ ] `git diff --check` clean

---

## Task S10 — Fix `saham fetch status` Default Database Path

### Metadata

- **Type:** Bugfix
- **Priority:** P2 — `fetch status` is the first command users run to verify data; showing wrong DB is misleading

### Problem

`src/adapters/cli/fetch_status_commands.py:23`:

```python
DEFAULT_DB_PATH = Path("data.db")
```

The configured application database is `APP_CFG.storage.db_path` which resolves to `data/db/data.db`. The `fetch status` command defaults to `data.db` (project root), which does not exist. The command reports "No database found" even though all screener commands successfully use the configured path.

The same run also showed a Yahoo DNS failure but displayed a green healthy icon. This is a separate but related trust issue.

### Desired Outcome

```python
from src.infrastructure.config.app_config import APP_CFG
DEFAULT_DB_PATH = Path(APP_CFG.storage.db_path)
```

**Optional (secondary):** Review the Yahoo Finance health check — a DNS failure should not display a green icon.

### Non-Goals

- No change to what data is checked.
- No change to schema or freshness logic.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: not touched
- Application: not touched
- Infrastructure: not touched
- Adapter: fetch_status_commands.py:23 — replace DEFAULT_DB_PATH with APP_CFG.storage.db_path
```

### Acceptance Criteria

- [ ] `saham fetch status` without `--db` uses `APP_CFG.storage.db_path`
- [ ] Running `saham fetch status` after a normal `saham screen accum` run shows the same database contents
- [ ] Test: default path equals `APP_CFG.storage.db_path`
- [ ] `git diff --check` clean

---

## Architecture Boundary Reminders

> [!IMPORTANT]
> Key boundaries from the architecture review (already confirmed good — do not undo):

- `AccumulationScreenUseCase` delegates major orchestration correctly — keep it that way
- Structural pruning occurs before expensive enrichment — preserve this order
- Risk funnel runs only on survivors — do not expand its scope
- Signal, risk, and TradeSetup remain distinct artifacts — do not merge them

> [!WARNING]
> Key architecture problems to fix (not introduce more of):

- **Do not** add new filtering logic inside display/adapter code — use the application projection (S2)
- **Do not** call `AccumulationScreenUseCase.execute()` from read-only contexts like compare or diagnostic views without the no-persistence path (S1)
- **Do not** add persistence decisions inside the `AccumulationScreenUseCase` — persistence policy belongs in a separate use case or explicit caller
- **Do not** use multi-window pattern classification in both application and adapter code — pick one canonical location (application)

---

## Already Confirmed Good (Do Not Re-implement)

These parts are working correctly — do not revisit unless a specific regression surfaces:

- CLI command hierarchy is small and understandable
- Help text correctly distinguishes foreign-flow score from SignalEngine score
- Session-based windows avoid weekend/holiday distortion
- Single-window action table leads with ENTER/WATCH/AVOID/BLOCKED
- Risk status correctly explains OPEN is not risk-free
- Output openly states TechnicalGate is not evaluated
- Foreign-flow component points are visible and auditable
- `--explain` panel provides useful score mechanics
- Pre-open presents conditional entry ranges, not fixed auction prices
- JSON includes artifact type and schema version
- Concrete construction is isolated in focused adapter factories
- Reads are bounded by as-of date, supporting historical replay
