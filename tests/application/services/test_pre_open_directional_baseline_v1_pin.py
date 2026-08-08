"""Pin pre-open directional baseline v1 discrete score behavior (task 05 slice 1).

These tests freeze the *current* six-value lookup and intensity-forced LOW
collapse before continuous scoring lands. Do not weaken them until the v2
implementation replaces this module with continuous-score tests.
"""

from __future__ import annotations

from src.application.services.pre_open_directional_baseline import (
    evaluate_pre_open_directional_baseline,
)
from src.application.services.signal_engine_config import (
    PreOpenDirectionalBaselineConfig,
)
from src.domain.value_objects.pre_open_directional_baseline import (
    PreOpenDirection,
    PreOpenDirectionConfidence,
)
from tests.application.services.test_pre_open_directional_baseline import _bundle, _evaluate


def test_v1_six_value_lookup_table() -> None:
    """Production ranking score is one of six discrete integers."""
    cfg = PreOpenDirectionalBaselineConfig()
    discrete = {
        cfg.bullish_high_score,
        cfg.bullish_medium_score,
        cfg.bullish_low_score,
        cfg.neutral_score,
        cfg.conflicted_score,
        cfg.bearish_score,
        cfg.unknown_score,
    }
    assert discrete == {0, 20, 35, 45, 55, 70, 80}

    samples = [
        _evaluate(),  # bullish high (intensity=2)
        _evaluate(iep=990, pressure=0.35),  # bearish
        _evaluate(iep=1010, pressure=0.35),  # conflicted
        _evaluate(delta_iev=None),  # bullish low
        _evaluate(iep=1004),  # neutral flat
        _evaluate(iep=None),  # unknown
        _evaluate(final_iev=520_000, delta_iev=10_000, intensity=2.0),  # medium
    ]
    for result in samples:
        assert result is not None
        assert result.raw_score in discrete
        assert type(result.raw_score) is int


def test_v1_corpus_scale_intensity_always_forces_low_confidence() -> None:
    """Live corpus max intensity ≪ 1.0 — the min_normalized gate never clears."""
    # Representative of measured live PRE_OPEN intensities (max ≈ 0.086).
    for intensity in (0.003, 0.017, 0.086, 0.999):
        result = evaluate_pre_open_directional_baseline(
            _bundle(intensity=intensity, delta_iev=40_000, final_iev=540_000),
            config=PreOpenDirectionalBaselineConfig(),
        )
        assert result is not None
        assert result.direction is PreOpenDirection.BULLISH
        assert result.confidence is PreOpenDirectionConfidence.LOW
        assert result.raw_score == 55  # bullish_low only


def test_v1_high_confidence_requires_unreachable_intensity_on_live_scale() -> None:
    low_intensity = _evaluate(intensity=0.05, final_iev=540_000, delta_iev=40_000)
    high_intensity = _evaluate(intensity=2.0, final_iev=540_000, delta_iev=40_000)
    assert low_intensity.confidence is PreOpenDirectionConfidence.LOW
    assert high_intensity.confidence is PreOpenDirectionConfidence.HIGH
    assert high_intensity.raw_score == 80
    assert low_intensity.raw_score == 55
