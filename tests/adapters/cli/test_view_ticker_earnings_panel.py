"""Unit tests for earnings panel helpers on the ticker dashboard."""

from datetime import datetime

from src.adapters.cli.view_ticker_valuation_display import (
    _earnings_surprise_cell,
    _earnings_yoy_cell,
)
from src.domain.value_objects.earnings_record import EarningsRecord


def _record(**overrides) -> EarningsRecord:
    base = dict(
        ticker="BBCA",
        year=2026,
        quarter=1,
        eps_actual=119.12,
        eps_estimate=None,
        eps_surprise_pct=None,
        eps_yoy_change=3.81,
        eps_prev_year=114.75,
        fetched_at=datetime(2026, 7, 22, 6, 27, 12),
    )
    base.update(overrides)
    return EarningsRecord(**base)


def test_earnings_yoy_cell_colors_positive_growth():
    cell = _earnings_yoy_cell(_record())
    assert "+3.8%" in cell.plain
    assert "green" in str(cell.style)


def test_earnings_surprise_cell_beat_and_miss():
    beat = _earnings_surprise_cell(_record(eps_surprise_pct=5.5))
    miss = _earnings_surprise_cell(_record(eps_surprise_pct=-2.0))
    none = _earnings_surprise_cell(_record(eps_surprise_pct=None))

    assert "BEAT +5.5%" in beat.plain
    assert "MISS -2.0%" in miss.plain
    assert none.plain == "\u2014"
