"""
Workflow factory for creating application use cases configured with infrastructure dependencies.

Layer: Adapter (composition root / dependency injection helper)
"""

from pathlib import Path

from src.adapters.cli.fetch_broker_provider_factory import create_broker_data_provider
from src.application.use_case.fetch_broker_command_workflows import (
    FetchBrokerFlowHistoryWorkflowUseCase,
    FetchBrokerSummaryWorkflowUseCase,
    FetchForeignTopStocksWorkflowUseCase,
)
from src.application.use_case.import_broker_data_use_case import ImportBrokerDataUseCase
from src.infrastructure.csv import BrokerCsvAdapter, MappingLoader
from src.infrastructure.persistence.sqlite_broker_repository import (
    SQLiteBrokerRepository,
)


def load_broker_import_mapping(mapping: str | None):
    """Load CSV mapping configuration by name or from a local file path."""
    if not mapping:
        return None
    mapping_loader = MappingLoader()
    mapping_path = Path(mapping)
    if mapping_path.exists():
        return mapping_loader.load_from_file(mapping_path)
    return mapping_loader.load(mapping)


def create_fetch_broker_summary_workflow(
    provider_name: str,
    db_path: Path,
) -> FetchBrokerSummaryWorkflowUseCase:
    """Create a FetchBrokerSummaryWorkflowUseCase configured with DB and provider."""
    provider = create_broker_data_provider(provider_name)
    repository = SQLiteBrokerRepository(db_path)
    return FetchBrokerSummaryWorkflowUseCase(provider=provider, repository=repository)


def create_foreign_top_stocks_workflow(
    provider_name: str,
    db_path: Path,
) -> FetchForeignTopStocksWorkflowUseCase:
    """Create a FetchForeignTopStocksWorkflowUseCase configured with DB and provider."""
    provider = create_broker_data_provider(provider_name)
    repository = SQLiteBrokerRepository(db_path)
    return FetchForeignTopStocksWorkflowUseCase(provider=provider, repository=repository)


def create_broker_flow_history_workflow(
    provider_name: str,
    db_path: Path,
) -> FetchBrokerFlowHistoryWorkflowUseCase:
    """Create a FetchBrokerFlowHistoryWorkflowUseCase configured with DB and provider."""
    provider = create_broker_data_provider(provider_name)
    repository = SQLiteBrokerRepository(db_path)
    return FetchBrokerFlowHistoryWorkflowUseCase(provider=provider, repository=repository)


def create_import_broker_data_use_case(
    db_path: Path,
) -> ImportBrokerDataUseCase:
    """Create an ImportBrokerDataUseCase configured with DB and CSV parser."""
    parser = BrokerCsvAdapter()
    repository = SQLiteBrokerRepository(db_path)
    return ImportBrokerDataUseCase(parser=parser, repository=repository)
