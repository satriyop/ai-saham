"""
Detailed (transaction) format CSV parser for broker data.

Parses CSV files with individual broker transactions.
Aggregates transactions by (ticker, date) into BrokerSummary objects.
Does NOT fall back to latin-1 encoding - raises on Unicode decode error.

Layer: Infrastructure
Dependencies: Domain ports, entities, shared field parsers, transaction aggregator
"""

import csv
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

from src.domain.entities.broker_flow import BrokerTransaction
from src.domain.ports.csv_broker_parser import (
    CsvBrokerParserError,
    CsvMappingConfig,
    ErrorStrategy,
    ParseError,
    ParseResult,
    Transform,
)
from src.infrastructure.csv.broker_csv_fields import (
    build_header_map,
    parse_broker_type,
    parse_csv_date,
    parse_csv_decimal,
    parse_csv_int,
)
from src.infrastructure.csv.broker_transaction_aggregator import (
    aggregate_broker_transactions,
)


def _parse_detailed_row(
    row: dict[str, str],
    row_num: int,
    header_map: dict[str, str],
    transforms: dict[str, Transform],
) -> tuple[str, date, BrokerTransaction]:
    """Parse a single row of detailed format into BrokerTransaction."""

    def get_value(field: str) -> str:
        csv_col = header_map.get(field)
        if csv_col and csv_col in row:
            return row[csv_col].strip()
        return ""

    # Parse date
    date_str = get_value("date")
    if not date_str:
        raise ValueError(f"Missing date in row {row_num}")
    row_date = parse_csv_date(date_str, transforms.get("date"))

    # Parse ticker
    ticker = get_value("ticker").upper()
    if not ticker:
        raise ValueError(f"Missing ticker in row {row_num}")

    # Parse broker info
    broker_code = get_value("broker_code").upper()
    if not broker_code:
        raise ValueError(f"Missing broker_code in row {row_num}")

    broker_name = get_value("broker_name") or broker_code
    broker_type_str = get_value("broker_type").upper()
    broker_type = parse_broker_type(broker_type_str)

    # Parse transaction values
    buy_lot = parse_csv_int(get_value("buy_lot"), default=0)
    sell_lot = parse_csv_int(get_value("sell_lot"), default=0)
    buy_value = parse_csv_decimal(
        get_value("buy_value"),
        transforms.get("buy_value"),
        default=Decimal("0"),
    )
    sell_value = parse_csv_decimal(
        get_value("sell_value"),
        transforms.get("sell_value"),
        default=Decimal("0"),
    )

    # Calculate average prices (if lots > 0)
    avg_buy_price = (
        buy_value / (buy_lot * 100) if buy_lot > 0 else Decimal("0")
    )  # 100 shares per lot
    avg_sell_price = sell_value / (sell_lot * 100) if sell_lot > 0 else Decimal("0")

    transaction = BrokerTransaction(
        broker_code=broker_code,
        broker_name=broker_name,
        broker_type=broker_type,
        buy_lot=buy_lot,
        sell_lot=sell_lot,
        buy_value=buy_value,
        sell_value=sell_value,
        avg_buy_price=avg_buy_price,
        avg_sell_price=avg_sell_price,
    )

    return ticker, row_date, transaction


def parse_detailed_broker_csv(
    file_path: Path,
    mapping: CsvMappingConfig,
    error_strategy: ErrorStrategy,
    max_rows: int | None = None,
) -> ParseResult:
    """
    Parse detailed (transaction) format broker CSV.

    Groups transactions by (ticker, date) and aggregates into BrokerSummary.
    Does NOT fall back to latin-1 - raises CsvBrokerParserError on decode error.

    Args:
        file_path: Path to CSV file
        mapping: Column mapping configuration
        error_strategy: How to handle parse errors
        max_rows: Optional limit for preview (applied after aggregation)

    Returns:
        ParseResult with aggregated summaries and any errors

    Raises:
        CsvBrokerParserError: If file not found, no headers, decode
            error, or FAIL strategy triggered
    """
    # Group transactions by (ticker, date)
    transactions_by_key: dict[tuple[str, date], list[BrokerTransaction]] = defaultdict(list)
    errors = []
    total_rows = 0
    skipped_rows = 0

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                raise CsvBrokerParserError("CSV file has no headers")

            header_map = build_header_map(reader.fieldnames, mapping.columns)

            for row_num, row in enumerate(reader, start=2):
                total_rows += 1

                try:
                    ticker, row_date, transaction = _parse_detailed_row(
                        row, row_num, header_map, mapping.transforms
                    )
                    key = (ticker, row_date)
                    transactions_by_key[key].append(transaction)
                except ValueError as e:
                    error = ParseError(
                        row_number=row_num,
                        field="row",
                        value=str(row),
                        message=str(e),
                    )
                    errors.append(error)
                    skipped_rows += 1

                    if error_strategy == ErrorStrategy.FAIL:
                        raise CsvBrokerParserError(f"Parse error: {error}")

    except UnicodeDecodeError:
        raise CsvBrokerParserError("Could not decode file. Please ensure UTF-8 encoding.")

    # Aggregate transactions into summaries
    summaries = []
    for (ticker, row_date), transactions in sorted(transactions_by_key.items()):
        if max_rows and len(summaries) >= max_rows:
            break

        summary = aggregate_broker_transactions(ticker, row_date, transactions)
        summaries.append(summary)

    return ParseResult(
        summaries=summaries,
        errors=errors,
        total_rows=total_rows,
        skipped_rows=skipped_rows,
        format_detected=mapping.format,
    )
