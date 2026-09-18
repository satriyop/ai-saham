"""
CLI helpers for screen discovery contract (format + empty errors).

Layer: Adapter
"""

from __future__ import annotations

from src.adapters.cli.cli_errors import raise_data_unavailable
from src.application.dto.screen_contract import missing_screen_message


def exit_missing_screen_data(
    *,
    what: str,
    name: str | None = None,
    source: str | None = None,
    fetch_hint: str | None = None,
) -> None:
    raise_data_unavailable(
        missing_screen_message(
            what=what,
            name=name,
            source=source,
            fetch_hint=fetch_hint,
        )
    )
