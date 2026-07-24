"""Pure VWAP-discount depth display helpers shared across adapters.

These are display-only classifications and plain-text formatters (no scoring
policy, no framework dependency). CLI colour rendering builds on
``vwap_depth_label`` with its own rich styles; the TUI consumes the plain-text
helpers directly. Keeping them here means the TUI never imports the CLI adapter.

Layer: Adapter (shared)
"""

from __future__ import annotations


def vwap_depth_label(discount: float | None) -> str | None:
    """Soft VWAP depth bucket for triage UX (display-only; not scoring policy).

    Aligns with research soft-filter bands (schema-7 VWAP×regime card):
    deep ≥ 8%, mid ≥ 3%, shallow ≥ 0%, over < 0%. Missing → None.
    """
    if discount is None:
        return None
    if discount >= 8.0:
        return "deep"
    if discount >= 3.0:
        return "mid"
    if discount >= 0.0:
        return "shallow"
    return "over"


def format_disc_pct_plain(discount: float | None) -> str:
    """Plain-text Disc% + full depth badge for TUI / enrichment surfaces."""
    if discount is None:
        return "—"
    depth = vwap_depth_label(discount)
    label = f"{discount:+.1f}%"
    if depth is None:
        return label
    return f"{label} {depth}"
