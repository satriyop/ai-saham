"""PIT regression guard for the fundamentals read path.

`34fc4360` fixed a real look-ahead bug on the risk path. This module guards the
same class of bug on the fundamentals side, which is the input to
FundamentalGate (`piotroski_f_score`) and to LiquidityGate's market-cap leg
(`market_cap_idr`).

The invariant: a `company_fundamentals` row dated *after* a session must not be
visible to that session's assessment, whatever wrote it — a live snapshot fetch
or a historical/backfilled row. When nothing is visible on or before the
cutoff, the correct answer is `None` (which the gates turn into
`GateOutcome.UNEVALUABLE`), never the nearest later row.

Layer: Infrastructure
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from src.domain.value_objects.company_fundamentals import CompanyFundamentals
from src.infrastructure.browser.stockbit_fundamentals_cache import (
    StockbitFundamentalsCache,
)

_TICKER = "BBCA"
_SESSION = date(2026, 6, 15)


@pytest.fixture()
def cache(tmp_path) -> StockbitFundamentalsCache:
    built = StockbitFundamentalsCache(tmp_path / "pit.db", cache_ttl_days=30)
    built.ensure_schema()
    return built


def _row(*, fetched_at: datetime, f_score: int, market_cap: int) -> CompanyFundamentals:
    return CompanyFundamentals(
        ticker=_TICKER,
        pe_ratio_ttm=None,
        roe_ttm=None,
        net_profit_margin=None,
        revenue_yoy_growth=None,
        piotroski_f_score=f_score,
        dividend_yield=None,
        week52_high=None,
        week52_low=None,
        near_52w_high_rank=None,
        market_cap_idr=market_cap,
        pbv=None,
        fetched_at=fetched_at,
    )


def test_a_row_dated_after_the_session_is_invisible_to_that_session(cache):
    cache.write(_row(fetched_at=datetime(2026, 7, 8), f_score=8, market_cap=50_000_000_000_000))

    assert cache.read(_TICKER, as_of_date=_SESSION) is None
    # …and is visible once the session is on or after its date.
    later = cache.read(_TICKER, as_of_date=date(2026, 7, 8))
    assert later is not None
    assert later.piotroski_f_score == 8


def test_the_newest_row_at_or_before_the_cutoff_wins_over_a_later_one(cache):
    cache.write(_row(fetched_at=datetime(2026, 5, 1), f_score=3, market_cap=1_000_000_000_000))
    cache.write(_row(fetched_at=datetime(2026, 6, 1), f_score=5, market_cap=2_000_000_000_000))
    cache.write(_row(fetched_at=datetime(2026, 7, 8), f_score=9, market_cap=9_000_000_000_000))

    seen = cache.read(_TICKER, as_of_date=_SESSION)
    assert seen is not None
    assert seen.piotroski_f_score == 5
    assert seen.market_cap_idr == 2_000_000_000_000


def test_a_backfilled_historical_row_obeys_the_same_cutoff(cache):
    """Backfilled rows are dated quarter-end + a publication lag, not today."""
    quarter_end = datetime(2026, 3, 31)
    written = cache.write_historical_rows(
        [
            CompanyFundamentals(
                ticker=_TICKER,
                pe_ratio_ttm=None,
                roe_ttm=None,
                net_profit_margin=12.5,
                revenue_yoy_growth=4.0,
                piotroski_f_score=None,
                dividend_yield=None,
                week52_high=None,
                week52_low=None,
                near_52w_high_rank=None,
                market_cap_idr=None,
                pbv=None,
                fetched_at=quarter_end,
            )
        ]
    )
    assert written == 1

    # quarter_end + 60d = 2026-05-30, so it is public before the session…
    visible = cache.read(_TICKER, as_of_date=_SESSION)
    assert visible is not None
    assert visible.net_profit_margin == 12.5
    # …and invisible to any session before the publication date.
    assert cache.read(_TICKER, as_of_date=date(2026, 5, 29)) is None


def test_a_row_stamped_with_a_future_date_cannot_leak_into_an_earlier_session(cache):
    """The forbidden shortcut: recomputed values stamped with a historical date.

    Even if such a row were written, PIT reads must still bound it by its own
    stored date rather than treating it as always-available.
    """
    cache.write(_row(fetched_at=datetime(2026, 8, 4), f_score=9, market_cap=99_000_000_000_000))

    for session in (date(2026, 6, 2), _SESSION, date(2026, 8, 3)):
        assert cache.read(_TICKER, as_of_date=session) is None


def test_no_visible_row_returns_none_rather_than_the_nearest_later_row(cache):
    cache.write(_row(fetched_at=datetime(2026, 7, 8), f_score=8, market_cap=50_000_000_000_000))
    assert cache.read(_TICKER, as_of_date=date(2026, 6, 2)) is None
