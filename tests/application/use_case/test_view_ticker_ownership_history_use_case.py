"""Offline tests for ViewTickerOwnershipHistoryUseCase (shared CLI/TUI/agent path)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from src.application.use_case.view_ticker_ownership_history_use_case import (
    MAX_LIMIT,
    ViewTickerOwnershipHistoryRequest,
    ViewTickerOwnershipHistoryUseCase,
)
from src.domain.value_objects.shareholding_composition import ShareholdingComposition


def _comp(
    report_date: date,
    *,
    institution_pct: float,
    individual_pct: float,
    top_holder_pct: float,
) -> ShareholdingComposition:
    return ShareholdingComposition(
        ticker="BBCA",
        report_date=report_date,
        institution_pct=institution_pct,
        individual_pct=individual_pct,
        top_holder_name="DWIMURIA",
        top_holder_pct=top_holder_pct,
        total_shares=100_000_000,
        total_shares_formatted="100M",
    )


@dataclass
class _FakeProvider:
    newest_first: tuple[ShareholdingComposition, ...]
    calls: list[tuple[str, int, date | None]] = field(default_factory=list)

    def get_history(self, ticker, limit, as_of_date=None):
        self.calls.append((ticker, limit, as_of_date))
        return self.newest_first


def test_missing_history_returns_none():
    use_case = ViewTickerOwnershipHistoryUseCase(_FakeProvider(()))
    result = use_case.execute(ViewTickerOwnershipHistoryRequest(ticker="BBCA"))
    assert result is None


def test_single_period_has_no_deltas():
    only = _comp(date(2026, 3, 31), institution_pct=40.0, individual_pct=25.0, top_holder_pct=30.0)
    use_case = ViewTickerOwnershipHistoryUseCase(_FakeProvider((only,)))
    result = use_case.execute(ViewTickerOwnershipHistoryRequest(ticker="bbca"))
    assert result is not None
    assert result.ticker == "BBCA"
    assert result.periods == (only,)
    assert result.institution_pct_change is None
    assert result.float_change is None
    assert result.top_holder_pct_change is None
    assert result.as_of == date(2026, 3, 31)


def test_multi_period_computes_latest_vs_previous_deltas():
    newest_first = (
        _comp(date(2026, 6, 30), institution_pct=42.0, individual_pct=26.0, top_holder_pct=31.0),
        _comp(date(2026, 3, 31), institution_pct=40.0, individual_pct=25.0, top_holder_pct=30.0),
    )
    use_case = ViewTickerOwnershipHistoryUseCase(_FakeProvider(newest_first))
    result = use_case.execute(ViewTickerOwnershipHistoryRequest(ticker="BBCA"))
    assert result is not None
    # oldest -> newest
    assert [p.report_date for p in result.periods] == [date(2026, 3, 31), date(2026, 6, 30)]
    assert result.institution_pct_change == 2.0
    assert result.float_change == 3.0  # (42+26) - (40+25)
    assert result.top_holder_pct_change == 1.0
    assert result.as_of == date(2026, 6, 30)


def test_limit_clamped_to_max_and_ticker_uppercased():
    fake = _FakeProvider(())
    use_case = ViewTickerOwnershipHistoryUseCase(fake)
    use_case.execute(ViewTickerOwnershipHistoryRequest(ticker="bbca", limit=999))
    assert fake.calls[0] == ("BBCA", MAX_LIMIT, None)


def test_as_of_date_forwarded_to_provider():
    fake = _FakeProvider(())
    use_case = ViewTickerOwnershipHistoryUseCase(fake)
    cutoff = date(2025, 1, 15)
    use_case.execute(ViewTickerOwnershipHistoryRequest(ticker="BBCA", as_of_date=cutoff))
    assert fake.calls[0] == ("BBCA", 8, cutoff)
