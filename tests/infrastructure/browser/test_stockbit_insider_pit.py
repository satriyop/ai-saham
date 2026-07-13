import sqlite3
from datetime import date

from src.domain.value_objects.insider_transaction import InsiderTransaction
from src.infrastructure.browser.stockbit_insider import StockbitInsiderActivityProvider


class FailingApiClient:
    def get(self, url):
        raise AssertionError("network must not be called during PIT replay")


def _insert_insider_row(
    db_path,
    *,
    ticker: str = "BBCA",
    name: str = "Jane Doe",
    role: str = "DIREKTUR",
    action_type: str = "BUY",
    shares: int = 1000,
    price: float = 5000.0,
    transaction_date: date = date(2026, 5, 20),
    fetched_date: date = date(2026, 6, 1),
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO insider_cache
                (ticker, name, role, action_type, shares, price, transaction_date,
                 ownership_before_pct, ownership_after_pct, fetched_date)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                ticker,
                name,
                role,
                action_type,
                shares,
                price,
                transaction_date.isoformat(),
                0.0,
                0.0,
                fetched_date.isoformat(),
            ),
        )


def test_insider_pit_ignores_future_fetched_rows(tmp_path):
    db_path = tmp_path / "stockbit.db"
    provider = StockbitInsiderActivityProvider(api_client=None, db_path=db_path)
    _insert_insider_row(
        db_path,
        transaction_date=date(2026, 5, 20),
        fetched_date=date(2026, 7, 1),
    )

    transactions = provider.get_insider_transactions(
        "BBCA",
        from_date=date(2026, 5, 1),
        to_date=date(2026, 6, 1),
        action_type="ALL",
        as_of_date=date(2026, 6, 1),
    )

    assert transactions == []


def test_insider_pit_returns_rows_fetched_on_or_before_as_of_date(tmp_path):
    db_path = tmp_path / "stockbit.db"
    provider = StockbitInsiderActivityProvider(api_client=None, db_path=db_path)
    _insert_insider_row(
        db_path,
        transaction_date=date(2026, 5, 20),
        fetched_date=date(2026, 6, 1),
    )

    transactions = provider.get_insider_transactions(
        "BBCA",
        from_date=date(2026, 5, 1),
        to_date=date(2026, 6, 1),
        action_type="ALL",
        as_of_date=date(2026, 6, 1),
    )

    assert len(transactions) == 1
    assert transactions[0].name == "Jane Doe"
    assert transactions[0].transaction_date == date(2026, 5, 20)


def test_insider_pit_read_does_not_call_network(tmp_path):
    db_path = tmp_path / "stockbit.db"
    provider = StockbitInsiderActivityProvider(
        api_client=FailingApiClient(),
        db_path=db_path,
    )

    transactions = provider.get_insider_transactions(
        "BBCA",
        from_date=date(2026, 5, 1),
        to_date=date(2026, 6, 1),
        action_type="ALL",
        as_of_date=date(2026, 6, 1),
    )

    assert transactions == []


def test_insider_write_cache_preserves_historical_snapshots(tmp_path):
    db_path = tmp_path / "stockbit.db"
    provider = StockbitInsiderActivityProvider(api_client=None, db_path=db_path)
    _insert_insider_row(db_path, fetched_date=date(2026, 6, 1))

    provider._cache.write(
        "BBCA",
        [
            InsiderTransaction(
                ticker="BBCA",
                name="Jane Doe",
                role="DIREKTUR",
                action_type="BUY",
                shares=2000,
                price=5100.0,
                transaction_date=date(2026, 5, 20),
                ownership_before_pct=0.0,
                ownership_after_pct=0.0,
            )
        ],
    )

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT COUNT(DISTINCT fetched_date)
            FROM insider_cache
            WHERE ticker='BBCA' AND name='Jane Doe'
            """
        ).fetchone()[0]

    assert rows == 2


def test_insider_pit_dedupes_logical_transaction_to_latest_eligible_snapshot(tmp_path):
    db_path = tmp_path / "stockbit.db"
    provider = StockbitInsiderActivityProvider(api_client=None, db_path=db_path)
    _insert_insider_row(db_path, shares=1000, fetched_date=date(2026, 6, 1))
    _insert_insider_row(db_path, shares=2000, fetched_date=date(2026, 6, 15))
    _insert_insider_row(db_path, shares=3000, fetched_date=date(2026, 7, 1))

    transactions = provider.get_insider_transactions(
        "BBCA",
        from_date=date(2026, 5, 1),
        to_date=date(2026, 6, 30),
        action_type="ALL",
        as_of_date=date(2026, 6, 20),
    )

    assert len(transactions) == 1
    assert transactions[0].shares == 2000


def test_insider_pit_empty_sentinel_does_not_return_older_rows(tmp_path):
    db_path = tmp_path / "stockbit.db"
    provider = StockbitInsiderActivityProvider(api_client=None, db_path=db_path)
    _insert_insider_row(db_path, shares=1000, fetched_date=date(2026, 6, 1))
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO insider_cache
                (ticker, name, role, action_type, shares, price, transaction_date,
                 ownership_before_pct, ownership_after_pct, fetched_date)
            VALUES ('BBCA', '__NONE__', '', 'NONE', 0, 0, '1970-01-01',
                    0, 0, '2026-06-15')
            """
        )

    transactions = provider.get_insider_transactions(
        "BBCA",
        from_date=date(2026, 5, 1),
        to_date=date(2026, 6, 30),
        action_type="ALL",
        as_of_date=date(2026, 6, 20),
    )

    assert transactions == []


def test_insider_old_cache_schema_migrates_to_fetched_date_primary_key(tmp_path):
    db_path = tmp_path / "stockbit.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE insider_cache (
                ticker                TEXT NOT NULL,
                name                  TEXT NOT NULL DEFAULT '',
                role                  TEXT NOT NULL DEFAULT '',
                action_type           TEXT NOT NULL,
                shares                INTEGER NOT NULL DEFAULT 0,
                price                 REAL NOT NULL DEFAULT 0,
                transaction_date      TEXT NOT NULL,
                ownership_before_pct  REAL NOT NULL DEFAULT 0,
                ownership_after_pct   REAL NOT NULL DEFAULT 0,
                fetched_date          TEXT NOT NULL,
                PRIMARY KEY (ticker, name, transaction_date, action_type)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO insider_cache
                (ticker, name, role, action_type, shares, price, transaction_date,
                 ownership_before_pct, ownership_after_pct, fetched_date)
            VALUES ('BBCA', 'Jane Doe', 'DIREKTUR', 'BUY', 1000, 5000,
                    '2026-05-20', 0, 0, '2026-06-01')
            """
        )

    StockbitInsiderActivityProvider(api_client=None, db_path=db_path)

    with sqlite3.connect(db_path) as conn:
        pk_cols = [
            row[1]
            for row in sorted(
                conn.execute("PRAGMA table_info(insider_cache)").fetchall(),
                key=lambda r: r[5],
            )
            if row[5] > 0
        ]
        count = conn.execute("SELECT COUNT(*) FROM insider_cache").fetchone()[0]

    assert pk_cols == [
        "ticker",
        "name",
        "transaction_date",
        "action_type",
        "fetched_date",
    ]
    assert count == 1
