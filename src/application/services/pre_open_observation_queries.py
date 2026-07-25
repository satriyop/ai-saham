"""Read helpers for pre-open saved observations (decision authority).

Layer: Application
"""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol

from src.application.services.pre_open_observation_payload import PRE_OPEN_WORKFLOW


class PreOpenObservationsReader(Protocol):
    def list_all_by_date(self, snapshot_date: date) -> list[Any]:
        ...


def list_pre_open_observations_by_ticker(
    repository: PreOpenObservationsReader | None,
    run_date: date,
) -> dict[str, Any]:
    """Latest pre-open observation row per ticker for a session date."""
    if repository is None:
        return {}
    try:
        rows = repository.list_all_by_date(run_date)
    except Exception:
        return {}
    pre_open = [
        r
        for r in rows
        if getattr(r, "workflow", None) == PRE_OPEN_WORKFLOW
        or (
            isinstance(getattr(r, "payload", None), dict)
            and r.payload.get("workflow") == PRE_OPEN_WORKFLOW
        )
    ]
    by_ticker: dict[str, Any] = {}
    for row in sorted(
        pre_open,
        key=lambda r: getattr(r, "captured_at", None) or date.min,
    ):
        by_ticker[row.ticker] = row
    return by_ticker


def list_pre_open_tickers(
    repository: PreOpenObservationsReader | None,
    run_date: date,
) -> list[str]:
    """Sorted tickers with saved pre-open observations for track / ops."""
    return sorted(list_pre_open_observations_by_ticker(repository, run_date).keys())
