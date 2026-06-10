"""
YAML mapping configuration loader.

Loads custom column mappings from YAML files for non-standard CSV formats.

Layer: Infrastructure
"""

from decimal import Decimal
from pathlib import Path

import yaml

from src.domain.ports.csv_broker_parser import (
    ColumnMapping,
    CsvBrokerParserError,
    CsvFormat,
    CsvMappingConfig,
    Transform,
)


class MappingLoader:
    """
    Loads custom CSV mapping configurations from YAML files.

    Mapping files allow users to import CSV exports from any source
    (RTI, Stockbit manual export, custom spreadsheets) by defining
    how their columns map to the expected fields.
    """

    # Default search paths for mapping files
    DEFAULT_SEARCH_PATHS = [
        Path("config/csv_mappings"),
    ]

    def __init__(self, search_paths: list[Path] | None = None) -> None:
        """
        Initialize loader with search paths.

        Args:
            search_paths: Directories to search for mapping files
        """
        self._search_paths = search_paths or self.DEFAULT_SEARCH_PATHS

    def load(self, mapping_name: str) -> CsvMappingConfig:
        """
        Load a mapping configuration by name.

        Searches for {mapping_name}.yaml in configured search paths.

        Args:
            mapping_name: Name of the mapping (without .yaml extension)

        Returns:
            CsvMappingConfig parsed from YAML

        Raises:
            CsvBrokerParserError: If mapping file not found or invalid
        """
        if mapping_name == "default":
            return CsvMappingConfig.default()

        mapping_file = self._find_mapping_file(mapping_name)
        return self._parse_mapping_file(mapping_file)

    def load_from_file(self, file_path: Path) -> CsvMappingConfig:
        """
        Load a mapping configuration from a specific file.

        Args:
            file_path: Path to the YAML mapping file

        Returns:
            CsvMappingConfig parsed from YAML

        Raises:
            CsvBrokerParserError: If file not found or invalid
        """
        if not file_path.exists():
            raise CsvBrokerParserError(f"Mapping file not found: {file_path}")
        return self._parse_mapping_file(file_path)

    def list_available(self) -> list[str]:
        """
        List all available mapping names.

        Returns:
            List of mapping names (without .yaml extension)
        """
        mappings = ["default"]

        for search_path in self._search_paths:
            if search_path.exists():
                for f in search_path.glob("*.yaml"):
                    name = f.stem
                    if name not in mappings:
                        mappings.append(name)
                for f in search_path.glob("*.yml"):
                    name = f.stem
                    if name not in mappings:
                        mappings.append(name)

        return sorted(mappings)

    def _find_mapping_file(self, mapping_name: str) -> Path:
        """Find mapping file in search paths."""
        for search_path in self._search_paths:
            for ext in [".yaml", ".yml"]:
                candidate = search_path / f"{mapping_name}{ext}"
                if candidate.exists():
                    return candidate

        searched = [str(p) for p in self._search_paths]
        raise CsvBrokerParserError(
            f"Mapping '{mapping_name}' not found. "
            f"Searched in: {searched}. "
            f"Available mappings: {self.list_available()}"
        )

    def _parse_mapping_file(self, file_path: Path) -> CsvMappingConfig:
        """Parse YAML mapping file into CsvMappingConfig."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise CsvBrokerParserError(f"Invalid YAML in {file_path}: {e}")
        except Exception as e:
            raise CsvBrokerParserError(f"Could not read {file_path}: {e}")

        if not isinstance(data, dict):
            raise CsvBrokerParserError(
                f"Invalid mapping file: expected dictionary, got {type(data).__name__}"
            )

        return self._build_config(data, file_path.stem)

    def _build_config(self, data: dict, default_name: str) -> CsvMappingConfig:
        """Build CsvMappingConfig from parsed YAML data."""
        # Parse name
        name = data.get("name", default_name)

        # Parse format
        format_str = data.get("format", "simple").lower()
        try:
            csv_format = CsvFormat(format_str)
        except ValueError:
            raise CsvBrokerParserError(
                f"Invalid format '{format_str}'. Must be one of: simple, detailed, custom"
            )

        # Parse columns
        columns_data = data.get("columns", {})
        columns = self._parse_columns(columns_data)

        # Parse transforms
        transforms_data = data.get("transforms", {})
        transforms = self._parse_transforms(transforms_data)

        return CsvMappingConfig(
            name=name,
            format=csv_format,
            columns=columns,
            transforms=transforms,
        )

    def _parse_columns(self, columns_data: dict) -> ColumnMapping:
        """Parse columns section into ColumnMapping."""
        # Build kwargs from columns_data, falling back to defaults
        default = ColumnMapping()
        kwargs = {}

        for field in [
            "date",
            "ticker",
            "foreign_buy_value",
            "foreign_sell_value",
            "foreign_buy_lot",
            "foreign_sell_lot",
            "total_value",
            "total_lot",
            "broker_code",
            "broker_name",
            "broker_type",
            "buy_lot",
            "sell_lot",
            "buy_value",
            "sell_value",
        ]:
            kwargs[field] = columns_data.get(field, getattr(default, field))

        return ColumnMapping(**kwargs)

    def _parse_transforms(self, transforms_data: dict) -> dict[str, Transform]:
        """Parse transforms section."""
        transforms = {}

        for field, transform_data in transforms_data.items():
            if not isinstance(transform_data, dict):
                continue

            date_format = transform_data.get("format")
            multiplier = transform_data.get("multiplier")

            transforms[field] = Transform(
                date_format=date_format,
                multiplier=Decimal(str(multiplier)) if multiplier else None,
            )

        return transforms
