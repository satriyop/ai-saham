"""
Simple (aggregate) format CSV parser for broker data.

Parses CSV files with pre-aggregated foreign flow data per ticker per day.
Handles UTF-8 encoding with latin-1 fallback on decode error.

Layer: Infrastructure
Dependencies: Domain ports, entities, shared field parsers
"""

import csv
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path

from src.domain.entities.broker_flow import BrokerSummary
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
    parse_csv_date,
    parse_csv_decimal,
    parse_csv_int,
)


def _parse_simple_row(
    row: Mapping[str, str],
    row_num: int,
    header_map: dict[str, str],
    transforms: Mapping[str, Transform],
) -> BrokerSummary:
    """Parse a single row of simple format into BrokerSummary."""

    def get_value(field: str) -> str:
        csv_col = header_map.get(field)
        if csv_col and csv_col in row:
            return row[csv_col].strip()
        return ""

    # Parse date with optional transform
    date_str = get_value("date")
    if not date_str:
        raise ValueError(f"Missing date in row {row_num}")

    row_date = parse_csv_date(date_str, transforms.get("date"))

    # Parse ticker (uppercase)
    ticker = get_value("ticker").upper()
    if not ticker:
        raise ValueError(f"Missing ticker in row {row_num}")

    # Parse values with optional multiplier transforms
    foreign_buy_value = parse_csv_decimal(
        get_value("foreign_buy_value"),
        transforms.get("foreign_buy_value"),
        default=Decimal("0"),
    )
    foreign_sell_value = parse_csv_decimal(
        get_value("foreign_sell_value"),
        transforms.get("foreign_sell_value"),
        default=Decimal("0"),
    )
    foreign_buy_lot = parse_csv_int(get_value("foreign_buy_lot"), default=0)
    foreign_sell_lot = parse_csv_int(get_value("foreign_sell_lot"), default=0)
    total_value = parse_csv_decimal(
        get_value("total_value"),
        transforms.get("total_value"),
        default=Decimal("0"),
    )
    total_lot = parse_csv_int(get_value("total_lot"), default=0)

    return BrokerSummary(
        ticker=ticker,
        date=row_date,
        top_buyers=(),  # Not available in simple format
        top_sellers=(),  # Not available in simple format
        foreign_buy_value=foreign_buy_value,
        foreign_sell_value=foreign_sell_value,
        foreign_buy_lot=foreign_buy_lot,
        foreign_sell_lot=foreign_sell_lot,
        total_value=total_value,
        total_lot=total_lot,
        source="csv-idx",
    )


def _parse_with_encoding(
    file_path: Path,
    mapping: CsvMappingConfig,
    error_strategy: ErrorStrategy,
    encoding: str,
    max_rows: int | None,
) -> ParseResult:
    """Parse CSV with specific encoding (used for latin-1 fallback)."""
    summaries = []
    errors = []
    total_rows = 0
    skipped_rows = 0

    with open(file_path, "r", encoding=encoding) as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise CsvBrokerParserError("CSV file has no headers")

        header_map = build_header_map(reader.fieldnames, mapping.columns)

        for row_num, row in enumerate(reader, start=2):  # Start at 2 (1=header)
            total_rows += 1

            if max_rows and len(summaries) >= max_rows:
                break

            try:
                summary = _parse_simple_row(row, row_num, header_map, mapping.transforms)
                summaries.append(summary)
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

    return ParseResult(
        summaries=summaries,
        errors=errors,
        total_rows=total_rows,
        skipped_rows=skipped_rows,
        format_detected=mapping.format,
    )


def parse_simple_broker_csv(
    file_path: Path,
    mapping: CsvMappingConfig,
    error_strategy: ErrorStrategy,
    max_rows: int | None = None,
) -> ParseResult:
    """
    Parse simple (aggregate) format broker CSV.

    Attempts UTF-8 first, falls back to latin-1 on UnicodeDecodeError.

    Args:
        file_path: Path to CSV file
        mapping: Column mapping configuration
        error_strategy: How to handle parse errors
        max_rows: Optional limit for preview mode

    Returns:
        ParseResult with summaries and any errors

    Raises:
        CsvBrokerParserError: If file not found, no headers, or FAIL strategy triggered
    """
    summaries = []
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

                if max_rows and len(summaries) >= max_rows:
                    break

                try:
                    summary = _parse_simple_row(row, row_num, header_map, mapping.transforms)
                    summaries.append(summary)
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
        # Retry with latin-1 encoding
        return _parse_with_encoding(file_path, mapping, error_strategy, "latin-1", max_rows)

    return ParseResult(
        summaries=summaries,
        errors=errors,
        total_rows=total_rows,
        skipped_rows=skipped_rows,
        format_detected=mapping.format,
    )
