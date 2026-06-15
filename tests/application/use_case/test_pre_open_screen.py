"""Tests for PreOpenScreenUseCase — focused on IEP floor filter logic."""

from unittest.mock import MagicMock

import pytest

from src.application.use_case.pre_open_screen import (
    PreOpenScreenConfig,
    PreOpenScreenRequest,
    PreOpenScreenUseCase,
)
from src.domain.value_objects.screener_result import MoverData


def _make_use_case(movers: list[MoverData]) -> PreOpenScreenUseCase:
    """Build a PreOpenScreenUseCase with stubbed dependencies.

    - browser: returns the given movers; order book not called (fast_mode=True)
    - market_repo: returns empty candles for every ticker
    - registry: returns empty indicator lists (no ATR/RSI/SMA computed)
    - broker_repository: None (accumulation/FVWAP signals skipped)
    """
    browser = MagicMock()
    browser.fetch_preopen_movers.return_value = movers
    browser.fetch_order_book_best_bid.return_value = None

    market_repo = MagicMock()
    market_repo.get_candles.return_value = []  # no cached data → context returns empty

    registry = MagicMock()
    registry.compute.return_value = []

    return PreOpenScreenUseCase(
        browser=browser,
        repository=market_repo,
        registry=registry,
        broker_repository=None,
    )


def _config(iep_min: int | None = None) -> PreOpenScreenConfig:
    return PreOpenScreenConfig(fast_mode=True, iep_min=iep_min)


def _tickers(response) -> list[str]:
    return [c.ticker for c in response.result.candidates]


# ── IEP floor filter (Step 5) ────────────────────────────────────────────────

def test_iep_floor_filters_movers_below_threshold():
    movers = [
        MoverData("BBCA", 300_000, iep=5_900),
        MoverData("PPRO", 450_000, iep=15),
        MoverData("TAXI", 350_000, iep=15),
    ]
    uc = _make_use_case(movers)
    response = uc.execute(PreOpenScreenRequest(_config(iep_min=50)))

    assert _tickers(response) == ["BBCA"]
    assert any("IEP floor" in w and "filtered out 2" in w for w in response.warnings)


def test_iep_floor_passes_none_iep():
    """Movers with iep=None are not penalised — IEP not captured ≠ low price."""
    movers = [
        MoverData("BBCA", 300_000, iep=None),
        MoverData("BBRI", 200_000, iep=10),
    ]
    uc = _make_use_case(movers)
    response = uc.execute(PreOpenScreenRequest(_config(iep_min=50)))

    assert "BBCA" in _tickers(response)
    assert "BBRI" not in _tickers(response)
    assert any("filtered out 1" in w for w in response.warnings)


def test_iep_floor_disabled_when_none():
    """iep_min=None means no floor — all movers reach the candidate loop."""
    movers = [
        MoverData("BBCA", 300_000, iep=5_900),
        MoverData("PPRO", 450_000, iep=15),
    ]
    uc = _make_use_case(movers)
    response = uc.execute(PreOpenScreenRequest(_config(iep_min=None)))

    tickers = _tickers(response)
    assert "BBCA" in tickers
    assert "PPRO" in tickers
    assert not any("IEP floor" in w for w in response.warnings)
