"""Tests for Stockbit IEV/IEP mover parsing."""

from src.infrastructure.browser import playwright_stockbit_provider as stockbit


def _body(ticker: str, iev: int, iep: int | None) -> dict:
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


def test_parse_iev_response_captures_iep():
    movers = stockbit._parse_iev_response(_body("BBCA", 450_000, 5_925), iev_min=1)

    assert len(movers) == 1
    assert movers[0].ticker == "BBCA"
    assert movers[0].iev == 450_000
    assert movers[0].iep == 5_925


class _FakeApiClient:
    """Stub StockbitApiClient that returns successive responses per URL call."""

    def __init__(self, responses):
        self._iter = iter(responses)

    def get(self, url, params=None):
        return next(self._iter)


def test_fetch_iev_all_boards_preserves_iep_after_dedup():
    client = _FakeApiClient([
        _body("BBCA", 450_000, 5_925),
        _body("BBCA", 430_000, 5_900),
    ])

    movers = stockbit._fetch_iev_all_boards(client)

    assert len(movers) == 1
    assert movers[0].ticker == "BBCA"
    assert movers[0].iev == 450_000
    assert movers[0].iep == 5_925
