"""Tests for ListCachedTickersUseCase.

Layer: Application
"""

from src.application.use_case.list_cached_tickers_use_case import (
    ListCachedTickersRequest,
    ListCachedTickersResult,
    ListCachedTickersUseCase,
)


class _FakeCatalog:
    def __init__(self, tickers: list[str]) -> None:
        self._tickers = tickers
        self.calls = 0

    def list_tickers(self) -> list[str]:
        self.calls += 1
        return list(self._tickers)


def test_lists_all_cached_tickers_when_no_prefix() -> None:
    catalog = _FakeCatalog(["BBRI", "BBCA", "BMRI"])
    result = ListCachedTickersUseCase(catalog).execute()

    assert isinstance(result, ListCachedTickersResult)
    assert result.tickers == ("BBRI", "BBCA", "BMRI")
    assert result.total_cached == 3


def test_prefix_filter_is_case_insensitive() -> None:
    catalog = _FakeCatalog(["BBRI", "BBCA", "BMRI", "ANTM"])
    result = ListCachedTickersUseCase(catalog).execute(ListCachedTickersRequest(prefix="bb"))

    assert result.tickers == ("BBRI", "BBCA")
    assert result.total_cached == 4  # total reflects full catalog, not matches


def test_limit_caps_matches() -> None:
    catalog = _FakeCatalog(["BBRI", "BBCA", "BMRI"])
    result = ListCachedTickersUseCase(catalog).execute(ListCachedTickersRequest(limit=2))

    assert result.tickers == ("BBRI", "BBCA")


def test_no_provider_call_is_possible_offline() -> None:
    # The use case only ever calls the catalog port — never a provider.
    catalog = _FakeCatalog(["BBRI"])
    ListCachedTickersUseCase(catalog).execute(ListCachedTickersRequest(prefix="X"))
    assert catalog.calls == 1
