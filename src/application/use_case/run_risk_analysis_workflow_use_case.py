"""
RunRiskAnalysisWorkflow use case - orchestrates the `saham analyze risk` command.

Coordinates optional sentiment enrichment, the deterministic risk assessment,
and an optional risk trend lookback into a single structured result. This is
the workflow policy previously embedded in the `analyze risk` CLI command.

Layer: Application
Depends on: AssessRiskRequest/Response DTOs, an injected risk assessor, and an
optional injected sentiment fetcher callable.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from src.application.dto.assess_risk import AssessRiskRequest

__all__ = [
    "RunRiskAnalysisWorkflowRequest",
    "RunRiskAnalysisWorkflowResult",
    "RunRiskAnalysisWorkflowUseCase",
]


class RiskAnalysisAssessor(Protocol):
    """Port-shaped dependency: anything that can assess a risk request and its trend."""

    def assess_request(self, request: AssessRiskRequest) -> Any: ...

    def assess_trend(self, request: AssessRiskRequest, days: int) -> Any: ...


class SentimentFetcher(Protocol):
    """Narrow callable seam for fetching a sentiment snapshot for a ticker."""

    def __call__(self, ticker: str, provider_name: str, no_ai: bool) -> Any: ...


@dataclass(frozen=True)
class RunRiskAnalysisWorkflowRequest:
    ticker: str
    sma_period: int
    ema_period: int
    rsi_period: int
    rules_file: Path | None
    include_sentiment: bool
    sentiment_provider_name: str
    no_ai_sentiment: bool
    trend_days: int


@dataclass(frozen=True)
class RunRiskAnalysisWorkflowResult:
    ticker: str
    response: Any
    sentiment_snapshot: Any | None
    trend_response: Any | None
    warnings: tuple[str, ...] = ()

    def to_json_dict(self) -> dict:
        """Preserve the `risk_assessment` artifact schema exactly."""
        assessment = self.response.assessment
        snapshot = assessment.indicators
        return {
            "schema_version": 1,
            "artifact_type": "risk_assessment",
            "ticker": self.response.ticker,
            "risk_status": assessment.risk_level_name,
            "status": assessment.risk_level_name,
            "verdict": assessment.risk_level_name,
            "gate_triggered": assessment.gate_triggered,
            "gate_confidence": assessment.gate_confidence,
            "rationale": assessment.rationale_list,
            "indicators": {
                f"sma_{self.response.sma_period}": float(snapshot.sma),
                f"ema_{self.response.ema_period}": float(snapshot.ema),
                f"rsi_{self.response.rsi_period}": float(snapshot.rsi),
            },
        }


class RunRiskAnalysisWorkflowUseCase:
    """Orchestrates sentiment enrichment, risk assessment, and trend lookback."""

    def __init__(
        self,
        risk_engine: RiskAnalysisAssessor,
        sentiment_fetcher: SentimentFetcher | None = None,
    ) -> None:
        self._risk_engine = risk_engine
        self._sentiment_fetcher = sentiment_fetcher

    def execute(self, request: RunRiskAnalysisWorkflowRequest) -> RunRiskAnalysisWorkflowResult:
        warnings: list[str] = []

        sentiment_snapshot = None
        if request.include_sentiment and self._sentiment_fetcher is not None:
            try:
                sentiment_snapshot = self._sentiment_fetcher(
                    request.ticker,
                    request.sentiment_provider_name,
                    request.no_ai_sentiment,
                )
            except Exception as exc:
                warnings.append(f"Warning: Could not fetch sentiment: {exc}")

        assess_request = AssessRiskRequest(
            ticker=request.ticker,
            sma_period=request.sma_period,
            ema_period=request.ema_period,
            rsi_period=request.rsi_period,
            rules_file=request.rules_file,
            sentiment=sentiment_snapshot,
        )

        response = self._risk_engine.assess_request(assess_request)

        trend_response = None
        if request.trend_days > 0 and not request.rules_file:
            try:
                trend_response = self._risk_engine.assess_trend(
                    assess_request, days=request.trend_days
                )
            except Exception as exc:
                warnings.append(f"Trend unavailable: {exc}")

        return RunRiskAnalysisWorkflowResult(
            ticker=request.ticker,
            response=response,
            sentiment_snapshot=sentiment_snapshot,
            trend_response=trend_response,
            warnings=tuple(warnings),
        )
