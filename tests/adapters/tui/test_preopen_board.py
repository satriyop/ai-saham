"""Pre-open board presenter + session strip + cell contract (design cockpit)."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace

from rich.text import Text

from src.adapters.tui.board_cell_markup import format_preopen_board_cells
from src.adapters.tui.controllers.board_controller import BoardController
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.presenters.preopen_presenter import (
    PREOPEN_BOARD_COLUMN_LABELS,
    PreOpenPresenter,
)
from src.adapters.tui.state import ScreenStatus


def _candidate(
    ticker: str = "BBRI",
    *,
    action: str | None = None,
    delta_iev: int | None = None,
    is_ncp_locked: bool | None = None,
    iev_intensity: float = 1.34,
    iev: int = 12_400_000,
) -> SimpleNamespace:
    return SimpleNamespace(
        ticker=ticker,
        iep=4820,
        iep_gap_pct=Decimal("1.8"),
        gap_pct=Decimal("1.8"),
        iev=iev,
        iev_intensity=iev_intensity,
        delta_iev=delta_iev,
        is_ncp_locked=is_ncp_locked,
        action=action,
        opening_broker_backing_tag="BACKED",
        trend_signal="BULLISH",
        gap_price_source="IEP",
    )


def _payload(
    tickers: list[str],
    *,
    with_action: bool = False,
    with_delta: bool = False,
    ncp_authoritative: bool | None = None,
    capture_phase: str | None = None,
    total_movers: int | None = None,
) -> SimpleNamespace:
    cands = []
    for t in tickers:
        cands.append(
            _candidate(
                t,
                action=(
                    "ENTER"
                    if with_action and t == tickers[0]
                    else ("WATCH" if with_action else None)
                ),
                delta_iev=2_100_000 if with_delta else None,
                is_ncp_locked=True if ncp_authoritative else None,
            )
        )
    result = SimpleNamespace(
        candidates=cands,
        total_movers_seen=total_movers if total_movers is not None else 312,
    )
    response = SimpleNamespace(
        result=result,
        warnings=[],
        ncp_authoritative=ncp_authoritative,
        capture_phase=capture_phase,
        source_is_live=False,
    )
    return SimpleNamespace(response=response, snapshot_date="2026-07-25", warnings=())


def test_preopen_board_column_labels_locked():
    assert PREOPEN_BOARD_COLUMN_LABELS == (
        "Tkr",
        "Act",
        "IEP",
        "Δ%",
        "IEV",
        "NCP",
        "ΔIEV",
        "Risk",
    )
    assert "Grd" not in PREOPEN_BOARD_COLUMN_LABELS
    assert "Grade" not in PREOPEN_BOARD_COLUMN_LABELS


def test_preopen_presenter_honest_discovery_no_action_no_intensity_as_ncp():
    """Snapshot path: Act=—, NCP=disc (not intensity), ΔIEV=— (not intensity copy)."""
    view = PreOpenPresenter().present(_payload(["BBRI", "BBCA"]))
    assert len(view.rows) == 2
    row = view.rows[0]
    assert row.ticker == "BBRI"
    assert row.action == "—"
    assert row.ncp == "disc"
    assert row.delta_iev == "—"
    # Must not paint intensity float into NCP or ΔIEV
    assert row.ncp not in {"1.34", "0.92", "1.2"}
    assert "1.34" not in row.delta_iev
    assert not hasattr(row, "grade") or getattr(row, "grade", None) is None
    assert "+" in row.delta_pct or row.delta_pct.startswith("1") or row.delta_pct.startswith("+")


def test_preopen_presenter_action_and_locked_delta_when_authoritative():
    view = PreOpenPresenter().present(
        _payload(
            ["BBRI", "ADRO"],
            with_action=True,
            with_delta=True,
            ncp_authoritative=True,
            capture_phase="NCP_LOCKED",
        )
    )
    assert view.rows[0].action == "ENTER"
    assert view.rows[1].action == "WATCH"
    assert view.rows[0].ncp == "LOCK"
    assert view.rows[0].delta_iev.startswith("+") and "M" in view.rows[0].delta_iev
    strip = view.session_strip
    assert strip is not None
    assert strip.source == "SNAPSHOT"
    assert "NCP_LOCKED" in strip.phase
    assert "E1" in strip.funnel or "E" in strip.funnel
    assert "W1" in strip.funnel or "W" in strip.funnel


def test_preopen_session_strip_discovery_funnel_no_invented_ew():
    view = PreOpenPresenter().present(_payload(["BBRI"], total_movers=50))
    strip = view.session_strip
    assert strip is not None
    assert strip.source == "SNAPSHOT"
    assert "discovery-only" in strip.phase
    assert "50" in strip.funnel
    assert "E—/W—" in strip.funnel or "E—" in strip.funnel
    assert "2026-07-25" in strip.window
    assert "SNAPSHOT" in view.meta


def test_preopen_board_cells_act_not_grd_and_ncp_flag():
    row = SimpleNamespace(
        ticker="BBRI",
        action="ENTER",
        iep="4,820",
        delta_pct="+1.8",
        iev="12.4M",
        ncp="LOCK",
        delta_iev="+2.1M",
        risk="~",
    )
    cells = format_preopen_board_cells(row)
    assert len(cells) == 8
    plains = [c.plain if isinstance(c, Text) else str(c) for c in cells]
    assert plains[0] == "BBRI"
    assert plains[1] == "ENTER"
    assert plains[2] == "4,820"
    assert "+1.8" in plains[3]
    assert plains[5] == "LOCK"
    assert "+2.1M" in plains[6]
    assert plains[7] == "~"
    # No letter grade column
    assert "A" not in plains
    assert "B" not in plains
    assert "C" not in plains


def test_preopen_ncp_cell_rejects_intensity_float_paint():
    row = SimpleNamespace(
        ticker="X",
        action="—",
        iep="—",
        delta_pct="—",
        iev="—",
        ncp="0.92",  # bad binding — cell formatter must not promote as NCP
        delta_iev="—",
        risk="—",
    )
    cells = format_preopen_board_cells(row)
    plains = [c.plain if isinstance(c, Text) else str(c) for c in cells]
    assert plains[5] == "—"


def test_intensity_not_copied_to_delta_iev_or_ncp():
    cand = _candidate("BBRI", iev_intensity=6.1, delta_iev=None)
    view = PreOpenPresenter().present(
        SimpleNamespace(
            response=SimpleNamespace(
                result=SimpleNamespace(candidates=[cand], total_movers_seen=1),
                warnings=[],
                source_is_live=False,
            ),
            snapshot_date="2026-08-01",
            warnings=(),
        )
    )
    assert view.rows[0].ncp != "6.10"
    assert view.rows[0].ncp != "6.1"
    assert view.rows[0].delta_iev == "—"
    assert "6.1" not in view.rows[0].ncp
    assert "6.1" not in view.rows[0].delta_iev


def test_preopen_controller_empty_when_no_response():
    controller = BoardController(
        lambda: SimpleNamespace(response=None, snapshot_date=None, warnings=("none",)),
        empty_when=lambda p: getattr(p, "response", None) is None,
    )
    gen = controller.begin()
    states = []

    def dispatch(cb, *a):
        cb(*a)

    controller.execute_generation(gen, dispatch=dispatch, listener=states.append)
    assert states[-1].status is ScreenStatus.EMPTY


def test_cockpit_preopen_board_from_fake():
    async def scenario() -> None:
        payload = _payload(["BBRI", "BMRI"])
        loader = lambda: payload  # noqa: E731
        app = CockpitApp(
            preopen_loader=loader,
            preopen_controller=BoardController(
                loader,
                empty_when=lambda p: (
                    not getattr(
                        getattr(getattr(p, "response", None), "result", None),
                        "candidates",
                        True,
                    )
                ),
            ),
            preopen_presenter=PreOpenPresenter(),
        )
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            app._run_command("screen-preopen")
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "preopen" and len(app._rows) == 2:
                    break
            assert app._stage == "preopen"
            assert app._board_kind == "preopen"
            assert app._focus_ticker == "BBRI"
            assert app._evidence_text
            # Session strip honesty
            assert "SNAPSHOT" in app._board_title or "discovery" in (app._status_note or "").lower()
            assert app._rows[0].action == "—"
            assert app._rows[0].ncp == "disc"
            assert app._rows[0].delta_iev == "—"

    asyncio.run(scenario())
