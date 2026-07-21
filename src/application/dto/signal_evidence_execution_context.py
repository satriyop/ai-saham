from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from src.domain.value_objects.signal_artifact_identity import (
    SemanticCompatibilityId,
)

if TYPE_CHECKING:
    from src.application.use_case.assess_source_availability_use_case import (
        AssessSourceAvailabilityUseCase,
    )


@dataclass(frozen=True)
class SignalEvidenceExecutionContext:
    effective_session: EffectiveMarketSession
    source_availability_use_case: "AssessSourceAvailabilityUseCase | None"
    # Lean observation identity (DQ-003 Slice A). Only the canonical capture
    # path (backfill → record → persist) stamps these; interactive/read-only
    # paths leave them None and never persist, so None is acceptable there.
    # The persister fail-closes on a canonical write with a None
    # semantic_compatibility_id and rejects any observation_contract other than
    # "accumulation-discovery".
    observation_contract: str | None = None
    semantic_compatibility_id: SemanticCompatibilityId | None = None
