"""Shared scalar/status formatting helpers for swing tuning displays.

Layer: Adapter
"""

from __future__ import annotations


def period(start_date: str | None, end_date: str | None) -> str:
    if start_date and end_date:
        return f"{start_date} to {end_date}"
    return "N/A"


def format_int(value: int | None) -> str:
    return "N/A" if value is None else str(value)


def format_pct(value: float | None, signed: bool = False) -> str:
    if value is None:
        return "N/A"
    color = "green" if value >= 0 else "red"
    text = f"{value:+.2f}%" if signed else f"{value:.1f}%"
    return f"[{color}]{text}[/]"


def format_value(value: object | None) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def format_delta(value: object | None) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        color = "green" if value >= 0 else "red"
        return f"[{color}]{value:+.2f}[/]"
    if isinstance(value, int):
        color = "green" if value >= 0 else "red"
        return f"[{color}]{value:+d}[/]"
    return str(value)
