"""Multi-session desk persistence over raw broker_daily_flow (facts only).

Aggregates from raw daily rows — never from per-day top-N lists — so a desk that
is modestly net-buy every session outranks a one-day spike. PIT: never count
rows after ``as_of``.

Layer: Application (pure over injected flow lists / repository)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

from src.application.services.institutional_flow_broker_metrics import is_foreign_broker
from src.domain.entities.broker_flow import BrokerDailyFlow

_DEFAULT_SESSIONS = 60
_MAX_SESSIONS = 60
_DEFAULT_LIMIT = 10
_MAX_LIMIT = 10
_ROTATION_RECENT = 20
_ROTATION_PRIOR = 40
_WEEKLY_POINT_CAP = 12


class BrokerDailyFlowSource(Protocol):
    def get_broker_daily_flows(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
        broker_codes: list[str] | None = None,
        source: str | None = None,
    ) -> list[BrokerDailyFlow]: ...

    def get_broker_daily_flow_date_range(
        self,
        ticker: str,
        source: str | None = None,
    ) -> tuple[date, date] | None: ...


@dataclass(frozen=True)
class DeskWindowFacts:
    broker_code: str
    broker_name: str
    is_foreign: bool
    cumulative_net: Decimal
    window_sessions: int
    active_sessions: int
    net_buy_sessions: int
    longest_streak: int
    avg_buy_price: Decimal | None
    avg_sell_price: Decimal | None
    weekly_net: tuple[tuple[str, Decimal], ...]  # (week_label, cumulative_net)


@dataclass(frozen=True)
class ForeignLocalSplit:
    foreign_cumulative_net: Decimal
    local_cumulative_net: Decimal
    foreign_desk_count: int
    local_desk_count: int


@dataclass(frozen=True)
class DeskRotation:
    recent_sessions: int
    prior_sessions: int
    entering_accumulators: tuple[str, ...]
    leaving_accumulators: tuple[str, ...]
    entering_distributors: tuple[str, ...]
    leaving_distributors: tuple[str, ...]


@dataclass(frozen=True)
class TickerDeskFlowHistoryResult:
    ticker: str
    as_of: date
    window_sessions: int
    requested_sessions: int
    top_accumulating: tuple[DeskWindowFacts, ...]
    top_distributing: tuple[DeskWindowFacts, ...]
    rotation: DeskRotation | None
    buy_side_split: ForeignLocalSplit
    sell_side_split: ForeignLocalSplit
    warnings: tuple[str, ...]


def clamp_sessions(value: int) -> int:
    return max(1, min(int(value), _MAX_SESSIONS))


def clamp_limit(value: int) -> int:
    return max(1, min(int(value), _MAX_LIMIT))


class TickerDeskFlowHistoryService:
    """Load raw broker_daily_flow and project multi-session desk facts."""

    def __init__(
        self,
        source: BrokerDailyFlowSource,
        *,
        foreign_broker_codes: frozenset[str],
    ) -> None:
        self._source = source
        self._foreign = foreign_broker_codes

    def compute(
        self,
        ticker: str,
        *,
        sessions: int = _DEFAULT_SESSIONS,
        limit: int = _DEFAULT_LIMIT,
        as_of: date | None = None,
    ) -> TickerDeskFlowHistoryResult | None:
        ticker = ticker.upper()
        sessions = clamp_sessions(sessions)
        limit = clamp_limit(limit)
        span = self._source.get_broker_daily_flow_date_range(ticker)
        if span is None:
            return None
        end = as_of if as_of is not None else span[1]
        # No look-ahead: never use rows after as_of or after last cached session.
        end = min(end, span[1])
        raw = self._source.get_broker_daily_flows(ticker, end_date=end)
        flows = [f for f in raw if f.date <= end]
        if not flows:
            return None
        return compute_desk_flow_history(
            ticker=ticker,
            flows=flows,
            sessions=sessions,
            limit=limit,
            as_of=end,
            foreign_broker_codes=self._foreign,
        )


def compute_desk_flow_history(
    *,
    ticker: str,
    flows: list[BrokerDailyFlow],
    sessions: int,
    limit: int,
    as_of: date,
    foreign_broker_codes: frozenset[str],
) -> TickerDeskFlowHistoryResult | None:
    """Pure aggregation path (testable without SQLite)."""
    sessions = clamp_sessions(sessions)
    limit = clamp_limit(limit)
    pit = [f for f in flows if f.date <= as_of]
    if not pit:
        return None
    all_sessions = sorted({f.date for f in pit})
    window_dates = all_sessions[-sessions:]
    if not window_dates:
        return None
    window_set = set(window_dates)
    window_flows = [f for f in pit if f.date in window_set]
    window_n = len(window_dates)
    warnings: list[str] = []
    if window_n < sessions:
        warnings.append("DESK_FLOW_WINDOW_SHORT")

    by_desk = _aggregate_desks(
        window_flows,
        window_dates,
        foreign_broker_codes=foreign_broker_codes,
    )
    if not by_desk:
        return None

    ranked_buy = sorted(
        by_desk.values(),
        key=lambda d: d.cumulative_net,
        reverse=True,
    )
    ranked_sell = sorted(
        by_desk.values(),
        key=lambda d: d.cumulative_net,
    )
    top_buy = tuple(ranked_buy[:limit])
    top_sell = tuple(ranked_sell[:limit])

    # Sell side should be net-negative desks; if top "sell" is still positive, keep empty list.
    top_sell = tuple(d for d in top_sell if d.cumulative_net < 0)[:limit]
    top_buy = tuple(d for d in top_buy if d.cumulative_net > 0)[:limit]

    rotation = _rotation(
        window_flows,
        window_dates,
        limit=limit,
        foreign_broker_codes=foreign_broker_codes,
    )
    if rotation is None and window_n >= _ROTATION_RECENT:
        warnings.append("DESK_ROTATION_SKIPPED")

    buy_split = _side_split(
        [d for d in by_desk.values() if d.cumulative_net > 0],
    )
    sell_split = _side_split(
        [d for d in by_desk.values() if d.cumulative_net < 0],
    )

    return TickerDeskFlowHistoryResult(
        ticker=ticker.upper(),
        as_of=as_of,
        window_sessions=window_n,
        requested_sessions=sessions,
        top_accumulating=top_buy,
        top_distributing=top_sell,
        rotation=rotation,
        buy_side_split=buy_split,
        sell_side_split=sell_split,
        warnings=tuple(warnings),
    )


def _aggregate_desks(
    flows: list[BrokerDailyFlow],
    window_dates: list[date],
    *,
    foreign_broker_codes: frozenset[str],
) -> dict[str, DeskWindowFacts]:
    window_n = len(window_dates)
    date_index = {d: i for i, d in enumerate(window_dates)}
    # code -> date -> flow (last wins if dup)
    by_code: dict[str, dict[date, BrokerDailyFlow]] = {}
    names: dict[str, str] = {}
    for flow in flows:
        code = flow.broker_code.upper()
        names[code] = flow.broker_name or code
        by_code.setdefault(code, {})[flow.date] = flow

    result: dict[str, DeskWindowFacts] = {}
    for code, by_date in by_code.items():
        ordered = sorted(by_date.items(), key=lambda kv: kv[0])
        cum = Decimal("0")
        active = 0
        net_buy = 0
        buy_val = Decimal("0")
        buy_shares = Decimal("0")
        sell_val = Decimal("0")
        sell_shares = Decimal("0")
        # streak over full window calendar of sessions
        present_net: dict[int, Decimal] = {}
        for d, flow in ordered:
            if d not in date_index:
                continue
            active += 1
            cum += flow.net_value
            if flow.net_value > 0:
                net_buy += 1
            present_net[date_index[d]] = flow.net_value
            if flow.buy_value > 0 and flow.avg_buy_price > 0:
                buy_val += flow.buy_value
                buy_shares += flow.buy_value / flow.avg_buy_price
            if flow.sell_value > 0 and flow.avg_sell_price > 0:
                sell_val += flow.sell_value
                sell_shares += flow.sell_value / flow.avg_sell_price

        streak = _longest_net_buy_streak(present_net, window_n)
        avg_buy = (buy_val / buy_shares) if buy_shares > 0 else None
        avg_sell = (sell_val / sell_shares) if sell_shares > 0 else None
        weekly = _weekly_rollup(ordered, cap=_WEEKLY_POINT_CAP)
        result[code] = DeskWindowFacts(
            broker_code=code,
            broker_name=names.get(code, code),
            is_foreign=is_foreign_broker(code, foreign_broker_codes),
            cumulative_net=cum,
            window_sessions=window_n,
            active_sessions=active,
            net_buy_sessions=net_buy,
            longest_streak=streak,
            avg_buy_price=avg_buy,
            avg_sell_price=avg_sell,
            weekly_net=weekly,
        )
    return result


def _longest_net_buy_streak(present_net: dict[int, Decimal], window_n: int) -> int:
    """Longest run of consecutive window sessions that are present and net-buy.

    Absence in a window session breaks the streak.
    """
    best = 0
    cur = 0
    for i in range(window_n):
        net = present_net.get(i)
        if net is not None and net > 0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def _weekly_rollup(
    ordered: list[tuple[date, BrokerDailyFlow]],
    *,
    cap: int,
) -> tuple[tuple[str, Decimal], ...]:
    buckets: dict[str, Decimal] = {}
    order: list[str] = []
    for d, flow in ordered:
        # ISO week label YYYY-Www
        iso = d.isocalendar()
        label = f"{iso.year}-W{iso.week:02d}"
        if label not in buckets:
            buckets[label] = Decimal("0")
            order.append(label)
        buckets[label] += flow.net_value
    labels = order[-cap:]
    return tuple((lab, buckets[lab]) for lab in labels)


def _top_codes_by_net(
    flows: list[BrokerDailyFlow],
    dates: list[date],
    *,
    limit: int,
    side: str,
) -> list[str]:
    date_set = set(dates)
    totals: dict[str, Decimal] = {}
    for flow in flows:
        if flow.date not in date_set:
            continue
        code = flow.broker_code.upper()
        totals[code] = totals.get(code, Decimal("0")) + flow.net_value
    if side == "buy":
        ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
        return [c for c, n in ranked if n > 0][:limit]
    ranked = sorted(totals.items(), key=lambda kv: kv[1])
    return [c for c, n in ranked if n < 0][:limit]


def _rotation(
    flows: list[BrokerDailyFlow],
    window_dates: list[date],
    *,
    limit: int,
    foreign_broker_codes: frozenset[str],
) -> DeskRotation | None:
    del foreign_broker_codes
    n = len(window_dates)
    if n < _ROTATION_RECENT + 1:
        return None
    recent_n = min(
        _ROTATION_RECENT, n // 3 if n < _ROTATION_RECENT + _ROTATION_PRIOR else _ROTATION_RECENT
    )
    if recent_n < 1:
        return None
    prior_n = min(_ROTATION_PRIOR, n - recent_n)
    if prior_n < 1:
        return None
    recent_dates = window_dates[-recent_n:]
    prior_dates = window_dates[-(recent_n + prior_n) : -recent_n]
    recent_buy = set(_top_codes_by_net(flows, recent_dates, limit=limit, side="buy"))
    prior_buy = set(_top_codes_by_net(flows, prior_dates, limit=limit, side="buy"))
    recent_sell = set(_top_codes_by_net(flows, recent_dates, limit=limit, side="sell"))
    prior_sell = set(_top_codes_by_net(flows, prior_dates, limit=limit, side="sell"))
    return DeskRotation(
        recent_sessions=recent_n,
        prior_sessions=prior_n,
        entering_accumulators=tuple(sorted(recent_buy - prior_buy)),
        leaving_accumulators=tuple(sorted(prior_buy - recent_buy)),
        entering_distributors=tuple(sorted(recent_sell - prior_sell)),
        leaving_distributors=tuple(sorted(prior_sell - recent_sell)),
    )


def _side_split(desks: list[DeskWindowFacts]) -> ForeignLocalSplit:
    foreign_net = Decimal("0")
    local_net = Decimal("0")
    foreign_n = 0
    local_n = 0
    for d in desks:
        if d.is_foreign:
            foreign_net += d.cumulative_net
            foreign_n += 1
        else:
            local_net += d.cumulative_net
            local_n += 1
    return ForeignLocalSplit(
        foreign_cumulative_net=foreign_net,
        local_cumulative_net=local_net,
        foreign_desk_count=foreign_n,
        local_desk_count=local_n,
    )
