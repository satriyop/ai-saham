"""Shared fixtures and helpers for accumulation screen CLI tests."""

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from typer.testing import CliRunner

from src.application.dto.accumulation_screen import (
    AccumulationCandidate,
)
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from src.domain.entities.broker_flow import BrokerSummary, BrokerTransaction, BrokerType

runner = CliRunner()

_WIB = ZoneInfo("Asia/Jakarta")
_FAKE_NOW = datetime(2026, 6, 28, 16, 30, tzinfo=_WIB)

# Standin for what a real caller (RunAccumulationScreenWorkflowUseCase)
# already resolved once — CLI-layer test fakes must not resolve sessions
# themselves.
_FAKE_EFFECTIVE_SESSION = EffectiveMarketSession(
    run_at=_FAKE_NOW,
    decision_at=_FAKE_NOW,
    latest_completed_session=date(2026, 6, 28),
    analysis_as_of=date(2026, 6, 28),
    market_session_name="AFTER_CLOSE",
    is_eod_pending=False,
    resolution_source="test_fixture",
    notes=(),
)


def _tx(
    code: str,
    buy: str,
    sell: str,
    broker_type: BrokerType = BrokerType.FOREIGN,
) -> BrokerTransaction:
    return BrokerTransaction(
        broker_code=code,
        broker_name=code,
        broker_type=broker_type,
        buy_lot=1000,
        sell_lot=500,
        buy_value=Decimal(buy),
        sell_value=Decimal(sell),
        avg_buy_price=Decimal("1000"),
        avg_sell_price=Decimal("1000"),
    )


def _summary(
    day: date,
    top_buyers: tuple[BrokerTransaction, ...] = (),
    top_sellers: tuple[BrokerTransaction, ...] = (),
) -> BrokerSummary:
    return BrokerSummary(
        ticker="BBCA",
        date=day,
        top_buyers=top_buyers,
        top_sellers=top_sellers,
        foreign_buy_value=Decimal("1000"),
        foreign_sell_value=Decimal("500"),
        foreign_buy_lot=10,
        foreign_sell_lot=5,
        total_value=Decimal("10000"),
        total_lot=100,
        source="stockbit",
    )


def _candidate(**overrides) -> AccumulationCandidate:
    values = {
        "ticker": "BBCA",
        "window_days": 7,
        "net_buy_days": 5,
        "total_days": 7,
        "net_buy_ratio": 5 / 7,
        "total_net_value": Decimal("10000000000"),
        "consecutive_streak": 3,
        "foreign_vwap": Decimal("1030"),
        "current_price": Decimal("1000"),
        "vwap_discount_pct": 3.0,
        "rsi": 55.0,
        "trend": "SIDE",
        "accum_score": 70.0,
        "top_brokers": None,
        "institutional_flag": False,
        "avg_flow_ratio": 5.0,
    }
    values.update(overrides)
    return AccumulationCandidate(**values)


class FakeBrokerSummaryRepository:
    def __init__(self, summaries):
        self._summaries = summaries

    def get_broker_summaries(self, ticker: str, start_date=None, end_date=None):
        return [
            summary
            for summary in self._summaries
            if summary.ticker == ticker
            and (start_date is None or summary.date >= start_date)
            and (end_date is None or summary.date <= end_date)
        ]


def _fake_workflow_result(**overrides):
    """Build a RunAccumulationScreenWorkflowResult-like object for CLI mocks.

    Auto-derives single_projection/multi_projection from response/multi_results
    (with no filters applied) unless the caller passes them explicitly, so
    existing fixtures that only set up a raw response still render.
    """
    from src.application.services.screen_accum_result_projector import (
        project_multi_screen_result,
        project_single_screen_result,
    )
    from src.application.use_case.run_accumulation_screen_workflow_use_case import (
        RunAccumulationScreenWorkflowResult,
    )
    params = dict(
        response=None,
        single_projection=None,
        multi_results={},
        multi_projection=None,
        tracked_broker_flow={},
        strategy_signals={},
        save_result=None,
        warnings=(),
        effective_session=_FAKE_EFFECTIVE_SESSION,
    )
    params.update(overrides)

    if params["response"] is not None and params["single_projection"] is None:
        params["single_projection"] = project_single_screen_result(
            params["response"],
            vwap_only=False,
            squeeze_only=False,
            top=len(params["response"].candidates),
            min_streak=0,
            coiled_spring_bb_pctile=0.20,
            effective_session=_FAKE_EFFECTIVE_SESSION,
        )

    if params["multi_results"] and params["multi_projection"] is None:
        resolved_windows = sorted(params["multi_results"].keys())
        params["multi_projection"] = project_multi_screen_result(
            params["multi_results"],
            tracked_broker_flow=params["tracked_broker_flow"],
            windows=resolved_windows,
            top=len(next(iter(params["multi_results"].values())).candidates) or 1,
            sort_by="avg",
            squeeze_only=False,
            coiled_spring_min_accum_score=50.0,
            coiled_spring_bb_pctile=0.20,
            canonical_window=7 if 7 in resolved_windows else resolved_windows[0],
            effective_session=_FAKE_EFFECTIVE_SESSION,
        )

    return RunAccumulationScreenWorkflowResult(**params)
