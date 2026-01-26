"""
CSV format detection based on column headers.

Layer: Infrastructure
"""

import csv
from pathlib import Path

from src.domain.ports.csv_broker_parser import (
    CsvFormat,
    CsvFormatDetectionError,
)


class FormatDetector:
    """
    Detects CSV format based on column headers.

    Supports:
    - Simple format: Aggregate foreign flow (date, ticker, foreign_buy_value, etc.)
    - Detailed format: Individual broker transactions (broker_code, broker_type, etc.)
    """

    # Required columns for simple format (aggregate foreign flow)
    SIMPLE_REQUIRED = {
        "date",
        "ticker",
        "foreign_buy_value",
        "foreign_sell_value",
    }

    SIMPLE_OPTIONAL = {
        "foreign_buy_lot",
        "foreign_sell_lot",
        "total_value",
        "total_lot",
    }

    # Required columns for detailed format (broker transactions)
    DETAILED_REQUIRED = {
        "date",
        "ticker",
        "broker_code",
        "broker_type",
        "buy_value",
        "sell_value",
    }

    DETAILED_OPTIONAL = {
        "broker_name",
        "buy_lot",
        "sell_lot",
    }

    def detect(self, file_path: Path) -> CsvFormat:
        """
        Detect CSV format from column headers.

        Args:
            file_path: Path to the CSV file

        Returns:
            Detected CsvFormat

        Raises:
            CsvFormatDetectionError: If file cannot be read or format unknown
        """
        headers = self._read_headers(file_path)
        normalized = self._normalize_headers(headers)

        # Check detailed format first (more specific)
        if self._is_detailed_format(normalized):
            return CsvFormat.DETAILED

        # Check simple format
        if self._is_simple_format(normalized):
            return CsvFormat.SIMPLE

        # Could not detect
        raise CsvFormatDetectionError(
            f"Could not detect CSV format. Headers found: {headers}. "
            f"Expected simple format columns: {self.SIMPLE_REQUIRED} "
            f"or detailed format columns: {self.DETAILED_REQUIRED}"
        )

    def _read_headers(self, file_path: Path) -> list[str]:
        """Read column headers from CSV file."""
        if not file_path.exists():
            raise CsvFormatDetectionError(f"File not found: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                headers = next(reader, None)
                if headers is None:
                    raise CsvFormatDetectionError("CSV file is empty")
                return headers
        except csv.Error as e:
            raise CsvFormatDetectionError(f"Invalid CSV file: {e}")
        except UnicodeDecodeError:
            # Try with different encoding
            try:
                with open(file_path, "r", encoding="latin-1") as f:
                    reader = csv.reader(f)
                    return next(reader, [])
            except Exception as e:
                raise CsvFormatDetectionError(f"Could not read file: {e}")

    def _normalize_headers(self, headers: list[str]) -> set[str]:
        """
        Normalize column headers for comparison.

        - Lowercase
        - Strip whitespace
        - Replace spaces with underscores
        """
        normalized = set()
        for h in headers:
            norm = h.strip().lower().replace(" ", "_").replace("-", "_")
            normalized.add(norm)
        return normalized

    def _is_simple_format(self, headers: set[str]) -> bool:
        """Check if headers match simple format."""
        return self.SIMPLE_REQUIRED.issubset(headers)

    def _is_detailed_format(self, headers: set[str]) -> bool:
        """Check if headers match detailed format."""
        return self.DETAILED_REQUIRED.issubset(headers)

    def get_missing_columns(
        self,
        file_path: Path,
        target_format: CsvFormat,
    ) -> set[str]:
        """
        Get missing required columns for a target format.

        Useful for error messages.
        """
        headers = self._read_headers(file_path)
        normalized = self._normalize_headers(headers)

        if target_format == CsvFormat.SIMPLE:
            return self.SIMPLE_REQUIRED - normalized
        elif target_format == CsvFormat.DETAILED:
            return self.DETAILED_REQUIRED - normalized
        else:
            return set()
