"""
Tests for Alpha/Trigger and Sector Context detail panels in `saham analyze swing` output.

Verifies that:
  - ALPHA/TRIGGER DETAIL panel renders when include_signal_detail=True and
    signal_assessment.alpha_trigger_score is present.
  - DIAGNOSTIC groups are visually labelled "no scoring authority".
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

from src.adapters.cli.analyze_swing_commands import _print_swing_output
from src.application.services.swing_data_freshness import SwingDataFreshness
from src.application.use_case.accumulation_screen_use_case import AccumulationCandidate
from src.domain.value_objects.alpha_trigger_score import (
    AlphaTriggerGroupContribution,
    AlphaTriggerScore,
    EvidenceAuthorityStatus,
)
from src.domain.value_objects.sector_context_evidence import SectorContextEvidence
from src.domain.value_objects.institutional_accumulation_evidence import EvidenceStatus


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
    signal_assessment=None,
    sector_context_evidence=None,
) -> None:
    _print_swing_output(
        ticker="BBCA",
        today=date(2026, 7, 1),
        strategy_name="foreign-accumulation",
        data_freshness=_freshness(),
        flow_detail=None,
        broker_detail=None,
        window=7,
        accum=None,
        risk_resp=None,
        atr_value=None,
        sizing=None,
        setup_eval=None,
        setup_sizing=None,
        broker_quality_note=None,
        market_regime=None,
        capital=None,
        backtest_result=None,
        sentiment_resp=None,
        sentiment_warning=None,
        sentiment_verbose=False,
        include_strategy=False,
        include_sentiment=False,
        include_flow_detail=False,
        include_signal_detail=include_signal_detail,
        include_risk_detail=False,
        include_market_detail=include_market_detail,
        signal_assessment=signal_assessment,
        sector_context_evidence=sector_context_evidence,
    )


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

    def test_production_group_not_labelled_no_authority(self, capsys):
        ats = _alpha_trigger_score(with_production=True, with_diagnostic=False)
        sa = _minimal_signal_assessment(alpha_trigger_score=ats)
        _call_print(include_signal_detail=True, signal_assessment=sa)

        out = capsys.readouterr().out
        assert "PRODUCTION" in out
        # The "no scoring authority" label must NOT appear for production-only groups
        assert "no scoring authority" not in out

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
