"""Tests for the accumulation screen workflow use case."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.application.dto.accumulation_screen import (
    AccumulationCandidate,
    AccumulationScreenResponse,
)
from src.application.dto.signal_evidence_execution_context import (
    SignalEvidenceExecutionContext,
)
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from src.application.services.indicator_registry import IndicatorRegistry
from src.application.services.signal_engine import SignalEngine
from src.application.services.signal_engine_config import SignalEngineConfig
from src.application.use_case.accumulation_screen_use_case import AccumulationScreenUseCase
from src.application.use_case.run_accumulation_screen_workflow_use_case import (
    RunAccumulationScreenWorkflowRequest,
    RunAccumulationScreenWorkflowUseCase,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from tests.application.use_case.accumulation_screen_fixtures import (
    FakeRulesLoader,
    MockBrokerRepository,
    MockMarketRepository,
    SpyCandidateObservationsRepository,
    _candle,
    _summary,
    _weekdays,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SWING_CFG = SimpleNamespace(
    tier1_broker_codes=frozenset({"AK", "BK"}),
    bci_cluster_min_count=3,
    bci_stable_min_count=1,
    min_market_cap_idr=0,
    resistance_gate_enabled=True,
    resistance_headroom_min_pct=5.0,
    ex_date_warning_days=10,
    sector_breadth_enabled=True,
    sector_breadth_threshold=0.60,
    sector_breadth_bonus_pts=10.0,
    sector_breadth_min_tickers=3,
    smart_money_brokers=("BK", "AK"),
    noise_brokers=("YP", "XC"),
)

_ASC_CFG = SimpleNamespace(
    min_foreign_flow_score=SimpleNamespace(enabled=True, value=30.0),
    min_signal_score=SimpleNamespace(enabled=False, value=0.0),
    foreign_flow_score_policy=None,
    derived_features=None,
    display=SimpleNamespace(
        coiled_spring_min_foreign_flow_score=50.0,
        coiled_spring_bb_pctile=0.20,
    ),
)


def _candidate(**overrides) -> AccumulationCandidate:
    values = dict(
        ticker="BBCA",
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
        foreign_flow_score=70.0,
        top_brokers=None,
        institutional_flag=False,
        avg_flow_ratio=5.0,
    )
    values.update(overrides)
    return AccumulationCandidate(**values)


def _screen_response(candidates=None, window_days=7) -> AccumulationScreenResponse:
    return AccumulationScreenResponse(
        candidates=candidates or [_candidate()],
        screened_at=date(2026, 7, 13),
        window_days=window_days,
        total_tickers_checked=len(candidates or [1]),
        tickers_skipped=0,
        provider="test",
    )


def _fake_effective_session() -> EffectiveMarketSession:
    decision_at = datetime(2026, 7, 13, 16, 0, tzinfo=IDX_TIMEZONE)
    return EffectiveMarketSession(
        run_at=decision_at,
        decision_at=decision_at,
        latest_completed_session=date(2026, 7, 13),
        analysis_as_of=date(2026, 7, 13),
        market_session_name="AFTER_CLOSE",
        is_eod_pending=False,
        resolution_source="test_fixture",
    )


def _fake_execution_context(effective_session=None) -> SignalEvidenceExecutionContext:
    return SignalEvidenceExecutionContext(
        effective_session=effective_session or _fake_effective_session(),
        source_availability_use_case=None,
    )


class RecordingLiveContextUseCase:
    def __init__(self, context):
        self.context = context
        self.run_at_values = []

    def execute(self, *, run_at):
        self.run_at_values.append(run_at)
        return self.context


def _make_uc(*, screen_use_case=None, broker_repo=None, market_repo=None,
             save_uc=None, live_context_use_case=None) -> RunAccumulationScreenWorkflowUseCase:
    return RunAccumulationScreenWorkflowUseCase(
        screen_use_case=screen_use_case or MagicMock(),
        broker_repository=broker_repo or MagicMock(),
        market_repository=market_repo or MagicMock(),
        swing_config=_SWING_CFG,
        accumulation_screener_config=_ASC_CFG,
        rules_loader=MagicMock(),
        indicator_registry_factory=MagicMock(),
        live_signal_evidence_context_use_case=(
            live_context_use_case
            or RecordingLiveContextUseCase(_fake_execution_context())
        ),
        save_watchlist_use_case=save_uc,
    )


def _single_request(**overrides) -> RunAccumulationScreenWorkflowRequest:
    params = dict(
        tickers=["BBCA", "BBRI"],
        universe_label="lq45",
        universe_name="lq45",
        window=7,
        min_streak=0,
        min_foreign_flow_score=None,
        min_signal_score=None,
        min_piotroski=0,
        strategy_name=None,
        include_strategy_overlay=False,
        multi=False,
        windows=[],
        top=20,
        save_name=None,
        save_enabled=False,
    )
    params.update(overrides)
    return RunAccumulationScreenWorkflowRequest(**params)


def _multi_request(**overrides) -> RunAccumulationScreenWorkflowRequest:
    params = dict(
        tickers=["BBCA", "BBRI"],
        universe_label="lq45",
        universe_name="lq45",
        window=7,
        min_streak=0,
        min_foreign_flow_score=None,
        min_signal_score=None,
        min_piotroski=0,
        strategy_name=None,
        include_strategy_overlay=False,
        multi=True,
        windows=[7, 30, 90],
        top=20,
        save_name=None,
        save_enabled=False,
    )
    params.update(overrides)
    return RunAccumulationScreenWorkflowRequest(**params)


# ---------------------------------------------------------------------------
# Single mode
# ---------------------------------------------------------------------------


def test_single_mode_executes_screen():
    screen_mock = MagicMock()
    screen_mock.execute.return_value = _screen_response()
    uc = _make_uc(screen_use_case=screen_mock)

    result = uc.execute(_single_request())

    screen_mock.execute.assert_called_once()
    assert result.response is not None
    assert result.multi_results == {}
    assert result.strategy_signals == {}


def test_single_mode_resolves_effective_session_once():
    """DQ-002B: the shared live execution-context use case is called once
    per execute(), not once per candidate."""
    c1 = _candidate(ticker="A")
    c2 = _candidate(ticker="B")
    c3 = _candidate(ticker="C")
    screen_mock = MagicMock()
    screen_mock.execute.return_value = _screen_response(candidates=[c1, c2, c3])
    live_context_uc = RecordingLiveContextUseCase(_fake_execution_context())
    uc = _make_uc(screen_use_case=screen_mock, live_context_use_case=live_context_uc)

    uc.execute(_single_request())

    assert len(live_context_uc.run_at_values) == 1


def test_single_mode_applies_min_streak_filter():
    c1 = _candidate(ticker="A", consecutive_streak=5)
    c2 = _candidate(ticker="B", consecutive_streak=2)
    c3 = _candidate(ticker="C", consecutive_streak=0)
    screen_mock = MagicMock()
    screen_mock.execute.return_value = _screen_response(candidates=[c1, c2, c3])
    uc = _make_uc(screen_use_case=screen_mock)

    result = uc.execute(_single_request(min_streak=3))

    assert result.response is not None
    assert result.single_projection is not None
    assert [c.ticker for c in result.single_projection.candidates] == ["A"]
    assert result.single_projection.raw_candidate_count == 3
    assert result.single_projection.applied_filters.min_streak == 3


def test_single_mode_min_streak_does_not_influence_raw_screen_request():
    """S2 regression: CLI min_streak must not leak into
    AccumulationScreenRequest.min_net_buy_days — that would let the raw
    screen drop candidates before the projector ever applies min_streak,
    violating the "filters applied exactly once, in the projector" contract.
    """
    c1 = _candidate(ticker="A", consecutive_streak=5)
    c2 = _candidate(ticker="B", consecutive_streak=2)
    c3 = _candidate(ticker="C", consecutive_streak=0)
    screen_mock = MagicMock()
    screen_mock.execute.return_value = _screen_response(candidates=[c1, c2, c3])
    uc = _make_uc(screen_use_case=screen_mock)

    result = uc.execute(_single_request(min_streak=5))

    raw_screen_request = screen_mock.execute.call_args[0][0]
    assert raw_screen_request.min_net_buy_days != 5

    assert result.single_projection is not None
    assert [c.ticker for c in result.single_projection.candidates] == ["A"]
    assert result.single_projection.raw_candidate_count == 3


def test_single_mode_zero_min_streak_keeps_all():
    c1 = _candidate(ticker="A", consecutive_streak=0)
    c2 = _candidate(ticker="B", consecutive_streak=0)
    screen_mock = MagicMock()
    screen_mock.execute.return_value = _screen_response(candidates=[c1, c2])
    uc = _make_uc(screen_use_case=screen_mock)

    result = uc.execute(_single_request(min_streak=0))

    assert result.response is not None
    assert result.single_projection is not None
    assert len(result.single_projection.candidates) == 2


# ---------------------------------------------------------------------------
# Multi mode
# ---------------------------------------------------------------------------


def test_multi_mode_resolves_effective_session_once_not_per_window():
    """DQ-002B: the shared live execution-context use case is called once
    per execute(), shared across all windows — never once per window."""
    screen_mock = MagicMock()
    screen_mock.execute.side_effect = (
        lambda req, *, execution_context: _screen_response(window_days=req.window_days)
    )
    live_context_uc = RecordingLiveContextUseCase(_fake_execution_context())
    uc = _make_uc(screen_use_case=screen_mock, live_context_use_case=live_context_uc)

    uc.execute(_multi_request(windows=[7, 30, 90]))

    assert len(live_context_uc.run_at_values) == 1


def test_multi_mode_executes_all_windows():
    screen_mock = MagicMock()
    screen_mock.execute.side_effect = (
        lambda req, *, execution_context: _screen_response(window_days=req.window_days)
    )
    uc = _make_uc(screen_use_case=screen_mock)

    result = uc.execute(_multi_request(windows=[7, 30]))

    assert screen_mock.execute.call_count == 2
    assert set(result.multi_results.keys()) == {7, 30}
    assert result.response is None


def test_multi_mode_score_filters_disabled():
    screen_mock = MagicMock()
    screen_mock.execute.side_effect = (
        lambda req, *, execution_context: _screen_response(window_days=req.window_days)
    )
    uc = _make_uc(screen_use_case=screen_mock)

    uc.execute(_multi_request(windows=[7]))

    req = screen_mock.execute.call_args[0][0]
    assert req.min_foreign_flow_score == 0.0
    assert req.min_foreign_flow_score_enabled is False
    assert req.min_signal_score == 0.0
    assert req.min_signal_score_enabled is False


def test_multi_mode_passthrough_min_piotroski():
    screen_mock = MagicMock()
    screen_mock.execute.side_effect = (
        lambda req, *, execution_context: _screen_response(window_days=req.window_days)
    )
    uc = _make_uc(screen_use_case=screen_mock)

    uc.execute(_multi_request(windows=[7], min_piotroski=5))

    req = screen_mock.execute.call_args[0][0]
    assert req.min_piotroski == 5


def test_multi_mode_tracked_broker_flow():
    screen_mock = MagicMock()
    screen_mock.execute.side_effect = (
        lambda req, *, execution_context: _screen_response(window_days=req.window_days)
    )

    broker_repo = MagicMock()
    broker_repo.get_broker_daily_flows.return_value = []
    uc = _make_uc(screen_use_case=screen_mock, broker_repo=broker_repo)

    result = uc.execute(_multi_request(windows=[7]))

    assert isinstance(result.tracked_broker_flow, dict)


def test_multi_mode_canonical_window_defaults_to_7():
    screen_mock = MagicMock()
    screen_mock.execute.side_effect = (
        lambda req, *, execution_context: _screen_response(window_days=req.window_days)
    )
    uc = _make_uc(screen_use_case=screen_mock)

    result = uc.execute(_multi_request(windows=[7, 30, 90]))

    assert result.multi_projection is not None
    assert result.multi_projection.canonical_window == 7


def test_multi_mode_canonical_window_falls_back_to_first_requested_window():
    """S7: when 7 is not among the requested windows, canonical window falls
    back to the first requested window rather than failing."""
    screen_mock = MagicMock()
    screen_mock.execute.side_effect = (
        lambda req, *, execution_context: _screen_response(window_days=req.window_days)
    )
    uc = _make_uc(screen_use_case=screen_mock)

    result = uc.execute(_multi_request(windows=[30, 90]))

    assert result.multi_projection is not None
    assert result.multi_projection.canonical_window == 30


def test_multi_mode_writes_zero_candidate_observations():
    """S1 regression: --multi is diagnostic and must never persist observations,
    even with a real screen use case wired to a live observations repository."""
    session_dates = _weekdays(date(2026, 1, 1), 7)
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100")) for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]
    spy_repo = SpyCandidateObservationsRepository()

    real_screen_use_case = AccumulationScreenUseCase(
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
        candidate_observations_repository=spy_repo,
        signal_engine=SignalEngine(config=SignalEngineConfig()),
    )
    broker_repo = MagicMock()
    broker_repo.get_broker_daily_flows.return_value = []
    uc = _make_uc(screen_use_case=real_screen_use_case, broker_repo=broker_repo)

    uc.execute(_multi_request(tickers=["BBCA"], windows=[7]))

    assert spy_repo.saved == []


# ---------------------------------------------------------------------------
# Strategy overlay
# ---------------------------------------------------------------------------


def test_strategy_overlay_only_when_flag_true(monkeypatch):
    from src.application.use_case import (
        run_accumulation_screen_workflow_use_case as uc_mod,
    )

    screen_mock = MagicMock()
    screen_mock.execute.return_value = _screen_response()
    uc = _make_uc(screen_use_case=screen_mock)

    strat_mock = MagicMock()
    strat_mock.resolve.return_value = Path("/tmp/fake.yaml")
    monkeypatch.setattr(
        uc_mod, "StrategyLoader", lambda *, rules_loader, registry: strat_mock
    )

    risk_mock = MagicMock()
    risk_mock.execute.return_value.assessment.risk_level_name = "OPEN"
    monkeypatch.setattr(
        uc_mod,
        "AssessRiskUseCase",
        lambda *, repository, registry, rules_loader: risk_mock,
    )

    result = uc.execute(_single_request(
        strategy_name="test-strat",
        include_strategy_overlay=True,
    ))

    strat_mock.resolve.assert_called_once_with("test-strat")
    assert len(result.strategy_signals) > 0


def test_strategy_overlay_skipped_when_flag_false(monkeypatch):
    from src.application.use_case import (
        run_accumulation_screen_workflow_use_case as uc_mod,
    )

    screen_mock = MagicMock()
    screen_mock.execute.return_value = _screen_response()
    uc = _make_uc(screen_use_case=screen_mock)

    strat_mock = MagicMock()
    monkeypatch.setattr(
        uc_mod, "StrategyLoader", lambda *, rules_loader, registry: strat_mock
    )

    risk_mock = MagicMock()
    monkeypatch.setattr(
        uc_mod,
        "AssessRiskUseCase",
        lambda *, repository, registry, rules_loader: risk_mock,
    )

    result = uc.execute(_single_request(
        strategy_name="test-strat",
        include_strategy_overlay=False,
    ))

    strat_mock.resolve.assert_not_called()
    assert result.strategy_signals == {}


def test_strategy_overlay_top_visible_only(monkeypatch):
    from src.application.use_case import (
        run_accumulation_screen_workflow_use_case as uc_mod,
    )

    candidates = [_candidate(ticker=f"T{i}", consecutive_streak=3) for i in range(10)]
    screen_mock = MagicMock()
    screen_mock.execute.return_value = _screen_response(candidates=candidates)
    uc = _make_uc(screen_use_case=screen_mock)

    strat_mock = MagicMock()
    strat_mock.resolve.return_value = Path("/tmp/fake.yaml")
    monkeypatch.setattr(
        uc_mod, "StrategyLoader", lambda *, rules_loader, registry: strat_mock
    )

    risk_mock = MagicMock()
    risk_mock.execute.return_value.assessment.risk_level_name = "OPEN"
    monkeypatch.setattr(
        uc_mod,
        "AssessRiskUseCase",
        lambda *, repository, registry, rules_loader: risk_mock,
    )

    result = uc.execute(_single_request(
        strategy_name="test-strat",
        include_strategy_overlay=True,
        top=3,
    ))

    assert len(result.strategy_signals) == 3


def test_strategy_overlay_maps_failures_to_question_mark(monkeypatch):
    from src.application.use_case import (
        run_accumulation_screen_workflow_use_case as uc_mod,
    )

    screen_mock = MagicMock()
    screen_mock.execute.return_value = _screen_response(
        candidates=[_candidate(ticker="OK"), _candidate(ticker="FAIL")]
    )
    uc = _make_uc(screen_use_case=screen_mock)

    strat_mock = MagicMock()
    strat_mock.resolve.return_value = Path("/tmp/fake.yaml")
    monkeypatch.setattr(
        uc_mod, "StrategyLoader", lambda *, rules_loader, registry: strat_mock
    )

    risk_mock = MagicMock()
    risk_mock.execute.side_effect = [
        MagicMock(assessment=MagicMock(risk_level_name="OPEN")),
        ValueError("boom"),
    ]
    monkeypatch.setattr(
        uc_mod,
        "AssessRiskUseCase",
        lambda *, repository, registry, rules_loader: risk_mock,
    )

    result = uc.execute(_single_request(
        strategy_name="test-strat",
        include_strategy_overlay=True,
        top=5,
    ))

    assert result.strategy_signals.get("OK") == "OPEN"
    assert result.strategy_signals.get("FAIL") == "?"


def test_missing_strategy_returns_warning(monkeypatch):
    from src.application.rules.exceptions import StrategyNotFoundError
    from src.application.use_case import (
        run_accumulation_screen_workflow_use_case as uc_mod,
    )

    screen_mock = MagicMock()
    screen_mock.execute.return_value = _screen_response()
    uc = _make_uc(screen_use_case=screen_mock)

    strat_mock = MagicMock()
    strat_mock.resolve.side_effect = StrategyNotFoundError(
        "missing", searched_paths=["/tmp/missing"]
    )
    monkeypatch.setattr(
        uc_mod, "StrategyLoader", lambda *, rules_loader, registry: strat_mock
    )

    result = uc.execute(_single_request(
        strategy_name="missing",
        include_strategy_overlay=True,
    ))

    assert len(result.warnings) == 1
    assert "Strategy not found" in result.warnings[0]


def test_missing_strategy_still_saves(monkeypatch):
    """Regression: missing strategy must not prevent save."""
    from src.application.rules.exceptions import StrategyNotFoundError
    from src.application.use_case import (
        run_accumulation_screen_workflow_use_case as uc_mod,
    )
    from src.application.use_case.save_screen_watchlist_use_case import (
        SaveScreenWatchlistResult,
    )

    screen_mock = MagicMock()
    screen_mock.execute.return_value = _screen_response(
        candidates=[_candidate(ticker="BBCA")]
    )
    save_mock = MagicMock()
    save_mock.execute.return_value = SaveScreenWatchlistResult(
        saved_count=1, name="missing-strat-save"
    )
    uc = _make_uc(screen_use_case=screen_mock, save_uc=save_mock)

    strat_mock = MagicMock()
    strat_mock.resolve.side_effect = StrategyNotFoundError(
        "missing", searched_paths=["/tmp/missing"]
    )
    monkeypatch.setattr(
        uc_mod, "StrategyLoader", lambda *, rules_loader, registry: strat_mock
    )

    result = uc.execute(_single_request(
        strategy_name="missing",
        include_strategy_overlay=True,
        save_name="missing-strat-save",
        save_enabled=True,
    ))

    assert len(result.warnings) == 1
    assert "Strategy not found" in result.warnings[0]
    save_mock.execute.assert_called_once()
    assert result.save_result is not None
    assert result.save_result.saved_count == 1


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------


def test_save_invoked_when_enabled():
    from src.application.use_case.save_screen_watchlist_use_case import (
        SaveScreenWatchlistResult,
    )

    screen_mock = MagicMock()
    screen_mock.execute.return_value = _screen_response(
        candidates=[_candidate(ticker="BBCA"), _candidate(ticker="BBRI")]
    )
    save_mock = MagicMock()
    save_mock.execute.return_value = SaveScreenWatchlistResult(
        saved_count=2, name="mywatch"
    )
    uc = _make_uc(screen_use_case=screen_mock, save_uc=save_mock)

    result = uc.execute(_single_request(
        save_name="mywatch",
        save_enabled=True,
        top=5,
    ))

    save_mock.execute.assert_called_once()
    call_args = save_mock.execute.call_args[0][0]
    assert call_args.name == "mywatch"
    assert len(call_args.candidates) == 2
    assert result.save_result is not None
    assert result.save_result.saved_count == 2


def test_save_skipped_when_disabled():
    screen_mock = MagicMock()
    screen_mock.execute.return_value = _screen_response()
    save_mock = MagicMock()
    uc = _make_uc(screen_use_case=screen_mock, save_uc=save_mock)

    result = uc.execute(_single_request(
        save_name="mywatch",
        save_enabled=False,
    ))

    save_mock.execute.assert_not_called()
    assert result.save_result is None


def test_save_uses_top_candidates():
    from src.application.use_case.save_screen_watchlist_use_case import (
        SaveScreenWatchlistResult,
    )

    candidates = [_candidate(ticker=f"T{i}") for i in range(10)]
    screen_mock = MagicMock()
    screen_mock.execute.return_value = _screen_response(candidates=candidates)
    save_mock = MagicMock()
    save_mock.execute.return_value = SaveScreenWatchlistResult(
        saved_count=3, name="top3"
    )
    uc = _make_uc(screen_use_case=screen_mock, save_uc=save_mock)

    result = uc.execute(_single_request(
        save_name="top3",
        save_enabled=True,
        top=3,
    ))

    call_args = save_mock.execute.call_args[0][0]
    assert len(call_args.candidates) == 3
    assert result.save_result is not None


class RecordingScreenFake:
    def __init__(self, responses: dict[int, AccumulationScreenResponse] | None = None) -> None:
        self.recorded_contexts = []
        self.recorded_requests = []
        self.responses = responses or {}

    def execute(
        self,
        request: "AccumulationScreenRequest",
        *,
        execution_context: "SignalEvidenceExecutionContext",
    ) -> "AccumulationScreenResponse":
        self.recorded_contexts.append(execution_context)
        self.recorded_requests.append(request)
        return self.responses.get(
            request.window_days,
            _screen_response(window_days=request.window_days),
        )


def test_multi_mode_context_lineage_preserves_object_identity(monkeypatch):
    from src.application.use_case import (
        run_accumulation_screen_workflow_use_case as uc_mod,
    )

    sentinel_context = _fake_execution_context()
    live_context_uc = RecordingLiveContextUseCase(sentinel_context)
    screen_fake = RecordingScreenFake()

    captured_projection_sessions = []
    real_project_multi = uc_mod.project_multi_screen_result

    def spy_project_multi_screen_result(
        multi_results,
        *,
        tracked_broker_flow,
        windows,
        top,
        sort_by,
        squeeze_only,
        coiled_spring_min_foreign_flow_score,
        coiled_spring_bb_pctile,
        canonical_window,
        effective_session,
    ):
        captured_projection_sessions.append(effective_session)
        return real_project_multi(
            multi_results,
            tracked_broker_flow=tracked_broker_flow,
            windows=windows,
            top=top,
            sort_by=sort_by,
            squeeze_only=squeeze_only,
            coiled_spring_min_foreign_flow_score=coiled_spring_min_foreign_flow_score,
            coiled_spring_bb_pctile=coiled_spring_bb_pctile,
            canonical_window=canonical_window,
            effective_session=effective_session,
        )

    monkeypatch.setattr(
        uc_mod, "project_multi_screen_result", spy_project_multi_screen_result
    )

    uc = RunAccumulationScreenWorkflowUseCase(
        screen_use_case=screen_fake,
        broker_repository=MagicMock(),
        market_repository=MagicMock(),
        swing_config=_SWING_CFG,
        accumulation_screener_config=_ASC_CFG,
        rules_loader=MagicMock(),
        indicator_registry_factory=MagicMock(),
        live_signal_evidence_context_use_case=live_context_uc,
        save_watchlist_use_case=None,
    )

    uc.execute(_multi_request(windows=[7, 30, 90]))

    # Live context use case must be called exactly once per workflow execution.
    assert len(live_context_uc.run_at_values) == 1

    # Screen receives the exact same context object across all 3 windows.
    assert len(screen_fake.recorded_contexts) == 3
    assert screen_fake.recorded_contexts[0] is sentinel_context
    assert screen_fake.recorded_contexts[1] is sentinel_context
    assert screen_fake.recorded_contexts[2] is sentinel_context

    # Projection receives context.effective_session.
    assert captured_projection_sessions == [sentinel_context.effective_session]


def test_single_mode_context_lineage_preserves_object_identity(monkeypatch):
    from src.application.use_case import (
        run_accumulation_screen_workflow_use_case as uc_mod,
    )

    sentinel_context = _fake_execution_context()
    live_context_uc = RecordingLiveContextUseCase(sentinel_context)
    screen_fake = RecordingScreenFake()

    captured_projection_sessions = []
    real_project_single = uc_mod.project_single_screen_result

    def spy_project_single_screen_result(
        response,
        *,
        vwap_only,
        squeeze_only,
        top,
        min_streak,
        coiled_spring_bb_pctile,
        effective_session,
        sort_by="vwap",
    ):
        captured_projection_sessions.append(effective_session)
        return real_project_single(
            response,
            vwap_only=vwap_only,
            squeeze_only=squeeze_only,
            top=top,
            min_streak=min_streak,
            coiled_spring_bb_pctile=coiled_spring_bb_pctile,
            effective_session=effective_session,
            sort_by=sort_by,
        )

    monkeypatch.setattr(
        uc_mod, "project_single_screen_result", spy_project_single_screen_result
    )

    uc = RunAccumulationScreenWorkflowUseCase(
        screen_use_case=screen_fake,
        broker_repository=MagicMock(),
        market_repository=MagicMock(),
        swing_config=_SWING_CFG,
        accumulation_screener_config=_ASC_CFG,
        rules_loader=MagicMock(),
        indicator_registry_factory=MagicMock(),
        live_signal_evidence_context_use_case=live_context_uc,
        save_watchlist_use_case=None,
    )

    uc.execute(_single_request())

    # Live context use case must be called exactly once per workflow execution.
    assert len(live_context_uc.run_at_values) == 1

    # Single-window screen receives its exact returned context.
    assert len(screen_fake.recorded_contexts) == 1
    assert screen_fake.recorded_contexts[0] is sentinel_context

    # Projection receives context.effective_session.
    assert captured_projection_sessions == [sentinel_context.effective_session]
