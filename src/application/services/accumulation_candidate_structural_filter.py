"""Early structural pruning for accumulation candidates.

Fetches fundamentals only when market-cap or Piotroski gates are active,
then rejects candidates that fail structural thresholds — all before
expensive provider enrichment runs.

Layer: Application
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.application.dto import accumulation_screen as accumulation_dto
from src.application.dto.accumulation_structural_filter import (
    StructuralFilterDecision,
    StructuralFilterField,
    StructuralFilterRejectionReason,
)

if TYPE_CHECKING:
    from src.domain.ports.fundamentals_provider import FundamentalsProvider

logger = logging.getLogger(__name__)


@dataclass
class StructuralFilterResult:
    candidate: accumulation_dto.AccumulationCandidate
    fundamentals_fetched: bool
    rejected: bool
    screen_result: str | None
    decision: StructuralFilterDecision


class StructuralFilterConfigurationError(RuntimeError):
    """An enabled structural filter has no provider capable of evaluating it."""


class AccumulationCandidateStructuralFilter:
    """Early structural pruning gate before expensive enrichment runs.

    Owns only the fundamentals provider — no other enrichment providers.
    """

    def __init__(
        self,
        fundamentals_provider: FundamentalsProvider | None = None,
    ) -> None:
        self._fundamentals_provider = fundamentals_provider

    def apply(
        self,
        candidate: accumulation_dto.AccumulationCandidate,
        request: accumulation_dto.AccumulationScreenRequest,
    ) -> StructuralFilterResult:
        """Run structural gates and return the outcome.

        Returns a ``StructuralFilterResult`` with ``rejected=True`` and
        ``screen_result="rejected_flow"`` when either the market-cap floor
        or the Piotroski F-Score floor is not met.
        """
        filters_disabled = request.min_market_cap_idr <= 0 and request.min_piotroski <= 0
        if filters_disabled:
            return StructuralFilterResult(
                candidate,
                False,
                False,
                None,
                StructuralFilterDecision.disabled(),
            )
        if self._fundamentals_provider is None:
            raise StructuralFilterConfigurationError(
                "accumulation structural fundamentals filter is enabled but no "
                "fundamentals provider is configured"
            )

        candidate.fundamentals = self._fundamentals_provider.get_fundamentals(
            ticker=candidate.ticker,
            as_of_date=request.as_of_date,
        )
        fundamentals_fetched = True

        if request.min_market_cap_idr > 0:
            market_cap = (
                candidate.fundamentals.market_cap_idr
                if candidate.fundamentals is not None
                else None
            )
            if market_cap is None or market_cap < request.min_market_cap_idr:
                cap_b = market_cap // 1_000_000_000 if market_cap is not None else None
                logger.debug(
                    "Skip %s: market_cap %sB IDR < floor %dB IDR",
                    candidate.ticker,
                    cap_b,
                    request.min_market_cap_idr // 1_000_000_000,
                )
                return StructuralFilterResult(
                    candidate,
                    fundamentals_fetched,
                    True,
                    "rejected_flow",
                    StructuralFilterDecision.rejected(
                        field=StructuralFilterField.MARKET_CAP_IDR,
                        reason=(
                            StructuralFilterRejectionReason.MISSING_VALUE
                            if market_cap is None
                            else StructuralFilterRejectionReason.BELOW_THRESHOLD
                        ),
                        observed_value=market_cap,
                        threshold=request.min_market_cap_idr,
                    ),
                )

        if request.min_piotroski > 0:
            fscore = (
                candidate.fundamentals.piotroski_f_score
                if candidate.fundamentals is not None
                else None
            )
            if fscore is None or fscore < request.min_piotroski:
                return StructuralFilterResult(
                    candidate,
                    fundamentals_fetched,
                    True,
                    "rejected_flow",
                    StructuralFilterDecision.rejected(
                        field=StructuralFilterField.PIOTROSKI_F_SCORE,
                        reason=(
                            StructuralFilterRejectionReason.MISSING_VALUE
                            if fscore is None
                            else StructuralFilterRejectionReason.BELOW_THRESHOLD
                        ),
                        observed_value=fscore,
                        threshold=request.min_piotroski,
                    ),
                )

        return StructuralFilterResult(
            candidate,
            fundamentals_fetched,
            False,
            None,
            StructuralFilterDecision.passed(),
        )
