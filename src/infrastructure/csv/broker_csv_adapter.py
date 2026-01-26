"""
CSV Broker Data Adapter - parses broker data from CSV files.

Implements the CsvBrokerParser port for importing broker flow data
from various CSV formats (RTI exports, Stockbit exports, custom spreadsheets).

Layer: Infrastructure
"""

import csv
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from src.domain.entities.broker_flow import (
    BrokerSummary,
    BrokerTransaction,
    BrokerType,
)
from src.domain.ports.csv_broker_parser import (
    ColumnMapping,
    CsvBrokerParser,
    CsvBrokerParserError,
    CsvFormat,
    CsvMappingConfig,
    ErrorStrategy,
    ParseError,
    ParseResult,
    Transform,
)
from src.infrastructure.csv.format_detector import FormatDetector


class BrokerCsvAdapter(CsvBrokerParser):
    """
    CSV adapter for parsing broker data.

    Supports two main formats:
    1. Simple (aggregate): Foreign flow totals per ticker per day
    2. Detailed (transactions): Individual broker transactions

    For detailed format, transactions are aggregated into BrokerSummary objects.
    """

    def __init__(self) -> None:
        """Initialize adapter with format detector."""
        self._detector = FormatDetector()

    def detect_format(self, file_path: Path) -> CsvFormat:
        """Auto-detect the CSV format based on column headers."""
        return self._detector.detect(file_path)

    def parse(
        self,
        file_path: Path,
        error_strategy: ErrorStrategy = ErrorStrategy.SKIP,
        mapping: CsvMappingConfig | None = None,
    ) -> ParseResult:
        """
        Parse a CSV file and return broker summaries.

        Args:
            file_path: Path to the CSV file
            error_strategy: How to handle parsing errors
            mapping: Optional custom column mapping

        Returns:
            ParseResult with parsed summaries and any errors
        """
        if not file_path.exists():
            raise CsvBrokerParserError(f"File not found: {file_path}")

        # Detect format if no mapping provided
        if mapping is None:
            detected_format = self.detect_format(file_path)
            mapping = CsvMappingConfig(
                name="auto-detected",
                format=detected_format,
                columns=ColumnMapping(),
                transforms={},
            )

        # Parse based on format
        if mapping.format == CsvFormat.SIMPLE:
            return self._parse_simple_format(file_path, mapping, error_strategy)
        elif mapping.format == CsvFormat.DETAILED:
            return self._parse_detailed_format(file_path, mapping, error_strategy)
        else:
            # Custom format - treat as simple with custom column mapping
            return self._parse_simple_format(file_path, mapping, error_strategy)

    def preview(
        self,
        file_path: Path,
        max_rows: int = 5,
        mapping: CsvMappingConfig | None = None,
    ) -> ParseResult:
        """
        Preview parsing without saving - useful for validation.

        Returns first max_rows successfully parsed rows.
        """
        if not file_path.exists():
            raise CsvBrokerParserError(f"File not found: {file_path}")

        # Detect format if no mapping provided
        if mapping is None:
            detected_format = self.detect_format(file_path)
            mapping = CsvMappingConfig(
                name="auto-detected",
                format=detected_format,
                columns=ColumnMapping(),
                transforms={},
            )

        # Parse with row limit
        if mapping.format == CsvFormat.SIMPLE:
            return self._parse_simple_format(
                file_path, mapping, ErrorStrategy.REPORT, max_rows=max_rows
            )
        elif mapping.format == CsvFormat.DETAILED:
            return self._parse_detailed_format(
                file_path, mapping, ErrorStrategy.REPORT, max_rows=max_rows
            )
        else:
            return self._parse_simple_format(
                file_path, mapping, ErrorStrategy.REPORT, max_rows=max_rows
            )

    def _parse_simple_format(
        self,
        file_path: Path,
        mapping: CsvMappingConfig,
        error_strategy: ErrorStrategy,
        max_rows: int | None = None,
    ) -> ParseResult:
        """
        Parse simple (aggregate) CSV format.

        Expected columns: date, ticker, foreign_buy_value, foreign_sell_value,
                         foreign_buy_lot, foreign_sell_lot, total_value, total_lot
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

                # Normalize header mapping
                header_map = self._build_header_map(reader.fieldnames, mapping.columns)

                for row_num, row in enumerate(reader, start=2):  # Start at 2 (1=header)
                    total_rows += 1

                    # Check row limit for preview
                    if max_rows and len(summaries) >= max_rows:
                        break

                    try:
                        summary = self._parse_simple_row(
                            row, row_num, header_map, mapping.transforms
                        )
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
            return self._parse_with_encoding(
                file_path, mapping, error_strategy, "latin-1", max_rows
            )

        return ParseResult(
            summaries=summaries,
            errors=errors,
            total_rows=total_rows,
            skipped_rows=skipped_rows,
            format_detected=mapping.format,
        )

    def _parse_with_encoding(
        self,
        file_path: Path,
        mapping: CsvMappingConfig,
        error_strategy: ErrorStrategy,
        encoding: str,
        max_rows: int | None = None,
    ) -> ParseResult:
        """Parse with specific encoding."""
        summaries = []
        errors = []
        total_rows = 0
        skipped_rows = 0

        with open(file_path, "r", encoding=encoding) as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                raise CsvBrokerParserError("CSV file has no headers")

            header_map = self._build_header_map(reader.fieldnames, mapping.columns)

            for row_num, row in enumerate(reader, start=2):
                total_rows += 1

                if max_rows and len(summaries) >= max_rows:
                    break

                try:
                    summary = self._parse_simple_row(
                        row, row_num, header_map, mapping.transforms
                    )
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

    def _parse_simple_row(
        self,
        row: dict[str, str],
        row_num: int,
        header_map: dict[str, str],
        transforms: dict[str, Transform],
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

        row_date = self._parse_date(date_str, transforms.get("date"))

        # Parse ticker
        ticker = get_value("ticker").upper()
        if not ticker:
            raise ValueError(f"Missing ticker in row {row_num}")

        # Parse values with optional multiplier transforms
        foreign_buy_value = self._parse_decimal(
            get_value("foreign_buy_value"),
            transforms.get("foreign_buy_value"),
            default=Decimal("0"),
        )
        foreign_sell_value = self._parse_decimal(
            get_value("foreign_sell_value"),
            transforms.get("foreign_sell_value"),
            default=Decimal("0"),
        )
        foreign_buy_lot = self._parse_int(
            get_value("foreign_buy_lot"), default=0
        )
        foreign_sell_lot = self._parse_int(
            get_value("foreign_sell_lot"), default=0
        )
        total_value = self._parse_decimal(
            get_value("total_value"),
            transforms.get("total_value"),
            default=Decimal("0"),
        )
        total_lot = self._parse_int(get_value("total_lot"), default=0)

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
        )

    def _parse_detailed_format(
        self,
        file_path: Path,
        mapping: CsvMappingConfig,
        error_strategy: ErrorStrategy,
        max_rows: int | None = None,
    ) -> ParseResult:
        """
        Parse detailed (transaction) CSV format.

        Expected columns: date, ticker, broker_code, broker_name, broker_type,
                         buy_lot, sell_lot, buy_value, sell_value

        Aggregates transactions by ticker+date into BrokerSummary objects.
        """
        # Group transactions by (ticker, date)
        transactions_by_key: dict[tuple[str, date], list[BrokerTransaction]] = (
            defaultdict(list)
        )
        errors = []
        total_rows = 0
        skipped_rows = 0

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames is None:
                    raise CsvBrokerParserError("CSV file has no headers")

                header_map = self._build_header_map(reader.fieldnames, mapping.columns)

                for row_num, row in enumerate(reader, start=2):
                    total_rows += 1

                    try:
                        ticker, row_date, transaction = self._parse_detailed_row(
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
            raise CsvBrokerParserError(
                "Could not decode file. Please ensure UTF-8 encoding."
            )

        # Aggregate transactions into summaries
        summaries = []
        for (ticker, row_date), transactions in sorted(transactions_by_key.items()):
            if max_rows and len(summaries) >= max_rows:
                break

            summary = self._aggregate_transactions(ticker, row_date, transactions)
            summaries.append(summary)

        return ParseResult(
            summaries=summaries,
            errors=errors,
            total_rows=total_rows,
            skipped_rows=skipped_rows,
            format_detected=mapping.format,
        )

    def _parse_detailed_row(
        self,
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
        row_date = self._parse_date(date_str, transforms.get("date"))

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
        broker_type = self._parse_broker_type(broker_type_str)

        # Parse transaction values
        buy_lot = self._parse_int(get_value("buy_lot"), default=0)
        sell_lot = self._parse_int(get_value("sell_lot"), default=0)
        buy_value = self._parse_decimal(
            get_value("buy_value"),
            transforms.get("buy_value"),
            default=Decimal("0"),
        )
        sell_value = self._parse_decimal(
            get_value("sell_value"),
            transforms.get("sell_value"),
            default=Decimal("0"),
        )

        # Calculate average prices (if lots > 0)
        avg_buy_price = (
            buy_value / (buy_lot * 100) if buy_lot > 0 else Decimal("0")
        )  # 100 shares per lot
        avg_sell_price = (
            sell_value / (sell_lot * 100) if sell_lot > 0 else Decimal("0")
        )

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

    def _aggregate_transactions(
        self,
        ticker: str,
        row_date: date,
        transactions: list[BrokerTransaction],
    ) -> BrokerSummary:
        """Aggregate broker transactions into a BrokerSummary."""
        # Calculate foreign flow totals
        foreign_buy_value = Decimal("0")
        foreign_sell_value = Decimal("0")
        foreign_buy_lot = 0
        foreign_sell_lot = 0
        total_value = Decimal("0")
        total_lot = 0

        for t in transactions:
            total_value += t.buy_value + t.sell_value
            total_lot += t.buy_lot + t.sell_lot

            if t.is_foreign:
                foreign_buy_value += t.buy_value
                foreign_sell_value += t.sell_value
                foreign_buy_lot += t.buy_lot
                foreign_sell_lot += t.sell_lot

        # Sort by net value for top buyers/sellers
        sorted_by_net = sorted(transactions, key=lambda t: t.net_value, reverse=True)

        # Top 10 buyers (positive net value)
        top_buyers = tuple(t for t in sorted_by_net[:10] if t.net_value > 0)

        # Top 10 sellers (most negative net value)
        top_sellers = tuple(
            t for t in reversed(sorted_by_net[-10:]) if t.net_value < 0
        )

        return BrokerSummary(
            ticker=ticker,
            date=row_date,
            top_buyers=top_buyers,
            top_sellers=top_sellers,
            foreign_buy_value=foreign_buy_value,
            foreign_sell_value=foreign_sell_value,
            foreign_buy_lot=foreign_buy_lot,
            foreign_sell_lot=foreign_sell_lot,
            total_value=total_value,
            total_lot=total_lot,
        )

    def _build_header_map(
        self,
        csv_headers: list[str],
        mapping: ColumnMapping,
    ) -> dict[str, str]:
        """
        Build mapping from field names to actual CSV column names.

        Handles case-insensitive matching and common variations.
        """
        header_map = {}

        # Normalize CSV headers for matching
        normalized_csv = {}
        for h in csv_headers:
            norm = h.strip().lower().replace(" ", "_").replace("-", "_")
            normalized_csv[norm] = h

        # Map each field to its CSV column
        field_mappings = {
            "date": mapping.date,
            "ticker": mapping.ticker,
            "foreign_buy_value": mapping.foreign_buy_value,
            "foreign_sell_value": mapping.foreign_sell_value,
            "foreign_buy_lot": mapping.foreign_buy_lot,
            "foreign_sell_lot": mapping.foreign_sell_lot,
            "total_value": mapping.total_value,
            "total_lot": mapping.total_lot,
            "broker_code": mapping.broker_code,
            "broker_name": mapping.broker_name,
            "broker_type": mapping.broker_type,
            "buy_lot": mapping.buy_lot,
            "sell_lot": mapping.sell_lot,
            "buy_value": mapping.buy_value,
            "sell_value": mapping.sell_value,
        }

        for field, column_name in field_mappings.items():
            norm_col = column_name.lower().replace(" ", "_").replace("-", "_")
            if norm_col in normalized_csv:
                header_map[field] = normalized_csv[norm_col]
            elif column_name in csv_headers:
                # Exact match
                header_map[field] = column_name

        return header_map

    def _parse_date(
        self,
        value: str,
        transform: Transform | None,
    ) -> date:
        """Parse date string with optional format transform."""
        if not value:
            raise ValueError("Empty date value")

        date_format = transform.date_format if transform else None

        if date_format:
            try:
                return datetime.strptime(value, date_format).date()
            except ValueError:
                raise ValueError(f"Invalid date '{value}' for format '{date_format}'")

        # Try common formats
        formats = [
            "%Y-%m-%d",  # ISO format
            "%d/%m/%Y",  # DD/MM/YYYY
            "%m/%d/%Y",  # MM/DD/YYYY
            "%d-%m-%Y",  # DD-MM-YYYY
            "%Y%m%d",  # YYYYMMDD
        ]

        for fmt in formats:
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue

        raise ValueError(
            f"Could not parse date '{value}'. "
            f"Supported formats: YYYY-MM-DD, DD/MM/YYYY, MM/DD/YYYY"
        )

    def _parse_decimal(
        self,
        value: str,
        transform: Transform | None,
        default: Decimal = Decimal("0"),
    ) -> Decimal:
        """Parse decimal value with optional multiplier transform."""
        if not value:
            return default

        # Clean value: remove commas, spaces, currency symbols
        cleaned = value.replace(",", "").replace(" ", "").replace("Rp", "").strip()

        try:
            result = Decimal(cleaned)
        except InvalidOperation:
            return default

        # Apply multiplier if specified
        if transform and transform.multiplier:
            result *= transform.multiplier

        return result

    def _parse_int(self, value: str, default: int = 0) -> int:
        """Parse integer value."""
        if not value:
            return default

        cleaned = value.replace(",", "").replace(" ", "").strip()

        try:
            return int(float(cleaned))  # Handle "1000.0" format
        except ValueError:
            return default

    def _parse_broker_type(self, value: str) -> BrokerType:
        """Parse broker type from string."""
        value_upper = value.upper()

        if value_upper in ("FOREIGN", "ASING", "F", "A"):
            return BrokerType.FOREIGN
        elif value_upper in ("LOCAL", "LOKAL", "L", "D", "DOMESTIC"):
            return BrokerType.LOCAL
        else:
            return BrokerType.UNKNOWN
