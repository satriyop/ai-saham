"""
RunRiskCompare use case - orchestrates the `saham analyze compare` command.

Assesses each ticker independently so a single failing ticker degrades to a
no-data row instead of aborting the whole comparison. This is the workflow
policy previously embedded in the `analyze compare` CLI command.

Layer: Application
Depends on: AssessRiskRequest DTO, an injected risk assessor, and an injected
market data repository port.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from src.application.dto.assess_risk import AssessRiskRequest

__all__ = [
    "RunRiskCompareRequest",
    "RiskCompareRow",
    "RunRiskCompareResult",
    "RunRiskCompareUseCase",
]


class CompareRiskAssessor(Protocol):
    """Port-shaped dependency: anything that can assess a risk request."""

    def assess_request(self, request: AssessRiskRequest) -> Any: ...


class CompareMarketRepository(Protocol):
    """Port-shaped dependency: anything that can return cached candles."""

    def get_candles(self, ticker: str) -> list[Any]: ...


@dataclass(frozen=True)
class RunRiskCompareRequest:
    tickers: list[str]
    sma_period: int
    rsi_period: int
    days: int


@dataclass(frozen=True)
class RiskCompareRow:
    ticker: str
    close: Decimal | None
    sma: Decimal | None
    rsi: Decimal | None
    risk_level_name: str | None
    confidence: int | None
    has_data: bool


@dataclass(frozen=True)
class RunRiskCompareResult:
    rows: tuple[RiskCompareRow, ...]


class RunRiskCompareUseCase:
    """Assesses each requested ticker independently for side-by-side comparison."""

    def __init__(
        self,
        risk_engine: CompareRiskAssessor,
        market_repository: CompareMarketRepository,
    ) -> None:
        self._risk_engine = risk_engine
        self._market_repository = market_repository

    def execute(self, request: RunRiskCompareRequest) -> RunRiskCompareResult:
        if len(request.tickers) < 2:
            raise ValueError("Provide at least 2 tickers to compare.")

        rows: list[RiskCompareRow] = []
        for ticker in request.tickers:
            rows.append(self._assess_one(ticker, request))
        return RunRiskCompareResult(rows=tuple(rows))

    def _assess_one(self, ticker: str, request: RunRiskCompareRequest) -> RiskCompareRow:
        try:
            assess_request = AssessRiskRequest(
                ticker=ticker,
                sma_period=request.sma_period,
                ema_period=request.sma_period,
                rsi_period=request.rsi_period,
            )
            response = self._risk_engine.assess_request(assess_request)
            assessment = response.assessment
            snapshot = assessment.indicators
            candles = self._market_repository.get_candles(ticker.upper())
            close = candles[-1].close if candles else None
            return RiskCompareRow(
                ticker=ticker.upper(),
                close=close,
                sma=snapshot.sma,
                rsi=snapshot.rsi,
                risk_level_name=assessment.risk_level_name,
                confidence=assessment.confidence,
                has_data=True,
            )
        except Exception:
            return RiskCompareRow(
                ticker=ticker.upper(),
                close=None,
                sma=None,
                rsi=None,
                risk_level_name=None,
                confidence=None,
                has_data=False,
            )
