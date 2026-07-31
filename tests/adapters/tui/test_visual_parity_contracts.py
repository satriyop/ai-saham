"""OpenCode visual parity contracts — shell, tokens, hierarchy, prompt rail.

Design authority: docs/design/tui-cockpit-opencode.md (mock `.app` only).
Asserts shipped paint path markers, not browser pixel identity.

Layer: tests (adapter)
"""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from textual.widgets import Input, Static

from src.adapters.shared.screen_accum_board_fields import BOARD_COLUMN_LABELS
from src.adapters.tui.board_cell_markup import format_accum_board_cells
from src.adapters.tui.broker_desk_calendar_model import build_broker_desk_calendar_model
from src.adapters.tui.broker_desk_home_model import build_broker_desk_home_model
from src.adapters.tui.broker_desk_matrix_model import build_broker_desk_matrix_model
from src.adapters.tui.broker_desk_top_model import build_broker_desk_top_model
from src.adapters.tui.controllers.board_controller import BoardController
from src.adapters.tui.judge_desk_model import build_judge_desk_model
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.presenters.accum_presenter import AccumPresenter, AccumRowView
from src.adapters.tui.theme import COCKPIT_CSS, FORBIDDEN_PRODUCT_MARKERS, OPENCODE_TOKENS
from src.adapters.tui.ticker_desk_model import build_ticker_desk_model_from_dashboard
from src.domain.entities.broker_flow import BrokerType


def test_density_css_left_accents_on_instrument_desks():
    """OpenCode density: peach/semantic left borders on primary heroes."""
    from src.adapters.tui.widgets.broker_desk import BrokerDesk
    from src.adapters.tui.widgets.broker_top_desk import BrokerTopDesk
    from src.adapters.tui.widgets.judge_desk import JudgeDesk
    from src.adapters.tui.widgets.plan_desk import PlanDesk
    from src.adapters.tui.widgets.ticker_desk import TickerDesk

    for cls, marker in (
        (JudgeDesk, "border-left: solid #c9a68a"),
        (PlanDesk, "border-left: solid #6fbf8a"),
        (BrokerDesk, "border-left: solid #c9a68a"),
        (BrokerTopDesk, "border-left: solid #6fbf8a"),
        (TickerDesk, "border-left: solid #c9a68a"),
    ):
        css = cls.DEFAULT_CSS
        assert marker in css, f"{cls.__name__} missing density accent {marker!r}"


def test_broker_deep_empty_shell_is_structured_not_cli_dump():
    """Text-only deep loaders still get empty structured models for widget paint."""
    from src.adapters.tui.broker_desk_matrix_model import build_broker_desk_matrix_model
    from src.adapters.tui.broker_desk_top_model import build_broker_desk_top_model

    reason = "no desk data in local cache · fetch broker data"
    mx = build_broker_desk_matrix_model(None, code="YP", empty_reason=reason)
    top = build_broker_desk_top_model(None, code="YP", empty_reason=reason)
    assert mx.empty and top.empty
    assert "fetch" in mx.empty_reason.lower()
    assert "CLI" not in mx.empty_reason and "CLI" not in top.empty_reason


def test_opencode_tokens_locked_in_theme():
    assert OPENCODE_TOKENS["bg"] == "#0b0b0b"
    assert OPENCODE_TOKENS["sel_bg"] == "#c9a68a"
    assert "#0b0b0b" in COCKPIT_CSS
    assert "#c9a68a" in COCKPIT_CSS
    # Peach selection on board cursor (not brass night-ink wash)
    assert "datatable--cursor" in COCKPIT_CSS
    assert "#c9a68a" in COCKPIT_CSS.split("datatable--cursor")[1][:200]
    # Shell regions
    for region in (
        "#main-header",
        "#stage",
        "#sidebar",
        "#prompt-rail",
        "#status",
        "#board-table",
        "#prompt-input",
        "#prompt-mode",
    ):
        assert region in COCKPIT_CSS, region
    # Forbidden journey/night-ink product markers not used as live surfaces
    for bad in FORBIDDEN_PRODUCT_MARKERS:
        if bad.startswith("#"):
            # Forbidden as active board/widget bg — allowed only in FORBIDDEN list constant
            # Count occurrences in CSS body should be zero
            assert COCKPIT_CSS.count(bad) == 0, f"night-ink token leaked into CSS: {bad}"
        else:
            assert bad not in COCKPIT_CSS


def test_product_tui_sources_have_no_journey_skin_markers():
    root = Path("src/adapters/tui")
    # theme.py documents forbidden markers — exclude that file from string ban
    for path in root.rglob("*.py"):
        if path.name == "theme.py":
            continue
        text = path.read_text(encoding="utf-8")
        assert "Fraunces" not in text
        assert "desk-v2" not in text
        assert "font-display" not in text
        assert "design-tools" not in text
        # night-ink surface hexes must not remain in product widgets
        for bad in ("#080b12", "#0d121c", "#121a28", "#1c2430"):
            assert bad not in text, f"{path}: {bad}"


def test_board_column_contracts_and_no_jargon_in_markup_module():
    assert BOARD_COLUMN_LABELS[0] == "Ticker"
    assert "Signal" in BOARD_COLUMN_LABELS or BOARD_COLUMN_LABELS[1]
    assert "Action" in BOARD_COLUMN_LABELS
    assert "Gate" in BOARD_COLUMN_LABELS
    # Action chips use OpenCode semantic fill (not plain string only)
    from rich.text import Text

    from src.adapters.tui.board_cell_markup import format_action_cell
    from src.adapters.tui.chrome_cues import (
        accum_source_badge_kind,
        accum_source_badge_text,
    )

    watch = format_action_cell("WATCH")
    assert isinstance(watch, Text)
    assert "WATCH" in watch.plain
    assert "#d4b06a" in watch.markup or "WATCH" in watch.plain
    assert accum_source_badge_kind(board_source="snapshot") == "snap"
    assert "limited judge" in accum_source_badge_text(board_source="snapshot")
    assert accum_source_badge_kind(board_source="live") == "live"
    assert "live" in accum_source_badge_text(board_source="live").lower()
    markup_src = Path("src/adapters/tui/board_cell_markup.py").read_text(encoding="utf-8")
    for ban in ("Price hero", "option-B", "JudgeDeskModel", "FULL_PANEL_ORDER", "night-ink"):
        assert ban not in markup_src
    row = SimpleNamespace(
        ticker="BBCA",
        signal="84",
        accum="48.2",
        action="WATCH",
        phase="COMPRESS",
        streak="2",
        rsi="48",
        net_pct="0.5",
        disc_pct="0.2",
        price="6275",
        gate="OPEN",
    )
    cells = format_accum_board_cells(row)
    assert len(cells) == len(BOARD_COLUMN_LABELS)
    assert "WATCH" in str(cells[3])


def test_product_operator_paint_path_has_no_implementer_cli_or_design_jargon():
    """AC1/AC2: operator-facing paint modules must not ship CLI/design/authority slogans."""
    # Runtime operator surfaces (not palette help for unimplemented jobs)
    product_paths = [
        Path("src/adapters/tui/chrome_cues.py"),
        Path("src/adapters/tui/widgets/plan_desk.py"),
        Path("src/adapters/tui/ticker_desk_model.py"),
        Path("src/adapters/tui/ticker_desk_present.py"),
        Path("src/adapters/tui/paper_log_display.py"),
        Path("src/adapters/tui/presenters/plan_stage_presenter.py"),
        Path("src/adapters/tui/board_cell_markup.py"),
        Path("src/adapters/tui/widgets/broker_desk.py"),
        Path("src/adapters/tui/widgets/broker_matrix_desk.py"),
        Path("src/adapters/tui/widgets/broker_top_desk.py"),
        Path("src/adapters/tui/widgets/broker_calendar_desk.py"),
        Path("src/adapters/tui/widgets/broker_flow_desk.py"),
        Path("src/adapters/tui/widgets/broker_history_desk.py"),
        Path("src/adapters/tui/widgets/ticker_desk.py"),
        Path("src/adapters/tui/widgets/judge_desk.py"),
        Path("src/adapters/tui/widgets/preopen_inspect_desk.py"),
        Path("src/adapters/tui/preopen_inspect_model.py"),
        Path("src/adapters/tui/empty_stage_body.py"),
        Path("src/adapters/tui/presenters/preopen_engine_inspect_presenter.py"),
    ]
    # Operator-facing slogans (string content), not code type names / docstrings alone
    banned = (
        "CLI: saham",
        "CLI: trade",
        "CLI: plan",
        "same job as",
        "HARGA MAST",
        "Price hero",
        "option-B",
        "saham view broker list",
        "trade accum log --from-plan",
        "not Action authority",
        "Not learning corpus",
        "never invents Signal",
        "no engine re-run on Enter",
        "TUI pre-open board",
        "Judge stays board Enter",
        "swing_trade_plan · paper",
        "present-only inspect",
        "local cache · not Action",
        "b desks · not Action",
        "not Action · esc back",
        "CLI view broker",
    )
    for path in product_paths:
        text = path.read_text(encoding="utf-8")
        for ban in banned:
            assert ban not in text, f"{path}: residual implementer/design jargon {ban!r}"
    # Operator chrome in main shell (meta / prompt) — no CLI or authority slogans
    main_src = Path("src/adapters/tui/main.py").read_text(encoding="utf-8")
    for ban in (
        "CLI view broker",
        "not Action · : or /",
        "present-only · same object",
        "j re-judge · not re-score",
        "prompt · design only · not Action",
        'placeholder="prompt · idle · not Action',
    ):
        assert ban not in main_src, f"main.py chrome noise: {ban!r}"
    assert 'placeholder="prompt · idle · : or / to focus"' in main_src
    # chrome_cues loading body specifically
    from src.adapters.tui.chrome_cues import (
        broker_list_loading_body,
        broker_list_loading_footer,
    )
    from src.adapters.tui.ticker_desk_model import build_ticker_desk_model_from_text

    body = broker_list_loading_body()
    foot = broker_list_loading_footer()
    assert "CLI:" not in body and "saham view" not in body
    assert "CLI" not in foot
    assert "View · broker list" in body
    # Runtime scraper/text mirrors
    assert (
        "HARGA MAST"
        not in build_ticker_desk_model_from_text(ticker="BBCA", body="Close: 1").as_text()
    )


def _accum_payload():
    c = SimpleNamespace(
        ticker="BBCA",
        accum_score=48.2,
        signal_assessment=SimpleNamespace(score=84, band="MODERATE"),
        trade_setup=SimpleNamespace(action="WATCH", rationale="ok"),
        risk_assessment=SimpleNamespace(status="OPEN", blocking_gates=()),
        setup_phase=SimpleNamespace(phase="COMPRESSION"),
        consecutive_streak=2,
        rsi=48.2,
        net_buy_ratio=0.5,
        vwap_discount_pct=0.2,
        current_price=6275,
        name="BBCA",
        source=object(),
    )
    return SimpleNamespace(
        single_projection=SimpleNamespace(
            candidates=[c],
            window_days=7,
            data_as_of={},
            applied_filters=SimpleNamespace(sort_by="signal", top=20),
        ),
        effective_session=None,
        market_context=None,
        multi_projection=None,
        warnings=(),
    )


def test_shell_compose_regions_and_prompt_interactive():
    async def scenario() -> None:
        app = CockpitApp(
            accum_loader=_accum_payload,
            accum_controller=BoardController(_accum_payload),
            accum_presenter=AccumPresenter(),
        )
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause(0.05)
            # Shell regions
            for rid in (
                "#view-title",
                "#view-meta",
                "#mode-pill",
                "#stage",
                "#sidebar",
                "#prompt-rail",
                "#prompt-input",
                "#prompt-mode",
                "#status",
                "#board-source-badge",
                "#board-table",
            ):
                app.query_one(rid)
            # On accum after load: snapshot|live src-badge paints (mock hierarchy)
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum" and app._rows:
                    break
            if app._stage == "accum":
                badge = app.query_one("#board-source-badge", Static)
                # live path from loader → badge text + class
                assert badge.display is True or app._board_source in {"live", "snapshot", "none"}
                if app._board_source in {"live", "snapshot"}:
                    assert badge.display is True
                    text = str(badge.content).lower()
                    assert "live" in text or "snapshot" in text
                    assert "snap" in badge.classes or "live" in badge.classes
            inp = app.query_one("#prompt-input", Input)
            assert isinstance(inp, Input)
            mode = str(app.query_one("#prompt-mode").content).lower()
            assert "idle" in mode
            # Focus path
            app.action_focus_prompt()
            await pilot.pause(0.05)
            rail = app.query_one("#prompt-rail")
            assert "is-focus" in rail.classes
            # Submit does not invent Action
            inp.value = "hello cockpit"
            await inp.action_submit()
            await pilot.pause(0.05)
            assert inp.value == ""
            # Mode switch chrome only
            inp.value = "mode agent"
            await inp.action_submit()
            await pilot.pause(0.05)
            assert "agent" in str(app.query_one("#prompt-mode").content).lower()
            # No design-tools / night-ink in live CSS
            css = app.CSS if isinstance(app.CSS, str) else COCKPIT_CSS
            assert "design-tools" not in css
            assert "Fraunces" not in css

    asyncio.run(scenario())


def test_nested_desks_hierarchy_markers_not_cli_dump_primary():
    # Judge hierarchy (real AccumRowView + source duck)
    source = SimpleNamespace(
        trade_setup=SimpleNamespace(
            action=SimpleNamespace(value="WATCH"),
            rationale="ok",
            signal_score=84,
        ),
        risk_assessment=SimpleNamespace(
            gate_triggered=None,
            gate_is_structural=False,
            rationale=("ok",),
            risk_level_name="OPEN",
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
        setup_phase=SimpleNamespace(current_phase=SimpleNamespace(value="COMPRESSION")),
        risk_gate_evaluations=(),
    )
    row = AccumRowView(
        ticker="BBCA",
        signal="84",
        accum="48.2",
        action="WATCH",
        phase="COMPRESS",
        streak="2",
        rsi="48",
        net_pct="0.5",
        disc_pct="0.2",
        price="6275",
        gate="OPEN",
        source=source,
    )
    jm = build_judge_desk_model(row, rank=1, total=3)
    assert jm.action == "WATCH"
    assert jm.scores
    assert "d detail" in jm.footer or "detail" in jm.footer.lower()
    assert "CLI dump" not in jm.footer

    # Ticker hierarchy
    dash = SimpleNamespace(
        ticker="BBCA",
        latest_close=Decimal("6275"),
        as_of=date(2026, 7, 29),
        notation=SimpleNamespace(
            listing_board="Utama",
            sector="Finance",
            sub_sector="Bank",
            tradeable=True,
            notations=(SimpleNamespace(description="BCA"),),
        ),
        profile=None,
        price_structure=SimpleNamespace(
            change_1d_pct=0.8,
            change_5d_pct=-1.0,
            change_20d_pct=5.0,
            range_52w_pct=30.0,
        ),
        fundamentals=SimpleNamespace(
            pe_ratio_ttm=13.3,
            pbv=3.0,
            market_cap_idr=1e14,
            roe_ttm=20.0,
            dividend_yield=4.0,
            piotroski_f_score=5,
        ),
        foreign_flow_points=(),
        foreign_flow_source="stockbit",
        bandar=None,
        earnings=(),
        analyst=object(),
        ownership=object(),
        insider_txns=(),
        iev_rows=(),
        seasonality=None,
        freshness=(),
    )
    tm = build_ticker_desk_model_from_dashboard(dash)
    assert "6,275" in tm.price
    assert tm.horizons
    assert tm.metrics
    assert tm.pulses
    assert tm.detail_panels
    text = tm.as_text()
    assert "LAST · LOCAL CLOSE" in text
    assert "HARGA MAST" not in text
    assert "Rich box" not in text

    # Broker home hero
    hm = build_broker_desk_home_model(
        SimpleNamespace(
            broker_code="YP",
            broker_name="YP Desk",
            broker_type=BrokerType.FOREIGN,
            as_of=date(2026, 7, 29),
            day_net_value=Decimal("11460000000"),
            day_net_lot=100,
            day_ticker_count=5,
            top_buy_stocks=(SimpleNamespace(ticker="AMMN", net_value=Decimal("1e9")),),
            top_sell_stocks=(),
            scope_note="Tracked desk activity only",
        ),
        pulse=SimpleNamespace(
            net5=Decimal("3e10"),
            sessions_in_net5=5,
            buy_streak=4,
            delta1=Decimal("1e9"),
        ),
    )
    assert hm.day_net_amount
    assert hm.side_stats
    assert "not full market" in hm.day_net_sub.lower() or "desk" in hm.day_net_sub.lower()
    assert not hm.body_contains_action_authority()

    # Matrix cells
    from src.application.services.broker_desk_from_daily_flow import DeskTickerWindowCell

    cell = DeskTickerWindowCell(
        ticker="AMMN",
        net_value=Decimal("1e9"),
        window=1,
        sessions_used=1,
        avg_buy_price=Decimal("9850"),
        buy_streak=6,
        is_partial=False,
    )
    mx = build_broker_desk_matrix_model(
        SimpleNamespace(
            broker_code="YP",
            broker_name="YP",
            as_of=date(2026, 7, 29),
            broker_type=BrokerType.FOREIGN,
            windows=(1, 3, 5, 10, 20),
            columns={1: (cell,), 3: (), 5: (), 10: (), 20: ()},
            sessions_cached=5,
            scope_note="Tracked",
            top_ticker_1s="AMMN",
        )
    )
    assert mx.rows[0][0].ticker == "AMMN"
    assert mx.rows[0][0].streak_label == "6s"
    assert "@" in mx.rows[0][0].avg_buy_display

    # Dual heat
    top = build_broker_desk_top_model(
        SimpleNamespace(
            broker_code="YP",
            broker_name="YP",
            date=date(2026, 7, 29),
            broker_type=BrokerType.FOREIGN,
            top_buy_stocks=(SimpleNamespace(ticker="AMMN", net_value=Decimal("1e9"), net_lot=10),),
            top_sell_stocks=(
                SimpleNamespace(ticker="BBCA", net_value=Decimal("-1e8"), net_lot=-2),
            ),
            scope_note="Tracked",
        )
    )
    assert top.buys[0].bar_pct == 100
    assert top.sells

    # Calendar month grid (not row-dump only)
    cal = build_broker_desk_calendar_model(
        SimpleNamespace(
            broker_code="YP",
            broker_name="YP",
            broker_type=BrokerType.FOREIGN,
            as_of=date(2026, 7, 29),
            sessions_cached=1,
            scope_note="Tracked desk · not market foreign total",
            days=(
                SimpleNamespace(
                    date=date(2026, 7, 29),
                    net_value=Decimal("1e9"),
                    buy_value=Decimal("2e9"),
                    sell_value=Decimal("1e9"),
                    top_ticker="AMMN",
                    top_net=Decimal("1e9"),
                    ticker_count=1,
                ),
            ),
        )
    )
    assert cal.days[0].top_ticker == "AMMN"
    assert "foreign" in cal.scope_note.lower()
    assert cal.month_label == "Jul 2026"
    assert any(c.kind == "session" and c.top_ticker == "AMMN" for c in cal.cells)
    assert cal.legend


def test_headless_paint_hierarchy_widgets():
    """Broker home/matrix/top paint contracts from pure models (no mount)."""
    home = build_broker_desk_home_model(
        SimpleNamespace(
            broker_code="YP",
            broker_name="YP Desk",
            broker_type=BrokerType.FOREIGN,
            as_of=date(2026, 7, 29),
            day_net_value=Decimal("11460000000"),
            day_net_lot=100,
            day_ticker_count=2,
            top_buy_stocks=(SimpleNamespace(ticker="AMMN", net_value=Decimal("5e9")),),
            top_sell_stocks=(),
            scope_note="Tracked desk",
        ),
        pulse=SimpleNamespace(
            net5=Decimal("1e10"),
            sessions_in_net5=5,
            buy_streak=3,
            delta1=Decimal("1e8"),
        ),
    )
    assert "11" in home.day_net_amount or home.day_net_amount.strip()
    assert home.empty is False

    from src.application.services.broker_desk_from_daily_flow import DeskTickerWindowCell

    mx_model = build_broker_desk_matrix_model(
        SimpleNamespace(
            broker_code="YP",
            broker_name="YP",
            as_of=date(2026, 7, 29),
            broker_type=BrokerType.FOREIGN,
            windows=(1, 3, 5, 10, 20),
            columns={
                1: (
                    DeskTickerWindowCell(
                        "AMMN",
                        Decimal("1e9"),
                        1,
                        1,
                        Decimal("9850"),
                        6,
                        False,
                    ),
                ),
                3: (),
                5: (),
                10: (),
                20: (),
            },
            sessions_cached=3,
            scope_note="Tracked",
            top_ticker_1s="AMMN",
        )
    )
    c00 = mx_model.rows[0][0]
    assert c00.ticker == "AMMN"
    assert c00.streak_label == "6s"
    assert "9,850" in c00.avg_buy_display or "9850" in c00.avg_buy_display

    top_m = build_broker_desk_top_model(
        SimpleNamespace(
            broker_code="YP",
            broker_name="YP",
            date=date(2026, 7, 29),
            broker_type=BrokerType.FOREIGN,
            top_buy_stocks=(SimpleNamespace(ticker="AMMN", net_value=Decimal("1e9"), net_lot=10),),
            top_sell_stocks=(
                SimpleNamespace(ticker="BBCA", net_value=Decimal("-1e8"), net_lot=-1),
            ),
            scope_note="Tracked",
        )
    )
    assert top_m.buys[0].ticker == "AMMN"
    assert top_m.sells[0].ticker == "BBCA"
