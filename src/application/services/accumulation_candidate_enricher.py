"""Provider-backed candidate enrichment after structural pruning passes.

Owns all provider-backed enrichment: corporate-action risk flags, seasonality,
insider transactions, analyst consensus, shareholding composition, bandar
detector, fundamentals, ticker notation, and forward estimates.

Foreign-flow scoring is owned by ``AccumulationCandidateSignalAssessor``.

Layer: Application
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from src.application.dto import accumulation_screen as accumulation_dto
from src.application.ports.corporate_action_repository import CorporateActionRepository
from src.domain.value_objects.insider_transaction import compute_net_buy_ratio

if TYPE_CHECKING:
    from src.domain.ports.analyst_consensus_provider import AnalystConsensusProvider
    from src.domain.ports.bandar_detector_provider import BandarDetectorProvider
    from src.domain.ports.forward_estimates_provider import ForwardEstimatesProvider
    from src.domain.ports.fundamentals_provider import FundamentalsProvider
    from src.domain.ports.insider_activity_provider import InsiderActivityProvider
    from src.domain.ports.seasonality_provider import SeasonalityProvider
    from src.domain.ports.shareholding_provider import ShareholdingProvider
    from src.domain.ports.ticker_notation_provider import TickerNotationProvider

logger = logging.getLogger(__name__)


@dataclass
class CandidateEnrichmentResult:
    candidate: accumulation_dto.AccumulationCandidate
    insider_net_buy_ratio: float | None = 0.0


class AccumulationCandidateEnricher:
    """Enrich a candidate with all provider-backed data.

    Does not perform foreign-flow scoring, signal scoring, pass/reject
    classification, or setup phase detection. Does not fetch fundamentals
    twice for the same candidate.
    """

    def __init__(
        self,
        corp_action_repo: CorporateActionRepository | None = None,
        seasonality_provider: SeasonalityProvider | None = None,
        insider_provider: InsiderActivityProvider | None = None,
        analyst_provider: AnalystConsensusProvider | None = None,
        shareholding_provider: ShareholdingProvider | None = None,
        bandar_provider: BandarDetectorProvider | None = None,
        fundamentals_provider: FundamentalsProvider | None = None,
        ticker_notation_provider: TickerNotationProvider | None = None,
        forward_estimates_provider: ForwardEstimatesProvider | None = None,
        derived_features: accumulation_dto.AccumulationDerivedFeaturePolicy | None = None,
    ) -> None:
        self._corp_action_repo = corp_action_repo
        self._seasonality_provider = seasonality_provider
        self._insider_provider = insider_provider
        self._analyst_provider = analyst_provider
        self._shareholding_provider = shareholding_provider
        self._bandar_provider = bandar_provider
        self._fundamentals_provider = fundamentals_provider
        self._ticker_notation_provider = ticker_notation_provider
        self._forward_estimates_provider = forward_estimates_provider
        self._derived_features = (
            derived_features or accumulation_dto.AccumulationDerivedFeaturePolicy()
        )

    def enrich(
        self,
        candidate: accumulation_dto.AccumulationCandidate,
        *,
        request: accumulation_dto.AccumulationScreenRequest,
        as_of_date: date,
        fundamentals_fetched: bool,
    ) -> CandidateEnrichmentResult:
        """Run all provider-backed enrichment on the candidate in order."""
        # Phase 2.2: resistance-proximity flag
        if (
            request.resistance_gate_enabled
            and candidate.nearest_resistance_pct is not None
            and candidate.nearest_resistance_pct < request.resistance_headroom_min_pct
        ):
            candidate.resistance_flag = True

        # Phase 3.1: corporate action risk flags
        if self._corp_action_repo is not None:
            events = self._corp_action_repo.get_upcoming_events(
                ticker=candidate.ticker,
                from_date=as_of_date,
                to_date=as_of_date + timedelta(days=request.ex_date_warning_days),
            )
            for event in events:
                if event.is_dividend:
                    candidate.dividend_risk = True
                elif event.is_rights_issue:
                    candidate.rights_issue_risk = True
                elif event.is_rups:
                    candidate.upcoming_rups.append(event.detail or "RUPS")

        # Phase 3.3: seasonality signal
        if self._seasonality_provider is not None:
            candidate.seasonal_edge = self._seasonality_provider.get_seasonal_edge(
                ticker=candidate.ticker,
                year=as_of_date.year,
                month=as_of_date.month,
                as_of_date=request.as_of_date,
            )

        # Insider transactions
        insider_net_buy_ratio: float | None = None
        if self._insider_provider is not None:
            insider_txns = self._insider_provider.get_insider_transactions(
                ticker=candidate.ticker,
                from_date=as_of_date
                - timedelta(days=self._derived_features.insider_lookback_days),
                to_date=as_of_date,
                action_type="ALL",
                as_of_date=request.as_of_date,
            )
            buy_txns = [t for t in insider_txns if t.is_buy]
            if buy_txns:
                candidate.insider_buying = True
                candidate.recent_insider_buys = [t.label for t in buy_txns[:3]]
            nbr = compute_net_buy_ratio(insider_txns)
            insider_net_buy_ratio = nbr if nbr is not None else 0.0

        # Analyst consensus
        if self._analyst_provider is not None:
            candidate.analyst_consensus = self._analyst_provider.get_consensus(
                ticker=candidate.ticker,
                as_of_date=request.as_of_date,
            )

        # Shareholding composition
        if self._shareholding_provider is not None:
            candidate.shareholding = self._shareholding_provider.get_composition(
                ticker=candidate.ticker,
                as_of_date=request.as_of_date,
            )

        # Bandar detector
        if self._bandar_provider is not None:
            candidate.bandar_detector = self._bandar_provider.get_snapshot(
                ticker=candidate.ticker,
                session_date=request.as_of_date,
            )

        # Company fundamentals (skip if already fetched by structural filter)
        if self._fundamentals_provider is not None and not fundamentals_fetched:
            candidate.fundamentals = self._fundamentals_provider.get_fundamentals(
                ticker=candidate.ticker,
                as_of_date=request.as_of_date,
            )

        # Ticker notation
        if self._ticker_notation_provider is not None:
            candidate.ticker_notation = self._ticker_notation_provider.get_notation(
                ticker=candidate.ticker,
                as_of_date=request.as_of_date,
            )

        # Forward estimates + forward PE derivation
        if self._forward_estimates_provider is not None:
            candidate.forward_estimates = (
                self._forward_estimates_provider.get_forward_estimates(
                    ticker=candidate.ticker,
                    as_of_date=request.as_of_date,
                )
            )
            if (
                candidate.forward_estimates is not None
                and candidate.forward_estimates.forward_pe is None
                and candidate.forward_estimates.forward_eps_1y is not None
                and candidate.current_price > Decimal("0")
            ):
                candidate.forward_estimates = (
                    candidate.forward_estimates.with_current_price(
                        float(candidate.current_price)
                    )
                )

        return CandidateEnrichmentResult(
            candidate=candidate,
            insider_net_buy_ratio=insider_net_buy_ratio,
        )
