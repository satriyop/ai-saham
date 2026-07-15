"""Catalog constants for SQLite data-quality audit read model.

Layer: Infrastructure
"""

from __future__ import annotations

ENRICHMENT_TABLE_SPECS: tuple[tuple[str, str], ...] = (
    ("ticker_notation_cache", "fetched_at"),
    ("analyst_cache", "fetched_date"),
    ("insider_cache", "fetched_date"),
    ("seasonality_cache", "fetched_month"),
    ("corp_action_cache", "fetched_date"),
    ("shareholding_composition", "fetched_date"),
    ("bandar_detector", "session_date"),
    ("company_fundamentals", "fetched_date"),
    ("forward_estimates_cache", "fetched_date"),
)

CANDLE_PROVENANCE_COLUMNS: frozenset[str] = frozenset(
    {"source", "volume_unit", "price_adjustment_policy"}
)
