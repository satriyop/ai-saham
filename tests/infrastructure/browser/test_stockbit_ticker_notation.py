from datetime import date, datetime

from src.domain.value_objects.ticker_notation import TickerNotationSnapshot
from src.infrastructure.browser.stockbit_ticker_notation import (
    StockbitTickerNotationProvider,
    _parse_snapshot,
)


def test_parse_emitten_info_notation_and_status():
    snapshot = _parse_snapshot(
        "GOTO",
        {
            "data": {
                "status": "STATUS_ACTIVE",
                "tradeable": True,
                "sector": "Teknologi",
                "sub_sector": "Perangkat Lunak & Jasa TI",
                "market_hour": {"status": "open", "suspend_info": ""},
                "trading_limit_info": {"haircut_percentage": "100%"},
                "notation": [
                    {
                        "notation_code": "N",
                        "notation_desc": "Multiple voting shares",
                    }
                ],
                "catalogs": [
                    {
                        "catalog_name": "Papan Pengembangan",
                        "company_type": "listing-board",
                        "show": True,
                    },
                    {
                        "catalog_name": "NOTASI-KHUSUS",
                        "company_type": "indeks",
                        "show": True,
                    },
                ],
            }
        },
    )

    assert snapshot is not None
    assert snapshot.ticker == "GOTO"
    assert snapshot.status == "STATUS_ACTIVE"
    assert snapshot.tradeable is True
    assert snapshot.listing_board == "Papan Pengembangan"
    assert snapshot.haircut_percentage == "100%"
    assert snapshot.codes == ["N"]
    assert snapshot.has_warning is True


def test_sqlite_cache_round_trip(tmp_path):
    provider = StockbitTickerNotationProvider(
        api_client=None,
        db_path=tmp_path / "data.db",
    )
    snapshot = _parse_snapshot(
        "MTFN",
        {
            "data": {
                "status": "STATUS_ACTIVE",
                "tradeable": True,
                "market_hour": {"status": "open", "suspend_info": ""},
                "trading_limit_info": {"haircut_percentage": "100%"},
                "notation": [
                    {"notation_code": "E", "notation_desc": "Negative equity"},
                    {"notation_code": "L", "notation_desc": "Late financial report"},
                    {"notation_code": "X", "notation_desc": "Special monitoring"},
                ],
                "catalogs": [
                    {
                        "catalog_name": "Papan Pemantauan Khusus",
                        "company_type": "listing-board",
                        "show": True,
                    }
                ],
            }
        },
    )

    assert snapshot is not None
    provider.save_notation(snapshot)

    cached = provider.get_notation("MTFN")
    assert cached is not None
    assert cached.fetched_at is not None
    assert isinstance(cached.fetched_at, datetime)
    assert cached.fetched_at.date() == date.today()
    assert cached.codes == ["E", "L", "X"]
    assert cached.listing_board == "Papan Pemantauan Khusus"
    assert cached.haircut_percentage == "100%"
    assert provider.is_cache_fresh("MTFN") is True


def test_get_notation_returns_latest_snapshot_on_or_before_as_of_date(tmp_path):
    provider = StockbitTickerNotationProvider(
        api_client=None,
        db_path=tmp_path / "data.db",
    )
    provider.save_notation(_snapshot("MTFN", "STATUS_ACTIVE", datetime(2026, 6, 1, 9)))
    provider.save_notation(_snapshot("MTFN", "STATUS_SUSPENDED", datetime(2026, 6, 5, 9)))
    provider.save_notation(_snapshot("MTFN", "STATUS_ACTIVE", datetime(2026, 6, 10, 9)))

    cached = provider.get_notation("MTFN", as_of_date=date(2026, 6, 6))

    assert cached is not None
    assert cached.status == "STATUS_SUSPENDED"
    assert cached.fetched_at == datetime(2026, 6, 5, 9)


def test_get_notation_ignores_future_snapshot_for_as_of_date(tmp_path):
    provider = StockbitTickerNotationProvider(
        api_client=None,
        db_path=tmp_path / "data.db",
    )
    provider.save_notation(_snapshot("MTFN", "STATUS_ACTIVE", datetime(2026, 6, 10, 9)))

    cached = provider.get_notation("MTFN", as_of_date=date(2026, 6, 6))

    assert cached is None


def test_get_notation_live_mode_returns_latest_cached_snapshot(tmp_path):
    provider = StockbitTickerNotationProvider(
        api_client=None,
        db_path=tmp_path / "data.db",
    )
    provider.save_notation(_snapshot("MTFN", "STATUS_ACTIVE", datetime(2026, 6, 1, 9)))
    provider.save_notation(_snapshot("MTFN", "STATUS_SUSPENDED", datetime(2026, 6, 5, 9)))

    cached = provider.get_notation("MTFN")

    assert cached is not None
    assert cached.status == "STATUS_SUSPENDED"


def _snapshot(
    ticker: str,
    status: str,
    fetched_at: datetime,
) -> TickerNotationSnapshot:
    return TickerNotationSnapshot(
        ticker=ticker,
        status=status,
        tradeable=True,
        market_status="open",
        haircut_percentage="100%",
        fetched_at=fetched_at,
    )
