"""Tests for PreOpenScreenUseCase — IEP floor filter, speculative symbol filter, offer side."""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.application.use_case.pre_open_screen_use_case import (
    PreOpenScreenConfig,
    PreOpenScreenRequest,
    PreOpenScreenUseCase,
)
from src.domain.entities.candle import Candle
from src.domain.value_objects.screener_result import MoverData, OrderBookBid, OrderBookTopOfBook


def _make_candles(ticker: str, n: int = 30) -> list[Candle]:
    """Return n daily candles so ATR/RSI have enough history to pass the min_history_days gate."""
    base = date(2026, 1, 1)
    return [
        Candle(
            ticker=ticker,
            date=base + timedelta(days=i),
            open=Decimal("5000"),
            high=Decimal("5100"),
            low=Decimal("4900"),
            close=Decimal("5050"),
            volume=1_000_000,
        )
        for i in range(n)
    ]


def _make_use_case(movers: list[MoverData], candle_count: int = 30) -> PreOpenScreenUseCase:
    """Build a PreOpenScreenUseCase with stubbed dependencies.

    - browser: returns the given movers; order book not called (fast_mode=True)
    - market_repo: returns candle_count mock candles per ticker (default 30)
    - registry: returns empty indicator lists (no ATR/RSI/SMA computed)
    - broker_repository: None (accumulation/FVWAP signals skipped)
    """
    browser = MagicMock()
    browser.fetch_preopen_movers.return_value = movers
    browser.fetch_order_book_best_bid.return_value = None

    market_repo = MagicMock()
    market_repo.get_candles.side_effect = lambda ticker: _make_candles(ticker, candle_count)

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
        MoverData("PPRO", 450_000, iep=75),
        MoverData("TAXI", 350_000, iep=60),
    ]
    uc = _make_use_case(movers)
    response = uc.execute(PreOpenScreenRequest(_config(iep_min=100)))

    assert _tickers(response) == ["BBCA"]
    assert any("IEP floor" in w and "filtered out 2" in w for w in response.warnings)


def test_iep_floor_passes_none_iep():
    """Movers with iep=None are not penalised — IEP not captured ≠ low price."""
    movers = [
        MoverData("BBCA", 300_000, iep=None),
        MoverData("BBRI", 200_000, iep=75),
    ]
    uc = _make_use_case(movers)
    response = uc.execute(PreOpenScreenRequest(_config(iep_min=100)))

    assert "BBCA" in _tickers(response)
    assert "BBRI" not in _tickers(response)
    assert any("filtered out 1" in w for w in response.warnings)


def test_iep_floor_disabled_when_none():
    """iep_min=None means no floor — all movers reach the candidate loop."""
    movers = [
        MoverData("BBCA", 300_000, iep=5_900),
        MoverData("PPRO", 450_000, iep=75),
    ]
    uc = _make_use_case(movers)
    response = uc.execute(PreOpenScreenRequest(_config(iep_min=None)))

    tickers = _tickers(response)
    assert "BBCA" in tickers
    assert "PPRO" in tickers
    assert not any("IEP floor" in w for w in response.warnings)


# ── Speculative symbol filter ─────────────────────────────────────────────────


def test_speculative_filter_excludes_warrants():
    """Warrants (-W suffix) are excluded from the pipeline."""
    movers = [
        MoverData("BBCA", 300_000),
        MoverData("BBCA-W", 500_000),
    ]
    uc = _make_use_case(movers)
    response = uc.execute(PreOpenScreenRequest(_config()))

    assert "BBCA" in _tickers(response)
    assert "BBCA-W" not in _tickers(response)
    assert any("SKIP_SPECULATIVE" in w and "BBCA-W" in w for w in response.warnings)


def test_speculative_filter_excludes_rights():
    """Rights (-R suffix) are excluded from the pipeline."""
    movers = [MoverData("INET-R", 200_000)]
    uc = _make_use_case(movers)
    response = uc.execute(PreOpenScreenRequest(_config()))

    assert _tickers(response) == []
    assert any("SKIP_SPECULATIVE" in w for w in response.warnings)


def test_speculative_filter_excludes_insufficient_history():
    """Tickers with < min_history_days candles are excluded."""
    movers = [
        MoverData("NEWIPO", 150_000),
        MoverData("BBCA", 300_000),
    ]
    # NEWIPO has only 5 candles; BBCA has 30
    browser = MagicMock()
    browser.fetch_preopen_movers.return_value = movers
    browser.fetch_order_book_best_bid.return_value = None
    market_repo = MagicMock()
    market_repo.get_candles.side_effect = lambda t: _make_candles(t, 5 if t == "NEWIPO" else 30)
    registry = MagicMock()
    registry.compute.return_value = []
    uc = PreOpenScreenUseCase(browser=browser, repository=market_repo, registry=registry)

    response = uc.execute(PreOpenScreenRequest(_config()))

    assert "NEWIPO" not in _tickers(response)
    assert "BBCA" in _tickers(response)
    assert any("SKIP_SPECULATIVE" in w and "NEWIPO" in w for w in response.warnings)


def test_speculative_filter_disabled_via_pattern():
    """Setting exclude_suffix_pattern to empty string disables suffix filtering."""
    movers = [MoverData("BBCA-W", 300_000)]
    uc = _make_use_case(movers)
    cfg = PreOpenScreenConfig(fast_mode=True, exclude_suffix_pattern="")
    response = uc.execute(PreOpenScreenRequest(cfg))

    # -W passes regex check (pattern is empty = never matches), but still needs candles
    assert "BBCA-W" in _tickers(response)


# ── Offer-side order book (Step 5 — offer gap closure) ───────────────────────


def _make_use_case_normal_mode(
    movers: list[MoverData], tob: OrderBookTopOfBook | None
) -> PreOpenScreenUseCase:
    """Build use case in normal mode (not fast) with a stubbed fetch_order_book_top_of_book."""
    browser = MagicMock()
    browser.fetch_preopen_movers.return_value = movers
    browser.fetch_order_book_top_of_book.return_value = tob

    market_repo = MagicMock()
    market_repo.get_candles.side_effect = lambda ticker: _make_candles(ticker)

    registry = MagicMock()
    registry.compute.return_value = []

    return PreOpenScreenUseCase(
        browser=browser,
        repository=market_repo,
        registry=registry,
        broker_repository=None,
    )


def _normal_config() -> PreOpenScreenConfig:
    return PreOpenScreenConfig(fast_mode=False)


def test_offer_side_stored_on_candidate():
    bid = OrderBookBid(price=Decimal("5000"), volume=200)
    offer = OrderBookBid(price=Decimal("5025"), volume=150)
    tob = OrderBookTopOfBook(bid=bid, offer=offer)

    uc = _make_use_case_normal_mode([MoverData("BBCA", 300_000)], tob)
    response = uc.execute(PreOpenScreenRequest(_normal_config()))

    c = response.result.candidates[0]
    assert c.best_offer == Decimal("5025")
    assert c.best_offer_lots == 150


def test_spread_pct_computed_correctly():
    bid = OrderBookBid(price=Decimal("5000"), volume=200)
    offer = OrderBookBid(price=Decimal("5025"), volume=150)
    tob = OrderBookTopOfBook(bid=bid, offer=offer)

    uc = _make_use_case_normal_mode([MoverData("BBCA", 300_000)], tob)
    response = uc.execute(PreOpenScreenRequest(_normal_config()))

    c = response.result.candidates[0]
    # spread = (5025 - 5000) / 5000 * 100 = 0.50%
    assert c.spread_pct == Decimal("0.50")
    assert c.spread_label == "0.50%"


def test_bid_offer_imbalance_computed():
    bid = OrderBookBid(price=Decimal("5000"), volume=1000)
    offer = OrderBookBid(price=Decimal("5025"), volume=500)
    tob = OrderBookTopOfBook(bid=bid, offer=offer)

    uc = _make_use_case_normal_mode([MoverData("BBCA", 300_000)], tob)
    response = uc.execute(PreOpenScreenRequest(_normal_config()))

    c = response.result.candidates[0]
    # imbalance = 1000 / (1000 + 500) = 0.667
    assert c.bid_offer_imbalance == pytest.approx(0.667, abs=0.001)


def test_offer_none_when_not_available():
    """When offer side is absent, spread_pct and bid_offer_imbalance stay None."""
    bid = OrderBookBid(price=Decimal("5000"), volume=200)
    tob = OrderBookTopOfBook(bid=bid, offer=None)

    uc = _make_use_case_normal_mode([MoverData("BBCA", 300_000)], tob)
    response = uc.execute(PreOpenScreenRequest(_normal_config()))

    c = response.result.candidates[0]
    assert c.best_offer is None
    assert c.spread_pct is None
    assert c.bid_offer_imbalance is None
    assert c.spread_label == "—"


def test_gap_pct_unchanged_uses_bid():
    """gap_pct must still be computed from bid.price only, not offer."""
    bid = OrderBookBid(price=Decimal("5050"), volume=200)
    offer = OrderBookBid(price=Decimal("5075"), volume=100)
    tob = OrderBookTopOfBook(bid=bid, offer=offer)

    uc = _make_use_case_normal_mode([MoverData("BBCA", 300_000)], tob)
    response = uc.execute(PreOpenScreenRequest(_normal_config()))

    c = response.result.candidates[0]
    # gap_pct = (bid - prev_close) / prev_close * 100
    # prev_close = candle close = 5050; bid = 5050 → gap = 0.00%
    assert c.gap_pct == Decimal("0.00")


# ── ManualBrowserDataProvider offer fallback ──────────────────────────────────


def test_manual_provider_top_of_book_returns_bid_no_offer():
    """ManualBrowserDataProvider.fetch_order_book_top_of_book wraps bid with offer=None."""
    from src.infrastructure.browser.stockbit_browser_provider import ManualBrowserDataProvider

    movers_json = [{"ticker": "BBCA", "iev": 300_000}]
    order_books_json = {"BBCA": {"price": 5000, "volume": 200}}
    provider = ManualBrowserDataProvider.from_json(movers_json, order_books_json)
    assert provider.provides_live_preopen_data is False

    tob = provider.fetch_order_book_top_of_book("BBCA")
    assert tob is not None
    assert tob.bid is not None
    assert tob.bid.price == Decimal("5000")
    assert tob.bid.volume == 200
    assert tob.offer is None


def test_manual_provider_top_of_book_returns_none_when_no_bid():
    from src.infrastructure.browser.stockbit_browser_provider import ManualBrowserDataProvider

    provider = ManualBrowserDataProvider.from_json([{"ticker": "BBCA", "iev": 300_000}])
    assert provider.fetch_order_book_top_of_book("BBCA") is None


def test_floor_price_guard_filters_out_goto_at_fifty():
    """Movers with prev_close <= 50 (such as GOTO at 50) have entry_price <= stop_loss_price

    (capped at 50) and are skipped entirely.
    """
    movers = [MoverData("GOTO", 300_000, iep=50)]

    market_repo = MagicMock()
    market_repo.get_candles.return_value = [
        Candle(
            ticker="GOTO",
            date=date(2026, 1, 1),
            open=Decimal("50"),
            high=Decimal("50"),
            low=Decimal("50"),
            close=Decimal("50"),
            volume=1_000_000,
        )
    ]

    browser = MagicMock()
    browser.fetch_preopen_movers.return_value = movers
    browser.fetch_order_book_best_bid.return_value = None

    registry = MagicMock()
    registry.compute.return_value = []

    uc = PreOpenScreenUseCase(
        browser=browser,
        repository=market_repo,
        registry=registry,
        broker_repository=None,
    )

    config = PreOpenScreenConfig(fast_mode=True, min_history_days=1)
    response = uc.execute(PreOpenScreenRequest(config))

    assert "GOTO" not in [c.ticker for c in response.result.candidates]
    assert any("GOTO: SKIP_FLOOR" in w for w in response.warnings)
