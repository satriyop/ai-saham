from __future__ import annotations

from datetime import date, datetime

from src.domain.value_objects.company_profile import CompanyProfile
from src.infrastructure.browser.stockbit_company_profile import (
    StockbitCompanyProfileProvider,
)


def test_company_profile_live_returns_latest_cached_snapshot(tmp_path):
    provider = StockbitCompanyProfileProvider(api_client=None, db_path=tmp_path / "data.db")
    provider._write_cache(_profile("BBCA", "Papan Utama", datetime.now().replace(hour=9)))
    provider._write_cache(
        _profile("BBCA", "Papan Pemantauan Khusus", datetime.now().replace(hour=10))
    )

    result = provider.get_profile("BBCA")

    assert result is not None
    assert result.listing_board == "Papan Pemantauan Khusus"


def test_company_profile_returns_latest_snapshot_on_or_before_as_of_date(tmp_path):
    provider = StockbitCompanyProfileProvider(api_client=None, db_path=tmp_path / "data.db")
    provider._write_cache(_profile("BBCA", "Papan Utama", datetime(2026, 6, 1, 9)))
    provider._write_cache(_profile("BBCA", "Papan Pemantauan Khusus", datetime(2026, 6, 5, 9)))
    provider._write_cache(_profile("BBCA", "Papan Utama", datetime(2026, 6, 10, 9)))

    result = provider.get_profile("BBCA", as_of_date=date(2026, 6, 6))

    assert result is not None
    assert result.listing_board == "Papan Pemantauan Khusus"
    assert result.fetched_at == datetime(2026, 6, 5, 9)


def test_company_profile_ignores_future_snapshot_for_as_of_date(tmp_path):
    provider = StockbitCompanyProfileProvider(api_client=None, db_path=tmp_path / "data.db")
    provider._write_cache(_profile("BBCA", "Papan Utama", datetime(2026, 6, 10, 9)))

    result = provider.get_profile("BBCA", as_of_date=date(2026, 6, 6))

    assert result is None


def _profile(
    ticker: str,
    listing_board: str,
    fetched_at: datetime,
) -> CompanyProfile:
    return CompanyProfile(
        ticker=ticker,
        background=None,
        listing_board=listing_board,
        ipo_date="31 May 2000",
        ipo_price=1400,
        ipo_amount="927 B",
        website=None,
        email=None,
        office_address=None,
        fetched_at=fetched_at,
    )
