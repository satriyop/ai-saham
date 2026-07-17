"""
BuildLiveSignalEvidenceExecutionContextUseCase — the single application-layer
authority for resolving the live signal-evidence execution context shared by
`saham screen accum` and `saham screen compare`.

Owns effective-session resolution and the 14-calendar-day availability
coverage window. Both live screen workflows must resolve this identically —
see ADR-041.

Layer: Application
"""

from __future__ import annotations

from datetime import datetime, timedelta

from src.application.dto.signal_evidence_execution_context import (
    SignalEvidenceExecutionContext,
)
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSessionResolver,
)
from src.application.services.signal_evidence_execution_context_builder import (
    SignalEvidenceExecutionContextBuilder,
)

_LIVE_SCREEN_CALENDAR_LOOKBACK_DAYS = 14


class BuildLiveSignalEvidenceExecutionContextUseCase:
    def __init__(
        self,
        *,
        session_resolver: EffectiveMarketSessionResolver,
        context_builder: SignalEvidenceExecutionContextBuilder,
    ) -> None:
        self._session_resolver = session_resolver
        self._context_builder = context_builder

    def execute(
        self,
        *,
        run_at: datetime,
    ) -> SignalEvidenceExecutionContext:
        effective_session = self._session_resolver.resolve(run_at=run_at)

        coverage_end = (
            effective_session.latest_completed_session
            or effective_session.analysis_as_of
            or effective_session.decision_at.date()
        )
        coverage_start = coverage_end - timedelta(
            days=_LIVE_SCREEN_CALENDAR_LOOKBACK_DAYS
        )

        return self._context_builder.build(
            effective_session=effective_session,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
        )
