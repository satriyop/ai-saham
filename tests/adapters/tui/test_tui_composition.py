from inspect import signature
from pathlib import Path

import pytest

from src.adapters.tui.composition import (
    _build_daily_request,
    _DailyExecution,
    _forbid_tui_refresh,
    _forbid_tui_sentiment,
    _SerializedDailyCapability,
    create_tui_app,
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
