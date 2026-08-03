"""Pure unit tests for multi-session desk flow history aggregation."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.application.services.ticker_desk_flow_history import compute_desk_flow_history
from src.domain.entities.broker_flow import BrokerDailyFlow

pytestmark = pytest.mark.agent

_FOREIGN = frozenset({"YP", "AK"})


def _flow(
    code: str,
    d: date,
    *,
    net: str,
    name: str | None = None,
    avg_buy: str = "1000",
    avg_sell: str = "1000",
) -> BrokerDailyFlow:
    net_v = Decimal(net)
    buy = net_v if net_v > 0 else Decimal("0")
    sell = -net_v if net_v < 0 else Decimal("0")
    return BrokerDailyFlow(
        ticker="BBCA",
        broker_code=code,
        broker_name=name or f"{code} Desk",
        date=d,
        buy_lot=10 if buy else 0,
        sell_lot=10 if sell else 0,
        net_lot=10 if buy else (-10 if sell else 0),
        buy_value=buy,
        sell_value=sell,
        net_value=net_v,
        avg_buy_price=Decimal(avg_buy),
        avg_sell_price=Decimal(avg_sell),
        avg_price=Decimal(avg_buy),
        buy_pct=0.0,
        sell_pct=0.0,
    )


def _dates(n: int, end: date = date(2026, 7, 31)) -> list[date]:
    return [end - timedelta(days=n - 1 - i) for i in range(n)]


def test_raw_not_topn_persistent_desk_outranks_spike() -> None:
    """Raw multi-session sum: steady desk outranks a one-day spike (not daily tops)."""
    dates = _dates(10)
    flows: list[BrokerDailyFlow] = []
    # Persistent: +600 every session → cumulative 6000
    for d in dates:
        flows.append(_flow("AA", d, net="600"))
    # Spike once: +5000 on last day only (wins any single-day top list)
    flows.append(_flow("ZZ", dates[-1], net="5000"))

    result = compute_desk_flow_history(
        ticker="BBCA",
        flows=flows,
        sessions=10,
        limit=5,
        as_of=dates[-1],
        foreign_broker_codes=_FOREIGN,
    )
    assert result is not None
    codes = [d.broker_code for d in result.top_accumulating]
    assert codes[0] == "AA"
    assert result.top_accumulating[0].cumulative_net == Decimal("6000")
    assert result.top_accumulating[0].net_buy_sessions == 10
    if "ZZ" in codes:
        assert codes.index("AA") < codes.index("ZZ")


def test_longest_streak_breaks_on_absence() -> None:
    dates = _dates(6)
    flows = [
        _flow("YP", dates[0], net="100"),
        _flow("YP", dates[1], net="100"),
        # gap day kept in window by filler desk
        _flow("EP", dates[2], net="10"),
        _flow("YP", dates[3], net="100"),
        _flow("YP", dates[4], net="100"),
        _flow("YP", dates[5], net="100"),
    ]
    result = compute_desk_flow_history(
        ticker="BBCA",
        flows=flows,
        sessions=6,
        limit=5,
        as_of=dates[-1],
        foreign_broker_codes=_FOREIGN,
    )
    assert result is not None
    yp = next(d for d in result.top_accumulating if d.broker_code == "YP")
    assert yp.longest_streak == 3
    assert yp.active_sessions == 5
    assert yp.window_sessions == 6


def test_pit_excludes_rows_after_as_of() -> None:
    dates = _dates(5)
    flows = [_flow("YP", d, net="100") for d in dates]
    # Extra future-looking row after as_of
    flows.append(_flow("YP", dates[-1] + timedelta(days=1), net="99999"))
    as_of = dates[2]
    result = compute_desk_flow_history(
        ticker="BBCA",
        flows=flows,
        sessions=10,
        limit=5,
        as_of=as_of,
        foreign_broker_codes=_FOREIGN,
    )
    assert result is not None
    assert result.as_of == as_of
    yp = result.top_accumulating[0]
    # Only 3 sessions on/before as_of
    assert yp.cumulative_net == Decimal("300")
    assert yp.active_sessions == 3


def test_foreign_local_split_and_rotation() -> None:
    dates = _dates(60)
    flows: list[BrokerDailyFlow] = []
    # Prior window: EP dominates buy; recent window: YP (foreign) takes over
    for d in dates[:40]:
        flows.append(_flow("EP", d, net="500"))
        flows.append(_flow("YP", d, net="50"))
    for d in dates[40:]:
        flows.append(_flow("YP", d, net="800"))
        flows.append(_flow("EP", d, net="10"))
    result = compute_desk_flow_history(
        ticker="BBCA",
        flows=flows,
        sessions=60,
        limit=3,
        as_of=dates[-1],
        foreign_broker_codes=_FOREIGN,
    )
    assert result is not None
    assert result.rotation is not None
    assert "YP" in result.rotation.entering_accumulators or "YP" in [
        d.broker_code for d in result.top_accumulating
    ]
    assert result.buy_side_split.foreign_desk_count >= 1
    # Weekly trajectory capped
    top = result.top_accumulating[0]
    assert len(top.weekly_net) <= 12


def test_no_score_fields_on_result() -> None:
    dates = _dates(5)
    flows = [_flow("YP", d, net="100") for d in dates]
    result = compute_desk_flow_history(
        ticker="BBCA",
        flows=flows,
        sessions=5,
        limit=5,
        as_of=dates[-1],
        foreign_broker_codes=_FOREIGN,
    )
    assert result is not None
    assert not hasattr(result, "score")
    assert not hasattr(result.top_accumulating[0], "score")
    assert not hasattr(result.top_accumulating[0], "quality")
