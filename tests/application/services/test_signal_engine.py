from src.application.services.signal_engine import SignalEngine
from src.application.use_case.assess_signal_use_case import (
    AccumulationScoreMappingConfig,
    BandarScoringConfig,
    SignalEngineConfig,
    SignalInputMappingConfig,
    SignalScoringConfig,
)


def test_signal_engine_input_mapping_helpers_use_config():
    engine = SignalEngine(config=SignalEngineConfig(
        input_mapping=SignalInputMappingConfig(
            accumulation_score=AccumulationScoreMappingConfig(
                max_score=150.0,
                clamp=True,
            )
        ),
        scoring=SignalScoringConfig(
            bandar=BandarScoringConfig(
                mandatory_signal_count=4,
                signal_score_unit=3,
                default_max_range=12,
            )
        ),
    ))

    assert engine.foreign_flow_quality_from_accum_score(75.0) == 0.5
    assert engine.foreign_flow_quality_from_accum_score(200.0) == 1.0
    assert engine.bandar_max_range(2) == 18
