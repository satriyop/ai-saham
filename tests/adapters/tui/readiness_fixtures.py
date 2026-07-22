from __future__ import annotations

from dataclasses import replace
from datetime import date

from src.application.use_case.report_signal_readiness_use_case import (
    SignalReadinessExclusionLedger,
    SignalReadinessReport,
    SignalReadinessTarget,
)

TARGET = "foreign_institutional_accumulation_large_cap_SWING_10D"
COHORT_A = "sha256:" + "a" * 64
COHORT_B = "sha256:" + "b" * 64


def readiness_report() -> SignalReadinessReport:
    return SignalReadinessReport(
        target=SignalReadinessTarget.parse(TARGET),
        observation_dates=(date(2026, 7, 20), date(2026, 7, 21)),
        latest_observation_date=date(2026, 7, 21),
        latest_observation_count=12,
        raw_latest_observation_count=14,
        target_filter_count=10,
        raw_target_filter_count=11,
        label_count=74,
        unavailable_label_count=9,
        target_label_count=60,
        raw_labeled_target_count=58,
        labeled_target_count=55,
        is_count=38,
        oos_count=17,
        oos_profit_factor=1.2,
        oos_average_return=0.4,
        diagnostic_ready=True,
        patch_eligible=True,
        promotion_eligible=False,
        oos_split="EPHEMERAL_CHRONOLOGICAL_70_30",
        selected_semantic_compatibility_id=COHORT_A,
        available_semantic_compatibility_ids=(COHORT_A,),
        unique_tickers=8,
        unique_signal_dates=16,
        exclusions=SignalReadinessExclusionLedger(
            excluded_schema_mismatch=4,
            excluded_unavailable=9,
            excluded_target_mismatch=18,
            excluded_wrong_cohort=7,
            excluded_unlinked_observation=3,
            excluded_duplicate_collapsed=2,
        ),
        notes=("diagnostic note",),
        blockers=("calibration blocker",),
    )


def mixed_cohort_report() -> SignalReadinessReport:
    return replace(
        readiness_report(),
        selected_semantic_compatibility_id=None,
        available_semantic_compatibility_ids=(COHORT_A, COHORT_B),
        is_count=0,
        oos_count=0,
        oos_profit_factor=None,
        oos_average_return=None,
        diagnostic_ready=False,
        patch_eligible=False,
        blockers=("mixed_semantic_cohorts",),
    )


def empty_readiness_report() -> SignalReadinessReport:
    return replace(
        readiness_report(),
        observation_dates=(),
        latest_observation_date=None,
        latest_observation_count=0,
        raw_latest_observation_count=0,
        target_filter_count=0,
        raw_target_filter_count=0,
        label_count=0,
        unavailable_label_count=0,
        target_label_count=0,
        raw_labeled_target_count=0,
        labeled_target_count=0,
        is_count=0,
        oos_count=0,
        diagnostic_ready=False,
        patch_eligible=False,
        selected_semantic_compatibility_id=None,
        available_semantic_compatibility_ids=(),
        unique_tickers=0,
        unique_signal_dates=0,
        blockers=(
            "no semantic_compatibility_id on canonical observations",
            "no candidate observations saved",
            "no forward labels generated yet",
        ),
    )
