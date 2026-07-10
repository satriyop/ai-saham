"""BCI/broker-flow behavior tests for foreign accumulation screening."""

from datetime import date, timedelta
from decimal import Decimal

from src.application.dto.accumulation_screen import (
    TIER1_FOREIGN_BROKERS,
    AccumulationScreenRequest,
)
from src.application.use_case.accumulation_screen_use_case import (
    BCI_CLUSTER,
    BCI_RETAIL,
    BCI_STABLE,
)
from tests.application.use_case.accumulation_screen_fixtures import (
    _daily_flow,
    _make_use_case,
    _summary,
    _weekdays,
)


def test_bci_cluster_when_three_or_more_tier1_codes_are_net_buyers():
    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]
    # AK, BK, ZP are all Tier 1 → should produce CLUSTER
    daily_flows = [
        _daily_flow("BBCA", session_dates[0], "AK", 100),
        _daily_flow("BBCA", session_dates[0], "BK", 80),
        _daily_flow("BBCA", session_dates[0], "ZP", 60),
        _daily_flow("BBCA", session_dates[1], "AK", 50),
    ]
    use_case, _ = _make_use_case(summaries, daily_flows)

    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"], window_days=7, min_net_buy_days=1, as_of_date=as_of
        )
    )
    c = response.candidates[0]

    assert c.bci_label == BCI_CLUSTER
    assert c.bci_tier1_count == 3
    assert c.foreign_flow_score_breakdown.breakdown_dict["inst"] == 12.5


def test_bci_stable_when_one_or_two_tier1_codes_are_net_buyers():
    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]
    # Only AK (Tier 1) + YP (domestic, not Tier 1)
    daily_flows = [
        _daily_flow("BBCA", session_dates[0], "AK", 100),
        _daily_flow("BBCA", session_dates[0], "YP", 200),  # YP is domestic, not Tier 1
    ]
    use_case, _ = _make_use_case(summaries, daily_flows)

    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"], window_days=7, min_net_buy_days=1, as_of_date=as_of
        )
    )
    c = response.candidates[0]

    assert c.bci_label == BCI_STABLE
    assert c.bci_tier1_count == 1
    assert c.foreign_flow_score_breakdown.breakdown_dict["inst"] == 4.2


def test_bci_retail_when_no_tier1_codes_are_net_buyers():
    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]
    # YP (domestic) only — no Tier 1 codes
    daily_flows = [
        _daily_flow("BBCA", session_dates[0], "YP", 300),
    ]
    use_case, _ = _make_use_case(summaries, daily_flows)

    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"], window_days=7, min_net_buy_days=1, as_of_date=as_of
        )
    )
    c = response.candidates[0]

    assert c.bci_label == BCI_RETAIL
    assert c.bci_tier1_count == 0
    assert c.foreign_flow_score_breakdown.breakdown_dict["inst"] == 0.0


def test_bci_none_when_no_daily_flow_data():
    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]
    use_case, _ = _make_use_case(summaries, daily_flows=None)

    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"], window_days=7, min_net_buy_days=1, as_of_date=as_of
        )
    )
    c = response.candidates[0]

    assert c.bci_label is None
    assert c.bci_tier1_count == 0
    assert c.foreign_flow_score_breakdown.breakdown_dict["inst"] == 0.0


def test_bci_counts_all_net_buyers_not_just_top5():
    """A Tier 1 code ranked 6th overall still counts toward BCI tier."""
    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]
    # 5 domestic/non-Tier1 codes with big lots + AK (Tier 1) in 6th place
    daily_flows = [
        _daily_flow("BBCA", session_dates[0], "YP", 1000),
        _daily_flow("BBCA", session_dates[0], "PD", 900),
        _daily_flow("BBCA", session_dates[0], "XL", 800),
        _daily_flow("BBCA", session_dates[0], "XC", 700),
        _daily_flow("BBCA", session_dates[0], "DR", 600),  # DR is Tier 1
        _daily_flow("BBCA", session_dates[0], "AK", 50),  # AK Tier 1, rank 6
    ]
    use_case, _ = _make_use_case(summaries, daily_flows)

    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"], window_days=7, min_net_buy_days=1, as_of_date=as_of
        )
    )
    c = response.candidates[0]

    # Both AK and DR are Tier 1 — STABLE (2 codes)
    assert c.bci_label == BCI_STABLE
    assert c.bci_tier1_count == 2


def test_tier1_codes_default_to_module_constant():
    req = AccumulationScreenRequest(tickers=["BBCA"])
    assert req.tier1_broker_codes == TIER1_FOREIGN_BROKERS


def test_tier1_codes_override_changes_bci():
    """Passing a custom tier1 set changes which brokers count for BCI."""
    as_of = date(2026, 6, 1)
    session_dates = [as_of - timedelta(days=i) for i in range(3)]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]
    # Only YP is a net buyer — YP is NOT in default TIER1_FOREIGN_BROKERS
    daily_flows = [_daily_flow("BBCA", session_dates[0], "YP", 500)]
    use_case, _ = _make_use_case(summaries, daily_flows)

    # Default tier1: YP not included → BCI RETAIL
    resp_default = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"], window_days=7, min_net_buy_days=1, as_of_date=as_of
        )
    )
    assert resp_default.candidates[0].bci_label == BCI_RETAIL

    # Custom tier1 including YP → BCI STABLE
    resp_custom = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
            tier1_broker_codes=frozenset({"YP"}),
        )
    )
    assert resp_custom.candidates[0].bci_label == BCI_STABLE
