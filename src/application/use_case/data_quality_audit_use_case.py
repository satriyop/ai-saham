"""
Deterministic local data-quality audit.

Layer: Application
AI usage: None
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass(frozen=True)
class DataQualityTableSnapshot:
    table: str
    rows: int
    tickers: int
    latest: date | None
    stale_tickers: int = 0
    missing_tickers: int = 0


@dataclass(frozen=True)
class DataQualityRawSnapshot:
    database_exists: bool
    expected_trading_day: date | None
    candles: DataQualityTableSnapshot | None
    broker_summaries_idx: DataQualityTableSnapshot | None
    foreign_flow_stockbit: DataQualityTableSnapshot | None
    broker_daily_flow_stockbit: DataQualityTableSnapshot | None
    stockbit_summary_rows: int
    unsafe_broker_summary_rows: int
    bad_candle_rows: int
    candle_source_columns_present: bool
    unknown_candle_provenance_rows: int
    enrichment_tables: tuple[DataQualityTableSnapshot, ...] = ()


class DataQualityAuditReader(Protocol):
    """Read-only input source for data-quality audit."""

    def load_snapshot(self, tickers: list[str] | None = None) -> DataQualityRawSnapshot:
        """Return database snapshot used by the audit policy."""


@dataclass(frozen=True)
class DataQualityIssue:
    severity: str  # "fail" | "warn" | "info"
    code: str
    message: str
    impact: str


@dataclass(frozen=True)
class DataQualityAuditResponse:
    status: str  # "pass" | "warn" | "fail"
    expected_trading_day: date | None
    core_tables: tuple[DataQualityTableSnapshot, ...]
    enrichment_tables: tuple[DataQualityTableSnapshot, ...]
    issues: tuple[DataQualityIssue, ...]

    @property
    def fail_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "fail")

    @property
    def warn_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "warn")


@dataclass(frozen=True)
class DataQualityAuditRequest:
    tickers: list[str] | None = None


class DataQualityAuditUseCase:
    """Evaluate local data quality from a deterministic read model."""

    def __init__(self, reader: DataQualityAuditReader) -> None:
        self._reader = reader

    def execute(self, request: DataQualityAuditRequest) -> DataQualityAuditResponse:
        tickers = [t.upper().strip() for t in request.tickers or [] if t.strip()]
        snapshot = self._reader.load_snapshot(tickers=tickers or None)
        issues: list[DataQualityIssue] = []

        if not snapshot.database_exists:
            return DataQualityAuditResponse(
                status="fail",
                expected_trading_day=None,
                core_tables=(),
                enrichment_tables=(),
                issues=(
                    DataQualityIssue(
                        severity="fail",
                        code="MISSING_DATABASE",
                        message="SQLite database does not exist.",
                        impact="Run a fetch command before relying on local analysis.",
                    ),
                ),
            )

        core_tables = tuple(
            table for table in (
                snapshot.candles,
                snapshot.broker_summaries_idx,
                snapshot.foreign_flow_stockbit,
                snapshot.broker_daily_flow_stockbit,
            )
            if table is not None
        )

        for table in (snapshot.candles, snapshot.broker_summaries_idx):
            if table is None or table.rows == 0:
                issues.append(
                    DataQualityIssue(
                        severity="fail",
                        code=f"MISSING_{(table.table if table else 'CORE').upper()}",
                        message="Required core market/broker data is missing.",
                        impact="Ranking and analysis commands may be incomplete.",
                    )
                )
                continue
            if (
                snapshot.expected_trading_day
                and table.latest
                and table.latest < snapshot.expected_trading_day
            ):
                issues.append(
                    DataQualityIssue(
                        severity="warn",
                        code=f"STALE_{table.table.upper()}",
                        message=(
                            f"{table.table} latest date {table.latest} is before "
                            f"expected trading day {snapshot.expected_trading_day}."
                        ),
                        impact="Candidates can be ranked using stale inputs.",
                    )
                )
            if table.stale_tickers > 0:
                issues.append(
                    DataQualityIssue(
                        severity="warn",
                        code=f"PARTIAL_STALE_{table.table.upper()}",
                        message=f"{table.stale_tickers} ticker(s) have stale {table.table} rows.",
                        impact="Fresh and stale tickers may be compared together.",
                    )
                )

        if snapshot.bad_candle_rows > 0:
            issues.append(
                DataQualityIssue(
                    severity="fail",
                    code="BAD_CANDLE_OHLC",
                    message=(
                        f"{snapshot.bad_candle_rows} candle row(s) have invalid "
                        "OHLC/volume values."
                    ),
                    impact="Indicators using those rows are not reliable.",
                )
            )

        if not snapshot.candle_source_columns_present:
            issues.append(
                DataQualityIssue(
                    severity="warn",
                    code="MISSING_CANDLE_PROVENANCE",
                    message="candles table has no source/unit provenance columns.",
                    impact="Yahoo shares and IDX lots cannot be audited after persistence.",
                )
            )
        elif snapshot.unknown_candle_provenance_rows > 0:
            issues.append(
                DataQualityIssue(
                    severity="warn",
                    code="UNKNOWN_CANDLE_PROVENANCE",
                    message=(
                        f"{snapshot.unknown_candle_provenance_rows} candle row(s) "
                        "have unknown source/unit provenance."
                    ),
                    impact=(
                        "Legacy rows may still mix Yahoo shares and IDX lots until "
                        "they are refreshed."
                    ),
                )
            )

        if snapshot.stockbit_summary_rows > 0:
            issues.append(
                DataQualityIssue(
                    severity="warn",
                    code="DEGRADED_STOCKBIT_SUMMARIES",
                    message=(
                        f"{snapshot.stockbit_summary_rows} Stockbit broker summary "
                        "row(s) remain."
                    ),
                    impact=(
                        "Stockbit summary total_value is synthetic; prefer IDX for "
                        "aggregate flow."
                    ),
                )
            )

        if snapshot.unsafe_broker_summary_rows > 0:
            issues.append(
                DataQualityIssue(
                    severity="warn",
                    code="UNSAFE_BROKER_DENOMINATOR",
                    message=(
                        f"{snapshot.unsafe_broker_summary_rows} broker summary row(s) "
                        "have non-positive total value or invalid lots."
                    ),
                    impact="FLOW% denominators can be unsafe unless those rows are excluded.",
                )
            )

        for table in snapshot.enrichment_tables:
            if table.rows == 0:
                issues.append(
                    DataQualityIssue(
                        severity="info",
                        code=f"EMPTY_{table.table.upper()}",
                        message=f"{table.table} has no rows.",
                        impact="Related context should be displayed as missing, not neutral.",
                    )
                )
            elif table.missing_tickers > 0:
                issues.append(
                    DataQualityIssue(
                        severity="info",
                        code=f"PARTIAL_{table.table.upper()}",
                        message=f"{table.table} is missing {table.missing_tickers} ticker(s).",
                        impact="Enrichment coverage is uneven across candidates.",
                    )
                )

        status = "fail" if any(i.severity == "fail" for i in issues) else (
            "warn" if any(i.severity == "warn" for i in issues) else "pass"
        )
        return DataQualityAuditResponse(
            status=status,
            expected_trading_day=snapshot.expected_trading_day,
            core_tables=core_tables,
            enrichment_tables=snapshot.enrichment_tables,
            issues=tuple(issues),
        )
