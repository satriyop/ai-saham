---
name: stockbit-api-explorer
description: >
  How to explore, probe, and integrate new Stockbit Exodus API endpoints into
  the ai-saham codebase. Use this skill whenever the user asks about discovering
  new Stockbit data, spying on API endpoints, probing an endpoint, adding a new
  Stockbit provider, or understanding how the Stockbit data pipeline works.
  Also trigger for: "what other Stockbit data can we use?", "how do I fetch X
  from Stockbit?", "add a new Stockbit signal", "wire up a new Stockbit endpoint".
---

# Stockbit API Explorer

The Stockbit Exodus API (`https://exodus.stockbit.com/`) is the private REST API
behind app.stockbit.com. We access it via a Bearer token (RS256 JWT) intercepted
from authenticated browser sessions using Playwright.

**Rule #0 — Probe first.** Always call a new endpoint in the Python REPL and
inspect the real JSON shape before writing any parser or value object. Past
parser bugs all came from assuming the shape from endpoint names alone.

---

## 1. Getting a Token (Interactive REPL)

```python
from src.infrastructure.browser.playwright_stockbit import (
    StockbitPlaywrightBrokerProvider, _exodus_get
)
p = StockbitPlaywrightBrokerProvider()
token = p._get_token()   # launches Chromium, intercepts Bearer token, closes
```

The token is cached for 30 minutes in-process. Call `_get_token()` once; reuse it.

---

## 2. Probing an Endpoint

```python
import json

url = "https://exodus.stockbit.com/some-endpoint/BBCA"
body = _exodus_get(url, token)

# Pretty-print the full shape
print(json.dumps(body, indent=2))

# Explore nested keys
print(list(body.keys()))                    # top-level keys
print(list(body.get("data", {}).keys()))    # one level in
```

For paginated endpoints add `?page=1&limit=20` and inspect `body["meta"]`
for total pages / counts.

For list endpoints, always check `body["data"][0]` to see one item's shape
before assuming the entire list.

---

## 3. Spying on New Endpoints (Browser Network Tab)

When you suspect Stockbit has data not yet in our catalog:

1. Open `app.stockbit.com` in Chrome, navigate to the stock detail page
2. Open DevTools → Network tab, filter by `exodus.stockbit.com`
3. Interact with the page section that shows the data you want
4. Look for XHR/Fetch requests, copy the Request URL
5. Note query parameters — Stockbit uses enum strings like `INVESTOR_TYPE_ALL`,
   `MARKET_BOARD_REGULER`, `BROKER_SUMMARY_PERIOD_LATEST`
6. Probe the URL in the REPL using `_exodus_get(url, token)` to confirm shape

The known endpoint catalog lives in `references/endpoint-catalog.md`. Check
there first before spelunking the network tab.

---

## 4. Adding a New Provider — Full Pattern

Every Stockbit integration follows this exact layer sequence. Don't skip layers.

```
1. Domain value object    src/domain/value_objects/<name>.py
2. Domain port            src/domain/ports/<name>_provider.py
3. Infrastructure         src/infrastructure/browser/stockbit_<name>.py
4. Wire into use case     src/application/use_case/accumulation_screen.py (or relevant UC)
5. Display in adapter     src/adapters/cli/accumulation_commands.py + swing_commands.py
6. Pre-warm in update     src/adapters/cli/update_commands.py → _fetch_enrichment()
```

See `references/provider-template.md` for a complete copy-paste template with
all six layers filled in.

### Layer checklist

**Value Object** (`frozen=True` dataclass):
- `ticker: str`, plus all data fields
- For daily data: include `session_date: date`
- For periodic data: include `fetched_date: date`
- Properties: `label` (one-line summary string), `to_dict()` (for JSON output)
- If you need a class-level dict (`_SCORE`, `_MAP`): use `ClassVar[...]` annotation
  or it will break `frozen=True`

**Port** (abstract base class):
- Single method, e.g. `get_snapshot(ticker, ...) -> MyValueObject | None`

**Infrastructure Provider**:
- SQLite table creation in `__init__` via `_ensure_table()`
- `_is_cache_fresh(ticker)` — cheap boolean, used by `_fetch_enrichment()`
- `get_xxx(ticker)` — check mem cache → read SQLite → if miss, call `_fetch()`
- `_fetch()` — first line: `if self._provider is None: return None`
  This enforces the read-only contract (see §5 below)
- `_read_cache()` / `_write_cache()` — pure SQLite, no broker needed

**Wire into use case** (`accumulation_screen.py`):
- Add `Optional` field on `AccumulationCandidate` (default `None`)
- Add provider param to `AccumulationScreenUseCase.__init__`
- Add fetch block in `execute()` after existing enrichment blocks
- Add to `to_dict()` via `result.to_dict() if result else None`

**Wire into `StockbitProviders` dataclass** (`accumulation_commands.py`):
- Add slot and `__init__` param
- Add `unavailable()` return value (set to `None`)
- Create provider in `_make_stockbit_providers()` with `broker_provider=None`
- Pass to both `AccumulationScreenUseCase` call sites

**Display** (both `accumulation_commands.py` and `swing_commands.py`):
- Add display block after the HOLDING line in `_print_swing_output()`
- Color logic: GREEN = strong signal, YELLOW = moderate, RED = negative, WHITE = neutral

**Pre-warm** (`update_commands.py` → `_fetch_enrichment()`):
- Import provider
- Instantiate with real `broker_provider`
- Add `_is_cache_fresh()` → cache/fetch block (same pattern as existing providers)

---

## 5. The Read-Only / Write Separation

**This is the most important architectural rule in the data pipeline.**

Analysis commands (`swing analyze`, `swing screen`, `accumulation screen`) must
**never** call external APIs. They only read from SQLite.

```
saham data update  →  creates providers WITH broker_provider  →  can fetch from API
swing analyze      →  creates providers WITH broker_provider=None  →  SQLite only
```

`_make_stockbit_providers()` in analysis adapters always passes
`broker_provider=None`. The `if self._provider is None: return None` guard in
every provider's `_fetch()` enforces this at runtime.

If data isn't in SQLite (user hasn't run `saham data update`), enrichment fields
show as `None` silently. No errors, no API calls.

---

## 6. SQLite Caching Patterns

Choose the pattern based on how often the underlying data changes:

| Data type | Pattern | Cache key | TTL check |
|-----------|---------|-----------|-----------|
| Daily (session data) | `(ticker, session_date)` PK | `ticker + date.today()` | Row exists for today? |
| Quarterly (ROE, F-score, shareholding) | `ticker` PK + `fetched_date` | `ticker` | `(today - fetched_date).days <= 7` |
| Daily but keep history | `(ticker, session_date)` PK | `ticker + date.today()` | Row exists for today? |

```python
# Daily pattern — _is_cache_fresh()
def _is_cache_fresh(self, ticker: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM my_table WHERE ticker=? AND session_date=?",
        (ticker.upper(), date.today().isoformat()),
    ).fetchone()
    return row is not None

# 7-day TTL pattern — _is_cache_fresh()
def _is_cache_fresh(self, ticker: str) -> bool:
    row = conn.execute(
        "SELECT fetched_date FROM my_table WHERE ticker=?",
        (ticker.upper(),),
    ).fetchone()
    if not row:
        return False
    fetched = date.fromisoformat(row[0])
    return (date.today() - fetched).days <= 7
```

---

## References

- `references/endpoint-catalog.md` — all known Exodus endpoints with confirmed shapes
- `references/provider-template.md` — copy-paste template for a complete new provider
- `src/infrastructure/browser/stockbit_bandar.py` — example: daily (ticker, session_date) cache
- `src/infrastructure/browser/stockbit_fundamentals.py` — example: 7-day TTL cache
- `src/infrastructure/browser/stockbit_analyst.py` — simplest provider (no session_date)
- `docs/stockbit_api_end_point.md` — live endpoint catalog in the repo
