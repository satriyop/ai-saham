from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)

if TYPE_CHECKING:
    from src.application.use_case.assess_source_availability_use_case import (
        AssessSourceAvailabilityUseCase,
    )


@dataclass(frozen=True)
class SignalEvidenceExecutionContext:
    effective_session: EffectiveMarketSession
    source_availability_use_case: "AssessSourceAvailabilityUseCase | None"
