"""Tests for the risk compare workflow use case."""

from datetime import date
from decimal import Decimal

import pytest

from src.application.dto.assess_risk import AssessRiskResponse
from src.application.use_case.run_risk_compare_use_case import (
    RunRiskCompareRequest,
    RunRiskCompareUseCase,
)
from src.domain.entities.candle import Candle
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_assessment import RiskAssessment


class FakeRiskEngine:
    def __init__(
        self,
        responses: dict[str, AssessRiskResponse],
        errors: dict[str, Exception] | None = None,
    ):
        self.responses = responses
        self.errors = errors or {}
        self.assess_requests = []

    def assess_request(self, request):
        self.assess_requests.append(request)
        if request.ticker in self.errors:
            raise self.errors[request.ticker]
        return self.responses[request.ticker]


class FakeMarketRepository:
    def __init__(self, candles: dict[str, list[Candle]]):
        self.candles = candles

    def get_candles(self, ticker: str):
        return self.candles.get(ticker, [])


def _response(
    ticker: str, sma: str, rsi: str, gate_triggered=None, confidence=None
) -> AssessRiskResponse:
    assessment = RiskAssessment(
        rationale=(),
        snapshot_date=date(2026, 7, 10),
        indicators=IndicatorSnapshot(
            date=date(2026, 7, 10),
            sma=Decimal(sma),
            ema=Decimal(sma),
            rsi=Decimal(rsi),
        ),
        gate_triggered=gate_triggered,
        gate_confidence=confidence,
    )
    return AssessRiskResponse(
        ticker=ticker, assessment=assessment, sma_period=20, ema_period=20, rsi_period=14
    )


def _candle(ticker: str, close: str) -> Candle:
    return Candle(
        ticker=ticker,
        date=date(2026, 7, 10),
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=1000,
    )


def test_rejects_fewer_than_two_tickers():
    engine = FakeRiskEngine(responses={})
    repository = FakeMarketRepository(candles={})
    use_case = RunRiskCompareUseCase(risk_engine=engine, market_repository=repository)

    with pytest.raises(ValueError, match="Provide at least 2 tickers to compare."):
        use_case.execute(
            RunRiskCompareRequest(tickers=["BBCA"], sma_period=20, rsi_period=14, days=365)
        )


def test_returns_one_row_per_ticker():
    engine = FakeRiskEngine(
        responses={
            "BBCA": _response("BBCA", "1000", "55"),
            "BBRI": _response("BBRI", "2000", "60"),
        }
    )
    repository = FakeMarketRepository(
        candles={"BBCA": [_candle("BBCA", "1050")], "BBRI": [_candle("BBRI", "2050")]}
    )
    use_case = RunRiskCompareUseCase(risk_engine=engine, market_repository=repository)

    result = use_case.execute(
        RunRiskCompareRequest(tickers=["BBCA", "BBRI"], sma_period=20, rsi_period=14, days=365)
    )

    assert len(result.rows) == 2
    assert [row.ticker for row in result.rows] == ["BBCA", "BBRI"]


def test_failed_ticker_becomes_has_data_false_not_exception():
    engine = FakeRiskEngine(
        responses={"BBCA": _response("BBCA", "1000", "55")},
        errors={"BBRI": ValueError("no cached data")},
    )
    repository = FakeMarketRepository(candles={"BBCA": [_candle("BBCA", "1050")]})
    use_case = RunRiskCompareUseCase(risk_engine=engine, market_repository=repository)

    result = use_case.execute(
        RunRiskCompareRequest(tickers=["BBCA", "BBRI"], sma_period=20, rsi_period=14, days=365)
    )

    ok_row, failed_row = result.rows
    assert ok_row.has_data is True
    assert failed_row.ticker == "BBRI"
    assert failed_row.has_data is False
    assert failed_row.close is None
    assert failed_row.sma is None
    assert failed_row.risk_level_name is None


def test_latest_close_comes_from_market_repository_candles():
    engine = FakeRiskEngine(
        responses={
            "BBCA": _response("BBCA", "1000", "55"),
            "BBRI": _response("BBRI", "2000", "60"),
        }
    )
    repository = FakeMarketRepository(
        candles={
            "BBCA": [_candle("BBCA", "1040"), _candle("BBCA", "1060")],
            "BBRI": [_candle("BBRI", "2100")],
        }
    )
    use_case = RunRiskCompareUseCase(risk_engine=engine, market_repository=repository)

    result = use_case.execute(
        RunRiskCompareRequest(tickers=["BBCA", "BBRI"], sma_period=20, rsi_period=14, days=365)
    )

    assert result.rows[0].close == Decimal("1060")
    assert result.rows[1].close == Decimal("2100")


def test_sma_rsi_risk_confidence_values_are_mapped_from_risk_response():
    engine = FakeRiskEngine(
        responses={
            "BBCA": _response("BBCA", "1000", "55", gate_triggered="LiquidityGate", confidence=90),
            "BBRI": _response("BBRI", "2000", "60"),
        }
    )
    repository = FakeMarketRepository(
        candles={"BBCA": [_candle("BBCA", "1050")], "BBRI": [_candle("BBRI", "2050")]}
    )
    use_case = RunRiskCompareUseCase(risk_engine=engine, market_repository=repository)

    result = use_case.execute(
        RunRiskCompareRequest(tickers=["BBCA", "BBRI"], sma_period=20, rsi_period=14, days=365)
    )

    bbca_row, bbri_row = result.rows
    assert bbca_row.sma == Decimal("1000")
    assert bbca_row.rsi == Decimal("55")
    assert bbca_row.risk_level_name == "BLOCKED"
    assert bbca_row.confidence == 90

    assert bbri_row.risk_level_name == "OPEN"
    assert bbri_row.confidence == 0
