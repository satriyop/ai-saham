"""
Pure helpers for desk-centric views over broker_daily_flow.

Tracked brokers only — not full-market composition.

Layer: Application (Service)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.application.services.institutional_flow_broker_metrics import is_foreign_broker
from src.domain.entities.broker_flow import BrokerDailyFlow, BrokerType


@dataclass(frozen=True)
class DeskTickerNet:
    """One ticker's net for a desk on a resolved window."""

    ticker: str
    net_value: Decimal
    net_lot: int
    buy_value: Decimal
    sell_value: Decimal
    sessions: int


@dataclass(frozen=True)
class DeskDayNet:
    """Desk aggregate net across all cached tickers on one date."""

    date: date
    net_value: Decimal
    net_lot: int
    buy_value: Decimal
    sell_value: Decimal
    ticker_count: int


@dataclass(frozen=True)
class DeskCalendarDay:
    """One session day on the desk calendar (tracked activity only)."""

    date: date
    net_value: Decimal
    buy_value: Decimal
    sell_value: Decimal
    top_ticker: str | None  # max net buy that day for this desk
    top_net: Decimal
    ticker_count: int


def classify_desk_type(
    broker_code: str,
    foreign_broker_codes: frozenset[str] | None,
) -> BrokerType:
    if foreign_broker_codes is None:
        return BrokerType.UNKNOWN
    if is_foreign_broker(broker_code, foreign_broker_codes):
        return BrokerType.FOREIGN
    return BrokerType.LOCAL


def rank_tickers_for_desk(
    flows: list[BrokerDailyFlow],
    *,
    limit: int = 20,
) -> tuple[tuple[DeskTickerNet, ...], tuple[DeskTickerNet, ...]]:
    """
    Aggregate flows by ticker, split net buyers vs net sellers for the desk.

    Buyers: net_value > 0 DESC; sellers: net_value < 0 ASC (most negative first).
    """
    if limit < 1:
        raise ValueError("limit must be >= 1")

    by_ticker: dict[str, list[BrokerDailyFlow]] = {}
    for flow in flows:
        by_ticker.setdefault(flow.ticker.upper(), []).append(flow)

    nets: list[DeskTickerNet] = []
    for ticker, rows in by_ticker.items():
        nets.append(
            DeskTickerNet(
                ticker=ticker,
                net_value=sum((r.net_value for r in rows), Decimal("0")),
                net_lot=sum(r.net_lot for r in rows),
                buy_value=sum((r.buy_value for r in rows), Decimal("0")),
                sell_value=sum((r.sell_value for r in rows), Decimal("0")),
                sessions=len({r.date for r in rows}),
            )
        )

    buyers = sorted(
        (n for n in nets if n.net_value > Decimal("0")),
        key=lambda n: n.net_value,
        reverse=True,
    )
    sellers = sorted(
        (n for n in nets if n.net_value < Decimal("0")),
        key=lambda n: n.net_value,
    )
    return tuple(buyers[:limit]), tuple(sellers[:limit])


def aggregate_desk_by_date(flows: list[BrokerDailyFlow]) -> tuple[DeskDayNet, ...]:
    """Sum desk activity per calendar date across tickers."""
    by_date: dict[date, list[BrokerDailyFlow]] = {}
    for flow in flows:
        by_date.setdefault(flow.date, []).append(flow)

    days: list[DeskDayNet] = []
    for d in sorted(by_date):
        rows = by_date[d]
        days.append(
            DeskDayNet(
                date=d,
                net_value=sum((r.net_value for r in rows), Decimal("0")),
                net_lot=sum(r.net_lot for r in rows),
                buy_value=sum((r.buy_value for r in rows), Decimal("0")),
                sell_value=sum((r.sell_value for r in rows), Decimal("0")),
                ticker_count=len({r.ticker.upper() for r in rows}),
            )
        )
    return tuple(days)


def build_desk_calendar_days(
    flows: list[BrokerDailyFlow],
    *,
    max_sessions: int = 22,
) -> tuple[DeskCalendarDay, ...]:
    """Session days for desk calendar: top stock · net · B/S.

    Sessions = dates with desk activity (not blank calendar days).
    Newest last (chronological). Truncated to last ``max_sessions``.
    Top stock = ticker with highest net_value among net buyers that day;
    if none, highest buy_value ticker.
    """
    if max_sessions < 1:
        raise ValueError("max_sessions must be >= 1")
    by_date: dict[date, list[BrokerDailyFlow]] = {}
    for flow in flows:
        by_date.setdefault(flow.date, []).append(flow)

    days: list[DeskCalendarDay] = []
    for d in sorted(by_date):
        rows = by_date[d]
        net = sum((r.net_value for r in rows), Decimal("0"))
        buy = sum((r.buy_value for r in rows), Decimal("0"))
        sell = sum((r.sell_value for r in rows), Decimal("0"))
        # Prefer strongest net buyer; else top buy_value name
        buyers = [r for r in rows if r.net_value > Decimal("0")]
        if buyers:
            top = max(buyers, key=lambda r: r.net_value)
        else:
            top = max(rows, key=lambda r: r.buy_value)
        days.append(
            DeskCalendarDay(
                date=d,
                net_value=net,
                buy_value=buy,
                sell_value=sell,
                top_ticker=str(top.ticker).upper() if top is not None else None,
                top_net=top.net_value if top is not None else Decimal("0"),
                ticker_count=len({r.ticker.upper() for r in rows}),
            )
        )
    if len(days) > max_sessions:
        days = days[-max_sessions:]
    return tuple(days)


# Default multi-window set for stock→desks (NetX = sum of last X sessions).
STOCK_DESK_NET_WINDOWS: tuple[int, ...] = (3, 5, 7, 10, 20)


@dataclass(frozen=True)
class DeskSessionPulse:
    """Multi-session pulse for desk list/show (cache-derived, not a score)."""

    as_of: date
    day_net: Decimal
    net5: Decimal  # sum of last min(5, n) session nets (compat for desk radar)
    sessions_in_net5: int
    buy_streak: int  # consecutive net-buy sessions ending at as_of (0 if latest ≤ 0)
    delta1: Decimal | None  # day_net − prior session net; None if only one session
    # (window, net_sum, sessions_used) sorted by window ascending
    window_nets: tuple[tuple[int, Decimal, int], ...] = ()

    def net_for(self, window: int) -> Decimal | None:
        """Sum of last min(window, n) session nets, or None if window not computed."""
        for w, net, _n in self.window_nets:
            if w == window:
                return net
        if window == 5:
            return self.net5
        return None

    def sessions_for(self, window: int) -> int:
        for w, _net, n in self.window_nets:
            if w == window:
                return n
        if window == 5:
            return self.sessions_in_net5
        return 0


def desk_session_pulse(
    flows: list[BrokerDailyFlow],
    *,
    net_window: int = 5,
    net_windows: tuple[int, ...] | None = None,
) -> DeskSessionPulse | None:
    """Build DayNet / NetX / buy-streak / Δ1 from distinct sessions with data.

    Sessions = calendar dates present for the desk (not blank calendar days).

    ``net_windows`` requests multiple NetX sums (e.g. 3/5/7/10/20). When omitted,
    only ``net_window`` (default 5) is computed — same as legacy Net5 radar.
    """
    if net_windows is not None:
        windows = tuple(sorted({int(w) for w in net_windows}))
    else:
        windows = (int(net_window),)
    if not windows or any(w < 1 for w in windows):
        raise ValueError("net windows must be >= 1")
    # Always materialize Net5 field for callers that only read .net5
    compute = tuple(sorted(set(windows) | {5}))

    days = aggregate_desk_by_date(flows)
    if not days:
        return None
    latest = days[-1]
    window_nets: list[tuple[int, Decimal, int]] = []
    for w in compute:
        chunk = days[-w:]
        window_nets.append(
            (
                w,
                sum((d.net_value for d in chunk), Decimal("0")),
                len(chunk),
            )
        )
    nets_t = tuple(window_nets)
    net5 = next(net for w, net, _n in nets_t if w == 5)
    sessions_in_net5 = next(n for w, _net, n in nets_t if w == 5)
    # Expose only requested windows in window_nets (plus 5 if it was requested)
    requested = set(windows)
    exposed = tuple((w, net, n) for w, net, n in nets_t if w in requested)

    streak = 0
    for d in reversed(days):
        if d.net_value > Decimal("0"):
            streak += 1
        else:
            break
    delta1: Decimal | None = None
    if len(days) >= 2:
        delta1 = days[-1].net_value - days[-2].net_value
    return DeskSessionPulse(
        as_of=latest.date,
        day_net=latest.net_value,
        net5=net5,
        sessions_in_net5=sessions_in_net5,
        buy_streak=streak,
        delta1=delta1,
        window_nets=exposed,
    )


# ── Desk top-5 net-buy matrix (multi-window) ─────────────────

# Default windows for desk top matrix (sessions-with-data, not blank calendar).
DESK_TOP_MATRIX_WINDOWS: tuple[int, ...] = (1, 3, 5, 10, 20)
DESK_TOP_MATRIX_LIMIT: int = 5


@dataclass(frozen=True)
class DeskTickerWindowCell:
    """One matrix cell: desk×ticker ranked net buy for a session window."""

    ticker: str
    net_value: Decimal
    window: int
    sessions_used: int  # desk sessions available in this column (≤ window)
    avg_buy_price: Decimal | None  # lot-weighted; None if no buy_lot in window
    buy_streak: int  # desk×ticker consecutive net-buy sessions ending as_of
    is_partial: bool  # sessions_used < window


def desk_session_dates(flows: list[BrokerDailyFlow]) -> tuple[date, ...]:
    """Distinct session dates for the desk, ascending (dates with any flow)."""
    return tuple(sorted({f.date for f in flows}))


def lot_weighted_avg_buy_price(rows: list[BrokerDailyFlow]) -> Decimal | None:
    """Lot-weighted avg_buy_price over rows with buy_lot > 0; else None."""
    total_lot = 0
    weighted = Decimal("0")
    for r in rows:
        if r.buy_lot > 0:
            total_lot += r.buy_lot
            weighted += r.avg_buy_price * Decimal(r.buy_lot)
    if total_lot <= 0:
        return None
    return weighted / Decimal(total_lot)


def desk_ticker_buy_streak(
    flows: list[BrokerDailyFlow],
    ticker: str,
    *,
    session_dates: tuple[date, ...] | None = None,
) -> int:
    """Consecutive sessions this desk net-bought ``ticker`` ending at latest.

    Sessions = desk-wide dates with any activity (not blank calendar days).
    A missing desk×ticker row or net_value ≤ 0 breaks the streak (returns 0
    when the latest session is not a buy) — same rule as desk-wide pulse.
    """
    ticker_u = ticker.upper()
    dates = session_dates if session_dates is not None else desk_session_dates(flows)
    if not dates:
        return 0
    by_date: dict[date, BrokerDailyFlow] = {}
    for f in flows:
        if f.ticker.upper() != ticker_u:
            continue
        by_date[f.date] = f
    streak = 0
    for d in reversed(dates):
        row = by_date.get(d)
        if row is None or row.net_value <= Decimal("0"):
            break
        streak += 1
    return streak


def rank_desk_top_buy_matrix(
    flows: list[BrokerDailyFlow],
    *,
    windows: tuple[int, ...] = DESK_TOP_MATRIX_WINDOWS,
    limit: int = DESK_TOP_MATRIX_LIMIT,
) -> dict[int, tuple[DeskTickerWindowCell, ...]]:
    """Top ``limit`` net-buy tickers per window for one desk.

    Window = last min(W, n) desk sessions-with-data. Partial when n < W.
    Rank metric: sum of net_value over the window (buyers only, net > 0).
    Avg buy: lot-weighted avg_buy_price on days with buy_lot > 0.
    Streak: desk×ticker buy streak ending at latest desk session (as_of).
    """
    if limit < 1:
        raise ValueError("limit must be >= 1")
    wins = tuple(sorted({int(w) for w in windows}))
    if not wins or any(w < 1 for w in wins):
        raise ValueError("windows must be >= 1")

    if not flows:
        return {w: () for w in wins}

    dates = desk_session_dates(flows)
    by_ticker_date: dict[str, dict[date, BrokerDailyFlow]] = {}
    for f in flows:
        t = f.ticker.upper()
        by_ticker_date.setdefault(t, {})[f.date] = f

    streaks = {t: desk_ticker_buy_streak(flows, t, session_dates=dates) for t in by_ticker_date}

    out: dict[int, tuple[DeskTickerWindowCell, ...]] = {}
    for w in wins:
        chunk_dates = dates[-w:]
        sessions_used = len(chunk_dates)
        is_partial = sessions_used < w

        cells: list[DeskTickerWindowCell] = []
        for ticker, day_map in by_ticker_date.items():
            rows = [day_map[d] for d in chunk_dates if d in day_map]
            if not rows:
                continue
            net = sum((r.net_value for r in rows), Decimal("0"))
            if net <= Decimal("0"):
                continue
            cells.append(
                DeskTickerWindowCell(
                    ticker=ticker,
                    net_value=net,
                    window=w,
                    sessions_used=sessions_used,
                    avg_buy_price=lot_weighted_avg_buy_price(rows),
                    buy_streak=streaks.get(ticker, 0),
                    is_partial=is_partial,
                )
            )
        cells.sort(key=lambda c: c.net_value, reverse=True)
        out[w] = tuple(cells[:limit])
    return out
