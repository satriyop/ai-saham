"""
SQLite broker data repository.

This adapter implements BrokerDataRepository using SQLite.
Provides local-first persistence for broker flow data caching.

Layer: Infrastructure
Depends on: Domain ports, sqlite3 (standard library)
"""

from datetime import date
from pathlib import Path

from src.domain.entities.broker_flow import (
    BrokerDailyFlow,
    BrokerSummary,
    ForeignFlowPoint,
    ForeignFlowSnapshot,
)
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.infrastructure.persistence.sqlite_broker_daily_flow_store import (
    SQLiteBrokerDailyFlowStore,
)
from src.infrastructure.persistence.sqlite_broker_schema import ensure_sqlite_broker_schema
from src.infrastructure.persistence.sqlite_broker_summary_store import SQLiteBrokerSummaryStore
from src.infrastructure.persistence.sqlite_foreign_flow_store import SQLiteForeignFlowStore


class SQLiteBrokerRepository(BrokerDataRepository):
    """
    Broker data repository using SQLite.

    Schema:
        broker_summaries(ticker, date, source, ...) PK (ticker, date, source)
        foreign_flow_points(ticker, date, source, ...) PK (ticker, date, source)
        foreign_flow_snapshots(ticker, snapshot_date, period_days, source) PK composite
        broker_daily_flow(ticker, date, broker_code, source) PK — Stockbit
            per-day rows for configured tracked broker codes only; not
            exhaustive full-market broker composition
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path).expanduser()
        ensure_sqlite_broker_schema(self._db_path)
        self._summaries = SQLiteBrokerSummaryStore(self._db_path)
        self._foreign_flow = SQLiteForeignFlowStore(self._db_path)
        self._daily_flow = SQLiteBrokerDailyFlowStore(self._db_path)

    # ── BrokerSummary persistence ──────────────────────────────────────────

    def save_broker_summary(self, summary: BrokerSummary) -> None:
        self._summaries.save_broker_summary(summary)

    def save_broker_summaries(self, summaries: list[BrokerSummary]) -> None:
        self._summaries.save_broker_summaries(summaries)

    def get_broker_summary(self, ticker: str, target_date: date) -> BrokerSummary | None:
        return self._summaries.get_broker_summary(ticker, target_date)

    def get_broker_summaries(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
        source: str | None = None,
    ) -> list[BrokerSummary]:
        return self._summaries.get_broker_summaries(ticker, start_date, end_date, source)

    def has_data(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
        source: str | None = None,
    ) -> bool:
        return self._summaries.has_data(ticker, start_date, end_date, source)

    def get_date_range(
        self,
        ticker: str,
        source: str | None = None,
    ) -> tuple[date, date] | None:
        return self._summaries.get_date_range(ticker, source)

    def get_cached_tickers(self) -> list[str]:
        return self._summaries.get_cached_tickers()

    # ── ForeignFlowPoint persistence ───────────────────────────────────────

    def save_foreign_flow_points(self, points: list[ForeignFlowPoint]) -> None:
        self._foreign_flow.save_foreign_flow_points(points)

    def get_foreign_flow_points(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
        source: str | None = None,
    ) -> list[ForeignFlowPoint]:
        return self._foreign_flow.get_foreign_flow_points(ticker, start_date, end_date, source)

    def get_foreign_flow_date_range(
        self,
        ticker: str,
        source: str | None = None,
    ) -> tuple[date, date] | None:
        return self._foreign_flow.get_foreign_flow_date_range(ticker, source)

    # ── ForeignFlowSnapshot persistence ───────────────────────────────────

    def save_foreign_flow_snapshots(
        self,
        snapshots: list[ForeignFlowSnapshot],
        snapshot_date: date,
        period_days: int,
    ) -> None:
        self._foreign_flow.save_foreign_flow_snapshots(snapshots, snapshot_date, period_days)

    def get_foreign_flow_snapshots(
        self,
        snapshot_date: date,
        period_days: int,
    ) -> list[ForeignFlowSnapshot]:
        return self._foreign_flow.get_foreign_flow_snapshots(snapshot_date, period_days)

    # ── BrokerDailyFlow persistence ───────────────────────────────────────

    def save_broker_daily_flows(self, flows: list[BrokerDailyFlow]) -> None:
        self._daily_flow.save_broker_daily_flows(flows)

    def get_broker_daily_flows(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
        broker_codes: list[str] | None = None,
        source: str | None = None,
    ) -> list[BrokerDailyFlow]:
        return self._daily_flow.get_broker_daily_flows(
            ticker, start_date, end_date, broker_codes, source
        )

    def get_broker_daily_flow_date_range(
        self,
        ticker: str,
        source: str | None = None,
    ) -> tuple[date, date] | None:
        return self._daily_flow.get_broker_daily_flow_date_range(ticker, source)

    def get_broker_daily_flows_by_code(
        self,
        broker_code: str,
        start_date: date | None = None,
        end_date: date | None = None,
        ticker: str | None = None,
        source: str | None = None,
    ) -> list[BrokerDailyFlow]:
        return self._daily_flow.get_broker_daily_flows_by_code(
            broker_code, start_date, end_date, ticker, source
        )

    def get_broker_daily_flows_for_codes(
        self,
        broker_codes: list[str],
        start_date: date | None = None,
        end_date: date | None = None,
        ticker: str | None = None,
        source: str | None = None,
    ) -> dict[str, list[BrokerDailyFlow]]:
        """Batch desk-centric read (one query) for list/pulse UIs."""
        return self._daily_flow.get_broker_daily_flows_for_codes(
            broker_codes, start_date, end_date, ticker, source
        )
