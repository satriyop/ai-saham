import sqlite3

from src.infrastructure.persistence.sqlite_signal_coverage_provider import (
    SqliteSignalCoverageProvider,
)


def test_signal_coverage_includes_pit_replay_tables_and_excludes_display_valuation(
    tmp_path,
):
    db_path = tmp_path / "coverage.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE candles (ticker TEXT);
            INSERT INTO candles (ticker) VALUES ('BBCA');

            CREATE TABLE bandar_detector (ticker TEXT, broker_accdist TEXT);
            CREATE TABLE foreign_flow_points (ticker TEXT);
            CREATE TABLE insider_cache (ticker TEXT, shares INTEGER);
            CREATE TABLE seasonality_cache (ticker TEXT);
            CREATE TABLE analyst_cache (ticker TEXT, analyst_count INTEGER);
            CREATE TABLE forward_estimates_cache (ticker TEXT);
            CREATE TABLE stock_meta (ticker TEXT, sector TEXT);
            CREATE TABLE company_profile_cache (ticker TEXT, listing_board TEXT);
            CREATE TABLE earnings_cache (ticker TEXT, eps_actual REAL);

            INSERT INTO stock_meta (ticker, sector) VALUES ('BBCA', 'Financials');
            INSERT INTO company_profile_cache (ticker, listing_board) VALUES ('BBCA', 'MAIN');
            INSERT INTO earnings_cache (ticker, eps_actual) VALUES ('BBCA', 42.0);
            """
        )

    report = SqliteSignalCoverageProvider().compute(db_path)
    by_factor = {factor.factor: factor for factor in report.factors}

    assert by_factor["sector_metadata"].usable_rows == 1
    assert by_factor["company_profile"].usable_rows == 1
    assert by_factor["earnings_history"].usable_rows == 1
    assert "valuation_metrics" not in by_factor
