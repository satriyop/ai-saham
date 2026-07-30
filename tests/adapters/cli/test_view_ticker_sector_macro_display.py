"""View ticker SECTOR MACRO panel rendering (shared helper, surface=view)."""

from datetime import date
from unittest.mock import patch

from src.adapters.cli.screen_accum_sector_macro_display import build_sector_macro_panel
from src.adapters.cli.view_ticker_json import ticker_dashboard_to_json_dict
from src.adapters.shared.view_ticker_dashboard_text import (
    format_ticker_dashboard_text,
)
from src.application.dto.ticker_dashboard import TickerDashboard
from src.application.services.ticker_dashboard_layout import panel_keys_for_mode
from src.application.services.ticker_dashboard_status import CacheStatus, FreshnessItem
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


def _dashboard_with_smc(*, brief: bool = False) -> TickerDashboard:
    return TickerDashboard(
        ticker="BBCA",
        mode="brief" if brief else "full",
        as_of=date(2026, 7, 23),
        today=date(2026, 7, 24),
        fetch_hint="saham fetch market BBCA",
        panel_keys=panel_keys_for_mode(brief=brief),
        freshness=(FreshnessItem("price", "Price", CacheStatus.MISSING),),
        related_actions=(),
        panel_errors=(),
        notation=None,
        fundamentals=None,
        forward_estimates=None,
        latest_close=None,
        price_structure=None,
        analyst=None,
        earnings=(),
        ownership=None,
        bandar=None,
        foreign_flow_points=(),
        foreign_flow_source=None,
        corp_actions=(),
        corp_status=CacheStatus.MISSING,
        insider_txns=(),
        insider_status=CacheStatus.MISSING,
        insider_last_known=None,
        seasonality=None,
        iev_rows=(),
        sentiment_logs=(),
        profile=None,
        candles=(),
        sector_macro_context_evidence=None if brief else _smc(),
    )


def _group_plain_text(group) -> str:
    texts = []
    for item in getattr(group, "renderables", []) or []:
        texts.append(getattr(item, "plain", str(item)))
    return " ".join(texts)


def test_view_surface_panel_has_diagnostic_and_judgment_pointer():
    with patch("src.adapters.cli.screen_accum_sector_macro_display.panel") as mock_panel:
        mock_panel.side_effect = lambda *a, **k: ("panel", k.get("title"), a)
        result = build_sector_macro_panel(_smc(), ticker="BBCA", surface="view")
        assert result is not None
        assert mock_panel.call_args.kwargs.get("title") == "SECTOR MACRO"
        joined = _group_plain_text(mock_panel.call_args.args[0])
        assert "DIAGNOSTIC" in joined
        assert "screen accum BBCA" in joined
        assert "Judgment" in joined


def test_view_surface_unavailable_evidence_still_has_diagnostic_and_judgment():
    """Pure fail-soft path: SectorMacroContextEvidence.unavailable — AC3 still holds."""
    smc = SectorMacroContextEvidence.unavailable(
        reason="sector_map:missing:consumer_goods",
        sector_group="consumer_goods",
        as_of_date=date(2026, 7, 1),
    )
    assert smc.macro_regime == "UNKNOWN"
    assert smc.factors == ()
    assert smc.unavailable_reasons

    with patch("src.adapters.cli.screen_accum_sector_macro_display.panel") as mock_panel:
        mock_panel.side_effect = lambda *a, **k: ("panel", k.get("title"), a)
        result = build_sector_macro_panel(smc, ticker="XXXX", surface="view")
        assert result is not None
        assert mock_panel.call_args.kwargs.get("title") == "SECTOR MACRO"
        joined = _group_plain_text(mock_panel.call_args.args[0])
        assert "unavailable" in joined.lower() or "sector_map:missing" in joined
        assert "DIAGNOSTIC" in joined
        assert "screen accum XXXX" in joined
        assert "Judgment" in joined

    # Full dashboard text path also keeps DIAGNOSTIC for unavailable evidence
    dash_unavail = TickerDashboard(
        ticker="XXXX",
        mode="full",
        as_of=date(2026, 7, 23),
        today=date(2026, 7, 24),
        fetch_hint="saham fetch market XXXX",
        panel_keys=panel_keys_for_mode(brief=False),
        freshness=(FreshnessItem("price", "Price", CacheStatus.MISSING),),
        related_actions=(),
        panel_errors=(),
        notation=None,
        fundamentals=None,
        forward_estimates=None,
        latest_close=None,
        price_structure=None,
        analyst=None,
        earnings=(),
        ownership=None,
        bandar=None,
        foreign_flow_points=(),
        foreign_flow_source=None,
        corp_actions=(),
        corp_status=CacheStatus.MISSING,
        insider_txns=(),
        insider_status=CacheStatus.MISSING,
        insider_last_known=None,
        seasonality=None,
        iev_rows=(),
        sentiment_logs=(),
        profile=None,
        candles=(),
        sector_macro_context_evidence=smc,
    )
    text = format_ticker_dashboard_text(dash_unavail, width=100)
    assert "SECTOR MACRO" in text
    assert "DIAGNOSTIC" in text
    assert "screen accum XXXX" in text
    assert "sector_map:missing" in text or "unavailable" in text.lower()


def test_format_dashboard_text_includes_sector_macro_title():
    text = format_ticker_dashboard_text(_dashboard_with_smc(brief=False), width=100)
    assert "SECTOR MACRO" in text
    assert "DIAGNOSTIC" in text
    assert "screen accum BBCA" in text
    # No Action/Gate invented by this panel block
    assert "TradeSetup" not in text


def test_format_dashboard_brief_omits_sector_macro_panel_key():
    # brief panel_keys exclude sector_macro — no full SECTOR MACRO table
    assert "sector_macro" not in panel_keys_for_mode(brief=True)
    text = format_ticker_dashboard_text(_dashboard_with_smc(brief=True), width=100)
    # Full panel title should not dominate brief (evidence not attached in brief DTO either)
    assert "bi_rate_policy" not in text


def test_json_includes_sector_macro_when_full():
    payload = ticker_dashboard_to_json_dict(_dashboard_with_smc(brief=False))
    data = payload["data"]
    assert "sector_macro" in data["panels"]
    smc = data["sector_macro_context_evidence"]
    assert smc is not None
    assert smc["diagnostic"] is True
    assert smc["authority"] == "DIAGNOSTIC"
    assert smc["macro_regime"] == "SUPPORTIVE"
    assert "screen accum BBCA" in smc["judgment_command"]
    assert smc["evidence_status"] == "DIAGNOSTIC"


def test_json_brief_has_no_sector_macro_key():
    payload = ticker_dashboard_to_json_dict(_dashboard_with_smc(brief=True))
    assert "sector_macro" not in payload["data"]["panels"]
    assert "sector_macro_context_evidence" not in payload["data"]


def test_plan_swing_evidence_still_no_sector_macro_printer():
    from src.adapters.cli import plan_swing_evidence_display as evidence_mod

    src = open(evidence_mod.__file__, encoding="utf-8").read()
    assert "print_sector_macro_context_panel" not in src
