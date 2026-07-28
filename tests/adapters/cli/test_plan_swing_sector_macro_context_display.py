"""Unit test for sector macro CLI panel (no network)."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.domain.value_objects.institutional_accumulation_evidence import EvidenceStatus
from src.domain.value_objects.sector_macro_context_evidence import (
    MacroFactorScore,
    SectorMacroContextEvidence,
)


def _smc() -> SectorMacroContextEvidence:
    return SectorMacroContextEvidence(
        sector_group="energy",
        as_of_date=date(2026, 7, 1),
        factors=(
            MacroFactorScore(
                name="coal_futures",
                series="MTF=F",
                value=0.06,
                score=1.0,
                weight=0.65,
                label="FAVORABLE",
                rationale="up",
            ),
        ),
        composite_score=0.9,
        macro_regime="SUPPORTIVE",
        coverage_score=1.0,
        evidence_status=EvidenceStatus.DIAGNOSTIC,
        reasons=("macro_regime:SUPPORTIVE",),
        unavailable_reasons=(),
    )


def test_print_sector_macro_panel_renders_when_detail_enabled():
    from src.adapters.cli.plan_swing_sector_macro_context_display import (
        print_sector_macro_context_panel,
    )

    ctx = SimpleNamespace(
        options=SimpleNamespace(include_market_detail=True),
        evidence=SimpleNamespace(sector_macro_context_evidence=_smc()),
    )
    with (
        patch("src.adapters.cli.plan_swing_sector_macro_context_display.console") as console_fn,
        patch("src.adapters.cli.plan_swing_sector_macro_context_display.panel") as panel_fn,
        patch("src.adapters.cli.plan_swing_sector_macro_context_display.compact_table") as table_fn,
    ):
        console = MagicMock()
        console_fn.return_value = console
        table = MagicMock()
        table_fn.return_value = table
        panel_fn.side_effect = lambda *a, **k: "PANEL"

        print_sector_macro_context_panel(ctx)

        assert console.print.called
        panel_fn.assert_called()
        # title SECTOR MACRO
        kwargs = panel_fn.call_args.kwargs
        assert kwargs.get("title") == "SECTOR MACRO"


def test_print_sector_macro_panel_skips_when_detail_disabled():
    from src.adapters.cli.plan_swing_sector_macro_context_display import (
        print_sector_macro_context_panel,
    )

    ctx = SimpleNamespace(
        options=SimpleNamespace(include_market_detail=False),
        evidence=SimpleNamespace(sector_macro_context_evidence=_smc()),
    )
    with patch("src.adapters.cli.plan_swing_sector_macro_context_display.console") as console_fn:
        console = MagicMock()
        console_fn.return_value = console
        print_sector_macro_context_panel(ctx)
        console.print.assert_not_called()
