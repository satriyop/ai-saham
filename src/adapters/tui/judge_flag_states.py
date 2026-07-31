"""Judge flag-chip availability / is-on state from real model data.

Design: docs/design/tui-cockpit-opencode.md — chips are data-contextual,
not a static peach wall.

Layer: Adapter (pure)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class JudgeFlagChipState:
    """One flag pill: available · expanded (is-on) · warn · visible."""

    key: str
    available: bool
    expanded: bool
    warn: bool = False
    visible: bool = True


def expandable_flags_available(model: Any) -> set[str]:
    """Keys that may open panels for this model."""
    by_key = {c.key: c for c in (getattr(model, "cards", ()) or ())}
    readiness = str(getattr(model, "readiness", "") or "")
    avail: set[str] = set()
    if getattr(model, "decision_lines", ()):
        avail.add("stack")
    if readiness and readiness not in {"—", "-"}:
        avail.add("readiness")
    if by_key.get("named_setups") is not None:
        avail.add("named")
    if by_key.get("market") is not None:
        avail.add("mce")
    if getattr(model, "phase_arrow", ""):
        avail.add("phase_plus")
    return avail


def open_panels(
    model: Any,
    *,
    detail_all: bool,
    open_flags: set[str] | frozenset[str],
) -> set[str]:
    """Which expandable panels should show body content."""
    avail = expandable_flags_available(model)
    if detail_all:
        return set(avail)
    return set(open_flags or ()) & avail


def judge_flag_chip_states(
    model: Any,
    *,
    detail_all: bool,
    open_flags: set[str] | frozenset[str],
) -> tuple[JudgeFlagChipState, ...]:
    """Compute chip states from JudgeDeskModel + open panel set.

    - available: data exists for that panel
    - expanded (is-on): master only when detail_all; singles only when that
      key is open *and* detail_all is False (avoids peach wall when d opens all)
    - limited: visible only when model.limited; warn + expanded as state
    """
    avail = expandable_flags_available(model)
    limited = bool(getattr(model, "limited", False))
    open_f = set(open_flags or ())

    def single_on(key: str) -> bool:
        if key not in avail:
            return False
        # Master open: panels show, but only detail chip is peach
        if detail_all:
            return False
        return key in open_f

    return (
        JudgeFlagChipState(
            key="detail",
            available=True,
            expanded=bool(detail_all),
            warn=False,
            visible=True,
        ),
        JudgeFlagChipState(
            key="stack",
            available="stack" in avail,
            expanded=single_on("stack"),
            warn=False,
            visible=True,
        ),
        JudgeFlagChipState(
            key="readiness",
            available="readiness" in avail,
            expanded=single_on("readiness"),
            warn=False,
            visible=True,
        ),
        JudgeFlagChipState(
            key="named",
            available="named" in avail,
            expanded=single_on("named"),
            warn=False,
            visible=True,
        ),
        JudgeFlagChipState(
            key="mce",
            available="mce" in avail,
            expanded=single_on("mce"),
            warn=False,
            visible=True,
        ),
        JudgeFlagChipState(
            key="phase_plus",
            available="phase_plus" in avail,
            expanded=single_on("phase_plus"),
            warn=False,
            visible=True,
        ),
        JudgeFlagChipState(
            key="limited",
            available=limited,
            expanded=limited,
            warn=limited,
            visible=limited,  # hide on full live judge
        ),
    )
