"""Unit tests for pre-open → confirm candidate mapping."""

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from src.application.services.pre_open_post_open_candidate_mapper import (
    extract_market_regime_label,
    extract_opening_price_from_track_payload,
    reconstruct_pre_open_post_open_candidate,
)
from src.domain.value_objects.learning_artifacts import (
    AssessmentPurpose,
    LearningObservation,
)

WIB = ZoneInfo("Asia/Jakarta")


def _obs(payload: dict) -> LearningObservation:
    return LearningObservation.create(
        purpose=AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION,
        policy_contract="pre_open_directional_baseline.v1",
        horizon_contract="open_30m",
        compatibility_id="compat-test",
        cutoff_at=datetime(2026, 6, 18, 8, 57, tzinfo=WIB),
        universe_id="iev:2026-06-18",
        window_id="BBCA:2026-06-18",
        decision_payload=payload,
        captured_at=datetime(2026, 6, 18, 8, 57, tzinfo=WIB),
    )


def test_reconstruct_maps_plan_field_aliases() -> None:
    obs = _obs(
        {
            "ticker": "BBCA",
            "candidate": {
                "ticker": "BBCA",
                "iev": 200_000,
                "entry_price": "10050",
                "stop_loss_price": "9800",
                "trend_signal": "BULLISH",
                "rsi": "52",
                "gap_pct": "1.0",
                "entry_range_low": "9900",
                "entry_range_high": "10100",
                "opening_broker_backing_tag": "BACKED",
                "fvwap_discount_pct": "0.5",
            },
        }
    )
    cand = reconstruct_pre_open_post_open_candidate(
        obs,
        opening_price=Decimal("10000"),
        opening_price_source="order_book_lastprice",
        opening_price_confidence="MEDIUM",
    )
    assert cand.ticker == "BBCA"
    assert cand.suggested_entry == Decimal("10050")
    assert cand.atr_stop == Decimal("9800")
    assert cand.trend == "BULLISH"
    assert cand.entry_range_low == Decimal("9900")
    assert cand.opening_price == Decimal("10000")
    assert cand.opening_price_source == "order_book_lastprice"
    assert cand.opening_broker_backing_tag == "BACKED"


def test_extract_opening_price_requires_explicit_key() -> None:
    price, source, conf = extract_opening_price_from_track_payload(
        {
            "mid_price": "10050",
            "best_bid": "10000",
            "best_offer": "10100",
        }
    )
    assert price is None
    assert source is None

    price, source, conf = extract_opening_price_from_track_payload(
        {
            "opening_price": "10020",
            "opening_price_source": "order_book_lastprice",
            "opening_price_confidence": "MEDIUM",
            "mid_price": "10050",
        }
    )
    assert price == Decimal("10020")
    assert source == "order_book_lastprice"
    assert conf == "MEDIUM"


def test_extract_market_regime_from_dict_and_string() -> None:
    label, warn = extract_market_regime_label(
        {"market_regime": {"regime": "RISK_ON", "conviction": 0.7}}
    )
    assert label == "RISK_ON"
    assert warn is None

    label, warn = extract_market_regime_label({"market_regime": "NEUTRAL"})
    assert label == "NEUTRAL"
    assert warn is None

    label, warn = extract_market_regime_label({"market_regime": {"regime": "WEIRD"}})
    assert label is None
    assert warn is not None
    assert "RISK_OFF" in warn

    label, warn = extract_market_regime_label({})
    assert label is None
    assert warn is None
