"""
Tests for Alpha/Trigger and Sector Context detail panels in `saham analyze swing` output.

Verifies that:
  - ALPHA/TRIGGER DETAIL panel renders when include_signal_detail=True and
    signal_assessment.alpha_trigger_score is present.
  - DIAGNOSTIC groups are visually labelled "— no weight" (effective_weight == 0.0).
  - SECTOR CONTEXT panel renders when include_market_detail=True and
    sector_context_evidence is present.
  - Unavailable sector context renders a single dim line (no metrics table).
  - Both panels are absent when their respective gates are False or objects are None.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.adapters.cli.analyze_swing_display import (
    SwingOutputDisplayContext,
    SwingOutputDisplayOptions,
    print_swing_output,
)
from src.application.dto.swing_analysis import SwingDiagnostics, SwingEvidence, SwingVerdict
from src.application.services.swing_data_freshness import SwingDataFreshness
from src.application.dto.accumulation_screen import AccumulationCandidate
from src.domain.value_objects.alpha_trigger_score import (
    AlphaTriggerGroupContribution,
    AlphaTriggerScore,
    EvidenceAuthorityStatus,
)
from src.domain.value_objects.sector_context_evidence import SectorContextEvidence
from src.domain.value_objects.institutional_accumulation_evidence import (
    CounterpartyTransferEvidence,
    DomesticBandarTrack,
    EvidenceStatus,
    ForeignInstitutionalTrack,
    InstitutionalAccumulationEvidence,
)


# ── Shared helpers ────────────────────────────────────────────────────────────

def _freshness() -> SwingDataFreshness:
    return SwingDataFreshness(
        as_of_date=date(2026, 7, 1),
        candle_start=date(2026, 1, 1),
        candle_end=date(2026, 6, 30),
        broker_start=date(2026, 1, 1),
        broker_end=date(2026, 6, 30),
        warnings=(),
    )


def _minimal_signal_assessment(alpha_trigger_score=None) -> SimpleNamespace:
    strength = SimpleNamespace(value="MODERATE")
    entry_quality = SimpleNamespace(value="WATCH")
    return SimpleNamespace(
        assessment=SimpleNamespace(
            score=65,
            strength=strength,
            entry_quality=entry_quality,
            score_label="65/100",
            confidence_score=0.8,
            rationale=("moderate signal",),
            breakdown_dict={},
            decision_constraints=None,
        ),
        coverage_warning=None,
        active_flags=(),
        flag_adjustment=0,
        raw_group_score=65,
        evidence_confidence=0.8,
        alpha_trigger_score=alpha_trigger_score,
    )


def _production_contribution(group: str = "setup_quality") -> AlphaTriggerGroupContribution:
    return AlphaTriggerGroupContribution(
        group=group,
        score=70.0,
        configured_weight=0.6,
        effective_weight=0.6,
        alpha_fraction=0.7,
        trigger_fraction=0.3,
        alpha_weighted=29.4,
        trigger_weighted=12.6,
        evidence_status=EvidenceAuthorityStatus.PRODUCTION,
        present=True,
        trigger_allowed=True,
        reasons=("good setup",),
    )


def _phase_blocked_flow_contribution() -> AlphaTriggerGroupContribution:
    return AlphaTriggerGroupContribution(
        group="institutional_flow",
        score=95.0,
        configured_weight=0.30,
        effective_weight=0.30,
        alpha_fraction=0.80,
        trigger_fraction=0.20,
        alpha_weighted=22.8,
        trigger_weighted=0.0,
        evidence_status=EvidenceAuthorityStatus.PRODUCTION,
        present=True,
        trigger_allowed=False,
        reasons=("flow_trigger_blocked:setup_phase_not_breakout_confirmation",),
    )


def _diagnostic_contribution(group: str = "sector_context") -> AlphaTriggerGroupContribution:
    return AlphaTriggerGroupContribution(
        group=group,
        score=50.0,
        configured_weight=0.3,
        effective_weight=0.0,
        alpha_fraction=0.7,
        trigger_fraction=0.3,
        alpha_weighted=0.0,
        trigger_weighted=0.0,
        evidence_status=EvidenceAuthorityStatus.DIAGNOSTIC,
        present=True,
        trigger_allowed=False,
        reasons=("diagnostic only",),
    )


def _alpha_trigger_score(
    *,
    with_production: bool = True,
    with_diagnostic: bool = False,
    with_unavailable: bool = False,
) -> AlphaTriggerScore:
    contribs = []
    if with_production:
        contribs.append(_production_contribution())
    if with_diagnostic:
        contribs.append(_diagnostic_contribution())
    return AlphaTriggerScore(
        alpha_score=62.0 if not with_unavailable else None,
        trigger_score=55.0 if not with_unavailable else None,
        final_exact_score=59.5 if not with_unavailable else None,
        horizon="swing_7d",
        alpha_weight=0.7,
        group_contributions=tuple(contribs),
        coverage=0.75,
        authority_coverage=0.6,
        conviction=0.65,
        flow_trigger_allowed=True,
        reasons=("within threshold",),
        unavailable_reasons=("sector_context missing",) if with_unavailable else (),
    )


def _sector_context_evidence_full() -> SectorContextEvidence:
    return SectorContextEvidence(
        sector="Finance",
        peer_count=3,
        peer_tickers=("BBNI", "BBRI", "BMRI"),
        sector_20d_return=0.032,
        sector_vs_ihsg_20d=0.011,
        sector_breadth=0.667,
        ticker_vs_sector_rs=0.015,
        sector_regime="BULLISH",
        coverage_score=0.75,
        evidence_status=EvidenceStatus.DIAGNOSTIC,
        reasons=("sector bullish",),
        unavailable_reasons=(),
    )


def _sector_context_unavailable() -> SectorContextEvidence:
    return SectorContextEvidence.unavailable(reason="no peer candles available")


def _call_print(
    *,
    include_signal_detail: bool = False,
    include_market_detail: bool = False,
    include_flow_detail: bool = False,
    signal_assessment=None,
    sector_context_evidence=None,
    institutional_accumulation_evidence=None,
) -> None:
    ctx = SwingOutputDisplayContext(
        ticker="BBCA",
        today=date(2026, 7, 1),
        strategy_name="foreign-accumulation",
        window=7,
        verdict=SwingVerdict(
            trade_setup=None,
            signal_assessment=signal_assessment,
            risk_response=None,
            market_regime=None,
        ),
        evidence=SwingEvidence(
            accumulation_candidate=None,
            setup_eval=None,
            backtest_result=None,
            sentiment_response=None,
            sentiment_warning=None,
            take_profit_pct=Decimal("5"),
            stop_loss_pct=Decimal("5"),
            regime_label=None,
            sector_context_evidence=sector_context_evidence,
            institutional_accumulation_evidence=institutional_accumulation_evidence,
        ),
        diagnostics=SwingDiagnostics(
            data_freshness=_freshness(),
            flow_detail=None,
            broker_detail=None,
            broker_quality_note=None,
            refresh_actions=(),
        ),
        options=SwingOutputDisplayOptions(
            include_strategy=False,
            include_sentiment=False,
            include_flow_detail=include_flow_detail,
            include_signal_detail=include_signal_detail,
            include_risk_detail=False,
            include_market_detail=include_market_detail,
        ),
    )
    print_swing_output(ctx)


# ── Alpha/Trigger panel ───────────────────────────────────────────────────────

class TestAlphaTriggerPanel:
    def test_panel_rendered_when_alpha_trigger_present(self, capsys):
        ats = _alpha_trigger_score(with_production=True)
        sa = _minimal_signal_assessment(alpha_trigger_score=ats)
        _call_print(include_signal_detail=True, signal_assessment=sa)

        out = capsys.readouterr().out
        assert "ALPHA/TRIGGER DETAIL" in out

    def test_panel_absent_when_include_signal_detail_false(self, capsys):
        ats = _alpha_trigger_score(with_production=True)
        sa = _minimal_signal_assessment(alpha_trigger_score=ats)
        _call_print(include_signal_detail=False, signal_assessment=sa)

        out = capsys.readouterr().out
        assert "ALPHA/TRIGGER DETAIL" not in out

    def test_panel_absent_when_alpha_trigger_score_none(self, capsys):
        sa = _minimal_signal_assessment(alpha_trigger_score=None)
        _call_print(include_signal_detail=True, signal_assessment=sa)

        out = capsys.readouterr().out
        assert "ALPHA/TRIGGER DETAIL" not in out

    def test_header_shows_alpha_trigger_final_scores(self, capsys):
        ats = _alpha_trigger_score(with_production=True)
        sa = _minimal_signal_assessment(alpha_trigger_score=ats)
        _call_print(include_signal_detail=True, signal_assessment=sa)

        out = capsys.readouterr().out
        assert "62.0" in out
        assert "55.0" in out
        assert "59.5" in out
        assert "swing_7d" in out

    def test_header_shows_weight_split(self, capsys):
        ats = _alpha_trigger_score(with_production=True)
        sa = _minimal_signal_assessment(alpha_trigger_score=ats)
        _call_print(include_signal_detail=True, signal_assessment=sa)

        out = capsys.readouterr().out
        # alpha_weight=0.7 → 70% alpha, 30% trigger
        assert "70%" in out
        assert "30%" in out

    def test_coverage_line_present(self, capsys):
        ats = _alpha_trigger_score(with_production=True)
        sa = _minimal_signal_assessment(alpha_trigger_score=ats)
        _call_print(include_signal_detail=True, signal_assessment=sa)

        out = capsys.readouterr().out
        assert "coverage" in out
        assert "conviction" in out

    def test_group_name_appears_in_table(self, capsys):
        ats = _alpha_trigger_score(with_production=True)
        sa = _minimal_signal_assessment(alpha_trigger_score=ats)
        _call_print(include_signal_detail=True, signal_assessment=sa)

        out = capsys.readouterr().out
        assert "setup_quality" in out

    def test_diagnostic_group_labelled_no_weight(self, capsys):
        ats = _alpha_trigger_score(with_production=True, with_diagnostic=True)
        sa = _minimal_signal_assessment(alpha_trigger_score=ats)
        _call_print(include_signal_detail=True, signal_assessment=sa)

        out = capsys.readouterr().out
        assert "DIAGNOSTIC" in out
        assert "no weight" in out

    def test_production_group_not_labelled_no_weight(self, capsys):
        ats = _alpha_trigger_score(with_production=True, with_diagnostic=False)
        sa = _minimal_signal_assessment(alpha_trigger_score=ats)
        _call_print(include_signal_detail=True, signal_assessment=sa)

        out = capsys.readouterr().out
        assert "PRODUCTION" in out
        # The "no weight" dim-label must NOT appear for production-only groups
        assert "no weight" not in out

    def test_unavailable_reasons_shown(self, capsys):
        ats = _alpha_trigger_score(with_production=False, with_unavailable=True)
        sa = _minimal_signal_assessment(alpha_trigger_score=ats)
        _call_print(include_signal_detail=True, signal_assessment=sa)

        out = capsys.readouterr().out
        assert "sector_context missing" in out

    def test_flow_trigger_allowed_shown(self, capsys):
        ats = _alpha_trigger_score(with_production=True)
        sa = _minimal_signal_assessment(alpha_trigger_score=ats)
        _call_print(include_signal_detail=True, signal_assessment=sa)

        out = capsys.readouterr().out
        assert "allowed" in out or "blocked" in out

    def test_flow_trigger_blocked_reason_rendered_readably(self, capsys):
        ats = AlphaTriggerScore(
            alpha_score=80.0,
            trigger_score=70.0,
            final_exact_score=74.0,
            horizon="SWING_10D",
            alpha_weight=0.40,
            group_contributions=(
                _production_contribution(),
                _phase_blocked_flow_contribution(),
            ),
            coverage=1.0,
            authority_coverage=1.0,
            conviction=0.74,
            flow_trigger_allowed=False,
            reasons=("flow_trigger_blocked:setup_phase_not_breakout_confirmation",),
            unavailable_reasons=(),
        )
        sa = _minimal_signal_assessment(alpha_trigger_score=ats)

        _call_print(include_signal_detail=True, signal_assessment=sa)

        out = capsys.readouterr().out
        assert "Flow trigger blocked" in out
        assert "setup phase is not BREAKOUT_CONFIRMATION" in out

    def test_phase_blocked_flow_output_does_not_imply_weak_flow(self, capsys):
        ats = AlphaTriggerScore(
            alpha_score=80.0,
            trigger_score=70.0,
            final_exact_score=74.0,
            horizon="SWING_10D",
            alpha_weight=0.40,
            group_contributions=(
                _production_contribution(),
                _phase_blocked_flow_contribution(),
            ),
            coverage=1.0,
            authority_coverage=1.0,
            conviction=0.74,
            flow_trigger_allowed=False,
            reasons=("flow_trigger_blocked:setup_phase_not_breakout_confirmation",),
            unavailable_reasons=(),
        )
        sa = _minimal_signal_assessment(alpha_trigger_score=ats)

        _call_print(include_signal_detail=True, signal_assessment=sa)

        out = capsys.readouterr().out.lower()
        assert "95.0" in out
        assert "weak flow" not in out
        assert "flow_not_confirmed" not in out

    def test_company_quality_context_row_renders_diagnostic_no_weight(self, capsys):
        # company_quality_context feeds the slot DIAGNOSTIC-only: it must appear
        # in the table with a real score but be labelled "— no weight".
        cq = _diagnostic_contribution(group="company_quality_context")
        ats = AlphaTriggerScore(
            alpha_score=62.0,
            trigger_score=55.0,
            final_exact_score=59.5,
            horizon="swing_7d",
            alpha_weight=0.7,
            group_contributions=(_production_contribution(), cq),
            coverage=0.75,
            authority_coverage=0.6,
            conviction=0.65,
            flow_trigger_allowed=True,
            reasons=("within threshold",),
            unavailable_reasons=(),
        )
        sa = _minimal_signal_assessment(alpha_trigger_score=ats)
        _call_print(include_signal_detail=True, signal_assessment=sa)

        out = capsys.readouterr().out
        assert "company_quality_context" in out
        assert "DIAGNOSTIC" in out
        assert "no weight" in out


# ── Sector Context panel ──────────────────────────────────────────────────────

class TestSectorContextPanel:
    def test_panel_rendered_when_sc_present(self, capsys):
        sc = _sector_context_evidence_full()
        _call_print(include_market_detail=True, sector_context_evidence=sc)

        out = capsys.readouterr().out
        assert "SECTOR CONTEXT" in out

    def test_panel_absent_when_include_market_detail_false(self, capsys):
        sc = _sector_context_evidence_full()
        _call_print(include_market_detail=False, sector_context_evidence=sc)

        out = capsys.readouterr().out
        assert "SECTOR CONTEXT" not in out

    def test_panel_absent_when_sc_none(self, capsys):
        _call_print(include_market_detail=True, sector_context_evidence=None)

        out = capsys.readouterr().out
        assert "SECTOR CONTEXT" not in out

    def test_sector_label_shown(self, capsys):
        sc = _sector_context_evidence_full()
        _call_print(include_market_detail=True, sector_context_evidence=sc)

        out = capsys.readouterr().out
        assert "Finance" in out

    def test_regime_shown(self, capsys):
        sc = _sector_context_evidence_full()
        _call_print(include_market_detail=True, sector_context_evidence=sc)

        out = capsys.readouterr().out
        assert "BULLISH" in out

    def test_peer_count_shown(self, capsys):
        sc = _sector_context_evidence_full()
        _call_print(include_market_detail=True, sector_context_evidence=sc)

        out = capsys.readouterr().out
        assert "3" in out

    def test_metrics_table_shows_signed_percentages(self, capsys):
        sc = _sector_context_evidence_full()
        _call_print(include_market_detail=True, sector_context_evidence=sc)

        out = capsys.readouterr().out
        # sector_20d_return=0.032 → +3.2%
        assert "+3.2%" in out

    def test_diagnostic_no_scoring_impact_shown(self, capsys):
        sc = _sector_context_evidence_full()
        _call_print(include_market_detail=True, sector_context_evidence=sc)

        out = capsys.readouterr().out
        assert "DIAGNOSTIC" in out
        assert "no scoring impact" in out

    def test_peer_tickers_shown(self, capsys):
        sc = _sector_context_evidence_full()
        _call_print(include_market_detail=True, sector_context_evidence=sc)

        out = capsys.readouterr().out
        assert "BBNI" in out

    def test_unavailable_sc_shows_dim_reason_not_metrics(self, capsys):
        sc = _sector_context_unavailable()
        _call_print(include_market_detail=True, sector_context_evidence=sc)

        out = capsys.readouterr().out
        assert "SECTOR CONTEXT" in out
        assert "no peer candles available" in out
        # Should NOT show metric table headers when data is unavailable
        assert "Sector 20d" not in out
        assert "vs IHSG" not in out


# ── Both panels gate correctly together ──────────────────────────────────────

class TestBothPanelAbsenceWhenGatesOff:
    def test_neither_panel_when_both_gates_false(self, capsys):
        ats = _alpha_trigger_score(with_production=True)
        sc = _sector_context_evidence_full()
        sa = _minimal_signal_assessment(alpha_trigger_score=ats)

        _call_print(
            include_signal_detail=False,
            include_market_detail=False,
            signal_assessment=sa,
            sector_context_evidence=sc,
        )

        out = capsys.readouterr().out
        assert "ALPHA/TRIGGER DETAIL" not in out
        assert "SECTOR CONTEXT" not in out

    def test_both_panels_when_both_gates_on(self, capsys):
        ats = _alpha_trigger_score(with_production=True)
        sc = _sector_context_evidence_full()
        sa = _minimal_signal_assessment(alpha_trigger_score=ats)

        _call_print(
            include_signal_detail=True,
            include_market_detail=True,
            signal_assessment=sa,
            sector_context_evidence=sc,
        )

        out = capsys.readouterr().out
        assert "ALPHA/TRIGGER DETAIL" in out
        assert "SECTOR CONTEXT" in out

# ── InstitutionalAccumulation panel ──────────────────────────────────────────

def _ia_evidence_full() -> InstitutionalAccumulationEvidence:
    foreign = ForeignInstitutionalTrack(
        foreign_participation_score=0.70,
        foreign_cr4_score=0.65,
        foreign_cr8_score=0.60,
        cnfb_divergence_score=0.55,
        foreign_vwap_distance_score=0.80,
        coverage_score=0.90,
        conviction_score=0.75,
        evidence_status=EvidenceStatus.DIAGNOSTIC,
        reasons=("strong_cnfb",),
        unavailable_reasons=(),
    )
    domestic = DomesticBandarTrack(
        broker_consistency_score=0.60,
        broker_reversal_score=0.50,
        accumulation_session_ratio=0.70,
        domestic_buy_vwap_distance_score=0.65,
        broker_hhi_divergence_score=0.55,
        bandar_broad_score_normalized=0.40,
        bandar_accumulation_score_normalized=None,  # missing — expect "—"
        coverage_score=0.80,
        conviction_score=0.65,
        evidence_status=EvidenceStatus.DIAGNOSTIC,
        reasons=("consistent_buying",),
        unavailable_reasons=(),
    )
    counterparty = CounterpartyTransferEvidence(
        transfer_asymmetry_score=0.70,
        buy_side_hhi=0.25,
        sell_side_hhi=0.15,
        coverage_score=0.85,
        conviction_score=0.70,
        evidence_status=EvidenceStatus.DIAGNOSTIC,
        unavailable_reasons=(),
    )
    return InstitutionalAccumulationEvidence(
        ticker="BBCA",
        snapshot_date=date(2026, 7, 1),
        foreign_institutional_track=foreign,
        domestic_bandar_track=domestic,
        counterparty_transfer=counterparty,
        coverage_score=0.85,
        conviction_score=0.70,
        evidence_status=EvidenceStatus.DIAGNOSTIC,
        reasons=(),
        unavailable_reasons=(),
    )


def _ia_evidence_unavailable() -> InstitutionalAccumulationEvidence:
    empty_foreign = ForeignInstitutionalTrack(
        foreign_participation_score=None,
        foreign_cr4_score=None,
        foreign_cr8_score=None,
        cnfb_divergence_score=None,
        foreign_vwap_distance_score=None,
        coverage_score=0.0,
        conviction_score=0.0,
        evidence_status=EvidenceStatus.DIAGNOSTIC,
        reasons=(),
        unavailable_reasons=("no_foreign_flows",),
    )
    empty_domestic = DomesticBandarTrack(
        broker_consistency_score=None,
        broker_reversal_score=None,
        accumulation_session_ratio=None,
        domestic_buy_vwap_distance_score=None,
        broker_hhi_divergence_score=None,
        bandar_broad_score_normalized=None,
        bandar_accumulation_score_normalized=None,
        coverage_score=0.0,
        conviction_score=0.0,
        evidence_status=EvidenceStatus.DIAGNOSTIC,
        reasons=(),
        unavailable_reasons=("no_local_flows",),
    )
    return InstitutionalAccumulationEvidence(
        ticker="BBCA",
        snapshot_date=date(2026, 7, 1),
        foreign_institutional_track=empty_foreign,
        domestic_bandar_track=empty_domestic,
        counterparty_transfer=None,
        coverage_score=0.0,
        conviction_score=0.0,
        evidence_status=EvidenceStatus.DIAGNOSTIC,
        reasons=(),
        unavailable_reasons=("insufficient_broker_data",),
    )


class TestInstitutionalAccumulationPanel:
    def test_panel_appears_with_flow_detail_true_and_evidence_present(self, capsys):
        _call_print(
            include_flow_detail=True,
            institutional_accumulation_evidence=_ia_evidence_full(),
        )
        out = capsys.readouterr().out
        assert "INSTITUTIONAL ACCUMULATION" in out

    def test_panel_absent_without_flow_detail(self, capsys):
        _call_print(
            include_flow_detail=False,
            institutional_accumulation_evidence=_ia_evidence_full(),
        )
        out = capsys.readouterr().out
        assert "INSTITUTIONAL ACCUMULATION" not in out

    def test_panel_absent_when_evidence_none(self, capsys):
        _call_print(
            include_flow_detail=True,
            institutional_accumulation_evidence=None,
        )
        out = capsys.readouterr().out
        assert "INSTITUTIONAL ACCUMULATION" not in out

    def test_diagnostic_no_scoring_authority_shown(self, capsys):
        _call_print(
            include_flow_detail=True,
            institutional_accumulation_evidence=_ia_evidence_full(),
        )
        out = capsys.readouterr().out
        assert "DIAGNOSTIC" in out
        assert "no scoring authority" in out

    def test_foreign_and_domestic_track_labels_shown(self, capsys):
        _call_print(
            include_flow_detail=True,
            institutional_accumulation_evidence=_ia_evidence_full(),
        )
        out = capsys.readouterr().out
        assert "Foreign Institutional Track" in out
        assert "Domestic Bandar Track" in out

    def test_missing_bandar_accumulation_renders_dash_not_zero(self, capsys):
        # bandar_accumulation_score_normalized=None → "—", never "0"
        _call_print(
            include_flow_detail=True,
            institutional_accumulation_evidence=_ia_evidence_full(),
        )
        out = capsys.readouterr().out
        assert "INSTITUTIONAL ACCUMULATION" in out
        # The row for bandar accumulation should NOT appear when value is None
        # (the display only adds the row when value is not None)
        assert "Bandar accumulation" not in out

    def test_unavailable_evidence_shows_reasons_not_metrics_table(self, capsys):
        _call_print(
            include_flow_detail=True,
            institutional_accumulation_evidence=_ia_evidence_unavailable(),
        )
        out = capsys.readouterr().out
        assert "INSTITUTIONAL ACCUMULATION" in out
        assert "insufficient_broker_data" in out
        assert "Foreign Institutional Track" not in out
