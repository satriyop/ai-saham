import hashlib
import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from src.application.dto.agent_tool_context import AgentToolExecutionContext
from src.application.services.agent_accumulation_context import (
    build_agent_accumulation_context,
)
from src.application.services.agent_broker_desk_tool import (
    BrokerDeskArguments,
    BrokerDeskTool,
)
from src.application.use_case.view_broker_desk_show_use_case import (
    ViewBrokerDeskShowRequest,
)
from src.domain.entities.broker_flow import BrokerDailyFlow
from src.infrastructure.composition.view_broker_deps import (
    build_read_only_broker_desk_use_cases,
)
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from tests.application.services.test_agent_accumulation_context import make_candidate

pytestmark = pytest.mark.agent


def _identity(path) -> tuple[str, int, int]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with sqlite3.connect(path) as connection:
        schema_version = int(connection.execute("PRAGMA schema_version").fetchone()[0])
        data_version = int(connection.execute("PRAGMA data_version").fetchone()[0])
    return digest, schema_version, data_version


def _seed_flow(db_path) -> None:
    repo = SQLiteBrokerRepository(db_path)
    repo.save_broker_daily_flows(
        [
            BrokerDailyFlow(
                ticker="BBCA",
                broker_code="YP",
                broker_name="YP Desk",
                date=date(2026, 8, 1),
                buy_lot=10,
                sell_lot=2,
                net_lot=8,
                buy_value=Decimal("1000"),
                sell_value=Decimal("200"),
                net_value=Decimal("800"),
                avg_buy_price=Decimal("100"),
                avg_sell_price=Decimal("100"),
                avg_price=Decimal("100"),
                buy_pct=1.0,
                sell_pct=0.2,
            )
        ]
    )


def test_read_only_composition_does_not_mutate_existing_database(tmp_path) -> None:
    db_path = tmp_path / "broker.db"
    _seed_flow(db_path)
    before = _identity(db_path)

    use_cases = build_read_only_broker_desk_use_cases(db_path)
    result = use_cases.show.execute(ViewBrokerDeskShowRequest(broker_code="YP"))
    tool_result = BrokerDeskTool(use_cases).execute(
        "desk",
        BrokerDeskArguments("YP", "SHOW"),
        AgentToolExecutionContext(build_agent_accumulation_context(make_candidate())),
    )

    assert result is not None
    assert result.broker_code == "YP"
    assert tool_result.data is not None
    assert tool_result.data.broker_code == "YP"
    assert _identity(db_path) == before


def test_read_only_composition_never_creates_missing_database(tmp_path) -> None:
    db_path = tmp_path / "missing" / "broker.db"

    with pytest.raises(FileNotFoundError, match="database is unavailable"):
        build_read_only_broker_desk_use_cases(db_path)

    assert not db_path.exists()
    assert not db_path.parent.exists()
