# ADR-038: Point-in-Time Enrichment And Conservative Derived Fundamentals

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)
**Status:** Accepted
**Date:** 2026-07-08
**Current implementation:** Point-in-time and conservative derivation rules are binding on audited enrichment paths. Historical-evidence readiness remains gated by the data-quality backlog rather than assumed globally.

### Context

Historical backtesting and walk-forward calibration require that all input signals represent the exact state of information available as of a specific historical date (`as_of_date`), with zero look-ahead leakages.
While candles and broker flows are naturally historical time-series, other corporate/valuation metrics (fundamentals, shareholding structure, analyst consensus, estimates, etc.) are typically retrieved from external APIs as "latest snapshots."

To support valid historical signal replay, we previously converted several single-row cache tables (e.g., `company_fundamentals` and `shareholding_composition`) to multi-row Point-in-Time (PIT) structures. However, since the external data vendor (Stockbit) only returns current state for many endpoints, we have admitted derived historical fundamentals (backfilled from key ratio trends) but need strict rules governing their availability, contents, and fallback logic to protect backtest validity.

### Decision

1. **PIT Capable Enrichment Caches:**
   All tables storing data relevant for signal replay must use a time-series/PIT format (storing one row per `(ticker, fetched_date)` or `(ticker, fetched_at)`) rather than overwriting a single `ticker` row with the latest snapshot. This applies to the following tables:
   - `company_fundamentals`
   - `shareholding_composition`
   - `analyst_cache`
   - `forward_estimates_cache`
   - `ticker_notation_cache`
   - `stock_meta`
   - `company_profile_cache`
   - `seasonality_cache`
   - `earnings_cache`

2. **PIT Replay Constraints:**
   When replaying signals historically (during backtest or backfill), providers must only load cache entries where `fetched_date <= as_of_date` (or `fetched_at <= as_of_date` or `COALESCE(report_date, fetched_date) <= as_of_date`). Any entries fetched after `as_of_date` are future data and must be ignored. If no valid row exists on or before the replay date, the metric is marked unavailable (`None`/`UNKNOWN`).

3. **Authoritative Live Snapshots:**
   Live-fetched snapshots remain the authoritative source of truth for the current date. Fresh API requests store the exact payload returned by the vendor with the current timestamp.

4. **Conservative Derived Fundamentals Availability:**
   Derived historical fundamental rows backfilled from quarterly trend summaries may be generated or populated (e.g., during historical backfill or data import), but their publication date must be conservatively estimated as `period_end_date + 60 days` to reflect typical corporate reporting lag in the IDX. Derived rows must never be read if the replay `as_of_date` is before this availability date.

5. **Derivation Boundaries:**
   Derived fundamental rows are restricted to the fields actually present in historical trend payloads, currently:
   - `net_profit_margin`
   - `revenue_yoy_growth`

   Derived rows must **never** fabricate or guess values for other fundamentals that are only available in live snapshots, including `market_cap_idr`, `piotroski_f_score`, PE/PBV, ROE, or dividend yield. These fields must remain `NULL` in derived rows.

6. **Protection of Live Refreshes:**
   Derived rows must not suppress live cache refreshes. The cache freshness check must ensure that a recently written derived row containing a future/recent date does not trick the system into believing a live snapshot is fresh. Freshness checks must target genuine live-fetched rows.

7. **Zero Authority Scope:**
   This record governs data ingestion and replay integrity. It does not promote company-quality evidence, nor does it modify SignalEngine scoring authority. Company-quality context remains diagnostic with zero scoring weight.

### Consequences

- Historical observations backfilled prior to the start of local EOD snapshots will correctly resolve to `tp_market_cap_bucket: UNKNOWN` and `piotroski_f_score = None`, leaving them ineligible for setup-specific targets that filter on market cap (e.g. `large_cap`).
- The system remains offline-capable for backtesting, but requires live cron observations to run going forward to naturally accumulate the mature `large_cap` labels required to unblock Phase I calibration.
