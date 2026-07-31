from datetime import date, datetime

from src.infrastructure.browser.stockbit_seasonality import (
    StockbitSeasonalityProvider,
    _parse_seasonality,
)


def _section(month: str, value: str) -> dict:
    return {"columns": [{"name": month, "value": value}]}


def _body(**sections: dict) -> dict:
    data = {
        "avg": _section("Jul", "1.23"),
        "prob": _section("Jul", "60"),
        "up": _section("Jul", "3"),
        "total_months": _section("Jul", "5"),
        "default_last_year": 5,
    }
    data.update(sections)
    return {"data": data}


def test_parse_seasonality_returns_edge_for_complete_stockbit_payload():
    edge = _parse_seasonality("bbca", month=7, back_years=5, body=_body())

    assert edge is not None
    assert edge.ticker == "BBCA"
    assert edge.month == 7
    assert edge.avg_monthly_return_pct == 1.23
    assert edge.win_rate_pct == 60.0
    assert edge.positive_years == 3
    assert edge.total_years == 5
    assert edge.back_years == 5


def test_parse_seasonality_returns_none_when_win_rate_is_missing():
    edge = _parse_seasonality(
        "BBCA",
        month=7,
        back_years=5,
        body=_body(prob={"columns": []}),
    )

    assert edge is None


def test_parse_seasonality_returns_none_when_win_rate_is_unparseable():
    edge = _parse_seasonality(
        "BBCA",
        month=7,
        back_years=5,
        body=_body(prob=_section("Jul", "-")),
    )

    assert edge is None


def _insert_row(
    provider: StockbitSeasonalityProvider,
    *,
    ticker: str = "BBCA",
    year: int = 2026,
    month: int = 7,
    avg_return_pct: float | None = 1.23,
    win_rate_pct: float | None = 60.0,
    positive_years: int | None = 3,
    total_years: int | None = 5,
    back_years: int | None = 5,
    source: str | None = "stockbit",
    fetched_month: str = "2026-07",
    fetched_at: str | None = datetime(2026, 7, 1).isoformat(),
) -> None:
    with provider._get_conn() as conn:
        conn.execute(
            """
            INSERT INTO seasonality_cache
                (ticker, year, month, avg_return_pct, win_rate_pct,
                 positive_years, total_years, back_years, source, fetched_month, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticker,
                year,
                month,
                avg_return_pct,
                win_rate_pct,
                positive_years,
                total_years,
                back_years,
                source,
                fetched_month,
                fetched_at,
            ),
        )


def test_read_cache_returns_edge_for_valid_row(tmp_path):
    provider = StockbitSeasonalityProvider(api_client=None, db_path=tmp_path / "data.db")
    _insert_row(provider)

    edge = provider._read_cache("BBCA", 2026, 7)

    assert edge is not None
    assert edge.avg_monthly_return_pct == 1.23
    assert edge.source == "stockbit"
    assert edge.fetched_at == datetime(2026, 7, 1)


def test_read_cache_returns_none_for_null_source(tmp_path):
    provider = StockbitSeasonalityProvider(api_client=None, db_path=tmp_path / "data.db")
    _insert_row(provider, source=None)

    assert provider._read_cache("BBCA", 2026, 7) is None


def test_read_cache_returns_none_for_empty_source(tmp_path):
    provider = StockbitSeasonalityProvider(api_client=None, db_path=tmp_path / "data.db")
    _insert_row(provider, source="")

    assert provider._read_cache("BBCA", 2026, 7) is None


def test_read_cache_returns_none_for_unknown_source_case_insensitive(tmp_path):
    provider = StockbitSeasonalityProvider(api_client=None, db_path=tmp_path / "data.db")
    _insert_row(provider, source="Unknown")

    assert provider._read_cache("BBCA", 2026, 7) is None


def test_read_cache_returns_none_for_null_fetched_at(tmp_path):
    provider = StockbitSeasonalityProvider(api_client=None, db_path=tmp_path / "data.db")
    _insert_row(provider, fetched_at=None)

    assert provider._read_cache("BBCA", 2026, 7) is None


def test_read_cache_returns_none_for_malformed_fetched_at(tmp_path):
    provider = StockbitSeasonalityProvider(api_client=None, db_path=tmp_path / "data.db")
    _insert_row(provider, fetched_at="not-a-date")

    assert provider._read_cache("BBCA", 2026, 7) is None


def test_read_cache_returns_none_for_null_required_metric(tmp_path):
    provider = StockbitSeasonalityProvider(api_client=None, db_path=tmp_path / "data.db")
    _insert_row(provider, positive_years=None)

    assert provider._read_cache("BBCA", 2026, 7) is None


def test_read_cache_does_not_fall_back_to_older_valid_row_when_newest_is_invalid(tmp_path):
    """If the newest PIT-eligible row has invalid provenance, the read must
    fail closed (None) rather than silently returning an older valid row —
    a bad latest snapshot must not be hidden by falling back."""
    provider = StockbitSeasonalityProvider(api_client=None, db_path=tmp_path / "data.db")
    _insert_row(
        provider,
        avg_return_pct=1.0,
        source="stockbit",
        fetched_month="2026-06",
        fetched_at=datetime(2026, 6, 1).isoformat(),
    )
    _insert_row(
        provider,
        avg_return_pct=2.0,
        source="unknown",
        fetched_month="2026-07",
        fetched_at=datetime(2026, 7, 1).isoformat(),
    )

    assert provider._read_cache("BBCA", 2026, 7) is None


def test_read_cache_returns_none_for_incomplete_cached_seasonality(tmp_path):
    provider = StockbitSeasonalityProvider(api_client=None, db_path=tmp_path / "data.db")

    with provider._get_conn() as conn:
        conn.execute(
            """
            INSERT INTO seasonality_cache
                (ticker, year, month, avg_return_pct, win_rate_pct,
                 positive_years, total_years, back_years, source, fetched_month, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "BBCA",
                2026,
                7,
                -2.0,
                None,
                None,
                None,
                None,
                "stockbit",
                "2026-07",
                datetime(2026, 7, 1).isoformat(),
            ),
        )

    assert provider._read_cache("BBCA", 2026, 7) is None


def test_get_seasonal_edge_returns_latest_cached_snapshot_on_or_before_as_of_date(tmp_path):
    provider = StockbitSeasonalityProvider(api_client=None, db_path=tmp_path / "data.db")
    provider._write_cache(
        "BBCA",
        2026,
        7,
        _edge("BBCA", avg=1.0, fetched_at=datetime(2026, 6, 1, 9)),
    )
    provider._write_cache(
        "BBCA",
        2026,
        7,
        _edge("BBCA", avg=2.0, fetched_at=datetime(2026, 6, 5, 9)),
    )
    provider._write_cache(
        "BBCA",
        2026,
        7,
        _edge("BBCA", avg=3.0, fetched_at=datetime(2026, 6, 10, 9)),
    )

    edge = provider.get_seasonal_edge("BBCA", 2026, 7, as_of_date=date(2026, 6, 6))

    assert edge is not None
    assert edge.avg_monthly_return_pct == 2.0
    assert edge.fetched_at == datetime(2026, 6, 5, 9)


def test_get_seasonal_edge_ignores_future_snapshot_for_as_of_date(tmp_path):
    provider = StockbitSeasonalityProvider(api_client=None, db_path=tmp_path / "data.db")
    provider._write_cache(
        "BBCA",
        2026,
        7,
        _edge("BBCA", avg=3.0, fetched_at=datetime(2026, 6, 10, 9)),
    )

    edge = provider.get_seasonal_edge("BBCA", 2026, 7, as_of_date=date(2026, 6, 6))

    assert edge is None


def _edge(ticker: str, avg: float, fetched_at: datetime, source: str = "stockbit"):
    from src.domain.value_objects.seasonal_edge import SeasonalEdge

    return SeasonalEdge(
        ticker=ticker,
        month=7,
        avg_monthly_return_pct=avg,
        win_rate_pct=60.0,
        positive_years=3,
        total_years=5,
        back_years=5,
        source=source,
        fetched_at=fetched_at,
    )


def _row_count(provider: StockbitSeasonalityProvider, ticker: str = "BBCA") -> int:
    with provider._get_conn() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM seasonality_cache WHERE ticker = ?", (ticker,)
        ).fetchone()[0]


# ── Provenance invariant: a no-data / source-less fetch is a persistence no-op ──
# (fix_seasonality_negative_cache_null_provenance.md). Writing null-source,
# all-null-metric rows produced chronic INVALID_SOURCE + ALL_METRICS_NULL audit
# churn; the writer must never persist a row without provenance.


def test_write_cache_persists_nothing_for_none_edge(tmp_path):
    provider = StockbitSeasonalityProvider(api_client=None, db_path=tmp_path / "data.db")

    provider._write_cache("BBCA", 2026, 7, None)

    assert _row_count(provider) == 0


def test_write_cache_persists_nothing_for_blank_source_edge(tmp_path):
    provider = StockbitSeasonalityProvider(api_client=None, db_path=tmp_path / "data.db")

    provider._write_cache(
        "BBCA", 2026, 7, _edge("BBCA", avg=1.0, fetched_at=datetime(2026, 6, 1, 9), source="  ")
    )

    assert _row_count(provider) == 0


def test_write_cache_persists_valid_edge(tmp_path):
    provider = StockbitSeasonalityProvider(api_client=None, db_path=tmp_path / "data.db")

    provider._write_cache(
        "BBCA", 2026, 7, _edge("BBCA", avg=1.0, fetched_at=datetime(2026, 6, 1, 9))
    )

    assert _row_count(provider) == 1
    edge = provider._read_cache("BBCA", 2026, 7)
    assert edge is not None
    assert edge.source == "stockbit"


def test_get_seasonal_edge_persists_nothing_on_no_data_fetch(tmp_path):
    # api_client=None makes _fetch return None (the no-data path). The old writer
    # persisted a null-source, all-null row here; the guard must leave the cache empty.
    provider = StockbitSeasonalityProvider(api_client=None, db_path=tmp_path / "data.db")

    result = provider.get_seasonal_edge("BBCA", 2026, 7)

    assert result is None
    assert _row_count(provider) == 0
