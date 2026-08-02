from dataclasses import replace
from datetime import date

import pytest

from src.application.dto.agent_tool_context import AgentToolExecutionContext
from src.application.dto.agent_tools import AgentToolExecutionStatus
from src.application.dto.ticker_dashboard import GetTickerDashboardRequest
from src.application.services.agent_accumulation_context import (
    build_agent_accumulation_context,
)
from src.application.services.agent_ticker_dashboard_tool import (
    TickerDashboardArguments,
    TickerDashboardResultData,
    TickerDashboardTool,
)
from src.application.services.ticker_dashboard_status import CacheStatus
from src.application.use_case.get_ticker_dashboard_use_case import GetTickerDashboardUseCase
from src.domain.value_objects.analyst_consensus import AnalystConsensus
from src.domain.value_objects.bandar_detector_snapshot import BandarDetectorSnapshot
from src.domain.value_objects.company_fundamentals import CompanyFundamentals
from src.domain.value_objects.forward_estimates import ForwardEstimates
from src.domain.value_objects.insider_transaction import InsiderTransaction
from src.domain.value_objects.shareholding_composition import ShareholdingComposition
from src.domain.value_objects.ticker_notation import TickerNotationSnapshot
from tests.application.services.test_agent_accumulation_context import make_candidate
from tests.application.use_case.test_get_ticker_dashboard_use_case import (
    FakeTickerDashboardSource,
)

pytestmark = pytest.mark.agent


def _context() -> AgentToolExecutionContext:
    return AgentToolExecutionContext(build_agent_accumulation_context(make_candidate()))


def test_dashboard_tool_returns_bounded_typed_partial_projection() -> None:
    source = FakeTickerDashboardSource()
    tool = TickerDashboardTool(
        GetTickerDashboardUseCase(source),
        today=lambda: date(2026, 7, 24),
    )

    result = tool.execute(
        "dashboard",
        TickerDashboardArguments("BBCA"),
        _context(),
    )

    assert result.status is AgentToolExecutionStatus.PARTIAL
    assert isinstance(result.data, TickerDashboardResultData)
    assert result.data.ticker == "BBCA"
    assert result.data.mode == "full"
    assert result.data.price is not None
    assert result.data.price.close_idr == "1023"
    assert result.data.foreign_flow is not None
    assert result.data.foreign_flow.latest_net_value_idr == "-50"
    assert len(result.data.earnings) == 1
    assert not hasattr(result.data, "profile")
    assert not hasattr(result.data, "candles")
    assert result.serialized_size() <= tool.definition.max_result_bytes


def test_complete_typed_dashboard_projection_is_success() -> None:
    source = FakeTickerDashboardSource()
    base = GetTickerDashboardUseCase(source).execute(
        GetTickerDashboardRequest(
            ticker="BBCA",
            brief=False,
            today=date(2026, 7, 24),
        )
    )
    complete = replace(
        base,
        freshness=tuple(replace(item, status=CacheStatus.OK) for item in base.freshness),
        notation=TickerNotationSnapshot(ticker="BBCA", status="STATUS_ACTIVE"),
        fundamentals=CompanyFundamentals(
            ticker="BBCA",
            pe_ratio_ttm=20.0,
            roe_ttm=18.0,
            net_profit_margin=25.0,
            revenue_yoy_growth=8.0,
            piotroski_f_score=7,
            dividend_yield=2.0,
            week52_high=1_500.0,
            week52_low=1_000.0,
            near_52w_high_rank=80.0,
        ),
        forward_estimates=ForwardEstimates.compute("BBCA", 100.0, 1_000.0, 1_200.0),
        analyst=AnalystConsensus(
            ticker="BBCA",
            buy_count=8,
            hold_count=2,
            sell_count=1,
            avg_price_target=1_400.0,
            current_price=1_200.0,
            last_updated=date(2026, 7, 23),
        ),
        ownership=ShareholdingComposition(
            ticker="BBCA",
            report_date=date(2026, 6, 30),
            institution_pct=40.0,
            individual_pct=20.0,
            top_holder_name="Holder",
            top_holder_pct=30.0,
        ),
        bandar=BandarDetectorSnapshot(
            ticker="BBCA",
            session_date=date(2026, 7, 23),
            broker_accdist="Acc",
            today_accdist="Small Acc",
            five_day_accdist="Small Acc",
            top1_accdist="Neutral",
            top1_percent=20.0,
            today_percent=5.0,
            total_buyer=10,
            total_seller=8,
        ),
        insider_txns=(
            InsiderTransaction(
                ticker="BBCA",
                name="Director",
                role="DIREKTUR",
                action_type="BUY",
                shares=100,
                price=1_000.0,
                transaction_date=date(2026, 7, 20),
                ownership_before_pct=0.1,
                ownership_after_pct=0.2,
            ),
        ),
        insider_status=CacheStatus.OK,
        sector_macro_context_evidence=object(),
        panel_errors=(),
    )

    class CompleteUseCase:
        def execute(self, request):
            return complete

    result = TickerDashboardTool(
        CompleteUseCase(),
        today=lambda: date(2026, 7, 24),
    ).execute("complete", TickerDashboardArguments("BBCA"), _context())

    assert result.status is AgentToolExecutionStatus.SUCCESS
    assert result.warnings == ()


def test_empty_dashboard_cache_is_unavailable() -> None:
    source = FakeTickerDashboardSource()
    source.notation = None
    source.fundamentals = None
    source.analyst = None
    source.ownership = None
    source.bandar = None
    source.forward = None
    source.profile = None
    source.seasonality = None
    source.candles = []
    source.calendar_corp = []
    source.insider_older = []
    source.flow_stockbit = []
    source.earnings = []
    source.iev = []
    source.sentiment = []
    tool = TickerDashboardTool(
        GetTickerDashboardUseCase(source),
        today=lambda: date(2026, 7, 24),
    )

    result = tool.execute("empty", TickerDashboardArguments("BBCA"), _context())

    assert result.status is AgentToolExecutionStatus.UNAVAILABLE
    assert result.data is None
    assert result.error_code == "DASHBOARD_UNAVAILABLE"


def test_cache_exception_is_failed_without_raw_error_copy() -> None:
    class BrokenUseCase:
        def execute(self, request):
            raise RuntimeError("/private/cache/data.db: secret SQL failed")

    tool = TickerDashboardTool(BrokenUseCase())

    result = tool.execute("broken", TickerDashboardArguments("BBCA"), _context())

    assert result.status is AgentToolExecutionStatus.FAILED
    assert result.error_code == "DASHBOARD_READ_FAILED"
    assert "/private" not in (result.error_message or "")
    assert "SQL" not in (result.error_message or "")


@pytest.mark.parametrize(
    "ticker",
    ("", "bbca", " BBCA", "BBCA ", "BBCA.JK", "^JKSE", "BBCA1", "ABC"),
)
def test_ticker_argument_rejects_noncanonical_values(ticker: str) -> None:
    with pytest.raises(ValueError, match="canonical four-letter"):
        TickerDashboardArguments(ticker)


def test_definition_locks_schema_timeout_and_single_argument() -> None:
    tool = TickerDashboardTool(GetTickerDashboardUseCase(FakeTickerDashboardSource()))

    assert tool.definition.argument_schema_id == "agent_tool.ticker_dashboard.args.v1"
    assert tool.definition.result_schema_id == "agent_tool.ticker_dashboard.result.v1"
    assert tuple(field.name for field in tool.definition.arguments) == ("ticker",)
    assert tool.definition.timeout_ms == 3_000
    assert tool.definition.max_result_bytes == 32 * 1024


def test_all_null_forward_cache_is_missing_not_neutral_filled() -> None:
    source = FakeTickerDashboardSource()
    source.forward = ForwardEstimates.compute("BBCA", None, None, None)
    tool = TickerDashboardTool(
        GetTickerDashboardUseCase(source),
        today=lambda: date(2026, 7, 24),
    )

    result = tool.execute("null-forward", TickerDashboardArguments("BBCA"), _context())

    assert isinstance(result.data, TickerDashboardResultData)
    assert result.data.forward_estimates is None
    assert "forward_estimates" in result.data.missing_branches
