"""
Refresh Stockbit Enrichment Use Case.

Owns the cache-freshness-then-fetch policy for all Stockbit enrichment
providers: notation, analyst, insider, seasonality, corp actions,
shareholding, bandar detector, fundamentals.

Layer: Application
Dependencies: None (infrastructure providers injected as callables)
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EnrichmentTask:
    """One enrichment provider expressed as a label + two zero-arg callables."""

    label: str
    is_fresh: Callable[[], bool]
    fetch: Callable[[], Any]


@dataclass(frozen=True)
class RefreshStockbitEnrichmentRequest:
    ticker: str
    tasks: list[EnrichmentTask]


@dataclass(frozen=True)
class RefreshStockbitEnrichmentResponse:
    status: str
    fetched: tuple[str, ...]
    cached: tuple[str, ...]
    errors: tuple[str, ...]


class RefreshStockbitEnrichmentUseCase:
    """
    Run cache-freshness-then-fetch for a list of enrichment tasks.

    For each task: if is_fresh() is True, mark as cached; otherwise call
    fetch() and mark as fetched (or record error on exception).

    Returns a compact status string matching the format produced by the
    previous adapter implementation:
      - "✓(label1,label2,...)"   — all providers were cached
      - "label1+label2  ✓(...)  — some fetched, some cached
      - "ERR:label:msg,..."      — one or more providers failed
    """

    def execute(
        self, request: RefreshStockbitEnrichmentRequest
    ) -> RefreshStockbitEnrichmentResponse:
        fetched: list[str] = []
        cached: list[str] = []
        errors: list[str] = []

        for task in request.tasks:
            try:
                if task.is_fresh():
                    cached.append(task.label)
                else:
                    task.fetch()
                    fetched.append(task.label)
            except Exception as exc:
                errors.append(f"{task.label}:{str(exc)[:20]}")

        status = _build_status(fetched, cached, errors)
        return RefreshStockbitEnrichmentResponse(
            status=status,
            fetched=tuple(fetched),
            cached=tuple(cached),
            errors=tuple(errors),
        )


def _build_status(
    fetched: list[str],
    cached: list[str],
    errors: list[str],
) -> str:
    if errors:
        return "ERR:" + ",".join(errors)
    if not fetched:
        return f"✓({','.join(cached)})"
    cached_part = f"  ✓({','.join(cached)})" if cached else ""
    return "+".join(fetched) + cached_part
