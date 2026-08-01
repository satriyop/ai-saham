"""Remaining TUI surface elevations: paper, preopen, broker, ticker, health posters."""

from __future__ import annotations

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
        net3="+10.0B",
        net5="+38.2B",
        net7="+40.0B",
        net10="+50.0B",
        net20="+60.0B",
        streak="4",
        delta1="+2.1B",
        tickers="18",
        top_buy="AMMN",
    )
    cells = format_broker_list_cells(row)
    # Code Type AsOf DayNet Net3 Net5 Net7 Net10 Net20 Stk Δ1 # Top
    assert len(cells) == 13
    plains = [c.plain if isinstance(c, Text) else str(c) for c in cells]
    assert plains[0] == "YP"
    assert plains[3] == "+11.5B"
    assert plains[4] == "+10.0B"  # Net3
    assert plains[5] == "+38.2B"  # Net5
    assert plains[6] == "+40.0B"  # Net7
    assert plains[7] == "+50.0B"  # Net10
    assert plains[8] == "+60.0B"  # Net20
    assert plains[12] == "AMMN"
    pos = format_signed_flow_cell("+11.5B")
    neg = format_signed_flow_cell("−6.2B")
    assert "+11.5B" in pos.plain
    assert "6.2B" in neg.plain

    from src.adapters.tui.board_cell_markup import (
        format_of_max_pct_label,
        format_of_max_pct_markup,
        format_scalar_bar_markup,
        format_signed_flow_markup,
        signed_flow_color,
    )

    # Static radar rows share the same mint/coral rule as DataTable cells
    assert signed_flow_color("+11.5B") == "#6fbf8a"
    assert signed_flow_color("−6.2B") == "#c97a72"
    assert signed_flow_color("12.88B") == "#6fbf8a"
    assert format_signed_flow_markup("+9.45B", width=8) == "[#6fbf8a]  +9.45B[/]"
    assert format_signed_flow_markup("-1.61B", width=8) == "[#c97a72]  -1.61B[/]"

    # Scalar bar contract: bar fill and % label share the same of-max number
    assert format_of_max_pct_label(42) == "42%"
    assert format_of_max_pct_label(100) == "100%"
    assert format_of_max_pct_markup(42, width=4) == "[#7a7a7a] 42%[/]"
    bar42 = format_scalar_bar_markup(42, width=10, tone="#6fbf8a")
    assert "█" in bar42 and "░" in bar42
    assert "#6fbf8a" in bar42
    empty_bar = format_scalar_bar_markup(0, width=8)
    assert empty_bar.count("░") == 8


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


def test_preopen_and_broker_board_cell_contracts():
    """Cell contracts for preopen grade/delta and broker day-net (no app mount)."""
    pre_row = SimpleNamespace(
        ticker="BBRI",
        iep="4,820",
        delta_pct="+1.8",
        iev="12.4M",
        ncp="0.92",
        delta_iev="+2.1M",
        grade="A",
        risk="clear",
    )
    cells = format_preopen_board_cells(pre_row)
    plains = [c.plain if isinstance(c, Text) else str(c) for c in cells]
    assert any("A" in p for p in plains)
    assert any("1.8" in p for p in plains)

    broker_row = SimpleNamespace(
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
    bcells = format_broker_list_cells(broker_row)
    bplains = [c.plain if isinstance(c, Text) else str(c) for c in bcells]
    assert any("YP" in p for p in bplains)
    assert any("11.5B" in p for p in bplains)


def test_paper_confirm_and_outcome_tape_pure():
    """Plan → paper confirm body + outcome tape (pure formatters)."""
    from src.adapters.tui.paper_log_display import plan_text_from_structure

    structure = PlanStructureResult(
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
    plan_text = plan_text_from_structure(structure, ticker="BBCA")
    assert "6,225" in plan_text

    tape = format_paper_outcome_tape(
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
    assert "PAPER" in tape or "LOGGED" in tape or "logged" in tape.lower()
    assert "BBCA" in tape
    assert "broker order" in tape.lower() or "paper" in tape.lower()

    modal = PaperLogConfirmModal(plan_text=plan_text, ticker="BBCA")
    assert "6,225" in modal._plan_text
    assert "no broker" in modal._plan_text.lower() or "paper" in modal._plan_text.lower()


def test_ticker_detail_harga_mast_pure():
    from src.adapters.tui.ticker_desk_model import build_ticker_desk_model_from_text

    model = build_ticker_desk_model_from_text(
        ticker="BBCA",
        body="Close: 6,275\nRSI 48\nnot Action dashboard body\n",
    )
    assert "6,275" in model.price
    assert "LAST" in model.as_text().upper() or "LOCAL" in model.as_text().upper()
    flow = next(p for p in model.pulses if p.key == "flow")
    assert "FOREIGN" in flow.title.upper()


def test_layout_board_table_row_payload_not_collapsed():
    """Board paint has multi-row payload contract (layout height is residual e2e)."""
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
    candidates = [c] * 8
    assert len(candidates) >= 8

    result = SimpleNamespace(
        single_projection=SimpleNamespace(
            candidates=candidates,
            window_days=7,
            data_as_of={"latest_candle_date": "2026-07-29"},
            applied_filters=SimpleNamespace(sort_by="signal", top=20),
        ),
        multi_projection=None,
        warnings=(),
        effective_session=None,
        market_context=None,
    )
    board = AccumPresenter().present(result)
    assert len(board.rows) >= 8
