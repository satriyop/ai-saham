"""
DQ-002G — planted future-row temporal leakage tests: market_context_snapshots,
regime_observations, sentiment.

Uses real SQLite repository code (not mocks) against tmp_path databases.

- market_context_snapshots / regime_observations: `get(as_of_date)` is an
  exact-match query keyed by date, so a planted future-dated row cannot leak
  into a query for the correct decision date by construction. This is
  proven directly. `MarketContextEngine._compute_stability` — the one real
  production consumer of the unbounded `get_recent()` — is exercised
  directly to prove its existing `if obs.observation_date >= as_of: continue`
  guard excludes a planted future regime observation from stability
  computation (a pre-existing guard, locked in here, not code added by this
  task).
- sentiment: proven diagnostic-only against a real, perfectly-current
  sentiment_logs row (not a hand-built input), per the DQ-002F guard.

Layer: Application (tests only) / Infrastructure (real repositories under test)
"""

from __future__ import annotations

from datetime import date, datetime

from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from src.application.services.market_context_engine import MarketContextEngine
from src.application.use_case.assess_source_availability_use_case import (
    AssessSourceAvailabilityUseCase,
)
from src.domain.ports.sentiment_repository import SentimentLog
from src.domain.services.trading_session_calendar import KnownTradingSessionCalendar
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.market_context import MarketContext, MarketRegime
from src.domain.value_objects.regime_detection_evidence import (
    RegimeDetectionEvidence,
    RegimeStability,
)
from src.domain.value_objects.sentiment import CatalystType, Sentiment
from src.domain.value_objects.source_availability import SourceAvailabilityStatus
from src.infrastructure.persistence.sentiment_repository import SQLiteSentimentRepository
from src.infrastructure.persistence.sqlite_market_context_repository import (
    SQLiteMarketContextRepository,
)
from src.infrastructure.persistence.sqlite_regime_observation_repository import (
    SQLiteRegimeObservationRepository,
)

DECISION_DATE = date(2026, 7, 16)
FUTURE_DATE = date(2026, 7, 17)


def _calendar() -> KnownTradingSessionCalendar:
    """DQ-002I: market_context_snapshots, regime_observations, and sentiment
    are all FETCH_TIMESTAMP/DIAGNOSTIC_ONLY, so the calendar is structurally
    required but never actually queried here."""
    return KnownTradingSessionCalendar(
        sessions=(), coverage_start=date(2026, 1, 1), coverage_end=date(2026, 12, 31)
    )


def _decision_session() -> EffectiveMarketSession:
    decision_at = datetime(2026, 7, 16, 16, 0, tzinfo=IDX_TIMEZONE)
    return EffectiveMarketSession(
        run_at=decision_at,
        decision_at=decision_at,
        latest_completed_session=DECISION_DATE,
        analysis_as_of=DECISION_DATE,
        market_session_name="AFTER_CLOSE",
        is_eod_pending=False,
        resolution_source="test_fixture",
        notes=(),
    )


def _context(on: date) -> MarketContext:
    return MarketContext(
        regime=MarketRegime.NEUTRAL,
        conviction=0.5,
        factors=(),
        signal_multiplier=1.0,
        gate_tightening=False,
        as_of_date=on,
    )


def _evidence(on: date, regime: str = "RISK_ON") -> RegimeDetectionEvidence:
    return RegimeDetectionEvidence(
        observation_date=on,
        schema_version=1,
        regime=regime,
        regime_score=0.75,
        regime_confidence=0.8,
        regime_stability=RegimeStability.STABLE,
        days_in_regime=5,
        transition_warning=None,
        ihsg_20d_return=0.02,
        ihsg_trend_structure="ABOVE_BOTH",
        ihsg_breadth_pct_above_ma=65.0,
        ihsg_volume_trend=1.1,
        ihsg_atr_pct=0.8,
        idx_foreign_flow_5d=1_000_000_000.0,
        idx_foreign_flow_20d=5_000_000_000.0,
        foreign_buy_streak=3,
        foreign_sell_streak=0,
        banking_sector_vs_ihsg=0.5,
        sector_breadth=65.0,
    )


class TestMarketContextSnapshotsTemporalLeakage:
    def test_market_context_get_is_keyed_by_exact_as_of_date_not_leaked_by_future_row(
        self, tmp_path
    ):
        repo = SQLiteMarketContextRepository(tmp_path / "context.db")
        repo.save(_context(DECISION_DATE))
        repo.save(_context(FUTURE_DATE))

        result = repo.get(DECISION_DATE)

        assert result is not None
        assert result.as_of_date == DECISION_DATE

    def test_market_context_snapshots_future_available_at_is_invalid(self):
        use_case = AssessSourceAvailabilityUseCase(calendar=_calendar())
        result = use_case.execute(
            source_family="market_context_snapshots",
            effective_session=_decision_session(),
            available_at=datetime(2026, 7, 17, tzinfo=IDX_TIMEZONE),
        )

        assert result.status is SourceAvailabilityStatus.INVALID
        assert result.is_authoritative is False

    def test_market_context_snapshots_current_when_available_at_decision(self):
        use_case = AssessSourceAvailabilityUseCase(calendar=_calendar())
        result = use_case.execute(
            source_family="market_context_snapshots",
            effective_session=_decision_session(),
            available_at=datetime(2026, 7, 16, 16, 0, tzinfo=IDX_TIMEZONE),
        )

        assert result.status is SourceAvailabilityStatus.CURRENT
        assert result.is_authoritative is True


class TestRegimeObservationsTemporalLeakage:
    def test_regime_observation_get_is_keyed_by_exact_date_not_leaked_by_future_row(self, tmp_path):
        repo = SQLiteRegimeObservationRepository(tmp_path / "regime.db")
        repo.save(_evidence(DECISION_DATE))
        repo.save(_evidence(FUTURE_DATE))

        result = repo.get(DECISION_DATE)

        assert result is not None
        assert result.observation_date == DECISION_DATE

    def test_market_context_engine_stability_guard_excludes_future_regime_observation(
        self, tmp_path
    ):
        """Real production leakage guard: `_compute_stability`'s
        `if obs.observation_date >= as_of: continue` must exclude a planted
        future-dated regime observation from prior-streak computation."""
        repo = SQLiteRegimeObservationRepository(tmp_path / "regime.db")
        repo.save(_evidence(date(2026, 7, 14), regime="RISK_ON"))
        repo.save(_evidence(FUTURE_DATE, regime="RISK_OFF"))  # must never be "prior"

        engine = MarketContextEngine(market_repository=None, regime_observation_repository=repo)

        days_in_regime, stability = engine._compute_stability(DECISION_DATE, "RISK_ON")

        # Only the 2026-07-14 RISK_ON observation is a valid prior (strictly
        # before decision date); the future RISK_OFF row must not break the
        # streak or otherwise influence the result. A streak of 1 day is
        # below stable_min_days=5, so stability is TRANSITIONING — the point
        # of this test is that the streak is 1 (from the real prior row),
        # not 0 (which is what a leaked future row breaking the streak, or
        # being counted itself, would produce).
        assert days_in_regime == 1
        assert stability == RegimeStability.TRANSITIONING.value

    def test_regime_observations_future_available_at_is_invalid(self):
        use_case = AssessSourceAvailabilityUseCase(calendar=_calendar())
        result = use_case.execute(
            source_family="regime_observations",
            effective_session=_decision_session(),
            available_at=datetime(2026, 7, 17, tzinfo=IDX_TIMEZONE),
        )

        assert result.status is SourceAvailabilityStatus.INVALID
        assert result.is_authoritative is False


class TestSentimentIsDiagnosticOnlyEvenWhenCurrent:
    def test_sentiment_is_diagnostic_only_even_when_current(self, tmp_path):
        repo = SQLiteSentimentRepository(tmp_path / "sentiment.db")
        log_id = repo.save_log(
            SentimentLog(
                id=None,
                date=DECISION_DATE,
                ticker="BBCA",
                sentiment=Sentiment.POSITIVE,
                catalyst=CatalystType.EARNINGS,
                score=0.9,
            )
        )
        assert log_id > 0

        logs = repo.get_ticker_logs("BBCA", limit=8)
        assert len(logs) == 1
        assert logs[0].date == DECISION_DATE  # perfectly current row, real repo read

        use_case = AssessSourceAvailabilityUseCase(calendar=_calendar())
        result = use_case.execute(
            source_family="sentiment",
            effective_session=_decision_session(),
            observed_through=logs[0].date,
            available_at=datetime(2026, 7, 16, 16, 0, tzinfo=IDX_TIMEZONE),
        )

        assert result.status is SourceAvailabilityStatus.DIAGNOSTIC_ONLY
        assert result.is_authoritative is False
