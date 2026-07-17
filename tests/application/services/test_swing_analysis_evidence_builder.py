"""Coordinator tests for SwingAnalysisEvidenceBuilder.build().

Focuses on the finding-3 refactor: evidence families must delegate to
CandidateEvidenceDataLoader + the candidate_*_evidence_assembler modules
instead of duplicating repository fetches/request construction inline, while
warning strings on failure stay byte-for-byte identical.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from src.application.dto.accumulation_screen import AccumulationCandidate
from src.application.services.swing_analysis_evidence_builder import (
    SwingAnalysisEvidenceBuilder,
)
from src.domain.entities.candle import Candle
from src.domain.value_objects.setup_evaluation import SetupEvaluation, SetupMatch
from src.domain.value_objects.ticker_notation import TickerNotationSnapshot
from src.infrastructure.config.rules_yaml_loader import RulesYamlLoader


class _MarketRepository:
    def __init__(self, candles_by_ticker: dict[str, list[Candle]] | None = None) -> None:
        self._candles_by_ticker = candles_by_ticker or {}
        self.get_candles_calls: list[dict] = []

    def get_candles(self, ticker, start_date=None, end_date=None):
        self.get_candles_calls.append(
            {"ticker": ticker, "start_date": start_date, "end_date": end_date}
        )
        return list(self._candles_by_ticker.get(ticker, []))

    def get_candle_source(self, ticker, on_date):
        return None


class _BrokerRepository:
    def __init__(self) -> None:
        self.get_broker_daily_flows_calls: list[dict] = []
        self.get_broker_summaries_calls: list[dict] = []

    def get_broker_daily_flows(self, ticker, start_date=None, end_date=None):
        self.get_broker_daily_flows_calls.append({"ticker": ticker, "start_date": start_date})
        return []

    def get_foreign_flow_points(self, ticker, start_date=None, end_date=None):
        return []

    def get_broker_summaries(self, ticker, start_date=None, end_date=None):
        self.get_broker_summaries_calls.append({"ticker": ticker, "start_date": start_date})
        return []


class _NullFlowConfirmationBuilder:
    def build(
        self, candidate, *, analysis_date, consumed_broker_summaries, consumed_broker_daily_flows
    ):
        return None


class _RecordingTickerProfileClassifier:
    def __init__(self) -> None:
        self.last_request = None

    def classify(self, request):
        self.last_request = request
        return object()


class _RecordingSectorContextBuilder:
    def __init__(self, peers: tuple[str, ...]) -> None:
        self._peers = peers
        self.last_request = None

    def peers_for_ticker(self, ticker):
        return self._peers

    def build(self, request):
        self.last_request = request
        return object()


class _RecordingCompanyQualityBuilder:
    def __init__(self) -> None:
        self.last_request = None

    def build(self, request):
        self.last_request = request
        return object()


class _FakeSignalEngine:
    def foreign_flow_quality_from_foreign_flow_score(self, score):
        return "MODERATE"

    def bandar_max_range(self, num_optional):
        return 100.0


class _RaisingFactory:
    def __init__(self, message: str) -> None:
        self._message = message

    def __call__(self):
        raise RuntimeError(self._message)


def _candles(ticker: str, start: date, count: int) -> list[Candle]:
    return [
        Candle(
            ticker=ticker,
            date=date.fromordinal(start.toordinal() + i),
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100") + Decimal(i),
            volume=1_000_000,
        )
        for i in range(count)
    ]


def _candidate(**overrides) -> AccumulationCandidate:
    values = dict(
        ticker="BBCA",
        window_days=7,
        net_buy_days=4,
        total_days=5,
        net_buy_ratio=0.8,
        total_net_value=Decimal("1000000"),
        consecutive_streak=3,
        foreign_vwap=Decimal("1000"),
        current_price=Decimal("1000"),
        vwap_discount_pct=0.0,
        rsi=50.0,
        trend="UP",
        foreign_flow_score=50.0,
        top_brokers=None,
        institutional_flag=False,
    )
    values.update(overrides)
    return AccumulationCandidate(**values)


def _eval_result(candidate) -> SimpleNamespace:
    """Minimal stand-in for AccumulationCandidateEvaluationResult."""
    return SimpleNamespace(
        candidate=candidate,
        consumed_candles=(),
        consumed_broker_summaries=(),
        consumed_broker_daily_flows=(),
    )


class _RaisingCandidateObservationsRepository:
    def list_recent(self, ticker, *, before_date=None, limit=20):
        raise RuntimeError("history unavailable")


def _builder(
    market_repo,
    broker_repo,
    *,
    ticker_profile_classifier_factory=None,
    sector_context_builder_factory=None,
    company_quality_context_builder_factory=None,
    signal_engine=None,
    candidate_observations_repository=None,
) -> SwingAnalysisEvidenceBuilder:
    return SwingAnalysisEvidenceBuilder(
        market_repository=market_repo,
        broker_repository=broker_repo,
        registry=None,
        rules_loader=RulesYamlLoader(),
        flow_confirmation_builder=_NullFlowConfirmationBuilder(),
        candidate_observations_repository=candidate_observations_repository,
        signal_engine=signal_engine,
        corporate_action_risk_use_case=None,
        ticker_profile_classifier_factory=ticker_profile_classifier_factory,
        sector_context_builder_factory=sector_context_builder_factory,
        company_quality_context_builder_factory=company_quality_context_builder_factory,
    )


class TestInstitutionalAccumulationDelegation:
    def test_delegates_through_data_loader_and_assembler(self):
        ticker = "BBCA"
        snapshot_date = date(2026, 6, 15)
        candles = _candles(ticker, date(2026, 6, 1), 10)
        market_repo = _MarketRepository()
        broker_repo = _BrokerRepository()
        builder = _builder(market_repo, broker_repo)

        result = builder.build(
            ticker=ticker,
            snapshot_date=snapshot_date,
            benchmark="IHSG",
            candles=candles,
            accumulation_evaluation=None,
            setup_eval=None,
            setup_name=None,
            strategy_name=None,
            swing_config=None,
        )

        assert result.institutional_accumulation_evidence is not None
        assert result.institutional_accumulation_evidence.ticker == ticker
        assert result.institutional_accumulation_evidence.snapshot_date == snapshot_date
        expected_start = snapshot_date - timedelta(days=45)
        assert broker_repo.get_broker_daily_flows_calls == [
            {"ticker": ticker, "start_date": expected_start}
        ]
        # Candles were reused from the already-loaded `candles` argument for
        # the target ticker, not re-fetched from the repository (only the
        # sector-context benchmark lookup calls the repository).
        assert all(call["ticker"] != ticker for call in market_repo.get_candles_calls)
        assert "Institutional accumulation evidence unavailable" not in " ".join(
            result.warnings
        )


class TestTickerProfileDelegation:
    def test_receives_reused_candles_and_candidate_derived_fields(self):
        ticker = "BBCA"
        snapshot_date = date(2026, 6, 15)
        candles = _candles(ticker, date(2026, 6, 1), 10)
        market_repo = _MarketRepository()
        broker_repo = _BrokerRepository()
        classifier = _RecordingTickerProfileClassifier()
        candidate = _candidate(
            ticker=ticker,
            ticker_notation=TickerNotationSnapshot(
                ticker=ticker, sector="Financials", sub_sector="Banks"
            ),
        )
        builder = _builder(
            market_repo, broker_repo, ticker_profile_classifier_factory=lambda: classifier
        )

        builder.build(
            ticker=ticker,
            snapshot_date=snapshot_date,
            benchmark="IHSG",
            candles=candles,
            accumulation_evaluation=_eval_result(candidate),
            setup_eval=None,
            setup_name=None,
            strategy_name=None,
            swing_config=None,
        )

        assert classifier.last_request is not None
        assert classifier.last_request.candles == tuple(candles)
        assert classifier.last_request.sector == "Financials"
        assert classifier.last_request.sub_sector == "Banks"


class TestSectorContextDelegation:
    def test_uses_peer_candles_and_benchmark(self):
        ticker = "BBCA"
        snapshot_date = date(2026, 6, 15)
        candles = _candles(ticker, date(2026, 6, 1), 10)
        peer_candles = {"PEER1": _candles("PEER1", date(2026, 6, 1), 10)}
        market_repo = _MarketRepository(
            {"PEER1": peer_candles["PEER1"], "IHSG": _candles("IHSG", date(2026, 5, 1), 25)}
        )
        broker_repo = _BrokerRepository()
        sector_builder = _RecordingSectorContextBuilder(peers=("PEER1",))
        builder = _builder(
            market_repo,
            broker_repo,
            sector_context_builder_factory=lambda: sector_builder,
        )

        builder.build(
            ticker=ticker,
            snapshot_date=snapshot_date,
            benchmark="IHSG",
            candles=candles,
            accumulation_evaluation=None,
            setup_eval=None,
            setup_name=None,
            strategy_name=None,
            swing_config=None,
        )

        assert sector_builder.last_request is not None
        assert "PEER1" in sector_builder.last_request.peer_candles
        assert sector_builder.last_request.ihsg_20d_return is not None


class TestCompanyQualityDelegation:
    def test_uses_candidate_signal_context(self):
        ticker = "BBCA"
        snapshot_date = date(2026, 6, 15)
        candles = _candles(ticker, date(2026, 6, 1), 10)
        market_repo = _MarketRepository()
        broker_repo = _BrokerRepository()
        cq_builder = _RecordingCompanyQualityBuilder()
        candidate = _candidate(ticker=ticker)
        builder = _builder(
            market_repo,
            broker_repo,
            company_quality_context_builder_factory=lambda: cq_builder,
            signal_engine=_FakeSignalEngine(),
        )

        builder.build(
            ticker=ticker,
            snapshot_date=snapshot_date,
            benchmark="IHSG",
            candles=candles,
            accumulation_evaluation=_eval_result(candidate),
            setup_eval=None,
            setup_name=None,
            strategy_name=None,
            swing_config=None,
        )

        assert cq_builder.last_request is not None
        assert cq_builder.last_request.signal_context.ticker == ticker
        assert cq_builder.last_request.signal_context.snapshot_date == snapshot_date


class TestWarningStringsExact:
    def test_institutional_accumulation_failure_warning(self):
        ticker = "BBCA"
        snapshot_date = date(2026, 6, 15)
        candles = _candles(ticker, date(2026, 6, 1), 10)
        market_repo = _MarketRepository()

        class _RaisingBrokerRepository:
            def get_broker_daily_flows(self, ticker, start_date=None, end_date=None):
                raise RuntimeError("broker down")

            def get_foreign_flow_points(self, ticker, start_date=None, end_date=None):
                return []

            def get_broker_summaries(self, ticker, start_date=None, end_date=None):
                return []

        builder = _builder(market_repo, _RaisingBrokerRepository())

        result = builder.build(
            ticker=ticker,
            snapshot_date=snapshot_date,
            benchmark="IHSG",
            candles=candles,
            accumulation_evaluation=None,
            setup_eval=None,
            setup_name=None,
            strategy_name=None,
            swing_config=None,
        )

        assert "Institutional accumulation evidence unavailable: broker down" in result.warnings

    def test_ticker_profile_sector_context_company_quality_and_setup_phase_failure_warnings(self):
        ticker = "BBCA"
        snapshot_date = date(2026, 6, 15)
        candles = _candles(ticker, date(2026, 6, 1), 10)
        market_repo = _MarketRepository()
        broker_repo = _BrokerRepository()
        candidate = _candidate(ticker=ticker)
        builder = _builder(
            market_repo,
            broker_repo,
            ticker_profile_classifier_factory=_RaisingFactory("tp down"),
            sector_context_builder_factory=_RaisingFactory("sector down"),
            company_quality_context_builder_factory=_RaisingFactory("cq down"),
            signal_engine=_FakeSignalEngine(),
            candidate_observations_repository=_RaisingCandidateObservationsRepository(),
        )
        setup_eval = SetupEvaluation(
            name="foreign-bounce", match=SetupMatch.MATCH, gates=(), failed_reasons=()
        )

        result = builder.build(
            ticker=ticker,
            snapshot_date=snapshot_date,
            benchmark="IHSG",
            candles=candles,
            accumulation_evaluation=_eval_result(candidate),
            setup_eval=setup_eval,
            setup_name="foreign-bounce",
            strategy_name=None,
            swing_config=None,
        )

        assert "Ticker profile classification unavailable: tp down" in result.warnings
        assert "Sector context evidence unavailable: sector down" in result.warnings
        assert "Company quality context evidence unavailable: cq down" in result.warnings
        assert any(w.startswith("Setup phase unavailable: ") for w in result.warnings)
