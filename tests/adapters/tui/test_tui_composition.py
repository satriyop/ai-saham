from inspect import signature
from pathlib import Path
from unittest.mock import patch

import pytest

from src.adapters.tui.composition import (
    _build_daily_preview_execution,
    _build_daily_request,
    _DailyExecution,
    _forbid_tui_refresh,
    _forbid_tui_sentiment,
    _SerializedDailyCapability,
    create_tui_app,
)
from src.application.use_case.refresh_daily_workspace_use_case import (
    RefreshDailyWorkspaceRequest,
)
from src.infrastructure.config.app_config import AnalysisConfig, AppConfig

from .daily_fixtures import ready_response


class _UseCase:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        return self.response


def test_daily_request_is_exact_phase_zero_contract():
    request = _build_daily_request(AppConfig(analysis=AnalysisConfig(universe="idx30")))
    assert request.universe == "idx30"
    assert request.top == 3
    assert request.as_of_date is None
    assert request.opening_data_dir == Path("data/opening")
    assert request.universe_config_path == Path("config/universes.yaml")


def test_serialized_capability_builds_once_and_executes_once_per_call():
    response = ready_response()
    use_case = _UseCase(response)
    request = _build_daily_request(AppConfig())
    builds = 0

    def factory():
        nonlocal builds
        builds += 1
        return _DailyExecution(use_case, request)

    capability = _SerializedDailyCapability(factory)
    assert capability() is response
    assert capability() is response
    assert builds == 1
    assert use_case.requests == [request, request]


@pytest.mark.parametrize(
    ("callable_", "message"),
    [
        (_forbid_tui_refresh, "TUI local-only contract forbids provider refresh"),
        (_forbid_tui_sentiment, "TUI local-only contract forbids sentiment fetch"),
    ],
)
def test_local_only_tripwires_have_exact_messages(callable_, message):
    with pytest.raises(RuntimeError, match=f"^{message}$"):
        callable_(ticker="BBCA", force=True)


def test_tui_composition_has_no_removed_readiness_or_scope_inputs():
    parameters = signature(create_tui_app).parameters
    assert "research_health_loader" not in parameters
    assert "research_scopes_loader" not in parameters


@pytest.mark.parametrize("broker_name", ["stockbit", "idx"])
def test_preview_plan_mirrors_cli_fetch_market_provider_selection(broker_name):
    """The Update confirmation modal must advertise the exact provider selection
    `saham fetch market` would use: a config-driven candle source resolved via
    `candle_source()` and an auto-detected broker via `create_broker_provider()`
    (Stockbit session, else the IDX fallback). It must never fall back to the old
    hardcoded 'yfinance' candles label or a 'none' broker that the CLI never
    produces. This test is the anti-drift guard for CLI/TUI source parity.
    """
    request = RefreshDailyWorkspaceRequest(universe="lq45")

    with (
        patch(
            "src.infrastructure.config.data_sources_config.candle_source",
            return_value="stockbit",
        ),
        patch(
            "src.infrastructure.composition.broker_provider_factory.create_broker_provider",
            return_value=(object(), broker_name),
        ) as create_broker,
        patch(
            "src.adapters.tui.composition.resolve_tickers",
            return_value=["BBCA", "BBRI", "BMRI"],
        ),
    ):
        plan = _build_daily_preview_execution(request)

    # Broker provider is auto-detected exactly like the CLI (name=None).
    assert create_broker.call_args.args == (None,)
    assert plan.candles_provider_label == "stockbit"
    assert plan.candles_provider_label != "yfinance"
    assert plan.broker_provider_label == broker_name
    assert plan.broker_provider_label != "none"
    assert plan.resolved_ticker_count == 3
    assert plan.universe == "lq45"


def test_tui_and_cli_resolve_candles_through_the_same_config_seam():
    """Both adapters must read the candle source from the identical config
    function, so a change to `config/data_sources.yaml` (or the resolver) can
    never diverge the TUI Update path from `saham fetch market`.
    """
    from src.adapters.cli.fetch_market_commands import _candle_source as cli_candle_source
    from src.infrastructure.config.data_sources_config import candle_source

    assert cli_candle_source is candle_source
