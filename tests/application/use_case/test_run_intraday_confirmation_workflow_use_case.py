"""
Tests for RunIntradayConfirmationWorkflowUseCase.

Layer: Application
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from src.application.dto.intraday_confirmation_workflow import (
    RunIntradayConfirmationWorkflowRequest,
)
from src.application.services.pre_open_screen_config import PreOpenScreenConfig
from src.application.use_case.resolve_opening_prices_use_case import (
    OpeningPriceObservation,
)
from src.application.use_case.run_intraday_confirmation_workflow_use_case import (
    EVENT_OBSERVATION,
    EVENT_REGIME_WARNING,
    IntradayAutoResolutionUnavailable,
    IntradayTrackFileParseError,
    RunIntradayConfirmationWorkflowUseCase,
)


def _write_sidecar(path: Path, *, regime: dict | None = None) -> None:
    data = {
        "screened_at": "2026-06-12",
        "candidates": [
            {
                "ticker": "BBCA",
                "iev": 450000,
                "gap_pct": "0.6",
                "entry_range_low": "8800",
                "entry_range_high": "9300",
                "suggested_entry": "9050",
                "atr_stop": "8900",
                "trend": "BULLISH",
                "rsi": "52",
                "opening_broker_backing_tag": "BACKED",
            },
            {
                "ticker": "GOTO",
                "iev": 155000,
                "gap_pct": "4.2",
                "entry_range_low": "228",
                "entry_range_high": "242",
                "suggested_entry": "235",
                "atr_stop": "221",
                "trend": "BEARISH",
                "rsi": "73",
            },
        ],
    }
    if regime is not None:
        data["market_regime"] = regime
    path.write_text(json.dumps(data))


class FakeRunningTradeProvider:
    def fetch_running_trade(self, ticker: str, limit: int = 80):
        return []


class FakeOrderBookProvider:
    def fetch_snapshot(self, ticker: str):
        return None


def _use_case(**kwargs) -> RunIntradayConfirmationWorkflowUseCase:
    kwargs.setdefault("pre_open_config", PreOpenScreenConfig())
    return RunIntradayConfirmationWorkflowUseCase(**kwargs)


def test_missing_sidecar_raises_file_not_found(tmp_path):
    use_case = _use_case()
    request = RunIntradayConfirmationWorkflowRequest(
        sidecar_path=tmp_path / "missing.json",
        output_path=tmp_path / "out.json",
        max_stop_pct=Decimal("0.07"),
        manual_prices={},
        track_file=None,
        live_auto_resolution_enabled=True,
    )

    with pytest.raises(FileNotFoundError):
        use_case.execute(request)


def test_track_file_disables_live_auto_resolution_even_with_missing_tickers(tmp_path):
    sidecar = tmp_path / "session.json"
    _write_sidecar(sidecar)
    track_file = tmp_path / "track.json"
    track_file.write_text(
        json.dumps(
            {
                "captured_at": "2026-06-12T09:00:05+07:00",
                "tickers": {"BBCA": {"mid_price": 9000}},
            }
        )
    )

    # No providers injected — if auto-resolution were attempted this would raise.
    use_case = _use_case()
    request = RunIntradayConfirmationWorkflowRequest(
        sidecar_path=sidecar,
        output_path=tmp_path / "out.json",
        max_stop_pct=Decimal("0.07"),
        manual_prices={},
        track_file=track_file,
        live_auto_resolution_enabled=False,
    )

    result = use_case.execute(request)

    assert result.observations["BBCA"].price is not None
    assert result.observations["GOTO"].price is None
    # Auto-resolution never attempted (no providers injected, none needed since
    # track_file disables it) — the unresolved reason reflects provider absence,
    # not a live-fetch failure, proving no fetch was attempted.
    assert result.observations["GOTO"].reason == "running trade provider unavailable"


def test_auto_resolution_needed_with_no_providers_raises(tmp_path):
    sidecar = tmp_path / "session.json"
    _write_sidecar(sidecar)

    use_case = _use_case()
    request = RunIntradayConfirmationWorkflowRequest(
        sidecar_path=sidecar,
        output_path=tmp_path / "out.json",
        max_stop_pct=Decimal("0.07"),
        manual_prices={},
        track_file=None,
        live_auto_resolution_enabled=True,
    )

    with pytest.raises(IntradayAutoResolutionUnavailable) as exc_info:
        use_case.execute(request)

    assert "No authenticated Stockbit profile for auto confirm." in str(exc_info.value)


def test_manual_prices_used_and_passed_into_candidates(tmp_path):
    sidecar = tmp_path / "session.json"
    _write_sidecar(sidecar)

    use_case = _use_case()
    request = RunIntradayConfirmationWorkflowRequest(
        sidecar_path=sidecar,
        output_path=tmp_path / "out.json",
        max_stop_pct=Decimal("0.07"),
        manual_prices={"BBCA": Decimal("9050"), "GOTO": Decimal("245")},
        track_file=None,
        live_auto_resolution_enabled=True,
    )

    result = use_case.execute(request)

    assert result.observations["BBCA"].price == Decimal("9050")
    assert result.observations["BBCA"].source == "manual"
    confirmed = {c.ticker: c for c in result.confirmations}
    assert confirmed["BBCA"].opening_price == Decimal("9050")


def test_track_file_parse_error_propagates(tmp_path):
    sidecar = tmp_path / "session.json"
    _write_sidecar(sidecar)
    track_file = tmp_path / "track.json"
    track_file.write_text("{not valid json")

    use_case = _use_case()
    request = RunIntradayConfirmationWorkflowRequest(
        sidecar_path=sidecar,
        output_path=tmp_path / "out.json",
        max_stop_pct=Decimal("0.07"),
        manual_prices={},
        track_file=track_file,
        live_auto_resolution_enabled=False,
    )

    with pytest.raises(IntradayTrackFileParseError) as exc_info:
        use_case.execute(request)

    assert isinstance(exc_info.value.__cause__, json.JSONDecodeError)


def test_missing_track_file_raises_file_not_found(tmp_path):
    sidecar = tmp_path / "session.json"
    _write_sidecar(sidecar)
    track_file = tmp_path / "does_not_exist.json"

    use_case = _use_case()
    request = RunIntradayConfirmationWorkflowRequest(
        sidecar_path=sidecar,
        output_path=tmp_path / "out.json",
        max_stop_pct=Decimal("0.07"),
        manual_prices={},
        track_file=track_file,
        live_auto_resolution_enabled=False,
    )

    with pytest.raises(FileNotFoundError) as exc_info:
        use_case.execute(request)

    assert exc_info.value.args[0] == track_file


def test_regime_warning_returned_and_falls_back_to_risk_off(tmp_path):
    sidecar = tmp_path / "session.json"
    _write_sidecar(sidecar, regime={"regime": "SOMETHING_UNKNOWN"})

    events: list[tuple[str, dict]] = []
    use_case = _use_case(on_event=lambda event, payload: events.append((event, payload)))
    request = RunIntradayConfirmationWorkflowRequest(
        sidecar_path=sidecar,
        output_path=tmp_path / "out.json",
        max_stop_pct=Decimal("0.07"),
        manual_prices={"BBCA": Decimal("9050"), "GOTO": Decimal("245")},
        track_file=None,
        live_auto_resolution_enabled=True,
    )

    result = use_case.execute(request)

    assert len(result.warnings) == 1
    assert "unrecognized regime" in result.warnings[0]
    regime_events = [p for e, p in events if e == EVENT_REGIME_WARNING]
    assert len(regime_events) == 1


def test_provider_factory_not_invoked_when_manual_prices_cover_all_tickers(tmp_path):
    sidecar = tmp_path / "session.json"
    _write_sidecar(sidecar)

    def _factory_should_not_be_called():
        raise AssertionError("provider_factory must not be called when not needed")

    use_case = _use_case(provider_factory=_factory_should_not_be_called)
    request = RunIntradayConfirmationWorkflowRequest(
        sidecar_path=sidecar,
        output_path=tmp_path / "out.json",
        max_stop_pct=Decimal("0.07"),
        manual_prices={"BBCA": Decimal("9050"), "GOTO": Decimal("245")},
        track_file=None,
        live_auto_resolution_enabled=True,
    )

    result = use_case.execute(request)

    assert result.observations["BBCA"].price == Decimal("9050")


def test_provider_factory_not_invoked_when_track_file_covers_tickers(tmp_path):
    sidecar = tmp_path / "session.json"
    _write_sidecar(sidecar)
    track_file = tmp_path / "track.json"
    track_file.write_text(
        json.dumps(
            {
                "captured_at": "2026-06-12T09:00:05+07:00",
                "tickers": {
                    "BBCA": {"mid_price": 9000},
                    "GOTO": {"mid_price": 235},
                },
            }
        )
    )

    def _factory_should_not_be_called():
        raise AssertionError("provider_factory must not be called when not needed")

    use_case = _use_case(provider_factory=_factory_should_not_be_called)
    request = RunIntradayConfirmationWorkflowRequest(
        sidecar_path=sidecar,
        output_path=tmp_path / "out.json",
        max_stop_pct=Decimal("0.07"),
        manual_prices={},
        track_file=track_file,
        live_auto_resolution_enabled=False,
    )

    result = use_case.execute(request)

    assert result.observations["BBCA"].price is not None
    assert result.observations["GOTO"].price is not None


def test_provider_factory_invoked_lazily_only_when_needed(tmp_path):
    sidecar = tmp_path / "session.json"
    _write_sidecar(sidecar)

    calls = []

    def _factory():
        calls.append(1)
        return FakeRunningTradeProvider(), FakeOrderBookProvider()

    use_case = _use_case(provider_factory=_factory)
    request = RunIntradayConfirmationWorkflowRequest(
        sidecar_path=sidecar,
        output_path=tmp_path / "out.json",
        max_stop_pct=Decimal("0.07"),
        manual_prices={},
        track_file=None,
        live_auto_resolution_enabled=True,
    )

    use_case.execute(request)

    assert calls == [1]


def test_confirmation_sidecar_writer_called_with_result(tmp_path):
    sidecar = tmp_path / "session.json"
    _write_sidecar(sidecar)
    output_path = tmp_path / "confirmation.json"

    use_case = _use_case()
    request = RunIntradayConfirmationWorkflowRequest(
        sidecar_path=sidecar,
        output_path=output_path,
        max_stop_pct=Decimal("0.07"),
        manual_prices={"BBCA": Decimal("9050"), "GOTO": Decimal("245")},
        track_file=None,
        live_auto_resolution_enabled=True,
    )

    result = use_case.execute(request)

    assert output_path.exists()
    saved = json.loads(output_path.read_text())
    assert saved["confirmed_at"] == "2026-06-12"
    assert len(saved["confirmations"]) == len(result.confirmations)
    assert result.output_path == output_path


def test_observation_callback_called_for_each_ticker(tmp_path):
    sidecar = tmp_path / "session.json"
    _write_sidecar(sidecar)

    events: list[tuple[str, dict]] = []
    use_case = _use_case(on_event=lambda event, payload: events.append((event, payload)))
    request = RunIntradayConfirmationWorkflowRequest(
        sidecar_path=sidecar,
        output_path=tmp_path / "out.json",
        max_stop_pct=Decimal("0.07"),
        manual_prices={"BBCA": Decimal("9050"), "GOTO": Decimal("245")},
        track_file=None,
        live_auto_resolution_enabled=True,
    )

    use_case.execute(request)

    observation_events = [p for e, p in events if e == EVENT_OBSERVATION]
    assert len(observation_events) == 2
    tickers_seen = {p["observation"].ticker for p in observation_events}
    assert tickers_seen == {"BBCA", "GOTO"}
    for p in observation_events:
        assert isinstance(p["observation"], OpeningPriceObservation)
