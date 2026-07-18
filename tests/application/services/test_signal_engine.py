from datetime import date

from src.application.services.signal_engine import SignalEngine
from src.application.use_case.assess_signal_use_case import (
    BandarScoringConfig,
    ForeignFlowScoreMappingConfig,
    SignalEngineConfig,
    SignalInputMappingConfig,
    SignalScoringConfig,
)
from src.domain.value_objects.forward_estimates import ForwardEstimates
from src.domain.value_objects.seasonal_edge import SeasonalEdge


class EmptyInsiderProvider:
    def get_insider_transactions(self, **kwargs):
        return []


class RecordingInsiderProvider(EmptyInsiderProvider):
    def __init__(self):
        self.calls = []

    def get_insider_transactions(self, **kwargs):
        self.calls.append(kwargs)
        return []


class ForwardProviderWithMissingPe:
    """Returns ForwardEstimates with no pre-computed PE — must be derived from price."""
    def get_forward_estimates(self, ticker, as_of_date=None):
        return ForwardEstimates(
            ticker=ticker,
            forward_eps_1y=2.0,          # PE=125 when price=250, PE=40 when price=80
            revenue_forward_1y=None,
            current_price=None,
            forward_pe=None,
        )


class AnalystProviderWithLowCurrentPrice:
    """Returns analyst consensus with a low current_price (→ PE=40, below threshold)."""
    def get_consensus(self, ticker, as_of_date=None):
        return type("Consensus", (), {
            "analyst_count": 1,
            "buy_count": 1,
            "buy_ratio": 1.0,        # required to populate analyst_current_price
            "upside_pct": 10.0,
            "current_price": 80.0,   # 80/2=40 PE → below VALUATION_STRETCHED threshold
        })()


class SeasonalityProviderWithShortHistory:
    def get_seasonal_edge(self, ticker, year, month, as_of_date=None):
        return SeasonalEdge(
            ticker=ticker,
            month=month,
            avg_monthly_return_pct=2.5,
            win_rate_pct=75.0,
            positive_years=3,
            total_years=4,
            back_years=5,
        )


class RecordingForwardProvider(ForwardProviderWithMissingPe):
    def __init__(self):
        self.calls = []

    def get_forward_estimates(self, ticker, as_of_date=None):
        self.calls.append((ticker, as_of_date))
        return super().get_forward_estimates(ticker, as_of_date=as_of_date)


class RecordingAnalystProvider(AnalystProviderWithLowCurrentPrice):
    def __init__(self):
        self.calls = []

    def get_consensus(self, ticker, as_of_date=None):
        self.calls.append((ticker, as_of_date))
        return super().get_consensus(ticker, as_of_date=as_of_date)


class RecordingSeasonalityProvider(SeasonalityProviderWithShortHistory):
    def __init__(self):
        self.calls = []

    def get_seasonal_edge(self, ticker, year, month, as_of_date=None):
        self.calls.append((ticker, year, month, as_of_date))
        return super().get_seasonal_edge(
            ticker,
            year,
            month,
            as_of_date=as_of_date,
        )


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
    from src.domain.value_objects.canonical_signal_evidence_input import CanonicalSignalEvidenceInput
    from tests.application.use_case.signal_evidence_fixtures import _flow_evidence, _wrap_flow_evidence

    # Empty insider list → insider_net_buy_ratio=0.0 (not INSIDER_SELLING threshold of -0.30)
    engine = SignalEngine(insider_activity_provider=EmptyInsiderProvider())

    ctx = engine.build_context("BBCA")
    response = engine.evaluate_with_context(
        ticker="BBCA",
        signal_context=ctx,
        canonical_evidence=CanonicalSignalEvidenceInput(
            setup=None,
            flow=_wrap_flow_evidence(_flow_evidence(capped_strength=0.70))
        )
    )

    # 0.0 ratio does NOT trigger INSIDER_SELLING penalty
    assert "INSIDER_SELLING" not in response.active_flags


def test_signal_engine_derives_forward_pe_from_latest_price_before_analyst_price():
    from src.domain.value_objects.canonical_signal_evidence_input import CanonicalSignalEvidenceInput
    from tests.application.use_case.signal_evidence_fixtures import _flow_evidence, _wrap_flow_evidence

    # With latest_price=250.0: PE = 250/2 = 125.0 > 50 → VALUATION_STRETCHED fires.
    # Without latest_price (analyst_price=80.0 only): PE = 80/2 = 40.0 ≤ 50 → no flag.
    # Flag firing proves latest_price was used in preference to analyst_current_price.
    engine = SignalEngine(
        analyst_provider=AnalystProviderWithLowCurrentPrice(),
        forward_estimates_provider=ForwardProviderWithMissingPe(),
        latest_price_provider=lambda ticker: 250.0,
    )

    ctx = engine.build_context("BBCA")
    response = engine.evaluate_with_context(
        ticker="BBCA",
        signal_context=ctx,
        canonical_evidence=CanonicalSignalEvidenceInput(
            setup=None,
            flow=_wrap_flow_evidence(_flow_evidence(capped_strength=0.70))
        )
    )

    assert "VALUATION_STRETCHED" in response.active_flags


def test_signal_engine_threads_seasonality_sample_size_into_context():
    engine = SignalEngine(seasonality_provider=SeasonalityProviderWithShortHistory())

    ctx = engine.build_context("BBCA")

    assert ctx.seasonality_win_rate == 75.0
    assert ctx.seasonality_avg_return_pct == 2.5
    assert ctx.seasonality_total_years == 4
    assert ctx.seasonality_back_years == 5


def test_signal_engine_passes_none_as_of_for_live_enrichment_and_date_for_replay():
    insider = RecordingInsiderProvider()
    analyst = RecordingAnalystProvider()
    forward = RecordingForwardProvider()
    seasonality = RecordingSeasonalityProvider()
    engine = SignalEngine(
        insider_activity_provider=insider,
        analyst_provider=analyst,
        forward_estimates_provider=forward,
        seasonality_provider=seasonality,
    )

    live_ctx = engine.build_context("BBCA")
    replay_ctx = engine.build_context("BBCA", as_of_date=date(2026, 6, 15))

    assert live_ctx.snapshot_date == date.today()
    assert replay_ctx.snapshot_date == date(2026, 6, 15)
    assert analyst.calls == [("BBCA", None), ("BBCA", date(2026, 6, 15))]
    assert forward.calls == [("BBCA", None), ("BBCA", date(2026, 6, 15))]
    assert seasonality.calls[0][3] is None
    assert seasonality.calls[1] == ("BBCA", 2026, 6, date(2026, 6, 15))
    assert insider.calls[0]["as_of_date"] is None
    assert insider.calls[1]["as_of_date"] == date(2026, 6, 15)


def test_flags_only_assessment_methods_are_removed():
    assert not hasattr(SignalEngine, "evaluate")
    assert not hasattr(SignalEngine, "evaluate_request")
    assert hasattr(SignalEngine, "build_context")
    assert hasattr(SignalEngine, "evaluate_with_context")
