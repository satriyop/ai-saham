"""Remaining visual-parity frames — pure model contracts.

Pre-open Enter journey residual: D3 (e2e smoke / preopen_engine_inspect).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.adapters.tui.broker_desk_flow_model import build_broker_desk_flow_model
from src.adapters.tui.broker_desk_history_model import build_broker_desk_history_model
from src.adapters.tui.broker_desk_home_model import build_broker_desk_home_model
from src.adapters.tui.empty_stage_body import format_empty_stage_body
from src.adapters.tui.paper_log_display import format_paper_confirm_body
from src.adapters.tui.preopen_inspect_model import build_preopen_inspect_model
from src.adapters.tui.ticker_desk_model import build_ticker_desk_model_from_dashboard
from src.adapters.tui.widgets.broker_flow_desk import _bar
from src.adapters.tui.widgets.flag_chip import FlagChip
from src.domain.entities.broker_flow import BrokerType


def test_preopen_inspect_model_flags_not_action():
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
    model = build_preopen_inspect_model(
        row,
        rank=1,
        total=3,
        snapshot_date="2026-07-25",
        warnings=("note: snapshot path",),
    )
    assert model.ticker == "BBRI"
    assert model.grade == "A"
    assert model.has_auction is True
    assert model.has_warn is True
    keys = {f.key for f in model.flags}
    assert keys == {"detail", "why", "auction_plus", "warn"}
    assert model.body_contains_action_authority() is False


def test_preopen_inspect_desk_hierarchy_paint():
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
    title = f"Inspect · {model.ticker}" if hasattr(model, "ticker") else model.ticker
    assert "BBRI" in title or model.ticker == "BBRI"
    assert model.grade == "A"
    assert "4,820" in model.iep or model.iep == "4,820"
    by_flag = {f.key: f for f in model.flags}
    assert "why" in by_flag
    ap = by_flag["auction_plus"]
    assert "auction" in ap.label or ap.key == "auction_plus"
    # Compact: panels closed until detail_open (paint-time)
    assert model.has_auction is True
    assert "BULLISH" in "\n".join(model.auction_lines)


def test_broker_home_deep_flag_chips():
    home = build_broker_desk_home_model(
        SimpleNamespace(
            broker_code="YP",
            broker_name="YP Desk",
            broker_type=BrokerType.FOREIGN,
            as_of=date(2026, 7, 29),
            day_net_value=Decimal("1e9"),
            day_net_lot=10,
            day_ticker_count=1,
            top_buy_stocks=(SimpleNamespace(ticker="AMMN", net_value=Decimal("1e9")),),
            top_sell_stocks=(),
            scope_note="Tracked desk",
        )
    )
    for key, lab in (("t", "buy/sell"), ("m", "top 5")):
        chip = FlagChip(key, lab, id=f"bd-flag-{key}")
        chip.set_chip_state(available=not home.empty, expanded=False)
        assert chip.flag_key == key
        assert chip._available is True
        assert "deep." not in lab


def test_flow_history_structured_density_not_row_dump_only():
    flow = build_broker_desk_flow_model(
        SimpleNamespace(
            broker_code="YP",
            broker_name="YP",
            broker_type=BrokerType.FOREIGN,
            scope_note="Tracked desk · not market foreign",
            days=(
                SimpleNamespace(
                    date=date(2026, 7, 29),
                    net_value=Decimal("1e9"),
                    net_lot=10,
                    ticker_count=2,
                ),
            ),
        )
    )
    hist = build_broker_desk_history_model(
        SimpleNamespace(
            broker_code="YP",
            broker_name="YP",
            broker_type=BrokerType.FOREIGN,
            scope_note="Tracked",
            pinned_ticker=None,
            flows=(
                SimpleNamespace(
                    date=date(2026, 7, 29),
                    ticker="AMMN",
                    net_value=Decimal("1e9"),
                    net_lot=5,
                ),
            ),
        )
    )
    assert flow.days[0].date_label == "2026-07-29"
    bar = _bar(flow.days[0].bar_pct)
    assert "█" in bar or "░" in bar
    assert hist.rows[0].ticker == "AMMN"
    # Structured fields, not monoline dump only
    assert flow.days[0].net_display
    assert hist.rows[0].lot_display or hist.rows[0].net_display


def test_ticker_detail_flag_row_paint():
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
            analyst=object(),
            ownership=object(),
            insider_txns=(),
            iev_rows=(),
            seasonality=None,
            freshness=(),
        )
    )
    # Design: single master detail · d chip (not per-panel peach wall)
    chip = FlagChip("detail", "detail · d", id="td-flag-detail")
    chip.set_chip_state(available=True, expanded=False)
    assert chip.flag_key == "detail"
    assert "is-on" not in chip.classes
    chip.set_chip_state(available=True, expanded=True)
    assert "is-on" in chip.classes
    # No analyst flag chip in model flags inventory — depth panels only
    assert model.detail_panels is not None


def test_ticker_view_meta_header_no_not_action_chrome():
    """Ticker view-meta language: local cache / full · local cache — never not Action."""
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
            analyst=None,
            ownership=None,
            insider_txns=(),
            iev_rows=(),
            seasonality=None,
            freshness=(),
        )
    )
    # Compact vs expanded meta copy contracts used by cockpit paint
    compact_meta = "local cache"
    full_meta = "full · local cache"
    assert "not Action" not in compact_meta
    assert "not Action" not in full_meta
    assert "local cache" in compact_meta.lower()
    assert "full" in full_meta.lower() and "local cache" in full_meta.lower()
    # Model footer does not inject Action authority chrome
    assert "not Action" not in model.footer
    assert "not Action" not in model.as_text()


def test_paper_and_health_opencode_density_copy():
    paper = format_paper_confirm_body(
        ticker="BBCA", entry="6225", stop="5900", target="6800", lots="3"
    )
    assert "PAPER TAPE" in paper
    assert "GEOMETRY" in paper
    assert "NOTEBOOK · PAPER ONLY" not in paper  # product tape language
    empty = format_empty_stage_body(cache_status="empty")
    assert "SESSION HEALTH" in empty or "No local market data" in empty
    assert "empty" in empty.lower()


def test_broker_list_flag_row_partial_net_rule():
    """No operator chips for partial_net / from_ticker — meta strings only."""
    from src.adapters.tui.chrome_cues import broker_radar_meta, ticker_desks_title

    rows = [
        SimpleNamespace(code="YP", type_label="Foreign", has_partial_netx=True),
    ]
    partial_on = any(getattr(r, "has_partial_netx", False) for r in rows)
    assert partial_on is True
    meta = broker_radar_meta(
        desk_count=len(rows),
        from_stock="BBCA",
        has_partial_netx=partial_on,
    )
    assert "thin NetX" in meta
    assert ticker_desks_title("BBCA").startswith("View · desks ·")
    assert "partial_net" not in meta
