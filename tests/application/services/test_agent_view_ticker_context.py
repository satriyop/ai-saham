"""ADR-066 Slice 2: view_ticker stage context contract."""

from __future__ import annotations

from datetime import date

import pytest

from src.application.dto.accumulation_agent import AgentStageKind
from src.application.dto.ticker_dashboard import GetTickerDashboardRequest, TickerDashboard
from src.application.services.agent_accumulation_context import (
    AgentContextUnavailableError,
)
from src.application.services.agent_stage_context import build_agent_stage_context
from src.application.services.agent_view_ticker_context import (
    SCHEMA_ID,
    build_agent_view_ticker_context,
)
from src.application.services.ticker_dashboard_status import CacheStatus
from src.application.use_case.get_ticker_dashboard_use_case import GetTickerDashboardUseCase
from tests.application.use_case.test_get_ticker_dashboard_use_case import (
    FakeTickerDashboardSource,
)

pytestmark = pytest.mark.agent


def _dashboard(ticker: str = "BBCA") -> TickerDashboard:
    return GetTickerDashboardUseCase(FakeTickerDashboardSource()).execute(
        GetTickerDashboardRequest(ticker=ticker, brief=False, today=date(2026, 7, 24))
    )


def test_happy_path_reuses_dashboard_projection_shape() -> None:
    dash = _dashboard()
    ctx = build_agent_view_ticker_context(dash)
    assert ctx.schema_id == SCHEMA_ID
    assert ctx.stage_kind is AgentStageKind.VIEW_TICKER
    assert ctx.ticker == "BBCA"
    assert ctx.context_reference.startswith("sha256:")
    assert ctx.session_subject == "BBCA"
    assert ctx.price is not None
    assert ctx.mode == "full"


def test_stable_hash() -> None:
    dash = _dashboard()
    a = build_agent_view_ticker_context(dash)
    b = build_agent_view_ticker_context(dash)
    assert a.context_reference == b.context_reference


def test_empty_cache_unavailable() -> None:
    dash = TickerDashboard(
        ticker="ZZZZ",
        mode="full",
        as_of=None,
        today=date(2026, 7, 24),
        fetch_hint="saham fetch market ZZZZ",
        panel_keys=(),
        freshness=(),
        related_actions=(),
        panel_errors=(),
        notation=None,
        fundamentals=None,
        forward_estimates=None,
        latest_close=None,
        price_structure=None,
        analyst=None,
        earnings=(),
        ownership=None,
        bandar=None,
        foreign_flow_points=(),
        foreign_flow_source=None,
        corp_actions=(),
        corp_status=CacheStatus.MISSING,
        insider_txns=(),
        insider_status=CacheStatus.MISSING,
        insider_last_known=None,
        seasonality=None,
        iev_rows=(),
        sentiment_logs=(),
        profile=None,
        candles=(),
    )
    with pytest.raises(AgentContextUnavailableError, match="no cached"):
        build_agent_view_ticker_context(dash)


def test_wrong_type() -> None:
    with pytest.raises(TypeError, match="TickerDashboard"):
        build_agent_view_ticker_context("BBCA")  # type: ignore[arg-type]


def test_facade_dispatches() -> None:
    dash = _dashboard()
    via = build_agent_stage_context(AgentStageKind.VIEW_TICKER, dash)
    direct = build_agent_view_ticker_context(dash)
    assert via.context_reference == direct.context_reference
    assert via.schema_id == SCHEMA_ID
