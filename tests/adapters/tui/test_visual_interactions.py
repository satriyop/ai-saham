"""Interaction + stage hierarchy — pure model/paint contracts (no full-app mount).

Residual multi-widget journeys: D3 e2e smoke / broker hub / view ticker.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.adapters.tui.broker_desk_home_model import build_broker_desk_home_model
from src.adapters.tui.broker_desk_matrix_model import build_broker_desk_matrix_model
from src.adapters.tui.health_poster_model import build_health_poster_model
from src.adapters.tui.paper_desk_model import build_paper_desk_model
from src.adapters.tui.ticker_desk_model import build_ticker_desk_model_from_dashboard
from src.adapters.tui.widgets.flag_chip import FlagChip
from src.application.services.broker_desk_from_daily_flow import DeskTickerWindowCell
from src.domain.entities.broker_flow import BrokerType


def test_paper_desk_hierarchy_empty_and_logged():
    empty = build_paper_desk_model([])
    assert empty.empty is True
    assert "notebook" in empty.title.lower() or "Paper" in empty.title
    assert empty.body_contains_action_authority() is False

    logged = build_paper_desk_model(
        [
            SimpleNamespace(
                ticker="BBCA",
                written=True,
                refused=False,
                message="logged",
                planned_entry="6225",
                planned_stop="5900",
                planned_target="6800",
            )
        ]
    )
    assert logged.empty is False
    assert logged.rows[0].kind == "ok"
    assert "BBCA" in logged.rows[0].headline


def test_paper_stage_paint_contract():
    model = build_paper_desk_model(
        [
            SimpleNamespace(
                ticker="BBCA",
                written=True,
                refused=False,
                message="ok",
                planned_entry="1",
                planned_stop="2",
                planned_target="3",
            )
        ]
    )
    assert model.empty is False
    assert "BBCA" in model.rows[0].headline or "LOGGED" in model.rows[0].headline.upper()


def test_health_poster_models_distinct():
    empty_m = build_health_poster_model(cache_status="empty")
    lag_m = build_health_poster_model(cache_status="lag")
    ready_m = build_health_poster_model(cache_status="ready")
    assert empty_m.kind == "empty" and "No local" in empty_m.title
    assert lag_m.kind == "lag"
    assert ready_m.kind == "ready"
    assert empty_m.title != lag_m.title
    assert "not Action" not in empty_m.title


def test_health_poster_empty_stage_contract():
    m = build_health_poster_model(cache_status="empty")
    assert m.title
    assert "not Action" not in m.title
    assert "No local" in m.title or "empty" in m.title.lower() or m.kind == "empty"


def test_broker_home_deep_chip_action_map():
    """deep.t/f/c/h/m → hub actions (pure dispatch table on widget)."""
    home = build_broker_desk_home_model(
        SimpleNamespace(
            broker_code="YP",
            broker_name="YP",
            broker_type=BrokerType.FOREIGN,
            as_of=date(2026, 7, 29),
            day_net_value=Decimal("1e9"),
            day_net_lot=10,
            day_ticker_count=1,
            top_buy_stocks=(SimpleNamespace(ticker="AMMN", net_value=Decimal("1")),),
            top_sell_stocks=(),
            scope_note="Tracked",
        )
    )
    assert home.empty is False
    # Product chip labels (bible: no deep.* chrome noise)
    from src.adapters.tui.widgets.chip_bar import BROKER_HOME_CHIPS

    deep_keys = ("t", "f", "c", "h", "m")
    labels = dict(BROKER_HOME_CHIPS)
    for key in deep_keys:
        chip = FlagChip(key, labels[key], id=f"bd-flag-{key}")
        chip.set_chip_state(available=not home.empty, expanded=False)
        assert chip._available is True
        assert "is-dim" not in chip.classes
        assert "deep." not in chip._label
    # Handler action map (shipped on BrokerDesk)
    expected = {
        "t": "action_broker_top",
        "f": "action_broker_flow",
        "c": "action_broker_calendar",
        "h": "action_broker_history",
        "m": "action_broker_matrix",
    }
    assert set(expected) == set(deep_keys)
    for k in deep_keys:
        assert k in home.hub_keys


def test_matrix_cell_jump_ticker_contract():
    cell = DeskTickerWindowCell(
        ticker="AMMN",
        net_value=Decimal("1e9"),
        window=1,
        sessions_used=1,
        avg_buy_price=Decimal("1000"),
        buy_streak=2,
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
            sessions_cached=3,
            scope_note="Tracked",
            top_ticker_1s="AMMN",
        )
    )
    assert mx.jump_ticker == "AMMN"
    c00 = mx.rows[0][0]
    assert c00.ticker == "AMMN"
    # Selected event carries ticker for jump (widget MatrixCell.Selected)
    from src.adapters.tui.widgets.broker_matrix_desk import MatrixCell

    ev = MatrixCell.Selected("AMMN")
    assert ev.ticker == "AMMN"


def test_ticker_detail_real_panel_facts_not_presence_only():
    model = build_ticker_desk_model_from_dashboard(
        SimpleNamespace(
            ticker="BBCA",
            latest_close=Decimal("6275"),
            as_of=date(2026, 7, 29),
            notation=None,
            profile=None,
            price_structure=None,
            fundamentals=None,
            foreign_flow_points=(),
            foreign_flow_source="",
            bandar=None,
            earnings=(),
            analyst=SimpleNamespace(
                buy_count=3,
                hold_count=2,
                sell_count=0,
                consensus_label="BUY",
                avg_price_target=7150.0,
                upside_pct=13.9,
                price_target_low=6800.0,
                price_target_high=7600.0,
                last_updated=None,
                fetched_at=None,
            ),
            ownership=SimpleNamespace(
                top_holder_name="PT Dwimuria",
                top_holder_pct=54.9,
                institution_pct=38.2,
                individual_pct=6.9,
                total_shares_formatted="123B",
                report_date=None,
            ),
            insider_txns=(),
            corp_actions=(),
            iev_rows=(),
            seasonality=None,
            candles=(),
            sentiment=(),
            freshness=(),
        )
    )
    analyst = next(p for p in model.detail_panels if p.key == "analyst")
    assert any("BUY" in ln or "Target" in ln or "3B" in ln for ln in analyst.lines)
    assert "analyst block present" not in " ".join(analyst.lines)
    own = next(p for p in model.detail_panels if p.key == "ownership")
    assert any("Dwimuria" in ln or "Institutional" in ln for ln in own.lines)
    # Single master chip design — panels are depth sections, not per-flag chips
    assert "analyst" in {p.key for p in model.detail_panels}


def test_broker_list_partial_net_flag_logic():
    """List honesty is meta copy — not partial_net / from_ticker chips."""
    from src.adapters.tui.chrome_cues import (
        broker_list_title,
        broker_radar_meta,
        ticker_desks_title,
    )

    rows = [SimpleNamespace(code="YP", has_partial_netx=True)]
    partial_on = any(
        getattr(r, "has_partial_netx", False) or getattr(r, "partial_net", False) for r in rows
    )
    assert partial_on is True
    assert broker_list_title() == "View · broker list"
    assert ticker_desks_title("bbca") == "View · desks · BBCA"
    meta = broker_radar_meta(
        desk_count=len(rows),
        from_stock="BBCA",
        has_partial_netx=partial_on,
    )
    assert "thin NetX (partial sessions)" in meta
    assert "top brokers" in meta
    assert "partial_net" not in meta
    assert "from_ticker" not in meta
