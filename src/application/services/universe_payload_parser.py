"""Payload parsing utilities for Stockbit Exodus universe API responses.

Layer: Application
"""

from typing import Any

from src.application.dto.universe_management import UniverseInspectRow


def extract_payload_list(
    body: dict[str, Any] | None, *keys: str
) -> list[dict[str, Any]]:
    """Extract a list of dict items from a response body using known key patterns.

    Accepted list keys (in order): companies, list, items, stocks.
    """
    if not body:
        return []
    data = body.get("data")
    if isinstance(data, list):
        return [i for i in data if isinstance(i, dict)]
    if isinstance(data, dict):
        for k in keys:
            if isinstance(data.get(k), list):
                return [i for i in data[k] if isinstance(i, dict)]
    return []


def extract_tickers(items: list[dict[str, Any]]) -> list[str]:
    """Extract ticker symbols from a list of company/item dicts.

    Accepted ticker keys (in order): ticker, code, stock_code, symbol,
    stock_detail.code (nested).

    Normalizes to uppercase, deduplicates, and sorts.
    """
    tickers: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        code = (
            item.get("ticker")
            or item.get("code")
            or item.get("stock_code")
            or item.get("symbol")
            or (item.get("stock_detail") or {}).get("code")
        )
        if code and isinstance(code, str) and code.strip():
            tickers.append(code.strip().upper())
    return sorted(set(tickers))


def extract_company_tickers(body: dict[str, Any] | None) -> list[str]:
    """Extract tickers from a company endpoint response."""
    items = extract_payload_list(body, "companies", "list", "items", "stocks")
    return extract_tickers(items)


def extract_sector_rows(body: dict[str, Any] | None) -> list[UniverseInspectRow]:
    """Extract sector rows from /emitten/sectors response."""
    items = extract_payload_list(body, "sectors", "list", "items")
    rows: list[UniverseInspectRow] = []
    for s in items:
        sid = s.get("id") or s.get("sector_id") or "?"
        name = s.get("name") or s.get("sector_name") or "?"
        count = s.get("total_company") or s.get("company_count") or ""
        rows.append(
            UniverseInspectRow(id=str(sid), name=name, count=str(count) if count else "—")
        )
    return rows


def extract_subsector_rows(body: dict[str, Any] | None) -> list[UniverseInspectRow]:
    """Extract subsector rows from /emitten/sectors/{id}/subsectors response."""
    items = extract_payload_list(body, "subsectors", "list", "items")
    rows: list[UniverseInspectRow] = []
    for sub in items:
        sub_id = sub.get("id") or sub.get("subsector_id") or "?"
        name = sub.get("name") or sub.get("subsector_name") or "?"
        count = sub.get("total_company") or sub.get("company_count") or ""
        rows.append(
            UniverseInspectRow(id=str(sub_id), name=name, count=str(count) if count else "?")
        )
    return rows


def extract_company_rows(body: dict[str, Any] | None) -> list[UniverseInspectRow]:
    """Extract company rows from /emitten/v3/sector/{sector}/subsector/{id}/company response."""
    items = extract_payload_list(body, "companies", "list", "items", "stocks")
    rows: list[UniverseInspectRow] = []
    for item in items:
        code = (
            item.get("ticker")
            or item.get("code")
            or item.get("stock_code")
            or item.get("symbol")
            or (item.get("stock_detail") or {}).get("code")
            or "?"
        )
        name = (
            item.get("name")
            or item.get("company_name")
            or item.get("company")
            or (item.get("stock_detail") or {}).get("name")
            or "Unknown Name"
        )
        rows.append(UniverseInspectRow(id=str(code).upper(), name=name, count=""))
    return rows
