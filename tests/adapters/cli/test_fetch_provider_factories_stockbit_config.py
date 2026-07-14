"""
Tests proving fetch_market/fetch_broker provider factories wire Stockbit
config explicitly instead of relying on provider constructor fallback loading.

Layer: Adapter (Tests)
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import src.adapters.cli.fetch_broker_provider_factory as broker_data_factory
import src.adapters.cli.fetch_market_provider_factory as market_provider_factory
import src.infrastructure.browser.stockbit_broker_provider as broker_provider_module
import src.infrastructure.browser.stockbit_config_bundle as config_bundle_module
import src.infrastructure.composition.stockbit_session_factory as session_factory_module
from src.infrastructure.config.stockbit_config import StockbitConfig


class _FakeStockbitBrokerProvider:
    def __init__(self, api_client, stockbit_config=None):
        self.api_client = api_client
        self.stockbit_config = stockbit_config


def _patch_config_loader_once(monkeypatch):
    calls = []
    sentinel = StockbitConfig()

    def _fake_load() -> StockbitConfig:
        calls.append(sentinel)
        return sentinel

    monkeypatch.setattr(config_bundle_module, "load_stockbit_provider_config", _fake_load)
    return calls, sentinel


def test_create_broker_provider_stockbit_loads_config_once_and_threads_it(monkeypatch):
    calls, sentinel = _patch_config_loader_once(monkeypatch)

    seen_sessions = []

    def _fake_get_session(stockbit_config=None):
        seen_sessions.append(stockbit_config)
        return SimpleNamespace(api_client=object(), authenticated=True)

    monkeypatch.setattr(session_factory_module, "get_stockbit_session", _fake_get_session)
    monkeypatch.setattr(
        broker_provider_module, "StockbitBrokerProvider", _FakeStockbitBrokerProvider
    )

    provider, name = market_provider_factory.create_broker_provider("stockbit")

    assert name == "stockbit"
    assert len(calls) == 1
    assert seen_sessions == [sentinel]
    assert provider.stockbit_config is sentinel


def test_create_broker_provider_auto_detect_loads_config_once_and_threads_it(monkeypatch):
    calls, sentinel = _patch_config_loader_once(monkeypatch)

    seen_sessions = []

    def _fake_get_session(stockbit_config=None):
        seen_sessions.append(stockbit_config)
        return SimpleNamespace(api_client=object(), authenticated=True)

    monkeypatch.setattr(session_factory_module, "get_stockbit_session", _fake_get_session)
    monkeypatch.setattr(
        broker_provider_module, "StockbitBrokerProvider", _FakeStockbitBrokerProvider
    )

    provider, name = market_provider_factory.create_broker_provider(None)

    assert name == "stockbit"
    assert len(calls) == 1
    assert seen_sessions == [sentinel]
    assert provider.stockbit_config is sentinel


def test_create_broker_data_provider_stockbit_loads_config_once_and_threads_it(monkeypatch):
    calls, sentinel = _patch_config_loader_once(monkeypatch)

    seen_sessions = []

    def _fake_get_session(stockbit_config=None):
        seen_sessions.append(stockbit_config)
        return SimpleNamespace(api_client=object(), authenticated=True)

    monkeypatch.setattr(session_factory_module, "get_stockbit_session", _fake_get_session)
    monkeypatch.setattr(
        broker_provider_module, "StockbitBrokerProvider", _FakeStockbitBrokerProvider
    )

    provider = broker_data_factory.create_broker_data_provider("stockbit")

    assert len(calls) == 1
    assert seen_sessions == [sentinel]
    assert provider.stockbit_config is sentinel


def test_create_broker_data_provider_missing_session_raises_without_config_reload(
    monkeypatch,
):
    calls, _sentinel = _patch_config_loader_once(monkeypatch)

    monkeypatch.setattr(
        session_factory_module, "get_stockbit_session", lambda stockbit_config=None: None
    )

    with pytest.raises(ValueError, match="No active Stockbit session"):
        broker_data_factory.create_broker_data_provider("stockbit")

    assert len(calls) == 1
