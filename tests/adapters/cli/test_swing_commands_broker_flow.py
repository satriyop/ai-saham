"""Foreign bounce and broker detail tests for swing commands."""

from datetime import date
from decimal import Decimal

from src.adapters.cli.analyze_swing_broker_display import (
    build_broker_quality_note,
)
from src.adapters.cli.analyze_swing_broker_display import (
    build_flow_detail as _build_flow_detail,
)
from src.adapters.cli.analyze_swing_commands import (
    FOREIGN_BOUNCE_SETUP_NAME,
    _evaluate_swing_setup,
)
from src.adapters.cli.analyze_swing_display import (
    format_failed_gates_summary as _format_failed_gates_summary,
)
from src.domain.entities.broker_flow import BrokerType
from src.domain.value_objects.setup_evaluation import SetupMatch
from tests.adapters.cli.swing_command_fixtures import (
    FakeBrokerSummaryRepository,
    _build_broker_detail,
    _candidate,
    _summary,
    _tx,
)


def _build_broker_quality_note(detail, setup):
    from src.adapters.cli.analyze_swing_broker_display import (
        build_broker_quality_note as _bbqn,
    )
    return _bbqn(detail, setup)


def test_foreign_bounce_passes_all_gates():
    evaluation = _evaluate_swing_setup(FOREIGN_BOUNCE_SETUP_NAME, _candidate())

    assert evaluation.name == FOREIGN_BOUNCE_SETUP_NAME
    assert evaluation.passed is True
    assert evaluation.match == SetupMatch.MATCH
    assert evaluation.failed_reasons == ()


def test_foreign_bounce_reports_failed_gates():
    evaluation = _evaluate_swing_setup(
        FOREIGN_BOUNCE_SETUP_NAME,
        _candidate(score=70.0, trend="DOWN"),
    )

    assert evaluation.passed is False
    assert evaluation.match == SetupMatch.PARTIAL
    assert any("trend" in reason for reason in evaluation.failed_reasons)


def test_failed_gates_summary_includes_all_failed_reasons():
    evaluation = _evaluate_swing_setup(
        FOREIGN_BOUNCE_SETUP_NAME,
        _candidate(
            score=26.8,
            vwap_discount_pct=-0.7,
            trend="DOWN",
            avg_flow_ratio=-3.0,
            rsi=32.0,
        )
    )

    summary = _format_failed_gates_summary(evaluation)

    assert "score: 26.8" in summary
    assert "fvwap%: -0.7%" in summary
    assert "trend: DOWN" in summary
    assert "flow_pct: -3.0%" in summary


def test_foreign_bounce_missing_accumulation_is_avoid():
    evaluation = _evaluate_swing_setup(FOREIGN_BOUNCE_SETUP_NAME, None)

    assert evaluation.passed is False
    assert evaluation.match == SetupMatch.NO_MATCH


def test_flow_detail_uses_latest_broker_sessions():
    detail = _build_flow_detail(
        ticker="BBCA",
        broker_repo=FakeBrokerSummaryRepository(
            [
                _summary(date(2026, 6, 1), "120000000", "20000000"),
                _summary(date(2026, 6, 2), "10000000", "50000000"),
                _summary(date(2026, 6, 3), "80000000", "10000000"),
                _summary(date(2026, 6, 4), "90000000", "10000000"),
            ]
        ),
        window_sessions=3,
        as_of_date=date(2026, 6, 4),
    )

    assert detail is not None
    assert detail.available_sessions == 3
    assert detail.from_date == date(2026, 6, 2)
    assert detail.through_date == date(2026, 6, 4)
    assert detail.total_net_flow == Decimal("110000000")
    assert detail.buy_sessions == 2
    assert detail.sell_sessions == 1
    assert detail.consecutive_buy_sessions == 2
    assert detail.latest_net_flow == Decimal("80000000")
    assert detail.to_dict()["window_sessions"] == 3


def test_broker_detail_aggregates_named_brokers_across_investor_types():
    detail = _build_broker_detail(
        ticker="BBCA",
        broker_repo=FakeBrokerSummaryRepository(
            [
                _summary(
                    date(2026, 6, 1),
                    "120000000",
                    "20000000",
                    top_buyers=(
                        _tx("AK", "UBS", "70000000", "10000000"),
                        _tx("CC", "Mandiri", "40000000", "5000000"),
                    ),
                    top_sellers=(_tx("KZ", "CLSA", "5000000", "30000000"),),
                ),
                _summary(
                    date(2026, 6, 2),
                    "100000000",
                    "20000000",
                    top_buyers=(
                        _tx("AK", "UBS", "50000000", "10000000"),
                        _tx("YP", "Mirae", "35000000", "5000000", BrokerType.LOCAL),
                    ),
                    top_sellers=(_tx("DB", "Deutsche", "5000000", "25000000"),),
                ),
                _summary(
                    date(2026, 6, 3),
                    "90000000",
                    "20000000",
                    top_buyers=(
                        _tx("CC", "Mandiri", "45000000", "5000000"),
                        _tx("YP", "Mirae", "30000000", "5000000", BrokerType.LOCAL),
                    ),
                    top_sellers=(),
                ),
            ]
        ),
        window_sessions=5,
        as_of_date=date(2026, 6, 3),
    )

    assert detail is not None
    assert detail.detail_sessions == 3
    assert detail.through_date == date(2026, 6, 3)
    assert detail.top_buyers[0].broker_code == "AK"
    assert detail.top_buyers[0].net_value == Decimal("100000000")
    assert detail.top_buyers[0].active_sessions == 2
    assert detail.top_sellers[0].broker_code == "KZ"
    assert detail.top_sellers[0].net_value == Decimal("-25000000")
    assert detail.smart_flow == Decimal("55000000")
    assert detail.noise_flow == Decimal("55000000")
    assert detail.neutral_flow == Decimal("75000000")
    assert detail.weighted_net_flow == Decimal("185000000.0")
    assert detail.smart_share_pct == 29.7
    assert detail.broker_weight_quality == "smart support"
    assert detail.quality == "broad accumulation"
    assert detail.to_dict()["top_buyers"][0]["broker_code"] == "AK"
    buyer_rows = {row["broker_code"]: row for row in detail.to_dict()["top_buyers"]}
    assert buyer_rows["YP"]["broker_type"] == "LOCAL"
    assert detail.to_dict()["smart_flow"] == "55000000"
    assert detail.to_dict()["broker_weight_quality"] == "smart support"


def test_broker_detail_marks_latest_selling_as_recent_distribution():
    detail = _build_broker_detail(
        ticker="BBCA",
        broker_repo=FakeBrokerSummaryRepository(
            [
                _summary(
                    date(2026, 6, 1),
                    "120000000",
                    "20000000",
                    top_buyers=(_tx("AK", "UBS", "90000000", "10000000"),),
                ),
                _summary(
                    date(2026, 6, 2),
                    "10000000",
                    "80000000",
                    top_buyers=(_tx("CC", "Mandiri", "20000000", "5000000"),),
                    top_sellers=(_tx("AK", "UBS", "5000000", "70000000"),),
                ),
            ]
        ),
        window_sessions=5,
        as_of_date=date(2026, 6, 2),
    )

    assert detail is not None
    assert detail.quality == "recent distribution"
    assert detail.smart_flow == Decimal("15000000")
    assert detail.noise_flow == Decimal("0")
    assert detail.broker_weight_quality == "smart distribution watch"


def test_broker_detail_marks_noise_led_buying():
    detail = _build_broker_detail(
        ticker="BBCA",
        broker_repo=FakeBrokerSummaryRepository(
            [
                _summary(
                    date(2026, 6, 1),
                    "180000000",
                    "20000000",
                    top_buyers=(
                        _tx("YP", "CGS-CIMB", "100000000", "10000000", BrokerType.LOCAL),
                        _tx("XL", "Stockbit", "40000000", "10000000", BrokerType.LOCAL),
                        _tx("XC", "Ajaib", "35000000", "5000000", BrokerType.LOCAL),
                    ),
                    top_sellers=(_tx("AK", "UBS", "5000000", "20000000"),),
                ),
            ]
        ),
        window_sessions=5,
        as_of_date=date(2026, 6, 1),
    )

    assert detail is not None
    assert detail.noise_flow == Decimal("150000000")
    assert detail.smart_flow == Decimal("-15000000")
    assert detail.weighted_net_flow == Decimal("52500000.0")
    assert detail.broker_weight_quality == "noisy accumulation"


def test_broker_quality_note_warns_when_enter_is_noise_led():
    detail = _build_broker_detail(
        ticker="BBCA",
        broker_repo=FakeBrokerSummaryRepository(
            [
                _summary(
                    date(2026, 6, 1),
                    "180000000",
                    "20000000",
                    top_buyers=(
                        _tx("YP", "CGS-CIMB", "100000000", "10000000", BrokerType.LOCAL),
                        _tx("XL", "Stockbit", "40000000", "10000000", BrokerType.LOCAL),
                    ),
                    top_sellers=(),
                ),
            ]
        ),
        window_sessions=5,
        as_of_date=date(2026, 6, 1),
    )
    setup = _evaluate_swing_setup(
        FOREIGN_BOUNCE_SETUP_NAME,
        _candidate(score=75, trend="SIDE"),
    )

    note = _build_broker_quality_note(detail, setup)

    assert note is not None
    assert note.level == "warning"
    assert "noise-led" in note.message


def test_broker_quality_note_supports_watch_when_smart_buying():
    detail = _build_broker_detail(
        ticker="BBCA",
        broker_repo=FakeBrokerSummaryRepository(
            [
                _summary(
                    date(2026, 6, 1),
                    "120000000",
                    "20000000",
                    top_buyers=(_tx("AK", "UBS", "90000000", "10000000"),),
                    top_sellers=(),
                ),
            ]
        ),
        window_sessions=5,
        as_of_date=date(2026, 6, 1),
    )
    setup = _evaluate_swing_setup(
        FOREIGN_BOUNCE_SETUP_NAME,
        _candidate(score=56.0, trend="SIDE"),
    )

    note = _build_broker_quality_note(detail, setup)

    assert note is not None
    assert note.level == "support"
    assert "watchlist priority" in note.message


def test_broker_quality_note_warns_on_smart_selling():
    detail = _build_broker_detail(
        ticker="BBCA",
        broker_repo=FakeBrokerSummaryRepository(
            [
                _summary(
                    date(2026, 6, 1),
                    "20000000",
                    "120000000",
                    top_buyers=(_tx("CC", "Mandiri", "20000000", "5000000"),),
                    top_sellers=(_tx("AK", "UBS", "5000000", "90000000"),),
                ),
            ]
        ),
        window_sessions=5,
        as_of_date=date(2026, 6, 1),
    )
    setup = _evaluate_swing_setup(
        FOREIGN_BOUNCE_SETUP_NAME,
        _candidate(score=75, trend="SIDE"),
    )

    note = _build_broker_quality_note(detail, setup)

    assert note is not None
    assert note.level == "warning"
    assert "smart-money net selling" in note.message
    assert "%" in note.message


def test_broker_quality_note_skips_warn_on_minor_smart_selling():
    """Smart selling below 15% share threshold must not fire the smart-selling warning.

    AK sells 5M, HD (neutral) buys 100M → smart sell share ~5% → below threshold.
    """
    detail = _build_broker_detail(
        ticker="BBCA",
        broker_repo=FakeBrokerSummaryRepository(
            [
                _summary(
                    date(2026, 6, 1),
                    "100000000",
                    "5000000",
                    top_buyers=(_tx("HD", "Mandiri", "100000000", "0"),),
                    top_sellers=(_tx("AK", "UBS", "0", "5000000"),),
                ),
            ]
        ),
        window_sessions=5,
        as_of_date=date(2026, 6, 1),
    )
    setup = _evaluate_swing_setup(
        FOREIGN_BOUNCE_SETUP_NAME,
        _candidate(score=75, trend="SIDE"),
    )

    note = build_broker_quality_note(detail, setup, smart_sell_min_share_pct=15.0)

    assert note is None or "smart-money net selling" not in (note.message or "")
