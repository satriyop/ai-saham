"""
Application orchestration for `saham fetch enrichment-history`.

Owns: ticker iteration, ok/fail counting, PIT coverage read policy.
Does NOT own: provider construction, output formatting, or arg parsing.

Layer: Application
AI usage: None
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class FetchEnrichmentHistoryRequest:
    tickers: list[str]
    force_refresh: bool = True


@dataclass(frozen=True)
class EnrichmentPitTableCoverage:
    table: str
    snapshot_count: int
    latest_date: str | None
    tickers_in_latest: int


@dataclass(frozen=True)
class FetchEnrichmentHistoryResponse:
    results: list[tuple[str, str]]
    ok_count: int
    fail_count: int
    coverage: list[EnrichmentPitTableCoverage] = field(default_factory=list)


class FetchEnrichmentHistoryUseCase:
    """Refresh enrichment for each ticker and report PIT coverage.

    Provider construction and output formatting belong in the adapter.
    This use case owns: iteration policy, ok/fail counting, coverage report.

    Args:
        enrich_ticker: Callable taking a ticker str, returning a status str.
            Status starts with "ERR:" on failure.
        read_pit_coverage: Callable returning list[EnrichmentPitTableCoverage].
    """

    def __init__(
        self,
        enrich_ticker: Callable[[str], str],
        read_pit_coverage: Callable[[], list[EnrichmentPitTableCoverage]],
    ) -> None:
        self._enrich_ticker = enrich_ticker
        self._read_pit_coverage = read_pit_coverage

    def execute(
        self, request: FetchEnrichmentHistoryRequest
    ) -> FetchEnrichmentHistoryResponse:
        results: list[tuple[str, str]] = []
        ok_count = 0
        fail_count = 0

        for ticker in request.tickers:
            status = self._enrich_ticker(ticker)
            results.append((ticker, status))
            if status.startswith("ERR:"):
                fail_count += 1
            else:
                ok_count += 1

        coverage = self._read_pit_coverage()
        return FetchEnrichmentHistoryResponse(
            results=results,
            ok_count=ok_count,
            fail_count=fail_count,
            coverage=coverage,
        )
