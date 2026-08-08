"""DQ-001: missing-vs-zero semantics through authority and Alpha/Trigger."""

from datetime import date
from types import SimpleNamespace

import pytest

from src.application.services.alpha_trigger_aggregator import (
    AlphaTriggerAggregationRequest,
    AlphaTriggerAggregator,
    AlphaTriggerGroupInput,
)
from src.application.services.flow_confirmation_evidence_builder import (
    FlowConfirmationEvidenceBuilder,
)
from src.application.services.signal_alpha_trigger_projection import (
    SignalAlphaTriggerProjection,
)
from src.application.services.signal_engine_config import (
    AlphaTriggerConfig,
    SignalEngineConfig,
)
from src.application.services.signal_evidence_group_scorer import SignalEvidenceGroupScorer
from src.application.use_case.score_accum_use_case import (
    ScoreAccumRequest,
    ScoreAccumUseCase,
)
from src.domain.value_objects.accum_score_breakdown import (
    ForeignFlowComponentScore,
    ForeignFlowComponentStatus,
)
from src.domain.value_objects.foreign_flow_evidence import ForeignFlowEvidence
from src.domain.value_objects.signal_artifact_schema import (
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
    SIGNAL_FORWARD_LABEL_SCHEMA_VERSION,
)
from src.domain.value_objects.signal_observation_fingerprint import (
    SignalObservationFingerprint,
)

SNAP = date(2026, 7, 3)


def _typed_flow_from_score(**overrides):
    base = dict(
        ticker="BBCA",
        snapshot_date=SNAP,
        net_buy_ratio=1.0,
        consecutive_streak=7,
        vwap_discount_pct=10.0,
        rsi=40.0,
        avg_flow_ratio=20.0,
        bb_width_pctile=0.0,
        bci_label="CLUSTER",
        bci_tier1_count=3,
    )
    base.update(overrides)
    breakdown = ScoreAccumUseCase().execute(ScoreAccumRequest(**base)).evidence
    return ForeignFlowEvidence.from_score_breakdown(breakdown, net_buy_days=5, total_days=7)


def _build_flow_ev(foreign_flow_evidence):
    return (
        FlowConfirmationEvidenceBuilder()
        .build(
            SimpleNamespace(
                ticker="BBCA",
                foreign_flow_evidence=foreign_flow_evidence,
                bandar_detector=None,
                bci_label="CLUSTER" if foreign_flow_evidence else None,
                bci_tier1_count=3 if foreign_flow_evidence else 0,
                latest_candle_date=SNAP,
            ),
            consumed_broker_summaries=(),
            consumed_broker_daily_flows=(),
        )
        .evidence
    )


def test_source_unavailable_flow_has_zero_authority():
    flow_ev = _build_flow_ev(_typed_flow_from_score())
    cfg = SignalEngineConfig()

    class _Avail:
        all_authoritative = False
        settled_authority_fraction = 0.0
        unassessed_contributors = ()

    class _Group:
        availability = _Avail()

    class _Canon:
        setup = None
        flow = _Group()

    req = SimpleNamespace(
        setup_evidence=None,
        flow_confirmation_evidence=flow_ev,
        signal_context=None,
        market_context=None,
        canonical_evidence=_Canon(),
    )
    facts = SignalEvidenceGroupScorer._group_authority_facts(req, flow_present=True, config=cfg)
    flow_fact = [f for f in facts if f.name == "flow_confirmation"][0]
    assert flow_fact.authority_fraction == 0.0
    coverage = SignalEvidenceGroupScorer._compute_signal_authority_coverage(facts)
    assert coverage == 0.0


def test_partial_flow_coverage_proportionally_lowers_authority():
    ffe = _typed_flow_from_score(vwap_discount_pct=None)
    flow_ev = _build_flow_ev(ffe)
    assert flow_ev.component_coverage < 1.0
    assert "vwap" in flow_ev.missing_components

    class _Avail:
        all_authoritative = True
        settled_authority_fraction = 1.0
        unassessed_contributors = ()

    class _Group:
        availability = _Avail()

    class _Canon:
        setup = _Group()
        flow = _Group()

    cfg = SignalEngineConfig()
    req = SimpleNamespace(
        setup_evidence=SimpleNamespace(match_strength=80.0),
        flow_confirmation_evidence=flow_ev,
        signal_context=None,
        market_context=None,
        canonical_evidence=_Canon(),
    )
    facts = SignalEvidenceGroupScorer._group_authority_facts(req, flow_present=True, config=cfg)
    flow_fact = [f for f in facts if f.name == "flow_confirmation"][0]
    assert flow_fact.authority_fraction == pytest.approx(flow_ev.component_coverage)
    assert 0.0 < flow_fact.authority_fraction < 1.0

    # ADR-067: flow_confirmation is the sole production evidence group, so its
    # weight cancels and coverage IS its authority fraction. Asserted against
    # the component coverage directly rather than a weight ratio, so the test
    # cannot silently pass on a reintroduced blend.
    coverage = SignalEvidenceGroupScorer._compute_signal_authority_coverage(facts)
    assert coverage == pytest.approx(flow_ev.component_coverage)


def test_alpha_trigger_partial_coverage_lowers_authority_not_directional_score():
    score_full = AlphaTriggerAggregator(AlphaTriggerConfig()).aggregate(
        AlphaTriggerAggregationRequest(
            horizon="SWING_10D",
            groups=(
                AlphaTriggerGroupInput(
                    "setup_quality",
                    80.0,
                    0.35,
                    True,
                    coverage_fraction=1.0,
                    authority_fraction=1.0,
                ),
                AlphaTriggerGroupInput(
                    "institutional_flow",
                    60.0,
                    0.30,
                    True,
                    coverage_fraction=1.0,
                    authority_fraction=1.0,
                ),
            ),
        )
    )
    score_partial = AlphaTriggerAggregator(AlphaTriggerConfig()).aggregate(
        AlphaTriggerAggregationRequest(
            horizon="SWING_10D",
            groups=(
                AlphaTriggerGroupInput(
                    "setup_quality",
                    80.0,
                    0.35,
                    True,
                    coverage_fraction=1.0,
                    authority_fraction=1.0,
                ),
                AlphaTriggerGroupInput(
                    "institutional_flow",
                    60.0,
                    0.30,
                    True,
                    coverage_fraction=0.5,
                    authority_fraction=0.5,
                ),
            ),
        )
    )
    assert score_partial.alpha_score == pytest.approx(score_full.alpha_score)
    assert score_partial.trigger_score == pytest.approx(score_full.trigger_score)
    assert score_partial.coverage < score_full.coverage
    assert score_partial.authority_coverage < score_full.authority_coverage
    expected = round((0.35 * 1.0 + 0.30 * 0.5) / 0.65, 4)
    assert score_partial.coverage == pytest.approx(expected)
    assert score_partial.authority_coverage == pytest.approx(expected)


def test_fingerprint_round_trip_preserves_coverage_and_missing():
    fp = SignalObservationFingerprint(
        flow_component_coverage=0.8123,
        flow_missing_components=("vwap", "flow"),
        signal_authority_coverage=0.75,
    )
    round_tripped = SignalObservationFingerprint.from_dict(fp.to_dict())
    assert round_tripped.flow_component_coverage == pytest.approx(0.8123)
    assert round_tripped.flow_missing_components == ("vwap", "flow")


def test_schema_versions_bumped_for_dq001():
    # ADR-068 dropped the write-only config_hash payload field, so the current
    # accumulation payload schema is 13. The engine/evidence version pins that
    # used to live here are gone with the constants themselves: engine change
    # detection is the behavioural probe digest, not a hand-typed string.
    assert CANDIDATE_OBSERVATION_SCHEMA_VERSION == 15
    assert SIGNAL_FORWARD_LABEL_SCHEMA_VERSION == 3


def test_schema_4_observations_are_noncanonical():
    assert CANDIDATE_OBSERVATION_SCHEMA_VERSION != 4
    assert SIGNAL_FORWARD_LABEL_SCHEMA_VERSION != 2


def test_all_input_present_score_vector_unchanged():
    evidence = (
        ScoreAccumUseCase()
        .execute(
            ScoreAccumRequest(
                ticker="BBCA",
                snapshot_date=SNAP,
                net_buy_ratio=1.0,
                consecutive_streak=7,
                vwap_discount_pct=10.0,
                rsi=40.0,
                avg_flow_ratio=20.0,
                bb_width_pctile=0.0,
                bci_label="CLUSTER",
                bci_tier1_count=3,
            )
        )
        .evidence
    )
    assert evidence.accum_score == 94.9
    assert evidence.component("bb").status is ForeignFlowComponentStatus.DISABLED


def test_invalid_bci_label_is_rejected_instead_of_becoming_available_zero():
    with pytest.raises(ValueError, match="bci_label must be"):
        ScoreAccumUseCase().execute(
            ScoreAccumRequest(
                ticker="BBCA",
                snapshot_date=SNAP,
                net_buy_ratio=1.0,
                consecutive_streak=7,
                vwap_discount_pct=0.0,
                rsi=40.0,
                avg_flow_ratio=0.0,
                bb_width_pctile=None,
                bci_label="TYPO",
            )
        )


def test_legacy_numeric_flow_evidence_is_rejected():
    candidate = SimpleNamespace(
        ticker="BBCA",
        foreign_flow_evidence=SimpleNamespace(
            component_breakdown=(("cons", 33.3),),
            confirmation_status="CONFIRMED",
            flow_direction="POSITIVE",
        ),
        bandar_detector=None,
        bci_label=None,
        bci_tier1_count=0,
        latest_candle_date=SNAP,
    )
    with pytest.raises(TypeError, match="legacy numeric component breakdowns"):
        FlowConfirmationEvidenceBuilder().build(
            candidate,
            consumed_broker_summaries=(),
            consumed_broker_daily_flows=(),
        )


def test_component_max_points_must_match_active_policy():
    evidence = _typed_flow_from_score()
    components = list(evidence.components)
    cons = evidence.component("cons")
    components[components.index(cons)] = ForeignFlowComponentScore(
        key="cons",
        score_points=1.0,
        max_points=1.0,
        status=ForeignFlowComponentStatus.AVAILABLE,
    )
    malformed = ForeignFlowEvidence(
        max_score=evidence.max_score,
        score_family=evidence.score_family,
        flow_direction=evidence.flow_direction,
        confirmation_status=evidence.confirmation_status,
        net_buy_days=evidence.net_buy_days,
        total_days=evidence.total_days,
        streak=evidence.streak,
        avg_flow_ratio=evidence.avg_flow_ratio,
        f_vwap_pct=evidence.f_vwap_pct,
        components=tuple(components),
    )
    candidate = SimpleNamespace(
        ticker="BBCA",
        foreign_flow_evidence=malformed,
        bandar_detector=None,
        bci_label="CLUSTER",
        bci_tier1_count=3,
        latest_candle_date=SNAP,
    )
    with pytest.raises(ValueError, match="does not match active policy"):
        FlowConfirmationEvidenceBuilder().build(
            candidate,
            consumed_broker_summaries=(),
            consumed_broker_daily_flows=(),
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"flow_component_coverage": 2.0, "flow_missing_components": []},
        {"flow_component_coverage": 1.0, "flow_missing_components": ["vwap"]},
        {"flow_component_coverage": 0.5, "flow_missing_components": ["vwap", "vwap"]},
        {"flow_component_coverage": 0.5, "flow_missing_components": ["bogus"]},
        {"flow_component_coverage": 0.5, "flow_missing_components": "vwap"},
    ],
)
def test_malformed_flow_fingerprint_is_rejected(payload):
    with pytest.raises(ValueError):
        SignalObservationFingerprint.from_dict(payload)


def test_projection_transports_partial_flow_authority_without_changing_score():
    full_flow = _build_flow_ev(_typed_flow_from_score())
    partial_flow = _build_flow_ev(_typed_flow_from_score(vwap_discount_pct=None))

    class _Avail:
        all_authoritative = True
        settled_authority_fraction = 1.0
        unassessed_contributors = ()

    class _Group:
        availability = _Avail()

    class _Canon:
        setup = _Group()
        flow = _Group()

    def _project(flow_ev):
        request = SimpleNamespace(
            horizon="SWING_10D",
            canonical_evidence=_Canon(),
            flow_confirmation_evidence=flow_ev,
            setup_phase=None,
            sector_context_evidence=None,
            company_quality_context_evidence=None,
        )
        scores = SimpleNamespace(
            setup_group_score=80.0,
            setup_present=True,
            flow_group_score=flow_ev.capped_strength * 100.0,
            flow_present=True,
        )
        return SignalAlphaTriggerProjection.build_score(
            request,
            SignalEngineConfig(),
            scores,
        )

    full = _project(full_flow)
    partial = _project(partial_flow)
    assert partial.final_exact_score == pytest.approx(full.final_exact_score)
    assert partial.authority_coverage < full.authority_coverage
