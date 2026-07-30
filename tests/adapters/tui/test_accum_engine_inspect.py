"""Present-only screen-accum engine inspect (Enter view)."""

from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace

from src.adapters.shared.screen_accum_board_fields import extract_screen_accum_board_fields
from src.adapters.tui.controllers.board_controller import BoardController
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.presenters.accum_engine_inspect_presenter import (
    present_accum_engine_inspect,
)
from src.adapters.tui.presenters.accum_presenter import AccumPresenter


def _gate(name: str, outcome: str = "pass", triggered: bool = False, reason: str = "ok"):
    return SimpleNamespace(
        gate=name,
        tier="structural",
        outcome=outcome,
        triggered=triggered,
        reason=reason,
        confidence=100,
    )


def _candidate(
    *,
    ticker: str = "INDF",
    signal: int = 76,
    accum: float = 57.1,
    readiness: object | None = "none",
) -> SimpleNamespace:
    if readiness == "none":
        setup_readiness = None
    elif readiness == "unavailable":
        setup_readiness = SimpleNamespace(
            status=SimpleNamespace(value="UNAVAILABLE"),
            setup_family="pullback",
            missing_required_inputs=("setup_evidence",),
            failed_requirements=(),
        )
    else:
        setup_readiness = readiness

    components = (
        SimpleNamespace(key="cons", score_points=28.5, status=SimpleNamespace(value="AVAILABLE")),
        SimpleNamespace(key="streak", score_points=14.4, status=SimpleNamespace(value="AVAILABLE")),
        SimpleNamespace(key="vwap", score_points=0.0, status=SimpleNamespace(value="AVAILABLE")),
        SimpleNamespace(key="bb", score_points=None, status=SimpleNamespace(value="DISABLED")),
        SimpleNamespace(key="inst", score_points=12.5, status=SimpleNamespace(value="AVAILABLE")),
    )
    assessment = SimpleNamespace(
        score=signal,
        strength=SimpleNamespace(value="STRONG"),
        entry_quality=SimpleNamespace(value="WATCH"),
        signal_authority_coverage=0.0,
        breakdown=(("flow_confirmation_group", 76.11), ("signal_authority_coverage", 0.0)),
        decision_constraints=SimpleNamespace(
            max_decision="WATCH",
            regime=None,
            constraint_reasons=("RISK_ON ENTER requires signal_authority_coverage >= 70%",),
        ),
        alpha_trigger_score=None,
    )
    return SimpleNamespace(
        ticker=ticker,
        accum_score=accum,
        rsi=56.5,
        consecutive_streak=5,
        net_buy_ratio=0.86,
        vwap_discount_pct=-0.6,
        current_price=6875,
        latest_candle_date=date(2026, 7, 27),
        latest_broker_date=date(2026, 7, 24),
        freshness=SimpleNamespace(
            candle_as_of=date(2026, 7, 27),
            broker_as_of=date(2026, 7, 24),
            alignment_state=SimpleNamespace(value="LAG"),
            candle_state=SimpleNamespace(value="OK"),
            broker_state=SimpleNamespace(value="STALE"),
        ),
        setup_phase=SimpleNamespace(current_phase=SimpleNamespace(value="ACCUMULATION")),
        trade_setup=SimpleNamespace(
            action=SimpleNamespace(value="WATCH", short="WATCH"),
            signal_score=signal,
            signal_strength=SimpleNamespace(value="STRONG"),
            rationale="Signal 76/100 (STRONG) | gate: open",
            blocking_gates=(),
        ),
        signal_assessment=SimpleNamespace(
            assessment=assessment,
            setup_readiness=setup_readiness,
            coverage_warning="Incomplete signal authority coverage",
            signal_authority_coverage=0.0,
        ),
        risk_assessment=SimpleNamespace(
            gate_triggered=None,
            rationale=("all gates passed",),
            risk_level_name="OPEN",
        ),
        risk_gate_evaluations=(
            _gate("FundamentalGate"),
            _gate("LiquidityGate"),
            _gate("BandarGate"),
        ),
        accum_score_breakdown=SimpleNamespace(components=components, accum_score=accum),
        name=f"{ticker} Corp",
    )


def _row(candidate: SimpleNamespace | None = None):
    c = candidate or _candidate()
    view = AccumPresenter().present(
        SimpleNamespace(
            single_projection=SimpleNamespace(
                candidates=[c],
                window_days=7,
                data_as_of={},
                applied_filters=SimpleNamespace(sort_by="signal", top=20),
            )
        )
    )
    return view.rows[0], view


def test_inspect_sections_and_board_parity():
    row, board = _row()
    session = SimpleNamespace(
        market_session_name="AFTER_CLOSE",
        analysis_as_of=date(2026, 7, 28),
        latest_completed_session=date(2026, 7, 28),
        resolution_source="ihsg_cache",
    )
    inspect = present_accum_engine_inspect(
        row,
        rank=1,
        total=1,
        board_summary=board.summary,
        effective_session=session,
    )
    text = inspect.text
    assert "Judge · INDF" in text or "INDF" in text
    for section in (
        "Judgment",
        "Decision",
        "Signal",
        "Risk",
        "TradeSetup",
        "Accum (screen)",
        "Data",
        "Session",
        "Market context",
    ):
        assert section in text
    assert "Action WATCH · Gate OPEN" in text or "Action" in text
    assert "← Signal" in text
    assert "← Why:" in text
    assert "not evaluated" in text or "Named setups" in text
    assert "flow-only" in text  # readiness None + no family
    assert "AFTER_CLOSE" in text
    assert "Accum breakdown" in text or "breakdown:" in text or "Accum brk" in text
    assert "recipe" not in text.lower()

    fields = extract_screen_accum_board_fields(row.source, phase_style="short")
    assert f"Signal {fields.signal}" in text or f"← Signal {fields.signal}" in text
    assert f"Accum {fields.accum}" in text or f"total {fields.accum}" in text
    assert fields.action in text
    assert fields.gate in text


def test_inspect_readiness_when_present():
    row, _ = _row(_candidate(readiness="unavailable"))
    text = present_accum_engine_inspect(row).text
    assert "UNAVAILABLE" in text
    assert "setup_evidence" in text


def test_inspect_display_market_context():
    row, _ = _row()
    mc = SimpleNamespace(
        regime=SimpleNamespace(value="NEUTRAL"),
        conviction=0.5,
        regime_confidence=0.4,
        regime_stability="STABLE",
        days_in_regime=2,
        staleness_warning=None,
        coverage_warning=None,
        transition_warning=None,
    )
    text = present_accum_engine_inspect(row, market_context=mc).text
    assert "regime NEUTRAL" in text
    assert "stability STABLE" in text
    assert "not evaluated for this screen run" not in text


def test_inspect_sparse_no_crash():
    row = SimpleNamespace(
        ticker="X",
        signal="—",
        accum="—",
        action="—",
        gate="—",
        phase="—",
        streak="—",
        rsi="—",
        net_pct="—",
        disc_pct="—",
        price="—",
        source=None,
    )
    text = present_accum_engine_inspect(row).text  # type: ignore[arg-type]
    assert "Signal" in text
    assert "Risk" in text
    assert "Decision" in text


def test_enter_opens_inspect_and_esc_returns():
    async def scenario() -> None:
        c = _candidate()
        result = SimpleNamespace(
            single_projection=SimpleNamespace(
                candidates=[c],
                window_days=7,
                data_as_of={},
                applied_filters=SimpleNamespace(sort_by="signal", top=20),
            ),
            effective_session=SimpleNamespace(
                market_session_name="AFTER_CLOSE",
                analysis_as_of=date(2026, 7, 28),
                latest_completed_session=date(2026, 7, 28),
                resolution_source="test",
            ),
            market_context=SimpleNamespace(
                regime=SimpleNamespace(value="RISK_ON"),
                conviction=0.8,
                regime_confidence=None,
                regime_stability=None,
                days_in_regime=None,
                staleness_warning=None,
                coverage_warning=None,
                transition_warning=None,
            ),
            multi_projection=None,
            warnings=(),
        )
        loader = lambda: result  # noqa: E731
        app = CockpitApp(
            accum_loader=loader,
            accum_controller=BoardController(loader),
            accum_presenter=AccumPresenter(),
        )
        async with app.run_test(size=(120, 40)) as pilot:
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum" and app._rows:
                    break
            assert app._stage == "accum"
            assert app._effective_session is not None
            app._open_detail()  # board Enter judge (not palette view-ticker)
            await pilot.pause()
            assert app._stage == "detail"
            assert "Judge" in app._board_title
            assert app._status_note == "judge"
            assert "Decision" in app._detail_text
            assert "Signal" in app._detail_text
            assert "Risk" in app._detail_text
            assert "regime RISK_ON" in app._detail_text
            assert "present-only" in app._meta or "re-judge" in app._meta
            await pilot.press("escape")
            await pilot.pause()
            assert app._stage == "accum"

    asyncio.run(scenario())
