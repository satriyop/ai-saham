"""Negative-validation tests for the ADR-041 canonical evidence boundary."""

from datetime import date, datetime, timedelta, timezone

import pytest

from src.domain.value_objects.benchmark_excess_return import (
    BenchmarkExcessReturn,
    BenchmarkExcessReturnStatus,
)
from src.domain.value_objects.canonical_signal_evidence_input import (
    BrokerDailyFlowRowIdentity,
    BrokerSummaryRowIdentity,
    CandleRowIdentity,
    CanonicalSignalEvidenceInput,
    FlowEvidenceGroupInput,
    FlowProvenance,
    SetupEvidenceGroupInput,
    SetupProvenance,
)
from src.domain.value_objects.evidence_source_availability import EvidenceSourceAvailability
from src.domain.value_objects.factor_evidence import Direction, Freshness
from src.domain.value_objects.flow_confirmation_evidence import (
    FlowConfirmationEvidence,
    FlowSubSignal,
)
from src.domain.value_objects.setup_evidence import SetupEvidence
from src.domain.value_objects.source_availability import (
    SourceAvailabilityAssessment,
    SourceAvailabilityStatus,
)

SNAP = date(2026, 7, 3)
DECISION_AT = datetime(2026, 7, 3, 16, 0, tzinfo=timezone.utc)


def _excess_return() -> BenchmarkExcessReturn:
    return BenchmarkExcessReturn(
        benchmark="IHSG",
        window_sessions=5,
        ticker_return_pct=1.0,
        benchmark_return_pct=0.0,
        excess_return_pct=1.0,
        window_start=date(2026, 6, 1),
        window_end=SNAP,
        common_session_count=6,
        status=BenchmarkExcessReturnStatus.AVAILABLE,
        unavailable_reason=None,
    )


def _setup_evidence(ticker: str = "BBCA") -> SetupEvidence:
    return SetupEvidence(
        ticker=ticker,
        snapshot_date=SNAP,
        setup_name="foreign-bounce",
        setup_match="MATCH",
        match_strength=100.0,
        failed_gates=(),
        trend="UP",
        rsi=45.0,
        bb_width_pctile=0.20,
        vwap_discount_pct=1.5,
        vwap_pct=1.02,
        benchmark_excess_return_5_session=_excess_return(),
        benchmark_excess_return_20_session=_excess_return(),
        volume_trend_ratio=1.2,
        volume_freshness=Freshness.FRESH,
        candle_source="stockbit",
    )


def _flow_evidence(ticker: str = "BBCA") -> FlowConfirmationEvidence:
    signal = FlowSubSignal(
        key="cons", score=40.0, weight=40.0, direction=Direction.BULLISH, freshness=Freshness.FRESH
    )
    return FlowConfirmationEvidence(
        ticker=ticker,
        snapshot_date=SNAP,
        flow_signals=(signal,),
        flow_score_ex_bb=40.0,
        confirmation_status="CONFIRMED",
        flow_direction="POSITIVE",
        bandar_broad_score=None,
        bandar_direction=Direction.NEUTRAL,
        bandar_freshness=Freshness.MISSING,
        bci_label=None,
        bci_tier1_count=0,
        uncapped_strength=0.70,
        capped_strength=0.70,
        group_cap=0.80,
        group_freshness=Freshness.FRESH,
    )


def _assessment(
    source_family: str,
    *,
    observed_through: date | None,
    status: SourceAvailabilityStatus = SourceAvailabilityStatus.CURRENT,
    is_authoritative: bool = True,
) -> SourceAvailabilityAssessment:
    return SourceAvailabilityAssessment(
        source_family=source_family,
        decision_at=DECISION_AT,
        observed_through=observed_through,
        available_at=DECISION_AT,
        status=status,
        is_authoritative=is_authoritative,
        reason="test",
    )


def _setup_provenance(ticker: str = "BBCA", *, with_benchmark: bool = True) -> SetupProvenance:
    return SetupProvenance(
        ticker=ticker,
        candle_rows=(CandleRowIdentity(ticker=ticker, date=SNAP, source="stockbit"),),
        benchmark_candle_rows=(
            (CandleRowIdentity(ticker="IHSG", date=SNAP, source="idx"),)
            if with_benchmark
            else ()
        ),
    )


def _setup_availability(observed_through: date | None = SNAP) -> EvidenceSourceAvailability:
    return EvidenceSourceAvailability(
        evidence_group="setup",
        assessments=(_assessment("candles", observed_through=observed_through),),
    )


def _flow_provenance(ticker: str = "BBCA") -> FlowProvenance:
    return FlowProvenance(
        ticker=ticker,
        broker_summary_rows=(BrokerSummaryRowIdentity(ticker=ticker, date=SNAP, source="idx"),),
        broker_daily_flow_rows=(
            BrokerDailyFlowRowIdentity(
                ticker=ticker, date=SNAP, broker_code="YP", source="stockbit"
            ),
        ),
    )


def _flow_availability(observed_through: date | None = SNAP) -> EvidenceSourceAvailability:
    return EvidenceSourceAvailability(
        evidence_group="flow",
        assessments=(
            _assessment("broker_summaries", observed_through=observed_through),
            _assessment("broker_daily_flow", observed_through=observed_through),
        ),
    )


class TestSetupProvenanceTickerMismatch:
    def test_foreign_candle_row_raises(self) -> None:
        with pytest.raises(ValueError, match="ticker mismatch"):
            SetupProvenance(
                ticker="BBCA",
                candle_rows=(CandleRowIdentity(ticker="ASII", date=SNAP, source="stockbit"),),
            )

    def test_group_input_evidence_provenance_ticker_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="ticker mismatch"):
            SetupEvidenceGroupInput(
                evidence=_setup_evidence(ticker="BBCA"),
                provenance=_setup_provenance(ticker="ASII"),
                availability=_setup_availability(),
            )

    def test_benchmark_rows_must_be_canonical_benchmark_ticker(self) -> None:
        with pytest.raises(ValueError, match="benchmark_candle_rows"):
            SetupProvenance(
                ticker="BBCA",
                candle_rows=(),
                benchmark_candle_rows=(
                    CandleRowIdentity(ticker="BBCA", date=SNAP, source="stockbit"),
                ),
            )


class TestBenchmarkProvenanceRequiredWhenBenchmarkEvidenceAvailable:
    def test_available_benchmark_excess_return_with_empty_benchmark_rows_raises(self) -> None:
        with pytest.raises(ValueError, match="benchmark excess-return"):
            SetupEvidenceGroupInput(
                evidence=_setup_evidence(),
                provenance=_setup_provenance(with_benchmark=False),
                availability=_setup_availability(),
            )

    def test_available_benchmark_excess_return_with_benchmark_rows_is_valid(self) -> None:
        group = SetupEvidenceGroupInput(
            evidence=_setup_evidence(),
            provenance=_setup_provenance(with_benchmark=True),
            availability=_setup_availability(),
        )
        assert group.provenance.benchmark_candle_rows


class TestFlowProvenanceTickerMismatch:
    def test_foreign_broker_summary_row_raises(self) -> None:
        with pytest.raises(ValueError, match="ticker mismatch"):
            FlowProvenance(
                ticker="BBCA",
                broker_summary_rows=(
                    BrokerSummaryRowIdentity(ticker="ASII", date=SNAP, source="idx"),
                ),
                broker_daily_flow_rows=(),
            )

    def test_foreign_broker_daily_flow_row_raises(self) -> None:
        with pytest.raises(ValueError, match="ticker mismatch"):
            FlowProvenance(
                ticker="BBCA",
                broker_summary_rows=(),
                broker_daily_flow_rows=(
                    BrokerDailyFlowRowIdentity(
                        ticker="ASII", date=SNAP, broker_code="YP", source="stockbit"
                    ),
                ),
            )


class TestBandarContributorCrossValidation:
    def _bandar_flow_provenance(self, ticker: str = "BBCA") -> FlowProvenance:
        return FlowProvenance(
            ticker=ticker,
            broker_summary_rows=(BrokerSummaryRowIdentity(ticker=ticker, date=SNAP, source="idx"),),
            broker_daily_flow_rows=(
                BrokerDailyFlowRowIdentity(
                    ticker=ticker, date=SNAP, broker_code="YP", source="stockbit"
                ),
            ),
            has_bandar_contributor=True,
        )

    def test_bandar_contributor_without_unassessed_marker_raises(self) -> None:
        availability = EvidenceSourceAvailability(
            evidence_group="flow",
            assessments=(
                _assessment("broker_summaries", observed_through=SNAP),
                _assessment("broker_daily_flow", observed_through=SNAP),
            ),
            # bandar_detector deliberately omitted from unassessed_contributors
        )
        with pytest.raises(ValueError, match="bandar_detector"):
            FlowEvidenceGroupInput(
                evidence=_flow_evidence(),
                provenance=self._bandar_flow_provenance(),
                availability=availability,
            )

    def test_bandar_contributor_with_unassessed_marker_is_valid(self) -> None:
        availability = EvidenceSourceAvailability(
            evidence_group="flow",
            assessments=(
                _assessment("broker_summaries", observed_through=SNAP),
                _assessment("broker_daily_flow", observed_through=SNAP),
            ),
            unassessed_contributors=("bandar_detector",),
        )
        group = FlowEvidenceGroupInput(
            evidence=_flow_evidence(),
            provenance=self._bandar_flow_provenance(),
            availability=availability,
        )
        assert group.availability.all_authoritative is False

    def test_bandar_contributor_with_explicit_assessment_is_valid(self) -> None:
        availability = EvidenceSourceAvailability(
            evidence_group="flow",
            assessments=(
                _assessment("broker_summaries", observed_through=SNAP),
                _assessment("broker_daily_flow", observed_through=SNAP),
                _assessment("bandar_detector", observed_through=SNAP),
            ),
        )
        group = FlowEvidenceGroupInput(
            evidence=_flow_evidence(),
            provenance=self._bandar_flow_provenance(),
            availability=availability,
        )
        assert group.availability.all_authoritative is True


class TestWrongAvailabilityGroup:
    def test_setup_group_rejects_flow_availability(self) -> None:
        with pytest.raises(ValueError, match="evidence_group"):
            SetupEvidenceGroupInput(
                evidence=_setup_evidence(),
                provenance=_setup_provenance(),
                availability=_flow_availability(),
            )

    def test_flow_group_rejects_setup_availability(self) -> None:
        with pytest.raises(ValueError, match="evidence_group"):
            FlowEvidenceGroupInput(
                evidence=_flow_evidence(),
                provenance=_flow_provenance(),
                availability=_setup_availability(),
            )


class TestMissingRequiredAssessment:
    def test_setup_missing_candles_assessment_raises(self) -> None:
        empty_availability = EvidenceSourceAvailability(evidence_group="setup", assessments=())
        with pytest.raises(ValueError, match="candles"):
            SetupEvidenceGroupInput(
                evidence=_setup_evidence(),
                provenance=_setup_provenance(),
                availability=empty_availability,
            )

    def test_flow_missing_broker_summaries_assessment_raises(self) -> None:
        availability = EvidenceSourceAvailability(
            evidence_group="flow",
            assessments=(_assessment("broker_daily_flow", observed_through=SNAP),),
        )
        with pytest.raises(ValueError, match="broker_summaries"):
            FlowEvidenceGroupInput(
                evidence=_flow_evidence(), provenance=_flow_provenance(), availability=availability
            )

    def test_flow_missing_broker_daily_flow_assessment_raises(self) -> None:
        availability = EvidenceSourceAvailability(
            evidence_group="flow",
            assessments=(_assessment("broker_summaries", observed_through=SNAP),),
        )
        with pytest.raises(ValueError, match="broker_daily_flow"):
            FlowEvidenceGroupInput(
                evidence=_flow_evidence(), provenance=_flow_provenance(), availability=availability
            )


class TestObservedThroughMismatch:
    def test_setup_observed_through_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="observed_through"):
            SetupEvidenceGroupInput(
                evidence=_setup_evidence(),
                provenance=_setup_provenance(),
                availability=_setup_availability(observed_through=date(2026, 7, 1)),
            )

    def test_flow_observed_through_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="observed_through"):
            FlowEvidenceGroupInput(
                evidence=_flow_evidence(),
                provenance=_flow_provenance(),
                availability=_flow_availability(observed_through=date(2026, 7, 1)),
            )


class TestEmptyProvenanceMustBeUnknownNonAuthoritative:
    def test_empty_setup_provenance_with_authoritative_assessment_raises(self) -> None:
        empty_provenance = SetupProvenance(ticker="BBCA", candle_rows=())
        availability = EvidenceSourceAvailability(
            evidence_group="setup",
            assessments=(_assessment("candles", observed_through=None),),
        )
        with pytest.raises(ValueError, match="UNKNOWN"):
            SetupEvidenceGroupInput(
                evidence=_setup_evidence(), provenance=empty_provenance, availability=availability
            )

    def test_empty_setup_provenance_with_explicit_unknown_non_authoritative_is_valid(self) -> None:
        # benchmark_candle_rows populated so this test isolates the
        # candle_rows-empty behavior from the separate benchmark-provenance
        # requirement (see TestBenchmarkProvenanceRequiredWhenBenchmarkEvidenceAvailable).
        empty_provenance = SetupProvenance(
            ticker="BBCA",
            candle_rows=(),
            benchmark_candle_rows=(CandleRowIdentity(ticker="IHSG", date=SNAP, source="idx"),),
        )
        availability = EvidenceSourceAvailability(
            evidence_group="setup",
            assessments=(
                _assessment(
                    "candles",
                    observed_through=None,
                    status=SourceAvailabilityStatus.UNKNOWN,
                    is_authoritative=False,
                ),
            ),
        )
        group = SetupEvidenceGroupInput(
            evidence=_setup_evidence(), provenance=empty_provenance, availability=availability
        )
        assert group.availability.all_authoritative is False

    def test_empty_flow_row_group_with_authoritative_assessment_raises(self) -> None:
        empty_provenance = FlowProvenance(
            ticker="BBCA", broker_summary_rows=(), broker_daily_flow_rows=()
        )
        availability = EvidenceSourceAvailability(
            evidence_group="flow",
            assessments=(
                _assessment("broker_summaries", observed_through=None),
                _assessment("broker_daily_flow", observed_through=None),
            ),
        )
        with pytest.raises(ValueError, match="UNKNOWN"):
            FlowEvidenceGroupInput(
                evidence=_flow_evidence(), provenance=empty_provenance, availability=availability
            )


class TestDuplicateRowIdentities:
    def test_duplicate_candle_rows_raise(self) -> None:
        row = CandleRowIdentity(ticker="BBCA", date=SNAP, source="stockbit")
        with pytest.raises(ValueError, match="duplicate"):
            SetupProvenance(ticker="BBCA", candle_rows=(row, row))

    def test_duplicate_broker_summary_rows_raise(self) -> None:
        row = BrokerSummaryRowIdentity(ticker="BBCA", date=SNAP, source="idx")
        with pytest.raises(ValueError, match="duplicate"):
            FlowProvenance(ticker="BBCA", broker_summary_rows=(row, row), broker_daily_flow_rows=())

    def test_duplicate_broker_daily_flow_rows_raise(self) -> None:
        row = BrokerDailyFlowRowIdentity(ticker="BBCA", date=SNAP, broker_code="YP", source="stockbit")
        with pytest.raises(ValueError, match="duplicate"):
            FlowProvenance(ticker="BBCA", broker_summary_rows=(), broker_daily_flow_rows=(row, row))


class TestRejectsNonDomainEvidence:
    def test_setup_group_rejects_arbitrary_object(self) -> None:
        class _FakeEvidence:
            ticker = "BBCA"

        with pytest.raises(ValueError, match="SetupEvidence"):
            SetupEvidenceGroupInput(
                evidence=_FakeEvidence(),  # type: ignore[arg-type]
                provenance=_setup_provenance(),
                availability=_setup_availability(),
            )

    def test_flow_group_rejects_arbitrary_object(self) -> None:
        class _FakeEvidence:
            ticker = "BBCA"

        with pytest.raises(ValueError, match="FlowConfirmationEvidence"):
            FlowEvidenceGroupInput(
                evidence=_FakeEvidence(),  # type: ignore[arg-type]
                provenance=_flow_provenance(),
                availability=_flow_availability(),
            )


class TestValidCanonicalSignalEvidenceInput:
    def test_missing_group_is_none_not_empty_present_group(self) -> None:
        canonical = CanonicalSignalEvidenceInput(setup=None, flow=None)
        assert canonical.setup is None
        assert canonical.flow is None

    def test_fully_populated_construction_succeeds(self) -> None:
        setup_group = SetupEvidenceGroupInput(
            evidence=_setup_evidence(),
            provenance=_setup_provenance(),
            availability=_setup_availability(),
        )
        flow_group = FlowEvidenceGroupInput(
            evidence=_flow_evidence(),
            provenance=_flow_provenance(),
            availability=_flow_availability(),
        )
        canonical = CanonicalSignalEvidenceInput(setup=setup_group, flow=flow_group)
        assert canonical.setup is setup_group
        assert canonical.flow is flow_group

    def test_screen_style_flow_only_input_is_valid(self) -> None:
        flow_group = FlowEvidenceGroupInput(
            evidence=_flow_evidence(),
            provenance=_flow_provenance(),
            availability=_flow_availability(),
        )
        canonical = CanonicalSignalEvidenceInput(setup=None, flow=flow_group)
        assert canonical.setup is None
        assert canonical.flow is flow_group


class TestCanonicalGroupRejectsFutureProvenance:
    """Finding 4: the final canonical group constructors must independently
    reject future-dated provenance rows even if an upstream builder was
    bypassed and a caller constructs the group directly with matching
    (also-future) observed_through values."""

    FUTURE = SNAP + timedelta(days=1)

    def test_future_setup_ticker_candle_raises(self) -> None:
        provenance = SetupProvenance(
            ticker="BBCA",
            candle_rows=(
                CandleRowIdentity(ticker="BBCA", date=self.FUTURE, source="stockbit"),
            ),
            benchmark_candle_rows=(
                CandleRowIdentity(ticker="IHSG", date=SNAP, source="idx"),
            ),
        )
        availability = _setup_availability(observed_through=self.FUTURE)

        with pytest.raises(
            ValueError,
            match=r"provenance\.candle_rows.*after evidence\.snapshot_date",
        ):
            SetupEvidenceGroupInput(
                evidence=_setup_evidence(),
                provenance=provenance,
                availability=availability,
            )

    def test_future_setup_benchmark_candle_raises(self) -> None:
        provenance = SetupProvenance(
            ticker="BBCA",
            candle_rows=(CandleRowIdentity(ticker="BBCA", date=SNAP, source="stockbit"),),
            benchmark_candle_rows=(
                CandleRowIdentity(ticker="IHSG", date=self.FUTURE, source="idx"),
            ),
        )
        availability = _setup_availability(observed_through=SNAP)

        with pytest.raises(
            ValueError,
            match=r"provenance\.benchmark_candle_rows.*after evidence\.snapshot_date",
        ):
            SetupEvidenceGroupInput(
                evidence=_setup_evidence(),
                provenance=provenance,
                availability=availability,
            )

    def test_future_broker_summary_row_raises(self) -> None:
        provenance = FlowProvenance(
            ticker="BBCA",
            broker_summary_rows=(
                BrokerSummaryRowIdentity(ticker="BBCA", date=self.FUTURE, source="idx"),
            ),
            broker_daily_flow_rows=(
                BrokerDailyFlowRowIdentity(
                    ticker="BBCA", date=SNAP, broker_code="YP", source="stockbit"
                ),
            ),
        )
        availability = EvidenceSourceAvailability(
            evidence_group="flow",
            assessments=(
                _assessment("broker_summaries", observed_through=self.FUTURE),
                _assessment("broker_daily_flow", observed_through=SNAP),
            ),
        )

        with pytest.raises(
            ValueError,
            match=r"provenance\.broker_summary_rows.*after evidence\.snapshot_date",
        ):
            FlowEvidenceGroupInput(
                evidence=_flow_evidence(),
                provenance=provenance,
                availability=availability,
            )

    def test_future_broker_daily_flow_row_raises(self) -> None:
        provenance = FlowProvenance(
            ticker="BBCA",
            broker_summary_rows=(
                BrokerSummaryRowIdentity(ticker="BBCA", date=SNAP, source="idx"),
            ),
            broker_daily_flow_rows=(
                BrokerDailyFlowRowIdentity(
                    ticker="BBCA", date=self.FUTURE, broker_code="YP", source="stockbit"
                ),
            ),
        )
        availability = EvidenceSourceAvailability(
            evidence_group="flow",
            assessments=(
                _assessment("broker_summaries", observed_through=SNAP),
                _assessment("broker_daily_flow", observed_through=self.FUTURE),
            ),
        )

        with pytest.raises(
            ValueError,
            match=r"provenance\.broker_daily_flow_rows.*after evidence\.snapshot_date",
        ):
            FlowEvidenceGroupInput(
                evidence=_flow_evidence(),
                provenance=provenance,
                availability=availability,
            )

    def test_rows_on_snapshot_date_are_accepted(self) -> None:
        setup_evidence = _setup_evidence()
        setup_provenance = _setup_provenance()
        setup_availability = _setup_availability()
        setup_group = SetupEvidenceGroupInput(
            evidence=setup_evidence,
            provenance=setup_provenance,
            availability=setup_availability,
        )
        assert setup_group.evidence is setup_evidence
        assert setup_group.provenance is setup_provenance

        flow_evidence = _flow_evidence()
        flow_provenance = _flow_provenance()
        flow_availability = _flow_availability()
        flow_group = FlowEvidenceGroupInput(
            evidence=flow_evidence,
            provenance=flow_provenance,
            availability=flow_availability,
        )
        assert flow_group.evidence is flow_evidence
        assert flow_group.provenance is flow_provenance
