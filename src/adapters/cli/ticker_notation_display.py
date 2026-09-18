"""Ticker special-notation labels shared by screen/plan displays.

Layer: Adapter (pure presentation)
"""

from __future__ import annotations

from typing import Any


def notation_label(snapshot: Any) -> str:
    if snapshot is None:
        return "-"
    parts = []
    if getattr(snapshot, "codes", None):
        parts.append(",".join(snapshot.codes))
    if getattr(snapshot, "tradeable", None) is False:
        parts.append("NO-TRADE")
    status = getattr(snapshot, "status", None)
    if status and status != "STATUS_ACTIVE":
        parts.append(status.replace("STATUS_", ""))
    if getattr(snapshot, "suspend_info", None):
        parts.append("SUSP")
    if getattr(snapshot, "has_uma", None):
        parts.append("UMA")
    return "+".join(parts) if parts else "-"


def notation_detail(snapshot: Any) -> str:
    if snapshot is None:
        return ""
    bits = []
    label = notation_label(snapshot)
    if label != "-":
        bits.append(label)
    if snapshot.listing_board:
        bits.append(snapshot.listing_board)
    if snapshot.haircut_percentage:
        bits.append(f"haircut={snapshot.haircut_percentage}")
    return " | ".join(bits)
