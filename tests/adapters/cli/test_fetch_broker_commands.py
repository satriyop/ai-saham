"""
Tests for Fetch Broker CLI Commands.

Layer: Adapter (Tests)
"""

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from src.adapters.cli.fetch_broker_provider_factory import (
    create_broker_data_provider,
)
from src.adapters.cli.main import app
from src.application.use_case.fetch_broker_command_workflows import (
    FetchBrokerSummaryWorkflowResult,
    FetchForeignTopStocksWorkflowResult,
)
from src.application.use_case.fetch_broker_data_use_case import (
    FetchBrokerDataResponse,
)
from src.application.use_case.import_broker_data_use_case import (
    ImportBrokerDataResponse,
)
from src.domain.entities.broker_flow import BrokerSummary, ForeignFlowSnapshot
from src.domain.ports.csv_broker_parser import CsvFormat, ParseError

runner = CliRunner()


def test_provider_factory_unknown_provider_and_missing_session() -> None:
    # 1. Unknown provider raises ValueError
    with pytest.raises(ValueError) as exc:
        create_broker_data_provider("nonexistent")
    assert "Unknown provider" in str(exc.value)

    # 2. Missing stockbit session message
    import src.infrastructure.composition.stockbit_session_factory as session_factory

    original_get_session = session_factory.get_stockbit_session
    session_factory.get_stockbit_session = lambda: None

    try:
        with pytest.raises(ValueError) as exc_session:
            create_broker_data_provider("stockbit")
        assert (
            "No active Stockbit session. Run `saham fetch stockbit login`."
            in str(exc_session.value)
        )
    finally:
        session_factory.get_stockbit_session = original_get_session


def test_broker_fetch_exact_flow_message_appears(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyWorkflow:
        def execute(self, request: Any) -> FetchBrokerSummaryWorkflowResult:
            response = FetchBrokerDataResponse(
                ticker="BBCA",
                summaries=[
                    BrokerSummary(
                        ticker="BBCA",
                        date=date(2024, 1, 1),
                        top_buyers=(),
                        top_sellers=(),
                        foreign_buy_value=Decimal("100"),
                        foreign_sell_value=Decimal("50"),
                        foreign_buy_lot=10,
                        foreign_sell_lot=5,
                        total_value=Decimal("1000"),
                        total_lot=100,
                        source="stockbit",
                    )
                ],
                from_cache=False,
                message="ok",
            )
            return FetchBrokerSummaryWorkflowResult(
                response=response,
                exact_flow_saved_count=42,
            )

    monkeypatch.setattr(
        "src.adapters.cli.fetch_broker_commands.create_fetch_broker_summary_workflow",
        lambda provider_name, db_path: DummyWorkflow(),
    )

    result = runner.invoke(app, ["fetch", "broker", "BBCA", "--provider", "stockbit"])
    assert result.exit_code == 0
    assert "Saved 42 exact foreign-flow points" in result.stdout


def test_broker_top_foreign_no_save(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_requests = []

    class DummyWorkflow:
        def execute(
            self, request: Any
        ) -> FetchForeignTopStocksWorkflowResult:
            captured_requests.append(request)
            return FetchForeignTopStocksWorkflowResult(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 5),
                snapshots=[
                    ForeignFlowSnapshot(
                        ticker="BBCA",
                        date=date(2024, 1, 5),
                        net_val=Decimal("1000"),
                        net_lot=100,
                    )
                ],
                saved_count=0,
                save_warning=None,
            )

    monkeypatch.setattr(
        "src.adapters.cli.fetch_broker_commands.create_foreign_top_stocks_workflow",
        lambda provider_name, db_path: DummyWorkflow(),
    )

    result = runner.invoke(app, ["fetch", "broker-top-foreign", "--no-save"])
    assert result.exit_code == 0
    assert len(captured_requests) == 1
    assert captured_requests[0].save is False


def test_broker_import_on_error_report_prints_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class DummyWorkflow:
        def execute(self, request: Any) -> ImportBrokerDataResponse:
            return ImportBrokerDataResponse(
                success=True,
                imported_count=1,
                skipped_count=1,
                total_rows=2,
                errors=[
                    ParseError(
                        row_number=2,
                        field="row",
                        value="invalid,row",
                        message="some parsing error",
                    )
                ],
                format_detected=CsvFormat.SIMPLE,
                summaries=[],
                message="Ok",
            )

    monkeypatch.setattr(
        "src.adapters.cli.fetch_broker_commands.create_import_broker_data_use_case",
        lambda db_path: DummyWorkflow(),
    )

    dummy_csv = tmp_path / "dummy.csv"
    dummy_csv.write_text("dummy")

    result = runner.invoke(
        app,
        [
            "fetch",
            "broker-import",
            str(dummy_csv),
            "--on-error",
            "report",
        ],
    )
    assert result.exit_code == 0
    assert "Parse Errors:" in result.stdout
    assert "some parsing error" in result.stdout
