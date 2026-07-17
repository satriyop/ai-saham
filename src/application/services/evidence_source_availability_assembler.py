"""Shadow-mode evidence-group source availability assembly (ADR-041
CANONICAL-EVIDENCE-BOUNDARY, formerly DQ-002J).

Layer: Application

Wraps one already-constructed `AssessSourceAvailabilityUseCase` (itself
already bound to one resolved `EffectiveMarketSession`-compatible calendar
and settlement registry, reused across a whole workflow execution) to answer,
per canonical setup/flow evidence group, whether the source families that
evidence group's underlying data actually came from were CURRENT/LATE/STALE/
...at decision time.

Availability is derived exclusively from `SetupProvenance`/`FlowProvenance`
— the exact consumed-row identities a `BuiltSetupEvidence`/`BuiltFlowEvidence`
already carries — never from raw candle lists, an `AccumulationCandidate`, or
any of its scalar `latest_*_date` fields. This is the binding ADR-041
invariant: availability must describe the exact rows a scored evidence group
consumed, not a separately fetched or inferred value that could silently
diverge from it.

**Known gap, deliberately not assessed, but not silently hidden either**:
`FlowConfirmationEvidence`'s Bandar sub-signal is sourced from
`StockbitBandarDetectorProvider` — a live Stockbit browser/API scrape, not
one of `SourceSettlementRegistry`'s persisted SQLite source families. It has
no settlement rule and cannot be given one without a separate registry/ADR
decision, so it is never given a `SourceAvailabilityAssessment`. Whenever
`provenance.has_bandar_contributor` is `True`, it is named in
`flow_availability.unassessed_contributors`, which forces
`flow_availability.all_authoritative` to `False` — this prevents the group
from ever claiming full authority while a real, present contributor went
unassessed.

Callers should call `assess_setup`/`assess_flow` only once the corresponding
evidence (`SetupEvidence`/`FlowConfirmationEvidence`) actually exists —
availability describes evidence that was produced, not evidence that could
theoretically have been produced from the same candidate.

This module does not decide availability policy itself (that stays in
`AssessSourceAvailabilityUseCase`/`SourceSettlementRegistry`); it only shapes
per-group results into `EvidenceSourceAvailability` for attachment to the
canonical evidence-group inputs (`SetupEvidenceGroupInput`/
`FlowEvidenceGroupInput`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domain.value_objects.evidence_source_availability import EvidenceSourceAvailability

if TYPE_CHECKING:
    from src.application.services.effective_market_session_resolver import (
        EffectiveMarketSession,
    )
    from src.application.use_case.assess_source_availability_use_case import (
        AssessSourceAvailabilityUseCase,
    )
    from src.domain.value_objects.canonical_signal_evidence_input import (
        FlowProvenance,
        SetupProvenance,
    )


class EvidenceSourceAvailabilityAssembler:
    """Assembles setup/flow `EvidenceSourceAvailability` from exact provenance."""

    def __init__(self, use_case: "AssessSourceAvailabilityUseCase") -> None:
        self._use_case = use_case

    def assess_setup(
        self,
        *,
        effective_session: "EffectiveMarketSession",
        provenance: "SetupProvenance",
    ) -> EvidenceSourceAvailability:
        latest_candle_date = max(
            (row.date for row in provenance.candle_rows), default=None
        )
        return EvidenceSourceAvailability(
            evidence_group="setup",
            assessments=(
                self._use_case.execute(
                    source_family="candles",
                    effective_session=effective_session,
                    observed_through=latest_candle_date,
                ),
            ),
        )

    def assess_flow(
        self,
        *,
        effective_session: "EffectiveMarketSession",
        provenance: "FlowProvenance",
    ) -> EvidenceSourceAvailability:
        max_summary_row_date = max(
            (row.date for row in provenance.broker_summary_rows), default=None
        )
        max_daily_flow_row_date = max(
            (row.date for row in provenance.broker_daily_flow_rows), default=None
        )
        unassessed_contributors = (
            ("bandar_detector",) if provenance.has_bandar_contributor else ()
        )

        return EvidenceSourceAvailability(
            evidence_group="flow",
            assessments=(
                self._use_case.execute(
                    source_family="broker_summaries",
                    effective_session=effective_session,
                    observed_through=max_summary_row_date,
                ),
                self._use_case.execute(
                    source_family="broker_daily_flow",
                    effective_session=effective_session,
                    observed_through=max_daily_flow_row_date,
                ),
            ),
            unassessed_contributors=unassessed_contributors,
        )
