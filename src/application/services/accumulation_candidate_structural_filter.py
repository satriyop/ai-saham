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

if TYPE_CHECKING:
    from src.domain.ports.fundamentals_provider import FundamentalsProvider

logger = logging.getLogger(__name__)


@dataclass
class StructuralFilterResult:
    candidate: accumulation_dto.AccumulationCandidate
    fundamentals_fetched: bool
    rejected: bool
    screen_result: str | None


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
        if self._fundamentals_provider is None or (
            request.min_market_cap_idr <= 0 and request.min_piotroski <= 0
        ):
            return StructuralFilterResult(candidate, False, False, None)

        candidate.fundamentals = self._fundamentals_provider.get_fundamentals(
            ticker=candidate.ticker,
            as_of_date=request.as_of_date,
        )
        fundamentals_fetched = True

        if request.min_market_cap_idr > 0:
            if (
                candidate.fundamentals is None
                or candidate.fundamentals.market_cap_idr is None
                or candidate.fundamentals.market_cap_idr < request.min_market_cap_idr
            ):
                cap_b = (
                    candidate.fundamentals.market_cap_idr // 1_000_000_000
                    if candidate.fundamentals and candidate.fundamentals.market_cap_idr
                    else None
                )
                logger.debug(
                    "Skip %s: market_cap %sB IDR < floor %dB IDR",
                    candidate.ticker,
                    cap_b,
                    request.min_market_cap_idr // 1_000_000_000,
                )
                return StructuralFilterResult(
                    candidate, fundamentals_fetched, True, "rejected_flow"
                )

        if request.min_piotroski > 0:
            fscore = (
                candidate.fundamentals.piotroski_f_score
                if candidate.fundamentals is not None
                else None
            )
            if fscore is None or fscore < request.min_piotroski:
                return StructuralFilterResult(
                    candidate, fundamentals_fetched, True, "rejected_flow"
                )

        return StructuralFilterResult(candidate, fundamentals_fetched, False, None)
