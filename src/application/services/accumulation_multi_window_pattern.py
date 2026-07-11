"""
AccumulationMultiWindowPattern service.

Classifies multi-window accumulation patterns.

Layer: Application
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.dto import accumulation_screen as accumulation_dto


def classify_multi_window_pattern(
    windows: list[int],
    candidates_by_window: dict[int, accumulation_dto.AccumulationCandidate | None],
    coiled_spring_min_score: float,
    coiled_spring_bb_pctile: float,
) -> str:
    """
    Label the multi-window accumulation pattern for a single ticker.

    Returns one of: "coiled spring", "sustained", "building",
    "fresh rotation", "long-term only", "mixed", "weak"
    """
    hot = [
        w
        for w in windows
        if candidates_by_window.get(w)
        and candidates_by_window[w].foreign_flow_score >= coiled_spring_min_score
    ]

    for w in windows:
        c = candidates_by_window.get(w)
        if (
            c
            and c.foreign_flow_score >= coiled_spring_min_score
            and c.bb_width_pctile is not None
            and c.bb_width_pctile <= coiled_spring_bb_pctile
        ):
            return "coiled spring"

    if not hot:
        return "weak"
    if set(hot) == set(windows):
        return "sustained"
    if min(windows) in hot and max(windows) not in hot:
        return "fresh rotation"
    if max(windows) in hot and min(windows) not in hot:
        return "long-term only"
    if min(windows) in hot and len(hot) >= 2:
        return "building"
    return "mixed"
