from datetime import date

from src.domain.value_objects.institutional_accumulation_evidence import (
    CounterpartyTransferEvidence,
    DomesticBandarTrack,
    EvidenceStatus,
    ForeignInstitutionalTrack,
    InstitutionalAccumulationEvidence,
)
from tests.adapters.cli.swing_display_alpha_sector_fixtures import _call_print


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
        bandar_accumulation_score_normalized=None,
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
        _call_print(
            include_flow_detail=True,
            institutional_accumulation_evidence=_ia_evidence_full(),
        )
        out = capsys.readouterr().out
        assert "INSTITUTIONAL ACCUMULATION" in out
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
