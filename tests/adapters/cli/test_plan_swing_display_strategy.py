"""
Regression tests for Phase D CLI adapter: strategy evidence display.

Verifies that:
  1. STRATEGY DIAGNOSTIC EVIDENCE panel renders when include_strategy=True and
     strategy_evidence (StrategyEvidence VO) is present.
  2. Strategy name / rule name / outcome renders.
  3. MATCHED / NOT_MATCHED / UNAVAILABLE / INVALID display clearly.
  4. Coverage / conviction / freshness render if present.
  5. If strategy evidence is unavailable, display reason compactly.
  6. Without the strategy flag (include_strategy=False), strategy evidence
     does NOT render.
  7. Output does not imply strategy evidence controls ENTER/WATCH/AVOID.
  8. Matched-rule fields (rule_name, rule_outcome, setup_family, setup_phase,
     evidence_route, rationale) render correctly.
  9. Strategy evidence without a matched_rule renders gracefully.

Layer: Adapter (render-only, no scoring, no DecisionPolicy changes).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.adapters.cli.plan_swing_display import (
    SwingOutputDisplayContext,
    SwingOutputDisplayOptions,
    print_swing_output,
)
from src.application.dto.plan_swing import (
    SignalAssessmentAvailability,
    SignalAssessmentStatus,
    SignalAssessmentUnavailableReason,
    SwingDiagnostics,
    SwingEvidence,
    SwingVerdict,
)
from src.application.services.swing_data_freshness import SwingDataFreshness
from src.domain.value_objects.strategy_evidence import (
    StrategyEvidence,
    StrategyEvidenceOutcome,
    StrategyRuleEvidence,
)

# ── Shared helpers ─────────────────────────────────────────────────────────────


def _freshness() -> SwingDataFreshness:
    return SwingDataFreshness(
        as_of_date=date(2026, 7, 1),
        candle_start=date(2026, 1, 1),
        candle_end=date(2026, 6, 30),
        broker_start=date(2026, 1, 1),
        broker_end=date(2026, 6, 30),
        warnings=(),
    )


def _matched_rule(
    *,
    rule_name: str = "volume_dry_up_then_expansion",
    rule_outcome: str = "ACCUMULATION_CONFIRMED",
    setup_family: str = "accumulation",
    setup_phase: str = "COMPRESSION",
    evidence_route: str = "indicator_registry",
    rationale: tuple[str, ...] = ("Volume expanded after dry-up",),
) -> StrategyRuleEvidence:
    return StrategyRuleEvidence(
        strategy_name="foreign-accumulation",
        rule_name=rule_name,
        rule_outcome=rule_outcome,
        evidence_route=evidence_route,
        setup_family=setup_family,
        setup_phase=setup_phase,
        rationale=rationale,
    )


def _make_strategy_evidence(
    outcome: StrategyEvidenceOutcome = StrategyEvidenceOutcome.MATCHED,
    *,
    with_matched_rule: bool = True,
    coverage_score: float | None = 0.80,
    conviction_score: float | None = 0.72,
    freshness_score: float | None = 0.90,
    rationale: tuple[str, ...] = ("Rule confirmed accumulation pattern",),
    unavailable_reasons: tuple[str, ...] = (),
) -> StrategyEvidence:
    return StrategyEvidence(
        ticker="BBCA",
        snapshot_date=date(2026, 7, 1),
        strategy_name="foreign-accumulation",
        outcome=outcome,
        matched_rule=_matched_rule() if with_matched_rule else None,
        coverage_score=coverage_score,
        conviction_score=conviction_score,
        freshness_score=freshness_score,
        rationale=rationale,
        unavailable_reasons=unavailable_reasons,
    )


def _call_print(
    *,
    include_strategy: bool = True,
    strategy_evidence: StrategyEvidence | None = None,
    backtest_result=None,
) -> None:
    ctx = SwingOutputDisplayContext(
        ticker="BBCA",
        today=date(2026, 7, 1),
        strategy_name="foreign-accumulation",
        window=7,
        verdict=SwingVerdict(
            trade_setup=None,
            signal_assessment=None,
            risk_response=None,
            market_regime=None,
            signal_assessment_availability=SignalAssessmentAvailability(
                status=SignalAssessmentStatus.UNAVAILABLE,
                unavailable_reason=SignalAssessmentUnavailableReason.NO_PRODUCTION_SIGNAL_EVIDENCE,
            ),
        ),
        evidence=SwingEvidence(
            accumulation_candidate=None,
            setup_eval=None,
            backtest_result=backtest_result,
            sentiment_response=None,
            sentiment_warning=None,
            take_profit_pct=Decimal("5"),
            stop_loss_pct=Decimal("5"),
            regime_label=None,
            strategy_rule_evidence=strategy_evidence,
        ),
        diagnostics=SwingDiagnostics(
            data_freshness=_freshness(),
            flow_detail=None,
            broker_detail=None,
            broker_quality_note=None,
            refresh_actions=(),
        ),
        options=SwingOutputDisplayOptions(
            include_strategy=include_strategy,
            include_sentiment=False,
            include_flow_detail=False,
            include_signal_detail=False,
            include_risk_detail=False,
            include_market_detail=False,
        ),
    )
    print_swing_output(ctx)


# ── Panel gate tests ───────────────────────────────────────────────────────────


class TestStrategyEvidencePanelGate:
    def test_panel_rendered_when_include_strategy_and_evidence_present(self, capsys):
        se = _make_strategy_evidence()
        _call_print(include_strategy=True, strategy_evidence=se)

        out = capsys.readouterr().out
        assert "STRATEGY DIAGNOSTIC EVIDENCE" in out

    def test_panel_absent_when_include_strategy_false(self, capsys):
        se = _make_strategy_evidence()
        _call_print(include_strategy=False, strategy_evidence=se)

        out = capsys.readouterr().out
        assert "STRATEGY DIAGNOSTIC EVIDENCE" not in out

    def test_strategy_evidence_vo_text_absent_when_evidence_none_and_no_backtest(self, capsys):
        # When include_strategy=True but strategy_evidence is None and backtest_result is None,
        # the panel renders a "no data" fallback. The StrategyEvidence VO-specific fields
        # (Strategy Rule header, outcome label) must NOT appear.
        _call_print(include_strategy=True, strategy_evidence=None)

        out = capsys.readouterr().out
        assert "Strategy Rule:" not in out
        assert "MATCHED" not in out

    def test_panel_rendered_with_evidence_even_without_backtest_result(self, capsys):
        se = _make_strategy_evidence()
        _call_print(include_strategy=True, strategy_evidence=se, backtest_result=None)

        out = capsys.readouterr().out
        assert "STRATEGY DIAGNOSTIC EVIDENCE" in out


# ── Outcome display tests ──────────────────────────────────────────────────────


class TestStrategyEvidenceOutcomeDisplay:
    def test_matched_outcome_shown(self, capsys):
        se = _make_strategy_evidence(outcome=StrategyEvidenceOutcome.MATCHED)
        _call_print(include_strategy=True, strategy_evidence=se)

        out = capsys.readouterr().out
        assert "MATCHED" in out

    def test_not_matched_outcome_shown(self, capsys):
        se = _make_strategy_evidence(
            outcome=StrategyEvidenceOutcome.NOT_MATCHED,
            with_matched_rule=False,
        )
        _call_print(include_strategy=True, strategy_evidence=se)

        out = capsys.readouterr().out
        assert "NOT_MATCHED" in out

    def test_unavailable_outcome_shown(self, capsys):
        se = _make_strategy_evidence(
            outcome=StrategyEvidenceOutcome.UNAVAILABLE,
            with_matched_rule=False,
            coverage_score=None,
            conviction_score=None,
            freshness_score=None,
            unavailable_reasons=("no indicator data",),
        )
        _call_print(include_strategy=True, strategy_evidence=se)

        out = capsys.readouterr().out
        assert "UNAVAILABLE" in out

    def test_invalid_outcome_shown(self, capsys):
        se = _make_strategy_evidence(
            outcome=StrategyEvidenceOutcome.INVALID,
            with_matched_rule=False,
            coverage_score=None,
            conviction_score=None,
            freshness_score=None,
        )
        _call_print(include_strategy=True, strategy_evidence=se)

        out = capsys.readouterr().out
        assert "INVALID" in out


# ── Strategy name and rule field tests ────────────────────────────────────────


class TestStrategyEvidenceNameAndRule:
    def test_strategy_name_shown(self, capsys):
        se = _make_strategy_evidence()
        _call_print(include_strategy=True, strategy_evidence=se)

        out = capsys.readouterr().out
        assert "foreign-accumulation" in out

    def test_rule_name_shown_when_matched_rule_present(self, capsys):
        se = _make_strategy_evidence()
        _call_print(include_strategy=True, strategy_evidence=se)

        out = capsys.readouterr().out
        assert "volume_dry_up_then_expansion" in out

    def test_rule_outcome_shown(self, capsys):
        se = _make_strategy_evidence()
        _call_print(include_strategy=True, strategy_evidence=se)

        out = capsys.readouterr().out
        assert "ACCUMULATION_CONFIRMED" in out

    def test_setup_family_shown(self, capsys):
        se = _make_strategy_evidence()
        _call_print(include_strategy=True, strategy_evidence=se)

        out = capsys.readouterr().out
        assert "accumulation" in out

    def test_setup_phase_shown(self, capsys):
        se = _make_strategy_evidence()
        _call_print(include_strategy=True, strategy_evidence=se)

        out = capsys.readouterr().out
        assert "COMPRESSION" in out

    def test_evidence_route_shown(self, capsys):
        se = _make_strategy_evidence()
        _call_print(include_strategy=True, strategy_evidence=se)

        out = capsys.readouterr().out
        assert "indicator_registry" in out

    def test_rule_rationale_shown(self, capsys):
        se = _make_strategy_evidence()
        _call_print(include_strategy=True, strategy_evidence=se)

        out = capsys.readouterr().out
        assert "Volume expanded after dry-up" in out


# ── Coverage/conviction/freshness tests ───────────────────────────────────────


class TestStrategyEvidenceScores:
    def test_coverage_shown_when_present(self, capsys):
        se = _make_strategy_evidence(coverage_score=0.80)
        _call_print(include_strategy=True, strategy_evidence=se)

        out = capsys.readouterr().out
        assert "Coverage" in out
        assert "0.80" in out

    def test_conviction_shown_when_present(self, capsys):
        se = _make_strategy_evidence(conviction_score=0.72)
        _call_print(include_strategy=True, strategy_evidence=se)

        out = capsys.readouterr().out
        assert "Conviction" in out
        assert "0.72" in out

    def test_freshness_shown_when_present(self, capsys):
        se = _make_strategy_evidence(freshness_score=0.90)
        _call_print(include_strategy=True, strategy_evidence=se)

        out = capsys.readouterr().out
        assert "Freshness" in out
        assert "0.90" in out

    def test_scores_absent_when_all_none(self, capsys):
        se = _make_strategy_evidence(
            coverage_score=None,
            conviction_score=None,
            freshness_score=None,
        )
        _call_print(include_strategy=True, strategy_evidence=se)

        out = capsys.readouterr().out
        # Panel still renders but no score rows
        assert "STRATEGY DIAGNOSTIC EVIDENCE" in out
        assert "Coverage" not in out
        assert "Conviction" not in out
        assert "Freshness" not in out


# ── Unavailable / no matched rule ─────────────────────────────────────────────


class TestStrategyEvidenceUnavailable:
    def test_unavailable_reason_shown(self, capsys):
        se = _make_strategy_evidence(
            outcome=StrategyEvidenceOutcome.UNAVAILABLE,
            with_matched_rule=False,
            coverage_score=None,
            conviction_score=None,
            freshness_score=None,
            unavailable_reasons=("no indicator data",),
        )
        _call_print(include_strategy=True, strategy_evidence=se)

        out = capsys.readouterr().out
        assert "no indicator data" in out

    def test_matched_outcome_without_rule_renders_gracefully(self, capsys):
        # Edge case: outcome MATCHED but no matched_rule (degenerate evidence)
        se = _make_strategy_evidence(
            outcome=StrategyEvidenceOutcome.MATCHED,
            with_matched_rule=False,
        )
        _call_print(include_strategy=True, strategy_evidence=se)

        out = capsys.readouterr().out
        assert "STRATEGY DIAGNOSTIC EVIDENCE" in out
        assert "MATCHED" in out


# ── DIAGNOSTIC disclaimer ──────────────────────────────────────────────────────


class TestStrategyEvidenceDiagnosticFooter:
    def test_diagnostic_disclaimer_shown(self, capsys):
        se = _make_strategy_evidence()
        _call_print(include_strategy=True, strategy_evidence=se)

        out = capsys.readouterr().out
        assert "DIAGNOSTIC" in out

    def test_output_does_not_say_strategy_controls_enter(self, capsys):
        se = _make_strategy_evidence()
        _call_print(include_strategy=True, strategy_evidence=se)

        out = capsys.readouterr().out
        # The disclaimer must say strategy does NOT control ENTER/WATCH/AVOID
        assert "does not control ENTER/WATCH/AVOID" in out

    def test_strategy_name_in_disclaimer(self, capsys):
        # The panel header "Strategy Rule: <name>" must be present
        se = _make_strategy_evidence()
        _call_print(include_strategy=True, strategy_evidence=se)

        out = capsys.readouterr().out
        assert "Strategy Rule:" in out


# ── Coexistence with backtest result ──────────────────────────────────────────


class TestStrategyEvidenceCoexistenceWithBacktest:
    def _make_backtest(self) -> SimpleNamespace:
        from decimal import Decimal

        return SimpleNamespace(
            trade_count=12,
            win_rate=Decimal("58.3"),
            profit_factor=Decimal("1.45"),
            max_drawdown_pct=Decimal("7.2"),
            avg_win=Decimal("1_200_000"),
            avg_loss=Decimal("800_000"),
            start_date=date(2025, 7, 1),
            end_date=date(2026, 6, 30),
        )

    def test_both_backtest_and_strategy_evidence_show_in_same_panel(self, capsys):
        se = _make_strategy_evidence()
        bt = self._make_backtest()
        _call_print(include_strategy=True, strategy_evidence=se, backtest_result=bt)

        out = capsys.readouterr().out
        # One single STRATEGY DIAGNOSTIC EVIDENCE panel
        assert out.count("STRATEGY DIAGNOSTIC EVIDENCE") == 1
        # Backtest stats present
        assert "Win Rate" in out
        # Strategy VO present
        assert "MATCHED" in out

    def test_only_backtest_shows_when_strategy_evidence_none(self, capsys):
        bt = self._make_backtest()
        _call_print(include_strategy=True, strategy_evidence=None, backtest_result=bt)

        out = capsys.readouterr().out
        assert "STRATEGY DIAGNOSTIC EVIDENCE" in out
        # StrategyEvidence VO-specific fields/footer should not appear (title still
        # says DIAGNOSTIC under ADR-057).
        assert "Strategy Rule:" not in out
        assert "does not control ENTER/WATCH/AVOID" not in out
        assert "Historical Backtest" in out
