"""Resolve the screen-owned judgment consumed by ``saham plan swing``.

Layer: Application. Pure: no IO, engines, reconstruction, or fallback.
"""

from __future__ import annotations

from src.application.dto.accumulation_screen import AccumulationCandidateEvaluationResult
from src.application.dto.plan_swing import (
    ScreenJudgmentReference,
    ScreenJudgmentSource,
    ScreenJudgmentStatus,
    ScreenJudgmentUnavailableReason,
)


class ScreenJudgmentInvariantError(ValueError):
    """Raised when a present screen judgment has conflicting provenance."""


def resolve_screen_judgment(
    evaluation: AccumulationCandidateEvaluationResult | None,
    *,
    expected_ticker: str,
    expected_snapshot_date,
) -> ScreenJudgmentReference:
    """Return the exact screen judgment or a typed observable missing state."""

    ticker = expected_ticker.strip().upper()
    if not ticker:
        raise ScreenJudgmentInvariantError("expected ticker is required")

    if evaluation is None:
        return _unavailable(
            ticker,
            expected_snapshot_date,
            ScreenJudgmentUnavailableReason.NO_SCREEN_CANDIDATE,
        )

    candidate = evaluation.candidate
    if evaluation.analysis_date != expected_snapshot_date:
        raise ScreenJudgmentInvariantError(
            "screen evaluation date does not match the plan request: "
            f"{evaluation.analysis_date!s} != {expected_snapshot_date!s}"
        )
    if candidate.ticker != ticker:
        raise ScreenJudgmentInvariantError(
            f"screen candidate ticker does not match the plan request: "
            f"{candidate.ticker!r} != {ticker!r}"
        )

    trade_setup = candidate.trade_setup
    signal_assessment = candidate.signal_assessment
    risk_assessment = candidate.risk_assessment

    if trade_setup is None:
        if signal_assessment is None:
            reason = ScreenJudgmentUnavailableReason.NO_SCREEN_SIGNAL_ASSESSMENT
        elif risk_assessment is None:
            reason = ScreenJudgmentUnavailableReason.NO_SCREEN_RISK_ASSESSMENT
        else:
            reason = ScreenJudgmentUnavailableReason.NO_SCREEN_TRADE_SETUP
        return _unavailable(ticker, evaluation.analysis_date, reason)

    if signal_assessment is None:
        raise ScreenJudgmentInvariantError(
            "screen trade_setup is present without screen signal_assessment"
        )
    if risk_assessment is None:
        raise ScreenJudgmentInvariantError(
            "screen trade_setup is present without screen risk_assessment"
        )
    if trade_setup.ticker != ticker:
        raise ScreenJudgmentInvariantError(
            f"screen trade_setup ticker does not match the plan request: "
            f"{trade_setup.ticker!r} != {ticker!r}"
        )
    if trade_setup.snapshot_date != evaluation.analysis_date:
        raise ScreenJudgmentInvariantError(
            "screen trade_setup date does not match the screen evaluation: "
            f"{trade_setup.snapshot_date!s} != {evaluation.analysis_date!s}"
        )

    return ScreenJudgmentReference(
        status=ScreenJudgmentStatus.AVAILABLE,
        source=ScreenJudgmentSource.SCREEN_ACCUM,
        ticker=ticker,
        snapshot_date=evaluation.analysis_date,
        trade_setup=trade_setup,
    )


def _unavailable(
    ticker: str,
    snapshot_date,
    reason: ScreenJudgmentUnavailableReason,
) -> ScreenJudgmentReference:
    return ScreenJudgmentReference(
        status=ScreenJudgmentStatus.UNAVAILABLE,
        source=ScreenJudgmentSource.SCREEN_ACCUM,
        ticker=ticker,
        snapshot_date=snapshot_date,
        trade_setup=None,
        unavailable_reason=reason,
    )
