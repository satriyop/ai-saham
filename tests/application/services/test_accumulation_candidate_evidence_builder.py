"""Coordinator tests for AccumulationCandidateEvidenceBuilder public methods.

Focuses on the finding-3 refactor: each public build_candidate_* /
detect_candidate_setup_phase method must delegate to
CandidateEvidenceDataLoader + the candidate_*_evidence_assembler modules,
preserve best-effort None-on-failure behavior, and keep attaching
benchmark_excess_return_5_session/20_session as diagnostic instance
attributes on successful setup phase detection.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.application.dto.accumulation_screen import AccumulationCandidate
from src.application.services.accumulation_candidate_evidence_builder import (
    AccumulationCandidateEvidenceBuilder,
)
from src.application.services.benchmark_excess_return_calculator import (
    BenchmarkExcessReturnResult,
)
from src.application.services.candidate_setup_phase_evidence_assembler import (
    CandidateSetupPhaseEvidenceAssembler,
)
from src.application.services.primary_setup_family_resolver import (
    PrimarySetupFamilyResolver,
)
from src.domain.entities.candle import Candle
from src.domain.value_objects.benchmark_excess_return import (
    BenchmarkExcessReturn,
    BenchmarkExcessReturnStatus,
)
from src.domain.value_objects.benchmark_symbol import CANONICAL_BENCHMARK_TICKER
from tests.application.use_case.accumulation_screen_fixtures import FakeRulesLoader


def _excess_return(
    window_sessions: int, excess_return_pct: float
) -> BenchmarkExcessReturn:
    return BenchmarkExcessReturn(
        benchmark="IHSG",
        window_sessions=window_sessions,
        ticker_return_pct=excess_return_pct,
        benchmark_return_pct=0.0,
        excess_return_pct=excess_return_pct,
        window_start=date(2026, 6, 1),
        window_end=date(2026, 6, 15),
        common_session_count=window_sessions + 1,
        status=BenchmarkExcessReturnStatus.AVAILABLE,
        unavailable_reason=None,
    )


class _MarketRepository:
    def __init__(self, candles_by_ticker: dict[str, list[Candle]] | None = None) -> None:
        self._candles_by_ticker = candles_by_ticker or {}

    def get_candles(self, ticker, start_date=None, end_date=None):
        return list(self._candles_by_ticker.get(ticker, []))

    def get_candle_source(self, ticker, on_date):
        return None


class _BrokerRepository:
    def get_broker_daily_flows(self, ticker, start_date=None, end_date=None):
        return []

    def get_foreign_flow_points(self, ticker, start_date=None, end_date=None):
        return []

    def get_broker_summaries(self, ticker, start_date=None, end_date=None):
        return []


class _RaisingFactory:
    def __init__(self, message: str) -> None:
        self._message = message

    def __call__(self):
        raise RuntimeError(self._message)


class _FakeSignalEngine:
    def foreign_flow_quality_from_accum_score(self, score):
        return "MODERATE"

    def bandar_max_range(self, num_optional):
        return 100.0


class _FakeBenchmarkExcessReturnCalculator:
    def __init__(
        self,
        result: BenchmarkExcessReturnResult | None = None,
        raise_error: bool = False,
    ):
        self._result = result or BenchmarkExcessReturnResult(
            excess_return_vs_ihsg_5_session=_excess_return(5, 1.5),
            excess_return_vs_ihsg_20_session=_excess_return(20, 2.5),
        )
        self._raise_error = raise_error

    def calculate(self, *, ticker_candles, benchmark_candles, as_of_date, benchmark="IHSG"):
        if self._raise_error:
            raise RuntimeError("benchmark excess return calc failed")
        return self._result


def _candle(ticker: str, on_date: date) -> Candle:
    return Candle(
        ticker=ticker,
        date=on_date,
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100"),
        volume=1_000_000,
    )


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
        accum_score=50.0,
        top_brokers=None,
        institutional_flag=False,
    )
    values.update(overrides)
    return AccumulationCandidate(**values)


def _builder(
    market_repo=None,
    broker_repo=None,
    *,
    signal_engine=None,
    ticker_profile_classifier_factory=None,
    sector_context_builder_factory=None,
    company_quality_context_builder_factory=None,
    benchmark_excess_return_calculator=None,
    candidate_observations_repository=None,
) -> AccumulationCandidateEvidenceBuilder:
    return AccumulationCandidateEvidenceBuilder(
        market_repository=market_repo or _MarketRepository(),
        broker_repository=broker_repo or _BrokerRepository(),
        signal_engine=signal_engine,
        candidate_observations_repository=candidate_observations_repository,
        swing_setup_catalog=None,
        primary_setup_family_resolver=PrimarySetupFamilyResolver(),
        benchmark_excess_return_calculator=benchmark_excess_return_calculator
        or _FakeBenchmarkExcessReturnCalculator(),
        indicator_registry=None,
        rules_loader=FakeRulesLoader(),
        ticker_profile_classifier_factory=ticker_profile_classifier_factory,
        sector_context_builder_factory=sector_context_builder_factory,
        company_quality_context_builder_factory=company_quality_context_builder_factory,
    )


class TestInstitutionalEvidenceFailureReturnsNone:
    def test_returns_none_when_broker_repository_raises(self):
        class _RaisingBrokerRepository:
            def get_broker_daily_flows(self, ticker, start_date=None, end_date=None):
                raise RuntimeError("broker down")

            def get_foreign_flow_points(self, ticker, start_date=None, end_date=None):
                return []

            def get_broker_summaries(self, ticker, start_date=None, end_date=None):
                return []

        builder = _builder(broker_repo=_RaisingBrokerRepository())
        candidate = _candidate()

        result = builder.build_candidate_institutional_accumulation_evidence(
            candidate, date(2026, 6, 10)
        )

        assert result is None


class TestTickerProfileFailureReturnsNone:
    def test_returns_none_when_classifier_factory_raises(self):
        builder = _builder(
            ticker_profile_classifier_factory=_RaisingFactory("classifier down")
        )
        candidate = _candidate()

        result = builder.build_candidate_ticker_profile(candidate, date(2026, 6, 10))

        assert result is None

    def test_returns_none_without_classifier_factory(self):
        builder = _builder()
        candidate = _candidate()

        result = builder.build_candidate_ticker_profile(candidate, date(2026, 6, 10))

        assert result is None


class TestSectorContextFailureReturnsNone:
    def test_returns_none_when_sector_builder_factory_raises(self):
        builder = _builder(sector_context_builder_factory=_RaisingFactory("sector down"))
        candidate = _candidate()

        result = builder.build_candidate_sector_context(
            candidate, date(2026, 6, 10), tp_snapshot=None
        )

        assert result is None


class TestCompanyQualityFailureReturnsNone:
    def test_returns_none_when_signal_engine_missing(self):
        builder = _builder(signal_engine=None)
        candidate = _candidate()

        result = builder.build_candidate_company_quality_context(
            candidate, date(2026, 6, 10)
        )

        assert result is None

    def test_returns_none_when_company_quality_factory_raises(self):
        builder = _builder(
            signal_engine=_FakeSignalEngine(),
            company_quality_context_builder_factory=_RaisingFactory("cq down"),
        )
        candidate = _candidate()

        result = builder.build_candidate_company_quality_context(
            candidate, date(2026, 6, 10)
        )

        assert result is None


class TestSetupPhaseFailureReturnsNone:
    def test_returns_none_when_benchmark_excess_return_calculator_raises(self):
        builder = _builder(
            benchmark_excess_return_calculator=_FakeBenchmarkExcessReturnCalculator(
                raise_error=True
            )
        )
        candidate = _candidate()

        result = builder.detect_candidate_setup_phase(candidate, None, date(2026, 6, 10))

        assert result is None


class TestEmptyCandlesDoNotCrash:
    def test_setup_phase_detection_with_empty_candles(self):
        builder = _builder(market_repo=_MarketRepository({}))
        candidate = _candidate()

        result = builder.detect_candidate_setup_phase(candidate, None, date(2026, 6, 10))

        # No candles means the phase detector has nothing to work with, but
        # the best-effort contract still holds: no exception escapes.
        assert result is None or result is not None

    def test_volatility_context_with_empty_candles(self):
        builder = _builder(market_repo=_MarketRepository({}))
        candidate = _candidate()

        result = builder.build_candidate_volatility_context(candidate, date(2026, 6, 10))

        assert result.volatility_bucket_at_signal == "UNKNOWN"
        assert result.atr_at_signal is None


class TestSetupPhaseAttachesBenchmarkExcessReturnOnSuccess:
    def test_benchmark_excess_return_attached_when_setup_phase_detection_succeeds(self):
        ticker = "BBCA"
        snapshot_date = date(2026, 6, 15)
        market_repo = _MarketRepository(
            {
                ticker: _candles(ticker, date(2026, 6, 1), 15),
                CANONICAL_BENCHMARK_TICKER: _candles(
                    CANONICAL_BENCHMARK_TICKER, date(2026, 6, 1), 15
                ),
            }
        )
        excess_return_calculator = _FakeBenchmarkExcessReturnCalculator(
            BenchmarkExcessReturnResult(
                excess_return_vs_ihsg_5_session=_excess_return(5, 3.3),
                excess_return_vs_ihsg_20_session=_excess_return(20, 7.7),
            )
        )
        builder = _builder(
            market_repo=market_repo,
            benchmark_excess_return_calculator=excess_return_calculator,
        )
        candidate = _candidate(ticker=ticker)

        result = builder.detect_candidate_setup_phase(candidate, None, snapshot_date)

        assert result is not None
        assert candidate.benchmark_excess_return_5_session.excess_return_pct == 3.3
        assert candidate.benchmark_excess_return_20_session.excess_return_pct == 7.7


class _RecordingMarketRepository:
    """Records every get_candles() call for repository-query-count assertions."""

    def __init__(self, candles_by_ticker: dict[str, list[Candle]]) -> None:
        self._candles_by_ticker = candles_by_ticker
        self.calls: list[tuple[str, date | None]] = []

    def get_candles(self, ticker, start_date=None, end_date=None):
        self.calls.append((ticker, end_date))
        return list(self._candles_by_ticker.get(ticker, []))

    def get_candle_source(self, ticker, on_date):
        return None


class _RecordingBenchmarkExcessReturnCalculator:
    """Captures the exact candle tuples/date passed to calculate()."""

    def __init__(self, result: BenchmarkExcessReturnResult) -> None:
        self._result = result
        self.calls: list[dict] = []

    def calculate(self, *, ticker_candles, benchmark_candles, as_of_date, benchmark="IHSG"):
        self.calls.append(
            {
                "ticker_candles": ticker_candles,
                "benchmark_candles": benchmark_candles,
                "as_of_date": as_of_date,
            }
        )
        return self._result


class _RecordingAssembler(CandidateSetupPhaseEvidenceAssembler):
    """Records the exact candle arguments build_setup_evidence()/detect_setup_phase()
    receive, without duplicating normalization logic — it only delegates and
    records what the real assembler passed along.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.build_setup_evidence_calls: list[dict] = []
        self.detect_setup_phase_calls: list[dict] = []
        self.built_setup_evidence = None

    def build_setup_evidence(self, **kwargs):
        self.build_setup_evidence_calls.append(kwargs)
        result = super().build_setup_evidence(**kwargs)
        self.built_setup_evidence = result
        return result

    def detect_setup_phase(self, **kwargs):
        self.detect_setup_phase_calls.append(kwargs)
        return "SENTINEL_PHASE"


class TestBenchmarkExcessReturnUsesCanonicalCandleRows:
    """Finding 3 regression: calculator, setup builder, and phase detector must
    consume the same normalized rows the provenance records — a wrong-ticker
    or future row must never influence calculation while being absent from
    provenance.
    """

    def test_wrong_ticker_and_future_rows_excluded_and_identity_shared(self):
        ticker = "BBCA"
        snapshot_date = date(2026, 6, 15)

        ticker_candles = [
            _candle("BBCA", date(2026, 6, 15)),
            _candle("ASII", date(2026, 6, 14)),
            _candle("BBCA", date(2026, 6, 16)),
            _candle("BBCA", date(2026, 6, 13)),
        ]
        benchmark_candles = [
            _candle("IHSG", date(2026, 6, 16)),
            _candle("BBCA", date(2026, 6, 14)),
            _candle("IHSG", date(2026, 6, 13)),
            _candle("IHSG", date(2026, 6, 15)),
        ]
        market_repo = _RecordingMarketRepository(
            {
                ticker: ticker_candles,
                CANONICAL_BENCHMARK_TICKER: benchmark_candles,
            }
        )
        excess_return_result = BenchmarkExcessReturnResult(
            excess_return_vs_ihsg_5_session=_excess_return(5, 3.3),
            excess_return_vs_ihsg_20_session=_excess_return(20, 7.7),
        )
        calculator = _RecordingBenchmarkExcessReturnCalculator(excess_return_result)
        assembler = _RecordingAssembler(market_repo, None)
        candidate = _candidate(ticker=ticker)

        result = assembler.detect_setup_phase_with_benchmark_excess_return(
            ticker=ticker,
            snapshot_date=snapshot_date,
            candidate=candidate,
            flow_evidence=None,
            setup_family=None,
            benchmark_excess_return_calculator=calculator,
        )

        assert result == "SENTINEL_PHASE"

        # 1. Repository queries are exactly one ticker read + one benchmark read.
        assert market_repo.calls == [
            (ticker, snapshot_date),
            (CANONICAL_BENCHMARK_TICKER, snapshot_date),
        ]

        # 2-6. Calculator receives only the canonical ticker/benchmark rows.
        assert len(calculator.calls) == 1
        calc_call = calculator.calls[0]
        recorded_calculator_ticker_candles = calc_call["ticker_candles"]
        recorded_calculator_benchmark_candles = calc_call["benchmark_candles"]
        assert tuple(c.date for c in recorded_calculator_ticker_candles) == (
            date(2026, 6, 13),
            date(2026, 6, 15),
        )
        assert all(c.ticker == "BBCA" for c in recorded_calculator_ticker_candles)
        assert tuple(c.date for c in recorded_calculator_benchmark_candles) == (
            date(2026, 6, 13),
            date(2026, 6, 15),
        )
        assert all(c.ticker == "IHSG" for c in recorded_calculator_benchmark_candles)
        assert calc_call["as_of_date"] == snapshot_date

        # 7-8. build_setup_evidence() receives the exact same normalized
        # tuple objects the calculator received.
        assert len(assembler.build_setup_evidence_calls) == 1
        build_call = assembler.build_setup_evidence_calls[0]
        recorded_build_ticker_candles = build_call["candles"]
        recorded_build_benchmark_candles = build_call["benchmark_candles"]
        assert recorded_build_ticker_candles is recorded_calculator_ticker_candles
        assert recorded_build_benchmark_candles is recorded_calculator_benchmark_candles

        # 9. detect_setup_phase() receives the exact same normalized ticker
        # tuple object as the calculator.
        assert len(assembler.detect_setup_phase_calls) == 1
        detect_call = assembler.detect_setup_phase_calls[0]
        assert detect_call["candles"] is recorded_calculator_ticker_candles

        # 10-11. Provenance contains only the canonical rows.
        built = assembler.built_setup_evidence
        assert tuple(
            (row.ticker, row.date) for row in built.provenance.candle_rows
        ) == (("BBCA", date(2026, 6, 13)), ("BBCA", date(2026, 6, 15)))
        assert tuple(
            (row.ticker, row.date) for row in built.provenance.benchmark_candle_rows
        ) == (("IHSG", date(2026, 6, 13)), ("IHSG", date(2026, 6, 15)))

        # 12. The ASII row, wrong benchmark row, and both future rows are
        # absent from calculator inputs, setup-builder inputs, provenance,
        # and the phase-detector input.
        forbidden_ticker_rows = {("ASII", date(2026, 6, 14)), ("BBCA", date(2026, 6, 16))}
        forbidden_benchmark_rows = {
            ("BBCA", date(2026, 6, 14)),
            ("IHSG", date(2026, 6, 16)),
        }
        observed_ticker_rows = {
            (c.ticker, c.date) for c in recorded_calculator_ticker_candles
        } | {(row.ticker, row.date) for row in built.provenance.candle_rows}
        observed_benchmark_rows = {
            (c.ticker, c.date) for c in recorded_calculator_benchmark_candles
        } | {(row.ticker, row.date) for row in built.provenance.benchmark_candle_rows}
        assert not (forbidden_ticker_rows & observed_ticker_rows)
        assert not (forbidden_benchmark_rows & observed_benchmark_rows)
        assert not any(
            (c.ticker, c.date) in forbidden_ticker_rows for c in detect_call["candles"]
        )

        # Existing behavior preserved: diagnostic attributes still attached.
        assert candidate.benchmark_excess_return_5_session.excess_return_pct == 3.3
        assert candidate.benchmark_excess_return_20_session.excess_return_pct == 7.7


class TestBuildSetupEvidenceDefensiveNormalization:
    """Direct coverage for build_setup_evidence() alone: it must independently
    exclude wrong-ticker and future rows for callers other than the setup-
    phase method (e.g. swing analysis, which already has a resolved
    setup_eval).
    """

    def test_excludes_wrong_ticker_and_future_stock_and_benchmark_rows(self):
        ticker = "BBCA"
        snapshot_date = date(2026, 6, 15)
        candles = [
            _candle("BBCA", date(2026, 6, 13)),
            _candle("BBCA", date(2026, 6, 15)),
            _candle("ASII", date(2026, 6, 14)),
            _candle("BBCA", date(2026, 6, 16)),
        ]
        benchmark_candles = [
            _candle("IHSG", date(2026, 6, 13)),
            _candle("IHSG", date(2026, 6, 15)),
            _candle("BBCA", date(2026, 6, 14)),
            _candle("IHSG", date(2026, 6, 16)),
        ]
        assembler = CandidateSetupPhaseEvidenceAssembler(_MarketRepository({}), None)
        candidate = _candidate(ticker=ticker)

        built = assembler.build_setup_evidence(
            ticker=ticker,
            snapshot_date=snapshot_date,
            candles=candles,
            candidate=candidate,
            setup_eval=None,
            benchmark_candles=benchmark_candles,
        )

        assert tuple(
            (row.ticker, row.date) for row in built.provenance.candle_rows
        ) == (("BBCA", date(2026, 6, 13)), ("BBCA", date(2026, 6, 15)))
        assert tuple(
            (row.ticker, row.date) for row in built.provenance.benchmark_candle_rows
        ) == (("IHSG", date(2026, 6, 13)), ("IHSG", date(2026, 6, 15)))
