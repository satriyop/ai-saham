"""Cohort-scoped persistence for market_context_snapshots."""

from __future__ import annotations

import sqlite3
from datetime import date

from src.domain.value_objects.market_context import MarketContext, MarketRegime
from src.infrastructure.persistence.sqlite_market_context_repository import (
    SQLiteMarketContextRepository,
)


def _make_context(**kwargs) -> MarketContext:
    defaults = dict(
        regime=MarketRegime.RISK_ON,
        conviction=0.75,
        factors=(),
        signal_multiplier=1.0,
        gate_tightening=False,
        as_of_date=date(2024, 1, 15),
    )
    defaults.update(kwargs)
    return MarketContext(**defaults)


def test_two_cohorts_same_date_both_survive(tmp_path):
    repo = SQLiteMarketContextRepository(tmp_path / "test.db")
    d = date(2024, 1, 15)
    repo.save(
        _make_context(as_of_date=d, conviction=0.7),
        semantic_compatibility_id="cohort-a",
    )
    repo.save(
        _make_context(as_of_date=d, conviction=0.3, regime=MarketRegime.RISK_OFF),
        semantic_compatibility_id="cohort-b",
    )

    a = repo.get(d, semantic_compatibility_id="cohort-a")
    b = repo.get(d, semantic_compatibility_id="cohort-b")
    assert a is not None and a.conviction == 0.7
    assert b is not None and b.conviction == 0.3
    assert b.regime == MarketRegime.RISK_OFF


def test_get_without_cohort_ambiguous_when_two_rows(tmp_path):
    repo = SQLiteMarketContextRepository(tmp_path / "test.db")
    d = date(2024, 1, 15)
    repo.save(_make_context(as_of_date=d), semantic_compatibility_id="cohort-a")
    repo.save(_make_context(as_of_date=d), semantic_compatibility_id="cohort-b")
    assert repo.get(d) is None


def test_get_recent_filters_by_cohort(tmp_path):
    repo = SQLiteMarketContextRepository(tmp_path / "test.db")
    repo.save(
        _make_context(as_of_date=date(2024, 1, 1)),
        semantic_compatibility_id="cohort-a",
    )
    repo.save(
        _make_context(as_of_date=date(2024, 1, 2)),
        semantic_compatibility_id="cohort-b",
    )
    repo.save(
        _make_context(as_of_date=date(2024, 1, 3)),
        semantic_compatibility_id="cohort-a",
    )

    recent = repo.get_recent(10, semantic_compatibility_id="cohort-a")
    assert len(recent) == 2
    assert all(r.as_of_date in {date(2024, 1, 1), date(2024, 1, 3)} for r in recent)


def test_cohort_metadata_persisted_on_save(tmp_path):
    repo = SQLiteMarketContextRepository(tmp_path / "test.db")
    d = date(2024, 1, 15)
    repo.save(
        _make_context(as_of_date=d),
        semantic_compatibility_id="sha256:abc",
        observation_contract="market-context-regime",
        universe_name="lq45",
        benchmark_ticker="IHSG",
    )

    with sqlite3.connect(tmp_path / "test.db") as conn:
        row = conn.execute(
            """
            SELECT semantic_compatibility_id, observation_contract,
                   universe_name, benchmark_ticker
            FROM market_context_snapshots
            WHERE as_of_date = ? AND semantic_compatibility_id = ?
            """,
            (d.isoformat(), "sha256:abc"),
        ).fetchone()
    assert row == ("sha256:abc", "market-context-regime", "lq45", "IHSG")


def test_legacy_schema_migrates_with_empty_cohort(tmp_path):
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE market_context_snapshots (
                as_of_date TEXT NOT NULL PRIMARY KEY,
                regime TEXT NOT NULL,
                conviction REAL NOT NULL,
                signal_multiplier REAL NOT NULL,
                gate_tightening INTEGER NOT NULL,
                factors_json TEXT NOT NULL,
                staleness_warning TEXT,
                coverage_warning TEXT,
                created_at TEXT NOT NULL,
                regime_confidence REAL,
                regime_stability TEXT,
                days_in_regime INTEGER,
                transition_warning TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO market_context_snapshots VALUES
            ('2024-01-01', 'RISK_ON', 0.7, 1.0, 0, '[]', NULL, NULL,
             '2024-01-01T00:00:00', NULL, NULL, NULL, NULL)
            """
        )
        conn.commit()

    repo = SQLiteMarketContextRepository(db_path)
    loaded = repo.get(date(2024, 1, 1))
    assert loaded is not None
    assert loaded.regime == MarketRegime.RISK_ON

    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(market_context_snapshots)")}
    assert "semantic_compatibility_id" in columns
