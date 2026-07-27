"""Tests for swing_broker_quality_note_policy.py."""

from decimal import Decimal
from unittest.mock import MagicMock

from src.application.dto.swing_broker_detail import BrokerDetail
from src.application.services.swing_broker_quality_note_policy import (
    build_broker_quality_note,
)
from src.domain.value_objects.setup_evaluation import SetupMatch


def _make_detail(
    smart_flow="0", noise_flow="0", neutral_flow="0", quality="neutral detail"
) -> BrokerDetail:
    return BrokerDetail(
        window_sessions=5,
        detail_sessions=3,
        through_date=MagicMock(),
        source="stockbit",
        top_buyers=(),
        top_sellers=(),
        top_buyer_share_pct=None,
        top_seller_share_pct=None,
        smart_flow=Decimal(smart_flow),
        noise_flow=Decimal(noise_flow),
        neutral_flow=Decimal(neutral_flow),
        weighted_net_flow=Decimal("0"),
        smart_share_pct=None,
        broker_weight_quality=quality,
        quality="broad accumulation",
    )


def _make_setup(match: SetupMatch):
    ev = MagicMock()
    ev.match = match
    return ev


def test_none_broker_detail_returns_none():
    assert build_broker_quality_note(None, _make_setup(SetupMatch.MATCH)) is None


def test_none_setup_eval_returns_none():
    assert build_broker_quality_note(_make_detail(), None) is None


def test_smart_selling_warning():
    detail = _make_detail(smart_flow="-8000000", noise_flow="1000000", neutral_flow="1000000")
    note = build_broker_quality_note(detail, _make_setup(SetupMatch.MATCH))
    assert note is not None
    assert note.level == "warning"
    assert "smart-money net selling" in note.message
    assert "80%" in note.message


def test_smart_selling_below_threshold_skips_warning():
    detail = _make_detail(smart_flow="-500000", noise_flow="5000000", neutral_flow="5000000")
    note = build_broker_quality_note(
        detail,
        _make_setup(SetupMatch.MATCH),
        smart_sell_min_share_pct=15.0,
    )
    assert note is None or "smart-money net selling" not in note.message


def test_noisy_accumulation_warning_for_match():
    detail = _make_detail(smart_flow="1000000", noise_flow="5000000", quality="noisy accumulation")
    note = build_broker_quality_note(detail, _make_setup(SetupMatch.MATCH))
    assert note is not None
    assert note.level == "warning"
    assert "noise-led" in note.message


def test_noisy_accumulation_trigger_via_condition():
    detail = _make_detail(smart_flow="1000000", noise_flow="5000000", quality="neutral detail")
    note = build_broker_quality_note(detail, _make_setup(SetupMatch.MATCH))
    assert note is not None
    assert note.level == "warning"
    assert "noise-led" in note.message


def test_smart_support_note_for_partial():
    detail = _make_detail(smart_flow="5000000")
    note = build_broker_quality_note(detail, _make_setup(SetupMatch.PARTIAL))
    assert note is not None
    assert note.level == "support"
    assert "watchlist priority" in note.message


def test_smart_confirmation_note_for_match():
    detail = _make_detail(smart_flow="5000000")
    note = build_broker_quality_note(detail, _make_setup(SetupMatch.MATCH))
    assert note is not None
    assert note.level == "support"
    assert "confirms the setup match" in note.message
