import sqlite3

from src.infrastructure.persistence.sqlite_enrichment_pit_coverage import (
    read_enrichment_pit_coverage,
)


def test_enrichment_pit_coverage_reports_all_replay_relevant_tables(tmp_path):
    db_path = tmp_path / "pit_coverage.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE company_fundamentals (ticker TEXT, fetched_date TEXT);
            CREATE TABLE shareholding_composition (ticker TEXT, fetched_date TEXT);
            CREATE TABLE analyst_cache (ticker TEXT, fetched_date TEXT);
            CREATE TABLE ticker_notation_cache (ticker TEXT, fetched_date TEXT);
            CREATE TABLE forward_estimates_cache (ticker TEXT, fetched_date TEXT);
            CREATE TABLE stock_meta (ticker TEXT, fetched_at TEXT);
            CREATE TABLE company_profile_cache (ticker TEXT, fetched_date TEXT);
            CREATE TABLE seasonality_cache (
                ticker TEXT,
                fetched_month TEXT,
                fetched_at TEXT
            );
            CREATE TABLE earnings_cache (ticker TEXT, fetched_date TEXT);

            INSERT INTO company_fundamentals VALUES ('BBCA', '2026-07-07T10:00:00');
            INSERT INTO shareholding_composition VALUES ('BBCA', '2026-07-07T10:00:00');
            INSERT INTO analyst_cache VALUES ('BBCA', '2026-07-07T10:00:00');
            INSERT INTO ticker_notation_cache VALUES ('BBCA', '2026-07-07T10:00:00');
            INSERT INTO forward_estimates_cache VALUES ('BBCA', '2026-07-07T10:00:00');
            INSERT INTO stock_meta VALUES ('BBCA', '2026-07-07T10:00:00');
            INSERT INTO company_profile_cache VALUES ('BBCA', '2026-07-07T10:00:00');
            INSERT INTO seasonality_cache VALUES ('BBCA', '2026-07', NULL);
            INSERT INTO earnings_cache VALUES ('BBCA', '2026-07-07T10:00:00');
            """
        )

    coverage = read_enrichment_pit_coverage(db_path)
    by_table = {row.table: row for row in coverage}

    assert set(by_table) == {
        "company_fundamentals",
        "shareholding_composition",
        "analyst_cache",
        "ticker_notation_cache",
        "forward_estimates_cache",
        "stock_meta",
        "company_profile_cache",
        "seasonality_cache",
        "earnings_cache",
    }
    assert by_table["stock_meta"].latest_date == "2026-07-07"
    assert by_table["company_profile_cache"].tickers_in_latest == 1
    assert by_table["seasonality_cache"].latest_date == "2026-07-01"
    assert by_table["earnings_cache"].snapshot_count == 1
