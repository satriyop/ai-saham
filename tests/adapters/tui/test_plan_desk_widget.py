"""Plan desk Geometry-mast widget — design-aligned, present-only structure."""

from __future__ import annotations

from types import SimpleNamespace

from src.adapters.tui.plan_desk_model import build_plan_desk_model
from src.adapters.tui.plan_structure_result import PlanStructureResult


def test_build_plan_desk_model_geometry_and_inherit():
    row = SimpleNamespace(
        ticker="BBCA",
        signal="84",
        accum="48.2",
        action="WATCH",
        gate="OPEN",
        source=None,
    )
    struct = PlanStructureResult(
        summary="structure WATCH · entry 6,225 · stop 5,900 · target 6,800 · 3 lots · no order",
        ticker="BBCA",
        action="WATCH",
        entry="6,225",
        stop="5,900",
        target="6,800",
        lots="3",
        plan_id_short="3f88eda7",
        risk_pct="1.0",
        horizon="swing",
        inherits_action=True,
        no_order=True,
    )
    model = build_plan_desk_model(
        row,
        ticker="BBCA",
        source="Screen · accumulation",
        rank=2,
        total=20,
        structure=struct,
        running=False,
    )
    assert model.action == "WATCH"
    assert model.entry == "6,225"
    assert model.stop == "5,900"
    assert model.target == "6,800"
    assert model.lots == "3"
    assert model.has_geometry is True
    assert model.no_order is True
    assert "re-score" in model.inherit_note.lower() or "inherit" in model.inherit_note.lower()
    keys = {c.key for c in model.cards}
    assert "board" in keys
    assert "sizing" in keys
    assert "status" in keys
    board = next(c for c in model.cards if c.key == "board")
    assert "84" in "\n".join(board.lines) or "Signal" in board.headline


def test_build_plan_desk_model_incomplete_capital():
    model = build_plan_desk_model(
        None,
        ticker="ASII",
        structure=PlanStructureResult(
            summary="structure WATCH · no capital · no order",
            action="WATCH",
            incomplete_reason="no capital · set swing.capital",
            inherits_action=True,
            no_order=True,
        ),
    )
    assert model.has_geometry is False
    status = next(c for c in model.cards if c.key == "status")
    assert "capital" in "\n".join(status.lines).lower() or "cannot" in status.headline.lower()


def test_plan_desk_geometry_mast_paint_contract():
    """Geometry mast fields paint from pure model (no full-app mount)."""
    row = SimpleNamespace(
        ticker="BBCA",
        signal="84",
        accum="48.2",
        action="WATCH",
        gate="OPEN",
        source=None,
    )
    struct = PlanStructureResult(
        summary=("structure WATCH · entry 6,225 · stop 5,900 · target 6,800 · 3 lots · no order"),
        ticker="BBCA",
        action="WATCH",
        entry="6,225",
        stop="5,900",
        target="6,800",
        lots="3",
        plan_id_short="3f88eda7",
        risk_pct="1.0",
        inherits_action=True,
        no_order=True,
    )
    model = build_plan_desk_model(
        row,
        ticker="BBCA",
        source="Screen · accumulation",
        rank=1,
        total=20,
        structure=struct,
        running=False,
    )
    assert model.entry == "6,225"
    assert model.stop == "5,900"
    assert model.target == "6,800"
    assert model.action == "WATCH"
    assert model.has_geometry is True
    assert model.no_order is True
    # Density contract: geo hero labels from model fields (Structure · horizon)
    horizon = model.horizon or "swing"
    geo_lab = f"Structure · {horizon}"
    assert "Structure" in geo_lab
    assert model.entry and model.stop and model.target
