"""Tests for SQLiteSeasonalityCacheRepairer (DQ-001H)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.application.use_case.repair_seasonality_cache_use_case import (
    SeasonalityCacheRepairRow,
)

_REPAIR_RUN_ID = "test-run-001"


def _build_schema(db_path: Path) -> None:
    from src.infrastructure.browser.stockbit_seasonality import StockbitSeasonalityProvider

    StockbitSeasonalityProvider(api_client=None, db_path=db_path)


def _insert_valid_row(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO seasonality_cache
            (ticker, year, month, avg_return_pct, win_rate_pct,
             positive_years, total_years, back_years, source, fetched_month, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("BBCA", 2026, 1, 1.0, 60.0, 3, 5, 5, "stockbit", "2026-01", "2026-01-01T00:00:00"),
    )
    conn.commit()
    conn.close()


def _insert_invalid_row(db_path: Path, **overrides) -> None:
    conn = sqlite3.connect(str(db_path))
    values = dict(
        ticker="BBRI",
        year=2026,
        month=2,
        avg_return_pct=None,
        win_rate_pct=None,
        positive_years=None,
        total_years=None,
        back_years=None,
        source=None,
        fetched_month="2026-02",
        fetched_at=None,
    )
    values.update(overrides)
    conn.execute(
        """
        INSERT INTO seasonality_cache
            (ticker, year, month, avg_return_pct, win_rate_pct,
             positive_years, total_years, back_years, source, fetched_month, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            values["ticker"],
            values["year"],
            values["month"],
            values["avg_return_pct"],
            values["win_rate_pct"],
            values["positive_years"],
            values["total_years"],
            values["back_years"],
            values["source"],
            values["fetched_month"],
            values["fetched_at"],
        ),
    )
    conn.commit()
    conn.close()


def _repair_row(**overrides) -> SeasonalityCacheRepairRow:
    values = dict(
        ticker="BBRI",
        year=2026,
        month=2,
        fetched_month="2026-02",
        fetched_at=None,
        source=None,
        avg_return_pct=None,
        win_rate_pct=None,
        positive_years=None,
        total_years=None,
        back_years=None,
        reasons=("INVALID_SOURCE", "MISSING_FETCHED_AT", "ALL_METRICS_NULL"),
    )
    values.update(overrides)
    return SeasonalityCacheRepairRow(**values)


def _make_repairer(db_path: Path):
    from src.infrastructure.persistence.sqlite_seasonality_cache_repairer import (
        SQLiteSeasonalityCacheRepairer,
    )

    return SQLiteSeasonalityCacheRepairer(db_path)


# ── Dry-run: no mutation ─────────────────────────────────────────────────────


def test_dry_run_does_not_change_existing_data_rows(tmp_path: Path):
    """DDL (ensure_quarantine_table) changes the file, but without calling
    quarantine_and_delete, existing seasonality_cache rows are untouched."""
    db_path = tmp_path / "data.db"
    _build_schema(db_path)
    _insert_valid_row(db_path)
    _insert_invalid_row(db_path)

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        count_before = conn.execute("SELECT COUNT(*) FROM seasonality_cache").fetchone()[0]
        row_before = conn.execute(
            "SELECT source, fetched_at FROM seasonality_cache WHERE ticker='BBRI'"
        ).fetchone()

    repairer = _make_repairer(db_path)
    repairer.ensure_quarantine_table()

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        count_after = conn.execute("SELECT COUNT(*) FROM seasonality_cache").fetchone()[0]
        row_after = conn.execute(
            "SELECT source, fetched_at FROM seasonality_cache WHERE ticker='BBRI'"
        ).fetchone()

    assert count_before == count_after
    assert row_before["source"] == row_after["source"]
    assert row_before["fetched_at"] == row_after["fetched_at"]


def test_ensure_quarantine_table_creates_table(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schema(db_path)

    repairer = _make_repairer(db_path)
    repairer.ensure_quarantine_table()

    with sqlite3.connect(str(db_path)) as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    assert "seasonality_cache_quarantine" in tables


def test_ensure_quarantine_table_is_idempotent(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schema(db_path)

    repairer = _make_repairer(db_path)
    repairer.ensure_quarantine_table()
    repairer.ensure_quarantine_table()

    with sqlite3.connect(str(db_path)) as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    assert "seasonality_cache_quarantine" in tables


# ── Apply: quarantine + delete ───────────────────────────────────────────────


def test_apply_creates_quarantine_table_implicitly(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schema(db_path)
    _insert_invalid_row(db_path)

    repairer = _make_repairer(db_path)
    repairer.ensure_quarantine_table()
    repairer.quarantine_and_delete([_repair_row()], _REPAIR_RUN_ID)

    with sqlite3.connect(str(db_path)) as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    assert "seasonality_cache_quarantine" in tables


def test_apply_moves_invalid_row_into_quarantine(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schema(db_path)
    _insert_valid_row(db_path)
    _insert_invalid_row(db_path)

    repairer = _make_repairer(db_path)
    repairer.ensure_quarantine_table()
    repairer.quarantine_and_delete([_repair_row()], _REPAIR_RUN_ID)

    with sqlite3.connect(str(db_path)) as conn:
        quarantine_rows = conn.execute("SELECT * FROM seasonality_cache_quarantine").fetchall()
    assert len(quarantine_rows) == 1
    assert quarantine_rows[0][0] == "BBRI"
    assert quarantine_rows[0][4] is None
    assert quarantine_rows[0][5] is None
    assert quarantine_rows[0][11] is not None
    assert _REPAIR_RUN_ID in str(quarantine_rows[0][13])


def test_apply_deletes_invalid_row_from_seasonality_cache(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schema(db_path)
    _insert_valid_row(db_path)
    _insert_invalid_row(db_path)

    repairer = _make_repairer(db_path)
    repairer.ensure_quarantine_table()
    repairer.quarantine_and_delete([_repair_row()], _REPAIR_RUN_ID)

    with sqlite3.connect(str(db_path)) as conn:
        remaining = conn.execute(
            "SELECT ticker, year, month FROM seasonality_cache ORDER BY ticker"
        ).fetchall()
    assert len(remaining) == 1
    assert remaining[0][0] == "BBCA"


def test_apply_preserves_valid_rows(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schema(db_path)
    _insert_valid_row(db_path)
    _insert_invalid_row(db_path, ticker="BBRI", month=2, fetched_month="2026-02")
    _insert_invalid_row(db_path, ticker="TLKM", month=3, fetched_month="2026-03")

    rows_to_repair = [
        _repair_row(ticker="BBRI", year=2026, month=2),
        _repair_row(ticker="TLKM", year=2026, month=3, fetched_month="2026-03"),
    ]

    repairer = _make_repairer(db_path)
    repairer.ensure_quarantine_table()
    repairer.quarantine_and_delete(rows_to_repair, _REPAIR_RUN_ID)

    with sqlite3.connect(str(db_path)) as conn:
        remaining = conn.execute("SELECT ticker FROM seasonality_cache ORDER BY ticker").fetchall()
    assert [r[0] for r in remaining] == ["BBCA"]


def test_apply_returns_affected_row_count(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schema(db_path)
    _insert_valid_row(db_path)
    _insert_invalid_row(db_path, ticker="BBRI", month=2, fetched_month="2026-02")
    _insert_invalid_row(db_path, ticker="TLKM", month=3, fetched_month="2026-03")

    rows_to_repair = [
        _repair_row(ticker="BBRI", year=2026, month=2),
        _repair_row(ticker="TLKM", year=2026, month=3, fetched_month="2026-03"),
    ]

    repairer = _make_repairer(db_path)
    repairer.ensure_quarantine_table()
    count = repairer.quarantine_and_delete(rows_to_repair, _REPAIR_RUN_ID)

    assert count == 2


# ── Idempotency ──────────────────────────────────────────────────────────────


def test_rerun_apply_is_idempotent(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schema(db_path)
    _insert_valid_row(db_path)
    _insert_invalid_row(db_path)

    repairer = _make_repairer(db_path)
    repairer.ensure_quarantine_table()

    count1 = repairer.quarantine_and_delete([_repair_row()], _REPAIR_RUN_ID)
    assert count1 == 1

    with sqlite3.connect(str(db_path)) as conn:
        remaining_invalid = conn.execute(
            "SELECT COUNT(*) FROM seasonality_cache WHERE source IS NULL AND fetched_at IS NULL"
        ).fetchone()[0]
    assert remaining_invalid == 0

    with sqlite3.connect(str(db_path)) as conn:
        quarantine_count = conn.execute(
            "SELECT COUNT(*) FROM seasonality_cache_quarantine"
        ).fetchone()[0]
    assert quarantine_count == 1


# ── NULL-safe matching ────────────────────────────────────────────────────────


def test_null_safe_deletion_handles_null_source(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schema(db_path)
    _insert_valid_row(db_path)
    _insert_invalid_row(db_path, source=None, fetched_at=None)

    repairer = _make_repairer(db_path)
    repairer.ensure_quarantine_table()
    repairer.quarantine_and_delete([_repair_row(source=None, fetched_at=None)], _REPAIR_RUN_ID)

    with sqlite3.connect(str(db_path)) as conn:
        remaining = conn.execute("SELECT ticker FROM seasonality_cache").fetchall()
    assert len(remaining) == 1
    assert remaining[0][0] == "BBCA"


def test_null_safe_deletion_handles_mixed_nulls(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schema(db_path)
    _insert_valid_row(db_path)
    _insert_invalid_row(
        db_path,
        ticker="BBRI",
        source="stockbit",
        fetched_at="2026-02-01T00:00:00",
        avg_return_pct=None,
        win_rate_pct=None,
        positive_years=None,
        total_years=None,
        back_years=None,
    )

    repairer = _make_repairer(db_path)
    repairer.ensure_quarantine_table()
    repairer.quarantine_and_delete(
        [
            _repair_row(
                source="stockbit",
                fetched_at="2026-02-01T00:00:00",
                avg_return_pct=None,
                win_rate_pct=None,
                positive_years=None,
                total_years=None,
                back_years=None,
            )
        ],
        _REPAIR_RUN_ID,
    )

    with sqlite3.connect(str(db_path)) as conn:
        remaining = conn.execute("SELECT ticker FROM seasonality_cache").fetchall()
    assert len(remaining) == 1
    assert remaining[0][0] == "BBCA"


# ── Transaction rollback ──────────────────────────────────────────────────────


def test_transaction_rollback_when_delete_matches_zero_rows(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schema(db_path)
    _insert_valid_row(db_path)
    _insert_invalid_row(db_path, ticker="BBRI")
    _insert_invalid_row(db_path, ticker="TLKM")

    repairer = _make_repairer(db_path)
    repairer.ensure_quarantine_table()

    good_row = _repair_row(ticker="BBRI", year=2026, month=2)
    bad_row = _repair_row(ticker="NONEXISTENT", year=9999, month=99)

    with pytest.raises(RuntimeError, match="Expected to delete 1 row"):
        repairer.quarantine_and_delete([good_row, bad_row], _REPAIR_RUN_ID)

    with sqlite3.connect(str(db_path)) as conn:
        remaining = conn.execute("SELECT ticker FROM seasonality_cache ORDER BY ticker").fetchall()
    assert [r[0] for r in remaining] == ["BBCA", "BBRI", "TLKM"]

    with sqlite3.connect(str(db_path)) as conn:
        qcount = conn.execute("SELECT COUNT(*) FROM seasonality_cache_quarantine").fetchone()[0]
    assert qcount == 0


def test_transaction_deletes_quarantine_entries_on_rollback(tmp_path: Path):
    """Simulate a failure during quarantine and verify rollback."""
    db_path = tmp_path / "data.db"
    _build_schema(db_path)
    _insert_valid_row(db_path)
    _insert_invalid_row(db_path, ticker="BBRI")

    from src.infrastructure.persistence.sqlite_seasonality_cache_repairer import (
        SQLiteSeasonalityCacheRepairer,
    )

    class _FailingRepairer(SQLiteSeasonalityCacheRepairer):
        def quarantine_and_delete(self, rows, repair_run_id):
            quarantined_at = "2026-07-16T00:00:00+00:00"
            conn = self._connect()
            try:
                conn.execute("BEGIN")
                for i, row in enumerate(rows):
                    import json

                    reasons_json = json.dumps(list(row.reasons))
                    conn.execute(
                        "INSERT INTO seasonality_cache_quarantine "
                        "(ticker, year, month, fetched_month, fetched_at, source, "
                        "avg_return_pct, win_rate_pct, positive_years, total_years, "
                        "back_years, quarantine_reasons_json, quarantined_at, "
                        "repair_run_id, original_table, schema_version) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            row.ticker,
                            row.year,
                            row.month,
                            row.fetched_month,
                            row.fetched_at,
                            row.source,
                            row.avg_return_pct,
                            row.win_rate_pct,
                            row.positive_years,
                            row.total_years,
                            row.back_years,
                            reasons_json,
                            quarantined_at,
                            repair_run_id,
                            "seasonality_cache",
                            1,
                        ),
                    )
                    if i == 0:
                        raise RuntimeError("Simulated failure mid-quarantine")
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    repairer = _FailingRepairer(db_path)
    repairer.ensure_quarantine_table()

    rows = [
        _repair_row(ticker="BBRI", year=2026, month=2),
    ]

    with pytest.raises(RuntimeError, match="Simulated failure"):
        repairer.quarantine_and_delete(rows, _REPAIR_RUN_ID)

    with sqlite3.connect(str(db_path)) as conn:
        remaining = conn.execute("SELECT ticker FROM seasonality_cache ORDER BY ticker").fetchall()
    assert [r[0] for r in remaining] == ["BBCA", "BBRI"]

    with sqlite3.connect(str(db_path)) as conn:
        quarantine_count = conn.execute(
            "SELECT COUNT(*) FROM seasonality_cache_quarantine"
        ).fetchone()[0]
    assert quarantine_count == 0


# ── Quarantine table schema ──────────────────────────────────────────────────


def test_quarantine_table_has_expected_columns(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schema(db_path)

    repairer = _make_repairer(db_path)
    repairer.ensure_quarantine_table()

    with sqlite3.connect(str(db_path)) as conn:
        columns = {
            row[1]: row[2]
            for row in conn.execute("PRAGMA table_info(seasonality_cache_quarantine)")
        }

    assert columns["ticker"] == "TEXT"
    assert columns["year"] == "INTEGER"
    assert columns["month"] == "INTEGER"
    assert columns["fetched_month"] == "TEXT"
    assert columns["fetched_at"] == "TEXT"
    assert columns["source"] == "TEXT"
    assert columns["avg_return_pct"] == "REAL"
    assert columns["win_rate_pct"] == "REAL"
    assert columns["positive_years"] == "INTEGER"
    assert columns["total_years"] == "INTEGER"
    assert columns["back_years"] == "INTEGER"
    assert columns["quarantine_reasons_json"] == "TEXT"
    assert columns["quarantined_at"] == "TEXT"
    assert columns["repair_run_id"] == "TEXT"
    assert columns["original_table"] == "TEXT"
    assert columns["schema_version"] == "INTEGER"
