# ADR-036: Persisted JWT Token Store Replaces Playwright-per-invocation for Stockbit Data Fetching

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted — **caller/auth-failure contract amended by [ADR-070](ADR-070-stockbit-auth-port-and-typed-failures.md)**
**Date:** Not recorded (legacy decision)
**Current implementation:** Implemented — persisted Stockbit token storage is the normal API path; browser login is an explicit refresh/recovery boundary. **Usable-session policy, typed AuthFailure vs empty market data, and dual refresh modes live in ADR-070** (`StockbitAuthPort`). This ADR still owns the JWT file, local expiry, and “providers do not launch a browser per request.”
### Context

Every CLI command that fetched live Stockbit data previously launched a headless Chromium
browser to intercept a Bearer JWT from outgoing request headers, then closed the browser
immediately after. The token was cached in-process for 30 minutes but never persisted to
disk. The next CLI invocation started a new browser — even if the previous token was still
valid (RS256 JWTs typically expire after 8–24 hours).

All 21 Stockbit data providers already used pure `httpx` calls (`_exodus_get`). The browser
was the sole reason Playwright was a runtime dependency for data workflows.

### Decision

1. **`StockbitTokenStore`** persists the JWT to `.stockbit_profile/token.json`. Validity
   uses the `exp` claim from the JWT payload (base64-decoded, no signature verify); falls
   back to `fetched_at + 8h` when `exp` is absent. Write is atomic (`tmp + os.replace`,
   chmod 0600).

2. **`StockbitApiClient`** is a thin authenticated HTTP client: `get(url, params) → dict | None`.
   On 401 it triggers one browser refresh via `extract_exodus_token()` then retries once
   (`already_refreshed` guard prevents infinite loops). It never exposes the token to callers.

3. **One shared `api_client` per CLI invocation.** `create_stockbit_api_client()` builds the
   instance; CLI adapters extract it once and inject it into all providers in the same command.
   This reproduces the old in-process cache benefit without a 30-minute timer.

4. **Playwright is retained** only for interactive commands (`login`, `spy`, `browse`) and the
   `extract_exodus_token()` helper called by `StockbitApiClient` on 401. No data-fetch path
   touches a browser directly.

5. **`StockbitBrokerProvider`** replaces `StockbitPlaywrightBrokerProvider`. The old class is
   deleted. All 21 data providers take `api_client: StockbitApiClient | None` instead of
   `broker_provider`.

### Consequences

- **First invocation** after `saham fetch stockbit login`: zero browser launches for data.
- **Token expired mid-session**: one silent browser launch (< 5s) then all subsequent calls
  in the same process use the refreshed token.
- **Offline / no Playwright**: the `api_client.get()` returns `None`; all providers fall back
  to their DB cache path. System remains fully usable offline.
- **Testing**: tests patch `StockbitApiClient.get` (instance method on the class) rather than
  the removed `_exodus_get` module-level function.

### Skills

- `stockbit-api-explorer` — how to add providers, endpoint patterns, test patterns
- `codebase-known-pitfalls` — `fetch_json` latent bug, single api_client rule, removed symbols
