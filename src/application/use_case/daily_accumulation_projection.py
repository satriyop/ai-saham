"""
Projects canonical AccumulationScreenUseCase output for the `today` briefing.

This is a read-only projection, not a decision engine: it does not sort,
rank, or invent actions. It surfaces fields already produced by the
accumulation screen (SignalEngine, RiskEngine, TradeSetup) verbatim.

Layer: Application
AI usage: None
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.application.dto.accumulation_screen import AccumulationCandidate

_BLOCKED_ACTIONS = {"BLOCKED_EXECUTION", "BLOCKED_STRUCTURAL"}


@dataclass(frozen=True)
class DailyAccumulationCandidate:
    ticker: str
    flow_score: float
    setup_phase: str | None
    signal_score: int | None
    coverage_score: float | None
    risk_status: str
    action: str | None


@dataclass(frozen=True)
class DailyAccumulationSummary:
    checked: int
    data_ready: int
    flow_candidates: int
    enter_count: int
    watch_count: int
    blocked_count: int
    unclassified_count: int


@dataclass(frozen=True)
class DailyAccumulationProjection:
    summary: DailyAccumulationSummary
    candidates: list[DailyAccumulationCandidate]
    warnings: tuple[str, ...] = field(default_factory=tuple)


class DailyAccumulationProjector:
    """Projects AccumulationCandidate list into daily-briefing display DTOs."""

    def project(
        self,
        *,
        candidates: list[AccumulationCandidate],
        checked: int,
        data_ready: int,
    ) -> DailyAccumulationProjection:
        projected = [self._project_candidate(candidate) for candidate in candidates]

        enter_count = sum(1 for c in projected if c.action == "ENTER")
        watch_count = sum(1 for c in projected if c.action == "WATCH")
        blocked_count = sum(1 for c in projected if c.action in _BLOCKED_ACTIONS)
        unclassified_count = sum(1 for c in projected if c.action is None)

        warnings: tuple[str, ...] = ()
        if unclassified_count > 0:
            warnings = (
                f"Canonical trade setup missing for {unclassified_count} "
                "accumulation candidate(s).",
            )

        summary = DailyAccumulationSummary(
            checked=checked,
            data_ready=data_ready,
            flow_candidates=len(projected),
            enter_count=enter_count,
            watch_count=watch_count,
            blocked_count=blocked_count,
            unclassified_count=unclassified_count,
        )

        return DailyAccumulationProjection(
            summary=summary,
            candidates=projected,
            warnings=warnings,
        )

    def _project_candidate(
        self, candidate: AccumulationCandidate
    ) -> DailyAccumulationCandidate:
        setup_phase = None
        if candidate.setup_phase is not None:
            phase = candidate.setup_phase.current_phase
            setup_phase = phase.value if hasattr(phase, "value") else str(phase)

        signal_score = None
        coverage_score = None
        if candidate.signal_assessment is not None:
            signal_score = candidate.signal_assessment.assessment.score
            coverage_score = candidate.signal_assessment.assessment.signal_authority_coverage

        if candidate.risk_assessment is None:
            risk_status = "UNKNOWN"
        elif candidate.risk_assessment.gate_triggered:
            risk_status = "BLOCK"
        else:
            risk_status = "OPEN"

        action = (
            candidate.trade_setup.action.value
            if candidate.trade_setup is not None
            else None
        )

        return DailyAccumulationCandidate(
            ticker=candidate.ticker,
            flow_score=candidate.foreign_flow_score,
            setup_phase=setup_phase,
            signal_score=signal_score,
            coverage_score=coverage_score,
            risk_status=risk_status,
            action=action,
        )
