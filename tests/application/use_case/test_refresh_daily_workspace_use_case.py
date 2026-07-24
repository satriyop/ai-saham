"""Tests for RefreshDailyWorkspaceUseCase and PreviewDailyWorkspaceRefreshUseCase.

Layer: Application
"""

from datetime import date
from unittest.mock import MagicMock

from src.application.use_case.daily_briefing_use_case import (
    DailyBriefingResponse,
    DailyBriefingUseCase,
)
from src.application.use_case.fetch_market_command_workflow_use_case import (
    FetchMarketCommandWorkflowResult,
    FetchMarketRefreshResponse,
)
from src.application.use_case.refresh_daily_workspace_use_case import (
    DailyWorkspaceRefreshPlan,
    PreviewDailyWorkspaceRefreshUseCase,
    RefreshDailyWorkspaceRequest,
    RefreshDailyWorkspaceResult,
    RefreshDailyWorkspaceUseCase,
)


def test_preview_daily_workspace_refresh_use_case() -> None:
    def fake_resolver(req: RefreshDailyWorkspaceRequest) -> tuple[int, str, str, tuple[str, ...]]:
        return (45, "yfinance", "stockbit", ())

    use_case = PreviewDailyWorkspaceRefreshUseCase(fake_resolver)
    request = RefreshDailyWorkspaceRequest(universe="lq45", days=30)

    plan = use_case.execute(request)

    assert isinstance(plan, DailyWorkspaceRefreshPlan)
    assert plan.universe == "lq45"
    assert plan.resolved_ticker_count == 45
    assert plan.history_days == 30
    assert plan.candles_provider_label == "yfinance"
    assert plan.broker_provider_label == "stockbit"
    assert "local cache" in plan.local_write_disclosure


def _refresh_response(fail_count: int) -> FetchMarketRefreshResponse:
    """Build a real FetchMarketRefreshResponse so the field contract is enforced.

    Using the real frozen dataclass (not a bare MagicMock) means a wrong attribute
    name in the use case — e.g. the ``failed_count`` typo that crashed every
    confirmed TUI Update — raises AttributeError here instead of being masked by a
    mock that mirrors the buggy access.
    """
    return FetchMarketRefreshResponse(
        ticker_list=["BBCA"],
        stock_tickers_only=["BBCA"],
        ticker_results=[],
        ok_count=1,
        fail_count=fail_count,
        failures=["BMRI"] * fail_count,
    )


def test_refresh_daily_workspace_use_case_execution() -> None:
    refresh_response = _refresh_response(fail_count=0)

    mock_workflow_result = MagicMock(spec=FetchMarketCommandWorkflowResult)
    mock_workflow_result.response = refresh_response

    fake_refresh_capability = MagicMock(return_value=mock_workflow_result)

    mock_briefing_response = MagicMock(spec=DailyBriefingResponse)
    mock_briefing_response.live_session_date = date(2026, 7, 21)

    mock_briefing_use_case = MagicMock(spec=DailyBriefingUseCase)
    mock_briefing_use_case.execute.return_value = mock_briefing_response

    use_case = RefreshDailyWorkspaceUseCase(
        refresh_market_data_capability=fake_refresh_capability,
        daily_briefing_use_case=mock_briefing_use_case,
    )

    request = RefreshDailyWorkspaceRequest(universe="lq45", briefing_top=5)
    result = use_case.execute(request)

    assert isinstance(result, RefreshDailyWorkspaceResult)
    assert result.refresh == mock_workflow_result
    assert result.briefing == mock_briefing_response
    assert result.warnings == ()

    fake_refresh_capability.assert_called_once_with(
        request,
        on_start=None,
        on_ticker_complete=None,
    )
    mock_briefing_use_case.execute.assert_called_once()


def test_refresh_daily_workspace_surfaces_failed_ticker_warning() -> None:
    """A non-zero fail_count must produce the summary warning without crashing.

    Regression guard for the ``failed_count`` attribute typo: this reads the
    real ``fail_count`` field and asserts the exact warning text, so the broken
    access path (which raised AttributeError on every confirmed Update) can never
    silently return.
    """
    mock_workflow_result = MagicMock(spec=FetchMarketCommandWorkflowResult)
    mock_workflow_result.response = _refresh_response(fail_count=2)

    mock_briefing_use_case = MagicMock(spec=DailyBriefingUseCase)
    mock_briefing_use_case.execute.return_value = MagicMock(spec=DailyBriefingResponse)

    use_case = RefreshDailyWorkspaceUseCase(
        refresh_market_data_capability=MagicMock(return_value=mock_workflow_result),
        daily_briefing_use_case=mock_briefing_use_case,
    )

    result = use_case.execute(RefreshDailyWorkspaceRequest(universe="lq45"))

    assert result.warnings == ("2 ticker(s) failed during refresh.",)
