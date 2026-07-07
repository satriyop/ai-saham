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


def _edge(ticker: str, avg: float, fetched_at: datetime):
    from src.domain.value_objects.seasonal_edge import SeasonalEdge

    return SeasonalEdge(
        ticker=ticker,
        month=7,
        avg_monthly_return_pct=avg,
        win_rate_pct=60.0,
        positive_years=3,
        total_years=5,
        back_years=5,
        source="stockbit",
        fetched_at=fetched_at,
    )
