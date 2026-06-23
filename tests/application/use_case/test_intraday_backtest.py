"""
Tests for walk-forward intraday backtest.

Uses in-memory repository stubs and a controllable IndicatorRegistry to keep
ATR/RSI/SMA deterministic. The candidate must reach the ENTER (or WAIT) branch
in ConfirmIntradayOpenUseCase, so candles + indicator values are tuned so that:

  - opening_price lands inside [entry_range_low, entry_range_high]
  - trend = BULLISH for ENTER, NEUTRAL for WAIT
  - accum_tag != "DISTRIBUTING"
  - stop_pct <= max_stop_pct
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.application.services.indicator_registry import IndicatorRegistry
from src.application.use_case.intraday_backtest_use_case import (
    IntradayBacktestRequest,
    IntradayBacktestUseCase,
)
from src.domain.entities.broker_flow import BrokerSummary
from src.domain.entities.candle import Candle
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository
from src.infrastructure.persistence.sqlite_iev_repository import IEVSnapshot

# ── Repository stubs ──────────────────────────────────────────────────────────


class InMemoryMarketRepository(MarketDataRepository):
    def __init__(self, candles: list[Candle]) -> None:
        self._candles = list(candles)

    def save_candles(self, candles: list[Candle]) -> None:
        self._candles.extend(candles)

    def get_candles(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Candle]:
        rows = [c for c in self._candles if c.ticker == ticker.upper()]
        if start_date is not None:
            rows = [c for c in rows if c.date >= start_date]
        if end_date is not None:
            rows = [c for c in rows if c.date <= end_date]
        return sorted(rows, key=lambda c: c.date)

    def has_data(self, ticker: str, start_date: date, end_date: date) -> bool:
        rng = self.get_date_range(ticker)
        return bool(rng and rng[0] <= start_date and rng[1] >= end_date)

    def get_date_range(self, ticker: str) -> tuple[date, date] | None:
        rows = self.get_candles(ticker)
        if not rows:
            return None
        return rows[0].date, rows[-1].date


class InMemoryBrokerRepository(BrokerDataRepository):
    def __init__(self, summaries: list[BrokerSummary] | None = None) -> None:
        self._summaries = list(summaries or [])

    def save_broker_summary(self, summary: BrokerSummary) -> None:
        self._summaries.append(summary)

    def save_broker_summaries(self, summaries: list[BrokerSummary]) -> None:
        self._summaries.extend(summaries)

    def get_broker_summary(
        self, ticker: str, target_date: date
    ) -> BrokerSummary | None:
        for s in self._summaries:
            if s.ticker == ticker.upper() and s.date == target_date:
                return s
        return None

    def get_broker_summaries(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[BrokerSummary]:
        rows = [s for s in self._summaries if s.ticker == ticker.upper()]
        if start_date is not None:
            rows = [s for s in rows if s.date >= start_date]
        if end_date is not None:
            rows = [s for s in rows if s.date <= end_date]
        return sorted(rows, key=lambda s: s.date)

    def has_data(self, ticker: str, start_date: date, end_date: date) -> bool:
        rng = self.get_date_range(ticker)
        return bool(rng and rng[0] <= start_date and rng[1] >= end_date)

    def get_date_range(self, ticker: str) -> tuple[date, date] | None:
        rows = self.get_broker_summaries(ticker)
        if not rows:
            return None
        return rows[0].date, rows[-1].date


# ── Indicator registry stub ───────────────────────────────────────────────────


class StubIndicatorRegistry(IndicatorRegistry):
    """Returns fixed ATR / RSI / SMA values regardless of candles passed in."""

    def __init__(
        self,
        atr: Decimal | None = Decimal("2"),
        rsi: Decimal | None = Decimal("50"),
        sma: Decimal | None = Decimal("99"),
    ) -> None:
        super().__init__()
        self._atr = atr
        self._rsi = rsi
        self._sma = sma

    def compute(  # type: ignore[override]
        self,
        name: str,
        candles: list[Candle],
        period: int,
        price_field: str = "close",
    ):
        if not candles:
            return []
        last_date = candles[-1].date
        n = name.upper()
        if n == "ATR":
            return [(last_date, self._atr)] if self._atr is not None else []
        if n == "RSI":
            return [(last_date, self._rsi)] if self._rsi is not None else []
        if n == "SMA":
            return [(last_date, self._sma)] if self._sma is not None else []
        return []


# ── Builders ──────────────────────────────────────────────────────────────────


def _candle(
    ticker: str,
    day: date,
    open_: Decimal,
    high: Decimal,
    low: Decimal,
    close: Decimal,
) -> Candle:
    return Candle(
        ticker=ticker,
        date=day,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=1_000_000,
    )


def _flat(ticker: str, day: date, price: Decimal) -> Candle:
    return _candle(ticker, day, price, price, price, price)


def _history(
    ticker: str,
    end_day: date,
    days: int = 30,
    base_price: Decimal = Decimal("100"),
) -> list[Candle]:
    """Build `days` flat historical candles ending on `end_day` (inclusive).

    The last candle is the "previous" candle the backtest reads as prev_close /
    prev_high / prev_low — we override that one separately when needed.
    """
    candles = []
    for i in range(days):
        day = end_day - timedelta(days=days - 1 - i)
        candles.append(_flat(ticker, day, base_price))
    return candles


def _history_with_prev(
    ticker: str,
    prev_day: date,
    prev_close: Decimal = Decimal("100"),
    prev_high: Decimal = Decimal("105"),
    prev_low: Decimal = Decimal("98"),
    days: int = 30,
) -> list[Candle]:
    """History with a specific final ('previous') candle controlling prev_high."""
    candles = _history(ticker, prev_day - timedelta(days=1), days=days - 1, base_price=prev_close)
    candles.append(_candle(ticker, prev_day, prev_close, prev_high, prev_low, prev_close))
    return candles


def _backed_summaries(
    ticker: str, end_day: date, days: int = 7
) -> list[BrokerSummary]:
    """Build `days` consecutive net-foreign-buy summaries ending on end_day."""
    out = []
    for i in range(days):
        day = end_day - timedelta(days=days - 1 - i)
        out.append(BrokerSummary(
            ticker=ticker,
            date=day,
            top_buyers=(),
            top_sellers=(),
            foreign_buy_value=Decimal("1000000"),
            foreign_sell_value=Decimal("100000"),
            foreign_buy_lot=10_000,
            foreign_sell_lot=1_000,
            total_value=Decimal("2000000"),
            total_lot=20_000,
        ))
    return out


# ── Common scaffolding ────────────────────────────────────────────────────────


PREV_DAY = date(2026, 6, 9)
TRADE_DAY = date(2026, 6, 10)
TICKER = "BBCA"


def _default_request(**overrides) -> IntradayBacktestRequest:
    base = {
        "tickers": [TICKER],
        "start_date": TRADE_DAY,
        "end_date": TRADE_DAY,
        "capital": Decimal("100000000"),
        "risk_pct": Decimal("0.01"),
        "max_daily_positions": 3,
        "cost_bps": Decimal("0"),
        "history_days": 30,
    }
    base.update(overrides)
    return IntradayBacktestRequest(**base)


def _build(
    today_candle: Candle,
    *,
    ticker: str = TICKER,
    history: list[Candle] | None = None,
    summaries: list[BrokerSummary] | None = None,
    registry: IndicatorRegistry | None = None,
) -> IntradayBacktestUseCase:
    hist = history if history is not None else _history_with_prev(ticker, PREV_DAY)
    market = InMemoryMarketRepository(hist + [today_candle])
    broker = InMemoryBrokerRepository(summaries if summaries is not None else _backed_summaries(ticker, PREV_DAY))
    reg = registry if registry is not None else StubIndicatorRegistry()
    return IntradayBacktestUseCase(
        market_repository=market,
        broker_repository=broker,
        indicator_registry=reg,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_exit_reason_target_when_high_reaches_prev_high():
    # target = prev_high = 105; stop = prev_close - atr = 98
    # high (106) >= target, low (99) > stop -> "target"
    today = _candle(
        TICKER, TRADE_DAY,
        open_=Decimal("100"),
        high=Decimal("106"),
        low=Decimal("99"),
        close=Decimal("101"),
    )
    use_case = _build(today)
    resp = use_case.execute(_default_request())

    assert resp.trade_count == 1
    trade = resp.trades[0]
    assert trade.exit_reason == "target"
    assert trade.exit_price == Decimal("105")
    assert trade.target_price == Decimal("105")
    assert trade.stop_price == Decimal("98")
    assert trade.same_day_both_breached is False


def test_exit_reason_stop_when_low_breaches_stop():
    # high (104) < target (105), low (97) <= stop (98) -> "stop"
    today = _candle(
        TICKER, TRADE_DAY,
        open_=Decimal("100"),
        high=Decimal("104"),
        low=Decimal("97"),
        close=Decimal("99"),
    )
    use_case = _build(today)
    resp = use_case.execute(_default_request())

    assert resp.trade_count == 1
    trade = resp.trades[0]
    assert trade.exit_reason == "stop"
    assert trade.exit_price == Decimal("98")
    assert trade.same_day_both_breached is False


def test_exit_reason_close_when_neither_stop_nor_target_hit():
    # high (104) < target (105), low (99) > stop (98) -> "close"
    today = _candle(
        TICKER, TRADE_DAY,
        open_=Decimal("100"),
        high=Decimal("104"),
        low=Decimal("99"),
        close=Decimal("102"),
    )
    use_case = _build(today)
    resp = use_case.execute(_default_request())

    assert resp.trade_count == 1
    trade = resp.trades[0]
    assert trade.exit_reason == "close"
    assert trade.exit_price == Decimal("102")


def test_exit_reason_both_assume_stop_when_high_and_low_both_breach():
    # high (106) >= target, low (97) <= stop -> "both_assume_stop"
    today = _candle(
        TICKER, TRADE_DAY,
        open_=Decimal("100"),
        high=Decimal("106"),
        low=Decimal("97"),
        close=Decimal("100"),
    )
    use_case = _build(today)
    resp = use_case.execute(_default_request())

    assert resp.trade_count == 1
    trade = resp.trades[0]
    assert trade.exit_reason == "both_assume_stop"
    assert trade.exit_price == Decimal("98")  # stop_price
    assert trade.same_day_both_breached is True


def test_include_wait_false_skips_wait_decisions():
    # NEUTRAL trend -> WAIT (SMA > close so above_sma=False)
    today = _candle(
        TICKER, TRADE_DAY,
        open_=Decimal("100"),
        high=Decimal("106"),
        low=Decimal("99"),
        close=Decimal("101"),
    )
    # sma=101 > close=100 -> not above_sma -> NEUTRAL with rsi=50
    registry = StubIndicatorRegistry(sma=Decimal("101"))
    use_case = _build(today, registry=registry)
    resp = use_case.execute(_default_request(include_wait=False))

    assert resp.trade_count == 0


def test_include_wait_true_trades_wait_decisions():
    # Same NEUTRAL setup as above, but include_wait=True traps WAIT into a trade
    today = _candle(
        TICKER, TRADE_DAY,
        open_=Decimal("100"),
        high=Decimal("106"),
        low=Decimal("99"),
        close=Decimal("101"),
    )
    registry = StubIndicatorRegistry(sma=Decimal("101"))
    use_case = _build(today, registry=registry)
    resp = use_case.execute(_default_request(include_wait=True))

    assert resp.trade_count == 1
    assert resp.trades[0].decision == "WAIT"


def test_max_daily_positions_one_caps_trades_per_day():
    # Two tickers both ENTER on the same day -> only 1 trade with cap=1
    tickers = ["BBCA", "BBRI"]
    today_candles = [
        _candle(t, TRADE_DAY, Decimal("100"), Decimal("106"), Decimal("99"), Decimal("101"))
        for t in tickers
    ]
    history = []
    summaries = []
    for t in tickers:
        history.extend(_history_with_prev(t, PREV_DAY))
        summaries.extend(_backed_summaries(t, PREV_DAY))

    market = InMemoryMarketRepository(history + today_candles)
    broker = InMemoryBrokerRepository(summaries)
    use_case = IntradayBacktestUseCase(
        market_repository=market,
        broker_repository=broker,
        indicator_registry=StubIndicatorRegistry(),
    )

    resp = use_case.execute(IntradayBacktestRequest(
        tickers=tickers,
        start_date=TRADE_DAY,
        end_date=TRADE_DAY,
        max_daily_positions=1,
        cost_bps=Decimal("0"),
        history_days=30,
    ))

    assert resp.trade_count == 1


def test_cost_arithmetic_and_gross_vs_net_for_winner():
    # target hit: entry=100, exit=105, cost_bps=20 (0.20% per side)
    today = _candle(
        TICKER, TRADE_DAY,
        open_=Decimal("100"),
        high=Decimal("106"),
        low=Decimal("99"),
        close=Decimal("101"),
    )
    use_case = _build(today)
    resp = use_case.execute(_default_request(cost_bps=Decimal("20")))

    assert resp.trade_count == 1
    trade = resp.trades[0]

    shares = Decimal(trade.shares)
    entry = trade.entry_price
    exit_p = trade.exit_price
    entry_cost = shares * entry * Decimal("20") / Decimal("10000")
    exit_cost = shares * exit_p * Decimal("20") / Decimal("10000")
    expected_cost_total = entry_cost + exit_cost
    expected_pnl = (exit_p - entry) * shares - expected_cost_total

    assert trade.cost_total == expected_cost_total
    assert trade.pnl == expected_pnl
    # For a winner, gross return (no cost) is higher than net (after cost)
    assert trade.gross_return_pct > trade.net_return_pct
    # And gross should be exactly (105 - 100) / 100 * 100 = 5.0
    assert trade.gross_return_pct == 5.0


def test_r_multiple_equals_pnl_over_initial_risk():
    today = _candle(
        TICKER, TRADE_DAY,
        open_=Decimal("100"),
        high=Decimal("106"),
        low=Decimal("99"),
        close=Decimal("101"),
    )
    use_case = _build(today)
    resp = use_case.execute(_default_request())

    trade = resp.trades[0]
    initial_risk = Decimal(trade.shares) * (trade.entry_price - trade.stop_price)
    expected_r = round(float(trade.pnl / initial_risk), 3)

    assert trade.r_multiple == expected_r


def test_validation_empty_tickers_raises():
    use_case = IntradayBacktestUseCase(
        market_repository=InMemoryMarketRepository([]),
        broker_repository=InMemoryBrokerRepository(),
        indicator_registry=StubIndicatorRegistry(),
    )
    with pytest.raises(ValueError, match="ticker"):
        use_case.execute(IntradayBacktestRequest(
            tickers=[],
            start_date=TRADE_DAY,
            end_date=TRADE_DAY,
        ))


def test_validation_start_after_end_raises():
    use_case = IntradayBacktestUseCase(
        market_repository=InMemoryMarketRepository([]),
        broker_repository=InMemoryBrokerRepository(),
        indicator_registry=StubIndicatorRegistry(),
    )
    with pytest.raises(ValueError, match="start_date"):
        use_case.execute(IntradayBacktestRequest(
            tickers=[TICKER],
            start_date=TRADE_DAY,
            end_date=TRADE_DAY - timedelta(days=1),
        ))


def test_no_broker_data_yields_none_accum_fields_but_trade_completes():
    today = _candle(
        TICKER, TRADE_DAY,
        open_=Decimal("100"),
        high=Decimal("106"),
        low=Decimal("99"),
        close=Decimal("101"),
    )
    use_case = _build(today, summaries=[])  # empty broker repo
    resp = use_case.execute(_default_request())

    assert resp.trade_count == 1
    trade = resp.trades[0]
    assert trade.accum_tag is None
    assert trade.accum_score is None
    assert trade.accum_streak is None
    assert trade.exit_reason == "target"


def test_insufficient_history_skips_ticker_silently():
    # min_required = max(14, 14, 20) + 2 = 22; provide only 10 candles
    today = _candle(
        TICKER, TRADE_DAY,
        open_=Decimal("100"),
        high=Decimal("106"),
        low=Decimal("99"),
        close=Decimal("101"),
    )
    short_history = _history(TICKER, PREV_DAY, days=10)
    use_case = _build(today, history=short_history)

    # Should not raise, just produces no trades
    resp = use_case.execute(_default_request())
    assert resp.trade_count == 0


def test_ranking_picks_higher_accum_score_when_capped():
    tickers = ["BBCA", "BBRI"]
    today_candles = [
        _candle(t, TRADE_DAY, Decimal("100"), Decimal("106"), Decimal("99"), Decimal("101"))
        for t in tickers
    ]
    history = []
    for t in tickers:
        history.extend(_history_with_prev(t, PREV_DAY))

    # BBCA: 7 consecutive backed days -> high accum_score (BACKED)
    # BBRI: only 4 of 7 backed (recent 4) -> lower accum_score (UNCONFIRMED)
    summaries = []
    summaries.extend(_backed_summaries("BBCA", PREV_DAY, days=7))
    # 3 non-accumulating older days + 4 accumulating recent days for BBRI
    for i in range(3):
        day = PREV_DAY - timedelta(days=6 - i)
        summaries.append(BrokerSummary(
            ticker="BBRI",
            date=day,
            top_buyers=(),
            top_sellers=(),
            foreign_buy_value=Decimal("100000"),
            foreign_sell_value=Decimal("1000000"),  # net sell
            foreign_buy_lot=1_000,
            foreign_sell_lot=10_000,
            total_value=Decimal("2000000"),
            total_lot=20_000,
        ))
    for i in range(4):
        day = PREV_DAY - timedelta(days=3 - i)
        summaries.append(BrokerSummary(
            ticker="BBRI",
            date=day,
            top_buyers=(),
            top_sellers=(),
            foreign_buy_value=Decimal("1000000"),
            foreign_sell_value=Decimal("100000"),
            foreign_buy_lot=10_000,
            foreign_sell_lot=1_000,
            total_value=Decimal("2000000"),
            total_lot=20_000,
        ))

    market = InMemoryMarketRepository(history + today_candles)
    broker = InMemoryBrokerRepository(summaries)
    use_case = IntradayBacktestUseCase(
        market_repository=market,
        broker_repository=broker,
        indicator_registry=StubIndicatorRegistry(),
    )

    resp = use_case.execute(IntradayBacktestRequest(
        tickers=tickers,
        start_date=TRADE_DAY,
        end_date=TRADE_DAY,
        max_daily_positions=1,
        cost_bps=Decimal("0"),
        history_days=30,
    ))

    assert resp.trade_count == 1
    chosen = resp.trades[0]
    assert chosen.ticker == "BBCA"
    # And BBCA should have a higher accum_score than what BBRI would have got
    assert chosen.accum_score is not None
    assert chosen.accum_tag == "BACKED"


# ── NCP snapshot in backtest (Step 6) ────────────────────────────────────────


def test_backtest_uses_get_ncp_snapshot():
    """Backtest must call get_ncp_snapshot (not get_snapshot) to filter candidates.

    Setup: two tickers BBCA and BBRI both have candle data, but the IEV repo's
    NCP snapshot only contains BBCA. The backtest should filter BBRI out and only
    trade BBCA.
    """
    tickers = ["BBCA", "BBRI"]
    today_candles = [
        _candle(t, TRADE_DAY, Decimal("100"), Decimal("106"), Decimal("99"), Decimal("101"))
        for t in tickers
    ]
    history: list[Candle] = []
    for t in tickers:
        history.extend(_history_with_prev(t, PREV_DAY))

    market = InMemoryMarketRepository(history + today_candles)
    broker = InMemoryBrokerRepository(
        _backed_summaries("BBCA", PREV_DAY) + _backed_summaries("BBRI", PREV_DAY)
    )

    # IEV repo stub: NCP snapshot contains BBCA only
    iev_repo = MagicMock()
    iev_repo.has_snapshot.return_value = True
    iev_repo.get_ncp_snapshot.return_value = [
        IEVSnapshot(date=TRADE_DAY, ticker="BBCA", iev=450_000, rank=1, iep=5_900)
    ]
    iev_repo.get_snapshot_dates.return_value = [TRADE_DAY]

    uc = IntradayBacktestUseCase(
        market_repository=market,
        broker_repository=broker,
        indicator_registry=StubIndicatorRegistry(),
        iev_repository=iev_repo,
    )

    resp = uc.execute(IntradayBacktestRequest(
        tickers=tickers,
        start_date=TRADE_DAY,
        end_date=TRADE_DAY,
        capital=Decimal("100000000"),
        risk_pct=Decimal("0.01"),
        max_daily_positions=3,
        cost_bps=Decimal("0"),
        history_days=30,
    ))

    # get_ncp_snapshot must have been called (not the legacy get_snapshot)
    iev_repo.get_ncp_snapshot.assert_called_once()
    iev_repo.get_snapshot.assert_not_called()

    # Only BBCA trades — BBRI filtered out by NCP snapshot
    traded_tickers = {t.ticker for t in resp.trades}
    assert "BBCA" in traded_tickers
    assert "BBRI" not in traded_tickers
