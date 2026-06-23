"""
Tests for ImportBrokerData use case.

Tests:
- Preview mode
- Import mode
- Error handling
- Integration with repository
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.application.use_case.import_broker_data_use_case import (
    DetectCsvFormatUseCase,
    ImportBrokerDataRequest,
    ImportBrokerDataUseCase,
)
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.csv_broker_parser import (
    CsvBrokerParserError,
    CsvFormat,
    ErrorStrategy,
)
from src.infrastructure.csv import BrokerCsvAdapter
from src.infrastructure.persistence.sqlite_broker_repository import (
    SQLiteBrokerRepository,
)


class TestImportBrokerDataUseCase:
    """Tests for import broker data use case."""

    @pytest.fixture
    def temp_db(self, tmp_path: Path) -> Path:
        """Create temporary database path."""
        return tmp_path / "test.db"

    @pytest.fixture
    def repository(self, temp_db: Path) -> BrokerDataRepository:
        """Create repository instance."""
        return SQLiteBrokerRepository(temp_db)

    @pytest.fixture
    def parser(self) -> BrokerCsvAdapter:
        """Create parser instance."""
        return BrokerCsvAdapter()

    @pytest.fixture
    def use_case(
        self,
        parser: BrokerCsvAdapter,
        repository: BrokerDataRepository,
    ) -> ImportBrokerDataUseCase:
        """Create use case instance."""
        return ImportBrokerDataUseCase(parser, repository)

    def test_preview_mode_does_not_save(
        self,
        use_case: ImportBrokerDataUseCase,
        repository: BrokerDataRepository,
        tmp_path: Path,
    ) -> None:
        """Preview mode should not save to repository."""
        csv_content = (
            "date,ticker,foreign_buy_value,foreign_sell_value,"
            "foreign_buy_lot,foreign_sell_lot,total_value,total_lot\n"
            "2024-01-15,BBCA,50000000000,30000000000,5000,3000,200000000000,20000\n"
        )
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(csv_content)

        request = ImportBrokerDataRequest(
            file_path=csv_file,
            preview_only=True,
        )

        response = use_case.execute(request)

        # Preview shows data
        assert response.success is True
        assert len(response.summaries) == 1
        assert response.imported_count == 0  # Not imported

        # Repository should be empty
        saved = repository.get_broker_summaries("BBCA")
        assert len(saved) == 0

    def test_import_mode_saves_to_repository(
        self,
        use_case: ImportBrokerDataUseCase,
        repository: BrokerDataRepository,
        tmp_path: Path,
    ) -> None:
        """Import mode should save to repository."""
        csv_content = (
            "date,ticker,foreign_buy_value,foreign_sell_value,"
            "foreign_buy_lot,foreign_sell_lot,total_value,total_lot\n"
            "2024-01-15,BBCA,50000000000,30000000000,5000,3000,200000000000,20000\n"
            "2024-01-16,BBCA,60000000000,40000000000,6000,4000,250000000000,25000\n"
        )
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(csv_content)

        request = ImportBrokerDataRequest(
            file_path=csv_file,
            preview_only=False,
        )

        response = use_case.execute(request)

        assert response.success is True
        assert response.imported_count == 2

        # Repository should have data
        saved = repository.get_broker_summaries("BBCA")
        assert len(saved) == 2

        # Verify data
        assert saved[0].date == date(2024, 1, 15)
        assert saved[0].foreign_buy_value == Decimal("50000000000")

    def test_import_upsert_semantics(
        self,
        use_case: ImportBrokerDataUseCase,
        repository: BrokerDataRepository,
        tmp_path: Path,
    ) -> None:
        """Importing same date should update existing record."""
        # First import
        csv_content1 = (
            "date,ticker,foreign_buy_value,foreign_sell_value,"
            "foreign_buy_lot,foreign_sell_lot,total_value,total_lot\n"
            "2024-01-15,BBCA,50000000000,30000000000,5000,3000,200000000000,20000\n"
        )
        csv_file1 = tmp_path / "first.csv"
        csv_file1.write_text(csv_content1)

        request1 = ImportBrokerDataRequest(file_path=csv_file1)
        use_case.execute(request1)

        # Second import with updated values
        csv_content2 = (
            "date,ticker,foreign_buy_value,foreign_sell_value,"
            "foreign_buy_lot,foreign_sell_lot,total_value,total_lot\n"
            "2024-01-15,BBCA,70000000000,40000000000,7000,4000,300000000000,30000\n"
        )
        csv_file2 = tmp_path / "second.csv"
        csv_file2.write_text(csv_content2)

        request2 = ImportBrokerDataRequest(file_path=csv_file2)
        response2 = use_case.execute(request2)

        assert response2.imported_count == 1

        # Should have updated values
        saved = repository.get_broker_summaries("BBCA")
        assert len(saved) == 1
        assert saved[0].foreign_buy_value == Decimal("70000000000")

    def test_import_with_errors_skip_strategy(
        self,
        use_case: ImportBrokerDataUseCase,
        repository: BrokerDataRepository,
        tmp_path: Path,
    ) -> None:
        """Should skip invalid rows and import valid ones."""
        csv_content = (
            "date,ticker,foreign_buy_value,foreign_sell_value,"
            "foreign_buy_lot,foreign_sell_lot,total_value,total_lot\n"
            "2024-01-15,BBCA,50000000000,30000000000,5000,3000,200000000000,20000\n"
            "invalid,BBRI,100,200,10,20,300,30\n"
            "2024-01-16,TLKM,40000000000,20000000000,4000,2000,150000000000,15000\n"
        )
        csv_file = tmp_path / "with_errors.csv"
        csv_file.write_text(csv_content)

        request = ImportBrokerDataRequest(
            file_path=csv_file,
            error_strategy=ErrorStrategy.SKIP,
        )

        response = use_case.execute(request)

        assert response.success is True
        assert response.imported_count == 2
        assert response.skipped_count == 1
        assert response.has_errors is True
        assert len(response.errors) == 1

    def test_import_file_not_found(
        self,
        use_case: ImportBrokerDataUseCase,
    ) -> None:
        """Should raise error for missing file."""
        request = ImportBrokerDataRequest(
            file_path=Path("/nonexistent/file.csv"),
        )

        with pytest.raises(CsvBrokerParserError):
            use_case.execute(request)

    def test_import_empty_file(
        self,
        use_case: ImportBrokerDataUseCase,
        tmp_path: Path,
    ) -> None:
        """Should handle empty file gracefully."""
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("")

        request = ImportBrokerDataRequest(file_path=csv_file)

        with pytest.raises(CsvBrokerParserError):
            use_case.execute(request)

    def test_import_multiple_tickers(
        self,
        use_case: ImportBrokerDataUseCase,
        repository: BrokerDataRepository,
        tmp_path: Path,
    ) -> None:
        """Should import data for multiple tickers."""
        csv_content = (
            "date,ticker,foreign_buy_value,foreign_sell_value,"
            "foreign_buy_lot,foreign_sell_lot,total_value,total_lot\n"
            "2024-01-15,BBCA,50000000000,30000000000,5000,3000,200000000000,20000\n"
            "2024-01-15,BBRI,40000000000,25000000000,4000,2500,180000000000,18000\n"
            "2024-01-15,TLKM,35000000000,20000000000,3500,2000,150000000000,15000\n"
        )
        csv_file = tmp_path / "multi.csv"
        csv_file.write_text(csv_content)

        request = ImportBrokerDataRequest(file_path=csv_file)

        response = use_case.execute(request)

        assert response.success is True
        assert response.imported_count == 3

        # Verify each ticker
        assert len(repository.get_broker_summaries("BBCA")) == 1
        assert len(repository.get_broker_summaries("BBRI")) == 1
        assert len(repository.get_broker_summaries("TLKM")) == 1

    def test_response_message_contains_info(
        self,
        use_case: ImportBrokerDataUseCase,
        tmp_path: Path,
    ) -> None:
        """Response message should contain useful info."""
        csv_content = (
            "date,ticker,foreign_buy_value,foreign_sell_value,"
            "foreign_buy_lot,foreign_sell_lot,total_value,total_lot\n"
            "2024-01-15,BBCA,50000000000,30000000000,5000,3000,200000000000,20000\n"
            "2024-01-16,BBCA,60000000000,40000000000,6000,4000,250000000000,25000\n"
        )
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(csv_content)

        request = ImportBrokerDataRequest(file_path=csv_file)

        response = use_case.execute(request)

        assert "Imported" in response.message
        assert "BBCA" in response.message


class TestDetectCsvFormatUseCase:
    """Tests for format detection use case."""

    @pytest.fixture
    def parser(self) -> BrokerCsvAdapter:
        """Create parser instance."""
        return BrokerCsvAdapter()

    @pytest.fixture
    def use_case(self, parser: BrokerCsvAdapter) -> DetectCsvFormatUseCase:
        """Create use case instance."""
        return DetectCsvFormatUseCase(parser)

    def test_detect_simple_format(
        self,
        use_case: DetectCsvFormatUseCase,
        tmp_path: Path,
    ) -> None:
        """Should detect simple format."""
        csv_content = (
            "date,ticker,foreign_buy_value,foreign_sell_value,"
            "foreign_buy_lot,foreign_sell_lot,total_value,total_lot\n"
        )
        csv_file = tmp_path / "simple.csv"
        csv_file.write_text(csv_content)

        result = use_case.execute(csv_file)

        assert result == CsvFormat.SIMPLE

    def test_detect_detailed_format(
        self,
        use_case: DetectCsvFormatUseCase,
        tmp_path: Path,
    ) -> None:
        """Should detect detailed format."""
        csv_content = (
            "date,ticker,broker_code,broker_name,broker_type,"
            "buy_lot,sell_lot,buy_value,sell_value\n"
        )
        csv_file = tmp_path / "detailed.csv"
        csv_file.write_text(csv_content)

        result = use_case.execute(csv_file)

        assert result == CsvFormat.DETAILED


class TestIntegrationImportAndQuery:
    """Integration tests for import and querying workflow."""

    def test_full_import_query_workflow(self, tmp_path: Path) -> None:
        """Test complete workflow: import CSV -> query data."""
        # Setup
        db_path = tmp_path / "data.db"
        csv_content = (
            "date,ticker,foreign_buy_value,foreign_sell_value,"
            "foreign_buy_lot,foreign_sell_lot,total_value,total_lot\n"
            "2024-01-15,BBCA,50000000000,30000000000,5000,3000,200000000000,20000\n"
            "2024-01-16,BBCA,60000000000,35000000000,6000,3500,220000000000,22000\n"
            "2024-01-17,BBCA,55000000000,40000000000,5500,4000,210000000000,21000\n"
        )
        csv_file = tmp_path / "data.csv"
        csv_file.write_text(csv_content)

        # Import
        parser = BrokerCsvAdapter()
        repository = SQLiteBrokerRepository(db_path)
        use_case = ImportBrokerDataUseCase(parser, repository)

        response = use_case.execute(
            ImportBrokerDataRequest(file_path=csv_file)
        )

        assert response.success is True
        assert response.imported_count == 3

        # Query
        summaries = repository.get_broker_summaries(
            "BBCA",
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 17),
        )

        assert len(summaries) == 3

        # Verify computations
        total_foreign_net = sum(s.foreign_net_value for s in summaries)
        # (50B-30B) + (60B-35B) + (55B-40B) = 20B + 25B + 15B = 60B
        assert total_foreign_net == Decimal("60000000000")

        # Check date range
        date_range = repository.get_date_range("BBCA")
        assert date_range == (date(2024, 1, 15), date(2024, 1, 17))
