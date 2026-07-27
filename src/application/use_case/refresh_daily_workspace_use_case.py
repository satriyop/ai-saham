"""
Application workflow use case for updating market data and recomputing the daily workspace.

Layer: Application
AI usage: None
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from src.application.use_case.daily_briefing_use_case import (
    DailyBriefingRequest,
    DailyBriefingResponse,
    DailyBriefingUseCase,
)
from src.application.use_case.fetch_market_command_workflow_use_case import (
    FetchMarketCommandWorkflowResult,
)


@dataclass(frozen=True)
class RefreshDailyWorkspaceRequest:
    universe: str = "lq45"
    tickers: tuple[str, ...] = ()
    days: int = 45
    force_refresh: bool = False
    components: Literal["ALL", "CANDLES_ONLY", "BROKER_ONLY"] = "ALL"
    include_meta: bool = True
    include_enrichment: bool = True
    include_calendar: bool = True
    briefing_top: int = 3


@dataclass(frozen=True)
class RefreshDailyWorkspaceResult:
    refresh: FetchMarketCommandWorkflowResult
    briefing: DailyBriefingResponse
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class DailyWorkspaceRefreshPlan:
    universe: str
    resolved_ticker_count: int
    history_days: int
    components: str
    candles_provider_label: str
    broker_provider_label: str
    include_meta: bool
    include_enrichment: bool
    include_calendar: bool
    local_write_disclosure: str
    warnings: tuple[str, ...] = ()


class PreviewDailyWorkspaceRefreshUseCase:
    """Pre-execution preview boundary for daily workspace updates."""

    def __init__(
        self,
        resolver_capability: Callable[
            [RefreshDailyWorkspaceRequest],
            tuple[int, str, str, tuple[str, ...]],
        ],
    ) -> None:
        self._resolver_capability = resolver_capability

    def execute(self, request: RefreshDailyWorkspaceRequest) -> DailyWorkspaceRefreshPlan:
        (
            ticker_count,
            candles_label,
            broker_label,
            warnings,
        ) = self._resolver_capability(request)

        return DailyWorkspaceRefreshPlan(
            universe=request.universe,
            resolved_ticker_count=ticker_count,
            history_days=request.days,
            components=request.components,
            candles_provider_label=candles_label,
            broker_provider_label=broker_label,
            include_meta=request.include_meta,
            include_enrichment=request.include_enrichment,
            include_calendar=request.include_calendar,
            local_write_disclosure=(
                "This operation fetches provider data and updateslocal cache storage."
            ),
            warnings=warnings,
        )


class RefreshDailyWorkspaceUseCase:
    """Sequence explicit market data refresh followed by briefing recomputation."""

    def __init__(
        self,
        refresh_market_data_capability: Callable[..., FetchMarketCommandWorkflowResult],
        daily_briefing_use_case: DailyBriefingUseCase,
    ) -> None:
        self._refresh_market_data = refresh_market_data_capability
        self._daily_briefing_use_case = daily_briefing_use_case

    def execute(
        self,
        request: RefreshDailyWorkspaceRequest,
        *,
        on_start: Callable[..., None] | None = None,
        on_ticker_complete: Callable[..., None] | None = None,
    ) -> RefreshDailyWorkspaceResult:
        refresh_result = self._refresh_market_data(
            request,
            on_start=on_start,
            on_ticker_complete=on_ticker_complete,
        )

        briefing_request = DailyBriefingRequest(
            universe=request.universe,
            top=request.briefing_top,
        )
        briefing_response = self._daily_briefing_use_case.execute(briefing_request)

        warnings: list[str] = []
        if refresh_result.response.fail_count > 0:
            warnings.append(
                f"{refresh_result.response.fail_count} ticker(s) failed during refresh."
            )

        return RefreshDailyWorkspaceResult(
            refresh=refresh_result,
            briefing=briefing_response,
            warnings=tuple(warnings),
        )
