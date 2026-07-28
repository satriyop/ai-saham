"""Unit tests for StockbitMacroCalendarProvider with mocked api_client."""

import json
from pathlib import Path

import pytest

from src.application.ports.macro_calendar_provider import MacroCalendarFetchError
from src.infrastructure.browser.stockbit_macro_calendar import StockbitMacroCalendarProvider
from src.infrastructure.config.stockbit_config import StockbitConfig

FIXTURE = (
    Path(__file__).resolve().parents[2] / "fixtures" / "stockbit" / "economic_calendar_sample.json"
)


class FakeApiClient:
    def __init__(self, body):
        self._body = body
        self.urls: list[str] = []

    def get(self, url: str):
        self.urls.append(url)
        return self._body


def test_fetch_success_parses_events():
    body = json.loads(FIXTURE.read_text(encoding="utf-8"))
    client = FakeApiClient(body)
    provider = StockbitMacroCalendarProvider(
        api_client=client,  # type: ignore[arg-type]
        stockbit_config=StockbitConfig(),
    )
    events = provider.fetch_events()
    assert len(events) == 4
    assert client.urls == [StockbitConfig().calendar_economic_url]


def test_none_body_raises_auth_or_network():
    provider = StockbitMacroCalendarProvider(
        api_client=FakeApiClient(None),  # type: ignore[arg-type]
        stockbit_config=StockbitConfig(),
    )
    with pytest.raises(MacroCalendarFetchError) as exc:
        provider.fetch_events()
    assert exc.value.reason == "auth-or-network"
    assert exc.value.partial_events == []


def test_malformed_body_raises_parse_error():
    provider = StockbitMacroCalendarProvider(
        api_client=FakeApiClient({"data": {"economic": "not-a-list"}}),  # type: ignore[arg-type]
        stockbit_config=StockbitConfig(),
    )
    with pytest.raises(MacroCalendarFetchError) as exc:
        provider.fetch_events()
    assert exc.value.reason.startswith("parse-error:")
