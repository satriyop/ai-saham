"""Unit tests for sector macro panel on screen accum judgment desk."""

from datetime import date
from unittest.mock import patch

from src.adapters.cli.screen_accum_sector_macro_display import build_sector_macro_panel
from src.domain.value_objects.institutional_accumulation_evidence import EvidenceStatus
from src.domain.value_objects.sector_macro_context_evidence import (
    MacroFactorScore,
    SectorMacroContextEvidence,
)


def _smc() -> SectorMacroContextEvidence:
    return SectorMacroContextEvidence(
        sector_group="bank",
        as_of_date=date(2026, 7, 1),
        factors=(
            MacroFactorScore(
                name="bi_rate_policy",
                series="BI_RATE",
                value=-1.0,
                score=1.0,
                weight=0.55,
                label="FAVORABLE",
                rationale="cut",
            ),
        ),
        composite_score=0.8,
        macro_regime="SUPPORTIVE",
        coverage_score=1.0,
        evidence_status=EvidenceStatus.DIAGNOSTIC,
        reasons=("bi_rate_policy:FAVORABLE:1.00",),
        unavailable_reasons=(),
    )


def test_build_sector_macro_panel_renders_title_and_net_steps():
    with patch("src.adapters.cli.screen_accum_sector_macro_display.panel") as mock_panel:
        mock_panel.side_effect = lambda *a, **k: ("panel", k.get("title"), a)
        result = build_sector_macro_panel(_smc())
        assert result is not None
        assert mock_panel.called
        kwargs = mock_panel.call_args.kwargs
        assert kwargs.get("title") == "SECTOR MACRO"


def test_build_sector_macro_panel_none_when_missing():
    assert build_sector_macro_panel(None) is None


def test_bi_rate_value_display_is_net_not_percent():
    from src.adapters.cli.screen_accum_sector_macro_display import _factor_value_display

    assert _factor_value_display("BI_RATE", -1.0) == "-1 net"
    assert _factor_value_display("IDR=X", 0.01) == "+1.0%"
