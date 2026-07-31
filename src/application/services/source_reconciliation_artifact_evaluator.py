"""
Pure evaluation policy for DQ-001E signal-artifact/market-context
reconciliation checks.

Canonical tables (post learning clean-break):
  learning_observations, learning_outcome_labels,
  market_context_snapshots, regime_observations.

Retired candidate_observations / signal_forward_labels are not required.
DTO/method names may still say "candidate"/"signal_forward" for call-site
stability; check ``name`` / ``table`` fields use canonical names.

Layer: Application
AI usage: None
"""

from __future__ import annotations

from src.application.dto.source_reconciliation_dto import (
    RawCandidateObservationIdentityObservation,
    RawLearningObservationsRiskPitObservation,
    RawMarketContextSnapshotObservation,
    RawRegimeObservationsObservation,
    RawSignalForwardLabelsLinkageObservation,
    SourceReconciliationCheckResult,
    SourceReconciliationFinding,
    aggregate_status,
)

_MISSING_TABLE_IMPACT = "Reconciliation cannot be performed for this table."


def _missing_table_result(
    name: str, table: str, severity: str
) -> tuple[SourceReconciliationCheckResult, tuple[SourceReconciliationFinding, ...]]:
    finding = SourceReconciliationFinding(
        severity=severity,
        code="MISSING_TABLE" if severity == "FAIL" else "MISSING_OPTIONAL_ARTIFACT_TABLE",
        table=table,
        field=None,
        message=f"{table} does not exist.",
        impact=_MISSING_TABLE_IMPACT,
    )
    check = SourceReconciliationCheckResult(
        name=name,
        status=severity,
        tables=(table,),
        checked_row_count=None,
        mismatch_count=None,
        summary={},
    )
    return check, (finding,)


def _schema_insufficient_result(
    name: str, table: str, code: str, row_count: int, missing_columns: tuple[str, ...]
) -> tuple[SourceReconciliationCheckResult, tuple[SourceReconciliationFinding, ...]]:
    finding = SourceReconciliationFinding(
        severity="FAIL",
        code=code,
        table=table,
        field=None,
        message=f"{table} is missing required column(s): {', '.join(missing_columns)}.",
        impact="Reconciliation cannot be performed for this table until the schema is repaired.",
        row_count=row_count,
    )
    check = SourceReconciliationCheckResult(
        name=name,
        status="FAIL",
        tables=(table,),
        checked_row_count=row_count,
        mismatch_count=None,
        summary={"missing_columns": list(missing_columns)},
    )
    return check, (finding,)


def evaluate_candidate_observations_identity(
    raw: RawCandidateObservationIdentityObservation,
) -> tuple[SourceReconciliationCheckResult, tuple[SourceReconciliationFinding, ...]]:
    """learning_observations identity (canonical post clean-break)."""
    table = "learning_observations"
    name = "learning_observations_identity"
    if not raw.exists:
        return _missing_table_result(name, table, "FAIL")

    if not raw.schema_sufficient:
        return _schema_insufficient_result(
            name,
            table,
            "LEARNING_OBSERVATIONS_SCHEMA_INSUFFICIENT",
            raw.row_count,
            raw.missing_columns,
        )

    findings: list[SourceReconciliationFinding] = []

    if raw.canonical_missing_identity_count:
        findings.append(
            SourceReconciliationFinding(
                severity="FAIL",
                code="LEARNING_OBSERVATIONS_CANONICAL_MISSING_IDENTITY",
                table=table,
                field=None,
                message=(
                    f"{raw.canonical_missing_identity_count} cohort-tagged "
                    "(compatibility_id set) row(s) have null/empty observation_id, "
                    "purpose, captured_at, contract_id, window_id, or decision_payload_json."
                ),
                impact="Canonical rows cannot be trusted for point-in-time replay/readiness.",
                sample_rows=raw.canonical_missing_identity_samples,
                row_count=raw.canonical_row_count,
                mismatch_count=raw.canonical_missing_identity_count,
            )
        )

    if raw.legacy_row_count:
        findings.append(
            SourceReconciliationFinding(
                severity="WARN",
                code="LEARNING_OBSERVATIONS_UNTAGGED_COMPATIBILITY",
                table=table,
                field="compatibility_id",
                message=(
                    f"{raw.legacy_row_count} of {raw.row_count} row(s) have empty "
                    "compatibility_id (untagged / non-cohort identity)."
                ),
                impact=(
                    "Untagged rows cannot be isolated by compatibility cohort; "
                    "exclude from single-cohort challenge/label runs."
                ),
                row_count=raw.row_count,
                mismatch_count=raw.legacy_row_count,
            )
        )

    if raw.duplicate_canonical_identity_count:
        findings.append(
            SourceReconciliationFinding(
                severity="WARN",
                code="LEARNING_OBSERVATIONS_DUPLICATE_OBSERVATION_ID",
                table=table,
                field="observation_id",
                message=(
                    f"{raw.duplicate_canonical_identity_count} duplicate "
                    "observation_id row(s) among compatibility-tagged observations."
                ),
                impact="Canonical identity is not unique; readiness counts may double-count.",
                sample_rows=raw.duplicate_canonical_identity_samples,
                row_count=raw.canonical_row_count,
                mismatch_count=raw.duplicate_canonical_identity_count,
            )
        )

    if raw.invalid_payload_json_count:
        findings.append(
            SourceReconciliationFinding(
                severity="FAIL",
                code="LEARNING_OBSERVATIONS_INVALID_DECISION_PAYLOAD_JSON",
                table=table,
                field="decision_payload_json",
                message=(
                    f"{raw.invalid_payload_json_count} row(s) have decision_payload_json "
                    "that does not parse as valid JSON."
                ),
                impact="Evidence/fingerprint payload cannot be read for affected rows.",
                sample_rows=raw.invalid_payload_json_samples,
                row_count=raw.row_count,
                mismatch_count=raw.invalid_payload_json_count,
            )
        )

    if raw.payload_missing_schema_marker_count:
        findings.append(
            SourceReconciliationFinding(
                severity="WARN",
                code="LEARNING_OBSERVATIONS_PAYLOAD_MISSING_SCHEMA_MARKER",
                table=table,
                field="decision_payload_json",
                message=(
                    f"{raw.payload_missing_schema_marker_count} row(s) have valid "
                    "JSON decision_payload_json but no top-level schema_version key."
                ),
                impact="Payload shape cannot be versioned for affected rows.",
                sample_rows=raw.payload_missing_schema_marker_samples,
                row_count=raw.row_count,
                mismatch_count=raw.payload_missing_schema_marker_count,
            )
        )

    status = aggregate_status(f.severity for f in findings)
    check = SourceReconciliationCheckResult(
        name=name,
        status=status,
        tables=(table,),
        checked_row_count=raw.row_count,
        mismatch_count=(
            raw.canonical_missing_identity_count
            + raw.duplicate_canonical_identity_count
            + raw.invalid_payload_json_count
        ),
        summary={
            "compatibility_tagged_row_count": raw.canonical_row_count,
            "untagged_row_count": raw.legacy_row_count,
        },
    )
    return check, tuple(findings)


def evaluate_signal_forward_labels_linkage(
    raw: RawSignalForwardLabelsLinkageObservation,
) -> tuple[SourceReconciliationCheckResult, tuple[SourceReconciliationFinding, ...]]:
    """learning_outcome_labels identity + join to learning_observations."""
    table = "learning_outcome_labels"
    name = "learning_outcome_labels_identity_linkage"
    if not raw.exists:
        return _missing_table_result(name, table, "FAIL")

    if not raw.schema_sufficient:
        return _schema_insufficient_result(
            name,
            table,
            "LEARNING_OUTCOME_LABELS_SCHEMA_INSUFFICIENT",
            raw.row_count,
            raw.missing_columns,
        )

    findings: list[SourceReconciliationFinding] = []

    if raw.missing_identity_count:
        findings.append(
            SourceReconciliationFinding(
                severity="FAIL",
                code="LEARNING_OUTCOME_LABELS_MISSING_IDENTITY",
                table=table,
                field=None,
                message=(
                    f"{raw.missing_identity_count} row(s) have null/empty label_id, "
                    "observation_id, or contract_id."
                ),
                impact="Row cannot be trusted as a valid identifiable label.",
                sample_rows=raw.missing_identity_samples,
                row_count=raw.row_count,
                mismatch_count=raw.missing_identity_count,
            )
        )

    if raw.duplicate_identity_count:
        findings.append(
            SourceReconciliationFinding(
                severity="FAIL",
                code="LEARNING_OUTCOME_LABELS_DUPLICATE_IDENTITY",
                table=table,
                field=None,
                message=(
                    f"{raw.duplicate_identity_count} duplicate "
                    "(observation_id, contract_id) row(s) found."
                ),
                impact="Duplicate identity directly inflates readiness/outcome counts.",
                sample_rows=raw.duplicate_identity_samples,
                row_count=raw.row_count,
                mismatch_count=raw.duplicate_identity_count,
            )
        )

    if raw.invalid_fingerprint_json_count:
        findings.append(
            SourceReconciliationFinding(
                severity="FAIL",
                code="LEARNING_OUTCOME_LABELS_INVALID_METRICS_JSON",
                table=table,
                field="metrics_json",
                message=(
                    f"{raw.invalid_fingerprint_json_count} row(s) have "
                    "metrics_json that does not parse as valid JSON."
                ),
                impact="Label metrics cannot be read for affected rows.",
                sample_rows=raw.invalid_fingerprint_json_samples,
                row_count=raw.row_count,
                mismatch_count=raw.invalid_fingerprint_json_count,
            )
        )

    if raw.linkage_provable:
        if raw.orphan_linkage_count:
            findings.append(
                SourceReconciliationFinding(
                    severity="FAIL",
                    code="LEARNING_OUTCOME_LABELS_ORPHAN_LINKAGE",
                    table=table,
                    field="observation_id",
                    message=(
                        f"{raw.orphan_linkage_count} label row(s) reference an "
                        "observation_id with no matching learning_observations row."
                    ),
                    impact="Label cannot be traced back to its source observation.",
                    sample_rows=raw.orphan_linkage_samples,
                    row_count=raw.row_count,
                    mismatch_count=raw.orphan_linkage_count,
                )
            )
    else:
        findings.append(
            SourceReconciliationFinding(
                severity="WARN",
                code="LEARNING_OUTCOME_LABELS_LINKAGE_UNPROVABLE",
                table=table,
                field=None,
                message=(
                    "learning_observations schema does not have enough identity "
                    "columns present to prove observation linkage."
                ),
                impact=(
                    "Labels are not canonical-grade for replay/readiness linkage "
                    "until observation linkage can be proven."
                ),
            )
        )

    status = aggregate_status(f.severity for f in findings)
    check = SourceReconciliationCheckResult(
        name=name,
        status=status,
        tables=(table, "learning_observations"),
        checked_row_count=raw.row_count,
        mismatch_count=(
            raw.missing_identity_count
            + raw.duplicate_identity_count
            + raw.invalid_fingerprint_json_count
            + raw.orphan_linkage_count
        ),
        summary={"linkage_provable": raw.linkage_provable},
    )
    return check, tuple(findings)


def evaluate_market_context_snapshot_identity(
    raw: RawMarketContextSnapshotObservation,
) -> tuple[SourceReconciliationCheckResult, tuple[SourceReconciliationFinding, ...]]:
    table = "market_context_snapshots"
    name = "market_context_snapshot_identity"
    if not raw.exists:
        return _missing_table_result(name, table, "WARN")

    if not raw.schema_sufficient:
        return _schema_insufficient_result(
            name,
            table,
            "MARKET_CONTEXT_SNAPSHOT_SCHEMA_INSUFFICIENT",
            raw.row_count,
            raw.missing_columns,
        )

    findings: list[SourceReconciliationFinding] = []

    if raw.invalid_regime_count:
        findings.append(
            SourceReconciliationFinding(
                severity="FAIL",
                code="MARKET_CONTEXT_SNAPSHOT_INVALID_REGIME",
                table=table,
                field="regime",
                message=(f"{raw.invalid_regime_count} row(s) have null/empty/unknown regime."),
                impact="Regime-conditioned signal behavior cannot be trusted for these rows.",
                sample_rows=raw.invalid_regime_samples,
                row_count=raw.row_count,
                mismatch_count=raw.invalid_regime_count,
            )
        )

    if raw.duplicate_identity_count:
        findings.append(
            SourceReconciliationFinding(
                severity="WARN",
                code="MARKET_CONTEXT_SNAPSHOT_DUPLICATE_IDENTITY",
                table=table,
                field="as_of_date",
                message=f"{raw.duplicate_identity_count} duplicate as_of_date row(s) found.",
                impact="Identity is not unique for affected dates.",
                sample_rows=raw.duplicate_identity_samples,
                row_count=raw.row_count,
                mismatch_count=raw.duplicate_identity_count,
            )
        )

    if raw.missing_provenance_count:
        findings.append(
            SourceReconciliationFinding(
                severity="WARN",
                code="MARKET_CONTEXT_SNAPSHOT_MISSING_PROVENANCE",
                table=table,
                field="created_at",
                message=(f"{raw.missing_provenance_count} row(s) have null created_at."),
                impact="PIT provenance is incomplete for affected rows.",
                sample_rows=raw.missing_provenance_samples,
                row_count=raw.row_count,
                mismatch_count=raw.missing_provenance_count,
            )
        )

    if raw.invalid_factors_json_count:
        findings.append(
            SourceReconciliationFinding(
                severity="FAIL",
                code="MARKET_CONTEXT_SNAPSHOT_INVALID_FACTORS_JSON",
                table=table,
                field="factors_json",
                message=(
                    f"{raw.invalid_factors_json_count} row(s) have factors_json "
                    "that does not parse as valid JSON."
                ),
                impact="Context factor evidence cannot be read for affected rows.",
                sample_rows=raw.invalid_factors_json_samples,
                row_count=raw.row_count,
                mismatch_count=raw.invalid_factors_json_count,
            )
        )

    status = aggregate_status(f.severity for f in findings)
    check = SourceReconciliationCheckResult(
        name=name,
        status=status,
        tables=(table,),
        checked_row_count=raw.row_count,
        mismatch_count=raw.invalid_regime_count + raw.duplicate_identity_count,
        summary={},
    )
    return check, tuple(findings)


def evaluate_regime_observations_identity(
    raw: RawRegimeObservationsObservation,
) -> tuple[SourceReconciliationCheckResult, tuple[SourceReconciliationFinding, ...]]:
    table = "regime_observations"
    name = "regime_observations_identity"
    if not raw.exists:
        return _missing_table_result(name, table, "WARN")

    if not raw.schema_sufficient:
        return _schema_insufficient_result(
            name,
            table,
            "REGIME_OBSERVATIONS_SCHEMA_INSUFFICIENT",
            raw.row_count,
            raw.missing_columns,
        )

    findings: list[SourceReconciliationFinding] = []

    if raw.invalid_regime_count:
        findings.append(
            SourceReconciliationFinding(
                severity="FAIL",
                code="REGIME_OBSERVATIONS_INVALID_REGIME",
                table=table,
                field="regime",
                message=(f"{raw.invalid_regime_count} row(s) have null/empty/unknown regime."),
                impact="Signal-conditioning evidence cannot be trusted for these rows.",
                sample_rows=raw.invalid_regime_samples,
                row_count=raw.row_count,
                mismatch_count=raw.invalid_regime_count,
            )
        )

    if raw.null_confidence_or_stability_count:
        findings.append(
            SourceReconciliationFinding(
                severity="WARN",
                code="REGIME_OBSERVATIONS_NULL_CONFIDENCE_OR_STABILITY",
                table=table,
                field=None,
                message=(
                    f"{raw.null_confidence_or_stability_count} row(s) have null "
                    "regime_confidence or regime_stability."
                ),
                impact="Confidence/stability context is incomplete for affected rows.",
                row_count=raw.row_count,
                mismatch_count=raw.null_confidence_or_stability_count,
            )
        )

    if raw.duplicate_identity_count:
        findings.append(
            SourceReconciliationFinding(
                severity="WARN",
                code="REGIME_OBSERVATIONS_DUPLICATE_IDENTITY",
                table=table,
                field="observation_date",
                message=(
                    f"{raw.duplicate_identity_count} duplicate observation_date row(s) found."
                ),
                impact="Identity is not unique for affected dates.",
                sample_rows=raw.duplicate_identity_samples,
                row_count=raw.row_count,
                mismatch_count=raw.duplicate_identity_count,
            )
        )

    if raw.invalid_detection_inputs_json_count:
        findings.append(
            SourceReconciliationFinding(
                severity="FAIL",
                code="REGIME_OBSERVATIONS_INVALID_DETECTION_INPUTS_JSON",
                table=table,
                field="detection_inputs_json",
                message=(
                    f"{raw.invalid_detection_inputs_json_count} row(s) have "
                    "detection_inputs_json that does not parse as valid JSON."
                ),
                impact="Deterministic-replay input fingerprint cannot be read for affected rows.",
                sample_rows=raw.invalid_detection_inputs_json_samples,
                row_count=raw.row_count,
                mismatch_count=raw.invalid_detection_inputs_json_count,
            )
        )

    status = aggregate_status(f.severity for f in findings)
    check = SourceReconciliationCheckResult(
        name=name,
        status=status,
        tables=(table,),
        checked_row_count=raw.row_count,
        mismatch_count=raw.invalid_regime_count + raw.duplicate_identity_count,
        summary={},
    )
    return check, tuple(findings)


def evaluate_learning_observations_risk_pit(
    raw: RawLearningObservationsRiskPitObservation,
) -> tuple[SourceReconciliationCheckResult, tuple[SourceReconciliationFinding, ...]]:
    """PIT check: ACCUMULATION_DISCOVERY risk.snapshot_date vs session_date.

    FAIL when risk snapshot is strictly later than the observation session
    (look-ahead contamination). WARN for gate_context mismatch and unreadable
    risk date fields. Missing table is WARN so non-learning DBs stay usable.
    """
    table = "learning_observations"
    name = "learning_observations_risk_pit"
    if not raw.exists:
        return _missing_table_result(name, table, "WARN")

    if not raw.schema_sufficient:
        return _schema_insufficient_result(
            name,
            table,
            "LEARNING_OBSERVATIONS_SCHEMA_INSUFFICIENT",
            raw.row_count,
            raw.missing_columns,
        )

    findings: list[SourceReconciliationFinding] = []

    if raw.risk_snapshot_after_session_count:
        findings.append(
            SourceReconciliationFinding(
                severity="FAIL",
                code="LEARNING_OBSERVATIONS_RISK_SNAPSHOT_AFTER_SESSION",
                table=table,
                field="decision_payload_json.risk.snapshot_date",
                message=(
                    f"{raw.risk_snapshot_after_session_count} ACCUMULATION_DISCOVERY "
                    "observation(s) have risk.snapshot_date later than session_date "
                    "(point-in-time look-ahead on the risk path)."
                ),
                impact=(
                    "Historical risk verdicts used future candles; corpus is not "
                    "point-in-time safe for risk/replay/tuning claims."
                ),
                sample_rows=raw.risk_snapshot_after_session_samples,
                row_count=raw.row_count,
                mismatch_count=raw.risk_snapshot_after_session_count,
            )
        )

    if raw.gate_context_session_mismatch_count:
        findings.append(
            SourceReconciliationFinding(
                severity="WARN",
                code="LEARNING_OBSERVATIONS_GATE_CONTEXT_SESSION_MISMATCH",
                table=table,
                field="decision_payload_json.risk.gate_context.snapshot_date",
                message=(
                    f"{raw.gate_context_session_mismatch_count} ACCUMULATION_DISCOVERY "
                    "observation(s) have risk.gate_context.snapshot_date disagreeing "
                    "with session_date."
                ),
                impact=(
                    "Gate-context session stamp is inconsistent with the observation "
                    "session; inspect capture wiring."
                ),
                sample_rows=raw.gate_context_session_mismatch_samples,
                row_count=raw.row_count,
                mismatch_count=raw.gate_context_session_mismatch_count,
            )
        )

    if raw.risk_snapshot_unreadable_count:
        findings.append(
            SourceReconciliationFinding(
                severity="WARN",
                code="LEARNING_OBSERVATIONS_RISK_SNAPSHOT_UNREADABLE",
                table=table,
                field="decision_payload_json",
                message=(
                    f"{raw.risk_snapshot_unreadable_count} ACCUMULATION_DISCOVERY "
                    "observation(s) have an unreadable risk snapshot date "
                    "(invalid JSON, missing session_date, or risk present without "
                    "parseable snapshot_date)."
                ),
                impact=(
                    "PIT coherence cannot be proven for affected rows; treat as "
                    "unverified rather than clean."
                ),
                sample_rows=raw.risk_snapshot_unreadable_samples,
                row_count=raw.row_count,
                mismatch_count=raw.risk_snapshot_unreadable_count,
            )
        )

    status = aggregate_status(f.severity for f in findings)
    check = SourceReconciliationCheckResult(
        name=name,
        status=status,
        tables=(table,),
        checked_row_count=raw.row_count,
        mismatch_count=raw.risk_snapshot_after_session_count,
        summary={
            "risk_snapshot_after_session_count": raw.risk_snapshot_after_session_count,
            "gate_context_session_mismatch_count": raw.gate_context_session_mismatch_count,
            "risk_snapshot_unreadable_count": raw.risk_snapshot_unreadable_count,
        },
    )
    return check, tuple(findings)
