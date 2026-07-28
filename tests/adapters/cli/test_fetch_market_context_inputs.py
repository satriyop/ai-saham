"""Adapter wiring tests for `saham fetch market`'s global context ticker refresh.

Verifies that fetch_market_context_inputs — not the application use case —
owns:
- constructing the no-suffix Yahoo provider exactly once (market_suffix="")
- passing configured global context tickers as non-IDX tickers so they
  never receive the `.JK` suffix applied to regular IDX tickers
- passing config/market_context_engine.yaml's global_context_end_tolerance_days
  into each per-ticker refresh request
- ADR-053 sector-macro live-map series (CL=F, CPO=F, …) ride along automatically
"""

from pathlib import Path

from src.application.use_case.refresh_market_data_use_case import RefreshMarketDataResponse
from src.infrastructure.composition.fetch_market import fetch_market_context_inputs as wiring
from src.infrastructure.config.market_context_config import (
    EidoFactorConfig,
    MarketContextConfig,
    MarketContextFetchConfig,
    UsdIdrFactorConfig,
    VixFactorConfig,
)


class _FakeYahooFinanceProvider:
    instances: list["_FakeYahooFinanceProvider"] = []

    def __init__(self, market_suffix=None, non_idx_tickers=None):
        self.market_suffix = market_suffix
        self.non_idx_tickers = non_idx_tickers
        _FakeYahooFinanceProvider.instances.append(self)


class _FakeMarketDataUseCase:
    captured_requests: list = []

    def __init__(self, provider, repository):
        self.provider = provider
        self.repository = repository

    def execute(self, request):
        _FakeMarketDataUseCase.captured_requests.append(request)
        return RefreshMarketDataResponse(
            ticker=request.ticker,
            status="+1rows/span=1d",
            candles=[],
            date_range=None,
            added_count=1,
            fetch_modes=frozenset(),
        )


def test_refresh_market_context_inputs_uses_no_suffix_provider_and_configured_tolerance(
    monkeypatch, tmp_path: Path
):
    _FakeYahooFinanceProvider.instances.clear()
    _FakeMarketDataUseCase.captured_requests.clear()

    dummy_cfg = MarketContextConfig(
        vix=VixFactorConfig(enabled=True, ticker="^VIX"),
        eido=EidoFactorConfig(enabled=True, ticker="EIDO"),
        usd_idr=UsdIdrFactorConfig(enabled=False),
        fetch=MarketContextFetchConfig(global_context_end_tolerance_days=7),
    )

    monkeypatch.setattr(wiring, "load_market_context_config", lambda: dummy_cfg)
    monkeypatch.setattr(wiring, "get_global_context_tickers", lambda: {"^VIX", "EIDO", "IDR=X"})
    monkeypatch.setattr(
        "src.infrastructure.config.sector_macro_context_config_loader."
        "required_sector_macro_series_tickers",
        lambda: frozenset({"CL=F", "CPO=F", "IDR=X"}),
    )
    monkeypatch.setattr(wiring, "YahooFinanceProvider", _FakeYahooFinanceProvider)
    monkeypatch.setattr(wiring, "RefreshMarketDataUseCase", _FakeMarketDataUseCase)

    response = wiring.refresh_market_context_inputs(tmp_path / "dummy.db", days=90)

    # No-suffix provider constructed exactly once, with configured global tickers
    # passed as non-IDX tickers so they never receive the .JK suffix.
    assert len(_FakeYahooFinanceProvider.instances) == 1
    provider = _FakeYahooFinanceProvider.instances[0]
    assert provider.market_suffix == ""
    assert provider.non_idx_tickers == {"^VIX", "EIDO", "IDR=X"}

    # Enabled MCE factors + sector-macro live maps (sorted: CL=F, CPO=F).
    # IDR=X appears only via sector_macro because MCE usd_idr is disabled here.
    captured = [
        (r.ticker, r.days, r.end_tolerance_days) for r in _FakeMarketDataUseCase.captured_requests
    ]
    assert captured == [
        ("^VIX", 90, 7),
        ("EIDO", 90, 7),
        ("CL=F", 90, 7),
        ("CPO=F", 90, 7),
        ("IDR=X", 90, 7),
    ]
    assert response.statuses == (
        "^VIX(vix):+1rows/span=1d",
        "EIDO(eido):+1rows/span=1d",
        "CL=F(sector_macro):+1rows/span=1d",
        "CPO=F(sector_macro):+1rows/span=1d",
        "IDR=X(sector_macro):+1rows/span=1d",
    )


def test_sector_macro_series_dedupe_against_mce_usd_idr(monkeypatch, tmp_path: Path):
    """IDR=X must not be refreshed twice when both MCE and sector-macro need it."""
    _FakeYahooFinanceProvider.instances.clear()
    _FakeMarketDataUseCase.captured_requests.clear()

    dummy_cfg = MarketContextConfig(
        vix=VixFactorConfig(enabled=False),
        eido=EidoFactorConfig(enabled=False),
        usd_idr=UsdIdrFactorConfig(enabled=True, ticker="IDR=X"),
        fetch=MarketContextFetchConfig(global_context_end_tolerance_days=1),
    )
    monkeypatch.setattr(wiring, "load_market_context_config", lambda: dummy_cfg)
    monkeypatch.setattr(wiring, "get_global_context_tickers", lambda: {"IDR=X", "CL=F"})
    monkeypatch.setattr(
        "src.infrastructure.config.sector_macro_context_config_loader."
        "required_sector_macro_series_tickers",
        lambda: frozenset({"CL=F", "IDR=X"}),
    )
    monkeypatch.setattr(wiring, "YahooFinanceProvider", _FakeYahooFinanceProvider)
    monkeypatch.setattr(wiring, "RefreshMarketDataUseCase", _FakeMarketDataUseCase)

    response = wiring.refresh_market_context_inputs(tmp_path / "dummy.db", days=30)
    tickers = [r.ticker for r in _FakeMarketDataUseCase.captured_requests]
    assert tickers.count("IDR=X") == 1
    assert "CL=F" in tickers
    # IDR kept MCE factor label (added first); CL is sector_macro
    assert "IDR=X(usd_idr):+1rows/span=1d" in response.statuses
    assert "CL=F(sector_macro):+1rows/span=1d" in response.statuses


def test_refresh_market_context_inputs_skips_when_nothing_enabled(monkeypatch, tmp_path: Path):
    _FakeYahooFinanceProvider.instances.clear()
    _FakeMarketDataUseCase.captured_requests.clear()

    dummy_cfg = MarketContextConfig(
        vix=VixFactorConfig(enabled=False),
        eido=EidoFactorConfig(enabled=False),
        usd_idr=UsdIdrFactorConfig(enabled=False),
    )

    monkeypatch.setattr(wiring, "load_market_context_config", lambda: dummy_cfg)
    monkeypatch.setattr(wiring, "YahooFinanceProvider", _FakeYahooFinanceProvider)
    monkeypatch.setattr(wiring, "RefreshMarketDataUseCase", _FakeMarketDataUseCase)
    # No sector-macro maps either
    monkeypatch.setattr(
        "src.infrastructure.config.sector_macro_context_config_loader."
        "required_sector_macro_series_tickers",
        lambda: frozenset(),
    )

    response = wiring.refresh_market_context_inputs(tmp_path / "dummy.db")

    assert response.statuses == ()
    assert _FakeYahooFinanceProvider.instances == []


def test_sector_macro_still_refreshes_when_all_mce_factors_disabled(monkeypatch, tmp_path: Path):
    _FakeYahooFinanceProvider.instances.clear()
    _FakeMarketDataUseCase.captured_requests.clear()

    dummy_cfg = MarketContextConfig(
        vix=VixFactorConfig(enabled=False),
        eido=EidoFactorConfig(enabled=False),
        usd_idr=UsdIdrFactorConfig(enabled=False),
        fetch=MarketContextFetchConfig(global_context_end_tolerance_days=3),
    )
    monkeypatch.setattr(wiring, "load_market_context_config", lambda: dummy_cfg)
    monkeypatch.setattr(wiring, "get_global_context_tickers", lambda: {"CL=F"})
    monkeypatch.setattr(
        "src.infrastructure.config.sector_macro_context_config_loader."
        "required_sector_macro_series_tickers",
        lambda: frozenset({"CL=F"}),
    )
    monkeypatch.setattr(wiring, "YahooFinanceProvider", _FakeYahooFinanceProvider)
    monkeypatch.setattr(wiring, "RefreshMarketDataUseCase", _FakeMarketDataUseCase)

    response = wiring.refresh_market_context_inputs(tmp_path / "dummy.db", days=60)
    assert [
        (r.ticker, r.days, r.end_tolerance_days) for r in _FakeMarketDataUseCase.captured_requests
    ] == [("CL=F", 60, 3)]
    assert response.statuses == ("CL=F(sector_macro):+1rows/span=1d",)
