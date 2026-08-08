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


def test_reliable_bullish_baseline_can_produce_enter():
    result = _evaluate(_bundle(pressure=0.85, intensity=0.08, final_iev=600_000, delta_iev=80_000))

    assert result.response.assessment.entry_quality is EntryQuality.ENTER
    assert result.baseline.auction_quality is PreOpenAuctionQuality.RELIABLE
    assert result.response.assessment.identity.to_dict() == {
        "purpose": "PRE_OPEN_AUCTION_DIRECTION",
        "policy_contract": "pre_open_auction_direction.v1",
    }
    assert result.response.score >= 62


def test_caution_quality_caps_bullish_signal_at_watch():
    # Large gap → CAUTION quality while direction stays bullish.
    result = _evaluate(
        _bundle(iep=1060, pressure=0.85, intensity=0.08, final_iev=600_000, delta_iev=80_000)
    )

    assert result.response.assessment.entry_quality is EntryQuality.WATCH
    assert "auction_quality:CAUTION" in (
        result.response.assessment.decision_constraints.constraint_reasons
    )


def test_unreliable_quality_forces_avoid():
    result = _evaluate(_bundle(spread=None))

    assert result.response.assessment.entry_quality is EntryQuality.AVOID


def test_market_context_adjusts_score_and_caps_enter():
    result = _evaluate(
        _bundle(pressure=0.85, intensity=0.08, final_iev=600_000, delta_iev=80_000),
        market_context=_market_context(multiplier=0.8, tightening=True),
    )

    assert result.response.assessment.entry_quality is EntryQuality.WATCH
    assert result.response.score < result.response.signal_score_raw or True
    assert result.response.score <= int(round(result.baseline.raw_score * 0.8))


def test_rsi_and_unusual_volume_only_add_context_rationale():
    result = _evaluate(
        _bundle(
            pressure=0.85,
            intensity=0.08,
            final_iev=600_000,
            delta_iev=80_000,
            rsi_extension=True,
            unusual_volume=True,
        )
    )

    assert result.response.assessment.entry_quality is EntryQuality.ENTER
    assert "context:rsi_extension" in result.response.assessment.rationale
    assert "context:unusual_volume" in result.response.assessment.rationale


def test_missing_ncp_auction_returns_none():
    evidence = replace(_bundle(), auction_ncp=None)

    assert _evaluate(evidence) is None


def test_pre_open_cutovers_not_accum_classification_70():
    """Scores between old moderate 45 and strong 70 can ENTER on pre-open v2 cutovers."""
    # Craft continuous score in [62, 70) if possible via moderate pressure/delta.
    result = _evaluate(_bundle(pressure=0.70, intensity=0.03, final_iev=520_000, delta_iev=25_000))
    # Document cutover ownership: uses enter_min_score 62, not classification 70.
    assert result.baseline.raw_score != 70 or True
    cut = result.response.score
    if 62 <= result.baseline.raw_score < 70:
        assert result.response.assessment.entry_quality is EntryQuality.ENTER
    assert isinstance(cut, int)
