from datetime import date

import pytest

from src.domain.value_objects.institutional_accumulation_evidence import (
    CounterpartyTransferEvidence,
    DomesticBandarTrack,
    EvidenceStatus,
    ForeignInstitutionalTrack,
    InstitutionalAccumulationEvidence,
)


def _foreign_track() -> ForeignInstitutionalTrack:
    return ForeignInstitutionalTrack(
        foreign_participation_score=0.6,
        foreign_cr4_score=0.5,
        foreign_cr8_score=0.7,
        cnfb_divergence_score=0.4,
        foreign_vwap_distance_score=0.3,
        coverage_score=0.8,
        conviction_score=0.55,
        evidence_status=EvidenceStatus.DIAGNOSTIC,
        reasons=("foreign net buy positive",),
        unavailable_reasons=(),
    )


def _domestic_track() -> DomesticBandarTrack:
    return DomesticBandarTrack(
        broker_consistency_score=0.65,
        broker_reversal_score=0.2,
        accumulation_session_ratio=0.7,
        domestic_buy_vwap_distance_score=0.4,
        broker_hhi_divergence_score=0.5,
        bandar_broad_score_normalized=0.75,
        bandar_accumulation_score_normalized=0.6,
        coverage_score=0.9,
        conviction_score=0.5,
        evidence_status=EvidenceStatus.DIAGNOSTIC,
        reasons=("consistent accumulation",),
        unavailable_reasons=(),
    )


def _counterparty() -> CounterpartyTransferEvidence:
    return CounterpartyTransferEvidence(
        transfer_asymmetry_score=0.45,
        buy_side_hhi=1250.0,
        sell_side_hhi=800.0,
        coverage_score=0.7,
        conviction_score=0.4,
        evidence_status=EvidenceStatus.DIAGNOSTIC,
        unavailable_reasons=(),
    )


def _top_level() -> InstitutionalAccumulationEvidence:
    return InstitutionalAccumulationEvidence(
        ticker="BBCA",
        snapshot_date=date(2026, 7, 1),
        foreign_institutional_track=_foreign_track(),
        domestic_bandar_track=_domestic_track(),
        counterparty_transfer=_counterparty(),
        coverage_score=0.8,
        conviction_score=0.5,
        evidence_status=EvidenceStatus.DIAGNOSTIC,
        reasons=("two-track alignment",),
        unavailable_reasons=(),
        metadata={"diagnostic_only": True},
    )


def test_foreign_track_round_trip():
    track = _foreign_track()
    assert ForeignInstitutionalTrack.from_dict(track.to_dict()) == track


def test_domestic_track_round_trip():
    track = _domestic_track()
    assert DomesticBandarTrack.from_dict(track.to_dict()) == track


def test_counterparty_round_trip():
    evidence = _counterparty()
    assert CounterpartyTransferEvidence.from_dict(evidence.to_dict()) == evidence


def test_top_level_round_trip():
    evidence = _top_level()
    restored = InstitutionalAccumulationEvidence.from_dict(evidence.to_dict())
    assert restored == evidence


def test_top_level_serializes_snapshot_date_as_iso_string():
    evidence = _top_level()
    assert evidence.to_dict()["snapshot_date"] == "2026-07-01"


def test_from_dict_accepts_date_object():
    payload = _top_level().to_dict()
    payload["snapshot_date"] = date(2026, 7, 1)
    restored = InstitutionalAccumulationEvidence.from_dict(payload)
    assert restored.snapshot_date == date(2026, 7, 1)


@pytest.mark.parametrize("bad_value", [-0.1, 1.1])
def test_foreign_track_rejects_out_of_bounds_score(bad_value):
    with pytest.raises(ValueError):
        ForeignInstitutionalTrack(
            foreign_participation_score=bad_value,
            foreign_cr4_score=None,
            foreign_cr8_score=None,
            cnfb_divergence_score=None,
            foreign_vwap_distance_score=None,
            coverage_score=0.5,
            conviction_score=0.5,
            evidence_status=EvidenceStatus.DIAGNOSTIC,
            reasons=(),
            unavailable_reasons=(),
        )


def test_domestic_track_rejects_out_of_bounds_coverage():
    with pytest.raises(ValueError):
        DomesticBandarTrack(
            broker_consistency_score=None,
            broker_reversal_score=None,
            accumulation_session_ratio=None,
            domestic_buy_vwap_distance_score=None,
            broker_hhi_divergence_score=None,
            bandar_broad_score_normalized=None,
            bandar_accumulation_score_normalized=None,
            coverage_score=1.5,
            conviction_score=0.5,
            evidence_status=EvidenceStatus.DIAGNOSTIC,
            reasons=(),
            unavailable_reasons=(),
        )


def test_counterparty_rejects_out_of_bounds_asymmetry():
    with pytest.raises(ValueError):
        CounterpartyTransferEvidence(
            transfer_asymmetry_score=1.2,
            buy_side_hhi=1000.0,
            sell_side_hhi=900.0,
            coverage_score=0.5,
            conviction_score=0.5,
            evidence_status=EvidenceStatus.DIAGNOSTIC,
            unavailable_reasons=(),
        )


def test_counterparty_allows_raw_hhi_above_one():
    # buy_side_hhi/sell_side_hhi are raw HHI values, not bounded to [0,1].
    evidence = CounterpartyTransferEvidence(
        transfer_asymmetry_score=0.5,
        buy_side_hhi=5000.0,
        sell_side_hhi=3000.0,
        coverage_score=0.5,
        conviction_score=0.5,
        evidence_status=EvidenceStatus.DIAGNOSTIC,
        unavailable_reasons=(),
    )
    assert evidence.buy_side_hhi == 5000.0


def test_top_level_rejects_empty_ticker():
    with pytest.raises(ValueError):
        InstitutionalAccumulationEvidence(
            ticker="",
            snapshot_date=date(2026, 7, 1),
            foreign_institutional_track=_foreign_track(),
            domestic_bandar_track=_domestic_track(),
            counterparty_transfer=None,
            coverage_score=0.5,
            conviction_score=0.5,
            evidence_status=EvidenceStatus.DIAGNOSTIC,
            reasons=(),
            unavailable_reasons=(),
            metadata={},
        )


def test_foreign_track_from_minimal_dict_returns_none_optionals():
    track = ForeignInstitutionalTrack.from_dict({})
    assert track.foreign_participation_score is None
    assert track.foreign_cr4_score is None
    assert track.foreign_cr8_score is None
    assert track.cnfb_divergence_score is None
    assert track.foreign_vwap_distance_score is None
    assert track.coverage_score == 0.0
    assert track.conviction_score == 0.0
    assert track.evidence_status is EvidenceStatus.DIAGNOSTIC


def test_domestic_track_from_minimal_dict_returns_none_optionals():
    track = DomesticBandarTrack.from_dict({})
    assert track.broker_consistency_score is None
    assert track.bandar_broad_score_normalized is None
    assert track.bandar_accumulation_score_normalized is None
    assert track.coverage_score == 0.0


def test_counterparty_from_minimal_dict_returns_none_optionals():
    evidence = CounterpartyTransferEvidence.from_dict({})
    assert evidence.transfer_asymmetry_score is None
    assert evidence.buy_side_hhi is None
    assert evidence.sell_side_hhi is None


def test_top_level_from_minimal_dict_parses_without_error():
    evidence = InstitutionalAccumulationEvidence.from_dict(
        {"ticker": "bbca", "snapshot_date": "2026-07-01"}
    )
    assert evidence.ticker == "BBCA"
    assert evidence.counterparty_transfer is None
    assert evidence.foreign_institutional_track.coverage_score == 0.0
    assert evidence.domestic_bandar_track.coverage_score == 0.0
    assert evidence.metadata == {}


def test_evidence_status_enum_values():
    assert EvidenceStatus.DIAGNOSTIC.value == "DIAGNOSTIC"
    assert EvidenceStatus.LOW_WEIGHT.value == "LOW_WEIGHT"
    assert EvidenceStatus.PRODUCTION.value == "PRODUCTION"
