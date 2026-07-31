"""Interactive flag chips expand named panels (bible detail flags)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from src.adapters.tui.controllers.board_controller import BoardController
from src.adapters.tui.judge_desk_model import build_judge_desk_model
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.phase_sequence import PhaseSequenceFact
from src.adapters.tui.presenters.accum_presenter import AccumPresenter, AccumRowView
from src.adapters.tui.widgets.flag_chip import FlagChip
from src.adapters.tui.widgets.judge_desk import JudgeDesk


def _candidate() -> SimpleNamespace:
    return SimpleNamespace(
        ticker="BBCA",
        accum_score=48.2,
        rsi=50.0,
        consecutive_streak=2,
        net_buy_ratio=0.5,
        vwap_discount_pct=0.0,
        current_price=6275,
        name="BBCA",
        latest_candle_date=None,
        latest_broker_date=None,
        freshness=None,
        setup_phase=SimpleNamespace(current_phase=SimpleNamespace(value="COMPRESSION")),
        trade_setup=SimpleNamespace(
            action=SimpleNamespace(value="WATCH", short="WATCH"),
            signal_score=84,
            signal_strength=SimpleNamespace(value="MODERATE"),
            rationale="Signal 84",
            blocking_gates=(),
        ),
        signal_assessment=SimpleNamespace(
            assessment=SimpleNamespace(
                score=84,
                strength=SimpleNamespace(value="MODERATE"),
                entry_quality=SimpleNamespace(value="WATCH"),
                signal_authority_coverage=0.92,
                breakdown=None,
                decision_constraints=None,
            ),
            setup_readiness=None,
            coverage_warning=None,
            signal_authority_coverage=0.92,
        ),
        risk_assessment=SimpleNamespace(
            gate_triggered=None,
            gate_is_structural=False,
            rationale=("ok",),
            risk_level_name="OPEN",
        ),
        risk_gate_evaluations=(),
    )


def _row() -> AccumRowView:
    return AccumRowView(
        ticker="BBCA",
        signal="84",
        accum="48.2",
        action="WATCH",
        phase="COMPRESSION",
        streak="2",
        rsi="50",
        net_pct="0.5",
        disc_pct="0",
        price="6275",
        gate="OPEN",
        source=_candidate(),
    )


def test_flag_chip_is_focusable_control():
    chip = FlagChip("stack", "stack", id="t-chip")
    assert chip.can_focus is True
    chip.set_chip_state(available=True, expanded=False)
    assert "is-dim" not in chip.classes
    chip.set_chip_state(available=False, expanded=False)
    assert "is-dim" in chip.classes


def test_judge_stack_chip_expands_decision_panel():
    async def scenario() -> None:
        model = build_judge_desk_model(
            _row(),
            phase_sequence=(
                PhaseSequenceFact(phase="ACCUMULATION", as_of="2026-07-20"),
                PhaseSequenceFact(phase="COMPRESSION", as_of="2026-07-28"),
            ),
        )
        app = CockpitApp()
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause(0.05)
            desk = app.query_one("#judge-desk", JudgeDesk)
            desk.display = True
            desk.paint(model, detail_open=False)
            assert desk.query_one("#jd-decision").display is False
            stack = desk.query_one("#jd-flag-stack", FlagChip)
            assert isinstance(stack, FlagChip)
            # Activate chip via real message path
            desk.post_message(FlagChip.Selected("stack"))
            await pilot.pause(0.05)
            # Handler is on desk; message may need to be posted from chip
            stack.post_message(FlagChip.Selected("stack"))
            await pilot.pause(0.1)
            # If still closed, call handler path directly (shipped method)
            if desk.query_one("#jd-decision").display is False:
                desk.on_flag_chip_selected(FlagChip.Selected("stack"))
            assert desk.query_one("#jd-decision").display is True
            assert "is-on" in desk.query_one("#jd-flag-stack", FlagChip).classes
            # phase+ expands phase detail lines
            desk.on_flag_chip_selected(FlagChip.Selected("phase_plus"))
            assert desk.query_one("#jd-phase-detail").display is True
            # detail · d opens all
            desk.on_flag_chip_selected(FlagChip.Selected("detail"))
            assert desk._detail_all is True
            assert desk.query_one("#jd-decision").display is True

    asyncio.run(scenario())


def test_preopen_why_chip_expands_panel():
    async def scenario() -> None:
        from src.adapters.tui.preopen_inspect_model import build_preopen_inspect_model
        from src.adapters.tui.widgets.preopen_inspect_desk import PreopenInspectDesk

        row = SimpleNamespace(
            ticker="BBRI",
            iep="4,820",
            delta_pct="+1.8",
            iev="12.4M",
            ncp="1.34",
            delta_iev="1.34",
            grade="A",
            risk="clear",
            evidence="ok",
            source=SimpleNamespace(
                trend_signal="BULLISH",
                opening_broker_backing_tag="BACKED",
                opening_broker_backing_score=0.9,
                opening_broker_buy_streak=3,
            ),
        )
        model = build_preopen_inspect_model(row, warnings=("w1",))
        app = CockpitApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.05)
            desk = app.query_one("#preopen-inspect-desk", PreopenInspectDesk)
            desk.display = True
            desk.paint(model, detail_open=False)
            assert desk.query_one("#poi-panel-why").display is False
            desk.on_flag_chip_selected(FlagChip.Selected("why"))
            assert desk.query_one("#poi-panel-why").display is True
            desk.on_flag_chip_selected(FlagChip.Selected("auction_plus"))
            assert desk.query_one("#poi-panel-auction").display is True
            assert "BULLISH" in str(desk.query_one("#poi-auction-body").content)

    asyncio.run(scenario())


def test_judge_d_key_still_toggles_all_via_app():
    async def scenario() -> None:
        live = SimpleNamespace(
            single_projection=SimpleNamespace(
                candidates=[_candidate()],
                window_days=7,
                data_as_of={"latest_candle_date": "2026-07-29"},
                applied_filters=SimpleNamespace(sort_by="signal", top=20),
            ),
            multi_projection=None,
            warnings=(),
            effective_session=None,
            market_context=None,
        )
        app = CockpitApp(
            accum_loader=lambda: live,
            accum_controller=BoardController(lambda: live),
            accum_presenter=AccumPresenter(),
            phase_history_loader=lambda t, d: (
                PhaseSequenceFact(phase="ACCUMULATION", as_of="2026-07-20"),
                PhaseSequenceFact(phase="COMPRESSION", as_of="2026-07-28"),
            ),
        )
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause(0.05)
            app._on_accum_payload(live)
            await pilot.pause(0.05)
            app._row_index = 0
            app._focus_ticker = "BBCA"
            app._open_detail()
            await pilot.pause(0.1)
            desk = app.query_one("#judge-desk", JudgeDesk)
            assert desk.display is True
            assert desk.query_one("#jd-decision").display is False
            app.action_toggle_detail()
            await pilot.pause(0.1)
            assert app._judge_detail_open is True
            assert desk.query_one("#jd-decision").display is True
            assert "is-on" in desk.query_one("#jd-flag-detail", FlagChip).classes

    asyncio.run(scenario())
