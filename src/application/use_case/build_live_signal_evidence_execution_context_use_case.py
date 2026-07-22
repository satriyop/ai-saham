"""
BuildLiveSignalEvidenceExecutionContextUseCase — the single application-layer
authority for resolving the live signal-evidence execution context shared by
`saham screen accum` and `saham screen compare`.

Owns effective-session resolution and a gap-free IHSG availability coverage
window (widest proven-session suffix ending at the latest completed session,
capped at a few sessions). Both live screen workflows must resolve this
identically — see ADR-041.

Layer: Application
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from src.application.dto.signal_evidence_execution_context import (
    SignalEvidenceExecutionContext,
)
from src.application.services.availability_calendar_window import (
    resolve_gap_free_availability_calendar_start,
)
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSessionResolver,
)
from src.application.services.signal_evidence_execution_context_builder import (
    SignalEvidenceExecutionContextBuilder,
)

if TYPE_CHECKING:
    from src.domain.ports.market_data_repository import MarketDataRepository

_LIVE_SCREEN_CALENDAR_MAX_SESSIONS = 5
_LIVE_SCREEN_CALENDAR_PROBE_DAYS = 45


class BuildLiveSignalEvidenceExecutionContextUseCase:
    def __init__(
        self,
        *,
        session_resolver: EffectiveMarketSessionResolver,
        context_builder: SignalEvidenceExecutionContextBuilder,
        market_data_repository: "MarketDataRepository",
    ) -> None:
        self._session_resolver = session_resolver
        self._context_builder = context_builder
        self._market = market_data_repository

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
        coverage_start = self._resolve_availability_calendar_start(coverage_end)

        return self._context_builder.build(
            effective_session=effective_session,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
        )

    def _resolve_availability_calendar_start(self, coverage_end: date) -> date:
        probe_start = coverage_end - timedelta(days=_LIVE_SCREEN_CALENDAR_PROBE_DAYS)
        candles = self._market.get_candles(
            "IHSG",
            start_date=probe_start,
            end_date=coverage_end,
        )
        sessions = tuple(sorted({candle.date for candle in candles}))
        return resolve_gap_free_availability_calendar_start(
            sessions=sessions,
            coverage_end=coverage_end,
            max_sessions=_LIVE_SCREEN_CALENDAR_MAX_SESSIONS,
        )
