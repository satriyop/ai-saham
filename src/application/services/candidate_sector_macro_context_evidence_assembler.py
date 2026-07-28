"""Sector macro context evidence assembly (ADR-053).

Layer: Application
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from src.application.services.candidate_evidence_data_loader import (
    SectorMacroContextInputs,
)

if TYPE_CHECKING:
    from src.application.services.sector_macro_context_evidence_builder import (
        SectorMacroContextEvidenceBuilder,
    )
    from src.domain.value_objects.sector_macro_context_evidence import (
        SectorMacroContextEvidence,
    )


class CandidateSectorMacroContextEvidenceAssembler:
    """Builds SectorMacroContextEvidence from pre-loaded series inputs."""

    def assemble(
        self,
        *,
        builder: "SectorMacroContextEvidenceBuilder",
        ticker: str,
        snapshot_date: date,
        sector_group: str | None,
        inputs: SectorMacroContextInputs,
    ) -> "SectorMacroContextEvidence":
        from src.application.services.sector_macro_context_evidence_builder import (
            SectorMacroContextRequest,
        )

        return builder.build(
            SectorMacroContextRequest(
                ticker=ticker,
                snapshot_date=snapshot_date,
                sector_group=sector_group,
                series_candles=inputs.series_candles,
                policy_steps=inputs.policy_steps,
            )
        )
