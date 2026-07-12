from tests.adapters.cli.swing_display_alpha_sector_fixtures import (
    _alpha_trigger_score,
    _call_print,
    _minimal_signal_assessment,
    _sector_context_evidence_full,
)


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
