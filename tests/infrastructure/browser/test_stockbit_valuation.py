"""Tests for StockbitValuationProvider and valuation response parser."""

from datetime import datetime

import pytest

from src.domain.value_objects.valuation_metrics import ValuationMetrics
from src.infrastructure.browser.stockbit_valuation import (
    StockbitValuationProvider,
    _parse_response,
)

# ── _parse_response ────────────────────────────────────────────────────────────

def _make_body(entries: list[dict] | None = None) -> dict:
    if entries is None:
        entries = [
            {"id": 12635, "value": "20.96"},
            {"id": 0,     "value": "0.00"},   # placeholder — must be filtered
            {"id": 13200, "value": "471.10"},
        ]
    return {"data": entries, "message": "Metric value for company BBCA"}


def test_parse_response_basic():
    result = _parse_response("BBCA", _make_body())
    assert result is not None
    assert result.ticker == "BBCA"
    assert result.pe_current == pytest.approx(20.96)
    assert result.eps_ttm == pytest.approx(471.10)


def test_parse_response_filters_id_zero():
    result = _parse_response("BBCA", _make_body())
    assert 0 not in result.raw


def test_parse_response_filters_zero_values():
    body = _make_body([{"id": 12635, "value": "0.00"}, {"id": 13200, "value": "20.00"}])
    result = _parse_response("BBCA", body)
    assert result is not None
    assert 12635 not in result.raw
    assert 13200 in result.raw


def test_parse_response_returns_none_when_all_zero():
    body = _make_body([{"id": 12635, "value": "0.00"}, {"id": 0, "value": "0.00"}])
    result = _parse_response("BBCA", body)
    assert result is None


def test_parse_response_returns_none_when_data_not_list():
    result = _parse_response("BBCA", {"data": {}, "message": "ok"})
    assert result is None


def test_parse_response_skips_non_dict_entries():
    body = _make_body([{"id": 12635, "value": "20.96"}, "bad", None])
    result = _parse_response("BBCA", body)
    assert result is not None
    assert 12635 in result.raw


def test_parse_response_skips_bad_value():
    body = _make_body([{"id": 12635, "value": "not_a_number"}, {"id": 13200, "value": "471.10"}])
    result = _parse_response("BBCA", body)
    assert result is not None
    assert 12635 not in result.raw
    assert 13200 in result.raw


def test_parse_response_ticker_uppercased():
    result = _parse_response("bbca", _make_body())
    assert result.ticker == "BBCA"


# ── ValuationMetrics properties ────────────────────────────────────────────────

def test_valuation_metrics_labeled_returns_known_ids():
    metrics = ValuationMetrics(
        ticker="BBCA",
        fetched_at=datetime(2026, 6, 20),
        raw={12635: 20.96, 13200: 471.10, 99999: 1.0},
    )
    labeled = dict(metrics.labeled)
    assert "P/E" in labeled
    assert labeled["P/E"] == pytest.approx(20.96)
    assert "EPS (TTM)" in labeled
    assert labeled["EPS (TTM)"] == pytest.approx(471.10)


def test_valuation_metrics_labeled_excludes_unknown_ids():
    metrics = ValuationMetrics(
        ticker="BBCA",
        fetched_at=datetime(2026, 6, 20),
        raw={99999: 1.0},
    )
    assert metrics.labeled == []


def test_valuation_metrics_is_empty():
    m = ValuationMetrics(ticker="BBCA", fetched_at=datetime(2026, 6, 20), raw={})
    assert m.is_empty is True
    m2 = ValuationMetrics(ticker="BBCA", fetched_at=datetime(2026, 6, 20), raw={12635: 20.96})
    assert m2.is_empty is False


def test_valuation_metrics_pe_sd_bands():
    m = ValuationMetrics(
        ticker="TEST",
        fetched_at=datetime(2026, 6, 20),
        raw={12623: 15.0, 12626: 18.0},
    )
    assert m.pe_plus1_sd == pytest.approx(15.0)
    assert m.pe_plus2_sd == pytest.approx(18.0)
    assert m.pe_current is None


# ── SQLite cache round-trip ────────────────────────────────────────────────────

@pytest.fixture
def provider(tmp_path):
    return StockbitValuationProvider(broker_provider=None, db_path=tmp_path / "test.db")


def test_cache_schema_created(provider):
    with provider._get_conn() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='valuation_metrics_cache'"
        ).fetchone()
    assert row is not None


def test_cache_write_and_read(provider):
    metrics = ValuationMetrics(
        ticker="BBCA",
        fetched_at=datetime(2026, 6, 20, 10, 0),
        raw={12635: 20.96, 13200: 471.10},
    )
    provider._write_cache(metrics)
    result = provider._read_cache("BBCA")
    assert result is not None
    assert result.ticker == "BBCA"
    assert result.raw[12635] == pytest.approx(20.96)
    assert result.raw[13200] == pytest.approx(471.10)


def test_is_cache_fresh_false_when_empty(provider):
    assert provider.is_cache_fresh("BBCA") is False


def test_is_cache_fresh_true_after_write(provider):
    metrics = ValuationMetrics(
        ticker="BBCA",
        fetched_at=datetime.now(),
        raw={12635: 20.96},
    )
    provider._write_cache(metrics)
    assert provider.is_cache_fresh("BBCA") is True


def test_get_valuation_returns_none_without_provider(provider):
    result = provider.get_valuation("BBCA")
    assert result is None
