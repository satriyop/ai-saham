"""
CSV Broker Data Adapter - parses broker data from CSV files.

Implements the CsvBrokerParser port for importing broker flow data
from various CSV formats (RTI exports, Stockbit exports, custom spreadsheets).

Layer: Infrastructure
Dependencies: Domain ports, format detector, and internal parser modules
"""

from pathlib import Path

from src.domain.ports.csv_broker_parser import (
    ColumnMapping,
    CsvBrokerParser,
    CsvBrokerParserError,
    CsvFormat,
    CsvMappingConfig,
    ErrorStrategy,
    ParseResult,
)
from src.infrastructure.csv.detailed_broker_csv_parser import parse_detailed_broker_csv
from src.infrastructure.csv.format_detector import FormatDetector
from src.infrastructure.csv.simple_broker_csv_parser import parse_simple_broker_csv


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

        Raises:
            CsvBrokerParserError: If file cannot be read or is invalid
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
            return parse_simple_broker_csv(file_path, mapping, error_strategy)
        elif mapping.format == CsvFormat.DETAILED:
            return parse_detailed_broker_csv(file_path, mapping, error_strategy)
        else:
            # Custom format - treat as simple with custom column mapping
            return parse_simple_broker_csv(file_path, mapping, error_strategy)

    def preview(
        self,
        file_path: Path,
        max_rows: int = 5,
        mapping: CsvMappingConfig | None = None,
    ) -> ParseResult:
        """
        Preview parsing without saving - useful for validation.

        Returns first max_rows successfully parsed rows.

        Args:
            file_path: Path to the CSV file
            max_rows: Maximum rows to preview
            mapping: Optional custom column mapping

        Returns:
            ParseResult with preview of parsed data
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

        # Parse with row limit and REPORT strategy
        if mapping.format == CsvFormat.SIMPLE:
            return parse_simple_broker_csv(
                file_path, mapping, ErrorStrategy.REPORT, max_rows=max_rows
            )
        elif mapping.format == CsvFormat.DETAILED:
            return parse_detailed_broker_csv(
                file_path, mapping, ErrorStrategy.REPORT, max_rows=max_rows
            )
        else:
            return parse_simple_broker_csv(
                file_path, mapping, ErrorStrategy.REPORT, max_rows=max_rows
            )
