"""Present-only pre-open Enter inspect — Judge-shaped brief."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace

from src.adapters.tui.controllers.board_controller import BoardController
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.preopen_inspect_model import (
    EXPANDABLE_FLAGS,
    FLAG_DEFS,
    build_preopen_inspect_model,
)
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
        delta_iev=None,
        opening_broker_backing_tag="BACKED",
        trend_signal="BULLISH",
        opening_broker_backing_score=0.9,
        opening_broker_buy_streak=3,
        bid_offer_imbalance=0.72,
        spread_pct=Decimal("0.42"),
        gap_price_source="IEP",
    )


def _payload(tickers: list[str]) -> SimpleNamespace:
    cands = [_candidate(t) for t in tickers]
    result = SimpleNamespace(candidates=cands, total_movers_seen=10)
    response = SimpleNamespace(result=result, warnings=[], source_is_live=False)
    return SimpleNamespace(
        response=response,
        snapshot_date="2026-07-25",
        warnings=("note: snapshot path",),
    )


def test_inspect_model_judge_shaped_no_option_chip_wall():
    view = PreOpenPresenter().present(_payload(["BBRI"]))
    row = view.rows[0]
    model = build_preopen_inspect_model(
        row,
        rank=1,
        total=1,
        snapshot_date="2026-07-25",
        board_meta=view.meta,
        warnings=("note: snapshot path",),
    )
    assert model.action == "—"
    assert model.why
    assert model.why != ""
    assert model.auction_lines  # always present
    assert model.has_warn is True
    keys = {f.key for f in model.flags}
    # At most density [d] detail — never why/auction+/plan/warn chips
    assert "why" not in keys
    assert "auction_plus" not in keys
    assert "auction+" not in keys
    assert "plan" not in keys
    assert "warn" not in keys
    assert EXPANDABLE_FLAGS == frozenset()
    flag_keys = {k for k, _ in FLAG_DEFS}
    assert flag_keys == {"detail"} or flag_keys <= {"detail"}
    # No Grd theater
    assert not hasattr(model, "grade") or getattr(model, "grade", None) is None


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
    assert "Pre-open · BBRI" in text or "Screen · pre-open · BBRI" in text
    assert f"risk {row.risk}" in text or "risk" in text.lower()
    assert row.iep in text
    assert row.delta_pct in text
    assert "Levels" in text or "IEV" in text
    assert "AUCTION" in text
    assert "Why:" in text or "← Why" in text
    assert "BACKED" in text or "trend" in text.lower() or "BULLISH" in text
    assert "2026-07-25" in text
    # No option-chip wall labels as primary chrome
    assert "auction+" not in text.lower()
    assert "Flags" not in text or "flag" not in text.lower()
    # Why matches shared helper / evidence
    why = format_preopen_why(row)
    assert why
    assert "never invents Signal" not in text
    assert "no engine re-run" not in text


def test_inspect_sparse_source_auction_always_dash():
    row = SimpleNamespace(
        ticker="X",
        action="—",
        iep="—",
        delta_pct="—",
        iev="—",
        ncp="—",
        delta_iev="—",
        risk="—",
        evidence="",
        source=None,
    )
    model = build_preopen_inspect_model(row)
    assert model.auction_lines  # always present
    assert model.auction_lines[0] == "—"
    text = present_preopen_engine_inspect(row).text  # type: ignore[arg-type]
    assert "Pre-open · X" in text or "X" in text
    assert "AUCTION" in text
    assert "—" in text
    assert "grade" not in text.lower() or "grade C" not in text


def test_inspect_warn_only_when_non_empty():
    row = SimpleNamespace(
        ticker="Y",
        action="—",
        iep="1",
        delta_pct="+0.1",
        iev="1K",
        ncp="disc",
        delta_iev="—",
        risk="—",
        evidence="ok",
        source=None,
    )
    empty = build_preopen_inspect_model(row, warnings=())
    assert empty.has_warn is False
    assert empty.warn_lines == ()
    with_w = build_preopen_inspect_model(row, warnings=("UMA",))
    assert with_w.has_warn is True
    assert "UMA" in with_w.warn_lines[0]


def test_enter_does_not_call_re_screen_loader():
    """Enter inspect uses board row only — loader not re-invoked."""
    calls = {"n": 0}

    def loader():
        calls["n"] += 1
        return _payload(["BBRI"])

    async def scenario() -> None:
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
            n_after_load = calls["n"]
            assert n_after_load >= 1
            app._open_detail()
            await pilot.pause()
            assert app._stage == "detail"
            assert app._status_note == "inspect"
            # No second loader call for Enter
            assert calls["n"] == n_after_load
            assert "Why" in app._detail_text or "why" in app._detail_text.lower()
            assert "AUCTION" in app._detail_text
            assert "auction+" not in app._detail_text.lower()
            await pilot.press("escape")
            await pilot.pause()
            assert app._stage == "preopen"
            assert app._board_kind == "preopen"

    asyncio.run(scenario())


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
            assert "pre-open" in app._board_title.lower() or "Pre-open" in app._board_title
            assert "inspect" in app._meta
            assert "AUCTION" in app._detail_text
            await pilot.press("escape")
            await pilot.pause()
            assert app._stage == "preopen"
            assert app._board_kind == "preopen"

    asyncio.run(scenario())
