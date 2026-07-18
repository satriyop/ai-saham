"""
Unit tests for AuditSignalUseCase (Phase 0 observability).

Synthetic SignalContext data only — no DB, no providers. Verifies factor
presence detection, weighted contributions, and the renormalized_score preview
against the production AssessSignalUseCase output.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.application.use_case.assess_signal_use_case import (
    _DEFAULT_WEIGHTS,
    AssessSignalRequest,
    AssessSignalUseCase,
    SignalEngineConfig,
)
from src.application.use_case.audit_signal_use_case import (
    AuditSignalRequest,
    AuditSignalUseCase,
)
from src.domain.value_objects.signal_assessment import SignalContext

SNAPSHOT = date(2026, 7, 3)


def _audit(ctx: SignalContext):
    weights = dict(_DEFAULT_WEIGHTS)
    return AuditSignalUseCase().execute(
        AuditSignalRequest(
            ticker=ctx.ticker,
            signal_context=ctx,
            weights=weights,
            raw_weights=weights,
            config=SignalEngineConfig(),
        )
    ).report


def _assess_score(ctx: SignalContext) -> int:
    return (
        AssessSignalUseCase(weights=dict(_DEFAULT_WEIGHTS))
        .execute(AssessSignalRequest(ticker=ctx.ticker, signal_context=ctx))
        .assessment.score
    )


def test_complete_evidence_all_present():
    ctx = SignalContext(
        ticker="TEST",
        snapshot_date=SNAPSHOT,
        bandar_broad_score=6,
        bandar_max_range=6,
        foreign_flow_quality=0.9,
        insider_net_buy_ratio=0.8,
        seasonality_win_rate=75.0,
        seasonality_avg_return_pct=2.5,
        seasonality_total_years=5,
        seasonality_back_years=5,
        analyst_buy_pct=0.85,
        analyst_upside_pct=25.0,
        forward_pe=12.0,
    )
    report = _audit(ctx)

    assert report.factors_present == 6
    assert report.factors_missing == 0
    assert all(e.present for e in report.entries)
    # final_score matches the production AssessSignalUseCase output
    assert report.final_score == _assess_score(ctx)
    # all present + weights sum to 1.0 → renormalized == final
    assert report.renormalized_score == report.final_score
    assert report.coverage_warning is None


def test_no_evidence_all_missing():
    ctx = SignalContext(ticker="TEST", snapshot_date=SNAPSHOT)
    report = _audit(ctx)

    assert report.factors_present == 0
    assert report.factors_missing == 6
    assert all(not e.present for e in report.entries)
    assert all(e.component_score == 50.0 for e in report.entries)
    assert all(e.raw_value == "None" for e in report.entries)
    assert report.final_score == 50
    assert report.renormalized_score == 50
    assert report.coverage_warning is not None  # 6 missing ≥ 3


def test_partial_evidence_renormalized_higher():
    # 3 present (all high-scoring), 3 missing → renormalized excludes neutral fill
    ctx = SignalContext(
        ticker="TEST",
        snapshot_date=SNAPSHOT,
        bandar_broad_score=6,
        bandar_max_range=6,       # → 100
        foreign_flow_quality=1.0,  # → 100
        forward_pe=8.0,            # → 95 (very cheap)
    )
    report = _audit(ctx)

    present = {e.factor for e in report.entries if e.present}
    assert present == {"bandar_intensity", "foreign_flow_quality", "forward_valuation"}
    assert report.factors_present == 3
    assert report.factors_missing == 3
    # present factors all score well above neutral → renormalized beats flat score
    assert report.renormalized_score != report.final_score
    assert report.renormalized_score > report.final_score
    assert report.coverage_warning is not None  # 3 missing ≥ 3


def test_insider_only_renormalized_100():
    ctx = SignalContext(
        ticker="TEST",
        snapshot_date=SNAPSHOT,
        insider_net_buy_ratio=1.0,  # → 100
    )
    report = _audit(ctx)

    insider = next(e for e in report.entries if e.factor == "insider_activity")
    assert insider.present is True
    assert insider.component_score == 100.0
    assert report.factors_present == 1
    # single present factor scoring 100 → renormalized pool is that factor alone
    assert report.renormalized_score == 100


def test_coverage_warning_three_missing():
    # 3 present, 3 missing → warning fires (threshold is 3)
    ctx = SignalContext(
        ticker="TEST",
        snapshot_date=SNAPSHOT,
        bandar_broad_score=3,
        bandar_max_range=6,
        foreign_flow_quality=0.5,
        insider_net_buy_ratio=0.0,
    )
    report = _audit(ctx)
    assert report.factors_missing == 3
    assert report.coverage_warning is not None


def test_weighted_contribution_and_configured_weight():
    ctx = SignalContext(
        ticker="TEST",
        snapshot_date=SNAPSHOT,
        bandar_broad_score=6,
        bandar_max_range=6,
    )
    report = _audit(ctx)
    bandar = next(e for e in report.entries if e.factor == "bandar_intensity")
    assert bandar.active_weight == pytest.approx(_DEFAULT_WEIGHTS["bandar_intensity"])
    assert bandar.configured_weight == pytest.approx(_DEFAULT_WEIGHTS["bandar_intensity"])
    assert bandar.weighted_contribution == pytest.approx(
        bandar.active_weight * bandar.component_score
    )
    assert bandar.raw_value == "broad_score=6/6"


def test_seasonality_unknown_years_is_missing_in_audit_and_evidence():
    ctx = SignalContext(
        ticker="TEST",
        snapshot_date=SNAPSHOT,
        seasonality_win_rate=75.0,
        seasonality_avg_return_pct=2.5,
    )
    response = AuditSignalUseCase().execute(
        AuditSignalRequest(
            ticker=ctx.ticker,
            signal_context=ctx,
            weights=dict(_DEFAULT_WEIGHTS),
            raw_weights=dict(_DEFAULT_WEIGHTS),
            config=SignalEngineConfig(),
        )
    )

    seasonal = next(e for e in response.report.entries if e.factor == "seasonality_edge")
    assert seasonal.present is False
    assert seasonal.component_score == pytest.approx(50.0)
    assert "seasonality_edge" in response.evidence.missing_factors


def test_display_report_wording(capsys):
    from src.adapters.cli.analyze_signal_audit_commands import _display_report
    from src.domain.value_objects.signal_audit import SignalAuditEntry, SignalAuditReport
    from datetime import date

    report = SignalAuditReport(
        ticker="BBCA",
        snapshot_date=date(2026, 7, 3),
        entries=(
            SignalAuditEntry(
                factor="bandar_intensity",
                present=True,
                raw_value="broad_score=6/6",
                component_score=100.0,
                configured_weight=0.20,
                active_weight=0.20,
                weighted_contribution=20.0,
            ),
        ),
        final_score=75,
        strength="STRONG",
        entry_quality="ENTER",
        coverage_warning=None,
        factors_present=1,
        factors_missing=5,
        renormalized_score=100,
    )

    _display_report(report)
    captured = capsys.readouterr()

    # Assert visible wording is correctly changed
    assert "Archived Signal Baseline Audit" in captured.out
    assert "ARCHIVED BASELINE SCORE" in captured.out
    assert "Archived factor presence" in captured.out

    # Assert old strings are NOT present
    assert "Signal Audit" not in captured.out.replace("Archived Signal Baseline Audit", "")
    assert "COMPOSITE SCORE" not in captured.out
    assert "Coverage" not in captured.out.replace("Archived factor presence", "")
    # Check that neither archived score is described as canonical
    assert "canonical score" not in captured.out.lower()
    assert "canonical baseline score" not in captured.out.lower()

    # Assert numeric values and factor rows remain unchanged
    assert "bandar_intensity" in captured.out
    assert "broad_score=6/6" in captured.out
    assert "100.0" in captured.out
    assert "75/100" in captured.out
    assert "STRONG" in captured.out
    assert "ENTER" in captured.out
    assert "100/100" in captured.out
