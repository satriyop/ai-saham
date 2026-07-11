"""
AccumulationSectorBreadthApplier service.

Computes sector breadth and applies scoring bonus for sector concentration in-place.

Layer: Application
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.dto import accumulation_screen as accumulation_dto


class AccumulationSectorBreadthApplier:
    def __init__(self, ticker_to_group: dict[str, str]) -> None:
        self._ticker_to_group = ticker_to_group

    def apply(
        self,
        candidates: list[accumulation_dto.AccumulationCandidate],
        request: accumulation_dto.AccumulationScreenRequest,
    ) -> None:
        """Post-processing: compute sector breadth and apply bonus in-place.

        Groups candidates by idx_groups mapping. For groups with enough members
        (>= min_tickers_for_breadth), computes the fraction with net_buy_ratio > 0.
        Applies sector_breadth_bonus_pts to ALL members of qualifying groups.
        """
        # Group candidates by their idx_groups group
        group_candidates: dict[str, list[accumulation_dto.AccumulationCandidate]] = defaultdict(
            list
        )
        for candidate in candidates:
            group = self._ticker_to_group.get(candidate.ticker.upper())
            if group:
                group_candidates[group].append(candidate)

        # For each group with enough members, compute breadth and apply bonus
        for group, members in group_candidates.items():
            if len(members) < request.sector_breadth_min_tickers:
                # Set breadth_pct but no bonus (insufficient sample)
                total = len(members)
                positive = sum(1 for m in members if m.net_buy_ratio > 0)
                breadth_pct = positive / total if total > 0 else 0.0
                for m in members:
                    m.sector_breadth_pct = breadth_pct
                continue

            positive = sum(1 for m in members if m.net_buy_ratio > 0)
            breadth_pct = positive / len(members)

            for m in members:
                m.sector_breadth_pct = breadth_pct
                if breadth_pct >= request.sector_breadth_threshold:
                    m.foreign_flow_score += request.sector_breadth_bonus_pts
                    m.sector_breadth_bonus = request.sector_breadth_bonus_pts
