"""
Point-in-time cutoff (`as_of_date`) tests for ComputeSMA/ComputeEMA/ComputeRSI.

`as_of_date: date | None` is a hard inclusive cutoff on the compute use
cases: None means "live" (latest cached candle); a value bounds the upper
anchor to `min(latest_date, as_of_date)` and no candle dated after it may be
read or retained.

All dates are FIXED (never `date.today()`) so cutoff-after-cache-head cases
are deterministic. A single long, consistently-priced candle series (~260
days) provides enough warm-up history for SMA(20)/EMA(20, 2x warm-up)/RSI(14,
3x warm-up) regardless of where the cutoff lands.

All tests run offline against a local in-memory MockRepository.
"""

from datetime import date, timedelta
from decimal import Decimal

from src.application.use_case.compute_ema_use_case import ComputeEMARequest, ComputeEMAUseCase
from src.application.use_case.compute_rsi_use_case import ComputeRSIRequest, ComputeRSIUseCase
from src.application.use_case.compute_sma_use_case import ComputeSMARequest, ComputeSMAUseCase
from src.domain.entities.candle import Candle
from src.domain.ports.market_data_repository import MarketDataRepository

_START = date(2026, 1, 1)
_COUNT = 260
_CUTOFF = _START + timedelta(days=150)  # mid-history cutoff


def make_candle(ticker: str, day: date, price: str) -> Candle:
    """Create a test candle at a fixed date."""
    return Candle(
        ticker=ticker,
        date=day,
        open=Decimal(price),
        high=Decimal(price),
        low=Decimal(price),
        close=Decimal(price),
        volume=100000,
    )


def make_series(ticker: str, count: int = _COUNT, start: date = _START) -> list[Candle]:
    """Deterministic, mildly trending candle series over fixed calendar dates."""
    return [make_candle(ticker, start + timedelta(days=i), str(100 + i)) for i in range(count)]


class MockRepository(MarketDataRepository):
    """Mirrors tests/application/use_case/test_compute_sma.py MockRepository."""

    def __init__(self, candles: list[Candle] | None = None):
        self._candles = candles or []

    def get_candles(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Candle]:
        filtered = [c for c in self._candles if c.ticker == ticker.upper()]
        if start_date:
            filtered = [c for c in filtered if c.date >= start_date]
        if end_date:
            filtered = [c for c in filtered if c.date <= end_date]
        return sorted(filtered, key=lambda c: c.date)

    def save_candles(self, candles: list[Candle]) -> None:
        pass

    def has_data(self, ticker: str, start_date: date, end_date: date) -> bool:
        return len(self._candles) > 0

    def get_date_range(self, ticker: str) -> tuple[date, date] | None:
        filtered = [c for c in self._candles if c.ticker == ticker.upper()]
        if not filtered:
            return None
        sorted_candles = sorted(filtered, key=lambda c: c.date)
        return (sorted_candles[0].date, sorted_candles[-1].date)


# --- SMA ---------------------------------------------------------------------


class TestComputeSMAPitCutoff:
    def test_cutoff_excludes_later_values(self):
        candles = make_series("BBCA")
        repository = MockRepository(candles)
        use_case = ComputeSMAUseCase(repository)

        unbounded = use_case.execute(ComputeSMARequest(ticker="BBCA", period=20))
        bounded = use_case.execute(ComputeSMARequest(ticker="BBCA", period=20, as_of_date=_CUTOFF))

        assert bounded.has_values
        assert all(d <= _CUTOFF for d, _ in bounded.values)
        last_date, last_value = bounded.values[-1]
        assert last_date <= _CUTOFF
        unbounded_by_date = dict(unbounded.values)
        assert unbounded_by_date[last_date] == last_value

    def test_live_none_matches_default(self):
        candles = make_series("BBCA")
        repository = MockRepository(candles)
        use_case = ComputeSMAUseCase(repository)

        explicit_none = use_case.execute(
            ComputeSMARequest(ticker="BBCA", period=20, as_of_date=None)
        )
        omitted = use_case.execute(ComputeSMARequest(ticker="BBCA", period=20))

        assert explicit_none.values == omitted.values

    def test_cutoff_before_all_data_returns_empty(self):
        candles = make_series("BBCA")
        repository = MockRepository(candles)
        use_case = ComputeSMAUseCase(repository)

        response = use_case.execute(
            ComputeSMARequest(ticker="BBCA", period=20, as_of_date=_START - timedelta(days=1))
        )

        assert response.values == []
        assert response.date_range is None

    def test_cutoff_after_cache_head_equals_live(self):
        candles = make_series("BBCA")
        repository = MockRepository(candles)
        use_case = ComputeSMAUseCase(repository)
        latest = candles[-1].date

        live = use_case.execute(ComputeSMARequest(ticker="BBCA", period=20, as_of_date=None))
        beyond_head = use_case.execute(
            ComputeSMARequest(ticker="BBCA", period=20, as_of_date=latest + timedelta(days=30))
        )

        assert beyond_head.values == live.values


# --- EMA ---------------------------------------------------------------------


class TestComputeEMAPitCutoff:
    def test_cutoff_excludes_later_values(self):
        candles = make_series("BBCA")
        repository = MockRepository(candles)
        use_case = ComputeEMAUseCase(repository)

        unbounded = use_case.execute(ComputeEMARequest(ticker="BBCA", period=20))
        bounded = use_case.execute(ComputeEMARequest(ticker="BBCA", period=20, as_of_date=_CUTOFF))

        assert bounded.has_values
        assert all(d <= _CUTOFF for d, _ in bounded.values)
        last_date, last_value = bounded.values[-1]
        assert last_date <= _CUTOFF
        unbounded_by_date = dict(unbounded.values)
        assert unbounded_by_date[last_date] == last_value

    def test_live_none_matches_default(self):
        candles = make_series("BBCA")
        repository = MockRepository(candles)
        use_case = ComputeEMAUseCase(repository)

        explicit_none = use_case.execute(
            ComputeEMARequest(ticker="BBCA", period=20, as_of_date=None)
        )
        omitted = use_case.execute(ComputeEMARequest(ticker="BBCA", period=20))

        assert explicit_none.values == omitted.values

    def test_cutoff_before_all_data_returns_empty(self):
        candles = make_series("BBCA")
        repository = MockRepository(candles)
        use_case = ComputeEMAUseCase(repository)

        response = use_case.execute(
            ComputeEMARequest(ticker="BBCA", period=20, as_of_date=_START - timedelta(days=1))
        )

        assert response.values == []
        assert response.date_range is None

    def test_cutoff_after_cache_head_equals_live(self):
        candles = make_series("BBCA")
        repository = MockRepository(candles)
        use_case = ComputeEMAUseCase(repository)
        latest = candles[-1].date

        live = use_case.execute(ComputeEMARequest(ticker="BBCA", period=20, as_of_date=None))
        beyond_head = use_case.execute(
            ComputeEMARequest(ticker="BBCA", period=20, as_of_date=latest + timedelta(days=30))
        )

        assert beyond_head.values == live.values


# --- RSI ---------------------------------------------------------------------


class TestComputeRSIPitCutoff:
    def test_cutoff_excludes_later_values(self):
        candles = make_series("BBCA")
        repository = MockRepository(candles)
        use_case = ComputeRSIUseCase(repository)

        unbounded = use_case.execute(ComputeRSIRequest(ticker="BBCA", period=14))
        bounded = use_case.execute(ComputeRSIRequest(ticker="BBCA", period=14, as_of_date=_CUTOFF))

        assert bounded.has_values
        assert all(d <= _CUTOFF for d, _ in bounded.values)
        last_date, last_value = bounded.values[-1]
        assert last_date <= _CUTOFF
        unbounded_by_date = dict(unbounded.values)
        assert unbounded_by_date[last_date] == last_value

    def test_live_none_matches_default(self):
        candles = make_series("BBCA")
        repository = MockRepository(candles)
        use_case = ComputeRSIUseCase(repository)

        explicit_none = use_case.execute(
            ComputeRSIRequest(ticker="BBCA", period=14, as_of_date=None)
        )
        omitted = use_case.execute(ComputeRSIRequest(ticker="BBCA", period=14))

        assert explicit_none.values == omitted.values

    def test_cutoff_before_all_data_returns_empty(self):
        candles = make_series("BBCA")
        repository = MockRepository(candles)
        use_case = ComputeRSIUseCase(repository)

        response = use_case.execute(
            ComputeRSIRequest(ticker="BBCA", period=14, as_of_date=_START - timedelta(days=1))
        )

        assert response.values == []
        assert response.date_range is None

    def test_cutoff_after_cache_head_equals_live(self):
        candles = make_series("BBCA")
        repository = MockRepository(candles)
        use_case = ComputeRSIUseCase(repository)
        latest = candles[-1].date

        live = use_case.execute(ComputeRSIRequest(ticker="BBCA", period=14, as_of_date=None))
        beyond_head = use_case.execute(
            ComputeRSIRequest(ticker="BBCA", period=14, as_of_date=latest + timedelta(days=30))
        )

        assert beyond_head.values == live.values
