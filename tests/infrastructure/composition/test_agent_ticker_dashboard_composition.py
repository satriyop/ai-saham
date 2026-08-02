import hashlib
import sqlite3
from datetime import date

import pytest

from src.application.dto.ticker_dashboard import GetTickerDashboardRequest
from src.infrastructure.composition.view_ticker_deps import (
    build_read_only_ticker_dashboard_use_case,
)
from src.infrastructure.persistence.sqlite_ticker_dashboard_source import (
    SQLiteTickerDashboardSource,
)

pytestmark = pytest.mark.agent


def _identity(path) -> tuple[str, int, int]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with sqlite3.connect(path) as connection:
        schema_version = int(connection.execute("PRAGMA schema_version").fetchone()[0])
        data_version = int(connection.execute("PRAGMA data_version").fetchone()[0])
    return digest, schema_version, data_version


def test_read_only_composition_does_not_mutate_existing_database(tmp_path) -> None:
    db_path = tmp_path / "dashboard.db"
    SQLiteTickerDashboardSource(db_path)
    before = _identity(db_path)

    use_case = build_read_only_ticker_dashboard_use_case(db_path)
    dashboard = use_case.execute(
        GetTickerDashboardRequest(
            ticker="BBCA",
            brief=False,
            today=date(2026, 7, 24),
        )
    )

    assert dashboard.ticker == "BBCA"
    assert _identity(db_path) == before


def test_read_only_composition_never_creates_missing_database(tmp_path) -> None:
    db_path = tmp_path / "missing" / "dashboard.db"

    with pytest.raises(FileNotFoundError, match="database is unavailable"):
        build_read_only_ticker_dashboard_use_case(db_path)

    assert not db_path.exists()
    assert not db_path.parent.exists()
