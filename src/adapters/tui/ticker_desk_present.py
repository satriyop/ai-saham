"""Ticker desk presentation facade (compat + text helpers).

Prefer ``ticker_desk_model`` + ``widgets.ticker_desk`` for visual paint.
This module keeps thin helpers used by tests and string loaders.

Layer: Adapter
"""

from __future__ import annotations

from typing import Any

from src.adapters.tui.theme import OC
from src.adapters.tui.ticker_desk_model import (
    TickerDeskModel,
    build_ticker_desk_model_from_dashboard,
    build_ticker_desk_model_from_text,
)


def format_harga_mast(
    *,
    ticker: str,
    price: str,
    as_of: str = "—",
    change_line: str = "",
    authority: str = "local cache · browse",
) -> str:
    """Hero block as text (tests / scrapers)."""
    t = (ticker or "—").strip().upper() or "—"
    p = (price or "—").strip() or "—"
    lines = [
        f"[bold {OC.text_bright}]View · ticker · {t}[/]",
        f"[bold {OC.peach}]LAST · LOCAL CLOSE[/]",
        f"[bold {OC.text_bright}]{p}[/]",
    ]
    if change_line:
        lines.append(f"[{OC.text_dim}]{change_line}[/]")
    lines.append(f"[{OC.text_mute}]as_of {as_of or '—'} · {authority}[/]")
    lines.append("[dim]local cache · b desks[/]")
    lines.append("")
    return "\n".join(lines)


def format_ticker_desk_from_dashboard(dashboard: Any, *, body: str = "") -> str:
    """Text form of price mast + body (legacy loaders)."""
    model = build_ticker_desk_model_from_dashboard(dashboard, body=body)
    return model.as_text()


def format_ticker_desk_from_text(*, ticker: str, body: str) -> str:
    model = build_ticker_desk_model_from_text(ticker=ticker, body=body)
    return model.as_text()


def model_from_loader_result(ticker: str, result: Any) -> TickerDeskModel:
    """Normalize loader return (model | str | other) into TickerDeskModel."""
    if isinstance(result, TickerDeskModel):
        return result
    if result is None:
        return build_ticker_desk_model_from_text(ticker=ticker, body="")
    # Duck: object with as_text / fields
    if hasattr(result, "price") and hasattr(result, "ticker") and hasattr(result, "metrics"):
        try:
            return result  # type: ignore[return-value]
        except Exception:
            pass
    return build_ticker_desk_model_from_text(ticker=ticker, body=str(result))
