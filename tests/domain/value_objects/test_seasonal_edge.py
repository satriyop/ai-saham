from datetime import datetime

import pytest

from src.domain.value_objects.seasonal_edge import SeasonalEdge


def _edge(**overrides: object) -> SeasonalEdge:
    values = {
        "ticker": "BBCA",
        "month": 7,
        "avg_monthly_return_pct": 1.25,
        "win_rate_pct": 60.0,
        "positive_years": 3,
        "total_years": 5,
        "back_years": 5,
        "source": "stockbit",
        "fetched_at": datetime(2026, 7, 1),
    }
    values.update(overrides)
    return SeasonalEdge(**values)


def test_seasonal_edge_accepts_consistent_stockbit_statistics():
    edge = _edge()

    assert edge.score == pytest.approx(0.75)
    assert edge.label == "+1.2% (60%wr, 5y)"
    assert edge.is_tailwind is True
    assert edge.is_headwind is False


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("ticker", "", "Ticker cannot be empty"),
        ("month", 0, "Month must be between 1 and 12"),
        ("month", 13, "Month must be between 1 and 12"),
        ("win_rate_pct", -0.1, "Win rate must be between 0 and 100"),
        ("win_rate_pct", 100.1, "Win rate must be between 0 and 100"),
        ("positive_years", -1, "Positive years cannot be negative"),
        ("total_years", 0, "Total years must be positive"),
        ("back_years", 0, "Back years must be positive"),
    ],
)
def test_seasonal_edge_rejects_invalid_statistics(field: str, value: object, message: str):
    with pytest.raises(ValueError, match=message):
        _edge(**{field: value})


def test_seasonal_edge_rejects_positive_years_above_total_years():
    with pytest.raises(ValueError, match="Positive years cannot exceed total years"):
        _edge(positive_years=6, total_years=5)
