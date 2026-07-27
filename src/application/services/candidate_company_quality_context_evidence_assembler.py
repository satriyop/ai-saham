"""Company quality context evidence assembly, shared by evidence coordinators.

Layer: Application

DIAGNOSTIC-only company-quality / ticker-alpha conviction evidence, built from
enrichment already loaded on the candidate (forward P/E, analyst, insider,
seasonality) via the shared SignalContext builder — no extra provider fetch.
Zero effective score authority (DIAGNOSTIC -> effective_weight 0.0).
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any, Callable

from src.application.services.signal_context_builder import (
    build_signal_context_from_candidate,
)

if TYPE_CHECKING:
    from src.application.services.company_quality_context_evidence_builder import (
        CompanyQualityContextEvidenceBuilder,
    )
    from src.application.services.signal_engine import SignalEngine
    from src.domain.value_objects.company_quality_context_evidence import (
        CompanyQualityContextEvidence,
    )


class CandidateCompanyQualityContextEvidenceAssembler:
    """Builds CompanyQualityContextEvidence from a candidate's signal context."""

    def __init__(
        self,
        builder_factory: Callable[[], "CompanyQualityContextEvidenceBuilder"],
    ) -> None:
        self._builder_factory = builder_factory

    def assemble(
        self,
        *,
        ticker: str,
        snapshot_date: date,
        candidate: Any,
        signal_engine: "SignalEngine | None",
    ) -> "CompanyQualityContextEvidence | None":
        if signal_engine is None:
            return None
        from src.application.services.company_quality_context_evidence_builder import (
            CompanyQualityContextRequest,
        )

        signal_context = build_signal_context_from_candidate(
            ticker=ticker,
            snapshot_date=snapshot_date,
            candidate=candidate,
            signal_engine=signal_engine,
        )
        builder = self._builder_factory()
        return builder.build(
            CompanyQualityContextRequest(
                ticker=ticker,
                snapshot_date=snapshot_date,
                signal_context=signal_context,
            )
        )
