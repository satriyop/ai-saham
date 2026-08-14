# ADR-070: Stockbit Auth Port and Typed Failures

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted — port contract implemented (2026-08-14); infrastructure adapter and caller migration in progress (issues #3–#5)

**Date:** 2026-08-14

**Amends:** [ADR-036](ADR-036-persisted-jwt-token-store-replaces-playwright-per-invocation-for-stockbit-data-fetching.md) (caller contract only)

**Does not change:** JWT persistence, expiry reading, atomic token-file writes, or the rule that data providers use HTTP rather than launching a browser per request.

## Context

ADR-036 made a persisted RS256 JWT the normal Stockbit path and reserved Playwright for login and on-demand refresh. Callers still could not tell **auth is dead** from **the market returned no rows**: factories returned silent `None`, the HTTP client collapsed 401 / refresh failure / empty payload into the same absence, and pre-open track dual-wired session vs client construction.

A usable JWT must remain offline-capable. Auth recovery must be one **module** behind a small **interface**, with a real **seam** (production adapter + test fake).

## Decision

### 1. ADR-036 vs this ADR

| Concern | Authority |
|---|---|
| Persist JWT, local `exp` / TTL, chmod, never expose token to providers | **ADR-036** (`StockbitTokenStore`) |
| “Is auth usable?”, refresh modes, typed failure vs empty market, who may call refresh | **This ADR** (`StockbitAuthPort`) |

### 2. Port interface

Application-facing port (no JWT string on the interface):

- `ensure_usable()` → Ready | AuthFailure. Valid stored RS256 is Ready without a browser. Otherwise at most one automatic **headless** refresh path, then Ready or AuthFailure.
- `force_refresh(mode=headless|headed)` → Ready | AuthFailure. Explicit recovery. Headless is cron-safe; headed is interactive UI.
- `inspect()` → `StockbitSessionStatus`. Local health only; never the JWT.

AuthFailure kinds (stable meanings): `missing_profile`, `missing_token`, `invalid_token`, `expired`, `refresh_failed`, `auth_ui` (headless cannot complete a login UI).

### 3. Empty market is not auth failure

The HTTP client remains a separate module. After this decision:

- Auth death is **typed** (never silent `None` on migrated paths).
- Empty / unparseable market payloads may still be empty or `None` for provider degrade.
- A valid token with no network browser launch must still work (local-first).

### 4. Dual refresh modes, one interface

Headless auto-ensure and headed recovery are strategies **inside** the same port. Cron calls headless (or `ensure_usable`). Humans call headed. Do not invent a second public “get me a JWT” story.

Cron fail-soft for the scheduled reauth job may remain an **outer shell** (`|| true`). Track and status **fail closed** on AuthFailure.

### 5. PR1 migration scope

First vertical slice: port + test fake (done); production adapter + HTTP client auth typing; wire **reauth** and **status**; wire **pre-open track** onto `ensure_usable`. Other Stockbit construction sites may keep the legacy factory until later tickets.

### 6. CLI mapping (PR1)

AuthFailure maps through the existing CLI error taxonomy as `data_unavailable` with a tip to headed reauth. No new error-category enum is required in PR1. Logs and stdout must not contain JWT or password material.

## Invariants

- Application depends on the port; infrastructure implements refresh and storage; adapters only map outcomes.
- Two adapters justify the seam: production (token store + Playwright refresh) and in-memory fake.
- `inspect` is not proof Stockbit accepted the token; only a live HTTP outcome is.

## Non-goals

- First-time `login` bootstrap redesign.
- Absorbing `browse` or `spy`.
- Putting IEV / order-book / broker provider logic behind the auth port.
- Big-bang migration of every Stockbit session/client construction site in PR1.
- A new CLI error enum value (follow-up allowed).
- Making AuthFailure a success inside track/status.

## Current implementation pointers

- Port and kinds: application `StockbitAuthPort` / `StockbitAuthReady` / `StockbitAuthFailure`
- Test fake: application `FakeStockbitAuth`
- Status DTO: existing `StockbitSessionStatus` (no token field)
- Store (unchanged owner): ADR-036 `StockbitTokenStore`
