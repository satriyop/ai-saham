# ADR-035: Port Method Naming Convention

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted
**Date:** Not recorded (legacy decision)
**Current implementation:** Aligned — provider/repository method prefixes describe their I/O boundary; verify legacy ports before renaming.
### Context

The codebase intentionally has both provider ports and repository ports. Their
method prefixes look inconsistent unless the source boundary is explicit.

### Decision

Port method prefixes distinguish data source boundaries:

| Prefix | Meaning | Examples |
|--------|---------|----------|
| `fetch_*` | Obtain data from a live/external provider or an interaction boundary. May perform network/browser/API work. | `MarketDataProvider.fetch_daily_ohlcv`, `BrokerDataProvider.fetch_broker_summary`, `NewsProvider.fetch_headlines` |
| `get_*` | Read from local repositories, caches, deterministic services, or enrichment providers that expose cached/as-of semantics. | `MarketDataRepository.get_candles`, `BrokerDataRepository.get_broker_summaries`, `ShareholdingProvider.get_composition` |

`MarketDataProvider.fetch_daily_ohlcv()` and `MarketDataRepository.get_candles()`
are not competing names for one operation: the provider crosses an external
source boundary; the repository reads persisted/cache-backed candles.

### Guidance

New live provider ports should use `fetch_*`. New repository/cache ports should
use `get_*`. If a provider exposes historical/as-of cached enrichment behind the
interface, `get_*` is acceptable when the caller is not asking it to perform a
fresh external fetch. Do not mechanically rename existing ports unless the
boundary meaning is wrong.
