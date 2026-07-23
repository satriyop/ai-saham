from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.application.services.flow_confirmation_evidence_builder import (
    FlowConfirmationEvidenceBuilder,
)
from src.application.use_case.score_accum_use_case import (
    BciEvidencePolicy,
    EvidenceComponentPolicy,
    AccumScorePolicy,
    LinearSaturationPolicy,
    StreakEvidencePolicy,
)
from src.domain.entities.broker_flow import BrokerDailyFlow, BrokerSummary
from src.domain.value_objects.factor_evidence import Direction, Freshness
from src.domain.value_objects.foreign_flow_evidence import ForeignFlowEvidence
from src.domain.value_objects.accum_score_breakdown import (
    ForeignFlowComponentScore,
    ForeignFlowComponentStatus,
)


def _broker_summary(ticker: str, day: date, *, source: str = "idx") -> BrokerSummary:
    return BrokerSummary(
        ticker=ticker,
        date=day,
        top_buyers=(),
        top_sellers=(),
        foreign_buy_value=Decimal("1000000"),
        foreign_sell_value=Decimal("0"),
        foreign_buy_lot=100,
        foreign_sell_lot=0,
        total_value=Decimal("2000000"),
        total_lot=200,
        source=source,
    )


def _broker_daily_flow(
    ticker: str, day: date, broker_code: str, *, source: str = "stockbit"
) -> BrokerDailyFlow:
    return BrokerDailyFlow(
        ticker=ticker,
        broker_code=broker_code,
        broker_name=broker_code,
        date=day,
        buy_lot=100,
        sell_lot=0,
        net_lot=100,
        buy_value=Decimal("1000000"),
        sell_value=Decimal("0"),
        net_value=Decimal("1000000"),
        avg_buy_price=Decimal("1000"),
        avg_sell_price=Decimal("1000"),
        avg_price=Decimal("1000"),
        buy_pct=100.0,
        sell_pct=0.0,
        source=source,
    )


def _comp(
    key: str,
    points: float | None,
    max_points: float,
    status: ForeignFlowComponentStatus = ForeignFlowComponentStatus.AVAILABLE,
) -> ForeignFlowComponentScore:
    return ForeignFlowComponentScore(
        key=key,
        score_points=points,
        max_points=max_points,
        status=status,
    )


def _flow_evidence(
    components: tuple[ForeignFlowComponentScore, ...],
    confirmation_status="CONFIRMED",
    flow_direction="POSITIVE",
):
    by_key = {component.key: component for component in components}
    defaults = {
        "cons": _comp("cons", None, 33.3, ForeignFlowComponentStatus.MISSING),
        "streak": _comp("streak", None, 25.0, ForeignFlowComponentStatus.MISSING),
        "vwap": _comp("vwap", None, 16.7, ForeignFlowComponentStatus.MISSING),
        "rsi": _comp("rsi", 0.0, 8.3),
        "flow": _comp("flow", None, 8.3, ForeignFlowComponentStatus.MISSING),
        "bb": _comp("bb", None, 8.3, ForeignFlowComponentStatus.DISABLED),
        "inst": _comp("inst", None, 12.5, ForeignFlowComponentStatus.MISSING),
    }
    defaults.update(by_key)
    return ForeignFlowEvidence(
        max_score=100.0,
        score_family="composite_foreign_flow",
        confirmation_status=confirmation_status,
        flow_direction=flow_direction,
        net_buy_days=5,
        total_days=7,
        streak=4,
        components=tuple(defaults[key] for key in (
            "cons", "streak", "vwap", "rsi", "flow", "bb", "inst"
        )),
    )


def _candidate(
    *,
    flow_evidence=None,
    bandar_detector=None,
    bci_label=None,
    bci_tier1_count=0,
    ticker="BBCA",
    latest_candle_date=date(2026, 6, 25),
):
    return SimpleNamespace(
        ticker=ticker,
        foreign_flow_evidence=flow_evidence,
        bandar_detector=bandar_detector,
        bci_label=bci_label,
        bci_tier1_count=bci_tier1_count,
        latest_candle_date=latest_candle_date,
    )


# All-input-present institutional-flow components (RSI/BB excluded from group).
_FULL_COMPONENTS = (
    _comp("cons", 33.3, 33.3),
    _comp("streak", 15.8, 25.0),
    _comp("vwap", 16.7, 16.7),
    _comp("flow", 8.3, 8.3),
    _comp("inst", 12.5, 12.5),
    _comp("rsi", 8.3, 8.3),  # excluded from flow group
    _comp("bb", None, 8.3, ForeignFlowComponentStatus.DISABLED),
)


def test_all_sub_signals_present():
    builder = FlowConfirmationEvidenceBuilder()
    candidate = _candidate(flow_evidence=_flow_evidence(_FULL_COMPONENTS))

    evidence = builder.build(
        candidate, consumed_broker_summaries=(), consumed_broker_daily_flows=()
    ).evidence

    keys = [s.key for s in evidence.flow_signals]
    assert keys == ["cons", "streak", "vwap", "flow", "inst"]


def test_bb_excluded_from_flow_signals():
    builder = FlowConfirmationEvidenceBuilder()
    candidate = _candidate(flow_evidence=_flow_evidence(_FULL_COMPONENTS))

    evidence = builder.build(
        candidate, consumed_broker_summaries=(), consumed_broker_daily_flows=()
    ).evidence

    assert "bb" not in {s.key for s in evidence.flow_signals}


def test_rsi_excluded_from_flow_signals():
    builder = FlowConfirmationEvidenceBuilder()
    candidate = _candidate(flow_evidence=_flow_evidence(_FULL_COMPONENTS))

    evidence = builder.build(
        candidate, consumed_broker_summaries=(), consumed_broker_daily_flows=()
    ).evidence

    assert "rsi" not in {s.key for s in evidence.flow_signals}


def test_flow_signals_are_fresh_when_all_components_available():
    builder = FlowConfirmationEvidenceBuilder()
    candidate = _candidate(flow_evidence=_flow_evidence(_FULL_COMPONENTS))

    evidence = builder.build(
        candidate, consumed_broker_summaries=(), consumed_broker_daily_flows=()
    ).evidence

    assert all(s.freshness == Freshness.FRESH for s in evidence.flow_signals)
    assert evidence.group_freshness == Freshness.FRESH
    assert evidence.component_coverage == 1.0
    assert evidence.missing_components == ()


def test_missing_components_are_never_fresh():
    components = (
        _comp("cons", 33.3, 33.3),
        _comp("streak", 15.8, 25.0),
        _comp("vwap", None, 16.7, ForeignFlowComponentStatus.MISSING),
        _comp("flow", 8.3, 8.3),
        _comp("inst", 12.5, 12.5),
    )
    builder = FlowConfirmationEvidenceBuilder()
    candidate = _candidate(flow_evidence=_flow_evidence(components))

    evidence = builder.build(
        candidate, consumed_broker_summaries=(), consumed_broker_daily_flows=()
    ).evidence

    by_key = {s.key: s for s in evidence.flow_signals}
    assert by_key["vwap"].freshness is Freshness.MISSING
    assert by_key["cons"].freshness is Freshness.FRESH
    assert "vwap" in evidence.missing_components
    assert evidence.component_coverage < 1.0


def test_available_zero_is_fresh_and_neutral():
    components = (
        _comp("cons", 33.3, 33.3),
        _comp("streak", 0.0, 25.0),
        _comp("vwap", 0.0, 16.7),
        _comp("flow", 0.0, 8.3),
        _comp("inst", 0.0, 12.5),
    )
    builder = FlowConfirmationEvidenceBuilder()
    candidate = _candidate(flow_evidence=_flow_evidence(components))

    evidence = builder.build(
        candidate, consumed_broker_summaries=(), consumed_broker_daily_flows=()
    ).evidence

    by_key = {s.key: s for s in evidence.flow_signals}
    assert by_key["vwap"].freshness is Freshness.FRESH
    assert by_key["vwap"].score == 0.0
    assert by_key["vwap"].direction is Direction.NEUTRAL
    assert evidence.component_coverage == 1.0
    # Real zero lowers directional strength but not coverage.
    assert evidence.uncapped_strength < 1.0


def test_missing_component_excluded_from_directional_denominator():
    # Only cons available at full points; vwap missing.
    components = (
        _comp("cons", 33.3, 33.3),
        _comp("streak", None, 25.0, ForeignFlowComponentStatus.MISSING),
        _comp("vwap", None, 16.7, ForeignFlowComponentStatus.MISSING),
        _comp("flow", None, 8.3, ForeignFlowComponentStatus.MISSING),
        _comp("inst", None, 12.5, ForeignFlowComponentStatus.MISSING),
    )
    builder = FlowConfirmationEvidenceBuilder()
    candidate = _candidate(flow_evidence=_flow_evidence(components))

    evidence = builder.build(
        candidate, consumed_broker_summaries=(), consumed_broker_daily_flows=()
    ).evidence

    # Directional strength = 33.3 / 33.3 = 1.0 (missing excluded from denom)
    assert evidence.uncapped_strength == 1.0
    # Coverage uses enabled weights: available 33.3 / 95.8
    assert evidence.component_coverage == pytest.approx(33.3 / 95.8)
    assert set(evidence.missing_components) == {"streak", "vwap", "flow", "inst"}


def test_real_zero_available_lowers_strength_not_coverage():
    full = _FULL_COMPONENTS
    zero_vwap = (
        _comp("cons", 33.3, 33.3),
        _comp("streak", 15.8, 25.0),
        _comp("vwap", 0.0, 16.7),
        _comp("flow", 8.3, 8.3),
        _comp("inst", 12.5, 12.5),
    )
    builder = FlowConfirmationEvidenceBuilder()
    full_ev = builder.build(
        _candidate(flow_evidence=_flow_evidence(full)),
        consumed_broker_summaries=(),
        consumed_broker_daily_flows=(),
    ).evidence
    zero_ev = builder.build(
        _candidate(flow_evidence=_flow_evidence(zero_vwap)),
        consumed_broker_summaries=(),
        consumed_broker_daily_flows=(),
    ).evidence

    assert zero_ev.component_coverage == full_ev.component_coverage == 1.0
    assert zero_ev.uncapped_strength < full_ev.uncapped_strength


def test_flow_signals_are_missing_when_no_evidence():
    builder = FlowConfirmationEvidenceBuilder()
    candidate = _candidate(flow_evidence=None)

    evidence = builder.build(
        candidate, consumed_broker_summaries=(), consumed_broker_daily_flows=()
    ).evidence

    assert all(s.freshness == Freshness.MISSING for s in evidence.flow_signals)
    assert evidence.group_freshness == Freshness.MISSING
    assert evidence.confirmation_status == "WEAK"
    assert evidence.component_coverage == 0.0


def test_bandar_fresh_when_snapshot_present():
    builder = FlowConfirmationEvidenceBuilder()
    candidate = _candidate(
        flow_evidence=_flow_evidence(_FULL_COMPONENTS),
        bandar_detector=SimpleNamespace(broad_score=8),
    )

    evidence = builder.build(
        candidate, consumed_broker_summaries=(), consumed_broker_daily_flows=()
    ).evidence

    assert evidence.bandar_freshness == Freshness.FRESH
    assert evidence.bandar_broad_score == 8


def test_bandar_missing_when_no_snapshot():
    builder = FlowConfirmationEvidenceBuilder()
    candidate = _candidate(
        flow_evidence=_flow_evidence(_FULL_COMPONENTS),
        bandar_detector=None,
    )

    evidence = builder.build(
        candidate, consumed_broker_summaries=(), consumed_broker_daily_flows=()
    ).evidence

    assert evidence.bandar_freshness == Freshness.MISSING
    assert evidence.bandar_broad_score is None
    assert evidence.bandar_direction == Direction.NEUTRAL


def test_bandar_direction_mapping():
    builder = FlowConfirmationEvidenceBuilder()
    flow = _flow_evidence(_FULL_COMPONENTS)

    bullish = builder.build(
        _candidate(flow_evidence=flow, bandar_detector=SimpleNamespace(broad_score=5)),
        consumed_broker_summaries=(),
        consumed_broker_daily_flows=(),
    ).evidence
    bearish = builder.build(
        _candidate(flow_evidence=flow, bandar_detector=SimpleNamespace(broad_score=-5)),
        consumed_broker_summaries=(),
        consumed_broker_daily_flows=(),
    ).evidence
    neutral = builder.build(
        _candidate(flow_evidence=flow, bandar_detector=SimpleNamespace(broad_score=0)),
        consumed_broker_summaries=(),
        consumed_broker_daily_flows=(),
    ).evidence

    assert bullish.bandar_direction == Direction.BULLISH
    assert bearish.bandar_direction == Direction.BEARISH
    assert neutral.bandar_direction == Direction.NEUTRAL


def test_group_cap_applied():
    builder = FlowConfirmationEvidenceBuilder()
    max_components = (
        _comp("cons", 33.3, 33.3),
        _comp("streak", 25.0, 25.0),
        _comp("vwap", 16.7, 16.7),
        _comp("flow", 8.3, 8.3),
        _comp("inst", 12.5, 12.5),
    )
    candidate = _candidate(
        flow_evidence=_flow_evidence(max_components),
        bandar_detector=SimpleNamespace(broad_score=12),
    )

    evidence = builder.build(
        candidate, consumed_broker_summaries=(), consumed_broker_daily_flows=()
    ).evidence

    assert evidence.capped_strength <= evidence.group_cap
    assert evidence.capped_strength <= evidence.uncapped_strength


def test_flow_score_ex_bb_sum():
    builder = FlowConfirmationEvidenceBuilder()
    candidate = _candidate(flow_evidence=_flow_evidence(_FULL_COMPONENTS))

    evidence = builder.build(
        candidate, consumed_broker_summaries=(), consumed_broker_daily_flows=()
    ).evidence

    expected = round(sum(s.score for s in evidence.flow_signals), 1)
    assert evidence.flow_score_ex_bb == expected
    assert evidence.flow_score_ex_bb == 86.6


def test_to_dict_structure():
    builder = FlowConfirmationEvidenceBuilder()
    candidate = _candidate(
        flow_evidence=_flow_evidence(_FULL_COMPONENTS),
        bandar_detector=SimpleNamespace(broad_score=6),
        bci_label="CLUSTER",
        bci_tier1_count=3,
    )

    d = builder.build(
        candidate, consumed_broker_summaries=(), consumed_broker_daily_flows=()
    ).evidence.to_dict()

    expected_keys = {
        "ticker",
        "snapshot_date",
        "flow_signals",
        "flow_score_ex_bb",
        "confirmation_status",
        "flow_direction",
        "bandar_broad_score",
        "bandar_direction",
        "bandar_freshness",
        "bci_label",
        "bci_tier1_count",
        "uncapped_strength",
        "capped_strength",
        "group_cap",
        "group_freshness",
        "component_coverage",
        "missing_components",
    }
    assert expected_keys <= set(d.keys())
    assert d["bandar_direction"] == "BULLISH"
    assert d["group_freshness"] == "FRESH"
    assert d["flow_direction"] == "POSITIVE"
    assert d["component_coverage"] == 1.0
    assert isinstance(d["flow_signals"], list)
    assert d["flow_signals"][0]["freshness"] == "FRESH"


def test_flow_direction_extracted_from_evidence():
    builder = FlowConfirmationEvidenceBuilder()

    pos = builder.build(
        _candidate(
            flow_evidence=_flow_evidence(_FULL_COMPONENTS, flow_direction="POSITIVE")
        ),
        consumed_broker_summaries=(),
        consumed_broker_daily_flows=(),
    ).evidence
    neg = builder.build(
        _candidate(
            flow_evidence=_flow_evidence(_FULL_COMPONENTS, flow_direction="NEGATIVE")
        ),
        consumed_broker_summaries=(),
        consumed_broker_daily_flows=(),
    ).evidence
    flat = builder.build(
        _candidate(
            flow_evidence=_flow_evidence(_FULL_COMPONENTS, flow_direction="FLAT")
        ),
        consumed_broker_summaries=(),
        consumed_broker_daily_flows=(),
    ).evidence
    missing = builder.build(
        _candidate(flow_evidence=None),
        consumed_broker_summaries=(),
        consumed_broker_daily_flows=(),
    ).evidence

    assert pos.flow_direction == "POSITIVE"
    assert neg.flow_direction == "NEGATIVE"
    assert flat.flow_direction == "FLAT"
    assert missing.flow_direction == "UNKNOWN"


def test_default_policy_weights_match_score_accum_use_case_defaults():
    builder = FlowConfirmationEvidenceBuilder()
    candidate = _candidate(flow_evidence=_flow_evidence(_FULL_COMPONENTS))

    evidence = builder.build(
        candidate, consumed_broker_summaries=(), consumed_broker_daily_flows=()
    ).evidence

    weights = {s.key: s.weight for s in evidence.flow_signals}
    assert weights == {
        "cons": 33.3,
        "streak": 25.0,
        "vwap": 16.7,
        "flow": 8.3,
        "inst": 12.5,
    }


def test_default_policy_proportional_strength_matches_known_example():
    """All-input-present known vector: strength uses available denom = full."""
    builder = FlowConfirmationEvidenceBuilder()
    candidate = _candidate(flow_evidence=_flow_evidence(_FULL_COMPONENTS))

    evidence = builder.build(
        candidate, consumed_broker_summaries=(), consumed_broker_daily_flows=()
    ).evidence

    assert evidence.flow_score_ex_bb == 86.6
    assert evidence.uncapped_strength == round(86.6 / 95.8, 4)
    assert abs(evidence.uncapped_strength - 0.904) < 0.001


def _custom_policy() -> AccumScorePolicy:
    return AccumScorePolicy(
        consistency=EvidenceComponentPolicy(enabled=True, weight=50.0),
        streak=StreakEvidencePolicy(enabled=True, weight=20.0),
        vwap_discount=LinearSaturationPolicy(enabled=True, weight=10.0),
        foreign_flow_ratio=LinearSaturationPolicy(enabled=True, weight=5.0),
        bci=BciEvidencePolicy(enabled=True, cluster_points=15.0, stable_points=5.0),
    )


def test_custom_policy_sub_signal_weights_reflect_policy():
    builder = FlowConfirmationEvidenceBuilder(accum_score_policy=_custom_policy())
    # Components carry their own max_points from scoring; builder uses those.
    custom_components = (
        _comp("cons", 33.3, 50.0),
        _comp("streak", 15.8, 20.0),
        _comp("vwap", 10.0, 10.0),
        _comp("flow", 5.0, 5.0),
        _comp("inst", 12.5, 15.0),
    )
    candidate = _candidate(flow_evidence=_flow_evidence(custom_components))

    evidence = builder.build(
        candidate, consumed_broker_summaries=(), consumed_broker_daily_flows=()
    ).evidence

    weights = {s.key: s.weight for s in evidence.flow_signals}
    assert weights == {
        "cons": 50.0,
        "streak": 20.0,
        "vwap": 10.0,
        "flow": 5.0,
        "inst": 15.0,
    }


def test_custom_policy_strength_uses_available_weights():
    builder = FlowConfirmationEvidenceBuilder(accum_score_policy=_custom_policy())
    custom_components = (
        _comp("cons", 33.3, 50.0),
        _comp("streak", 15.8, 20.0),
        _comp("vwap", 10.0, 10.0),
        _comp("flow", 5.0, 5.0),
        _comp("inst", 12.5, 15.0),
    )
    candidate = _candidate(flow_evidence=_flow_evidence(custom_components))

    evidence = builder.build(
        candidate, consumed_broker_summaries=(), consumed_broker_daily_flows=()
    ).evidence

    available_weight = 50.0 + 20.0 + 10.0 + 5.0 + 15.0
    expected_strength = round(evidence.flow_score_ex_bb / available_weight, 4)
    assert evidence.uncapped_strength == expected_strength


def test_disabled_component_excluded_from_flow_group():
    policy = AccumScorePolicy(
        foreign_flow_ratio=LinearSaturationPolicy(enabled=False, weight=8.3),
    )
    builder = FlowConfirmationEvidenceBuilder(accum_score_policy=policy)
    components = (
        _comp("cons", 33.3, 33.3),
        _comp("streak", 15.8, 25.0),
        _comp("vwap", 16.7, 16.7),
        _comp("flow", None, 8.3, ForeignFlowComponentStatus.DISABLED),
        _comp("inst", 12.5, 12.5),
    )
    candidate = _candidate(flow_evidence=_flow_evidence(components))

    evidence = builder.build(
        candidate, consumed_broker_summaries=(), consumed_broker_daily_flows=()
    ).evidence

    assert "flow" not in {s.key for s in evidence.flow_signals}
    assert sum(signal.weight for signal in evidence.flow_signals) == 87.5
    assert evidence.flow_score_ex_bb == round(86.6 - 8.3, 1)


def test_all_disabled_flow_strength_is_zero_without_bandar():
    policy = AccumScorePolicy(
        consistency=EvidenceComponentPolicy(enabled=False, weight=33.3),
        streak=StreakEvidencePolicy(enabled=False, weight=25.0),
        vwap_discount=LinearSaturationPolicy(enabled=False, weight=16.7),
        foreign_flow_ratio=LinearSaturationPolicy(enabled=False, weight=8.3),
        bci=BciEvidencePolicy(enabled=False, cluster_points=12.5, stable_points=4.2),
    )
    builder = FlowConfirmationEvidenceBuilder(accum_score_policy=policy)
    disabled_components = tuple(
        _comp(k, None, weight, ForeignFlowComponentStatus.DISABLED)
        for k, weight in {
            "cons": 33.3,
            "streak": 25.0,
            "vwap": 16.7,
            "flow": 8.3,
            "inst": 12.5,
        }.items()
    )
    candidate = _candidate(
        flow_evidence=_flow_evidence(disabled_components), bandar_detector=None
    )

    evidence = builder.build(
        candidate, consumed_broker_summaries=(), consumed_broker_daily_flows=()
    ).evidence

    assert evidence.uncapped_strength == 0.0
    assert evidence.capped_strength == 0.0
    assert evidence.flow_signals == ()


def test_all_disabled_bandar_strength_still_works():
    policy = AccumScorePolicy(
        consistency=EvidenceComponentPolicy(enabled=False, weight=33.3),
        streak=StreakEvidencePolicy(enabled=False, weight=25.0),
        vwap_discount=LinearSaturationPolicy(enabled=False, weight=16.7),
        foreign_flow_ratio=LinearSaturationPolicy(enabled=False, weight=8.3),
        bci=BciEvidencePolicy(enabled=False, cluster_points=12.5, stable_points=4.2),
    )
    builder = FlowConfirmationEvidenceBuilder(accum_score_policy=policy)
    disabled_components = tuple(
        _comp(k, None, weight, ForeignFlowComponentStatus.DISABLED)
        for k, weight in {
            "cons": 33.3,
            "streak": 25.0,
            "vwap": 16.7,
            "flow": 8.3,
            "inst": 12.5,
        }.items()
    )
    candidate = _candidate(
        flow_evidence=_flow_evidence(disabled_components),
        bandar_detector=SimpleNamespace(broad_score=12),
    )

    evidence = builder.build(
        candidate, consumed_broker_summaries=(), consumed_broker_daily_flows=()
    ).evidence

    assert evidence.uncapped_strength == 0.5


class TestProvenance:
    def test_provenance_reflects_exact_consumed_broker_summary_rows(self):
        builder = FlowConfirmationEvidenceBuilder()
        candidate = _candidate(flow_evidence=_flow_evidence(_FULL_COMPONENTS))
        summaries = (
            _broker_summary("BBCA", date(2026, 6, 1), source="idx"),
            _broker_summary("BBCA", date(2026, 6, 2), source="idx"),
        )

        built = builder.build(
            candidate, consumed_broker_summaries=summaries, consumed_broker_daily_flows=()
        )

        assert len(built.provenance.broker_summary_rows) == 2
        assert {r.date for r in built.provenance.broker_summary_rows} == {
            date(2026, 6, 1),
            date(2026, 6, 2),
        }
        assert all(r.ticker == "BBCA" for r in built.provenance.broker_summary_rows)
        assert all(r.source == "idx" for r in built.provenance.broker_summary_rows)

    def test_provenance_reflects_exact_consumed_daily_flow_rows(self):
        builder = FlowConfirmationEvidenceBuilder()
        candidate = _candidate(flow_evidence=_flow_evidence(_FULL_COMPONENTS))
        flows = (
            _broker_daily_flow("BBCA", date(2026, 6, 1), "AK", source="stockbit"),
            _broker_daily_flow("BBCA", date(2026, 6, 1), "BK", source="stockbit"),
        )

        built = builder.build(
            candidate, consumed_broker_summaries=(), consumed_broker_daily_flows=flows
        )

        assert len(built.provenance.broker_daily_flow_rows) == 2
        assert {r.broker_code for r in built.provenance.broker_daily_flow_rows} == {
            "AK",
            "BK",
        }
        assert all(r.ticker == "BBCA" for r in built.provenance.broker_daily_flow_rows)
        assert all(
            r.source == "stockbit" for r in built.provenance.broker_daily_flow_rows
        )

    def test_provenance_excludes_rows_not_passed_in(self):
        builder = FlowConfirmationEvidenceBuilder()
        candidate = _candidate(flow_evidence=_flow_evidence(_FULL_COMPONENTS))
        only_row = (_broker_summary("BBCA", date(2026, 6, 1)),)

        built = builder.build(
            candidate, consumed_broker_summaries=only_row, consumed_broker_daily_flows=()
        )

        assert len(built.provenance.broker_summary_rows) == 1
        assert built.provenance.broker_summary_rows[0].date == date(2026, 6, 1)

    def test_has_bandar_contributor_true_when_broad_score_present(self):
        builder = FlowConfirmationEvidenceBuilder()
        candidate = _candidate(
            flow_evidence=_flow_evidence(_FULL_COMPONENTS),
            bandar_detector=SimpleNamespace(broad_score=8),
        )

        built = builder.build(
            candidate, consumed_broker_summaries=(), consumed_broker_daily_flows=()
        )

        assert built.provenance.has_bandar_contributor is True

    def test_has_bandar_contributor_false_when_no_bandar_snapshot(self):
        builder = FlowConfirmationEvidenceBuilder()
        candidate = _candidate(
            flow_evidence=_flow_evidence(_FULL_COMPONENTS),
            bandar_detector=None,
        )

        built = builder.build(
            candidate, consumed_broker_summaries=(), consumed_broker_daily_flows=()
        )

        assert built.provenance.has_bandar_contributor is False

    def test_has_bandar_contributor_false_when_broad_score_is_none(self):
        builder = FlowConfirmationEvidenceBuilder()
        candidate = _candidate(
            flow_evidence=_flow_evidence(_FULL_COMPONENTS),
            bandar_detector=SimpleNamespace(broad_score=None),
        )

        built = builder.build(
            candidate, consumed_broker_summaries=(), consumed_broker_daily_flows=()
        )

        assert built.provenance.has_bandar_contributor is False

    def test_mismatched_ticker_summary_row_raises(self):
        builder = FlowConfirmationEvidenceBuilder()
        candidate = _candidate(
            ticker="BBCA", flow_evidence=_flow_evidence(_FULL_COMPONENTS)
        )
        foreign_row = (_broker_summary("ASII", date(2026, 6, 1)),)

        with pytest.raises(ValueError, match="ticker mismatch"):
            builder.build(
                candidate,
                consumed_broker_summaries=foreign_row,
                consumed_broker_daily_flows=(),
            )

    def test_mismatched_ticker_daily_flow_row_raises(self):
        builder = FlowConfirmationEvidenceBuilder()
        candidate = _candidate(
            ticker="BBCA", flow_evidence=_flow_evidence(_FULL_COMPONENTS)
        )
        foreign_row = (_broker_daily_flow("ASII", date(2026, 6, 1), "AK"),)

        with pytest.raises(ValueError, match="ticker mismatch"):
            builder.build(
                candidate,
                consumed_broker_summaries=(),
                consumed_broker_daily_flows=foreign_row,
            )
