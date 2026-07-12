"""
Shared formatting helpers for ticker dashboard panels.

Layer: Adapter
"""

from __future__ import annotations

from rich.text import Text


def _fmt_idr(value: float | int | None, *, suffix: bool = True) -> str:
    if value is None:
        return "\u2014"
    v = float(value)
    if suffix:
        if abs(v) >= 1e12:
            return f"{v / 1e12:.2f} T"
        if abs(v) >= 1e9:
            return f"{v / 1e9:.2f} B"
        if abs(v) >= 1e6:
            return f"{v / 1e6:.2f} M"
    return f"{v:,.0f}"


def _fmt_vol(volume: int | None) -> str:
    if volume is None:
        return "\u2014"
    if volume >= 1_000_000:
        return f"{volume / 1_000_000:.1f} M"
    if volume >= 1_000:
        return f"{volume / 1_000:.1f} K"
    return str(volume)


def _pct(value: float | None, decimals: int = 1) -> str:
    if value is None:
        return "\u2014"
    return f"{value:.{decimals}f}%"


def _f(value: float | None, decimals: int = 1) -> str:
    if value is None:
        return "\u2014"
    return f"{value:.{decimals}f}"


def _not_cached() -> Text:
    return Text("  not cached", style="dim")
