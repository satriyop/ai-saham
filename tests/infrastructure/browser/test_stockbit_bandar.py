from datetime import date

from src.domain.value_objects.bandar_detector_snapshot import BandarDetectorSnapshot
from src.infrastructure.browser.stockbit_bandar import StockbitBandarDetectorProvider


def test_bandar_cache_uses_latest_snapshot_on_or_before_target_date(tmp_path):
    provider = StockbitBandarDetectorProvider(
        api_client=None,
        db_path=tmp_path / "stockbit.db",
    )
    provider._write_cache(
        BandarDetectorSnapshot(
            ticker="ASII",
            session_date=date(2026, 6, 26),
            broker_accdist="Dist",
            today_accdist="Big Dist",
            five_day_accdist="Big Dist",
            top1_accdist="Big Dist",
            top1_percent=-36.0,
            today_percent=-37.0,
            total_buyer=47,
            total_seller=10,
        )
    )

    snapshot = provider.get_snapshot("ASII", session_date=date(2026, 6, 28))

    assert snapshot is not None
    assert snapshot.session_date == date(2026, 6, 26)
    assert snapshot.is_distributing is True
    assert snapshot.five_day_accdist == "Big Dist"


def test_bandar_cache_requires_exact_date_when_previous_not_allowed(tmp_path):
    provider = StockbitBandarDetectorProvider(
        api_client=None,
        db_path=tmp_path / "stockbit.db",
    )
    provider._write_cache(
        BandarDetectorSnapshot(
            ticker="ASII",
            session_date=date(2026, 6, 26),
            broker_accdist="Dist",
            today_accdist="Big Dist",
            five_day_accdist="Big Dist",
            top1_accdist="Big Dist",
            top1_percent=-36.0,
            today_percent=-37.0,
            total_buyer=47,
            total_seller=10,
        )
    )

    assert provider._read_cache("ASII", date(2026, 6, 28), allow_previous=False) is None
