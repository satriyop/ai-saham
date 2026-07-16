"""
Read-only executable source reconciliation audit (DQ-001B).

Proves OHLC/arithmetic invariants, identity uniqueness, and cross-table
foreign-flow overlaps for core market/broker tables. Never repairs,
quarantines, or mutates data — read-only findings only.

Layer: Application
AI usage: None
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Protocol

_STATUS_ORDER = {"PASS": 0, "INFO": 0, "WARN": 1, "FAIL": 2}


def _worse(a: str, b: str) -> str:
    return b if _STATUS_ORDER.get(b, 0) > _STATUS_ORDER.get(a, 0) else a


def _aggregate_status(values: Iterable[str]) -> str:
    status = "PASS"
    for value in values:
        if value in ("FAIL", "WARN"):
            status = _worse(status, value)
    return status


_MAX_SAMPLE_ROWS = 10


@dataclass(frozen=True)
class SourceReconciliationFinding:
    severity: str  # "FAIL" | "WARN" | "INFO"
    code: str
    table: str
    field: str | None
    message: str
    impact: str
    sample_rows: tuple[dict, ...] = ()
    row_count: int | None = None
    mismatch_count: int | None = None

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "code": self.code,
            "table": self.table,
            "field": self.field,
            "message": self.message,
            "impact": self.impact,
            "sample_rows": [dict(r) for r in self.sample_rows[:_MAX_SAMPLE_ROWS]],
            "row_count": self.row_count,
            "mismatch_count": self.mismatch_count,
        }


@dataclass(frozen=True)
class SourceReconciliationCheckResult:
    name: str
    status: str  # "PASS" | "WARN" | "FAIL"
    tables: tuple[str, ...]
    checked_row_count: int | None
    mismatch_count: int | None
    summary: dict

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "tables": list(self.tables),
            "checked_row_count": self.checked_row_count,
            "mismatch_count": self.mismatch_count,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class AuditSourceReconciliationResponse:
    artifact_type: str
    schema_version: int
    generated_at: str
    status: str  # "PASS" | "WARN" | "FAIL"
    checks: tuple[SourceReconciliationCheckResult, ...]
    findings: tuple[SourceReconciliationFinding, ...]

    def to_dict(self) -> dict:
        return {
            "artifact_type": self.artifact_type,
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "status": self.status,
            "checks": [c.to_dict() for c in self.checks],
            "findings": [f.to_dict() for f in self.findings],
        }


@dataclass(frozen=True)
class RawCandlesOhlcObservation:
    exists: bool
    row_count: int = 0
    identity_columns_present: bool = True
    price_columns_present: bool = True
    volume_column_present: bool = True
    invalid_ohlc_count: int = 0
    invalid_ohlc_samples: tuple[dict, ...] = ()
    negative_volume_count: int = 0
    negative_volume_samples: tuple[dict, ...] = ()
    unknown_provenance_count: int = 0
    unknown_provenance_samples: tuple[dict, ...] = ()
    source_distribution: dict = field(default_factory=dict)
    volume_unit_distribution: dict = field(default_factory=dict)
    price_adjustment_policy_distribution: dict = field(default_factory=dict)


@dataclass(frozen=True)
class RawBrokerSummariesObservation:
    exists: bool
    row_count: int = 0
    identity_columns_present: bool = True
    value_columns_present: bool = True
    negative_value_count: int = 0
    negative_value_samples: tuple[dict, ...] = ()
    duplicate_identity_count: int = 0
    duplicate_identity_samples: tuple[dict, ...] = ()


@dataclass(frozen=True)
class RawBrokerDailyFlowObservation:
    exists: bool
    row_count: int = 0
    identity_columns_present: bool = True
    value_columns_present: bool = True
    negative_value_count: int = 0
    negative_value_samples: tuple[dict, ...] = ()
    net_mismatch_count: int = 0
    net_mismatch_samples: tuple[dict, ...] = ()
    duplicate_identity_count: int = 0
    duplicate_identity_samples: tuple[dict, ...] = ()
    broker_code_count_min: int | None = None
    broker_code_count_max: int | None = None
    broker_code_count_avg: float | None = None
    distinct_broker_code_total: int | None = None


@dataclass(frozen=True)
class RawForeignFlowReconciliationObservation:
    foreign_flow_points_exists: bool
    foreign_flow_points_schema_sufficient: bool
    total_row_count: int = 0
    matched_row_count: int = 0
    unmatched_row_count: int = 0
    mismatch_count: int = 0
    mismatch_samples: tuple[dict, ...] = ()
    foreign_flow_snapshots_exists: bool = False


class SourceReconciliationReader(Protocol):
    """Read-only observer of reconciliation facts. Must never mutate the database."""

    def database_exists(self) -> bool: ...

    def observe_candles_ohlc(self) -> RawCandlesOhlcObservation: ...

    def observe_broker_summaries(self) -> RawBrokerSummariesObservation: ...

    def observe_broker_daily_flow(self) -> RawBrokerDailyFlowObservation: ...

    def observe_foreign_flow_reconciliation(self) -> RawForeignFlowReconciliationObservation: ...


class AuditSourceReconciliationUseCase:
    """Evaluate executable source reconciliation checks for core tables (DQ-001B)."""

    _ARTIFACT_TYPE = "source_reconciliation_audit"
    _SCHEMA_VERSION = 1

    def __init__(
        self,
        reader: SourceReconciliationReader,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._reader = reader
        self._clock = clock or _default_clock

    def execute(self) -> AuditSourceReconciliationResponse:
        if not self._reader.database_exists():
            finding = SourceReconciliationFinding(
                severity="FAIL",
                code="DATABASE_MISSING",
                table="",
                field=None,
                message="SQLite database does not exist.",
                impact="No source reconciliation can be performed.",
            )
            return AuditSourceReconciliationResponse(
                artifact_type=self._ARTIFACT_TYPE,
                schema_version=self._SCHEMA_VERSION,
                generated_at=self._clock(),
                status="FAIL",
                checks=(),
                findings=(finding,),
            )

        checks: list[SourceReconciliationCheckResult] = []
        findings: list[SourceReconciliationFinding] = []

        check, check_findings = self._evaluate_candles_ohlc(self._reader.observe_candles_ohlc())
        checks.append(check)
        findings.extend(check_findings)

        check, check_findings = self._evaluate_broker_summaries(
            self._reader.observe_broker_summaries()
        )
        checks.append(check)
        findings.extend(check_findings)

        check, check_findings = self._evaluate_broker_daily_flow(
            self._reader.observe_broker_daily_flow()
        )
        checks.append(check)
        findings.extend(check_findings)

        check, check_findings = self._evaluate_foreign_flow_reconciliation(
            self._reader.observe_foreign_flow_reconciliation()
        )
        checks.append(check)
        findings.extend(check_findings)

        status = _aggregate_status(c.status for c in checks)
        return AuditSourceReconciliationResponse(
            artifact_type=self._ARTIFACT_TYPE,
            schema_version=self._SCHEMA_VERSION,
            generated_at=self._clock(),
            status=status,
            checks=tuple(checks),
            findings=tuple(findings),
        )

    def _missing_table_result(
        self, name: str, table: str
    ) -> tuple[SourceReconciliationCheckResult, tuple[SourceReconciliationFinding, ...]]:
        finding = SourceReconciliationFinding(
            severity="FAIL",
            code="MISSING_TABLE",
            table=table,
            field=None,
            message=f"{table} does not exist.",
            impact="Reconciliation cannot be performed for this table.",
        )
        check = SourceReconciliationCheckResult(
            name=name,
            status="FAIL",
            tables=(table,),
            checked_row_count=None,
            mismatch_count=None,
            summary={},
        )
        return check, (finding,)

    def _schema_insufficient_result(
        self, name: str, table: str, code: str, row_count: int, message: str
    ) -> tuple[SourceReconciliationCheckResult, tuple[SourceReconciliationFinding, ...]]:
        finding = SourceReconciliationFinding(
            severity="FAIL",
            code=code,
            table=table,
            field=None,
            message=message,
            impact="Arithmetic/identity reconciliation cannot be performed for this table.",
            row_count=row_count,
        )
        check = SourceReconciliationCheckResult(
            name=name,
            status="FAIL",
            tables=(table,),
            checked_row_count=row_count,
            mismatch_count=None,
            summary={},
        )
        return check, (finding,)

    def _evaluate_candles_ohlc(
        self, raw: RawCandlesOhlcObservation
    ) -> tuple[SourceReconciliationCheckResult, tuple[SourceReconciliationFinding, ...]]:
        if not raw.exists:
            return self._missing_table_result("candles_ohlc_invariants", "candles")

        if (
            not raw.identity_columns_present
            or not raw.price_columns_present
            or not raw.volume_column_present
        ):
            return self._schema_insufficient_result(
                name="candles_ohlc_invariants",
                table="candles",
                code="CANDLES_SCHEMA_INSUFFICIENT",
                row_count=raw.row_count,
                message=(
                    "candles is missing required identity, OHLC, or volume "
                    "columns (ticker, date, open, high, low, close, volume)."
                ),
            )

        findings: list[SourceReconciliationFinding] = []

        if raw.invalid_ohlc_count:
            findings.append(
                SourceReconciliationFinding(
                    severity="FAIL",
                    code="INVALID_OHLC_INVARIANT",
                    table="candles",
                    field=None,
                    message=(
                        f"{raw.invalid_ohlc_count} candle row(s) violate OHLC "
                        "invariants (high/low bounds)."
                    ),
                    impact="Indicators computed from these rows are unreliable.",
                    sample_rows=raw.invalid_ohlc_samples,
                    row_count=raw.row_count,
                    mismatch_count=raw.invalid_ohlc_count,
                )
            )

        if raw.negative_volume_count:
            findings.append(
                SourceReconciliationFinding(
                    severity="FAIL",
                    code="NEGATIVE_CANDLE_VOLUME",
                    table="candles",
                    field="volume",
                    message=f"{raw.negative_volume_count} candle row(s) have negative volume.",
                    impact="Volume-based indicators are unreliable for affected rows.",
                    sample_rows=raw.negative_volume_samples,
                    row_count=raw.row_count,
                    mismatch_count=raw.negative_volume_count,
                )
            )

        if raw.unknown_provenance_count:
            findings.append(
                SourceReconciliationFinding(
                    severity="WARN",
                    code="UNKNOWN_CANDLE_PROVENANCE",
                    table="candles",
                    field=None,
                    message=(
                        f"{raw.unknown_provenance_count} candle row(s) have null/empty/"
                        "unknown source, volume_unit, or price_adjustment_policy."
                    ),
                    impact="Cross-source volume/price comparisons are unsafe for these rows.",
                    sample_rows=raw.unknown_provenance_samples,
                    row_count=raw.row_count,
                    mismatch_count=raw.unknown_provenance_count,
                )
            )

        status = _aggregate_status(f.severity for f in findings)
        total_mismatch = (
            raw.invalid_ohlc_count + raw.negative_volume_count + raw.unknown_provenance_count
        )
        check = SourceReconciliationCheckResult(
            name="candles_ohlc_invariants",
            status=status,
            tables=("candles",),
            checked_row_count=raw.row_count,
            mismatch_count=total_mismatch,
            summary={
                "source_distribution": raw.source_distribution,
                "volume_unit_distribution": raw.volume_unit_distribution,
                "price_adjustment_policy_distribution": raw.price_adjustment_policy_distribution,
            },
        )
        return check, tuple(findings)

    def _evaluate_broker_summaries(
        self, raw: RawBrokerSummariesObservation
    ) -> tuple[SourceReconciliationCheckResult, tuple[SourceReconciliationFinding, ...]]:
        if not raw.exists:
            return self._missing_table_result(
                "broker_summaries_arithmetic_identity", "broker_summaries"
            )

        if not raw.identity_columns_present or not raw.value_columns_present:
            return self._schema_insufficient_result(
                name="broker_summaries_arithmetic_identity",
                table="broker_summaries",
                code="BROKER_SUMMARY_SCHEMA_INSUFFICIENT",
                row_count=raw.row_count,
                message=(
                    "broker_summaries is missing required identity or value "
                    "columns (ticker, date, source, foreign_buy_value, "
                    "foreign_sell_value, foreign_buy_lot, foreign_sell_lot, "
                    "total_value)."
                ),
            )

        findings: list[SourceReconciliationFinding] = []

        if raw.negative_value_count:
            findings.append(
                SourceReconciliationFinding(
                    severity="FAIL",
                    code="NEGATIVE_BROKER_SUMMARY_VALUE",
                    table="broker_summaries",
                    field=None,
                    message=(
                        f"{raw.negative_value_count} broker_summaries row(s) have "
                        "negative value/lot fields."
                    ),
                    impact="Foreign flow arithmetic is unreliable for affected rows.",
                    sample_rows=raw.negative_value_samples,
                    row_count=raw.row_count,
                    mismatch_count=raw.negative_value_count,
                )
            )

        if raw.duplicate_identity_count:
            findings.append(
                SourceReconciliationFinding(
                    severity="FAIL",
                    code="DUPLICATE_BROKER_SUMMARY_IDENTITY",
                    table="broker_summaries",
                    field=None,
                    message=(
                        f"{raw.duplicate_identity_count} duplicate (ticker, date, source) "
                        "row(s) found in broker_summaries."
                    ),
                    impact="Identity is not unique; aggregates may double-count.",
                    sample_rows=raw.duplicate_identity_samples,
                    row_count=raw.row_count,
                    mismatch_count=raw.duplicate_identity_count,
                )
            )

        status = _aggregate_status(f.severity for f in findings)
        total_mismatch = raw.negative_value_count + raw.duplicate_identity_count
        check = SourceReconciliationCheckResult(
            name="broker_summaries_arithmetic_identity",
            status=status,
            tables=("broker_summaries",),
            checked_row_count=raw.row_count,
            mismatch_count=total_mismatch,
            summary={
                "derived_foreign_net_formula": "foreign_buy_value - foreign_sell_value",
            },
        )
        return check, tuple(findings)

    def _evaluate_broker_daily_flow(
        self, raw: RawBrokerDailyFlowObservation
    ) -> tuple[SourceReconciliationCheckResult, tuple[SourceReconciliationFinding, ...]]:
        if not raw.exists:
            return self._missing_table_result(
                "broker_daily_flow_arithmetic_scope", "broker_daily_flow"
            )

        if not raw.identity_columns_present or not raw.value_columns_present:
            return self._schema_insufficient_result(
                name="broker_daily_flow_arithmetic_scope",
                table="broker_daily_flow",
                code="TRACKED_BROKER_SCHEMA_INSUFFICIENT",
                row_count=raw.row_count,
                message=(
                    "broker_daily_flow is missing required identity or value "
                    "columns (ticker, date, broker_code, source, buy_value, "
                    "sell_value, net_value)."
                ),
            )

        findings: list[SourceReconciliationFinding] = []

        if raw.negative_value_count:
            findings.append(
                SourceReconciliationFinding(
                    severity="FAIL",
                    code="NEGATIVE_TRACKED_BROKER_VALUE",
                    table="broker_daily_flow",
                    field=None,
                    message=(
                        f"{raw.negative_value_count} broker_daily_flow row(s) have "
                        "negative buy_value/sell_value."
                    ),
                    impact="Tracked broker arithmetic is unreliable for affected rows.",
                    sample_rows=raw.negative_value_samples,
                    row_count=raw.row_count,
                    mismatch_count=raw.negative_value_count,
                )
            )

        if raw.net_mismatch_count:
            findings.append(
                SourceReconciliationFinding(
                    severity="FAIL",
                    code="TRACKED_BROKER_NET_MISMATCH",
                    table="broker_daily_flow",
                    field="net_value",
                    message=(
                        f"{raw.net_mismatch_count} broker_daily_flow row(s) have "
                        "net_value != buy_value - sell_value."
                    ),
                    impact="Stored net_value cannot be trusted for affected rows.",
                    sample_rows=raw.net_mismatch_samples,
                    row_count=raw.row_count,
                    mismatch_count=raw.net_mismatch_count,
                )
            )

        if raw.duplicate_identity_count:
            findings.append(
                SourceReconciliationFinding(
                    severity="FAIL",
                    code="DUPLICATE_TRACKED_BROKER_FLOW_IDENTITY",
                    table="broker_daily_flow",
                    field=None,
                    message=(
                        f"{raw.duplicate_identity_count} duplicate (ticker, date, "
                        "broker_code, source) row(s) found in broker_daily_flow."
                    ),
                    impact="Identity is not unique; aggregates may double-count.",
                    sample_rows=raw.duplicate_identity_samples,
                    row_count=raw.row_count,
                    mismatch_count=raw.duplicate_identity_count,
                )
            )

        findings.append(
            SourceReconciliationFinding(
                severity="INFO",
                code="TRACKED_BROKER_SUBSET_NOT_FULL_MARKET",
                table="broker_daily_flow",
                field=None,
                message="broker_daily_flow captures tracked broker codes only.",
                impact=(
                    "broker_daily_flow is a tracked broker subset and must not be used "
                    "as full broker composition."
                ),
            )
        )

        status = _aggregate_status(f.severity for f in findings)
        total_mismatch = (
            raw.negative_value_count + raw.net_mismatch_count + raw.duplicate_identity_count
        )
        check = SourceReconciliationCheckResult(
            name="broker_daily_flow_arithmetic_scope",
            status=status,
            tables=("broker_daily_flow",),
            checked_row_count=raw.row_count,
            mismatch_count=total_mismatch,
            summary={
                "broker_code_count_per_ticker_date": {
                    "min": raw.broker_code_count_min,
                    "max": raw.broker_code_count_max,
                    "avg": raw.broker_code_count_avg,
                },
                "distinct_broker_code_total": raw.distinct_broker_code_total,
            },
        )
        return check, tuple(findings)

    def _evaluate_foreign_flow_reconciliation(
        self, raw: RawForeignFlowReconciliationObservation
    ) -> tuple[SourceReconciliationCheckResult, tuple[SourceReconciliationFinding, ...]]:
        findings: list[SourceReconciliationFinding] = []
        tables = ["broker_summaries"]

        if not raw.foreign_flow_points_exists:
            findings.append(
                SourceReconciliationFinding(
                    severity="WARN",
                    code="FOREIGN_FLOW_POINTS_UNRECONCILABLE_SCHEMA",
                    table="foreign_flow_points",
                    field=None,
                    message="foreign_flow_points table does not exist.",
                    impact="Cannot cross-check foreign_flow_points against broker_summaries.",
                )
            )
        else:
            tables.append("foreign_flow_points")
            if not raw.foreign_flow_points_schema_sufficient:
                findings.append(
                    SourceReconciliationFinding(
                        severity="WARN",
                        code="FOREIGN_FLOW_POINTS_UNRECONCILABLE_SCHEMA",
                        table="foreign_flow_points",
                        field=None,
                        message=(
                            "foreign_flow_points schema does not have the fields needed "
                            "to prove equivalence with broker_summaries."
                        ),
                        impact="Cannot cross-check foreign_flow_points against broker_summaries.",
                    )
                )
            elif raw.matched_row_count == 0:
                findings.append(
                    SourceReconciliationFinding(
                        severity="WARN",
                        code="FOREIGN_FLOW_POINTS_UNRECONCILABLE_SCHEMA",
                        table="foreign_flow_points",
                        field=None,
                        message=(
                            "No overlapping same-source (ticker, date, source) rows found "
                            "between foreign_flow_points and broker_summaries; nothing "
                            "could be cross-checked."
                        ),
                        impact="Cannot cross-check foreign_flow_points against broker_summaries.",
                    )
                )
            else:
                if raw.mismatch_count:
                    findings.append(
                        SourceReconciliationFinding(
                            severity="FAIL",
                            code="FOREIGN_FLOW_RECONCILIATION_MISMATCH",
                            table="foreign_flow_points",
                            field="net_val",
                            message=(
                                f"{raw.mismatch_count} foreign_flow_points row(s) differ "
                                "from derived broker_summaries.foreign_buy_value - "
                                "foreign_sell_value by more than 1.0 IDR."
                            ),
                            impact=(
                                "foreign_flow_points net_val cannot be trusted as "
                                "equivalent to broker_summaries for affected same-source "
                                "rows."
                            ),
                            sample_rows=raw.mismatch_samples,
                            row_count=raw.matched_row_count,
                            mismatch_count=raw.mismatch_count,
                        )
                    )

                if raw.unmatched_row_count:
                    findings.append(
                        SourceReconciliationFinding(
                            severity="WARN",
                            code="FOREIGN_FLOW_POINTS_PARTIAL_COVERAGE",
                            table="foreign_flow_points",
                            field=None,
                            message=(
                                f"{raw.unmatched_row_count} of {raw.total_row_count} "
                                "foreign_flow_points row(s) have no matching same-source "
                                "(ticker, date, source) row in broker_summaries and were "
                                "not cross-checked (commonly a different provider, e.g. "
                                "stockbit, with no idx-source broker_summaries "
                                "counterpart)."
                            ),
                            impact=(
                                "Reconciliation only covers the "
                                f"{raw.matched_row_count} matched row(s); PASS/FAIL does "
                                "not attest to the unmatched rows."
                            ),
                            row_count=raw.total_row_count,
                            mismatch_count=raw.unmatched_row_count,
                        )
                    )

        if raw.foreign_flow_snapshots_exists:
            tables.append("foreign_flow_snapshots")
            findings.append(
                SourceReconciliationFinding(
                    severity="INFO",
                    code="FOREIGN_FLOW_SNAPSHOTS_AGGREGATED_NOT_DIRECT_DAILY",
                    table="foreign_flow_snapshots",
                    field=None,
                    message="foreign_flow_snapshots is windowed/aggregated, not daily.",
                    impact=(
                        "foreign_flow_snapshots is not directly comparable to daily "
                        "broker_summaries rows; do not reconcile as if equivalent."
                    ),
                )
            )

        status = _aggregate_status(f.severity for f in findings)
        check = SourceReconciliationCheckResult(
            name="foreign_flow_reconciliation",
            status=status,
            tables=tuple(tables),
            checked_row_count=raw.matched_row_count if raw.foreign_flow_points_exists else None,
            mismatch_count=raw.mismatch_count if raw.foreign_flow_points_exists else None,
            summary={
                "tolerance_idr": 1.0,
                "reconciliation_formula": (
                    "foreign_flow_points.net_val == broker_summaries.foreign_buy_value "
                    "- broker_summaries.foreign_sell_value (same ticker/date/source only)"
                ),
                "foreign_flow_points_total_rows": (
                    raw.total_row_count if raw.foreign_flow_points_exists else None
                ),
                "foreign_flow_points_matched_rows": (
                    raw.matched_row_count if raw.foreign_flow_points_exists else None
                ),
                "foreign_flow_points_unmatched_rows": (
                    raw.unmatched_row_count if raw.foreign_flow_points_exists else None
                ),
            },
        )
        return check, tuple(findings)


def _default_clock() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
