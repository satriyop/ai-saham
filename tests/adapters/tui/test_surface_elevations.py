"""Remaining TUI surface elevations: paper, preopen, broker, ticker, health posters."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace

from rich.text import Text

from src.adapters.tui.board_cell_markup import (
    format_broker_list_cells,
    format_preopen_board_cells,
    format_preopen_delta_cell,
    format_signed_flow_cell,
)
from src.adapters.tui.empty_stage_body import format_empty_stage_body
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.paper_log_display import (
    format_paper_confirm_body,
    format_paper_outcome_tape,
    plan_text_from_structure,
)
from src.adapters.tui.paper_log_result import PaperLogResult, refuse_paper_log
from src.adapters.tui.plan_structure_result import PlanStructureResult
from src.adapters.tui.presenters.accum_presenter import AccumPresenter
from src.adapters.tui.screens.paper_log_confirm import PaperLogConfirmModal
from src.adapters.tui.ticker_desk_present import (
    format_harga_mast,
    format_ticker_desk_from_dashboard,
    format_ticker_desk_from_text,
)
from src.adapters.tui.widgets.plan_desk import PlanDesk


def test_paper_confirm_body_uses_geometry_not_action_invent():
    body = format_paper_confirm_body(
        ticker="BBCA",
        entry="6,225",
        stop="5,900",
        target="6,800",
        lots="3",
        plan_id="3f88eda7",
    )
    assert "6,225" in body and "5,900" in body and "6,800" in body
    assert "3" in body
    assert "paper only" in body.lower() or "no broker order" in body.lower()
    assert "ENTER" not in body  # does not invent Action
    assert "notebook" in body.lower() or "NOTEBOOK" in body


def test_paper_outcome_tape_written_and_refused():
    ok = format_paper_outcome_tape(
        PaperLogResult(
            ticker="BBCA",
            written=True,
            message="logged BBCA",
            planned_entry="6225",
            planned_stop="5900",
            planned_target="6800",
            plan_id="abc",
        )
    )
    assert "LOGGED" in ok or "logged" in ok.lower()
    assert "BBCA" in ok
    assert "no broker order" in ok.lower() or "paper only" in ok.lower()

    bad = format_paper_outcome_tape(refuse_paper_log("ASII", "no capital"))
    assert "REFUSED" in bad or "refused" in bad.lower()
    assert "no capital" in bad
    assert "no write" in bad.lower() or "refused" in bad.lower()


def test_plan_text_from_structure_fields_only():
    struct = PlanStructureResult(
        summary="structure WATCH · entry 1 · no order",
        ticker="BBRI",
        action="WATCH",
        entry="4,825",
        stop="4,600",
        target="5,275",
        lots="2",
        plan_id_short="deadbeef",
    )
    text = plan_text_from_structure(struct, ticker="BBRI")
    assert "4,825" in text and "4,600" in text and "5,275" in text
    assert "deadbeef" in text


def test_preopen_board_cells_contract_and_delta_tint():
    row = SimpleNamespace(
        ticker="BBRI",
        iep="4,820",
        delta_pct="+1.8",
        iev="12.4M",
        ncp="0.92",
        delta_iev="+2.1M",
        grade="A",
        risk="clear",
    )
    cells = format_preopen_board_cells(row)
    assert len(cells) == 8
    plains = [c.plain if isinstance(c, Text) else str(c) for c in cells]
    assert plains[0] == "BBRI"
    assert plains[1] == "4,820"
    assert "+1.8" in plains[2]
    assert plains[6] == "A"
    assert "clear" in plains[7].lower()
    d = format_preopen_delta_cell("+1.8")
    assert isinstance(d, Text)
    assert "+1.8" in d.plain


def test_broker_list_cells_contract_and_sign_tint():
    row = SimpleNamespace(
        code="YP",
        type_label="Local",
        as_of="07-29",
        day_net="+11.5B",
        net5="+38.2B",
        streak="4",
        delta1="+2.1B",
        tickers="18",
        top_buy="AMMN",
    )
    cells = format_broker_list_cells(row)
    assert len(cells) == 9
    plains = [c.plain if isinstance(c, Text) else str(c) for c in cells]
    assert plains[0] == "YP"
    assert plains[3] == "+11.5B"
    assert plains[4] == "+38.2B"
    assert plains[8] == "AMMN"
    pos = format_signed_flow_cell("+11.5B")
    neg = format_signed_flow_cell("−6.2B")
    assert "+11.5B" in pos.plain
    assert "6.2B" in neg.plain


def test_harga_mast_never_action():
    """Price mast product title is LAST · LOCAL CLOSE (not design jargon HARGA)."""
    mast = format_harga_mast(ticker="BBCA", price="6,275", as_of="2026-07-29")
    assert "LAST · LOCAL CLOSE" in mast
    assert "HARGA" not in mast
    assert "6,275" in mast
    assert "local cache" in mast.lower() or "browse" in mast.lower()
    # Must not invent board Action chips as authority stamps
    assert " ENTER " not in f" {mast} "
    assert "WATCH" not in mast
    assert "not Action" not in mast  # no authority slogans on operator mast

    dash = SimpleNamespace(
        ticker="BBCA",
        latest_close=Decimal("6275"),
        as_of=__import__("datetime").date(2026, 7, 29),
        price_structure=None,
    )
    full = format_ticker_desk_from_dashboard(dash, body="Close 6,275\nFresh ok\n")
    assert "6,275" in full or "6275" in full
    assert "LAST · LOCAL CLOSE" in full or "BBCA" in full
    assert "HARGA" not in full
    assert "ENTER" not in full
    assert "not Action" not in full

    from_text = format_ticker_desk_from_text(ticker="TLKM", body="Last: 3,180\nmore")
    assert "TLKM" in from_text
    assert "3,180" in from_text or "LAST · LOCAL CLOSE" in from_text
    assert "HARGA" not in from_text


def test_health_posters_distinct():
    empty = format_empty_stage_body(cache_status="empty")
    lag = format_empty_stage_body(cache_status="lag")
    ready = format_empty_stage_body(cache_status="ready")
    zero = format_empty_stage_body(
        cache_status="ready",
        board_kind="accum",
        board_title="Screen · accumulation",
        meta="0 candidates",
    )
    assert "No local market data" in empty
    assert "lag" in lag.lower()
    assert "ready" in ready.lower()
    assert "0" in zero.lower() or "candidate" in zero.lower()
    # distinct poster labels
    titles = {empty.splitlines()[0], lag.splitlines()[0], ready.splitlines()[0]}
    assert len(titles) >= 2


def test_cockpit_preopen_and_broker_paint_chips():
    async def scenario() -> None:
        app = CockpitApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.05)
            # preopen board
            app._stage = "preopen"
            app._board_kind = "preopen"
            app._rows = [
                SimpleNamespace(
                    ticker="BBRI",
                    iep="4,820",
                    delta_pct="+1.8",
                    iev="12.4M",
                    ncp="0.92",
                    delta_iev="+2.1M",
                    grade="A",
                    risk="clear",
                )
            ]
            app._row_index = 0
            app._render_board_table()
            await pilot.pause(0.05)
            from textual.widgets import DataTable

            dt = app.query_one("#board-table", DataTable)
            grade = dt.get_cell_at((0, 6))
            gplain = grade.plain if isinstance(grade, Text) else str(grade)
            assert "A" in gplain
            delta = dt.get_cell_at((0, 2))
            dplain = delta.plain if isinstance(delta, Text) else str(delta)
            assert "1.8" in dplain

            # broker list
            app._stage = "broker-list"
            app._broker_rows = [
                SimpleNamespace(
                    code="YP",
                    type_label="Local",
                    as_of="07-29",
                    day_net="+11.5B",
                    net5="+38.2B",
                    streak="4",
                    delta1="+2.1B",
                    tickers="18",
                    top_buy="AMMN",
                )
            ]
            app._broker_row_index = 0
            app._render_board_table()
            await pilot.pause(0.05)
            code = dt.get_cell_at((0, 0))
            cplain = code.plain if isinstance(code, Text) else str(code)
            assert "YP" in cplain
            day = dt.get_cell_at((0, 3))
            day_plain = day.plain if isinstance(day, Text) else str(day)
            assert "11.5B" in day_plain

    asyncio.run(scenario())


def test_cockpit_paper_confirm_and_outcome_on_plan():
    async def scenario() -> None:
        app = CockpitApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.05)
            app._focus_ticker = "BBCA"
            app._stage = "accum"
            app._board_kind = "accum"
            app._rows = [
                SimpleNamespace(
                    ticker="BBCA",
                    signal="84",
                    accum="48",
                    action="WATCH",
                    gate="OPEN",
                    source=None,
                )
            ]
            app._row_index = 0
            app._plan_ticker = "BBCA"
            app._plan_structure = PlanStructureResult(
                summary="structure WATCH · entry 6,225 · 3 lots · no order",
                ticker="BBCA",
                action="WATCH",
                entry="6,225",
                stop="5,900",
                target="6,800",
                lots="3",
                plan_id_short="abc12345",
                inherits_action=True,
                no_order=True,
            )
            app._plan_running = False
            app._stage = "plan"
            app._refresh_chrome()
            await pilot.pause(0.05)

            # open confirm via real action path builder
            from src.adapters.tui.paper_log_display import plan_text_from_structure

            plan_text = plan_text_from_structure(app._plan_structure, ticker="BBCA")
            assert "6,225" in plan_text

            # simulate paper log done → tape on plan desk
            app._paper_outcome = format_paper_outcome_tape(
                PaperLogResult(
                    ticker="BBCA",
                    written=True,
                    message="logged BBCA from plan",
                    planned_entry="6225",
                    planned_stop="5900",
                    planned_target="6800",
                    plan_id="abc12345",
                )
            )
            app._status_note = "paper logged"
            app._refresh_chrome()
            await pilot.pause(0.1)
            desk = app.query_one("#plan-desk", PlanDesk)
            assert desk.display is True
            tape = str(app.query_one("#pd-paper-tape").render())
            assert "PAPER" in tape or "LOGGED" in tape or "logged" in tape.lower()
            assert "BBCA" in tape
            assert "broker order" in tape.lower() or "paper" in tape.lower()

            # modal compose uses plan_text
            modal = PaperLogConfirmModal(plan_text=plan_text, ticker="BBCA")
            assert "6,225" in modal._plan_text
            assert "no broker" in modal._plan_text.lower() or "paper" in modal._plan_text.lower()

    asyncio.run(scenario())


def test_cockpit_ticker_detail_harga_widget():
    from src.adapters.tui.ticker_desk_model import build_ticker_desk_model_from_text
    from src.adapters.tui.widgets.ticker_desk import TickerDesk

    async def scenario() -> None:
        def loader(t: str):
            return build_ticker_desk_model_from_text(
                ticker=t,
                body="Close: 6,275\nRSI 48\nnot Action dashboard body\n",
            )

        app = CockpitApp(ticker_detail_loader=loader)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause(0.05)
            app._focus_ticker = "BBCA"
            app._stage = "accum"
            app._board_kind = "accum"
            app._rows = [
                SimpleNamespace(
                    ticker="BBCA",
                    signal="84",
                    accum="48",
                    action="WATCH",
                    gate="OPEN",
                    source=None,
                )
            ]
            app._row_index = 0
            app._run_command("view-ticker")
            for _ in range(40):
                await pilot.pause(0.05)
                if (
                    app._stage == "detail"
                    and app._status_note == "view ticker"
                    and app._ticker_desk_model is not None
                ):
                    break
            desk = app.query_one("#ticker-desk", TickerDesk)
            assert desk.display is True
            price = str(app.query_one("#td-price").render())
            assert "6,275" in price
            lab = str(app.query_one("#td-mast-lab").render()).upper()
            assert "LAST" in lab or "LOCAL" in lab
            # Design pulse trio exists
            assert "FOREIGN" in str(app.query_one("#td-pulse-t-flow").render()).upper()

    asyncio.run(scenario())


def test_layout_board_table_not_collapsed():
    c = SimpleNamespace(
        ticker="BBCA",
        accum_score=48.2,
        rsi=48.0,
        consecutive_streak=2,
        net_buy_ratio=0.5,
        vwap_discount_pct=0.2,
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
            rationale="ok",
            blocking_gates=(),
        ),
        signal_assessment=SimpleNamespace(
            assessment=SimpleNamespace(
                score=84,
                strength=SimpleNamespace(value="MODERATE"),
                entry_quality=SimpleNamespace(value="WATCH"),
                signal_authority_coverage=0.9,
                breakdown=None,
                decision_constraints=None,
            ),
            setup_readiness=None,
            coverage_warning=None,
            signal_authority_coverage=0.9,
        ),
        risk_assessment=SimpleNamespace(
            gate_triggered=None,
            gate_is_structural=False,
            rationale=("ok",),
            risk_level_name="OPEN",
        ),
        risk_gate_evaluations=(),
    )
    result = SimpleNamespace(
        single_projection=SimpleNamespace(
            candidates=[c] * 8,
            window_days=7,
            data_as_of={"latest_candle_date": "2026-07-29"},
            applied_filters=SimpleNamespace(sort_by="signal", top=20),
        ),
        multi_projection=None,
        warnings=(),
        effective_session=None,
        market_context=None,
    )

    async def scenario() -> None:
        app = CockpitApp(
            accum_loader=lambda: result,
            accum_presenter=AccumPresenter(),
        )
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause(0.05)
            app._on_accum_payload(result)
            await pilot.pause(0.15)
            table = app.query_one("#board-table")
            assert table.display is True
            assert table.size.height >= 10, table.size

    asyncio.run(scenario())
