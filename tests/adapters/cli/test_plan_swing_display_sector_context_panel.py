from tests.adapters.cli.plan_swing_display_alpha_sector_fixtures import (
    _call_print,
    _sector_context_evidence_full,
    _sector_context_unavailable,
)


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
        assert "Sector 20d" not in out
        assert "vs IHSG" not in out
