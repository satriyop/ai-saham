from datetime import date

from src.domain.value_objects.bandar_detector_snapshot import BandarDetectorSnapshot


def _snapshot(broker_accdist: str) -> BandarDetectorSnapshot:
    return BandarDetectorSnapshot(
        ticker="ASII",
        session_date=date(2026, 6, 27),
        broker_accdist=broker_accdist,
        today_accdist="Big Dist",
        five_day_accdist="Big Dist",
        top1_accdist="Big Dist",
        top1_percent=-36.0,
        today_percent=-37.0,
        total_buyer=47,
        total_seller=10,
    )


def test_bandar_detector_treats_dist_and_dis_as_distribution():
    assert _snapshot("Dist").is_distributing is True
    assert _snapshot("Dis").is_distributing is True


def test_bandar_detector_acc_and_neutral_are_not_distribution():
    assert _snapshot("Acc").is_distributing is False
    assert _snapshot("Neutral").is_distributing is False
