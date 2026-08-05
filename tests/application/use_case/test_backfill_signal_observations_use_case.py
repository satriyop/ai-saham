"""Unit tests for BackfillSignalObservationsUseCase (PIT membership + policy)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.application.services.lean_observation_identity import (
    LeanObservationIdentity,
)
from src.application.use_case.backfill_signal_observations_use_case import (
    BackfillSignalObservationsRequest,
    BackfillSignalObservationsUseCase,
    survivorship_limitation_for_source,
)
from src.domain.entities.candle import Candle
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.signal_artifact_identity import SemanticCompatibilityId
from src.domain.value_objects.signal_semantic_contract import (
    ACCUMULATION_DISCOVERY_CONTRACT,
)


def _candle(ticker: str, on: date) -> Candle:
    price = Decimal("100")
    return Candle(
        ticker=ticker,
        date=on,
        open=price,
        high=price,
        low=price,
        close=price,
        volume=1000,
    )


def _sessions(start: date, count: int) -> list[date]:
    days: list[date] = []
    current = start
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


class FakeMarketRepository(MarketDataRepository):
    def __init__(self, candles: dict[str, list[Candle]]) -> None:
        self._candles = candles

    def save_candles(self, candles: list[Candle]) -> None:
        raise NotImplementedError

    def get_candles(self, ticker, start_date=None, end_date=None):
        rows = list(self._candles.get(ticker, []))
        if start_date is not None:
            rows = [c for c in rows if c.date >= start_date]
        if end_date is not None:
            rows = [c for c in rows if c.date <= end_date]
        return sorted(rows, key=lambda c: c.date)

    def has_data(self, ticker, start_date, end_date) -> bool:
        return bool(self.get_candles(ticker, start_date, end_date))

    def get_date_range(self, ticker: str):
        rows = self.get_candles(ticker)
        if not rows:
            return None
        return rows[0].date, rows[-1].date

    def list_tickers_with_candles_between(self, start_date, end_date):
        found: set[str] = set()
        for ticker, rows in self._candles.items():
            if any(start_date <= c.date <= end_date for c in rows):
                found.add(ticker)
        return sorted(found)


@dataclass
class _FakeScreenResponse:
    observation_candidates: list = field(default_factory=list)
    candidates: list = field(default_factory=list)
    total_tickers_checked: int = 0


class _FakeCandidate:
    def __init__(self, ticker: str) -> None:
        self.ticker = ticker


class _FakeObservationCandidate:
    def __init__(self, ticker: str) -> None:
        self.candidate = _FakeCandidate(ticker)


class RecordingRecordUseCase:
    def __init__(self) -> None:
        self.screen_calls: list[dict] = []
        self.persist_calls: list[dict] = []

    def screen(self, screen_request, execution_context=None):
        tickers = list(screen_request.tickers)
        self.screen_calls.append({"tickers": tickers, "as_of": screen_request.as_of_date})
        obs = [_FakeObservationCandidate(t) for t in tickers]
        return _FakeScreenResponse(
            observation_candidates=obs,
            candidates=obs,
            total_tickers_checked=len(tickers),
        )

    def persist_multi_window(
        self,
        *,
        window_results,
        snapshot_date,
        execution_context,
        universe_tickers,
        population_binding,
        canonical_window,
    ) -> int:
        self.persist_calls.append(
            {
                "snapshot_date": snapshot_date,
                "universe_tickers": list(universe_tickers),
                "population_binding": population_binding,
            }
        )
        # one saved row per unique ticker in universe for this date
        return len(set(universe_tickers))


class StubRequestBuilder:
    def build(self, *, tickers, window_days, as_of_date, market_context=None):
        return SimpleNamespace(
            tickers=list(tickers),
            window_days=window_days,
            as_of_date=as_of_date,
            market_context=market_context,
        )


def _identity() -> LeanObservationIdentity:
    """Backfill treats the cohort tag as an opaque pass-through value.

    A literal stands in for the ADR-068 resolved cohort id on purpose: this use
    case never derives, recomputes, or inspects identity, so binding the test to
    the real resolver would couple it to a mechanism it does not own (and pay for
    a probe run per test).
    """
    return LeanObservationIdentity(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        semantic_compatibility_id=SemanticCompatibilityId("sha256:" + "cd" * 32),
    )


def _make_use_case(
    *,
    market: MarketDataRepository,
    membership_resolver,
    pit_window_sessions: int = 10,
    record: RecordingRecordUseCase | None = None,
    named_universe_tickers: list[str] | None = None,
) -> tuple[BackfillSignalObservationsUseCase, RecordingRecordUseCase]:
    record = record or RecordingRecordUseCase()
    uc = BackfillSignalObservationsUseCase(
        record_observations_use_case=record,  # type: ignore[arg-type]
        screen_request_builder=StubRequestBuilder(),  # type: ignore[arg-type]
        market_data_repository=market,
        observation_identity=_identity(),
        membership_resolver=membership_resolver,
        pit_window_sessions=pit_window_sessions,
        # Synthetic membership in tests must remain a subset of this roster.
        named_universe_tickers=named_universe_tickers
        or ["A", "B", "ASII", "BBCA", "BBRI", "BMRI", "MISS", "OK", "TLKM"],
        producer_source_revision="ai-saham@test+git:deadbeef",
        evaluate_market_context=None,
        session_resolver=MagicMock(
            resolve=lambda run_at: SimpleNamespace(
                latest_completed_session=run_at.date(),
                analysis_as_of=run_at.date(),
                decision_at=run_at,
            )
        ),
        evidence_context_builder=None,
    )
    return uc, record


class TestSurvivorshipLimitationPolicy:
    def test_current_broad_note(self):
        note = survivorship_limitation_for_source("lq45@current", pit_window_sessions=10)
        assert note is not None
        assert "survivorship-biased" in note

    def test_pit_named_narrowed(self):
        note = survivorship_limitation_for_source("lq45@pit", pit_window_sessions=10)
        assert note is not None
        assert "Tradable-universe PIT" in note
        assert "10" in note
        assert "lq45" in note
        assert "survivorship-biased" not in note

    def test_pit_cached_board_narrowed(self):
        note = survivorship_limitation_for_source("cached@pit", pit_window_sessions=7)
        assert note is not None
        assert "Board-wide tradable-universe PIT" in note
        assert "7" in note

    def test_unknown_suffix_none(self):
        assert survivorship_limitation_for_source("lq45", pit_window_sessions=10) is None


class TestBackfillPerDateMembership:
    def test_resolver_called_per_trading_date(self):
        sessions = _sessions(date(2026, 7, 6), 3)
        market = FakeMarketRepository(
            {
                "IHSG": [_candle("IHSG", d) for d in sessions],
                "BBCA": [_candle("BBCA", d) for d in sessions],
            }
        )
        calls: list[date] = []

        def resolver(as_of: date):
            calls.append(as_of)
            return ("BBCA",)

        uc, record = _make_use_case(market=market, membership_resolver=resolver)
        response = uc.execute(
            BackfillSignalObservationsRequest(
                start_date=sessions[0],
                end_date=sessions[-1],
                windows=(7,),
                universe_membership_source="lq45@pit",
            )
        )
        assert calls == list(sessions)
        assert response.processed_date_count == 3
        assert response.universe_membership_source == "lq45@pit"
        assert response.survivorship_limitation is not None
        assert "Tradable-universe PIT" in response.survivorship_limitation
        assert len(record.persist_calls) == 3

    def test_membership_differs_by_date(self):
        sessions = _sessions(date(2026, 7, 6), 2)
        market = FakeMarketRepository(
            {
                "IHSG": [_candle("IHSG", d) for d in sessions],
                "A": [_candle("A", d) for d in sessions],
                "B": [_candle("B", d) for d in sessions],
            }
        )

        def resolver(as_of: date):
            if as_of == sessions[0]:
                return ("A",)
            return ("A", "B")

        uc, record = _make_use_case(market=market, membership_resolver=resolver)
        response = uc.execute(
            BackfillSignalObservationsRequest(
                start_date=sessions[0],
                end_date=sessions[-1],
                windows=(7,),
                universe_membership_source="cached@pit",
            )
        )
        assert record.persist_calls[0]["universe_tickers"] == ["A"]
        assert record.persist_calls[1]["universe_tickers"] == ["A", "B"]
        assert response.universe_size == 2  # union

    def test_empty_membership_skips_with_reason(self):
        sessions = _sessions(date(2026, 7, 6), 2)
        market = FakeMarketRepository({"IHSG": [_candle("IHSG", d) for d in sessions]})
        uc, record = _make_use_case(
            market=market,
            membership_resolver=lambda as_of: (),
        )
        response = uc.execute(
            BackfillSignalObservationsRequest(
                start_date=sessions[0],
                end_date=sessions[-1],
                windows=(7,),
                universe_membership_source="lq45@pit",
            )
        )
        assert response.processed_date_count == 0
        assert response.universe_size == 0
        assert all(s.reason == "empty_pit_membership" for s in response.skipped_dates)
        assert record.persist_calls == []
        # limitation still set for @pit even when nothing processed
        assert response.survivorship_limitation is not None

    def test_no_ihsg_calendar_zero_dates_with_note(self):
        market = FakeMarketRepository({})
        uc, _ = _make_use_case(
            market=market,
            membership_resolver=lambda as_of: ("BBCA",),
        )
        response = uc.execute(
            BackfillSignalObservationsRequest(
                start_date=date(2026, 7, 6),
                end_date=date(2026, 7, 10),
                windows=(7,),
                universe_membership_source="lq45@pit",
            )
        )
        assert response.requested_date_count == 0
        assert response.processed_date_count == 0
        assert "ihsg_calendar_unavailable" in response.notes

    def test_exclusions_use_that_date_membership_only(self):
        sessions = _sessions(date(2026, 7, 6), 1)
        market = FakeMarketRepository(
            {
                "IHSG": [_candle("IHSG", d) for d in sessions],
                "OK": [_candle("OK", d) for d in sessions],
                # MISS is in membership but has no candle on the session
            }
        )

        class PartialRecord(RecordingRecordUseCase):
            def screen(self, screen_request, execution_context=None):
                # only evaluate OK
                self.screen_calls.append(
                    {"tickers": list(screen_request.tickers), "as_of": screen_request.as_of_date}
                )
                obs = [_FakeObservationCandidate("OK")]
                return _FakeScreenResponse(
                    observation_candidates=obs,
                    candidates=obs,
                    total_tickers_checked=len(screen_request.tickers),
                )

        record = PartialRecord()
        uc, _ = _make_use_case(
            market=market,
            membership_resolver=lambda as_of: ("OK", "MISS"),
            record=record,
        )
        # MISS has no candle → _has_any_ticker_candle still true because OK has one
        response = uc.execute(
            BackfillSignalObservationsRequest(
                start_date=sessions[0],
                end_date=sessions[0],
                windows=(7,),
                universe_membership_source="lq45@pit",
            )
        )
        assert response.processed_date_count == 1
        excluded = {(e.ticker, e.reason) for e in response.ticker_exclusions}
        assert ("MISS", "source_unavailable_not_evaluated") in excluded
        assert "OK" not in {e.ticker for e in response.ticker_exclusions}

    def test_current_policy_regression(self):
        sessions = _sessions(date(2026, 7, 6), 1)
        market = FakeMarketRepository(
            {
                "IHSG": [_candle("IHSG", d) for d in sessions],
                "BBCA": [_candle("BBCA", d) for d in sessions],
            }
        )
        uc, _ = _make_use_case(
            market=market,
            membership_resolver=lambda as_of: ("BBCA",),
        )
        response = uc.execute(
            BackfillSignalObservationsRequest(
                start_date=sessions[0],
                end_date=sessions[0],
                windows=(7,),
                universe_membership_source="lq45@current",
            )
        )
        assert response.survivorship_limitation is not None
        assert "survivorship-biased" in response.survivorship_limitation


class TestPitWindowValidation:
    def test_invalid_window_raises(self):
        with pytest.raises(ValueError):
            BackfillSignalObservationsUseCase(
                record_observations_use_case=MagicMock(),
                screen_request_builder=MagicMock(),
                market_data_repository=FakeMarketRepository({}),
                observation_identity=_identity(),
                membership_resolver=lambda d: (),
                pit_window_sessions=0,
                named_universe_tickers=["BBCA"],
                producer_source_revision="ai-saham@test",
            )

    def test_unsupported_population_name_rejected_at_construction(self):
        """--universe idx30 must fail before any session loop/persist."""
        with pytest.raises(ValueError, match="unsupported population_name=.idx30"):
            BackfillSignalObservationsUseCase(
                record_observations_use_case=MagicMock(),
                screen_request_builder=MagicMock(),
                market_data_repository=FakeMarketRepository({}),
                observation_identity=_identity(),
                membership_resolver=lambda d: ("BBCA",),
                pit_window_sessions=10,
                named_universe_tickers=["BBCA", "BBRI"],
                producer_source_revision="ai-saham@test",
                population_name="idx30",
            )

    def test_lq45_population_name_accepted_at_construction(self):
        uc, _ = _make_use_case(
            market=FakeMarketRepository({}),
            membership_resolver=lambda d: ("BBCA",),
        )
        assert uc is not None
