"""Tests for broker_detail_aggregation.py pure aggregation module."""

from datetime import date
from decimal import Decimal

from src.application.services.broker_detail_aggregation import (
    BrokerFlowRow,
    aggregate_broker_detail_rows,
)

_SMART = {"AK", "BK", "KZ"}
_NOISE = {"YP", "XL"}
_WEIGHTS = {"AK": Decimal("1.5"), "BK": Decimal("1.5"), "KZ": Decimal("1.5"),
            "YP": Decimal("0.5"), "XL": Decimal("0.5")}
_THRESHOLD = 60.0


def _row(code, name, signed, day=1, broker_type="FOREIGN"):
    return BrokerFlowRow(code, name, broker_type, Decimal(str(signed)), date(2026, 6, day))


def test_positive_rows_become_buyers_negative_rows_become_sellers():
    agg = aggregate_broker_detail_rows(
        [
            _row("AK", "UBS", 1000000),
            _row("YP", "CGS-CIMB", -500000),
        ],
        latest_net_flow=Decimal("500000"),
        smart_money_brokers=_SMART,
        noise_brokers=_NOISE,
        broker_weights=_WEIGHTS,
        smart_share_threshold_pct=_THRESHOLD,
    )
    assert len(agg.buyers) == 1
    assert agg.buyers[0].broker_code == "AK"
    assert agg.buyers[0].net_value == Decimal("1000000")

    assert len(agg.sellers) == 1
    assert agg.sellers[0].broker_code == "YP"
    assert agg.sellers[0].net_value == Decimal("-500000")


def test_broker_rows_aggregate_across_sessions_and_count_distinct_dates():
    agg = aggregate_broker_detail_rows(
        [
            _row("AK", "UBS", 1000000, day=1),
            _row("AK", "UBS", 2000000, day=2),
            _row("AK", "UBS", 3000000, day=3),
            _row("YP", "CGS-CIMB", -500000, day=1),
            _row("YP", "CGS-CIMB", -500000, day=1),
        ],
        latest_net_flow=Decimal("6000000"),
        smart_money_brokers=_SMART,
        noise_brokers=_NOISE,
        broker_weights=_WEIGHTS,
        smart_share_threshold_pct=_THRESHOLD,
    )
    assert len(agg.buyers) == 1
    assert agg.buyers[0].broker_code == "AK"
    assert agg.buyers[0].net_value == Decimal("6000000")
    assert agg.buyers[0].active_sessions == 3

    assert len(agg.sellers) == 1
    assert agg.sellers[0].broker_code == "YP"
    assert agg.sellers[0].net_value == Decimal("-1000000")
    assert agg.sellers[0].active_sessions == 1


def test_top_5_limit_and_sort_by_abs_value():
    rows = []
    for i in range(7):
        code = f"BR{i:02d}"
        rows.append(BrokerFlowRow(code, f"Broker{i}", "FOREIGN",
                                   Decimal(f"{7-i}00000"), date(2026, 6, 1)))
    agg = aggregate_broker_detail_rows(
        rows,
        latest_net_flow=Decimal("1000000"),
        smart_money_brokers=_SMART,
        noise_brokers=_NOISE,
        broker_weights=_WEIGHTS,
        smart_share_threshold_pct=_THRESHOLD,
    )
    assert len(agg.buyers) == 5
    values = [b.net_value for b in agg.buyers]
    assert values == [Decimal("700000"), Decimal("600000"), Decimal("500000"),
                       Decimal("400000"), Decimal("300000")]


def test_smart_noise_neutral_flow_totals():
    agg = aggregate_broker_detail_rows(
        [
            _row("AK", "UBS", 10000000, broker_type="FOREIGN"),
            _row("YP", "CGS-CIMB", 5000000, broker_type="LOCAL"),
            _row("HD", "Mandiri", 3000000, broker_type="FOREIGN"),
            _row("AK", "UBS", -2000000, broker_type="FOREIGN"),
        ],
        latest_net_flow=Decimal("16000000"),
        smart_money_brokers=_SMART,
        noise_brokers=_NOISE,
        broker_weights=_WEIGHTS,
        smart_share_threshold_pct=_THRESHOLD,
    )
    assert agg.smart_flow == Decimal("8000000")
    assert agg.noise_flow == Decimal("5000000")
    assert agg.neutral_flow == Decimal("3000000")
    expected_weighted = (Decimal("8000000") * Decimal("1.5")
                         + Decimal("5000000") * Decimal("0.5")
                         + Decimal("3000000"))
    assert agg.weighted_net_flow == expected_weighted


def test_smart_share_pct_rounding():
    agg = aggregate_broker_detail_rows(
        [
            _row("AK", "UBS", 10000000),
            _row("YP", "CGS-CIMB", 5000000),
            _row("HD", "Mandiri", 5000000),
        ],
        latest_net_flow=Decimal("20000000"),
        smart_money_brokers=_SMART,
        noise_brokers=_NOISE,
        broker_weights=_WEIGHTS,
        smart_share_threshold_pct=_THRESHOLD,
    )
    assert agg.smart_share_pct == 50.0


def test_smart_share_pct_none_when_zero_total():
    agg = aggregate_broker_detail_rows(
        [],
        latest_net_flow=Decimal("0"),
        smart_money_brokers=_SMART,
        noise_brokers=_NOISE,
        broker_weights=_WEIGHTS,
        smart_share_threshold_pct=_THRESHOLD,
    )
    assert agg.smart_share_pct is None


def test_top_buyer_share_pct_rounding():
    agg = aggregate_broker_detail_rows(
        [
            _row("AK", "UBS", 7000000),
            _row("YP", "CGS-CIMB", 3000000),
        ],
        latest_net_flow=Decimal("10000000"),
        smart_money_brokers=_SMART,
        noise_brokers=_NOISE,
        broker_weights=_WEIGHTS,
        smart_share_threshold_pct=_THRESHOLD,
    )
    assert agg.top_buyer_share_pct == 70.0


def test_top_seller_share_pct_rounding():
    agg = aggregate_broker_detail_rows(
        [
            _row("AK", "UBS", 1000000),
            _row("YP", "CGS-CIMB", -8000000),
            _row("HD", "Mandiri", -2000000),
        ],
        latest_net_flow=Decimal("-9000000"),
        smart_money_brokers=_SMART,
        noise_brokers=_NOISE,
        broker_weights=_WEIGHTS,
        smart_share_threshold_pct=_THRESHOLD,
    )
    assert agg.top_seller_share_pct == 80.0


def test_broker_weight_quality_smart_distribution():
    agg = aggregate_broker_detail_rows(
        [
            _row("AK", "UBS", -10000000),
            _row("HD", "Mandiri", 2000000),
        ],
        latest_net_flow=Decimal("-8000000"),
        smart_money_brokers=_SMART,
        noise_brokers=_NOISE,
        broker_weights=_WEIGHTS,
        smart_share_threshold_pct=_THRESHOLD,
    )
    assert agg.broker_weight_quality == "smart distribution"


def test_broker_weight_quality_smart_distribution_watch():
    agg = aggregate_broker_detail_rows(
        [
            _row("AK", "UBS", 5000000),
            _row("HD", "Mandiri", -10000000),
        ],
        latest_net_flow=Decimal("-5000000"),
        smart_money_brokers=_SMART,
        noise_brokers=_NOISE,
        broker_weights=_WEIGHTS,
        smart_share_threshold_pct=_THRESHOLD,
    )
    assert agg.broker_weight_quality == "smart distribution watch"


def test_broker_weight_quality_smart_accumulation():
    agg = aggregate_broker_detail_rows(
        [
            _row("AK", "UBS", 12000000),
            _row("YP", "CGS-CIMB", 3000000),
        ],
        latest_net_flow=Decimal("15000000"),
        smart_money_brokers=_SMART,
        noise_brokers=_NOISE,
        broker_weights=_WEIGHTS,
        smart_share_threshold_pct=60.0,
    )
    assert agg.smart_share_pct == 80.0
    assert agg.broker_weight_quality == "smart accumulation"


def test_broker_weight_quality_noisy_accumulation():
    agg = aggregate_broker_detail_rows(
        [
            _row("YP", "CGS-CIMB", 10000000),
            _row("HD", "Mandiri", 2000000),
        ],
        latest_net_flow=Decimal("12000000"),
        smart_money_brokers=_SMART,
        noise_brokers=_NOISE,
        broker_weights=_WEIGHTS,
        smart_share_threshold_pct=_THRESHOLD,
    )
    assert agg.broker_weight_quality == "noisy accumulation"


def test_broker_weight_quality_smart_support():
    agg = aggregate_broker_detail_rows(
        [
            _row("AK", "UBS", 5000000),
            _row("YP", "CGS-CIMB", 10000000),
        ],
        latest_net_flow=Decimal("15000000"),
        smart_money_brokers=_SMART,
        noise_brokers=_NOISE,
        broker_weights=_WEIGHTS,
        smart_share_threshold_pct=60.0,
    )
    assert agg.broker_weight_quality == "smart support"


def test_broker_weight_quality_smart_selling_pressure():
    agg = aggregate_broker_detail_rows(
        [
            _row("AK", "UBS", -3000000),
            _row("HD", "Mandiri", 10000000),
        ],
        latest_net_flow=Decimal("7000000"),
        smart_money_brokers=_SMART,
        noise_brokers=_NOISE,
        broker_weights=_WEIGHTS,
        smart_share_threshold_pct=_THRESHOLD,
    )
    assert agg.broker_weight_quality == "smart selling pressure"


def test_broker_weight_quality_neutral_accumulation():
    agg = aggregate_broker_detail_rows(
        [
            _row("HD", "Mandiri", 10000000),
        ],
        latest_net_flow=Decimal("10000000"),
        smart_money_brokers=_SMART,
        noise_brokers=_NOISE,
        broker_weights=_WEIGHTS,
        smart_share_threshold_pct=_THRESHOLD,
    )
    assert agg.broker_weight_quality == "neutral accumulation"


def test_broker_weight_quality_neutral_detail():
    agg = aggregate_broker_detail_rows(
        [
            _row("HD", "Mandiri", 0),
        ],
        latest_net_flow=Decimal("0"),
        smart_money_brokers=_SMART,
        noise_brokers=_NOISE,
        broker_weights=_WEIGHTS,
        smart_share_threshold_pct=_THRESHOLD,
    )
    assert agg.broker_weight_quality == "neutral detail"
