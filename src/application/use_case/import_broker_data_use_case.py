"""
Import Broker Data Use Case.

Orchestrates importing broker flow data from CSV files
into the local repository.

Layer: Application
"""

from dataclasses import dataclass
from pathlib import Path

from src.domain.entities.broker_flow import BrokerSummary
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.csv_broker_parser import (
    CsvBrokerParser,
    CsvBrokerParserError,
    CsvFormat,
    CsvMappingConfig,
    ErrorStrategy,
    ParseError,
)


@dataclass(frozen=True)
class ImportBrokerDataRequest:
    """Request to import broker data from CSV."""

    file_path: Path
    preview_only: bool = False
    error_strategy: ErrorStrategy = ErrorStrategy.SKIP
    mapping: CsvMappingConfig | None = None
    max_preview_rows: int = 5


@dataclass(frozen=True)
class ImportBrokerDataResponse:
    """Response from importing broker data."""

    success: bool
    imported_count: int
    skipped_count: int
    total_rows: int
    errors: list[ParseError]
    format_detected: CsvFormat
    summaries: list[BrokerSummary]  # For preview mode
    message: str

    @property
    def has_errors(self) -> bool:
        """True if there were parsing errors."""
        return len(self.errors) > 0


class ImportBrokerDataUseCase:
    """
    Use case for importing broker data from CSV files.

    Flow:
    1. Parse CSV file using the parser
    2. Validate parsed data
    3. If preview mode, return without saving
    4. Save summaries to repository (upsert semantics)
    5. Return import result

    Supports two modes:
    - Import mode: Parse and save to repository
    - Preview mode: Parse without saving (--preview flag)
    """

    def __init__(
        self,
        parser: CsvBrokerParser,
        repository: BrokerDataRepository,
    ) -> None:
        """
        Initialize use case.

        Args:
            parser: CSV parser implementation
            repository: Local repository for broker data
        """
        self._parser = parser
        self._repository = repository

    def execute(self, request: ImportBrokerDataRequest) -> ImportBrokerDataResponse:
        """
        Execute the import broker data use case.

        Args:
            request: ImportBrokerDataRequest with file path and options

        Returns:
            ImportBrokerDataResponse with import results

        Raises:
            CsvBrokerParserError: If parsing fails critically
        """
        # Validate file exists
        if not request.file_path.exists():
            raise CsvBrokerParserError(f"File not found: {request.file_path}")

        # Preview mode - parse limited rows without saving
        if request.preview_only:
            return self._execute_preview(request)

        # Full import mode
        return self._execute_import(request)

    def _execute_preview(
        self,
        request: ImportBrokerDataRequest,
    ) -> ImportBrokerDataResponse:
        """Execute preview mode - parse without saving."""
        parse_result = self._parser.preview(
            file_path=request.file_path,
            max_rows=request.max_preview_rows,
            mapping=request.mapping,
        )

        return ImportBrokerDataResponse(
            success=True,
            imported_count=0,  # Nothing imported in preview
            skipped_count=parse_result.skipped_rows,
            total_rows=parse_result.total_rows,
            errors=parse_result.errors,
            format_detected=parse_result.format_detected,
            summaries=parse_result.summaries,
            message=self._build_preview_message(parse_result),
        )

    def _execute_import(
        self,
        request: ImportBrokerDataRequest,
    ) -> ImportBrokerDataResponse:
        """Execute full import - parse and save."""
        # Parse the CSV file
        parse_result = self._parser.parse(
            file_path=request.file_path,
            error_strategy=request.error_strategy,
            mapping=request.mapping,
        )

        if not parse_result.summaries:
            return ImportBrokerDataResponse(
                success=False,
                imported_count=0,
                skipped_count=parse_result.skipped_rows,
                total_rows=parse_result.total_rows,
                errors=parse_result.errors,
                format_detected=parse_result.format_detected,
                summaries=[],
                message="No valid data to import. Check errors for details.",
            )

        # Save to repository (upsert semantics)
        self._repository.save_broker_summaries(parse_result.summaries)

        return ImportBrokerDataResponse(
            success=True,
            imported_count=len(parse_result.summaries),
            skipped_count=parse_result.skipped_rows,
            total_rows=parse_result.total_rows,
            errors=parse_result.errors,
            format_detected=parse_result.format_detected,
            summaries=parse_result.summaries,
            message=self._build_import_message(parse_result),
        )

    def _build_preview_message(self, result) -> str:
        """Build preview message."""
        lines = [
            f"Preview: {result.success_count} rows parsed successfully",
            f"Format detected: {result.format_detected.value}",
        ]

        if result.skipped_rows > 0:
            lines.append(f"Rows with errors: {result.skipped_rows}")

        return " | ".join(lines)

    def _build_import_message(self, result) -> str:
        """Build import success message."""
        lines = [
            f"Imported {result.success_count} broker summaries",
        ]

        if result.skipped_rows > 0:
            lines.append(f"Skipped {result.skipped_rows} invalid rows")

        # Count unique tickers and date range
        if result.summaries:
            tickers = set(s.ticker for s in result.summaries)
            dates = sorted(s.date for s in result.summaries)
            lines.append(f"Tickers: {', '.join(sorted(tickers))}")
            if len(dates) > 1:
                lines.append(f"Date range: {dates[0]} to {dates[-1]}")
            else:
                lines.append(f"Date: {dates[0]}")

        return " | ".join(lines)


class DetectCsvFormatUseCase:
    """
    Use case for detecting CSV format without full parsing.

    Useful for CLI to display format info before import.
    """

    def __init__(self, parser: CsvBrokerParser) -> None:
        """Initialize with parser."""
        self._parser = parser

    def execute(self, file_path: Path) -> CsvFormat:
        """
        Detect CSV format from file headers.

        Args:
            file_path: Path to the CSV file

        Returns:
            Detected CsvFormat

        Raises:
            CsvBrokerParserError: If format cannot be detected
        """
        return self._parser.detect_format(file_path)
