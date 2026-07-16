"""
DQ-002G — planted future-row temporal leakage tests: market/broker sources.

Proves, using real SQLite repository code (not mocks) against tmp_path
databases, that a row dated/observed after `decision_at` cannot be read as
current for: candles, broker_summaries, broker_daily_flow,
foreign_flow_points, foreign_flow_snapshots.

Layer: Infrastructure (tests only) / Application (AssessSourceAvailabilityUseCase)
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from src.application.use_case.assess_source_availability_use_case import (
    AssessSourceAvailabilityUseCase,
)
from src.domain.entities.broker_flow import (
    BrokerDailyFlow,
    BrokerSummary,
    ForeignFlowPoint,
    ForeignFlowSnapshot,
)
from src.domain.entities.candle import Candle
from src.domain.services.trading_session_calendar import KnownTradingSessionCalendar
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.source_availability import SourceAvailabilityStatus
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

DECISION_DATE = date(2026, 7, 16)
FUTURE_DATE = date(2026, 7, 17)


def _calendar() -> KnownTradingSessionCalendar:
    """DQ-002I: none of this file's fixed dates (2026-07-01..2026-07-31)
    cross an IDX holiday, so a plain Mon-Fri calendar for the whole month
    preserves each test's pre-DQ-002I gap expectations exactly."""
    start, end = date(2026, 7, 1), date(2026, 7, 31)
    sessions = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            sessions.append(current)
        current += timedelta(days=1)
    return KnownTradingSessionCalendar(
        sessions=tuple(sessions), coverage_start=start, coverage_end=end
    )


def _decision_session(latest_completed_session: date = DECISION_DATE) -> EffectiveMarketSession:
    decision_at = datetime(2026, 7, 16, 16, 0, tzinfo=IDX_TIMEZONE)
    return EffectiveMarketSession(
        run_at=decision_at,
        decision_at=decision_at,
        latest_completed_session=latest_completed_session,
        analysis_as_of=latest_completed_session,
        market_session_name="AFTER_CLOSE",
        is_eod_pending=False,
        resolution_source="test_fixture",
        notes=(),
    )


def _candle(ticker: str, on: date, close: int = 100) -> Candle:
    return Candle(ticker=ticker, date=on, open=close, high=close, low=close, close=close, volume=1000)


class TestCandleTemporalLeakage:
    def test_candle_reader_excludes_rows_after_latest_completed_session(self, tmp_path):
        repo = SQLiteMarketRepository(db_path=tmp_path / "market.db")
        repo.save_candles(
            [
                _candle("BBCA", DECISION_DATE, close=9000),
                _candle("BBCA", FUTURE_DATE, close=9999),
            ]
        )

        bounded = repo.get_candles("BBCA", end_date=DECISION_DATE)

        assert [c.date for c in bounded] == [DECISION_DATE]
        assert all(c.date <= DECISION_DATE for c in bounded)

    def test_candle_observed_through_decision_date_is_current(self, tmp_path):
        repo = SQLiteMarketRepository(db_path=tmp_path / "market.db")
        repo.save_candles([_candle("BBCA", DECISION_DATE)])
        bounded = repo.get_candles("BBCA", end_date=DECISION_DATE)

        use_case = AssessSourceAvailabilityUseCase(calendar=_calendar())
        result = use_case.execute(
            source_family="candles",
            effective_session=_decision_session(),
            observed_through=bounded[-1].date,
        )

        assert result.status is SourceAvailabilityStatus.CURRENT
        assert result.is_authoritative is True

    def test_future_candle_date_fed_directly_is_invalid_never_current(self):
        use_case = AssessSourceAvailabilityUseCase(calendar=_calendar())
        result = use_case.execute(
            source_family="candles",
            effective_session=_decision_session(),
            observed_through=FUTURE_DATE,
        )

        assert result.status is SourceAvailabilityStatus.INVALID
        assert result.is_authoritative is False


class TestBrokerSummariesTemporalLeakage:
    def _summary(self, on: date) -> BrokerSummary:
        return BrokerSummary(
            ticker="BBCA",
            date=on,
            top_buyers=(),
            top_sellers=(),
            foreign_buy_value=Decimal("1000"),
            foreign_sell_value=Decimal("500"),
            foreign_buy_lot=10,
            foreign_sell_lot=5,
            total_value=Decimal("2000"),
            total_lot=20,
            source="idx",
        )

    def test_broker_summaries_reader_excludes_rows_after_decision_date(self, tmp_path):
        repo = SQLiteBrokerRepository(tmp_path / "broker.db")
        repo.save_broker_summaries([self._summary(DECISION_DATE), self._summary(FUTURE_DATE)])

        bounded = repo.get_broker_summaries("BBCA", end_date=DECISION_DATE, source="idx")

        assert [s.date for s in bounded] == [DECISION_DATE]

    def test_broker_summaries_future_rows_are_not_authoritative(self, tmp_path):
        repo = SQLiteBrokerRepository(tmp_path / "broker.db")
        repo.save_broker_summaries([self._summary(FUTURE_DATE)])
        # A caller that (incorrectly) queried without an end_date bound would
        # still see the future row from the raw repository call...
        unbounded = repo.get_broker_summaries("BBCA", source="idx")
        assert [s.date for s in unbounded] == [FUTURE_DATE]

        # ...but feeding that observed date into the availability contract
        # must never classify it as CURRENT/authoritative.
        use_case = AssessSourceAvailabilityUseCase(calendar=_calendar())
        result = use_case.execute(
            source_family="broker_summaries",
            effective_session=_decision_session(),
            observed_through=unbounded[0].date,
        )

        assert result.status is SourceAvailabilityStatus.INVALID
        assert result.is_authoritative is False


class TestBrokerDailyFlowTemporalLeakage:
    def _flow(self, on: date) -> BrokerDailyFlow:
        return BrokerDailyFlow(
            ticker="BBCA",
            broker_code="YP",
            broker_name="Mirae Asset",
            date=on,
            buy_lot=100,
            sell_lot=50,
            net_lot=50,
            buy_value=Decimal("1000"),
            sell_value=Decimal("500"),
            net_value=Decimal("500"),
            avg_buy_price=Decimal("100"),
            avg_sell_price=Decimal("100"),
            avg_price=Decimal("100"),
            buy_pct=10.0,
            sell_pct=5.0,
            source="stockbit",
        )

    def test_broker_daily_flow_reader_excludes_rows_after_decision_date(self, tmp_path):
        repo = SQLiteBrokerRepository(tmp_path / "broker.db")
        repo.save_broker_daily_flows([self._flow(DECISION_DATE), self._flow(FUTURE_DATE)])

        bounded = repo.get_broker_daily_flows("BBCA", end_date=DECISION_DATE, source="stockbit")

        assert [f.date for f in bounded] == [DECISION_DATE]

    def test_broker_daily_flow_late_within_lag_is_not_authoritative(self, tmp_path):
        repo = SQLiteBrokerRepository(tmp_path / "broker.db")
        repo.save_broker_daily_flows([self._flow(date(2026, 7, 15))])

        rows = repo.get_broker_daily_flows("BBCA", end_date=DECISION_DATE, source="stockbit")

        use_case = AssessSourceAvailabilityUseCase(calendar=_calendar())
        result = use_case.execute(
            source_family="broker_daily_flow",
            effective_session=_decision_session(),
            observed_through=rows[-1].date,
        )

        assert result.status is SourceAvailabilityStatus.LATE
        assert result.is_authoritative is False


class TestForeignFlowPointsTemporalLeakage:
    def _point(self, on: date) -> ForeignFlowPoint:
        return ForeignFlowPoint(
            ticker="BBCA",
            date=on,
            net_val=Decimal("1000"),
            net_lot=10,
            avg_price=Decimal("9000"),
            source="idx",
        )

    def test_foreign_flow_points_reader_excludes_rows_after_decision_date(self, tmp_path):
        repo = SQLiteBrokerRepository(tmp_path / "broker.db")
        repo.save_foreign_flow_points([self._point(DECISION_DATE), self._point(FUTURE_DATE)])

        bounded = repo.get_foreign_flow_points("BBCA", end_date=DECISION_DATE, source="idx")

        assert [p.date for p in bounded] == [DECISION_DATE]

    def test_foreign_flow_points_future_row_is_invalid_never_current(self, tmp_path):
        repo = SQLiteBrokerRepository(tmp_path / "broker.db")
        repo.save_foreign_flow_points([self._point(FUTURE_DATE)])
        unbounded = repo.get_foreign_flow_points("BBCA", source="idx")

        use_case = AssessSourceAvailabilityUseCase(calendar=_calendar())
        result = use_case.execute(
            source_family="foreign_flow_points",
            effective_session=_decision_session(),
            observed_through=unbounded[0].date,
        )

        assert result.status is SourceAvailabilityStatus.INVALID
        assert result.is_authoritative is False


class TestForeignFlowSnapshotsTemporalLeakage:
    def _snapshot(self, ticker: str = "BBCA") -> ForeignFlowSnapshot:
        return ForeignFlowSnapshot(ticker=ticker, date=DECISION_DATE, net_val=Decimal("1000"), net_lot=10)

    def test_foreign_flow_snapshots_reader_is_keyed_by_exact_snapshot_date(self, tmp_path):
        """`get_foreign_flow_snapshots` is an exact-match query (no end_date
        bound exists), so planting a future-dated snapshot must not appear
        when querying the correct decision-date key."""
        repo = SQLiteBrokerRepository(tmp_path / "broker.db")
        repo.save_foreign_flow_snapshots([self._snapshot()], snapshot_date=DECISION_DATE, period_days=7)
        repo.save_foreign_flow_snapshots([self._snapshot()], snapshot_date=FUTURE_DATE, period_days=7)

        rows = repo.get_foreign_flow_snapshots(DECISION_DATE, period_days=7)

        assert len(rows) == 1
        assert rows[0].date == DECISION_DATE

    def test_foreign_flow_snapshots_future_snapshot_date_is_invalid(self, tmp_path):
        repo = SQLiteBrokerRepository(tmp_path / "broker.db")
        repo.save_foreign_flow_snapshots([self._snapshot()], snapshot_date=FUTURE_DATE, period_days=7)
        rows = repo.get_foreign_flow_snapshots(FUTURE_DATE, period_days=7)

        use_case = AssessSourceAvailabilityUseCase(calendar=_calendar())
        result = use_case.execute(
            source_family="foreign_flow_snapshots",
            effective_session=_decision_session(),
            observed_through=rows[0].date,
        )

        assert result.status is SourceAvailabilityStatus.INVALID
        assert result.is_authoritative is False
