"""Display/rendering tests for screen accum output helpers."""

from datetime import date
from decimal import Decimal

from src.adapters.cli.screen_accum_display import (
    display_multi,
    display_results,
)
from src.adapters.cli.screen_accum_formatters import (
    accumulation_display_config_from_screener,
)
from src.application.dto.accumulation_screen import (
    AccumulationScreenResponse,
)
from src.application.services.screen_accum_result_projector import (
    project_multi_screen_result,
    project_single_screen_result,
)
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_assessment import RiskAssessment
from src.domain.value_objects.setup_phase import SetupPhaseSnapshot, SetupPhaseState
from src.domain.value_objects.signal_assessment import SignalStrength
from src.domain.value_objects.trade_setup import SetupAction, TradeSetup
from src.infrastructure.config.accumulation_screener_config import load_accumulation_screener_config
from tests.adapters.cli.screen_accum_test_fixtures import (
    _FAKE_EFFECTIVE_SESSION,
    _candidate,
)

_CFG = accumulation_display_config_from_screener(load_accumulation_screener_config())


def test_display_results_renders_rich_accumulation_panel(capsys):
    response = AccumulationScreenResponse(
        candidates=[_candidate()],
        screened_at=date(2026, 6, 19),
        window_days=7,
        total_tickers_checked=1,
        tickers_skipped=0,
        provider="stockbit",
    )

    display_results(
        response=response,
        candidates=response.candidates,
        universe_label="lq45",
        show_top_broker=False,
        display_config=_CFG,
        include_detail=False,
    )

    out = capsys.readouterr().out
    assert "Foreign Accumulation - LQ45" in out
    assert "Candidate Actions" in out
    assert "Decision · Action Why" in out
    assert "Why Action" in out or "Why" in out
    assert "Setup readiness" in out
    assert "Verdict" not in out
    assert "BBCA" in out
    assert "Risk Status" in out
    assert "Gate detail" in out
    assert "Rule Conf" not in out
    assert "Gate Conf" not in out
    assert "TechnicalGate is not evaluated by screen accum" in out
    assert "Scoring Definitions" not in out
    assert "Run Context" not in out
    # Option 1: Signal summary + FlowGrp component panel always present
    assert "FlowGrp" in out or "flow confirmation" in out.lower()
    assert "Signal" in out


def test_display_results_never_shows_fresh_ok_and_splits_align_from_ready(capsys):
    """S3: the retired 'Fresh: OK' label must be gone; alignment and
    readiness render as separate, typed labels sourced from the same
    DataFreshnessStatus the projector attaches to each candidate."""
    candidate = _candidate(
        latest_candle_date=date(2026, 6, 26),
        latest_broker_date=date(2026, 6, 26),
    )
    response = AccumulationScreenResponse(
        candidates=[candidate],
        screened_at=date(2026, 6, 28),
        window_days=7,
        total_tickers_checked=1,
        tickers_skipped=0,
        provider="stockbit",
    )
    projection = project_single_screen_result(
        response,
        vwap_only=False,
        squeeze_only=False,
        top=10,
        min_streak=0,
        coiled_spring_bb_pctile=0.20,
        effective_session=_FAKE_EFFECTIVE_SESSION,
    )

    display_results(
        response=response,
        candidates=projection.candidates,
        universe_label="lq45",
        show_top_broker=False,
        display_config=_CFG,
        include_detail=False,
    )

    out = capsys.readouterr().out
    assert "Fresh" not in out
    assert "OK" not in out
    assert "Align" in out
    assert "Ready" in out
    assert candidate.freshness is not None
    assert candidate.freshness.alignment_state.value == "ALIGNED"


def test_display_results_renders_explanation_panels_when_requested(capsys):
    response = AccumulationScreenResponse(
        candidates=[_candidate()],
        screened_at=date(2026, 6, 19),
        window_days=7,
        total_tickers_checked=1,
        tickers_skipped=0,
        provider="stockbit",
    )

    display_results(
        response=response,
        candidates=response.candidates,
        universe_label="lq45",
        show_top_broker=False,
        display_config=_CFG,
        include_detail=True,
    )

    out = capsys.readouterr().out
    assert "Run Context" in out
    assert "Scoring Definitions" in out
    assert "Candidate Actions is the screen summary" in out
    assert "Swing trade watchlist" in out
    assert "Market context" in out
    assert "diagnostic only" in out
    # Rich may wrap "does not move Action" across lines
    assert "move Action" in out


def test_display_results_decision_why_matches_shared_formatter(capsys):
    """CLI Action Why must use decision_display (TUI parity), not a private path."""
    from types import SimpleNamespace

    from src.adapters.shared.decision_display import format_action_why
    from src.adapters.shared.screen_accum_board_fields import extract_screen_accum_board_fields
    from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
    from src.domain.value_objects.risk_assessment import RiskAssessment
    from src.domain.value_objects.signal_assessment import SignalStrength
    from src.domain.value_objects.trade_setup import SetupAction, TradeSetup

    constraints = SimpleNamespace(
        constraint_reasons=(
            "RISK_ON ENTER requires signal_authority_coverage >= 70%",
            "Setup readiness UNAVAILABLE caps ENTER to WATCH",
        ),
        max_decision="WATCH",
        regime=None,
    )
    readiness = SimpleNamespace(
        status=SimpleNamespace(value="UNAVAILABLE"),
        setup_family="pullback",
        missing_required_inputs=("setup match not evaluated",),
        failed_requirements=(),
        current_phase=None,
    )
    assessment = SimpleNamespace(
        score=79,
        score_label="STRONG 79",
        strength=SimpleNamespace(value="STRONG"),
        signal_authority_coverage=0.0,
        decision_constraints=constraints,
        setup_readiness=readiness,
        breakdown_dict={
            "setup_quality_group": 50.0,
            "flow_confirmation_group": 70.0,
            "signal_authority_coverage": 0.0,
        },
    )
    signal_assessment = SimpleNamespace(
        assessment=assessment,
        setup_readiness=readiness,
        signal_authority_coverage=0.0,
        active_flags=(),
        coverage_warning=None,
    )
    trade_setup = TradeSetup(
        ticker="BBCA",
        snapshot_date=date(2026, 6, 19),
        action=SetupAction.WATCH,
        signal_score=79,
        signal_score_raw=79,
        signal_strength=SignalStrength.STRONG,
        blocking_gates=(),
        regime=None,
        signal_multiplier=1.0,
        gate_tightening=False,
        rationale="Signal 79/100 | gate: open",
    )
    risk = RiskAssessment(
        rationale=("all gates passed",),
        snapshot_date=date(2026, 6, 19),
        indicators=IndicatorSnapshot(
            date=date(2026, 6, 19),
            sma=Decimal("1000"),
            ema=Decimal("1010"),
            rsi=Decimal("55"),
        ),
        gate_triggered=None,
        gate_is_structural=False,
        gate_confidence=100,
    )
    components = (
        SimpleNamespace(key="cons", score_points=28.5, status=SimpleNamespace(value="AVAILABLE")),
        SimpleNamespace(key="bb", score_points=None, status=SimpleNamespace(value="DISABLED")),
    )
    candidate = _candidate(
        trade_setup=trade_setup,
        risk_assessment=risk,
        signal_assessment=signal_assessment,
        accum_score=62.2,
        accum_score_breakdown=SimpleNamespace(
            components=components,
            accum_score=62.2,
            breakdown_dict={"cons": 28.5, "bb": None},
        ),
    )
    fields = extract_screen_accum_board_fields(candidate, phase_style="full")
    expected_why = format_action_why(candidate, gate=fields.gate)
    # Shared formatter contract (TUI uses the same function)
    assert "authority 0%" in expected_why
    assert "setup readiness UNAVAILABLE" in expected_why
    assert "(setup match not evaluated)" in expected_why
    assert "gate open" in expected_why

    response = AccumulationScreenResponse(
        candidates=[candidate],
        screened_at=date(2026, 6, 19),
        window_days=7,
        total_tickers_checked=1,
        tickers_skipped=0,
        provider="stockbit",
    )
    display_results(
        response=response,
        candidates=response.candidates,
        universe_label="lq45",
        show_top_broker=False,
        display_config=_CFG,
        include_detail=False,
    )
    out = capsys.readouterr().out
    # Rich may wrap the Why column; assert key tokens from shared formatter
    assert "authority 0%" in out
    assert "setup readiness UNAVAILABLE" in out
    assert "setup match not evaluated" in out
    assert "gate open" in out
    assert "Decision · Action Why" in out
    assert "cons 28.5" in out
    assert "bb off" in out
    assert "recipe" not in out.lower()
    # ADR-054 S1: single-candidate board opens with Judgment strip
    assert "Judgment" in out
    assert "WATCH" in out or "Watch" in out
    assert "plan swing" in out
    assert "horizon" in out.lower() or "Structure" in out
    # Judgment package: TradeSetup serializes for JSON clients (candidate field)
    ts = trade_setup.to_dict()
    assert ts["action"] == "WATCH"
    assert ts["ticker"] == "BBCA"


def test_display_results_judgment_header_only_for_single_candidate(capsys):
    """Universe/multi rows must not force a single-ticker Judgment strip."""
    c1 = _candidate(ticker="BBCA")
    c2 = _candidate(ticker="BBRI")
    response = AccumulationScreenResponse(
        candidates=[c1, c2],
        screened_at=date(2026, 6, 19),
        window_days=7,
        total_tickers_checked=2,
        tickers_skipped=0,
        provider="stockbit",
    )
    display_results(
        response=response,
        candidates=response.candidates,
        universe_label="lq45",
        show_top_broker=False,
        display_config=_CFG,
        include_detail=False,
    )
    out = capsys.readouterr().out
    assert "Candidate Actions" in out
    # Title "Judgment" is single-case only
    assert "Judgment case file" not in out


def test_display_results_diagnostic_market_context_panel(capsys):
    from types import SimpleNamespace

    mc = SimpleNamespace(
        regime=SimpleNamespace(value="NEUTRAL"),
        conviction=0.51,
        regime_confidence=0.4,
        regime_stability="STABLE",
        days_in_regime=3,
        staleness_warning=None,
        coverage_warning=None,
        transition_warning=None,
    )
    response = AccumulationScreenResponse(
        candidates=[_candidate()],
        screened_at=date(2026, 6, 19),
        window_days=7,
        total_tickers_checked=1,
        tickers_skipped=0,
        provider="stockbit",
    )
    display_results(
        response=response,
        candidates=response.candidates,
        universe_label="lq45",
        show_top_broker=False,
        display_config=_CFG,
        include_detail=True,
        market_context=mc,
    )
    out = capsys.readouterr().out
    assert "Market context (diagnostic)" in out
    assert "NEUTRAL" in out
    assert "diagnostic only" in out
    assert "move Action" in out


def test_display_results_renders_blocked_risk_diagnostics(capsys):
    risk_assessment = RiskAssessment(
        rationale=("Piotroski F-Score 1 below threshold 3",),
        snapshot_date=date(2026, 6, 19),
        indicators=IndicatorSnapshot(
            date=date(2026, 6, 19),
            sma=Decimal("1000"),
            ema=Decimal("1010"),
            rsi=Decimal("55"),
        ),
        gate_triggered="FundamentalGate",
        gate_is_structural=True,
        gate_confidence=100,
    )
    trade_setup = TradeSetup(
        ticker="BBCA",
        snapshot_date=date(2026, 6, 19),
        action=SetupAction.BLOCKED_STRUCTURAL,
        signal_score=72,
        signal_score_raw=72,
        signal_strength=SignalStrength.STRONG,
        blocking_gates=("FundamentalGate",),
        regime=None,
        signal_multiplier=1.0,
        gate_tightening=False,
        rationale="Blocked by FundamentalGate",
    )
    response = AccumulationScreenResponse(
        candidates=[
            _candidate(
                risk_assessment=risk_assessment,
                trade_setup=trade_setup,
            )
        ],
        screened_at=date(2026, 6, 19),
        window_days=7,
        total_tickers_checked=1,
        tickers_skipped=0,
        provider="stockbit",
    )

    display_results(
        response=response,
        candidates=response.candidates,
        universe_label="lq45",
        show_top_broker=False,
        display_config=_CFG,
        include_detail=False,
    )

    out = capsys.readouterr().out
    assert "Risk Status" in out
    assert "BLOCKED" in out
    assert "structural" in out
    assert "FundamentalGate" in out


def test_display_multi_renders_rich_accumulation_panel(capsys):
    results = {
        7: AccumulationScreenResponse(
            candidates=[_candidate(accum_score=72.0, window_days=7)],
            screened_at=date(2026, 6, 19),
            window_days=7,
            total_tickers_checked=1,
            tickers_skipped=0,
            provider="stockbit",
        ),
        30: AccumulationScreenResponse(
            candidates=[_candidate(accum_score=55.0, window_days=30)],
            screened_at=date(2026, 6, 19),
            window_days=30,
            total_tickers_checked=1,
            tickers_skipped=0,
            provider="stockbit",
        ),
    }

    projection = project_multi_screen_result(
        results,
        tracked_broker_flow=None,
        windows=[7, 30],
        top=10,
        sort_by="avg",
        squeeze_only=False,
        coiled_spring_min_accum_score=_CFG.coiled_spring_min_accum_score,
        coiled_spring_bb_pctile=_CFG.coiled_spring_bb_pctile,
        canonical_window=7,
        effective_session=_FAKE_EFFECTIVE_SESSION,
    )

    display_multi(
        rows=projection.rows,
        universe_label="lq45",
        windows=projection.resolved_windows,
        screened_at=date(2026, 6, 19),
        display_config=_CFG,
    )

    out = capsys.readouterr().out
    assert "Foreign Accumulation - LQ45" in out
    assert "multi-window" in out
    assert "BBCA" in out
    assert "Pattern" in out
    assert "Run Context" not in out
    assert "Tracked" in out
    assert "Disc%" in out


def test_display_multi_renders_canonical_signal_risk_phase_data_next(capsys):
    """S7: multi table must render the canonical window's Signal/Risk/Phase/
    Data/Next evidence instead of discarding it."""
    setup_phase = SetupPhaseSnapshot(
        current_phase=SetupPhaseState.ACCUMULATION,
        previous_phase=None,
        phase_age_sessions=1,
        phase_detection_strength=0.6,
        phase_input_coverage=0.67,
        sequence_valid=True,
    )
    risk_assessment = RiskAssessment(
        rationale=("ok",),
        snapshot_date=date(2026, 6, 19),
        indicators=IndicatorSnapshot(
            date=date(2026, 6, 19),
            sma=Decimal("1000"),
            ema=Decimal("1010"),
            rsi=Decimal("55"),
        ),
        gate_triggered=None,
        gate_is_structural=None,
        gate_confidence=None,
    )
    trade_setup = TradeSetup(
        ticker="BBCA",
        snapshot_date=date(2026, 6, 19),
        action=SetupAction.WATCH,
        signal_score=72,
        signal_score_raw=72,
        signal_strength=SignalStrength.MODERATE,
        blocking_gates=(),
        regime=None,
        signal_multiplier=1.0,
        gate_tightening=False,
        rationale="watch",
    )
    candidate = _candidate(
        setup_phase=setup_phase,
        risk_assessment=risk_assessment,
        trade_setup=trade_setup,
        latest_candle_date=date(2026, 6, 19),
        latest_broker_date=date(2026, 6, 19),
    )
    results = {
        7: AccumulationScreenResponse(
            candidates=[candidate],
            screened_at=date(2026, 6, 19),
            window_days=7,
            total_tickers_checked=1,
            tickers_skipped=0,
            provider="stockbit",
        ),
    }

    projection = project_multi_screen_result(
        results,
        tracked_broker_flow=None,
        windows=[7],
        top=10,
        sort_by="avg",
        squeeze_only=False,
        coiled_spring_min_accum_score=_CFG.coiled_spring_min_accum_score,
        coiled_spring_bb_pctile=_CFG.coiled_spring_bb_pctile,
        canonical_window=7,
        effective_session=_FAKE_EFFECTIVE_SESSION,
    )

    display_multi(
        rows=projection.rows,
        universe_label="lq45",
        windows=projection.resolved_windows,
        screened_at=date(2026, 6, 19),
        display_config=_CFG,
        canonical_window=projection.canonical_window,
    )

    out = capsys.readouterr().out
    assert "Signal" in out
    assert "Risk" in out
    assert "Phase" in out
    assert "Data" in out
    assert "Next" in out
    assert "ACCUMULATION" in out
    assert "WATCH" in out
    assert "N/A" in out  # broker quality missing
    assert "Disc%" in out


def test_display_results_renders_phase_column_and_note(capsys):
    from src.domain.value_objects.setup_phase import SetupPhaseSnapshot, SetupPhaseState

    setup_phase = SetupPhaseSnapshot(
        current_phase=SetupPhaseState.ACCUMULATION,
        previous_phase=None,
        phase_age_sessions=1,
        phase_detection_strength=0.6,
        phase_input_coverage=0.67,
        sequence_valid=True,
    )
    response = AccumulationScreenResponse(
        candidates=[_candidate(setup_phase=setup_phase)],
        screened_at=date(2026, 6, 19),
        window_days=7,
        total_tickers_checked=1,
        tickers_skipped=0,
        provider="stockbit",
    )

    display_results(
        response=response,
        candidates=response.candidates,
        universe_label="lq45",
        show_top_broker=False,
        display_config=_CFG,
        include_detail=False,
    )

    out = capsys.readouterr().out
    assert "Phase" in out
    assert "ACCUMULATION" in out
    assert "accumulation-lifecycle diagnostic" in out
    # ADR-054: deep judgment is screen; structure is plan (no --setup required).
    assert "saham screen accum" in out
    assert "saham plan swing" in out
    assert "MATCH" in out or "MATCH ≠" in out or "pattern" in out.lower()
    assert "Disc%" in out


def test_display_results_shows_unknown_phase_when_detection_unavailable(capsys):
    response = AccumulationScreenResponse(
        candidates=[_candidate()],
        screened_at=date(2026, 6, 19),
        window_days=7,
        total_tickers_checked=1,
        tickers_skipped=0,
        provider="stockbit",
    )

    display_results(
        response=response,
        candidates=response.candidates,
        universe_label="lq45",
        show_top_broker=False,
        display_config=_CFG,
        include_detail=False,
    )

    out = capsys.readouterr().out
    assert "UNKNOWN" in out


def test_display_multi_with_explanation_signal_auth(capsys):
    # Test G: Multi Display
    from src.application.services.screen_accum_result_projector import ScreenAccumMultiRow

    row = ScreenAccumMultiRow(
        ticker="BBCA",
        candidates_by_window={7: _candidate(accum_score=72.0, window_days=7)},
        pattern="sustained",
        trend="UP",
        tracked_broker_flow=None,
        canonical_window=7,
        canonical_candidate=_candidate(accum_score=72.0, window_days=7),
        signal_score=72.0,
        signal_authority_coverage=0.83,
        risk_status="OPEN",
        setup_phase="ACCUMULATION",
        data_status="ALIGNED",
        next_action="WATCH",
    )

    display_multi(
        rows=[row],
        universe_label="lq45",
        windows=[7],
        screened_at=date(2026, 6, 19),
        display_config=_CFG,
        include_detail=True,
        canonical_window=7,
    )

    out = capsys.readouterr().out
    # Table + Run Context both use Signal for SignalEngine total.
    assert "Signal" in out
    assert "72/0.83" in out
    assert "SignalEngine total score" in out
    assert "canonical window" in out
