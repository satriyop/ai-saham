"""Durable TUI journey smoke — fakes by default; optional real DB skip.

Does not require an interactive terminal. Fast loaders keep CI bounded.
Real composition path is opt-in via AI_SAHAM_TUI_E2E_REAL=1 and existing DB.
"""

from __future__ import annotations

import asyncio
import os
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.adapters.tui.main import CockpitApp
from src.adapters.tui.paper_log_result import PaperLogResult
from src.adapters.tui.phase_sequence import PhaseSequenceFact
from src.adapters.tui.plan_structure_result import PlanStructureResult
from src.adapters.tui.presenters.accum_presenter import AccumPresenter
from src.adapters.tui.screens.fetch_confirm import FetchConfirmModal
from src.adapters.tui.screens.paper_log_confirm import PaperLogConfirmModal


def _live_result(tickers: list[str]) -> SimpleNamespace:
    # Candidates are the source objects for AccumPresenter
    candidates = []
    for i, t in enumerate(tickers):
        candidates.append(
            SimpleNamespace(
                ticker=t,
                accum_score=50.0 + i,
                rsi=50.0,
                consecutive_streak=2,
                net_buy_ratio=0.5,
                vwap_discount_pct=0.0,
                current_price=1000 + i,
                setup_phase=SimpleNamespace(current_phase=SimpleNamespace(value="ACCUMULATION")),
                trade_setup=SimpleNamespace(
                    action=SimpleNamespace(value="WATCH", short="WATCH"),
                    rationale="t",
                ),
                signal_assessment=SimpleNamespace(
                    assessment=SimpleNamespace(
                        score=80 - i, strength=SimpleNamespace(value="MODERATE")
                    )
                ),
                risk_assessment=SimpleNamespace(
                    gate_triggered=None,
                    gate_is_structural=False,
                    rationale=("ok",),
                ),
                name=t,
                latest_candle_date=None,
                latest_broker_date=None,
                freshness=None,
            )
        )
    return SimpleNamespace(
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


def test_e2e_smoke_core_journeys_with_fakes():
    """Drive real CockpitApp paths with fast injected loaders (no network)."""
    broker_gate = threading.Event()
    paper_calls: list[str] = []

    def broker_loader():
        broker_gate.wait(timeout=3.0)
        return [
            SimpleNamespace(
                code="YP",
                broker_type="T1",
                as_of="2026-07-29",
                day_net="1",
                net5="2",
                buy_streak="1",
                delta1="0",
                rank="1",
                top_buy="BBCA",
                has_data=True,
            )
        ]

    def plan_runner(ticker: str) -> PlanStructureResult:
        return PlanStructureResult(
            summary=(
                "structure WATCH · entry 1 · stop 2 · target 3 · 1 lots · plan deadbeef · no order"
            ),
            ticker=ticker,
            action="WATCH",
            entry="1",
            stop="2",
            target="3",
            lots="1",
            plan_id_short="deadbeef",
            incomplete_reason="",
            no_order=True,
            inherits_action=True,
        )

    def paper_log(ticker: str) -> PaperLogResult:
        paper_calls.append(ticker)
        return PaperLogResult(
            ticker=ticker,
            written=True,
            message=f"paper logged {ticker}",
            planned_entry="1",
            planned_stop="2",
            planned_target="3",
            plan_id="deadbeef",
        )

    def phase_loader(ticker: str, before):
        return (
            PhaseSequenceFact(phase="ACCUMULATION", as_of="2026-07-20"),
            PhaseSequenceFact(phase="COMPRESSION", as_of="2026-07-28"),
        )

    live = _live_result(["BBRI", "BBCA"])

    async def scenario() -> None:
        app = CockpitApp(
            accum_loader=lambda: live,
            accum_presenter=AccumPresenter(),
            plan_runner=plan_runner,
            paper_log_runner=paper_log,
            phase_history_loader=phase_loader,
            broker_list_loader=broker_loader,
            fetch_runner=lambda: None,
            fetch_previewer=lambda: SimpleNamespace(summary="preview ok"),
        )
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause(0.05)
            # Force live board (skip mount race)
            app._on_accum_payload(live)
            await pilot.pause(0.05)
            assert app._stage == "accum"
            assert app._board_source == "live"
            assert app._rows
            assert getattr(app._rows[0], "source", None) is not None

            # Live Enter = full judge
            app._row_index = 0
            app._focus_ticker = app._rows[0].ticker
            app._open_detail()
            await pilot.pause(0.05)
            assert app._status_note == "judge"
            assert app._judge_limited is False
            assert "Phase sequence" in (app._detail_text or "")
            assert "ACCUMULATION → COMPRESSION" in (app._detail_text or "")

            # Snapshot-style limited: plant row without source
            app._rows[0] = SimpleNamespace(
                **{
                    **{
                        k: getattr(app._rows[0], k)
                        for k in (
                            "ticker",
                            "signal",
                            "accum",
                            "action",
                            "phase",
                            "streak",
                            "rsi",
                            "net_pct",
                            "disc_pct",
                            "price",
                            "gate",
                            "name",
                        )
                    },
                    "source": None,
                }
            )
            app._board_source = "snapshot"
            app._stage = "accum"
            app._snapshot_freshness = "snapshot · test"
            app._refresh_chrome()
            await pilot.pause(0.05)
            foot = app._footer_hint().lower()
            assert "limited judge" in foot
            assert "j" in foot and "r" in foot
            app._open_detail()
            await pilot.pause(0.05)
            assert app._judge_limited is True

            # Plan + paper log confirm
            app._focus_ticker = "BBRI"
            app._plan_ticker = "BBRI"
            app._stage = "plan"
            app._plan_running = False
            app._plan_structure = plan_runner("BBRI")
            app.action_paper_log()
            await pilot.pause(0.05)
            assert isinstance(app.screen, PaperLogConfirmModal)
            await pilot.press("escape")
            await pilot.pause(0.05)
            assert paper_calls == []  # cancelled

            # Confirm path
            app.action_paper_log()
            await pilot.pause(0.05)
            await pilot.press("enter")
            for _ in range(40):
                await pilot.pause(0.05)
                if paper_calls:
                    break
            assert paper_calls == ["BBRI"]

            # Fetch confirm cancel
            app._open_fetch_confirm()
            await pilot.pause(0.05)
            assert isinstance(app.screen, FetchConfirmModal)
            await pilot.press("escape")
            await pilot.pause(0.05)

            # Broker loading → ready
            app._open_view_broker_list()
            await pilot.pause(0.1)
            assert app._stage == "loading"
            body = str(app.query_one("#stage-body").render()).lower()
            assert "broker" in body and "loading" in body
            broker_gate.set()
            for _ in range(80):
                await pilot.pause(0.05)
                if app._stage == "broker-list":
                    break
            assert app._stage == "broker-list"
            assert len(app._broker_rows) == 1

    asyncio.run(scenario())


def test_e2e_snapshot_open_marks_limited_judge_chrome(tmp_path: Path):
    from src.adapters.tui.board_snapshot import AccumBoardSnapshot, AccumBoardSnapshotIdentity

    path = tmp_path / "s.json"
    snap = AccumBoardSnapshot(
        schema_version=1,
        identity=AccumBoardSnapshotIdentity(
            board_kind="accum",
            universe="lq45",
            window=7,
            sort_by="signal",
            top=20,
            as_of="2026-07-29",
            captured_at="2026-07-29T00:00:00+00:00",
        ),
        meta="1 names",
        cache_label="local",
        summary="",
        columns=("Ticker",),
        rows=(
            {
                "ticker": "ASII",
                "signal": "60",
                "accum": "40",
                "action": "WATCH",
                "phase": "NONE",
                "streak": "0",
                "rsi": "50",
                "net_pct": "0",
                "disc_pct": "0",
                "price": "5000",
                "gate": "OPEN",
                "name": "ASII",
            },
        ),
    )
    from src.adapters.composition.board_snapshot_store import write_accum_board_snapshot

    write_accum_board_snapshot(path, snap)

    async def scenario() -> None:
        app = CockpitApp(board_snapshot_path=path)
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause(0.05)
            assert app._try_restore_accum_snapshot()
            assert app._board_source == "snapshot"
            assert "limited" in app._footer_hint().lower()
            assert "limited" in (app._meta or "").lower()

    asyncio.run(scenario())


@pytest.mark.skipif(
    os.environ.get("AI_SAHAM_TUI_E2E_REAL", "") != "1",
    reason="Set AI_SAHAM_TUI_E2E_REAL=1 to run composition smoke against local DB",
)
def test_e2e_optional_real_composition_smoke():
    """Optional slow path: real create_tui_app + config DB if present."""
    from src.infrastructure.config.app_config import load_app_config

    cfg = load_app_config()
    db = Path(cfg.storage.db_path)
    if not db.is_file():
        pytest.skip(f"local DB missing: {db}")

    from src.adapters.tui.composition import create_tui_app

    async def scenario() -> None:
        app = create_tui_app()
        async with app.run_test(size=(120, 36)) as pilot:
            for _ in range(150):
                await pilot.pause(0.1)
                if app._stage in {"accum", "empty", "error"}:
                    break
            assert app._stage in {"accum", "empty", "error", "loading", "shell"}
            # Health rail should paint something
            cache = str(app.query_one("#side-cache").render())
            assert cache.startswith("Cache")

    asyncio.run(scenario())
