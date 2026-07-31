"""Judge density helpers: brief ↔ detail (CLI screen accum --detail dual).

Multi-chip walls removed from design. This module still names which *content*
sections exist under detail mode from real model fields.

Layer: Adapter (pure)
"""

from __future__ import annotations

from typing import Any


def expandable_flags_available(model: Any) -> set[str]:
    """Section keys that have data for detail-mode body (not chip chrome)."""
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
    """Which detail sections should show body content.

    Brief (detail_all=False): empty set — primary cards only.
    Detail (detail_all=True): all sections that have data.
    """
    avail = expandable_flags_available(model)
    if detail_all:
        return set(avail)
    # Legacy: individual open_flags ignored for Judge density (detail-only toggle)
    _ = open_flags
    return set()
