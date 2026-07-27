"""Tests for swing_broker_detail_builder.py orchestrator."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from src.application.services.swing_broker_detail_builder import (
    build_broker_detail,
    build_broker_detail_from_daily_flows,
)

_SMART = {"AK", "BK", "KZ"}
_NOISE = {"YP", "XL"}
_WEIGHTS = {
    "AK": Decimal("1.5"),
    "BK": Decimal("1.5"),
    "KZ": Decimal("1.5"),
    "YP": Decimal("0.5"),
    "XL": Decimal("0.5"),
}
_THRESHOLD = 60.0


def _flow(broker_code, broker_name, net_value, day=1):
    f = MagicMock()
    f.broker_code = broker_code
    f.broker_name = broker_name
    f.net_value = Decimal(str(net_value))
    f.date = date(2026, 6, day)
    return f


def test_daily_flow_path_uses_daily_flows():
    """build_broker_detail calls get_broker_daily_flows first when method exists."""
    flows = [
        _flow("AK", "UBS", 8000000, 1),
        _flow("YP", "CGS-CIMB", -2000000, 1),
    ]
    repo = MagicMock()
    repo.get_broker_daily_flows.return_value = flows

    detail = build_broker_detail(
        "BBCA",
        repo,
        window_sessions=5,
        as_of_date=date(2026, 6, 1),
        smart_money_brokers=_SMART,
        noise_brokers=_NOISE,
        broker_weights=_WEIGHTS,
        smart_share_threshold_pct=_THRESHOLD,
    )
    assert detail is not None
    assert detail.source == "stockbit"
    assert detail.detail_sessions == 1
    assert detail.through_date == date(2026, 6, 1)
    repo.get_broker_daily_flows.assert_called_once()


def test_daily_flow_preserves_source_and_broker_type():
    flows = [
        _flow("AK", "UBS", 5000000, 1),
        _flow("YP", "CGS-CIMB", -3000000, 1),
    ]
    detail = build_broker_detail_from_daily_flows(
        "BBCA",
        flows,
        window_sessions=5,
        as_of_date=date(2026, 6, 1),
        smart_money_brokers=_SMART,
        noise_brokers=_NOISE,
        broker_weights=_WEIGHTS,
        smart_share_threshold_pct=_THRESHOLD,
    )
    assert detail is not None
    assert detail.source == "stockbit"
    for buyer in detail.top_buyers:
        assert buyer.broker_type == "unknown"
    for seller in detail.top_sellers:
        assert seller.broker_type == "unknown"


def test_summary_fallback_preserves_latest_source_and_broker_type():
    """When no get_broker_daily_flows, summary fallback preserves tx.broker_type and source."""

    class _FakeTx:
        def __init__(self, code, name, broker_type, net_value):
            self.broker_code = code
            self.broker_name = name
            self.broker_type = broker_type
            self.net_value = Decimal(str(net_value))

    class _FakeSummary:
        def __init__(self, day, source, top_buyers, top_sellers, foreign_net):
            self.date = day
            self.source = source
            self.top_buyers = top_buyers
            self.top_sellers = top_sellers
            self.foreign_net_value = Decimal(str(foreign_net))

    class _FakeRepo:
        def get_broker_summaries(self, ticker, end_date=None):
            return [
                _FakeSummary(
                    date(2026, 6, 1),
                    "idx",
                    top_buyers=(_FakeTx("AK", "UBS", MagicMock(value="FOREIGN"), 5000000),),
                    top_sellers=(),
                    foreign_net=5000000,
                ),
            ]

    repo = _FakeRepo()
    detail = build_broker_detail(
        "BBCA",
        repo,
        window_sessions=5,
        as_of_date=date(2026, 6, 1),
        smart_money_brokers=_SMART,
        noise_brokers=_NOISE,
        broker_weights=_WEIGHTS,
        smart_share_threshold_pct=_THRESHOLD,
    )
    assert detail is not None
    assert detail.source == "idx"
    assert detail.top_buyers[0].broker_type == "FOREIGN"


def test_daily_flow_quality_labels():
    # no buyers
    flows = [
        _flow("AK", "UBS", -5000000, 1),
    ]
    detail = build_broker_detail_from_daily_flows(
        "BBCA",
        flows,
        window_sessions=5,
        as_of_date=None,
        smart_money_brokers=_SMART,
        noise_brokers=_NOISE,
        broker_weights=_WEIGHTS,
        smart_share_threshold_pct=_THRESHOLD,
    )
    assert detail is not None
    assert detail.quality == "no buyer detail"

    # concentrated accumulation
    flows = [
        _flow("AK", "UBS", 8000000, 1),
        _flow("HD", "Mandiri", 2000000, 1),
    ]
    detail = build_broker_detail_from_daily_flows(
        "BBCA",
        flows,
        window_sessions=5,
        as_of_date=None,
        smart_money_brokers=_SMART,
        noise_brokers=_NOISE,
        broker_weights=_WEIGHTS,
        smart_share_threshold_pct=_THRESHOLD,
    )
    assert detail is not None
    assert detail.quality == "concentrated accumulation"

    # broad accumulation (need 3+ distinct dates and 3+ buyers)
    flows = [
        _flow("AK", "UBS", 5000000, 1),
        _flow("BK", "DB", 4000000, 1),
        _flow("YP", "CGS-CIMB", 3000000, 1),
        _flow("AK", "UBS", 2000000, 2),
        _flow("BK", "DB", 1000000, 2),
        _flow("YP", "CGS-CIMB", 1000000, 2),
        _flow("HD", "Mandiri", 500000, 3),
    ]
    detail = build_broker_detail_from_daily_flows(
        "BBCA",
        flows,
        window_sessions=5,
        as_of_date=None,
        smart_money_brokers=_SMART,
        noise_brokers=_NOISE,
        broker_weights=_WEIGHTS,
        smart_share_threshold_pct=_THRESHOLD,
    )
    assert detail is not None
    assert detail.quality == "broad accumulation"

    # recent distribution (smart_flow < 0, top buyer share < 60% so no concentrated accumulation)
    flows = [
        _flow("AK", "UBS", -5000000, 1),
        _flow("HD", "Mandiri", 2000000, 1),
        _flow("YP", "CGS-CIMB", 2000000, 1),
    ]
    detail = build_broker_detail_from_daily_flows(
        "BBCA",
        flows,
        window_sessions=5,
        as_of_date=None,
        smart_money_brokers=_SMART,
        noise_brokers=_NOISE,
        broker_weights=_WEIGHTS,
        smart_share_threshold_pct=_THRESHOLD,
    )
    assert detail is not None
    assert detail.quality == "recent distribution"

    # limited accumulation detail (fallback: buyers exist, top share < 60, < 3 dates)
    flows = [
        _flow("AK", "UBS", 5000000, 1),
        _flow("YP", "CGS-CIMB", 4000000, 1),
    ]
    detail = build_broker_detail_from_daily_flows(
        "BBCA",
        flows,
        window_sessions=5,
        as_of_date=None,
        smart_money_brokers=_SMART,
        noise_brokers=_NOISE,
        broker_weights=_WEIGHTS,
        smart_share_threshold_pct=_THRESHOLD,
    )
    assert detail is not None
    assert detail.quality == "limited accumulation detail"


def test_summary_fallback_quality_labels():
    """Test summary fallback quality label logic via build_broker_detail."""

    class _FakeTx:
        def __init__(self, code, name, net_value):
            self.broker_code = code
            self.broker_name = name
            self.broker_type = MagicMock(value="FOREIGN")
            self.net_value = Decimal(str(net_value))

    class _FakeSummary:
        def __init__(self, day, top_buyers, top_sellers, foreign_net):
            self.date = day
            self.top_buyers = top_buyers
            self.top_sellers = top_sellers
            self.foreign_net_value = Decimal(str(foreign_net))
            self.source = "stockbit"

    class _FakeRepo:
        def __init__(self, summaries):
            self._summaries = summaries

        def get_broker_summaries(self, ticker, end_date=None):
            return self._summaries

    # recent distribution (latest foreign net < 0)
    repo = _FakeRepo(
        [
            _FakeSummary(
                date(2026, 6, 1),
                top_buyers=(_FakeTx("AK", "UBS", 5000000),),
                top_sellers=(),
                foreign_net=-2000000,
            ),
        ]
    )
    detail = build_broker_detail(
        "BBCA",
        repo,
        window_sessions=5,
        as_of_date=date(2026, 6, 1),
        smart_money_brokers=_SMART,
        noise_brokers=_NOISE,
        broker_weights=_WEIGHTS,
        smart_share_threshold_pct=_THRESHOLD,
    )
    assert detail is not None
    assert detail.quality == "recent distribution"

    # no buyers -> no buyer detail
    repo = _FakeRepo(
        [
            _FakeSummary(
                date(2026, 6, 1),
                top_buyers=(),
                top_sellers=(_FakeTx("AK", "UBS", -5000000),),
                foreign_net=2000000,
            ),
        ]
    )
    detail = build_broker_detail(
        "BBCA",
        repo,
        window_sessions=5,
        as_of_date=date(2026, 6, 1),
        smart_money_brokers=_SMART,
        noise_brokers=_NOISE,
        broker_weights=_WEIGHTS,
        smart_share_threshold_pct=_THRESHOLD,
    )
    assert detail is not None
    assert detail.quality == "no buyer detail"


def test_build_broker_detail_returns_none_when_no_data():
    """build_broker_detail returns None when no daily flows and no detail summaries."""

    class _FakeRepo:
        def get_broker_daily_flows(self, ticker, end_date=None):
            return []

        def get_broker_summaries(self, ticker, end_date=None):
            return []

    detail = build_broker_detail(
        "BBCA",
        _FakeRepo(),
        window_sessions=5,
        as_of_date=date(2026, 6, 1),
        smart_money_brokers=_SMART,
        noise_brokers=_NOISE,
        broker_weights=_WEIGHTS,
        smart_share_threshold_pct=_THRESHOLD,
    )
    assert detail is None
