"""
Tests for BrokerCsvAdapter and CSV parsing infrastructure.

Tests:
- Format detection
- Simple format parsing
- Detailed format parsing
- Custom mappings
- Error handling
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.domain.ports.csv_broker_parser import (
    ColumnMapping,
    CsvBrokerParserError,
    CsvFormat,
    CsvFormatDetectionError,
    CsvMappingConfig,
    ErrorStrategy,
    Transform,
)
from src.infrastructure.csv.broker_csv_adapter import BrokerCsvAdapter
from src.infrastructure.csv.format_detector import FormatDetector
from src.infrastructure.csv.mapping_loader import MappingLoader


class TestFormatDetector:
    """Tests for CSV format detection."""

    def test_detect_simple_format(self, tmp_path: Path) -> None:
        """Should detect simple format from headers."""
        csv_content = (
            "date,ticker,foreign_buy_value,foreign_sell_value,"
            "foreign_buy_lot,foreign_sell_lot,total_value,total_lot\n"
            "2024-01-15,BBCA,100000000,80000000,1000,800,500000000,5000\n"
        )
        csv_file = tmp_path / "simple.csv"
        csv_file.write_text(csv_content)

        detector = FormatDetector()
        result = detector.detect(csv_file)

        assert result == CsvFormat.SIMPLE

    def test_detect_detailed_format(self, tmp_path: Path) -> None:
        """Should detect detailed format from headers."""
        csv_content = (
            "date,ticker,broker_code,broker_name,broker_type,"
            "buy_lot,sell_lot,buy_value,sell_value\n"
            "2024-01-15,BBCA,YP,Mirae Asset,FOREIGN,100,50,1000000,500000\n"
        )
        csv_file = tmp_path / "detailed.csv"
        csv_file.write_text(csv_content)

        detector = FormatDetector()
        result = detector.detect(csv_file)

        assert result == CsvFormat.DETAILED

    def test_detect_format_case_insensitive(self, tmp_path: Path) -> None:
        """Should handle case-insensitive headers."""
        csv_content = (
            "DATE,TICKER,FOREIGN_BUY_VALUE,FOREIGN_SELL_VALUE,"
            "FOREIGN_BUY_LOT,FOREIGN_SELL_LOT,TOTAL_VALUE,TOTAL_LOT\n"
            "2024-01-15,BBCA,100000000,80000000,1000,800,500000000,5000\n"
        )
        csv_file = tmp_path / "upper.csv"
        csv_file.write_text(csv_content)

        detector = FormatDetector()
        result = detector.detect(csv_file)

        assert result == CsvFormat.SIMPLE

    def test_detect_format_with_spaces(self, tmp_path: Path) -> None:
        """Should handle headers with spaces."""
        csv_content = (
            "date,ticker,foreign buy value,foreign sell value,"
            "foreign buy lot,foreign sell lot,total value,total lot\n"
            "2024-01-15,BBCA,100000000,80000000,1000,800,500000000,5000\n"
        )
        csv_file = tmp_path / "spaces.csv"
        csv_file.write_text(csv_content)

        detector = FormatDetector()
        result = detector.detect(csv_file)

        assert result == CsvFormat.SIMPLE

    def test_detect_format_unknown(self, tmp_path: Path) -> None:
        """Should raise error for unknown format."""
        csv_content = "col1,col2,col3\nval1,val2,val3\n"
        csv_file = tmp_path / "unknown.csv"
        csv_file.write_text(csv_content)

        detector = FormatDetector()

        with pytest.raises(CsvFormatDetectionError):
            detector.detect(csv_file)

    def test_detect_format_file_not_found(self) -> None:
        """Should raise error for missing file."""
        detector = FormatDetector()

        with pytest.raises(CsvFormatDetectionError):
            detector.detect(Path("/nonexistent/file.csv"))

    def test_detect_format_empty_file(self, tmp_path: Path) -> None:
        """Should raise error for empty file."""
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("")

        detector = FormatDetector()

        with pytest.raises(CsvFormatDetectionError):
            detector.detect(csv_file)


class TestBrokerCsvAdapter:
    """Tests for CSV parsing adapter."""

    @pytest.fixture
    def adapter(self) -> BrokerCsvAdapter:
        """Create adapter instance."""
        return BrokerCsvAdapter()

    def test_parse_simple_format(self, adapter: BrokerCsvAdapter, tmp_path: Path) -> None:
        """Should parse simple format correctly."""
        csv_content = (
            "date,ticker,foreign_buy_value,foreign_sell_value,"
            "foreign_buy_lot,foreign_sell_lot,total_value,total_lot\n"
            "2024-01-15,BBCA,50000000000,30000000000,5000,3000,200000000000,20000\n"
            "2024-01-16,BBCA,60000000000,40000000000,6000,4000,250000000000,25000\n"
        )
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(csv_content)

        result = adapter.parse(csv_file)

        assert result.success_count == 2
        assert result.skipped_rows == 0
        assert result.format_detected == CsvFormat.SIMPLE

        # Verify first summary
        summary = result.summaries[0]
        assert summary.ticker == "BBCA"
        assert summary.date == date(2024, 1, 15)
        assert summary.foreign_buy_value == Decimal("50000000000")
        assert summary.foreign_sell_value == Decimal("30000000000")
        assert summary.foreign_buy_lot == 5000
        assert summary.foreign_sell_lot == 3000
        assert summary.total_value == Decimal("200000000000")
        assert summary.total_lot == 20000

    def test_parse_detailed_format(self, adapter: BrokerCsvAdapter, tmp_path: Path) -> None:
        """Should parse detailed format and aggregate correctly."""
        csv_content = (
            "date,ticker,broker_code,broker_name,broker_type,"
            "buy_lot,sell_lot,buy_value,sell_value\n"
            "2024-01-15,BBCA,YP,Mirae Asset,FOREIGN,1000,500,10000000000,5000000000\n"
            "2024-01-15,BBCA,CC,Mandiri Sekuritas,LOCAL,800,1200,8000000000,12000000000\n"
            "2024-01-15,BBCA,MS,Morgan Stanley,FOREIGN,500,300,5000000000,3000000000\n"
        )
        csv_file = tmp_path / "detailed.csv"
        csv_file.write_text(csv_content)

        result = adapter.parse(csv_file)

        assert result.success_count == 1  # Aggregated to 1 summary
        assert result.format_detected == CsvFormat.DETAILED

        summary = result.summaries[0]
        assert summary.ticker == "BBCA"
        assert summary.date == date(2024, 1, 15)

        # Foreign flow: YP + MS
        assert summary.foreign_buy_value == Decimal("15000000000")  # 10B + 5B
        assert summary.foreign_sell_value == Decimal("8000000000")  # 5B + 3B
        assert summary.foreign_buy_lot == 1500  # 1000 + 500
        assert summary.foreign_sell_lot == 800  # 500 + 300

        # Total includes all brokers
        assert summary.total_value == Decimal("43000000000")  # Sum of all
        assert summary.total_lot == 4300  # Sum of all lots

    def test_parse_with_errors_skip_strategy(
        self, adapter: BrokerCsvAdapter, tmp_path: Path
    ) -> None:
        """Should skip invalid rows with skip strategy."""
        csv_content = (
            "date,ticker,foreign_buy_value,foreign_sell_value,"
            "foreign_buy_lot,foreign_sell_lot,total_value,total_lot\n"
            "2024-01-15,BBCA,50000000000,30000000000,5000,3000,200000000000,20000\n"
            "invalid-date,BBRI,100,200,10,20,300,30\n"  # Invalid date
            "2024-01-16,TLKM,40000000000,20000000000,4000,2000,150000000000,15000\n"
        )
        csv_file = tmp_path / "with_errors.csv"
        csv_file.write_text(csv_content)

        result = adapter.parse(csv_file, error_strategy=ErrorStrategy.SKIP)

        assert result.success_count == 2
        assert result.skipped_rows == 1
        assert result.has_errors is True
        assert len(result.errors) == 1

    def test_parse_with_errors_fail_strategy(
        self, adapter: BrokerCsvAdapter, tmp_path: Path
    ) -> None:
        """Should fail on first error with fail strategy."""
        csv_content = (
            "date,ticker,foreign_buy_value,foreign_sell_value,"
            "foreign_buy_lot,foreign_sell_lot,total_value,total_lot\n"
            "invalid-date,BBCA,100,200,10,20,300,30\n"
        )
        csv_file = tmp_path / "invalid.csv"
        csv_file.write_text(csv_content)

        with pytest.raises(CsvBrokerParserError):
            adapter.parse(csv_file, error_strategy=ErrorStrategy.FAIL)

    def test_parse_with_custom_mapping(self, adapter: BrokerCsvAdapter, tmp_path: Path) -> None:
        """Should parse using custom column mapping."""
        csv_content = (
            "Trade Date,Stock Code,FB Val,FS Val,FB Lot,FS Lot,Total Val,Total Lot\n"
            "15/01/2024,BBCA,50000,30000,5000,3000,200000,20000\n"
        )
        csv_file = tmp_path / "custom.csv"
        csv_file.write_text(csv_content)

        mapping = CsvMappingConfig(
            name="custom",
            format=CsvFormat.SIMPLE,
            columns=ColumnMapping(
                date="Trade Date",
                ticker="Stock Code",
                foreign_buy_value="FB Val",
                foreign_sell_value="FS Val",
                foreign_buy_lot="FB Lot",
                foreign_sell_lot="FS Lot",
                total_value="Total Val",
                total_lot="Total Lot",
            ),
            transforms={
                "date": Transform(date_format="%d/%m/%Y"),
                "foreign_buy_value": Transform(multiplier=Decimal("1000000")),
                "foreign_sell_value": Transform(multiplier=Decimal("1000000")),
                "total_value": Transform(multiplier=Decimal("1000000")),
            },
        )

        result = adapter.parse(csv_file, mapping=mapping)

        assert result.success_count == 1

        summary = result.summaries[0]
        assert summary.ticker == "BBCA"
        assert summary.date == date(2024, 1, 15)
        # Values multiplied by 1M
        assert summary.foreign_buy_value == Decimal("50000000000")  # 50000 * 1M
        assert summary.foreign_sell_value == Decimal("30000000000")  # 30000 * 1M

    def test_preview_limits_rows(self, adapter: BrokerCsvAdapter, tmp_path: Path) -> None:
        """Should limit rows in preview mode."""
        lines = [
            "date,ticker,foreign_buy_value,foreign_sell_value,"
            "foreign_buy_lot,foreign_sell_lot,total_value,total_lot"
        ]
        for i in range(1, 11):
            lines.append(
                f"2024-01-{i:02d},BBCA,{i}000000000,{i - 1}000000000,"
                f"{i}000,{i - 1}000,{i}0000000000,{i}0000"
            )
        csv_content = "\n".join(lines)
        csv_file = tmp_path / "many_rows.csv"
        csv_file.write_text(csv_content)

        result = adapter.preview(csv_file, max_rows=3)

        # Preview should return limited summaries
        assert result.success_count == 3
        # total_rows counts all rows processed (may be more due to loop increment)
        assert result.total_rows >= 3

    def test_parse_handles_commas_in_values(
        self, adapter: BrokerCsvAdapter, tmp_path: Path
    ) -> None:
        """Should handle values with commas as thousand separators."""
        csv_content = (
            "date,ticker,foreign_buy_value,foreign_sell_value,"
            "foreign_buy_lot,foreign_sell_lot,total_value,total_lot\n"
            '2024-01-15,BBCA,"50,000,000,000","30,000,000,000",'
            '"5,000","3,000","200,000,000,000","20,000"\n'
        )
        csv_file = tmp_path / "commas.csv"
        csv_file.write_text(csv_content)

        result = adapter.parse(csv_file)

        assert result.success_count == 1

        summary = result.summaries[0]
        assert summary.foreign_buy_value == Decimal("50000000000")

    def test_parse_multiple_tickers(self, adapter: BrokerCsvAdapter, tmp_path: Path) -> None:
        """Should handle multiple tickers in same file."""
        csv_content = (
            "date,ticker,foreign_buy_value,foreign_sell_value,"
            "foreign_buy_lot,foreign_sell_lot,total_value,total_lot\n"
            "2024-01-15,BBCA,50000000000,30000000000,5000,3000,200000000000,20000\n"
            "2024-01-15,BBRI,40000000000,25000000000,4000,2500,180000000000,18000\n"
            "2024-01-16,BBCA,60000000000,35000000000,6000,3500,220000000000,22000\n"
        )
        csv_file = tmp_path / "multi_ticker.csv"
        csv_file.write_text(csv_content)

        result = adapter.parse(csv_file)

        assert result.success_count == 3

        tickers = {s.ticker for s in result.summaries}
        assert tickers == {"BBCA", "BBRI"}

    def test_parse_lowercase_ticker_uppercased(
        self, adapter: BrokerCsvAdapter, tmp_path: Path
    ) -> None:
        """Should uppercase lowercase tickers."""
        csv_content = (
            "date,ticker,foreign_buy_value,foreign_sell_value,"
            "foreign_buy_lot,foreign_sell_lot,total_value,total_lot\n"
            "2024-01-15,bbca,50000000000,30000000000,5000,3000,200000000000,20000\n"
        )
        csv_file = tmp_path / "lower.csv"
        csv_file.write_text(csv_content)

        result = adapter.parse(csv_file)

        assert result.summaries[0].ticker == "BBCA"


class TestMappingLoader:
    """Tests for YAML mapping loader."""

    def test_load_default_mapping(self) -> None:
        """Should return default mapping."""
        loader = MappingLoader()
        config = loader.load("default")

        assert config.name == "default"
        assert config.format == CsvFormat.SIMPLE
        assert config.columns.date == "date"

    def test_load_from_file(self, tmp_path: Path) -> None:
        """Should load mapping from YAML file."""
        yaml_content = """
version: 1
name: "test_mapping"
format: simple

columns:
  date: "Trade Date"
  ticker: "Stock"
  foreign_buy_value: "FB"
  foreign_sell_value: "FS"

transforms:
  date:
    format: "%d/%m/%Y"
  foreign_buy_value:
    multiplier: 1000000
"""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(yaml_content)

        loader = MappingLoader()
        config = loader.load_from_file(yaml_file)

        assert config.name == "test_mapping"
        assert config.format == CsvFormat.SIMPLE
        assert config.columns.date == "Trade Date"
        assert config.columns.ticker == "Stock"
        assert config.transforms["date"].date_format == "%d/%m/%Y"
        assert config.transforms["foreign_buy_value"].multiplier == Decimal("1000000")

    def test_load_mapping_not_found(self) -> None:
        """Should raise error for missing mapping."""
        loader = MappingLoader([Path("/nonexistent")])

        with pytest.raises(CsvBrokerParserError):
            loader.load("nonexistent_mapping")

    def test_list_available(self, tmp_path: Path) -> None:
        """Should list available mappings."""
        # Create test mapping files
        (tmp_path / "mapping1.yaml").write_text("name: mapping1\nformat: simple")
        (tmp_path / "mapping2.yml").write_text("name: mapping2\nformat: simple")

        loader = MappingLoader([tmp_path])
        available = loader.list_available()

        assert "default" in available
        assert "mapping1" in available
        assert "mapping2" in available


class TestBrokerTypeDetection:
    """Tests for broker type detection in detailed format."""

    @pytest.fixture
    def adapter(self) -> BrokerCsvAdapter:
        """Create adapter instance."""
        return BrokerCsvAdapter()

    @pytest.mark.parametrize(
        "type_value,expected",
        [
            ("FOREIGN", "FOREIGN"),
            ("foreign", "FOREIGN"),
            ("ASING", "FOREIGN"),
            ("F", "FOREIGN"),
            ("LOCAL", "LOCAL"),
            ("LOKAL", "LOCAL"),
            ("L", "LOCAL"),
            ("DOMESTIC", "LOCAL"),
            ("D", "LOCAL"),
            ("UNKNOWN", "UNKNOWN"),
            ("OTHER", "UNKNOWN"),
        ],
    )
    def test_broker_type_parsing(
        self,
        adapter: BrokerCsvAdapter,
        tmp_path: Path,
        type_value: str,
        expected: str,
    ) -> None:
        """Should correctly parse broker types."""
        csv_content = (
            "date,ticker,broker_code,broker_name,broker_type,"
            "buy_lot,sell_lot,buy_value,sell_value\n"
            f"2024-01-15,BBCA,XX,Test Broker,{type_value},"
            "100,50,1000000000,500000000\n"
        )
        csv_file = tmp_path / "broker_type.csv"
        csv_file.write_text(csv_content)

        result = adapter.parse(csv_file)

        # Get the broker from top buyers/sellers
        summary = result.summaries[0]
        # With a net buyer, should be in top_buyers
        if summary.top_buyers:
            broker_type = summary.top_buyers[0].broker_type.value
        else:
            broker_type = summary.top_sellers[0].broker_type.value

        assert broker_type == expected
