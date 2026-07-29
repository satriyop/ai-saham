# ADR-056: Accum Corpus Session Observation + accum_* Path Labels

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted  
**Date:** 2026-07-29  
**Amends:** [ADR-049](ADR-049-database-owned-learning-pipeline-clean-break.md) (accum observation unit + label contract names)  
**Related:** ADR-050 (CLI `research accum`), ADR-030 (accum evidence)

## Context

Accumulation learning capture wrote **three** `learning_observations` per ticker per session (windows 7 / 30 / 90) while default labels used **`price_path.accum_20d.v1`**. That inflated sample counts, mixed lookback features with a longer hold label, and used **tactical/swing** label brand names for an accum corpus.

Product lock: swing/accum book is graded primarily on **~10 sessions**; multi-window scores are **features**, not three independent decisions.

## Decision

### Unit of analysis

- **One** accumulation observation per `(ticker, session)`.
- Lookbacks **7 / 30 / 90** live in `decision_payload.features_by_window` with full engine factors (accum candidate, signal, risk, market context, sector context / sector-macro when produced).
- `window_id = {TICKER}:{YYYY-MM-DD}` (no window length in identity).
- `horizon_contract` on the observation stamps the **primary** path: `accum_10d`.

### Observation contracts (clean break)

| Item | Value |
|------|--------|
| Learning observation contract | `learning_observation.accumulation_discovery.v2` |
| Producer gate | `accumulation-discovery.v2` |

No dual-write or dual-read of v1 multi-row shape. Legacy accum rows are **deleted**, not migrated.

### Path label contracts (accum corpus only)

| Role | Contract id | Sessions |
|------|-------------|----------|
| Aux | `price_path.accum_3d.v1` | 3 |
| **Primary** | `price_path.accum_10d.v1` | 10 |
| Aux | `price_path.accum_20d.v1` | 20 |

Forbidden for accum research defaults, cron, evaluate primary, and docs: `price_path.tactical_3d.v1`, `price_path.swing_10d.v1`.

### Labels / evaluate / cron

- Entry price: session close frozen as `shared.current_price` (same for all path horizons).
- Provisional incomplete horizon: **skip** (no locked UNAVAILABLE).
- Already labeled: **skip** (no `labeled_at` digest conflict on re-run).
- Cron: capture once; labels for **3d, 10d, 20d** (independent runs or wrapper).
- **Cohort evaluate (`research accum evaluate`): product-dropped** for accum — scoring authority is sibling **`ml-saham` challenge**. Primary path grade for corpus remains label contract **`accum_10d`**. See root [BOUNDARY.md](../../BOUNDARY.md).

### Pre-open

Unchanged. Pre-open remains 1 obs / ticker / session with `open_30m` and track snapshots.

## Consequences

- Compatibility / material identity will form a **new** accum cohort after v2 + purge.
- Capture still evaluates three windows (compute cost); persists one row.
- Effective learning N ≈ tickers × sessions, not ×3 windows.
- Operators: **7/30/90 = lookback features; 10d = primary grade.**

## Non-goals

- Matching 7→7 / 30→30 / 90→90 labels  
- Execution-cost labels  
- Historical LQ45 membership platform  
- Preserving or reinterpreting triple-window v1 rows  
