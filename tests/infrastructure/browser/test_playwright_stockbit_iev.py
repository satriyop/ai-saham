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


def test_fetch_iev_all_boards_preserves_iep_after_dedup(monkeypatch):
    responses = iter([
        _body("BBCA", 450_000, 5_925),
        _body("BBCA", 430_000, 5_900),
    ])

    def fake_exodus_get(url, token):
        return next(responses)

    monkeypatch.setattr(stockbit, "_exodus_get", fake_exodus_get)

    movers = stockbit._fetch_iev_all_boards("token")

    assert len(movers) == 1
    assert movers[0].ticker == "BBCA"
    assert movers[0].iev == 450_000
    assert movers[0].iep == 5_925
