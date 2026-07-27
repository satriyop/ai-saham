"""Sector context evidence assembly, shared by evidence coordinators.

Layer: Application
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from src.application.services.candidate_evidence_data_loader import (
    SectorContextInputs,
)

if TYPE_CHECKING:
    from src.application.services.sector_context_evidence_builder import (
        SectorContextEvidenceBuilder,
    )
    from src.domain.value_objects.sector_context_evidence import SectorContextEvidence


class CandidateSectorContextEvidenceAssembler:
    """Builds SectorContextEvidence from pre-loaded repository inputs.

    Takes the already-resolved `SectorContextEvidenceBuilder` per call rather
    than a factory: the coordinator must resolve one builder instance per
    evidence pass to use for both `peers_for_ticker()` and `build()`.
    """

    def assemble(
        self,
        *,
        builder: "SectorContextEvidenceBuilder",
        ticker: str,
        snapshot_date: date,
        sector: str | None,
        inputs: SectorContextInputs,
    ) -> "SectorContextEvidence":
        from src.application.services.sector_context_evidence_builder import (
            SectorContextRequest,
        )

        return builder.build(
            SectorContextRequest(
                ticker=ticker,
                snapshot_date=snapshot_date,
                sector=sector,
                ticker_candles=inputs.ticker_candles,
                peer_candles=inputs.peer_candles,
                ihsg_20d_return=inputs.ihsg_20d_return,
            )
        )
