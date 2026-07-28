"""
Tests for macro calendar wiring in fetch market:
refresh_market_macro_calendar() + --no-macro-calendar CLI routing.
"""

from pathlib import Path

import pytest
from typer import Typer
from typer.testing import CliRunner

import src.adapters.cli.fetch_market_commands as fetch_market_commands
from src.adapters.cli.fetch_market_commands import fetch_market
from src.application.use_case.sync_macro_calendar_use_case import SyncMacroCalendarResponse
from src.infrastructure.composition.fetch_market.fetch_market_macro_calendar_refresh import (
    refresh_market_macro_calendar,
)


class FakeUseCase:
    def __init__(self, response=None, exception: Exception | None = None):
        self._response = response
        self._exception = exception
        self.execute_calls: list = []

    def execute(self, request):
        self.execute_calls.append(request)
        if self._exception is not None:
            raise self._exception
        return self._response


def _response(**overrides) -> SyncMacroCalendarResponse:
    kwargs = dict(
        status="success",
        fetched_count=2,
        stored_count=2,
        category_counts={"bi_rate": 1, "other": 1},
        errors=(),
        from_cache=False,
    )
    kwargs.update(overrides)
    return SyncMacroCalendarResponse(**kwargs)


def _patch_use_case(monkeypatch, response=None, exception=None):
    from src.infrastructure.composition.fetch_market import (
        fetch_market_macro_calendar_refresh as refresh_module,
    )

    fake_uc = FakeUseCase(response=response, exception=exception)
    monkeypatch.setattr(
        refresh_module,
        "SyncMacroCalendarUseCase",
        lambda *args, **kwargs: fake_uc,
    )
    return fake_uc


class TestRefreshMarketMacroCalendar:
    def test_provider_construction_failure_returns_err(self, monkeypatch, tmp_path: Path):
        import src.infrastructure.browser.stockbit_macro_calendar as provider_module

        monkeypatch.setattr(
            provider_module,
            "StockbitMacroCalendarProvider",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        status = refresh_market_macro_calendar(
            db_path=tmp_path / "x.db", api_client=object(), refresh=False
        )
        assert status.startswith("ERR:")

    def test_cached_status(self, monkeypatch, tmp_path: Path):
        _patch_use_case(
            monkeypatch,
            response=_response(status="cached", from_cache=True, fetched_count=0, stored_count=0),
        )
        status = refresh_market_macro_calendar(
            db_path=tmp_path / "x.db", api_client=object(), refresh=False
        )
        assert status == "cached"

    def test_success_lists_category_counts(self, monkeypatch, tmp_path: Path):
        _patch_use_case(monkeypatch, response=_response())
        status = refresh_market_macro_calendar(
            db_path=tmp_path / "x.db", api_client=object(), refresh=False
        )
        assert status.startswith("stockbit")
        assert "bi_rate=1" in status
        assert "other=1" in status

    def test_failed_auth_maps_to_err_auth(self, monkeypatch, tmp_path: Path):
        _patch_use_case(
            monkeypatch,
            response=_response(
                status="failed",
                fetched_count=0,
                stored_count=0,
                category_counts={},
                errors=("auth-or-network",),
            ),
        )
        status = refresh_market_macro_calendar(
            db_path=tmp_path / "x.db", api_client=object(), refresh=False
        )
        assert status == "ERR:auth"

    def test_refresh_flag_threaded(self, monkeypatch, tmp_path: Path):
        fake = _patch_use_case(monkeypatch, response=_response())
        refresh_market_macro_calendar(db_path=tmp_path / "x.db", api_client=object(), refresh=True)
        assert fake.execute_calls[0].force_remote_fetch is True


def _make_app() -> Typer:
    app = Typer()
    app.command()(fetch_market)
    return app


class _CountingMacroRefresh:
    def __init__(self, status: str = "stockbit bi_rate=1") -> None:
        self.status = status
        self.calls: list[dict] = []

    def __call__(self, db_path, api_client, refresh):
        self.calls.append({"db_path": db_path, "api_client": api_client, "refresh": refresh})
        return self.status


@pytest.fixture
def _base_monkeypatches(monkeypatch, tmp_path: Path):
    class _FakeApiClient:
        pass

    class _FakeStockbitBrokerProvider:
        def __init__(self):
            self.api_client = _FakeApiClient()

    fake_broker_provider = _FakeStockbitBrokerProvider()

    monkeypatch.setattr(
        fetch_market_commands,
        "create_broker_provider",
        lambda name: (fake_broker_provider, "stockbit"),
    )
    monkeypatch.setattr(
        "src.infrastructure.composition.fetch_market.fetch_market_workflow_factory.resolve_tickers",
        lambda **kwargs: ["BBCA", "BBRI", "BMRI"],
    )
    monkeypatch.setattr(
        "src.application.services.fetch_market_provider_precondition.FetchMarketProviderPrecondition.validate",
        lambda self, request: None,
    )
    from src.application.use_case.fetch_market_refresh_use_case import (
        FetchMarketRefreshResponse,
    )

    monkeypatch.setattr(
        "src.application.use_case.fetch_market_refresh_use_case.FetchMarketRefreshUseCase.execute",
        lambda self, request, on_ticker_complete=None: FetchMarketRefreshResponse(
            ticker_list=request.tickers,
            stock_tickers_only=request.tickers,
            ticker_results=[],
            ok_count=len(request.tickers),
            fail_count=0,
        ),
    )
    # Avoid real CA calendar I/O in these tests
    monkeypatch.setattr(
        "src.infrastructure.composition.fetch_market.fetch_market_calendar_refresh.refresh_market_calendar",
        lambda *a, **k: "cached",
    )
    return tmp_path


class TestMacroCalendarInFetchMarket:
    def test_called_once_for_multi_ticker(self, monkeypatch, _base_monkeypatches):
        counting = _CountingMacroRefresh()
        monkeypatch.setattr(
            "src.infrastructure.composition.fetch_market.fetch_market_macro_calendar_refresh.refresh_market_macro_calendar",
            counting,
        )
        result = CliRunner().invoke(
            _make_app(),
            [
                "BBCA",
                "BBRI",
                "BMRI",
                "--provider",
                "yahoo",
                "--no-meta",
                "--db",
                str(_base_monkeypatches / "data.db"),
            ],
        )
        assert result.exit_code == 0, result.output
        assert len(counting.calls) == 1
        assert "Macro calendar: stockbit bi_rate=1" in result.output

    def test_no_macro_calendar_flag_skips(self, monkeypatch, _base_monkeypatches):
        counting = _CountingMacroRefresh()
        monkeypatch.setattr(
            "src.infrastructure.composition.fetch_market.fetch_market_macro_calendar_refresh.refresh_market_macro_calendar",
            counting,
        )
        result = CliRunner().invoke(
            _make_app(),
            [
                "BBCA",
                "--provider",
                "yahoo",
                "--no-meta",
                "--no-macro-calendar",
                "--db",
                str(_base_monkeypatches / "data.db"),
            ],
        )
        assert result.exit_code == 0, result.output
        assert counting.calls == []
        assert "Macro calendar: skip:--no-macro-calendar" in result.output

    def test_no_enrichment_does_not_skip_macro(self, monkeypatch, _base_monkeypatches):
        counting = _CountingMacroRefresh()
        monkeypatch.setattr(
            "src.infrastructure.composition.fetch_market.fetch_market_macro_calendar_refresh.refresh_market_macro_calendar",
            counting,
        )
        result = CliRunner().invoke(
            _make_app(),
            [
                "BBCA",
                "--provider",
                "yahoo",
                "--no-meta",
                "--no-enrichment",
                "--db",
                str(_base_monkeypatches / "data.db"),
            ],
        )
        assert result.exit_code == 0, result.output
        assert len(counting.calls) == 1
        assert "Calendar: skip:--no-enrichment" in result.output
        assert "Macro calendar: stockbit bi_rate=1" in result.output
