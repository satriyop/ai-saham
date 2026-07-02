# Infrastructure Provider Refactor Plan
_Created: 2026-07-02_

Retrospective action plan following the Playwright → persisted JWT migration (ADR-036).
Four structural improvements, ranked by maintenance impact. Each is independently deliverable.

---

## Priority Overview

| # | Item | Impact | Effort | Status |
|---|------|--------|--------|--------|
| 1 | Shared base class for Stockbit providers | High | Medium | ✅ Done — a623b4b |
| 2 | Centralized SQLite migration runner | High | Medium | ✅ Done — 7613c93 |
| 3 | Application-layer provider factory | Medium | Small | ✅ Done — 5027b4c |
| 4 | Shared SQLite connection per db_path | Low-Med | Small | ✅ Done — 6471391 |

**Out of scope here:** directory rename (`browser/` → `stockbit/`) — cosmetic only, deferred.

---

## Phase 1 — Shared Base Class for Stockbit Providers

### Problem

22 Stockbit provider classes each contain identical boilerplate:

```python
def __init__(self, api_client: "StockbitApiClient | None", db_path: Path) -> None:
    self._api_client = api_client
    self._db_path = Path(db_path).expanduser()
    self._ensure_schema()     # or _ensure_table() — inconsistent naming

def _get_conn(self) -> sqlite3.Connection:
    self._db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(self._db_path))
    conn.row_factory = sqlite3.Row
    return conn
```

Additional inconsistencies:
- 7 providers use `_ensure_schema()`, 6 use `_ensure_table()` — same concept, different names
- 5 providers have `db_path: str | Path = Path("data.db")` default; others require `db_path: Path`
- Some providers have `_get_conn()` helper; others call `sqlite3.connect()` inline

The JWT migration (Phase C) proved the cost: every structural change touches all 22 files.

### Solution

New file: `src/infrastructure/browser/stockbit_base_provider.py`

```python
class StockbitCachingProvider:
    """Base class for all Stockbit providers that cache to SQLite.

    Subclasses implement _ensure_schema() to create their table(s).
    Constructor signature is fixed: (api_client, db_path).
    """

    def __init__(
        self,
        api_client: "StockbitApiClient | None",
        db_path: Path | str = Path("data.db"),
    ) -> None:
        self._api_client = api_client
        self._db_path = Path(db_path).expanduser()
        self._ensure_schema()

    def _get_conn(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        raise NotImplementedError
```

Each provider then becomes:

```python
class StockbitAnalystConsensusProvider(AnalystConsensusProvider, StockbitCachingProvider):
    def __init__(self, api_client, db_path=Path("data.db")) -> None:
        super().__init__(api_client, db_path)

    def _ensure_schema(self) -> None:
        # existing CREATE TABLE + ALTER TABLE logic
        ...
```

### Affected Files

All 22 providers in `src/infrastructure/browser/`:
`stockbit_analyst`, `stockbit_bandar`, `stockbit_broker_distribution`,
`stockbit_company_profile`, `stockbit_corp_action`, `stockbit_earnings`,
`stockbit_forward_estimates`, `stockbit_fundamentals`, `stockbit_insider`,
`stockbit_intraday_broker_chart`, `stockbit_market_time`, `stockbit_order_book`,
`stockbit_running_trade`, `stockbit_running_trade_chart`, `stockbit_seasonality`,
`stockbit_shareholding`, `stockbit_ticker_notation`, `stockbit_universe`,
`stockbit_valuation`  
+ `src/infrastructure/data_providers/stockbit_historical.py`

### What Changes Per Provider

- Add `StockbitCachingProvider` to inheritance chain
- Remove duplicate `__init__` body (keep only extra fields like `_mem_cache`)
- Remove `_get_conn()` definition (inherited)
- Rename `_ensure_table()` → `_ensure_schema()` where inconsistent
- Normalize `db_path` type annotation to `Path | str = Path("data.db")`

### Tests

No new tests needed — existing tests cover the provider behavior.
Run full suite after each provider migration; do them in small batches (3–4 at a time).

### Entry Condition

None. Can start immediately.

### Exit Condition

- `grep -rn "def _get_conn" src/infrastructure/browser/` returns only the base class
- `grep -rn "_ensure_table" src/infrastructure/browser/` returns zero results
- Full test suite green

---

## Phase 2 — Centralized SQLite Migration Runner

### Problem

5 providers manage their own incremental schema migrations via `_MIGRATE_COLUMNS` lists
that run on every `__init__` call:

```python
_MIGRATE_COLUMNS = [
    "ALTER TABLE bandar_detector ADD COLUMN top3_accdist TEXT",
    "ALTER TABLE bandar_detector ADD COLUMN vwap REAL",
    ...
]

def _ensure_schema(self) -> None:
    with sqlite3.connect(self._db_path) as conn:
        conn.execute(_CREATE_TABLE)
        for col_sql in _MIGRATE_COLUMNS:
            try:
                conn.execute(col_sql)
            except sqlite3.OperationalError:
                pass   # column already exists — silently swallowed
```

Problems:
1. **Runs on every instantiation** — a single CLI command triggers this 5+ times per DB open
2. **Silent failure masking** — `except sqlite3.OperationalError: pass` hides real errors
3. **No version state** — impossible to know which migrations have run without inspecting the DB directly
4. **No ordering guarantee** — if two migrations depend on each other, the list order is the only contract

Affected files: `stockbit_bandar`, `stockbit_fundamentals`, `stockbit_shareholding`,
`stockbit_analyst`, `stockbit_seasonality`

### Solution

New file: `src/infrastructure/persistence/sqlite_migration_runner.py`

```python
class SqliteMigrationRunner:
    """Versioned, run-once schema migration runner for SQLite.

    Tracks applied migrations in a `_schema_migrations` table keyed by
    (namespace, version). Each namespace is one provider/table group.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def run(self, namespace: str, migrations: list[tuple[int, str]]) -> None:
        """Apply any unapplied migrations in order. Idempotent."""
        with sqlite3.connect(str(self._db_path)) as conn:
            self._ensure_migration_table(conn)
            applied = self._applied_versions(conn, namespace)
            for version, sql in sorted(migrations, key=lambda x: x[0]):
                if version not in applied:
                    conn.execute(sql)
                    conn.execute(
                        "INSERT INTO _schema_migrations (namespace, version) VALUES (?, ?)",
                        (namespace, version),
                    )

    def _ensure_migration_table(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS _schema_migrations (
                namespace TEXT NOT NULL,
                version   INTEGER NOT NULL,
                applied_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (namespace, version)
            )"""
        )

    def _applied_versions(self, conn: sqlite3.Connection, namespace: str) -> set[int]:
        rows = conn.execute(
            "SELECT version FROM _schema_migrations WHERE namespace = ?", (namespace,)
        ).fetchall()
        return {row[0] for row in rows}
```

Each provider converts its `_MIGRATE_COLUMNS` list to a versioned migrations list:

```python
# Before
_MIGRATE_COLUMNS = [
    "ALTER TABLE bandar_detector ADD COLUMN top3_accdist TEXT",
    "ALTER TABLE bandar_detector ADD COLUMN vwap REAL",
]

# After
_MIGRATIONS: list[tuple[int, str]] = [
    (0, _CREATE_TABLE),
    (1, "ALTER TABLE bandar_detector ADD COLUMN top3_accdist TEXT"),
    (2, "ALTER TABLE bandar_detector ADD COLUMN vwap REAL"),
]

def _ensure_schema(self) -> None:
    SqliteMigrationRunner(self._db_path).run("bandar_detector", _MIGRATIONS)
```

### Affected Files

- New: `src/infrastructure/persistence/sqlite_migration_runner.py`
- New: `tests/infrastructure/persistence/test_sqlite_migration_runner.py`
- Modify: `stockbit_bandar`, `stockbit_fundamentals`, `stockbit_shareholding`,
  `stockbit_analyst`, `stockbit_seasonality`

### Tests

`test_sqlite_migration_runner.py` should cover:
- First run applies all migrations
- Second run is a no-op (idempotent)
- Migrations applied in version order regardless of list order
- Real errors (not `OperationalError: duplicate column`) propagate

### Entry Condition

Phase 1 complete (base class in place) — so `_ensure_schema()` naming is normalized first.

### Exit Condition

- `grep -rn "_MIGRATE_COLUMNS" src/` returns zero results
- `grep -rn "except sqlite3.OperationalError: pass" src/` returns zero results
- Migration runner tests green, full suite green

---

## Phase 3 — Application-Layer Provider Factory

### Problem

CLI adapters currently own provider selection and auth-checking logic. This was partially
fixed during the simplify pass, but the pattern keeps re-emerging with new commands.
Examples from current code:

```python
# learn_commands.py — adapter decides auth + provider wiring
_shared_api_client = None
try:
    from src.infrastructure.browser.stockbit_api_client import create_stockbit_api_client
    from src.infrastructure.browser.playwright_stockbit_provider import StockbitBrokerProvider
    _shared_api_client = create_stockbit_api_client()
except Exception:
    pass
if _shared_api_client and StockbitBrokerProvider(_shared_api_client).is_authenticated():
    running_trade_provider = StockbitRunningTradeProvider(api_client=_shared_api_client)
```

Per CLAUDE.md, adapters may "select dependencies" but not own "fetch strategy or persistence
orchestration decisions." Auth-checking + api_client construction is infrastructure policy,
not adapter logic.

### Solution

New file: `src/application/services/stockbit_session.py`

```python
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.infrastructure.browser.stockbit_api_client import StockbitApiClient

@dataclass(frozen=True)
class StockbitSession:
    api_client: "StockbitApiClient"
    authenticated: bool

def get_stockbit_session() -> StockbitSession | None:
    """Return a StockbitSession if a valid profile exists, else None.

    Never raises. Returns None when:
    - profile directory absent
    - token missing/expired and browser refresh fails
    - any unexpected exception
    """
    try:
        from src.infrastructure.browser.stockbit_api_client import create_stockbit_api_client
        from src.infrastructure.browser.playwright_stockbit_provider import StockbitBrokerProvider
        from src.infrastructure.config.app_config import APP_CFG
        from pathlib import Path
        if not Path(APP_CFG.storage.stockbit_profile_dir).exists():
            return None
        api_client = create_stockbit_api_client()
        authenticated = StockbitBrokerProvider(api_client).is_authenticated()
        return StockbitSession(api_client=api_client, authenticated=authenticated)
    except Exception:
        return None
```

CLI adapters then become:

```python
# learn_commands.py — adapter just wires
from src.application.services.stockbit_session import get_stockbit_session

session = get_stockbit_session()
if session and session.authenticated:
    running_trade_provider = StockbitRunningTradeProvider(api_client=session.api_client)
```

This also consolidates the 4 separate copies of the same try/except/auth-check pattern
currently spread across `learn_commands.py`, `fetch_market_commands.py`,
`stockbit_market_time.py`, and `trade_intraday_commands.py`.

### Affected Files

- New: `src/application/services/stockbit_session.py`
- Modify: `learn_commands.py`, `fetch_market_commands.py`, `trade_intraday_commands.py`,
  `stockbit_market_time.py` — replace inline auth-check blocks with `get_stockbit_session()`

### Tests

- Unit test `get_stockbit_session()` with mocked filesystem and api_client
- Verify `authenticated=False` path doesn't raise

### Entry Condition

None. Can be done independently of Phase 1 and 2.

### Exit Condition

- `grep -rn "StockbitBrokerProvider.*is_authenticated" src/adapters/` returns zero results
- `grep -rn "create_stockbit_api_client" src/adapters/` returns zero results
- Full suite green

---

## Phase 4 — Shared SQLite Connection per db_path

### Problem

13 providers each call `sqlite3.connect(str(self._db_path))` inside every method — a new
connection opened and closed for every cache read and write. A single
`saham analyze risk BBRI` that instantiates 10 providers makes 30–50 SQLite connection
round-trips to the same file.

No data is lost (SQLite handles concurrent openers), but it wastes syscalls and makes
cross-provider transactions impossible.

### Solution

Add to `StockbitCachingProvider` (Phase 1 base class):

```python
import weakref

_conn_registry: weakref.WeakValueDictionary[str, sqlite3.Connection] = weakref.WeakValueDictionary()

class StockbitCachingProvider:
    ...
    def _get_conn(self) -> sqlite3.Connection:
        key = str(self._db_path.resolve())
        conn = _conn_registry.get(key)
        if conn is None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            _conn_registry[key] = conn
        return conn
```

`WeakValueDictionary` means the connection is closed automatically when no provider holds
a reference — no manual cleanup required. `check_same_thread=False` is safe here because
this is a single-process CLI tool.

### Affected Files

Only `src/infrastructure/browser/stockbit_base_provider.py` — if Phase 1 is done first,
this is a 10-line change in one file.

### Entry Condition

Phase 1 complete (base class with `_get_conn()` centralized).

### Exit Condition

- `grep -rn "sqlite3.connect" src/infrastructure/browser/` returns only the base class
- Full suite green

---

## Implementation Order

```
Phase 3  (independent — application-layer factory, small, high clarity gain)
   ↓
Phase 1  (base class — normalizes the 22 providers, unblocks 2 and 4)
   ↓
Phase 2  (migration runner — depends on _ensure_schema() naming from Phase 1)
   ↓
Phase 4  (shared connection — 10-line change once Phase 1 base class exists)
```

Phase 3 can be done in a single PR and merged immediately. Phases 1–2–4 form a natural
sequence and can be one larger PR or three small ones.

---

## Verification (after all phases)

```bash
# No per-provider _get_conn definitions
grep -rn "def _get_conn" src/infrastructure/browser/

# No legacy migration pattern
grep -rn "_MIGRATE_COLUMNS\|_ensure_table" src/infrastructure/browser/

# No auth logic in adapters
grep -rn "is_authenticated\|create_stockbit_api_client" src/adapters/

# Full test suite
python -m pytest tests/ -x -q
```
