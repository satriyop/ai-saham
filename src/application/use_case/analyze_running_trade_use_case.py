"""
AnalyzeRunningTradeUseCase — compute institutional broker absorption from trade ticks.

Pure use case: takes list[TradeTick] + set of institutional broker codes.
Returns RunningTradeSignal summarising whether institutions are net buyers or sellers.

absorption_ratio = institutional_buy_lot / total_buy_lot
dominant_side:
  BUY  → institutional_net_lot > 0
  SELL → institutional_net_lot < 0
  NEUTRAL → net zero or no ticks

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.domain.entities.trade_tick import TradeTick
from src.domain.value_objects.running_trade_signal import RunningTradeSignal


@dataclass(frozen=True)
class AnalyzeRunningTradeRequest:
    ticker: str
    ticks: list[TradeTick]
    institutional_broker_codes: frozenset[str]


def analyze_running_trade(request: AnalyzeRunningTradeRequest) -> RunningTradeSignal | None:
    """Compute RunningTradeSignal from raw ticks. Returns None if no ticks provided."""
    ticks = request.ticks
    if not ticks:
        return None

    codes = request.institutional_broker_codes
    inst_buy_lot = 0
    inst_sell_lot = 0
    inst_buy_value = 0.0
    inst_sell_value = 0.0
    total_buy_lot = 0

    for tick in ticks:
        buyer_is_inst = tick.buyer_broker_code.upper() in codes
        seller_is_inst = tick.seller_broker_code.upper() in codes

        total_buy_lot += tick.lot

        if buyer_is_inst:
            inst_buy_lot += tick.lot
            inst_buy_value += tick.value
        if seller_is_inst:
            inst_sell_lot += tick.lot
            inst_sell_value += tick.value

    net_lot = inst_buy_lot - inst_sell_lot
    net_value = inst_buy_value - inst_sell_value

    if net_lot > 0:
        dominant: Literal["BUY", "SELL", "NEUTRAL"] = "BUY"
    elif net_lot < 0:
        dominant = "SELL"
    else:
        dominant = "NEUTRAL"

    absorption = inst_buy_lot / total_buy_lot if total_buy_lot > 0 else 0.0

    as_of = max(t.timestamp for t in ticks)

    return RunningTradeSignal(
        ticker=request.ticker,
        as_of=as_of,
        tick_count=len(ticks),
        institutional_net_lot=net_lot,
        institutional_net_value=net_value,
        absorption_ratio=round(absorption, 4),
        dominant_side=dominant,
    )
