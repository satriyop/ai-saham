"""Visual ticker desk (Harga mast) — pure model hierarchy, not CLI dump.

Journey view-ticker residual: ``test_view_ticker_desks_journey`` / D3.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.adapters.tui.ticker_desk_model import (
    build_ticker_desk_model_from_dashboard,
    build_ticker_desk_model_from_text,
)


def _dashboard(**over):
    base = dict(
        ticker="BBCA",
        latest_close=Decimal("6275"),
        as_of=date(2026, 7, 29),
        notation=SimpleNamespace(
            listing_board="Papan Utama",
            sector="Keuangan",
            sub_sector="Bank",
            tradeable=True,
            notations=(SimpleNamespace(description="Bank Central Asia"),),
        ),
        profile=None,
        price_structure=SimpleNamespace(
            change_1d_pct=0.8,
            change_5d_pct=-3.5,
            change_20d_pct=12.1,
            range_52w_pct=35.0,
            high_52w=Decimal("8975"),
            low_52w=Decimal("4820"),
            volume=122_400_000,
            avg_volume_20d=169_900_000,
            volume_vs_20d=0.72,
        ),
        fundamentals=SimpleNamespace(
            pe_ratio_ttm=13.3,
            pbv=3.0,
            market_cap_idr=774_000_000_000_000,
            roe_ttm=22.4,
            dividend_yield=4.8,
            piotroski_f_score=5,
        ),
        foreign_flow_points=(
            SimpleNamespace(date=date(2026, 7, 25), net_val=Decimal("-10000000000"), net_lot=-1),
            SimpleNamespace(date=date(2026, 7, 28), net_val=Decimal("5000000000"), net_lot=1),
            SimpleNamespace(date=date(2026, 7, 29), net_val=Decimal("-27800000000"), net_lot=-2),
        ),
        foreign_flow_source="stockbit",
        bandar=SimpleNamespace(
            broker_accdist="Acc",
            today_accdist="Normal Acc",
            five_day_accdist="Big Acc",
            top1_accdist="Acc",
            top1_percent=17.0,
            top10_accdist="Small Acc",
            broad_score=2,
            accumulation_score=2,
            session_date=date(2026, 7, 29),
            is_accumulating=True,
            is_distributing=False,
        ),
        earnings=(
            SimpleNamespace(
                year=2026,
                quarter=1,
                eps_actual=119.1,
                eps_prev_year=114.7,
                eps_yoy_change=4.4,
            ),
            SimpleNamespace(
                year=2025,
                quarter=4,
                eps_actual=114.7,
                eps_prev_year=111.7,
                eps_yoy_change=3.0,
            ),
        ),
        analyst=SimpleNamespace(
            buy_count=3,
            hold_count=2,
            sell_count=0,
            consensus_label="BUY",
            avg_price_target=7150.0,
            upside_pct=13.9,
            price_target_low=6800.0,
            price_target_high=7600.0,
            last_updated=date(2026, 7, 20),
            fetched_at=None,
            current_price=6275.0,
        ),
        ownership=SimpleNamespace(
            top_holder_name="PT Dwimuria Investama Andalan",
            top_holder_pct=54.9,
            institution_pct=38.2,
            individual_pct=6.9,
            total_shares_formatted="123.28B",
            report_date=date(2026, 3, 31),
        ),
        insider_txns=(
            SimpleNamespace(
                name="J. Widjaja",
                role="Dir",
                action_type="BUY",
                shares=50000,
                price=6100,
                transaction_date=date(2026, 3, 12),
            ),
        ),
        corp_actions=(
            SimpleNamespace(
                event_type="DIV",
                ex_date=date(2026, 4, 17),
                detail="Cash div Rp175 / share",
                status="completed",
            ),
        ),
        iev_rows=(SimpleNamespace(date=date(2026, 7, 29), iep=6275, iev=1_000_000, ncp=1.2),),
        seasonality=SimpleNamespace(label="strong Q1", edge_label="positive"),
        candles=(object(),) * 5,
        sentiment=(),
        freshness=(
            SimpleNamespace(label="Price", status=SimpleNamespace(value="ok")),
            SimpleNamespace(label="Flow", status=SimpleNamespace(value="ok")),
            SimpleNamespace(label="Bandar", status=SimpleNamespace(value="ok")),
            SimpleNamespace(label="Analyst", status=SimpleNamespace(value="ok")),
        ),
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_model_design_hierarchy_not_cli_primary():
    model = build_ticker_desk_model_from_dashboard(
        _dashboard(),
        body="THIS SHOULD NOT BE THE DESK — CLI DUMP",
    )
    assert model.ticker == "BBCA"
    assert "6,275" in model.price
    assert model.change_tone == "pos"
    assert any(m.label == "PE TTM" and "13" in m.value for m in model.metrics)
    # Mock fresh-grid pills (ok / miss / stale hierarchy)
    assert len(model.freshness) >= 10
    by_lab = {p.label: p for p in model.freshness}
    assert by_lab["Price"].status == "ok" and by_lab["Price"].value == "ok"
    assert by_lab["Flow"].status == "ok"
    assert by_lab["Analyst"].status == "ok"
    assert "Freshness" in model.as_text() or "Price:ok" in model.as_text()
    keys = {p.key for p in model.pulses}
    assert keys == {"flow", "struct", "bandar"}
    flow = next(p for p in model.pulses if p.key == "flow")
    assert flow.headline != "" and flow.title == "Foreign flow"
    struct = next(p for p in model.pulses if p.key == "struct")
    assert "×" in struct.headline or struct.headline != "—"
    bandar = next(p for p in model.pulses if p.key == "bandar")
    assert "Acc" in bandar.headline
    assert len(model.earnings) >= 1
    assert model.secondary
    # Detail inventory panels for d expand (not Action)
    assert model.detail_panels
    keys = {p.key for p in model.detail_panels}
    assert "analyst" in keys
    assert "ownership" in keys
    assert "insider" in keys
    assert any(p.status == "present" for p in model.detail_panels)
    analyst = next(p for p in model.detail_panels if p.key == "analyst")
    assert any("BUY" in ln or "Target" in ln or "3B" in ln for ln in analyst.lines)
    assert "analyst block present" not in " ".join(analyst.lines)
    own = next(p for p in model.detail_panels if p.key == "ownership")
    assert any("Dwimuria" in ln or "Institutional" in ln for ln in own.lines)
    assert "d detail" in model.footer
    # Primary as_text is hierarchical, not a Rich box dump
    text = model.as_text()
    assert "LAST · LOCAL CLOSE" in text
    assert "Foreign flow" in text
    assert "Bandar" in text
    assert "DETAIL PANELS" in text


def test_ticker_paint_contract_design_sections():
    """Mast / freshness / pulses / earnings / detail facts — pure model."""
    model = build_ticker_desk_model_from_dashboard(_dashboard())
    assert "6,275" in model.price
    assert "LAST" in model.as_text().upper()

    by_lab = {p.label: p for p in model.freshness}
    assert "Price" in by_lab and by_lab["Price"].status == "ok"

    flow = next(p for p in model.pulses if p.key == "flow")
    assert flow.title.upper() == "FOREIGN FLOW" or "FOREIGN" in flow.title.upper()
    struct = next(p for p in model.pulses if p.key == "struct")
    assert "STRUCTURE" in struct.title.upper() or struct.title
    bandar = next(p for p in model.pulses if p.key == "bandar")
    assert "BANDAR" in bandar.title.upper()

    earn0 = model.earnings[0]
    earn_blob = " ".join(model.earnings) if isinstance(earn0, str) else str(model.earnings)
    assert "Q" in earn_blob or "119" in earn_blob or model.earnings

    assert any("13" in m.value for m in model.metrics)

    # Compact more section until d
    assert "d detail" in model.footer.lower() or "detail" in model.footer.lower()

    analyst = next(p for p in model.detail_panels if p.key == "analyst")
    assert any("BUY" in ln or "Target" in ln or "3B" in ln for ln in analyst.lines)
    assert "analyst block present" not in " ".join(analyst.lines)
    # Single master detail chip design — panels keyed, not a wall of flag chips
    assert "analyst" in {p.key for p in model.detail_panels}


def test_text_fallback_still_has_mast_and_pulses():
    m = build_ticker_desk_model_from_text(ticker="TLKM", body="Close: 3,180")
    assert m.ticker == "TLKM"
    assert "3,180" in m.price
    assert len(m.pulses) == 3
    assert "LAST · LOCAL CLOSE" in m.as_text()
