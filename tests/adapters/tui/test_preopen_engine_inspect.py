"""Present-only pre-open Enter inspect."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace

from src.adapters.tui.controllers.board_controller import BoardController
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.presenters.preopen_engine_inspect_presenter import (
    present_preopen_engine_inspect,
)
from src.adapters.tui.presenters.preopen_presenter import (
    PreOpenPresenter,
    format_preopen_why,
)


def _candidate(ticker: str = "BBRI") -> SimpleNamespace:
    return SimpleNamespace(
        ticker=ticker,
        iep=4820,
        iep_gap_pct=Decimal("1.8"),
        gap_pct=Decimal("1.8"),
        iev=12_400_000,
        iev_intensity=1.34,
        opening_broker_backing_tag="BACKED",
        trend_signal="BULLISH",
        opening_broker_backing_score=0.9,
        opening_broker_buy_streak=3,
    )


def _payload(tickers: list[str]) -> SimpleNamespace:
    cands = [_candidate(t) for t in tickers]
    result = SimpleNamespace(candidates=cands)
    response = SimpleNamespace(result=result, warnings=[])
    return SimpleNamespace(
        response=response,
        snapshot_date="2026-07-25",
        warnings=("note: snapshot path",),
    )


def test_inspect_board_parity_and_sections():
    view = PreOpenPresenter().present(_payload(["BBRI"]))
    row = view.rows[0]
    inspect = present_preopen_engine_inspect(
        row,
        rank=1,
        total=1,
        snapshot_date="2026-07-25",
        board_meta=view.meta,
        warnings=("note: snapshot path",),
    )
    text = inspect.text
    assert "Screen · pre-open · BBRI" in text
    assert f"grade {row.grade}" in text
    assert f"risk {row.risk}" in text
    assert row.iep in text
    assert row.delta_pct in text
    assert "Snapshot" in text
    assert "Levels" in text
    assert "Auction / broker" in text
    assert "BACKED" in text
    assert "BULLISH" in text
    assert "2026-07-25" in text
    # Operator inspect: levels + flags; no implementer authority slogans
    assert "never invents Signal" not in text
    assert "no engine re-run" not in text
    assert "TUI pre-open board" not in text
    assert "present-only inspect" not in text
    # Why matches shared helper / evidence
    why = format_preopen_why(row)
    assert why
    assert "Why:" in text
    assert "trend" in text.lower() or "broker" in text.lower()
    assert "why" in text.lower() and "auction+" in text


def test_inspect_sparse_source_no_crash():
    row = SimpleNamespace(
        ticker="X",
        iep="—",
        delta_pct="—",
        iev="—",
        ncp="—",
        delta_iev="—",
        grade="C",
        risk="clear",
        evidence="",
        source=None,
    )
    text = present_preopen_engine_inspect(row).text  # type: ignore[arg-type]
    assert "Screen · pre-open · X" in text
    assert "not on this row" in text
    assert "grade C" in text


def test_enter_opens_preopen_inspect_and_esc_returns():
    async def scenario() -> None:
        payload = _payload(["BBRI", "BBCA"])
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
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app._run_command("screen-preopen")
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "preopen" and app._rows:
                    break
            assert app._stage == "preopen"
            assert app._board_kind == "preopen"
            app._open_detail()  # board Enter inspect (not palette view-ticker)
            await pilot.pause()
            assert app._stage == "detail"
            assert app._detail_return_stage == "preopen"
            assert "Screen · pre-open ·" in app._board_title
            assert "Snapshot" in app._detail_text
            assert "grade" in app._detail_text
            assert "inspect" in app._meta
            assert "present-only inspect" not in app._meta
            await pilot.press("escape")
            await pilot.pause()
            assert app._stage == "preopen"
            assert app._board_kind == "preopen"

    asyncio.run(scenario())
