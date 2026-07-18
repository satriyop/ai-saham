"""Tests for DailyBriefingUseCase."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from src.application.dto.accumulation_screen import AccumulationCandidate
from src.application.services.indicator_registry import IndicatorRegistry
from src.application.services.signal_engine import SignalEngine
from src.application.services.signal_engine_config import SignalEngineConfig
from src.application.use_case.accumulation_screen_use_case import AccumulationScreenUseCase
from src.application.use_case.daily_briefing_use_case import (
    DailyBriefingRequest,
    DailyBriefingUseCase,
)
from tests.application.use_case.accumulation_screen_fixtures import (
    FakeRulesLoader,
    MockBrokerRepository,
    MockMarketRepository,
    SpyCandidateObservationsRepository,
    _candle,
    _summary,
    _weekdays,
)


def test_daily_briefing_rolls_back_weekends():
    market_repo = MagicMock()
    market_repo.get_date_range.return_value = None
    # No cached IHSG benchmark data: the effective-session resolver falls
    # back to weekday-only logic, matching the pre-resolver behavior.
    market_repo.get_candles.return_value = []

    broker_repo = MagicMock()
    broker_repo.get_date_range.return_value = None

    regime_uc = MagicMock()
    regime_uc.execute.return_value = None

    accum_uc = MagicMock()
    accum_uc.execute.return_value = MagicMock(candidates=[])

    use_case = DailyBriefingUseCase(
        market_repository=market_repo,
        broker_repository=broker_repo,
        regime_use_case=regime_uc,
        accumulation_use_case=accum_uc,
        universe_loader=MagicMock(),
    )

    # Mocking date.today() via patch of daily_briefing's imported date class
    with patch("src.application.use_case.daily_briefing_use_case.date") as mock_date:
        # Saturday, June 20, 2026
        mock_date.today.return_value = date(2026, 6, 20)
        # Ensure side_effect allows creating new date instances in the code
        mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)

        response = use_case.execute(DailyBriefingRequest(as_of_date=None))
        # Should roll back Saturday to Friday, June 19, 2026
        assert response.live_session_date == date(2026, 6, 19)
        assert response.is_historical is False

        # Sunday, June 21, 2026
        mock_date.today.return_value = date(2026, 6, 21)
        response = use_case.execute(DailyBriefingRequest(as_of_date=None))
        # Should roll back Sunday to Friday, June 19, 2026
        assert response.live_session_date == date(2026, 6, 19)
        assert response.is_historical is False


def test_daily_briefing_weekend_prefers_cached_ihsg_session_over_blind_friday():
    """DQ-002A: the effective-session resolver uses the cached IHSG benchmark
    session for weekend rollback instead of blindly assuming Friday — this
    also correctly reflects a Friday holiday when the cache proves it."""
    market_repo = MagicMock()
    market_repo.get_date_range.return_value = None
    # IHSG cache stops at Thursday 2026-06-18: Friday 2026-06-19 was a holiday.
    market_repo.get_candles.return_value = [
        MagicMock(date=date(2026, 6, 17)),
        MagicMock(date=date(2026, 6, 18)),
    ]

    broker_repo = MagicMock()
    broker_repo.get_date_range.return_value = None

    regime_uc = MagicMock()
    accum_uc = MagicMock()
    accum_uc.execute.return_value = MagicMock(candidates=[])

    use_case = DailyBriefingUseCase(
        market_repository=market_repo,
        broker_repository=broker_repo,
        regime_use_case=regime_uc,
        accumulation_use_case=accum_uc,
        universe_loader=MagicMock(),
    )

    with patch("src.application.use_case.daily_briefing_use_case.date") as mock_date:
        mock_date.today.return_value = date(2026, 6, 20)  # Saturday
        mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)

        response = use_case.execute(DailyBriefingRequest(as_of_date=None))

    # Not blindly Friday (2026-06-19) — the holiday-aware cache says Thursday.
    assert response.live_session_date == date(2026, 6, 18)


def test_daily_briefing_normal_trading_day_date_unaffected_by_resolver_integration():
    """Compatibility: on a normal (non-weekend) live trading day, the
    live_session_date is still `date.today()`, unaffected by the new
    effective-session resolver call (only the weekend branch overrides it)."""
    market_repo = MagicMock()
    market_repo.get_date_range.return_value = None
    market_repo.get_candles.return_value = [MagicMock(date=date(2026, 6, 18))]

    broker_repo = MagicMock()
    broker_repo.get_date_range.return_value = None

    regime_uc = MagicMock()
    accum_uc = MagicMock()
    accum_uc.execute.return_value = MagicMock(candidates=[])

    use_case = DailyBriefingUseCase(
        market_repository=market_repo,
        broker_repository=broker_repo,
        regime_use_case=regime_uc,
        accumulation_use_case=accum_uc,
        universe_loader=MagicMock(),
    )

    with patch("src.application.use_case.daily_briefing_use_case.date") as mock_date:
        mock_date.today.return_value = date(2026, 6, 19)  # Friday, a live trading day
        mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)

        response = use_case.execute(DailyBriefingRequest(as_of_date=None))

    assert response.live_session_date == date(2026, 6, 19)
    assert response.is_historical is False


def test_daily_briefing_explicit_as_of_date_uses_deterministic_after_close_decision():
    """DQ-002B: historical mode must resolve a deterministic after-market-close
    WIB decision timestamp for the requested date, not midnight/live wall-clock."""
    from src.domain.value_objects.idx_market import IDX_TIMEZONE, MARKET_CLOSE

    market_repo = MagicMock()
    broker_repo = MagicMock()
    broker_repo.get_date_range.return_value = None
    regime_uc = MagicMock()
    accum_uc = MagicMock()
    accum_uc.execute.return_value = MagicMock(candidates=[])

    fake_resolver = MagicMock()
    fake_resolver.resolve.return_value = MagicMock(
        latest_completed_session=date(2026, 6, 19),
        is_eod_pending=False,
        market_session_name="AFTER_CLOSE",
    )

    use_case = DailyBriefingUseCase(
        market_repository=market_repo,
        broker_repository=broker_repo,
        regime_use_case=regime_uc,
        accumulation_use_case=accum_uc,
        universe_loader=MagicMock(),
        session_resolver=fake_resolver,
    )

    use_case.execute(DailyBriefingRequest(as_of_date=date(2026, 6, 19)))

    fake_resolver.resolve.assert_called_once()
    called_run_at = fake_resolver.resolve.call_args.kwargs["run_at"]
    assert called_run_at == datetime.combine(
        date(2026, 6, 19), MARKET_CLOSE, tzinfo=IDX_TIMEZONE
    )


def test_daily_briefing_resolves_session_once_per_execute_not_per_ticker(monkeypatch):
    """DQ-002B: the effective session must be resolved once per execute(),
    shared across every ticker's freshness computation — never once per
    ticker or once per window."""
    tickers = [f"T{i}" for i in range(10)]
    monkeypatch.setattr(
        "src.application.use_case.daily_briefing_use_case.load_universe",
        lambda *a, **kw: tickers,
    )

    market_repo = MagicMock()
    market_repo.get_date_range.return_value = (date(2026, 6, 1), date(2026, 6, 19))
    broker_repo = MagicMock()
    broker_repo.get_date_range.return_value = (date(2026, 6, 1), date(2026, 6, 19))
    regime_uc = MagicMock()
    accum_uc = MagicMock()
    accum_uc.execute.return_value = MagicMock(candidates=[])

    fake_resolver = MagicMock()
    fake_resolver.resolve.return_value = MagicMock(
        latest_completed_session=date(2026, 6, 19),
        is_eod_pending=False,
        market_session_name="AFTER_CLOSE",
    )

    use_case = DailyBriefingUseCase(
        market_repository=market_repo,
        broker_repository=broker_repo,
        regime_use_case=regime_uc,
        accumulation_use_case=accum_uc,
        universe_loader=MagicMock(),
        session_resolver=fake_resolver,
    )

    use_case.execute(
        DailyBriefingRequest(universe="lq45", as_of_date=date(2026, 6, 19))
    )

    fake_resolver.resolve.assert_called_once()


def test_daily_briefing_writes_zero_candidate_observations(monkeypatch):
    """S1 regression: DailyBriefingUseCase calls AccumulationScreenUseCase.execute()
    directly, which is read-only — it must never persist observations even with
    a real screen use case wired to a live observations repository."""
    from src.application.use_case import daily_briefing_use_case as module

    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100")) for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]
    spy_repo = SpyCandidateObservationsRepository()

    real_accum_uc = AccumulationScreenUseCase(
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
        candidate_observations_repository=spy_repo,
        signal_engine=SignalEngine(config=SignalEngineConfig()),
    )

    monkeypatch.setattr(module, "load_universe", lambda *a, **kw: ["BBCA"])

    market_repo = MagicMock()
    market_repo.get_candles.return_value = []
    market_repo.get_date_range.return_value = (as_of, as_of)
    broker_repo = MagicMock()
    broker_repo.get_date_range.return_value = (as_of, as_of)
    regime_uc = MagicMock()
    regime_uc.evaluate.return_value = None

    use_case = DailyBriefingUseCase(
        market_repository=market_repo,
        broker_repository=broker_repo,
        regime_use_case=regime_uc,
        accumulation_use_case=real_accum_uc,
        universe_loader=MagicMock(),
    )

    use_case.execute(DailyBriefingRequest(universe="lq45", as_of_date=as_of))

    assert spy_repo.saved == []


def test_daily_briefing_historical_mode(monkeypatch):
    market_repo = MagicMock()
    market_repo.get_candles.return_value = []
    market_repo.get_date_range.return_value = (date(2026, 6, 1), date(2026, 6, 19))

    broker_repo = MagicMock()
    broker_repo.get_date_range.return_value = (date(2026, 6, 1), date(2026, 6, 19))

    regime_uc = MagicMock()
    accum_uc = MagicMock()
    accum_uc.execute.return_value = MagicMock(candidates=[])

    monkeypatch.setattr(
        "src.application.use_case.daily_briefing_use_case.load_universe",
        lambda *a, **kw: ["BBCA"],
    )

    use_case = DailyBriefingUseCase(
        market_repository=market_repo,
        broker_repository=broker_repo,
        regime_use_case=regime_uc,
        accumulation_use_case=accum_uc,
        universe_loader=MagicMock(),
    )

    response = use_case.execute(
        DailyBriefingRequest(universe="lq45", as_of_date=date(2026, 6, 19))
    )

    assert response.is_historical is True
    assert response.live_session_date == date(2026, 6, 19)
    assert response.latest_completed_eod_date == date(2026, 6, 19)


def test_daily_briefing_shared_freshness(monkeypatch):
    # June 19, 2026 is Friday. If expected latest EOD is 2026-06-19,
    # but candle_as_of is 2026-06-18 (older/stale).
    market_repo = MagicMock()
    market_repo.get_candles.return_value = []
    market_repo.get_date_range.return_value = (date(2026, 6, 1), date(2026, 6, 18))

    broker_repo = MagicMock()
    broker_repo.get_date_range.return_value = (date(2026, 6, 1), date(2026, 6, 19))

    regime_uc = MagicMock()
    accum_uc = MagicMock()
    accum_uc.execute.return_value = MagicMock(candidates=[])

    monkeypatch.setattr(
        "src.application.use_case.daily_briefing_use_case.load_universe",
        lambda *a, **kw: ["BBCA"],
    )

    use_case = DailyBriefingUseCase(
        market_repository=market_repo,
        broker_repository=broker_repo,
        regime_use_case=regime_uc,
        accumulation_use_case=accum_uc,
        universe_loader=MagicMock(),
    )

    response = use_case.execute(
        DailyBriefingRequest(universe="lq45", as_of_date=date(2026, 6, 19))
    )

    assert len(response.data_freshness) == 1
    assert response.data_freshness[0].freshness.candle_state.value == "STALE"
    assert response.stale_count == 1


def test_daily_briefing_opening_snapshot(tmp_path, monkeypatch):
    import json
    opening_dir = tmp_path / "opening"
    date_dir = opening_dir / "20260619"
    date_dir.mkdir(parents=True)

    snapshot_file = date_dir / "snapshot.json"
    snapshot_data = {
        "captured_at": "2026-06-19T09:05:00+07:00",
        "candidates": [
            {"ticker": "BBCA", "opening_setup": "PRIME", "iev": 10000, "iep": 10050, "trend": "UP"}
        ]
    }
    snapshot_file.write_text(json.dumps(snapshot_data))

    market_repo = MagicMock()
    market_repo.get_candles.return_value = []
    market_repo.get_date_range.return_value = None
    broker_repo = MagicMock()
    broker_repo.get_date_range.return_value = None

    regime_uc = MagicMock()
    accum_uc = MagicMock()
    accum_uc.execute.return_value = MagicMock(candidates=[])

    monkeypatch.setattr(
        "src.application.use_case.daily_briefing_use_case.load_universe",
        lambda *a, **kw: ["BBCA"],
    )

    use_case = DailyBriefingUseCase(
        market_repository=market_repo,
        broker_repository=broker_repo,
        regime_use_case=regime_uc,
        accumulation_use_case=accum_uc,
        universe_loader=MagicMock(),
    )

    response = use_case.execute(
        DailyBriefingRequest(
            universe="lq45",
            as_of_date=date(2026, 6, 19),
            opening_data_dir=opening_dir,
        )
    )

    assert response.opening_snapshot_date == date(2026, 6, 19)
    assert len(response.opening_candidates) == 1
    assert response.opening_candidates[0].ticker == "BBCA"


def test_daily_briefing_not_ready_when_candle_coverage_below_policy(monkeypatch):
    tickers = [f"T{i}" for i in range(45)]
    monkeypatch.setattr(
        "src.application.use_case.daily_briefing_use_case.load_universe",
        lambda *a, **kw: tickers,
    )

    current_tickers = [f"T{i}" for i in range(4)]
    market_repo = MagicMock()
    market_repo.get_candles.return_value = []
    def market_side_effect(ticker):
        if ticker in current_tickers:
            return (date(2026, 6, 1), date(2026, 6, 19))
        return (date(2026, 6, 1), date(2026, 6, 18))
    market_repo.get_date_range.side_effect = market_side_effect

    broker_repo = MagicMock()
    broker_repo.get_date_range.return_value = (date(2026, 6, 1), date(2026, 6, 19))

    regime_uc = MagicMock()
    accum_uc = MagicMock()
    accum_uc.execute.return_value = MagicMock(candidates=[])

    use_case = DailyBriefingUseCase(
        market_repository=market_repo,
        broker_repository=broker_repo,
        regime_use_case=regime_uc,
        accumulation_use_case=accum_uc,
        universe_loader=MagicMock(),
    )

    response = use_case.execute(
        DailyBriefingRequest(universe="lq45", as_of_date=date(2026, 6, 19))
    )

    candles_readiness = next(item for item in response.readiness_items if item.dataset == "candles")
    assert candles_readiness.status == "NOT_READY"
    assert response.overall_authority == "NOT_READY"
    assert response.accumulation_candidates == []
    accum_uc.execute.assert_not_called()


def test_daily_briefing_suppresses_accumulation_when_broker_coverage_below_policy(monkeypatch):
    tickers = [f"T{i}" for i in range(45)]
    monkeypatch.setattr(
        "src.application.use_case.daily_briefing_use_case.load_universe",
        lambda *a, **kw: tickers,
    )

    market_repo = MagicMock()
    market_repo.get_candles.return_value = []
    market_repo.get_date_range.return_value = (date(2026, 6, 1), date(2026, 6, 19))

    current_tickers = [f"T{i}" for i in range(4)]
    broker_repo = MagicMock()
    def broker_side_effect(ticker):
        if ticker in current_tickers:
            return (date(2026, 6, 1), date(2026, 6, 19))
        return (date(2026, 6, 1), date(2026, 6, 18))
    broker_repo.get_date_range.side_effect = broker_side_effect

    regime_uc = MagicMock()
    accum_uc = MagicMock()
    accum_uc.execute.return_value = MagicMock(candidates=[])

    use_case = DailyBriefingUseCase(
        market_repository=market_repo,
        broker_repository=broker_repo,
        regime_use_case=regime_uc,
        accumulation_use_case=accum_uc,
        universe_loader=MagicMock(),
    )

    response = use_case.execute(
        DailyBriefingRequest(universe="lq45", as_of_date=date(2026, 6, 19))
    )

    broker_readiness = next(
        item for item in response.readiness_items if item.dataset == "broker_flow"
    )
    assert broker_readiness.status == "NOT_READY"
    assert response.overall_authority == "NOT_READY"
    assert response.accumulation_candidates == []
    accum_uc.execute.assert_not_called()


def test_daily_briefing_partial_allows_accumulation_with_warning(monkeypatch):
    tickers = [f"T{i}" for i in range(10)]
    monkeypatch.setattr(
        "src.application.use_case.daily_briefing_use_case.load_universe",
        lambda *a, **kw: tickers,
    )

    current_tickers = [f"T{i}" for i in range(8)]

    market_repo = MagicMock()
    market_repo.get_candles.return_value = []
    def market_side_effect(ticker):
        if ticker in current_tickers:
            return (date(2026, 6, 1), date(2026, 6, 19))
        return (date(2026, 6, 1), date(2026, 6, 18))
    market_repo.get_date_range.side_effect = market_side_effect

    broker_repo = MagicMock()
    def broker_side_effect(ticker):
        if ticker in current_tickers:
            return (date(2026, 6, 1), date(2026, 6, 19))
        return (date(2026, 6, 1), date(2026, 6, 18))
    broker_repo.get_date_range.side_effect = broker_side_effect

    regime_uc = MagicMock()
    accum_uc = MagicMock()
    fake_candidate = MagicMock()
    accum_uc.execute.return_value = MagicMock(candidates=[fake_candidate])

    use_case = DailyBriefingUseCase(
        market_repository=market_repo,
        broker_repository=broker_repo,
        regime_use_case=regime_uc,
        accumulation_use_case=accum_uc,
        universe_loader=MagicMock(),
    )

    response = use_case.execute(
        DailyBriefingRequest(universe="lq45", as_of_date=date(2026, 6, 19))
    )

    assert response.overall_authority == "PARTIAL"
    accum_uc.execute.assert_called_once()
    assert any("PARTIAL data readiness" in w for w in response.warnings)


def test_daily_briefing_ready_when_all_critical_sources_ready(tmp_path, monkeypatch):
    tickers = ["T1", "T2", "T3"]
    monkeypatch.setattr(
        "src.application.use_case.daily_briefing_use_case.load_universe",
        lambda *a, **kw: tickers,
    )

    market_repo = MagicMock()
    market_repo.get_candles.return_value = []
    market_repo.get_date_range.return_value = (date(2026, 6, 1), date(2026, 6, 19))

    broker_repo = MagicMock()
    broker_repo.get_date_range.return_value = (date(2026, 6, 1), date(2026, 6, 19))

    regime_uc = MagicMock()
    regime_uc.evaluate.return_value = MagicMock()

    import json
    opening_dir = tmp_path / "opening"
    date_dir = opening_dir / "20260619"
    date_dir.mkdir(parents=True)
    snapshot_file = date_dir / "snapshot.json"
    snapshot_data = {
        "captured_at": "2026-06-19T09:05:00+07:00",
        "candidates": [{"ticker": "T1", "opening_setup": "PRIME"}]
    }
    snapshot_file.write_text(json.dumps(snapshot_data))

    accum_uc = MagicMock()
    accum_uc.execute.return_value = MagicMock(candidates=[])

    use_case = DailyBriefingUseCase(
        market_repository=market_repo,
        broker_repository=broker_repo,
        regime_use_case=regime_uc,
        accumulation_use_case=accum_uc,
        universe_loader=MagicMock(),
    )

    response = use_case.execute(
        DailyBriefingRequest(
            universe="lq45",
            as_of_date=date(2026, 6, 19),
            opening_data_dir=opening_dir,
        )
    )

    candles_readiness = next(
        item for item in response.readiness_items if item.dataset == "candles"
    )
    broker_readiness = next(
        item for item in response.readiness_items if item.dataset == "broker_flow"
    )

    assert candles_readiness.status == "READY"
    assert broker_readiness.status == "READY"
    assert response.overall_authority == "READY"


def test_daily_briefing_splits_opening_snapshot_by_universe_scope(tmp_path, monkeypatch):
    import json
    opening_dir = tmp_path / "opening"
    date_dir = opening_dir / "20260619"
    date_dir.mkdir(parents=True)

    snapshot_file = date_dir / "snapshot.json"
    snapshot_data = {
        "captured_at": "2026-06-19T09:05:00+07:00",
        "candidates": [
            {"ticker": "a", "opening_setup": "PRIME"},
            {"ticker": "c", "opening_setup": "WATCH"}
        ]
    }
    snapshot_file.write_text(json.dumps(snapshot_data))

    market_repo = MagicMock()
    market_repo.get_candles.return_value = []
    market_repo.get_date_range.return_value = None
    broker_repo = MagicMock()
    broker_repo.get_date_range.return_value = None

    regime_uc = MagicMock()
    accum_uc = MagicMock()
    accum_uc.execute.return_value = MagicMock(candidates=[])

    monkeypatch.setattr(
        "src.application.use_case.daily_briefing_use_case.load_universe",
        lambda *a, **kw: ["A", "B"],
    )

    use_case = DailyBriefingUseCase(
        market_repository=market_repo,
        broker_repository=broker_repo,
        regime_use_case=regime_uc,
        accumulation_use_case=accum_uc,
        universe_loader=MagicMock(),
    )

    response = use_case.execute(
        DailyBriefingRequest(
            universe="lq45",
            as_of_date=date(2026, 6, 19),
            opening_data_dir=opening_dir,
        )
    )

    assert response.opening_snapshot_date == date(2026, 6, 19)
    assert len(response.opening_candidates) == 1
    assert response.opening_candidates[0].ticker == "A"
    assert response.opening_candidates[0].opening_setup == "PRIME"

    assert len(response.market_wide_opening_observations) == 1
    assert response.market_wide_opening_observations[0].ticker == "C"
    assert response.market_wide_opening_observations[0].opening_setup == "WATCH"


def test_daily_briefing_empty_universe_treats_opening_rows_as_market_wide(tmp_path, monkeypatch):
    import json
    opening_dir = tmp_path / "opening"
    date_dir = opening_dir / "20260619"
    date_dir.mkdir(parents=True)

    snapshot_file = date_dir / "snapshot.json"
    snapshot_data = {
        "captured_at": "2026-06-19T09:05:00+07:00",
        "candidates": [
            {"ticker": "A", "opening_setup": "PRIME"}
        ]
    }
    snapshot_file.write_text(json.dumps(snapshot_data))

    market_repo = MagicMock()
    market_repo.get_candles.return_value = []
    market_repo.get_date_range.return_value = None
    broker_repo = MagicMock()
    broker_repo.get_date_range.return_value = None

    regime_uc = MagicMock()
    accum_uc = MagicMock()
    accum_uc.execute.return_value = MagicMock(candidates=[])

    monkeypatch.setattr(
        "src.application.use_case.daily_briefing_use_case.load_universe",
        lambda *a, **kw: [],
    )

    use_case = DailyBriefingUseCase(
        market_repository=market_repo,
        broker_repository=broker_repo,
        regime_use_case=regime_uc,
        accumulation_use_case=accum_uc,
        universe_loader=MagicMock(),
    )

    response = use_case.execute(
        DailyBriefingRequest(
            universe="lq45",
            as_of_date=date(2026, 6, 19),
            opening_data_dir=opening_dir,
        )
    )

    assert response.opening_candidates == []
    assert len(response.market_wide_opening_observations) == 1
    assert response.market_wide_opening_observations[0].ticker == "A"


def _real_accumulation_candidate(ticker: str = "BBCA") -> AccumulationCandidate:
    return AccumulationCandidate(
        ticker=ticker,
        window_days=7,
        net_buy_days=5,
        total_days=7,
        net_buy_ratio=0.71,
        total_net_value=Decimal("1000000"),
        consecutive_streak=3,
        foreign_vwap=Decimal("10000"),
        current_price=Decimal("10050"),
        vwap_discount_pct=0.5,
        rsi=50.0,
        trend="UP",
        foreign_flow_score=60.6,
        top_brokers=None,
        institutional_flag=True,
    )


def test_daily_briefing_projects_accumulation_candidates(monkeypatch):
    tickers = ["T1", "T2", "T3"]
    monkeypatch.setattr(
        "src.application.use_case.daily_briefing_use_case.load_universe",
        lambda *a, **kw: tickers,
    )

    market_repo = MagicMock()
    market_repo.get_candles.return_value = []
    market_repo.get_date_range.return_value = (date(2026, 6, 1), date(2026, 6, 19))
    broker_repo = MagicMock()
    broker_repo.get_date_range.return_value = (date(2026, 6, 1), date(2026, 6, 19))

    regime_uc = MagicMock()
    accum_uc = MagicMock()
    fake_candidate = _real_accumulation_candidate("BBCA")
    accum_uc.execute.return_value = MagicMock(candidates=[fake_candidate])

    use_case = DailyBriefingUseCase(
        market_repository=market_repo,
        broker_repository=broker_repo,
        regime_use_case=regime_uc,
        accumulation_use_case=accum_uc,
        universe_loader=MagicMock(),
    )

    response = use_case.execute(
        DailyBriefingRequest(universe="lq45", as_of_date=date(2026, 6, 19))
    )

    assert response.accumulation_summary is not None
    assert response.accumulation_summary.checked == 3
    assert response.accumulation_summary.flow_candidates == 1
    assert response.accumulation_summary.unclassified_count == 1
    assert len(response.daily_accumulation_candidates) == 1
    assert response.daily_accumulation_candidates[0].ticker == "BBCA"
    assert response.daily_accumulation_candidates[0].flow_score == 60.6
    assert response.daily_accumulation_candidates[0].action is None


def test_daily_briefing_not_ready_skips_accumulation_projection_rows(monkeypatch):
    tickers = [f"T{i}" for i in range(45)]
    monkeypatch.setattr(
        "src.application.use_case.daily_briefing_use_case.load_universe",
        lambda *a, **kw: tickers,
    )

    current_tickers = [f"T{i}" for i in range(4)]
    market_repo = MagicMock()
    market_repo.get_candles.return_value = []

    def market_side_effect(ticker):
        if ticker in current_tickers:
            return (date(2026, 6, 1), date(2026, 6, 19))
        return (date(2026, 6, 1), date(2026, 6, 18))

    market_repo.get_date_range.side_effect = market_side_effect

    broker_repo = MagicMock()
    broker_repo.get_date_range.return_value = (date(2026, 6, 1), date(2026, 6, 19))

    regime_uc = MagicMock()
    accum_uc = MagicMock()
    accum_uc.execute.return_value = MagicMock(candidates=[])

    use_case = DailyBriefingUseCase(
        market_repository=market_repo,
        broker_repository=broker_repo,
        regime_use_case=regime_uc,
        accumulation_use_case=accum_uc,
        universe_loader=MagicMock(),
    )

    response = use_case.execute(
        DailyBriefingRequest(universe="lq45", as_of_date=date(2026, 6, 19))
    )

    assert response.overall_authority == "NOT_READY"
    assert response.daily_accumulation_candidates == []
    assert response.accumulation_summary is not None
    assert response.accumulation_summary.flow_candidates == 0
    assert response.accumulation_summary.checked == 45
    accum_uc.execute.assert_not_called()


def test_daily_briefing_passes_capped_candidates_to_setup_lens_impact(monkeypatch):
    tickers = ["T1", "T2", "T3"]
    monkeypatch.setattr(
        "src.application.use_case.daily_briefing_use_case.load_universe",
        lambda *a, **kw: tickers,
    )

    market_repo = MagicMock()
    market_repo.get_candles.return_value = []
    market_repo.get_date_range.return_value = (date(2026, 6, 1), date(2026, 6, 19))
    broker_repo = MagicMock()
    broker_repo.get_date_range.return_value = (date(2026, 6, 1), date(2026, 6, 19))

    regime_uc = MagicMock()
    accum_uc = MagicMock()
    fake_candidate = _real_accumulation_candidate("BBCA")
    accum_uc.execute.return_value = MagicMock(candidates=[fake_candidate])

    impact_uc = MagicMock()
    impact_uc.execute.return_value = MagicMock(rows=())

    use_case = DailyBriefingUseCase(
        market_repository=market_repo,
        broker_repository=broker_repo,
        regime_use_case=regime_uc,
        accumulation_use_case=accum_uc,
        universe_loader=MagicMock(),
        setup_lens_impact_use_case=impact_uc,
    )

    response = use_case.execute(
        DailyBriefingRequest(universe="lq45", top=1, as_of_date=date(2026, 6, 19))
    )

    impact_uc.execute.assert_called_once()
    passed_request = impact_uc.execute.call_args.args[0]
    # Only the already-selected daily accumulation candidates (capped by top) are passed.
    assert len(passed_request.candidates) == len(response.daily_accumulation_candidates)
    assert passed_request.candidates[0].ticker == "BBCA"
    assert response.setup_lens_impact is impact_uc.execute.return_value


def test_daily_briefing_not_ready_never_calls_setup_lens_impact(monkeypatch):
    tickers = [f"T{i}" for i in range(45)]
    monkeypatch.setattr(
        "src.application.use_case.daily_briefing_use_case.load_universe",
        lambda *a, **kw: tickers,
    )

    current_tickers = [f"T{i}" for i in range(4)]
    market_repo = MagicMock()
    market_repo.get_candles.return_value = []

    def market_side_effect(ticker):
        if ticker in current_tickers:
            return (date(2026, 6, 1), date(2026, 6, 19))
        return (date(2026, 6, 1), date(2026, 6, 18))

    market_repo.get_date_range.side_effect = market_side_effect

    broker_repo = MagicMock()
    broker_repo.get_date_range.return_value = (date(2026, 6, 1), date(2026, 6, 19))

    regime_uc = MagicMock()
    accum_uc = MagicMock()
    accum_uc.execute.return_value = MagicMock(candidates=[])

    impact_uc = MagicMock()

    use_case = DailyBriefingUseCase(
        market_repository=market_repo,
        broker_repository=broker_repo,
        regime_use_case=regime_uc,
        accumulation_use_case=accum_uc,
        universe_loader=MagicMock(),
        setup_lens_impact_use_case=impact_uc,
    )

    response = use_case.execute(
        DailyBriefingRequest(universe="lq45", as_of_date=date(2026, 6, 19))
    )

    assert response.overall_authority == "NOT_READY"
    impact_uc.execute.assert_not_called()
    assert response.setup_lens_impact is None


def test_daily_briefing_without_setup_lens_impact_use_case_leaves_none(monkeypatch):
    tickers = ["T1", "T2", "T3"]
    monkeypatch.setattr(
        "src.application.use_case.daily_briefing_use_case.load_universe",
        lambda *a, **kw: tickers,
    )

    market_repo = MagicMock()
    market_repo.get_candles.return_value = []
    market_repo.get_date_range.return_value = (date(2026, 6, 1), date(2026, 6, 19))
    broker_repo = MagicMock()
    broker_repo.get_date_range.return_value = (date(2026, 6, 1), date(2026, 6, 19))

    regime_uc = MagicMock()
    accum_uc = MagicMock()
    accum_uc.execute.return_value = MagicMock(candidates=[_real_accumulation_candidate("BBCA")])

    use_case = DailyBriefingUseCase(
        market_repository=market_repo,
        broker_repository=broker_repo,
        regime_use_case=regime_uc,
        accumulation_use_case=accum_uc,
        universe_loader=MagicMock(),
    )

    response = use_case.execute(
        DailyBriefingRequest(universe="lq45", as_of_date=date(2026, 6, 19))
    )

    assert response.setup_lens_impact is None
