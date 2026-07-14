"""Ticker profile evidence assembly, shared by evidence coordinators.

Layer: Application
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from src.application.services.candidate_evidence_data_loader import (
    TickerProfileEvidenceInputs,
)

if TYPE_CHECKING:
    from src.application.services.ticker_profile_classifier import (
        TickerProfileClassifier,
    )
    from src.domain.value_objects.ticker_profile_snapshot import TickerProfileSnapshot


class CandidateTickerProfileEvidenceAssembler:
    """Builds TickerProfileSnapshot from pre-loaded repository inputs."""

    def __init__(
        self,
        classifier_factory: Callable[[], "TickerProfileClassifier"] | None,
    ) -> None:
        self._classifier_factory = classifier_factory

    def assemble(
        self,
        *,
        ticker: str,
        snapshot_date: date,
        inputs: TickerProfileEvidenceInputs,
        market_cap_idr: Decimal | None,
        sector: str | None,
        sub_sector: str | None,
    ) -> "TickerProfileSnapshot | None":
        if self._classifier_factory is None:
            return None
        from src.application.dto.ticker_profile import TickerProfileRequest

        classifier = self._classifier_factory()
        return classifier.classify(
            TickerProfileRequest(
                ticker=ticker,
                snapshot_date=snapshot_date,
                candles=inputs.candles,
                broker_daily_flows=inputs.broker_daily_flows,
                broker_summaries=inputs.broker_summaries,
                market_cap_idr=market_cap_idr,
                sector=sector,
                sub_sector=sub_sector,
            )
        )
