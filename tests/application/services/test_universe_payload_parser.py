"""Tests for universe payload parser."""

from src.application.services.universe_payload_parser import (
    extract_company_rows,
    extract_company_tickers,
    extract_payload_list,
    extract_sector_rows,
    extract_subsector_rows,
    extract_tickers,
)


def test_extract_payload_list_handles_all_keys():
    """extract_payload_list handles all accepted list keys."""
    body = {"data": {"companies": [{"ticker": "BBCA"}]}}
    result = extract_payload_list(body, "companies", "list", "items", "stocks")
    assert result == [{"ticker": "BBCA"}]

    body = {"data": {"list": [{"ticker": "BBRI"}]}}
    result = extract_payload_list(body, "companies", "list", "items", "stocks")
    assert result == [{"ticker": "BBRI"}]

    body = {"data": {"items": [{"ticker": "BMRI"}]}}
    result = extract_payload_list(body, "companies", "list", "items", "stocks")
    assert result == [{"ticker": "BMRI"}]

    body = {"data": {"stocks": [{"ticker": "BBCA"}]}}
    result = extract_payload_list(body, "companies", "list", "items", "stocks")
    assert result == [{"ticker": "BBCA"}]

    body = {"data": [{"ticker": "BBCA"}]}
    result = extract_payload_list(body, "companies", "list", "items", "stocks")
    assert result == [{"ticker": "BBCA"}]

    assert extract_payload_list(None, "companies") == []
    assert extract_payload_list({}, "companies") == []
    assert extract_payload_list({"data": "not-a-list"}, "companies") == []


def test_extract_tickers_handles_all_keys():
    """extract_tickers extracts from all accepted ticker keys."""
    items = [
        {"ticker": "BBCA"},
        {"code": "BBRI"},
        {"stock_code": "BMRI"},
        {"symbol": "BDMN"},
        {"stock_detail": {"code": "BRPT"}},
    ]
    result = extract_tickers(items)
    # Sorted alphabetically
    assert result == ["BBCA", "BBRI", "BDMN", "BMRI", "BRPT"]


def test_extract_tickers_normalizes_uppercase():
    """extract_tickers normalizes to uppercase."""
    items = [{"ticker": "bbca"}, {"code": "Bbri"}]
    assert extract_tickers(items) == ["BBCA", "BBRI"]


def test_extract_tickers_deduplicates_and_sorts():
    """extract_tickers deduplicates and sorts."""
    items = [{"ticker": "BBCA"}, {"ticker": "BBRI"}, {"ticker": "BBCA"}]
    assert extract_tickers(items) == ["BBCA", "BBRI"]


def test_extract_tickers_ignores_invalid():
    """extract_tickers ignores invalid/empty codes."""
    items = [
        {"ticker": ""},
        {"ticker": None},
        {"code": "  "},
        {"ticker": "BBCA"},
    ]
    assert extract_tickers(items) == ["BBCA"]


def test_extract_company_tickers_composes_correctly():
    """extract_company_tickers combines payload list and ticker extraction."""
    body = {"data": {"companies": [{"ticker": "MYOR"}, {"code": "icbp"}]}}
    assert extract_company_tickers(body) == ["ICBP", "MYOR"]


def test_extract_sector_rows():
    """extract_sector_rows parses sector response."""
    body = {"data": {"sectors": [{"id": 70, "name": "Finance", "total_company": 10}]}}
    rows = extract_sector_rows(body)
    assert len(rows) == 1
    assert rows[0].id == "70"
    assert rows[0].name == "Finance"
    assert rows[0].count == "10"


def test_extract_sector_rows_handles_alternative_keys():
    """extract_sector_rows handles alternative key names."""
    body = {"data": {"list": [{"sector_id": 88, "sector_name": "Indices", "company_count": 5}]}}
    rows = extract_sector_rows(body)
    assert rows[0].id == "88"
    assert rows[0].name == "Indices"
    assert rows[0].count == "5"


def test_extract_subsector_rows():
    """extract_subsector_rows parses subsector response."""
    body = {"data": {"subsectors": [{"id": 10, "name": "Bank", "total_company": 5}]}}
    rows = extract_subsector_rows(body)
    assert len(rows) == 1
    assert rows[0].id == "10"
    assert rows[0].name == "Bank"
    assert rows[0].count == "5"


def test_extract_subsector_rows_handles_missing_count():
    """extract_subsector_rows uses '?' for missing count."""
    body = {"data": {"items": [{"id": 11, "name": "Insurance"}]}}
    rows = extract_subsector_rows(body)
    assert rows[0].count == "?"


def test_extract_company_rows():
    """extract_company_rows parses company response."""
    body = {"data": {"companies": [
        {"ticker": "BBCA", "name": "Bank BCA"},
        {"code": "BBRI", "company_name": "Bank BRI"},
        {"stock_detail": {"code": "BMRI", "name": "Bank Mandiri"}},
    ]}}
    rows = extract_company_rows(body)
    assert len(rows) == 3
    assert rows[0].id == "BBCA"
    assert rows[0].name == "Bank BCA"
    assert rows[1].id == "BBRI"
    assert rows[2].id == "BMRI"


def test_extract_company_rows_handles_missing_fields():
    """extract_company_rows handles missing fields with defaults."""
    body = {"data": {"items": [{}]}}  # no ticker, no name
    rows = extract_company_rows(body)
    assert rows[0].id == "?"
    assert rows[0].name == "Unknown Name"


def test_extract_company_rows_nested_stock_detail():
    """extract_company_rows extracts from nested stock_detail."""
    body = {"data": {"list": [{"stock_detail": {"code": "TEST", "name": "Test Co"}}]}}
    rows = extract_company_rows(body)
    assert rows[0].id == "TEST"
    assert rows[0].name == "Test Co"
