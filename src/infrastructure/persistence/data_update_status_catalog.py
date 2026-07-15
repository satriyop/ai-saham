"""Table catalog for fetch-market data update status read model.

Layer: Infrastructure
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DataUpdateTableSpec:
    table: str
    source: str
    contains: str
    date_column: str | None
    source_column: str | None = None
    source_value: str | None = None
    freshness: str = "range"
    applicable: bool = True
    skipped_reason: str | None = None


def build_data_update_table_specs(
    *,
    candles_provider: str,
    broker_provider_name: str,
    no_meta: bool,
    candles_only: bool,
    broker_only: bool,
    enrichment_available: bool,
) -> list[DataUpdateTableSpec]:
    broker_source_value = broker_provider_name

    return [
        DataUpdateTableSpec(
            "candles",
            candles_provider,
            "Daily OHLCV price history",
            "date",
            applicable=not broker_only,
            skipped_reason="--broker-only",
        ),
        DataUpdateTableSpec(
            "broker_summaries",
            "idx",
            "IDX foreign buy/sell totals + top named brokers",
            "date",
            source_column="source",
            source_value="idx",
            applicable=not candles_only,
            skipped_reason="--candles-only",
        ),
        DataUpdateTableSpec(
            "foreign_flow_points",
            broker_provider_name,
            "Net foreign flow time series",
            "date",
            source_column="source",
            source_value=broker_source_value,
            applicable=not candles_only,
            skipped_reason="--candles-only",
        ),
        DataUpdateTableSpec(
            "broker_daily_flow",
            broker_provider_name,
            "Per-broker named buy/sell flow",
            "date",
            source_column="source",
            source_value=broker_source_value,
            applicable=not candles_only and broker_provider_name == "stockbit",
            skipped_reason="provider has no per-broker daily flow",
        ),
        DataUpdateTableSpec(
            "stock_meta",
            "yahoo",
            "Sector/industry classification",
            "fetched_at",
            freshness="ttl30",
            applicable=not no_meta,
            skipped_reason="--no-meta",
        ),
        DataUpdateTableSpec(
            "analyst_cache",
            "stockbit",
            "Analyst consensus",
            "fetched_date",
            freshness="today",
            applicable=enrichment_available,
            skipped_reason="no Stockbit enrichment",
        ),
        DataUpdateTableSpec(
            "insider_cache",
            "stockbit",
            "Insider transaction cache",
            "fetched_date",
            freshness="today",
            applicable=enrichment_available,
            skipped_reason="no Stockbit enrichment",
        ),
        DataUpdateTableSpec(
            "seasonality_cache",
            "stockbit",
            "Monthly seasonality cache",
            "fetched_month",
            freshness="month",
            applicable=enrichment_available,
            skipped_reason="no Stockbit enrichment",
        ),
        DataUpdateTableSpec(
            "corp_action_cache",
            "stockbit",
            "Corporate action cache",
            "fetched_date",
            freshness="today",
            applicable=enrichment_available,
            skipped_reason="no Stockbit enrichment",
        ),
        DataUpdateTableSpec(
            "shareholding_composition",
            "stockbit",
            "Shareholding composition",
            "fetched_date",
            freshness="ttl7",
            applicable=enrichment_available,
            skipped_reason="no Stockbit enrichment",
        ),
        DataUpdateTableSpec(
            "bandar_detector",
            "stockbit",
            "Bandar detector snapshot",
            "session_date",
            freshness="today",
            applicable=enrichment_available,
            skipped_reason="no Stockbit enrichment",
        ),
        DataUpdateTableSpec(
            "company_fundamentals",
            "stockbit",
            "Company fundamental ratios",
            "fetched_date",
            freshness="ttl7",
            applicable=enrichment_available,
            skipped_reason="no Stockbit enrichment",
        ),
    ]
