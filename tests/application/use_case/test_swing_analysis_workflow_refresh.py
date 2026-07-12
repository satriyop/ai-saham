from datetime import date

from tests.application.use_case.swing_analysis_workflow_fixtures import (
    FakeMarketRepository,
    _candle,
    _request,
    _workflow,
)


def test_swing_workflow_runs_auto_refresh_when_enabled():
    calls: list[str] = []
    workflow = _workflow(
        FakeMarketRepository([_candle(date(2026, 6, 18))]),
        calls,
    )

    response = workflow.execute(_request(auto_refresh=True))

    assert calls == ["refresh"]
    assert response.refresh_actions == ("candles=ok",)
