from src.application.services.signal_engine import SignalEngine
from src.application.use_case.assess_signal_use_case import (
    AccumulationScoreMappingConfig,
    BandarScoringConfig,
    SignalEngineConfig,
    SignalInputMappingConfig,
    SignalScoringConfig,
)


class EmptyInsiderProvider:
    def get_insider_transactions(self, **kwargs):
        return []


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


def test_signal_engine_empty_insider_fetch_counts_as_neutral_data():
    engine = SignalEngine(insider_activity_provider=EmptyInsiderProvider())

    response = engine.evaluate("BBCA")

    assert response.assessment.breakdown_dict["insider_activity"] == 50.0
    assert response.coverage_warning is not None
    assert "5/6" in response.coverage_warning
