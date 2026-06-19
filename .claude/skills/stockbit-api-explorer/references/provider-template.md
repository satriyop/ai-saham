# New Provider Template

Copy-paste template for adding a complete new Stockbit provider.
Replace `MySignal` / `my_signal` / `my_table` / `my_endpoint` throughout.

---

## Layer 1 — Domain Value Object

`src/domain/value_objects/my_signal.py`

```python
"""MySignal — [one-line description of what this data represents]."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import ClassVar  # use ClassVar for any class-level dicts/sets


@dataclass(frozen=True)
class MySignal:
    ticker: str
    # For daily data, include:
    session_date: date
    # For periodic data (7-day TTL), include instead:
    # fetched_date: date

    # Data fields:
    some_value: float
    some_label: str

    # If you need a scoring dict, use ClassVar — required for frozen dataclasses
    _SCORE_MAP: ClassVar[dict[str, int]] = {"High": 2, "Medium": 1, "Low": 0}

    @property
    def score(self) -> int:
        return self._SCORE_MAP.get(self.some_label, 0)

    @property
    def label(self) -> str:
        return f"{self.some_label} | val={self.some_value:.1f}"

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "session_date": self.session_date.isoformat(),
            "some_value": self.some_value,
            "some_label": self.some_label,
            "score": self.score,
        }
```

---

## Layer 2 — Domain Port

`src/domain/ports/my_signal_provider.py`

```python
"""Port: MySignalProvider."""
from __future__ import annotations
from abc import ABC, abstractmethod
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.value_objects.my_signal import MySignal


class MySignalProvider(ABC):
    @abstractmethod
    def get_signal(
        self, ticker: str, session_date: date | None = None
    ) -> "MySignal | None":
        ...
```

---

## Layer 3 — Infrastructure Provider

`src/infrastructure/browser/stockbit_my_signal.py`

```python
"""StockbitMySignalProvider — [what data, confirmed date].

Calls /my-endpoint/{ticker}?param=VALUE
Response shape (confirmed YYYY-MM-DD, BBCA):
  data.some_field  → ...

Caching: SQLite table `my_table` keyed by (ticker, session_date).
[OR: keyed by ticker with 7-day TTL on fetched_date]
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from src.domain.ports.my_signal_provider import MySignalProvider
from src.domain.value_objects.my_signal import MySignal

if TYPE_CHECKING:
    from src.infrastructure.browser.playwright_stockbit import StockbitPlaywrightBrokerProvider

logger = logging.getLogger(__name__)

_URL = "https://exodus.stockbit.com/my-endpoint/{ticker}?param=VALUE"

# For 7-day TTL providers:
_CACHE_TTL_DAYS = 7

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS my_table (
    ticker        TEXT NOT NULL,
    session_date  TEXT NOT NULL,
    some_value    REAL,
    some_label    TEXT,
    PRIMARY KEY (ticker, session_date)
)
"""
# For 7-day TTL (single row per ticker):
# PRIMARY KEY (ticker), with fetched_date TEXT NOT NULL column instead of session_date


def _parse(ticker: str, session_date: date, body: dict) -> MySignal | None:
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        return None

    try:
        some_value = float(data.get("some_field") or 0)
        some_label = str(data.get("some_label") or "").strip()
    except (TypeError, ValueError):
        return None

    return MySignal(
        ticker=ticker.upper(),
        session_date=session_date,
        some_value=some_value,
        some_label=some_label,
    )


class StockbitMySignalProvider(MySignalProvider):
    """Fetches [signal name] from Stockbit Exodus API.

    SQLite cache keyed by (ticker, session_date). [Explain TTL rationale.]
    """

    def __init__(
        self,
        broker_provider: "StockbitPlaywrightBrokerProvider | None",
        db_path: Path,
    ) -> None:
        self._provider = broker_provider
        self._db_path = db_path
        self._mem_cache: dict[tuple[str, str], MySignal | None] = {}
        self._ensure_table()

    def _ensure_table(self) -> None:
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(_CREATE_TABLE)
        except Exception as e:
            logger.warning("my_table: failed to create cache table: %s", e)

    def _is_cache_fresh(self, ticker: str) -> bool:
        """True if a row exists for today's session date."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                row = conn.execute(
                    "SELECT 1 FROM my_table WHERE ticker=? AND session_date=? LIMIT 1",
                    (ticker.upper(), date.today().isoformat()),
                ).fetchone()
            return row is not None
        except Exception:
            return False

    def get_signal(
        self, ticker: str, session_date: date | None = None
    ) -> MySignal | None:
        target_date = session_date or date.today()
        key = (ticker.upper(), target_date.isoformat())

        if key in self._mem_cache:
            return self._mem_cache[key]

        cached = self._read_cache(ticker.upper(), target_date)
        if cached is not None:
            self._mem_cache[key] = cached
            return cached

        result = self._fetch(ticker.upper(), target_date)
        self._mem_cache[key] = result
        if result is not None:
            self._write_cache(result)
        return result

    def _read_cache(self, ticker: str, target_date: date) -> MySignal | None:
        try:
            with sqlite3.connect(self._db_path) as conn:
                row = conn.execute(
                    "SELECT some_value, some_label FROM my_table "
                    "WHERE ticker=? AND session_date=?",
                    (ticker, target_date.isoformat()),
                ).fetchone()
            if not row:
                return None
            return MySignal(
                ticker=ticker,
                session_date=target_date,
                some_value=float(row[0] or 0),
                some_label=str(row[1] or ""),
            )
        except Exception as e:
            logger.warning("my_table: cache read failed for %s: %s", ticker, e)
            return None

    def _write_cache(self, sig: MySignal) -> None:
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO my_table "
                    "(ticker, session_date, some_value, some_label) VALUES (?,?,?,?)",
                    (sig.ticker, sig.session_date.isoformat(), sig.some_value, sig.some_label),
                )
        except Exception as e:
            logger.warning("my_table: cache write failed for %s: %s", sig.ticker, e)

    def _fetch(self, ticker: str, session_date: date) -> MySignal | None:
        # This guard enforces the read-only contract for analysis commands.
        if self._provider is None:
            return None
        try:
            from src.infrastructure.browser.playwright_stockbit import _exodus_get
            token = self._provider._get_token()
            url = _URL.format(ticker=ticker)
            body = _exodus_get(url, token)
            if not body:
                logger.debug("Empty response for %s", ticker)
                return None
            result = _parse(ticker, session_date, body)
            if result:
                logger.debug("MySignal %s → %s", ticker, result.label)
            return result
        except Exception as e:
            logger.warning("MySignal fetch failed for %s: %s", ticker, e)
            return None
```

---

## Layer 4 — Wire into Use Case

`src/application/use_case/accumulation_screen.py`

```python
# Add to TYPE_CHECKING block:
from src.domain.value_objects.my_signal import MySignal
from src.domain.ports.my_signal_provider import MySignalProvider

# Add field to AccumulationCandidate:
my_signal: "MySignal | None" = None

# Add to AccumulationCandidate.to_dict():
"my_signal": self.my_signal.to_dict() if self.my_signal else None,

# Add param to AccumulationScreenUseCase.__init__:
my_signal_provider: "MySignalProvider | None" = None,

# Add fetch block in execute() after existing enrichment:
if self._my_signal_provider:
    try:
        signal = self._my_signal_provider.get_signal(ticker)
        candidate = AccumulationCandidate(
            **{**candidate.__dict__, "my_signal": signal}
        )
    except Exception:
        pass
```

---

## Layer 5 — Wire into StockbitProviders + Display

`src/adapters/cli/accumulation_commands.py`

```python
# In StockbitProviders.__slots__ / __init__:
"my_signal_prov",

# In unavailable():
my_signal_prov=None,

# In _make_stockbit_providers() (read-only, no broker):
my_signal_prov=StockbitMySignalProvider(broker_provider=None, db_path=db_path),

# In AccumulationScreenUseCase call site:
my_signal_provider=_sb.my_signal_prov,

# Display block (after HOLDING section):
if c.my_signal is not None:
    sig = c.my_signal
    color = typer.colors.GREEN if sig.score >= 2 else typer.colors.YELLOW if sig.score >= 1 else typer.colors.WHITE
    typer.echo(typer.style(f"    🔎 SIGNAL: {sig.label}", fg=color))
```

Repeat same display addition in `swing_commands.py` `_print_swing_output()`.

---

## Layer 6 — Pre-warm in saham data update

`src/adapters/cli/update_commands.py` → `_fetch_enrichment()`

```python
# Import:
from src.infrastructure.browser.stockbit_my_signal import StockbitMySignalProvider

# Instantiate with real broker_provider:
my_signal_prov = StockbitMySignalProvider(broker_provider=broker_provider, db_path=db_path)

# Cache check + fetch:
if my_signal_prov._is_cache_fresh(ticker):
    cached.append("signal")
elif _run("signal", lambda: my_signal_prov.get_signal(ticker)):
    fetched.append("signal")
```
