# ADR-052: `saham today` is a live-first adapter surface with offline fallback

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted — implementation in progress (2026-07-28)
**Date:** 2026-07-28
**Scopes:** [ADR-011](ADR-011-offline-capable-cli-as-primary-interface.md) (offline-capable CLI)
**Depends on:** [ADR-040](ADR-040-manual-dependency-injection-and-composition-roots.md),
[ADR-049](ADR-049-database-owned-learning-pipeline-clean-break.md),
[ADR-050](ADR-050-cli-verb-contracts.md)

## Context

`saham today` was defined as a strictly offline read: "read-only daily briefing dashboard
from local cached data … does not fetch." In practice this made the most-used morning
command show yesterday's state. On 2026-07-28 the briefing suppressed its accumulation
screen because `broker_flow` coverage was `5/45` — stale local cache, not a live-market
condition — and reported a `local_clock`-inferred market status with no IDX-holiday
awareness. The offline contract, intended to guarantee availability, instead guaranteed
staleness at the exact moment freshness matters most.

The deeper principle behind ADR-011 (offline-first) is **reproducibility and availability**:
the engine must run without the network, and the same data + config must produce the same
result. That principle lives in the *engine/domain*, not in a specific adapter's fetch policy.

## Decision

`saham today` becomes **live-first with graceful offline fallback**. This **scopes**, and does
not reverse, ADR-011:

- **Offline-first still holds for the engine/domain.** Every use case, indicator, rule, and
  the deterministic analysis flow remain fully offline-capable. Nothing about this decision
  lets domain logic depend on the network.
- **`today` is a live *adapter* surface.** On each run it refreshes its live-sensitive inputs
  (candles, broker flow, market context, corporate-action calendar) by reusing the existing
  `RefreshDailyWorkspaceUseCase` — **the fetch writes to cache and the briefing renders from
  cache**, so a completed run remains reproducible as "the state as of the last refresh."
- **Reliability is preserved by fallback.** The refresh is timeboxed; on any failure, offline,
  or timeout, `today` degrades to a cached render with explicit `⚠ stale` / `CACHED` markers
  and a warning. `today` never produces an empty briefing because a fetch failed.
- **`--offline` / `--no-fetch`** forces the instant cache-only read (the pre-ADR behaviour).
- **Pre-open lock-window guard.** During the NCP lock window (pre-open session), `today`
  prefers the committed 08:57 `research pre-open capture` decision over any live IEV probe, so
  it never shows a pre-lock number the engine never decided on (see [ADR-049], [ADR-048]).

The header exposes the provenance of every run: `LIVE`, `CACHED`, `LOCK_WINDOW`, or
`HISTORICAL`.

## Consequences

- **Positive:** the briefing reflects the current session; `broker_flow`/regime staleness
  self-heals; authoritative Stockbit market status replaces the `local_clock` guess when a
  session exists; realized-open-vs-IEP reconciliation becomes possible.
- **Cost / risk:** live-first makes `today` depend on the fetch stack (session/network/rate
  limits) and mutates the cache on read. Both are mitigated: the fallback render keeps the
  "always works" property, and reproducibility is preserved by rendering from cache.
  Write-on-read contention with the 18:30 cron and the TUI auto-load loop is a known
  operational risk (follow-up: consider WAL journal mode / a short refresh TTL).
- **Boundary:** `today` remains a *read/refresh* surface. It does not gain decision authority
  (`plan swing` / `assess pre-open` own that per ADR-050), and the refresh logic is reused
  application workflow — the adapter owns no new fetch/cache policy.
