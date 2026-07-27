"""Tests for run_fresh_accumulation_screen_for_compare."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from src.adapters.cli.screen_accum_compare_factory import (
    run_fresh_accumulation_screen_for_compare,
)
from src.adapters.composition.screen_accum_workflow_factory import (
    create_live_signal_evidence_execution_context_use_case,
)
from src.application.dto.accumulation_screen import (
    AccumulationCandidate,
    AccumulationScreenResponse,
)
from src.application.services.indicator_registry import IndicatorRegistry
from src.application.services.signal_engine import SignalEngine
from src.application.services.signal_engine_config import SignalEngineConfig
from src.application.use_case.accumulation_screen_use_case import AccumulationScreenUseCase
from src.domain.value_objects.idx_market import IDX_TIMEZONE, MARKET_CLOSE
from tests.application.use_case.accumulation_screen_fixtures import (
    FakeRulesLoader,
    MockBrokerRepository,
    MockMarketRepository,
    SpyCandidateObservationsRepository,
    _candle,
    _summary,
    _weekdays,
)


def _fake_candidate(ticker: str, score: float = 70.0) -> AccumulationCandidate:
    return AccumulationCandidate(
        ticker=ticker,
        window_days=7,
        net_buy_days=5,
        total_days=7,
        net_buy_ratio=5 / 7,
        total_net_value=Decimal("10000000000"),
        consecutive_streak=3,
        foreign_vwap=Decimal("1030"),
        current_price=Decimal("1000"),
        vwap_discount_pct=3.0,
        rsi=55.0,
        trend="SIDE",
        accum_score=score,
        top_brokers=None,
        institutional_flag=False,
        avg_flow_ratio=5.0,
    )


_FAKE_SC = SimpleNamespace(
    tier1_broker_codes=frozenset(),
    bci_cluster_min_count=3,
    bci_stable_min_count=1,
    resistance_gate_enabled=False,
    resistance_headroom_min_pct=5.0,
    ex_date_warning_days=10,
)

_FAKE_ASC = SimpleNamespace()


class RecordingLiveContextFactory:
    """Recording fake standing in for
    `create_live_signal_evidence_execution_context_use_case`. Records the
    exact market_repository it is called with and counts execute() calls
    on the use case it returns."""

    def __init__(self, context):
        self.context = context
        self.received_market_repository = None
        self.execute_call_count = 0

    def __call__(self, market_repository):
        self.received_market_repository = market_repository
        outer = self

        class _RecordingUseCase:
            def execute(self, *, run_at):
                outer.execute_call_count += 1
                return outer.context

        return _RecordingUseCase()


def test_returns_top_candidates(monkeypatch):
    candidates = [
        _fake_candidate("BBCA", 80.0),
        _fake_candidate("BBRI", 70.0),
        _fake_candidate("BMRI", 60.0),
    ]

    def fake_resolve(*, universe, explicit, db_path, loader, repository):
        return ["BBCA", "BBRI", "BMRI"]

    received_execution_contexts = []

    class FakeUseCase:
        def execute(self, request, *, execution_context):
            received_execution_contexts.append(execution_context)
            return AccumulationScreenResponse(
                candidates=candidates,
                screened_at=date(2026, 7, 1),
                window_days=request.window_days,
                total_tickers_checked=3,
                tickers_skipped=0,
                provider="fake",
            )

    sentinel_market_repository = object()
    sentinel_context = object()
    live_context_factory = RecordingLiveContextFactory(sentinel_context)

    monkeypatch.setattr(
        "src.adapters.cli.screen_accum_compare_factory.resolve_tickers",
        fake_resolve,
    )
    monkeypatch.setattr(
        "src.adapters.cli.screen_accum_compare_factory.create_accumulation_screen_workflow",
        lambda *, db_path, screener_config, with_risk, swing_config: SimpleNamespace(
            use_case=FakeUseCase(), market_repository=sentinel_market_repository
        ),
    )
    monkeypatch.setattr(
        "src.adapters.cli.screen_accum_compare_factory."
        "create_live_signal_evidence_execution_context_use_case",
        live_context_factory,
    )

    result = run_fresh_accumulation_screen_for_compare(
        universe="lq45",
        window=7,
        top=2,
        db_path=Path("/tmp/fake.db"),
        screener_config=_FAKE_ASC,
        swing_config=_FAKE_SC,
    )

    assert result.ok
    assert result.error is None
    assert len(result.candidates) == 2
    assert result.candidates[0].ticker == "BBCA"
    assert result.candidates[1].ticker == "BBRI"

    # The helper receives workflow.market_repository.
    assert live_context_factory.received_market_repository is sentinel_market_repository
    # Its execute() is called exactly once.
    assert live_context_factory.execute_call_count == 1
    # Screen receives the exact sentinel context object.
    assert received_execution_contexts == [sentinel_context]


def test_returns_specific_error_on_empty_universe(monkeypatch):
    monkeypatch.setattr(
        "src.adapters.cli.screen_accum_compare_factory.resolve_tickers",
        lambda *, universe, explicit, db_path, loader, repository: [],
    )

    result = run_fresh_accumulation_screen_for_compare(
        universe="empty",
        window=7,
        top=10,
        db_path=Path("/tmp/fake.db"),
        screener_config=_FAKE_ASC,
        swing_config=_FAKE_SC,
    )

    assert not result.ok
    assert result.candidates == []
    assert "No tickers resolved for universe 'empty'" in result.error


def test_returns_specific_error_on_exception(monkeypatch):
    def fake_resolve(*, universe, explicit, db_path, loader, repository):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(
        "src.adapters.cli.screen_accum_compare_factory.resolve_tickers",
        fake_resolve,
    )

    result = run_fresh_accumulation_screen_for_compare(
        universe="boom",
        window=7,
        top=10,
        db_path=Path("/tmp/fake.db"),
        screener_config=_FAKE_ASC,
        swing_config=_FAKE_SC,
    )

    assert not result.ok
    assert "RuntimeError" in result.error
    assert "simulated failure" in result.error


def test_builds_workflow_with_risk_false(monkeypatch):
    captured = {}

    def fake_resolve(*, universe, explicit, db_path, loader, repository):
        return ["BBCA"]

    def fake_workflow(*, db_path, screener_config, with_risk, swing_config):
        captured["with_risk"] = with_risk
        captured["screener_config"] = screener_config
        captured["swing_config"] = swing_config
        return SimpleNamespace(
            use_case=SimpleNamespace(
                execute=lambda req, *, execution_context: AccumulationScreenResponse(
                    candidates=[_fake_candidate("BBCA")],
                    screened_at=date(2026, 7, 1),
                    window_days=req.window_days,
                    total_tickers_checked=1,
                    tickers_skipped=0,
                    provider="fake",
                )
            ),
            market_repository=MockMarketRepository([]),
        )

    monkeypatch.setattr(
        "src.adapters.cli.screen_accum_compare_factory.resolve_tickers",
        fake_resolve,
    )
    monkeypatch.setattr(
        "src.adapters.cli.screen_accum_compare_factory.create_accumulation_screen_workflow",
        fake_workflow,
    )

    run_fresh_accumulation_screen_for_compare(
        universe="lq45",
        window=7,
        top=10,
        db_path=Path("/tmp/fake.db"),
        screener_config=_FAKE_ASC,
        swing_config=_FAKE_SC,
    )

    assert captured["with_risk"] is False
    assert captured["screener_config"] is _FAKE_ASC
    assert captured["swing_config"] is _FAKE_SC


def test_compare_writes_zero_candidate_observations(monkeypatch):
    """S1 regression: screen compare is read-only and must never persist
    observations, even with a real screen use case wired to a live repo."""
    session_dates = _weekdays(date(2026, 1, 1), 7)
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100")) for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]
    spy_repo = SpyCandidateObservationsRepository()

    fake_market_repository = MockMarketRepository(candles)
    real_use_case = AccumulationScreenUseCase(
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=fake_market_repository,
        rules_loader=FakeRulesLoader(),
        candidate_observations_repository=spy_repo,
        signal_engine=SignalEngine(config=SignalEngineConfig()),
    )

    monkeypatch.setattr(
        "src.adapters.cli.screen_accum_compare_factory.resolve_tickers",
        lambda *, universe, explicit, db_path, loader, repository: ["BBCA"],
    )
    monkeypatch.setattr(
        "src.adapters.cli.screen_accum_compare_factory.create_accumulation_screen_workflow",
        lambda *, db_path, screener_config, with_risk, swing_config: SimpleNamespace(
            use_case=real_use_case, market_repository=fake_market_repository
        ),
    )

    result = run_fresh_accumulation_screen_for_compare(
        universe="lq45",
        window=7,
        top=10,
        db_path=Path("/tmp/fake.db"),
        screener_config=_FAKE_ASC,
        swing_config=_FAKE_SC,
    )

    assert result.ok, result.error
    assert len(result.candidates) >= 1
    assert spy_repo.saved == []


def test_live_context_composition_helper_wires_real_ihsg_calendar_provider():
    """The shared composition helper must wire the real IHSG-backed
    trading-session calendar loader — not an absent/no-calendar loader —
    for both `saham screen accum` and `saham screen compare`. Proven here
    with an in-memory fake market repository holding a gap-free bounded
    IHSG candle series; no network or SQLite access is used."""
    session_dates = _weekdays(date(2025, 12, 1), 60)
    decision_date = session_dates[-5]
    ihsg_candles = [_candle("IHSG", d, Decimal("7000")) for d in session_dates]
    market_repository = MockMarketRepository(ihsg_candles)

    context_use_case = create_live_signal_evidence_execution_context_use_case(market_repository)
    run_at = datetime.combine(decision_date, MARKET_CLOSE, tzinfo=IDX_TIMEZONE)

    execution_context = context_use_case.execute(run_at=run_at)

    # A gap-free bounded IHSG candle series lets the real
    # IHSGTradingSessionCalendarProvider prove the coverage window, which
    # only happens when the composition helper wired the real calendar
    # loader (not `trading_session_calendar_loader=None`).
    assert execution_context.source_availability_use_case is not None
