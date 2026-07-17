# ADR-019: Unified Fetch Timestamp (`fetched_at: datetime`) on Cached Domain Value Objects

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted — implementation coverage evolved
**Date:** Not recorded (legacy decision)
**Current implementation:** Implemented for audited cached snapshot contracts; do not infer universal coverage for a new cache without checking its value object and repository.
**Decision**
Every domain value object backed by a SQLite cache carries `fetched_at: datetime | None = None`.
Set to `datetime.now()` at fetch time, serialised as an ISO datetime string in the existing
`fetched_date` SQLite column, and round-tripped through `_read_cache()`.
Consumers derive `.date()` for day precision or `.strftime("%Y-%m")` for month precision.

**Implications**

* Single field name and type across all cached snapshot objects.
* No per-consumer ambiguity about data age — callers do not need to know which providers
  used `date` vs `datetime` granularity in storage.
* SQLite column names remain unchanged (`fetched_date` TEXT) — no schema migrations needed
  for the 6 existing providers; only `seasonality_cache` received a new `fetched_at` column.
* TTL checks use `substr(fetched_date, 1, 10)` or `datetime.fromisoformat()` to handle both
  old date-only strings and new ISO datetime strings in the same column, ensuring backward
  compatibility with rows cached before this change.

**Exceptions**

Date naming convention:

* `snapshot_date` — the date a computed assessment/evidence snapshot represents.
* `session_date` — an exchange trading session key for immutable market-session data.
* `report_date` — an issuer/API filing or reporting date.
* `as_of_date` — a caller-supplied evaluation cutoff date, especially for replay/backtest.
* `fetched_at` — the timestamp when data was retrieved and cached.

* `BandarDetectorSnapshot.session_date: date` — the session date is the semantic key for
  immutable end-of-day data, not a cache freshness indicator. Not changed.
* List-row objects (`InsiderTransaction`, `CorporateActionEvent`) — individual records are
  time-series data; the provider manages the batch fetch marker in SQLite. Not changed.
* API data dates (`AnalystConsensus.last_updated`, `ShareholdingComposition.report_date`) —
  these are response dates (when the API last updated the data), distinct from `fetched_at`
  (when we retrieved and cached it). Both coexist on the same object.

**Rationale**
A uniform `datetime` field gives callers full information (date, time) in one field without
forcing them to know the storage granularity of any particular provider. It also closes the
round-trip gap where three providers (`analyst`, `shareholding`, `seasonality`) stored the
timestamp in SQLite but never materialised it onto the returned domain object.
