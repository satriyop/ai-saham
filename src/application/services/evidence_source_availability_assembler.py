"""Shadow-mode evidence-group source availability assembly — DQ-002 Blocker 2.

Layer: Application

Wraps one already-constructed `AssessSourceAvailabilityUseCase` (itself
already bound to one resolved `EffectiveMarketSession`-compatible calendar
and settlement registry, reused across a whole workflow execution) to answer,
per canonical setup/flow evidence group, whether the source families that
evidence group's underlying data actually came from were CURRENT/LATE/STALE/
...at decision time.

Scope (Phase 2, shadow mode only, partial — `saham analyze swing` only, see
DQ-002J): only the source families this workflow's setup/flow evidence path
actually consumes:

- **setup**: `candles`. `observed_through` is the max date of the `candles`
  list the caller passes in — the *same* bounded list actually handed to
  `SwingAnalysisEvidenceBuilder`/the setup-phase detector — never
  `AccumulationCandidate.latest_candle_date`, which is computed from a
  separate repository call and previously caused availability to describe a
  different read than the one evidence actually consumes.
- **flow**: `broker_summaries` (via `AccumulationCandidate.latest_broker_date`
  — proven to be exactly `window_summaries`' window, the same rows
  `ScoreForeignFlowUseCase`'s net_buy_ratio/streak/vwap/flow sub-signals are
  computed from) and `broker_daily_flow` (via
  `AccumulationCandidate.latest_broker_daily_flow_date` — the max date among
  `daily_flows` rows actually inside that same window, feeding the
  `bci_label`/`top_brokers` sub-signals). Both `None` when the candidate
  never populated them (fails closed to `UNKNOWN`, never inferred).

**Known gap, deliberately not assessed, but not silently hidden either**:
`FlowConfirmationEvidence`'s Bandar sub-signal (`candidate.bandar_detector`)
is sourced from `StockbitBandarDetectorProvider` — a live Stockbit
browser/API scrape, not one of `SourceSettlementRegistry`'s persisted SQLite
source families. It has no settlement rule and cannot be given one without a
separate registry/ADR decision, so it is never given a
`SourceAvailabilityAssessment`. Whenever `candidate.bandar_detector is not
None` (i.e. it actually contributed to `FlowConfirmationEvidence` for this
decision), it is named in `flow_availability.unassessed_contributors`, which
forces `flow_availability.all_authoritative` to `False` — this prevents the
group from ever claiming full authority while a real, present contributor
went unassessed. When Bandar was never fetched (`None`), it is not a
contributor to this decision and is not listed. `foreign_flow_points`/
`foreign_flow_snapshots` are likewise not consumed by this workflow's
setup/flow evidence path and are intentionally out of scope.

Callers should call `assess_setup`/`assess_flow` only once the corresponding
evidence (`SetupEvidence`/`FlowConfirmationEvidence`) actually exists —
availability describes evidence that was produced, not evidence that could
theoretically have been produced from the same candidate.

This module does not decide availability policy itself (that stays in
`AssessSourceAvailabilityUseCase`/`SourceSettlementRegistry`); it only shapes
per-group results into `EvidenceSourceAvailability` for attachment to the
canonical `AssessSignalResponse`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Sequence

from src.domain.value_objects.evidence_source_availability import EvidenceSourceAvailability

if TYPE_CHECKING:
    from src.application.services.effective_market_session_resolver import (
        EffectiveMarketSession,
    )
    from src.application.use_case.assess_source_availability_use_case import (
        AssessSourceAvailabilityUseCase,
    )


class EvidenceSourceAvailabilityAssembler:
    """Assembles setup/flow `EvidenceSourceAvailability` from actually-consumed rows."""

    def __init__(self, use_case: "AssessSourceAvailabilityUseCase") -> None:
        self._use_case = use_case

    def assess_setup(
        self,
        *,
        effective_session: "EffectiveMarketSession",
        candles: Sequence[Any],
    ) -> EvidenceSourceAvailability:
        # Derived from the literal candles list the caller actually passed to
        # the evidence builder — not a separately fetched candidate field —
        # so availability can never describe a different read than the one
        # setup evidence actually consumed.
        latest_candle_date = max((c.date for c in candles), default=None)
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
        candidate: Any,
    ) -> EvidenceSourceAvailability:
        latest_broker_date = getattr(candidate, "latest_broker_date", None)
        latest_broker_daily_flow_date = getattr(
            candidate, "latest_broker_daily_flow_date", None
        )
        bandar_detector = getattr(candidate, "bandar_detector", None)
        unassessed_contributors = ("bandar_detector",) if bandar_detector is not None else ()

        return EvidenceSourceAvailability(
            evidence_group="flow",
            assessments=(
                self._use_case.execute(
                    source_family="broker_summaries",
                    effective_session=effective_session,
                    observed_through=latest_broker_date,
                ),
                self._use_case.execute(
                    source_family="broker_daily_flow",
                    effective_session=effective_session,
                    observed_through=latest_broker_daily_flow_date,
                ),
            ),
            unassessed_contributors=unassessed_contributors,
        )
