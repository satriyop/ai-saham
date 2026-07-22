"""Typed verdict/evidence/diagnostics presenter for ticker research.

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.application.dto.swing_analysis import (
    SignalAssessmentStatus,
    SwingAnalysisWorkflowResponse,
)


def _enum_value(value):
    return value.value if hasattr(value, "value") else value


def _risk_name(risk_response) -> str | None:
    if risk_response is None:
        return None
    assessment = getattr(risk_response, "assessment", risk_response)
    return getattr(assessment, "risk_level_name", None)


def _flatten(value: Any, prefix: str = "") -> tuple[tuple[str, str], ...]:
    if isinstance(value, dict):
        rows = []
        for key, item in value.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            rows.extend(_flatten(item, name))
        return tuple(rows)
    if isinstance(value, (list, tuple)):
        if not value:
            return ((prefix, "—"),)
        return tuple((f"{prefix}[{index}]", str(item)) for index, item in enumerate(value))
    return ((prefix, "—" if value is None else str(value)),)


@dataclass(frozen=True)
class CanonicalVerdictView:
    signal_status: str
    unavailable_reason: str | None
    action: str | None
    signal_score: int | None
    signal_coverage: float | None
    risk: str | None
    regime: str | None


@dataclass(frozen=True)
class TickerResearchViewModel:
    source: SwingAnalysisWorkflowResponse
    ticker: str
    canonical: CanonicalVerdictView
    evidence: tuple[tuple[str, str], ...]
    diagnostics: tuple[tuple[str, str], ...]
    preview: tuple[tuple[str, str], ...]
    warnings: tuple[str, ...]


class TickerResearchPresenter:
    def present(self, response: SwingAnalysisWorkflowResponse) -> TickerResearchViewModel:
        verdict = response.verdict
        evidence = response.evidence
        diagnostics = response.diagnostics
        if verdict is None or evidence is None or diagnostics is None:
            raise ValueError("swing response omitted typed verdict/evidence/diagnostics")

        availability = verdict.signal_assessment_availability
        signal = verdict.signal_assessment
        available = availability.status is SignalAssessmentStatus.AVAILABLE
        trade_setup = verdict.trade_setup if available else None
        canonical = CanonicalVerdictView(
            signal_status=availability.status.value,
            unavailable_reason=(
                availability.unavailable_reason.value
                if availability.unavailable_reason is not None
                else None
            ),
            action=_enum_value(trade_setup.action) if trade_setup else None,
            signal_score=signal.assessment.score if signal else None,
            signal_coverage=(signal.assessment.signal_authority_coverage if signal else None),
            risk=_risk_name(verdict.risk_response),
            regime=_enum_value(verdict.market_regime.regime) if verdict.market_regime else None,
        )
        preview = _flatten(
            {
                "signal": (
                    verdict.market_context_signal_preview.assessment.score
                    if verdict.market_context_signal_preview
                    else None
                ),
                "risk": _risk_name(verdict.market_context_risk_preview),
                "action": (
                    _enum_value(verdict.market_context_trade_setup_preview.action)
                    if verdict.market_context_trade_setup_preview
                    else None
                ),
            }
        )
        return TickerResearchViewModel(
            source=response,
            ticker=response.ticker,
            canonical=canonical,
            evidence=_flatten(evidence.to_dict()),
            diagnostics=_flatten(diagnostics.to_dict()),
            preview=preview,
            warnings=tuple(response.warnings),
        )
