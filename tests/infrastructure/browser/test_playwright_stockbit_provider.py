"""
Regression tests for PlaywrightStockbitProvider proving the browser-profile-age
guard (`_assert_session_fresh`) and the `profile_dir` constructor param were
fully removed. The provider now depends only on an injected StockbitApiClient
and never touches the filesystem.
"""

from __future__ import annotations

import inspect
import time

from src.infrastructure.browser.playwright_stockbit_provider import (
    PlaywrightStockbitProvider,
)

# ── Fakes ─────────────────────────────────────────────────────────────────


def _movers_body(ticker: str, iev: int, iep: int | None = None) -> dict:
    iepiev_detail = {"iev": {"raw": iev}}
    if iep is not None:
        iepiev_detail["iep"] = {"raw": iep}
    return {
        "data": {
            "mover_list": [
                {
                    "stock_detail": {"code": ticker},
                    "iepiev_detail": iepiev_detail,
                }
            ]
        }
    }


def _orderbook_body(bid_price: int, bid_qty: int, offer_price: int, offer_qty: int) -> dict:
    return {
        "data": {
            "iepiev": {
                "best_bid_offer": {
                    "bid": {"price": {"raw": bid_price}, "quantity": {"raw": bid_qty}},
                    "offer": {"price": {"raw": offer_price}, "quantity": {"raw": offer_qty}},
                }
            }
        }
    }


class _FakeApiClient:
    """Stub StockbitApiClient — returns per-URL canned bodies, no network I/O."""

    def __init__(self, responses: dict[str, dict | None]):
        self._responses = responses
        self.calls: list[str] = []

    def get(self, url, params=None):
        self.calls.append(url)
        for key, body in self._responses.items():
            if key in url:
                return body
        return None


class _AlwaysNoneApiClient:
    """Stub that simulates an unauthenticated/failed API call for every URL."""

    def __init__(self):
        self.calls: list[str] = []

    def get(self, url, params=None):
        self.calls.append(url)
        return None


def _fake_movers_client() -> _FakeApiClient:
    return _FakeApiClient(
        {
            "market-mover": _movers_body("BBCA", 450_000, 5_925),
            "orderbook": _orderbook_body(5_900, 10, 5_925, 20),
        }
    )


# ── No filesystem / no profile-age awareness ────────────────────────────────


def test_fetch_preopen_movers_ignores_profile_dir_contents(tmp_path):
    # Write a stale marker into tmp_path to prove the provider never reads it.
    (tmp_path / ".logged_in_at").write_text(str(time.time() - 100 * 3600))

    fake_client = _fake_movers_client()
    provider = PlaywrightStockbitProvider(api_client=fake_client)
    assert provider.provides_live_preopen_data is True

    movers = provider.fetch_preopen_movers(iev_min=1)

    assert len(movers) == 1
    assert movers[0].ticker == "BBCA"


def test_fetch_top5_iev_with_orderbooks_ignores_profile_dir_contents(tmp_path):
    (tmp_path / ".logged_in_at").write_text(str(time.time() - 100 * 3600))

    fake_client = _fake_movers_client()
    provider = PlaywrightStockbitProvider(api_client=fake_client)

    results = provider.fetch_top5_iev_with_orderbooks(top_n=5)

    assert len(results) == 1
    assert results[0].ticker == "BBCA"
    assert results[0].best_bid is not None


def test_fetch_iev_snapshot_ignores_profile_dir_contents(tmp_path):
    (tmp_path / ".logged_in_at").write_text(str(time.time() - 100 * 3600))

    fake_client = _fake_movers_client()
    provider = PlaywrightStockbitProvider(api_client=fake_client)

    snapshot = provider.fetch_iev_snapshot(top_n=50)

    assert len(snapshot) == 1
    assert snapshot[0].ticker == "BBCA"


# ── Structural proof the guard and the dead param are gone ─────────────────


def test_no_assert_session_fresh_method_exists():
    assert not hasattr(PlaywrightStockbitProvider, "_assert_session_fresh")


def test_constructor_no_longer_accepts_profile_dir():
    params = inspect.signature(PlaywrightStockbitProvider.__init__).parameters
    assert "profile_dir" not in params
    assert "api_client" in params


# ── Unauthenticated / failed API call behavior (no guard involved) ─────────


def test_fetch_preopen_movers_returns_empty_list_when_api_client_returns_none():
    fake_client = _AlwaysNoneApiClient()
    provider = PlaywrightStockbitProvider(api_client=fake_client)

    result = provider.fetch_preopen_movers(iev_min=1)

    assert result == []
    assert len(fake_client.calls) >= 1
