from dataclasses import replace
from datetime import date

from src.application.dto.pre_open_signal import PreOpenSignalEvaluationInput
from src.application.services.signal_engine import SignalEngine
from src.domain.value_objects.market_context import MarketContext, MarketRegime
from src.domain.value_objects.pre_open_directional_baseline import (
    PreOpenAuctionQuality,
)
from src.domain.value_objects.signal_assessment import EntryQuality
from tests.application.services.test_pre_open_directional_baseline import _bundle

DAY = date(2026, 7, 27)


def _evaluate(bundle=None, market_context=None):
    engine = SignalEngine()
    return engine.evaluate_pre_open_auction_direction(
        PreOpenSignalEvaluationInput(
            ticker="BBCA",
            snapshot_date=DAY,
            evidence=bundle or _bundle(),
        ),
        market_context=market_context,
    )


def _market_context(*, multiplier=1.0, tightening=False):
    return MarketContext(
        regime=MarketRegime.RISK_OFF if tightening else MarketRegime.NEUTRAL,
        conviction=0.5,
        factors=(),
        signal_multiplier=multiplier,
        gate_tightening=tightening,
        as_of_date=DAY,
    )


def test_reliable_bullish_baseline_produces_enter():
    result = _evaluate()

    assert result.response.score == 80
    assert result.response.assessment.entry_quality is EntryQuality.ENTER
    assert result.baseline.auction_quality is PreOpenAuctionQuality.RELIABLE
    assert result.response.assessment.identity.to_dict() == {
        "purpose": "PRE_OPEN_AUCTION_DIRECTION",
        "policy_contract": "pre_open_auction_direction.v1",
    }


def test_caution_quality_caps_bullish_signal_at_watch():
    result = _evaluate(_bundle(iep=1060))

    assert result.response.signal_score_raw == 80
    assert result.response.assessment.entry_quality is EntryQuality.WATCH
    assert "auction_quality:CAUTION" in (
        result.response.assessment.decision_constraints.constraint_reasons
    )


def test_unreliable_quality_forces_avoid():
    result = _evaluate(_bundle(spread=None))

    assert result.response.assessment.entry_quality is EntryQuality.AVOID


def test_market_context_adjusts_score_and_caps_enter():
    result = _evaluate(market_context=_market_context(multiplier=0.8, tightening=True))

    assert result.response.signal_score_raw == 80
    assert result.response.score == 64
    assert result.response.assessment.entry_quality is EntryQuality.WATCH


def test_rsi_and_unusual_volume_only_add_context_rationale():
    result = _evaluate(_bundle(rsi_extension=True, unusual_volume=True))

    assert result.response.assessment.entry_quality is EntryQuality.ENTER
    assert "context:rsi_extension" in result.response.assessment.rationale
    assert "context:unusual_volume" in result.response.assessment.rationale


def test_missing_ncp_auction_returns_none():
    evidence = replace(_bundle(), auction_ncp=None)

    assert _evaluate(evidence) is None
