from src.domain.value_objects.alpha_trigger_score import AlphaTriggerScore
from tests.adapters.cli.swing_display_alpha_sector_fixtures import (
    _alpha_trigger_score,
    _call_print,
    _diagnostic_contribution,
    _minimal_signal_assessment,
    _phase_blocked_flow_contribution,
    _production_contribution,
)


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
