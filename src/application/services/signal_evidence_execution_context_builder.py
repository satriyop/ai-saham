from datetime import date
from typing import Callable

from src.application.dto.signal_evidence_execution_context import (
    SignalEvidenceExecutionContext,
)
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from src.application.use_case.assess_source_availability_use_case import (
    AssessSourceAvailabilityUseCase,
)
from src.domain.services.trading_session_calendar import KnownTradingSessionCalendar


class SignalEvidenceExecutionContextBuilder:
    def __init__(
        self,
        trading_session_calendar_loader: (
            Callable[[date, date], KnownTradingSessionCalendar | None] | None
        ),
    ) -> None:
        self._trading_session_calendar_loader = trading_session_calendar_loader

    def build(
        self,
        *,
        effective_session: EffectiveMarketSession,
        coverage_start: date,
        coverage_end: date,
    ) -> SignalEvidenceExecutionContext:
        if coverage_start > coverage_end:
            raise ValueError("coverage_start cannot be after coverage_end")

        use_case = None
        if self._trading_session_calendar_loader is not None:
            try:
                calendar = self._trading_session_calendar_loader(coverage_start, coverage_end)
                if calendar is not None:
                    use_case = AssessSourceAvailabilityUseCase(calendar=calendar)
            except (ValueError, TypeError):
                raise
            except Exception:
                use_case = None

        return SignalEvidenceExecutionContext(
            effective_session=effective_session,
            source_availability_use_case=use_case,
        )
