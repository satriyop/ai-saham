from src.application.services.signal_engine import SignalEngine
from src.application.use_case.assess_signal_use_case import (
    ForeignFlowScoreMappingConfig,
    BandarScoringConfig,
    SignalEngineConfig,
    SignalInputMappingConfig,
    SignalScoringConfig,
)
from src.domain.value_objects.forward_estimates import ForwardEstimates



class EmptyInsiderProvider:
    def get_insider_transactions(self, **kwargs):
        return []


class ForwardProviderWithMissingPe:
    def get_forward_estimates(self, ticker):
        return ForwardEstimates(
            ticker=ticker,
            forward_eps_1y=10.0,
            revenue_forward_1y=None,
            current_price=None,
            forward_pe=None,
        )


class AnalystProviderWithStalePrice:
    def get_consensus(self, ticker):
        return type("Consensus", (), {
            "analyst_count": 1,
            "buy_count": 1,
            "upside_pct": 10.0,
            "current_price": 80.0,
        })()


def test_signal_engine_input_mapping_helpers_use_config():
    engine = SignalEngine(config=SignalEngineConfig(
        input_mapping=SignalInputMappingConfig(
            foreign_flow_score=ForeignFlowScoreMappingConfig(
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

    assert engine.foreign_flow_quality_from_foreign_flow_score(75.0) == 0.5
    assert engine.foreign_flow_quality_from_foreign_flow_score(200.0) == 1.0
    assert engine.bandar_max_range(2) == 18


def test_signal_engine_empty_insider_fetch_counts_as_neutral_data():
    engine = SignalEngine(insider_activity_provider=EmptyInsiderProvider())

    response = engine.evaluate("BBCA")

    assert response.assessment.breakdown_dict["insider_activity"] == 50.0
    assert response.coverage_warning is not None
    assert "5/6" in response.coverage_warning


def test_signal_engine_derives_forward_pe_from_latest_price_before_analyst_price():
    engine = SignalEngine(
        analyst_provider=AnalystProviderWithStalePrice(),
        forward_estimates_provider=ForwardProviderWithMissingPe(),
        latest_price_provider=lambda ticker: 250.0,
    )

    response = engine.evaluate("BBCA")

    assert response.assessment.breakdown_dict["forward_valuation"] == 37.5
