"""
CsvBrokerParser port - interface for parsing broker data from CSV files.

This is a domain port (interface). Concrete implementations
live in infrastructure/csv/.

Layer: Domain
Dependencies: None (only domain entities)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path

from src.domain.entities.broker_flow import BrokerSummary


class CsvFormat(Enum):
    """Supported CSV format types."""

    SIMPLE = "SIMPLE"  # Aggregate foreign flow only
    DETAILED = "DETAILED"  # With broker transactions
    CUSTOM = "CUSTOM"  # User-defined mapping

    @classmethod
    def parse(cls, value: str) -> "CsvFormat":
        """Parse canonical uppercase and legacy lowercase CSV format values."""
        normalized = value.strip().upper().replace("-", "_")
        for csv_format in cls:
            if normalized in {csv_format.name, csv_format.value}:
                return csv_format
        valid = [csv_format.value for csv_format in cls]
        raise ValueError(f"Invalid CSV format '{value}'. Must be one of: {valid}")


class ErrorStrategy(Enum):
    """How to handle parsing errors."""

    SKIP = "SKIP"  # Skip invalid rows, continue processing
    FAIL = "FAIL"  # Stop on first error
    REPORT = "REPORT"  # Collect all errors, report at end

    @classmethod
    def parse(cls, value: str) -> "ErrorStrategy":
        """Parse canonical uppercase and legacy lowercase error strategy values."""
        normalized = value.strip().upper().replace("-", "_")
        for strategy in cls:
            if normalized in {strategy.name, strategy.value}:
                return strategy
        valid = [strategy.value for strategy in cls]
        raise ValueError(f"Invalid error strategy '{value}'. Must be one of: {valid}")


@dataclass(frozen=True)
class ParseError:
    """Represents a parsing error for a specific row."""

    row_number: int
    field: str
    value: str
    message: str

    def __str__(self) -> str:
        return f"Row {self.row_number}, field '{self.field}': {self.message} (value: '{self.value}')"


@dataclass(frozen=True)
class ParseResult:
    """Result of parsing a CSV file."""

    summaries: list[BrokerSummary]
    errors: list[ParseError]
    total_rows: int
    skipped_rows: int
    format_detected: CsvFormat

    @property
    def success_count(self) -> int:
        """Number of successfully parsed rows."""
        return len(self.summaries)

    @property
    def has_errors(self) -> bool:
        """True if there were parsing errors."""
        return len(self.errors) > 0


@dataclass(frozen=True)
class ColumnMapping:
    """Maps CSV column names to expected fields."""

    date: str = "date"
    ticker: str = "ticker"
    foreign_buy_value: str = "foreign_buy_value"
    foreign_sell_value: str = "foreign_sell_value"
    foreign_buy_lot: str = "foreign_buy_lot"
    foreign_sell_lot: str = "foreign_sell_lot"
    total_value: str = "total_value"
    total_lot: str = "total_lot"
    # Detailed format additional columns
    broker_code: str = "broker_code"
    broker_name: str = "broker_name"
    broker_type: str = "broker_type"
    buy_lot: str = "buy_lot"
    sell_lot: str = "sell_lot"
    buy_value: str = "buy_value"
    sell_value: str = "sell_value"


@dataclass(frozen=True)
class Transform:
    """Transformation rules for a column."""

    date_format: str | None = None  # e.g., "%d/%m/%Y"
    multiplier: Decimal | None = None  # e.g., 1000000 for values in millions


@dataclass(frozen=True)
class CsvMappingConfig:
    """Configuration for custom CSV mapping."""

    name: str
    format: CsvFormat
    columns: ColumnMapping
    transforms: dict[str, Transform]  # field -> transform

    @classmethod
    def default(cls) -> "CsvMappingConfig":
        """Default mapping for standard format."""
        return cls(
            name="default",
            format=CsvFormat.SIMPLE,
            columns=ColumnMapping(),
            transforms={},
        )


class CsvBrokerParser(ABC):
    """
    Abstract interface for parsing broker data from CSV files.

    Implementations may include:
    - BrokerCsvAdapter (standard CSV parsing)
    - Custom format adapters

    The domain layer depends on this interface, never on concrete implementations.
    """

    @abstractmethod
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
        pass

    @abstractmethod
    def detect_format(self, file_path: Path) -> CsvFormat:
        """
        Auto-detect the CSV format based on column headers.

        Args:
            file_path: Path to the CSV file

        Returns:
            Detected CsvFormat

        Raises:
            CsvBrokerParserError: If format cannot be detected
        """
        pass

    @abstractmethod
    def preview(
        self,
        file_path: Path,
        max_rows: int = 5,
        mapping: CsvMappingConfig | None = None,
    ) -> ParseResult:
        """
        Preview parsing without saving - useful for validation.

        Args:
            file_path: Path to the CSV file
            max_rows: Maximum rows to preview
            mapping: Optional custom column mapping

        Returns:
            ParseResult with preview of parsed data
        """
        pass


class CsvBrokerParserError(Exception):
    """Raised when CSV parsing encounters an error."""

    pass


class CsvFormatDetectionError(CsvBrokerParserError):
    """Raised when CSV format cannot be detected."""

    pass
