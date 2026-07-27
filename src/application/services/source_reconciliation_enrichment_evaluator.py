"""
Pure evaluation policy for DQ-001D enrichment/source-context reconciliation
checks. Takes read-only Raw*Observation facts and turns them into
CheckResult/Finding DTOs — no I/O, no SQL, no field-contract duplication
(DQ-001C already reports per-field nulls; this reports table-level
reconciliation/invariant issues).

Layer: Application
AI usage: None
"""

from __future__ import annotations

from src.application.dto.source_reconciliation_dto import (
    RawCorporateActionLinkageObservation,
    RawInsiderCacheObservation,
    RawPitCacheObservation,
    RawSeasonalityObservation,
    RawStockMetaObservation,
    RawTickerNotationObservation,
    SourceReconciliationCheckResult,
    SourceReconciliationFinding,
    aggregate_status,
)

_MISSING_TABLE_IMPACT = "Reconciliation cannot be performed for this table."


def _missing_enrichment_table_result(
    name: str, table: str
) -> tuple[SourceReconciliationCheckResult, tuple[SourceReconciliationFinding, ...]]:
    finding = SourceReconciliationFinding(
        severity="WARN",
        code="MISSING_ENRICHMENT_TABLE",
        table=table,
        field=None,
        message=f"{table} does not exist.",
        impact=_MISSING_TABLE_IMPACT,
    )
    check = SourceReconciliationCheckResult(
        name=name,
        status="WARN",
        tables=(table,),
        checked_row_count=None,
        mismatch_count=None,
        summary={},
    )
    return check, (finding,)


def _empty_table_finding(table: str) -> SourceReconciliationFinding:
    return SourceReconciliationFinding(
        severity="INFO",
        code="ENRICHMENT_TABLE_EMPTY",
        table=table,
        field=None,
        message=f"{table} exists but has zero rows.",
        impact="No reconciliation could be performed; coverage is currently empty.",
        row_count=0,
    )


def _schema_insufficient_result(
    name: str,
    table: str,
    code: str,
    row_count: int,
    missing_columns: tuple[str, ...],
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


def evaluate_seasonality(
    raw: RawSeasonalityObservation,
) -> tuple[SourceReconciliationCheckResult, tuple[SourceReconciliationFinding, ...]]:
    table = "seasonality_cache"
    if not raw.exists:
        return _missing_enrichment_table_result("seasonality_provenance_consistency", table)

    if not raw.schema_sufficient:
        return _schema_insufficient_result(
            "seasonality_provenance_consistency",
            table,
            "SEASONALITY_SCHEMA_INSUFFICIENT",
            raw.row_count,
            raw.missing_columns,
        )

    findings: list[SourceReconciliationFinding] = []

    if raw.row_count == 0:
        findings.append(_empty_table_finding(table))

    if raw.invalid_source_count:
        findings.append(
            SourceReconciliationFinding(
                severity="FAIL",
                code="SEASONALITY_INVALID_SOURCE",
                table=table,
                field="source",
                message=(
                    f"{raw.invalid_source_count} seasonality_cache row(s) have "
                    "null/empty/unknown source."
                ),
                impact="Provenance cannot be trusted for affected rows.",
                sample_rows=raw.invalid_source_samples,
                row_count=raw.row_count,
                mismatch_count=raw.invalid_source_count,
            )
        )

    if raw.null_fetched_at_count:
        findings.append(
            SourceReconciliationFinding(
                severity="FAIL",
                code="SEASONALITY_MISSING_FETCHED_AT",
                table=table,
                field="fetched_at",
                message=(
                    f"{raw.null_fetched_at_count} seasonality_cache row(s) have null fetched_at."
                ),
                impact="Provenance timestamp missing; PIT coverage cannot be verified.",
                sample_rows=raw.null_fetched_at_samples,
                row_count=raw.row_count,
                mismatch_count=raw.null_fetched_at_count,
            )
        )

    if raw.null_fetched_month_count:
        findings.append(
            SourceReconciliationFinding(
                severity="WARN",
                code="SEASONALITY_MISSING_FETCHED_MONTH",
                table=table,
                field="fetched_month",
                message=(
                    f"{raw.null_fetched_month_count} seasonality_cache row(s) have "
                    "null fetched_month."
                ),
                impact="Provenance period is incomplete for affected rows.",
                row_count=raw.row_count,
                mismatch_count=raw.null_fetched_month_count,
            )
        )

    if raw.fetched_month_mismatch_count:
        findings.append(
            SourceReconciliationFinding(
                severity="WARN",
                code="SEASONALITY_FETCHED_MONTH_MISMATCH",
                table=table,
                field="fetched_month",
                message=(
                    f"{raw.fetched_month_mismatch_count} seasonality_cache row(s) have "
                    "fetched_month not matching the YYYY-MM prefix of fetched_at."
                ),
                impact="Provenance fields disagree; unclear which is authoritative.",
                sample_rows=raw.fetched_month_mismatch_samples,
                row_count=raw.row_count,
                mismatch_count=raw.fetched_month_mismatch_count,
            )
        )

    if raw.all_metrics_null_count:
        findings.append(
            SourceReconciliationFinding(
                severity="INFO",
                code="SEASONALITY_ALL_METRICS_NULL",
                table=table,
                field=None,
                message=(
                    f"{raw.all_metrics_null_count} seasonality_cache row(s) have all "
                    "seasonality metrics null."
                ),
                impact="Row carries identity/provenance only; optional metrics unavailable.",
                row_count=raw.row_count,
                mismatch_count=raw.all_metrics_null_count,
            )
        )

    status = aggregate_status(f.severity for f in findings)
    check = SourceReconciliationCheckResult(
        name="seasonality_provenance_consistency",
        status=status,
        tables=(table,),
        checked_row_count=raw.row_count,
        mismatch_count=(
            raw.invalid_source_count + raw.null_fetched_at_count + raw.fetched_month_mismatch_count
        ),
        summary={
            "invalid_source_count": raw.invalid_source_count,
            "null_fetched_at_count": raw.null_fetched_at_count,
            "null_fetched_month_count": raw.null_fetched_month_count,
            "fetched_month_mismatch_count": raw.fetched_month_mismatch_count,
            "all_metrics_null_count": raw.all_metrics_null_count,
        },
    )
    return check, tuple(findings)


def _evaluate_pit_cache(
    raw: RawPitCacheObservation,
    *,
    check_name: str,
    table: str,
    schema_insufficient_code: str,
    missing_identity_code: str,
    duplicate_identity_code: str,
    all_metrics_null_code: str,
    identity_description: str,
    metrics_description: str,
) -> tuple[SourceReconciliationCheckResult, tuple[SourceReconciliationFinding, ...]]:
    if not raw.exists:
        return _missing_enrichment_table_result(check_name, table)

    if not raw.schema_sufficient:
        return _schema_insufficient_result(
            check_name, table, schema_insufficient_code, raw.row_count, raw.missing_columns
        )

    findings: list[SourceReconciliationFinding] = []

    if raw.row_count == 0:
        findings.append(_empty_table_finding(table))

    if raw.missing_identity_count:
        findings.append(
            SourceReconciliationFinding(
                severity="FAIL",
                code=missing_identity_code,
                table=table,
                field=None,
                message=(
                    f"{raw.missing_identity_count} {table} row(s) have null {identity_description}."
                ),
                impact="Row cannot be trusted as a valid PIT-identifiable record.",
                sample_rows=raw.missing_identity_samples,
                row_count=raw.row_count,
                mismatch_count=raw.missing_identity_count,
            )
        )

    if raw.duplicate_identity_count:
        findings.append(
            SourceReconciliationFinding(
                severity="WARN",
                code=duplicate_identity_code,
                table=table,
                field=None,
                message=(
                    f"{raw.duplicate_identity_count} duplicate (ticker, fetched_date) "
                    f"row(s) found in {table}."
                ),
                impact="PIT lookup becomes ambiguous for affected ticker/date pairs.",
                sample_rows=raw.duplicate_identity_samples,
                row_count=raw.row_count,
                mismatch_count=raw.duplicate_identity_count,
            )
        )

    if raw.all_metrics_null_count:
        findings.append(
            SourceReconciliationFinding(
                severity="WARN",
                code=all_metrics_null_code,
                table=table,
                field=None,
                message=(
                    f"{raw.all_metrics_null_count} {table} row(s) have all of "
                    f"{metrics_description} null."
                ),
                impact="Row carries identity/provenance only; no usable metric data.",
                sample_rows=raw.all_metrics_null_samples,
                row_count=raw.row_count,
                mismatch_count=raw.all_metrics_null_count,
            )
        )

    status = aggregate_status(f.severity for f in findings)
    check = SourceReconciliationCheckResult(
        name=check_name,
        status=status,
        tables=(table,),
        checked_row_count=raw.row_count,
        mismatch_count=raw.missing_identity_count + raw.duplicate_identity_count,
        summary={
            "missing_identity_count": raw.missing_identity_count,
            "duplicate_identity_count": raw.duplicate_identity_count,
            "all_metrics_null_count": raw.all_metrics_null_count,
        },
    )
    return check, tuple(findings)


def evaluate_company_fundamentals(
    raw: RawPitCacheObservation,
) -> tuple[SourceReconciliationCheckResult, tuple[SourceReconciliationFinding, ...]]:
    return _evaluate_pit_cache(
        raw,
        check_name="company_fundamentals_pit_coverage",
        table="company_fundamentals",
        schema_insufficient_code="FUNDAMENTALS_SCHEMA_INSUFFICIENT",
        missing_identity_code="FUNDAMENTALS_MISSING_IDENTITY",
        duplicate_identity_code="FUNDAMENTALS_DUPLICATE_IDENTITY",
        all_metrics_null_code="FUNDAMENTALS_ALL_METRICS_NULL",
        identity_description="ticker or fetched_date",
        metrics_description=(
            "pe_ratio_ttm, roe_ttm, net_profit_margin, revenue_yoy_growth, "
            "piotroski_f_score, dividend_yield, market_cap_idr, pbv"
        ),
    )


def evaluate_analyst_cache(
    raw: RawPitCacheObservation,
) -> tuple[SourceReconciliationCheckResult, tuple[SourceReconciliationFinding, ...]]:
    return _evaluate_pit_cache(
        raw,
        check_name="analyst_cache_pit_coverage",
        table="analyst_cache",
        schema_insufficient_code="ANALYST_SCHEMA_INSUFFICIENT",
        missing_identity_code="ANALYST_MISSING_IDENTITY",
        duplicate_identity_code="ANALYST_DUPLICATE_IDENTITY",
        all_metrics_null_code="ANALYST_RATING_COUNTS_NULL",
        identity_description="ticker or fetched_date",
        metrics_description="buy_count, hold_count, sell_count",
    )


def evaluate_forward_estimates(
    raw: RawPitCacheObservation,
) -> tuple[SourceReconciliationCheckResult, tuple[SourceReconciliationFinding, ...]]:
    return _evaluate_pit_cache(
        raw,
        check_name="forward_estimates_pit_coverage",
        table="forward_estimates_cache",
        schema_insufficient_code="FORWARD_ESTIMATES_SCHEMA_INSUFFICIENT",
        missing_identity_code="FORWARD_ESTIMATES_MISSING_IDENTITY",
        duplicate_identity_code="FORWARD_ESTIMATES_DUPLICATE_IDENTITY",
        all_metrics_null_code="FORWARD_ESTIMATES_ALL_METRICS_NULL",
        identity_description="ticker or fetched_date",
        metrics_description="forward_eps_1y, current_price, forward_pe",
    )


def evaluate_insider_cache(
    raw: RawInsiderCacheObservation,
) -> tuple[SourceReconciliationCheckResult, tuple[SourceReconciliationFinding, ...]]:
    table = "insider_cache"
    if not raw.exists:
        return _missing_enrichment_table_result("insider_cache_pit_coverage", table)

    if not raw.schema_sufficient:
        return _schema_insufficient_result(
            "insider_cache_pit_coverage",
            table,
            "INSIDER_SCHEMA_INSUFFICIENT",
            raw.row_count,
            raw.missing_columns,
        )

    findings: list[SourceReconciliationFinding] = []

    if raw.row_count == 0:
        findings.append(_empty_table_finding(table))

    if raw.missing_identity_count:
        findings.append(
            SourceReconciliationFinding(
                severity="FAIL",
                code="INSIDER_MISSING_IDENTITY",
                table=table,
                field=None,
                message=(
                    f"{raw.missing_identity_count} insider_cache row(s) have null "
                    "ticker, name, action_type, transaction_date, or fetched_date."
                ),
                impact="Row cannot be trusted as a valid PIT-identifiable record.",
                sample_rows=raw.missing_identity_samples,
                row_count=raw.row_count,
                mismatch_count=raw.missing_identity_count,
            )
        )

    if raw.duplicate_identity_count:
        findings.append(
            SourceReconciliationFinding(
                severity="WARN",
                code="INSIDER_DUPLICATE_IDENTITY",
                table=table,
                field=None,
                message=(
                    f"{raw.duplicate_identity_count} duplicate (ticker, name, "
                    "action_type, transaction_date, fetched_date) row(s) found in "
                    "insider_cache."
                ),
                impact="Natural-key uniqueness is violated; aggregates may double-count.",
                sample_rows=raw.duplicate_identity_samples,
                row_count=raw.row_count,
                mismatch_count=raw.duplicate_identity_count,
            )
        )

    status = aggregate_status(f.severity for f in findings)
    check = SourceReconciliationCheckResult(
        name="insider_cache_pit_coverage",
        status=status,
        tables=(table,),
        checked_row_count=raw.row_count,
        mismatch_count=raw.missing_identity_count + raw.duplicate_identity_count,
        summary={
            "missing_identity_count": raw.missing_identity_count,
            "duplicate_identity_count": raw.duplicate_identity_count,
        },
    )
    return check, tuple(findings)


def evaluate_corporate_action_linkage(
    raw: RawCorporateActionLinkageObservation,
) -> tuple[SourceReconciliationCheckResult, tuple[SourceReconciliationFinding, ...]]:
    events_table = "corporate_action_events"
    dates_table = "corporate_action_event_dates"
    findings: list[SourceReconciliationFinding] = []
    tables: list[str] = []

    if not raw.events_exists:
        findings.append(
            SourceReconciliationFinding(
                severity="WARN",
                code="MISSING_ENRICHMENT_TABLE",
                table=events_table,
                field=None,
                message=f"{events_table} does not exist.",
                impact=_MISSING_TABLE_IMPACT,
            )
        )
    else:
        tables.append(events_table)

    if not raw.event_dates_exists:
        findings.append(
            SourceReconciliationFinding(
                severity="WARN",
                code="MISSING_ENRICHMENT_TABLE",
                table=dates_table,
                field=None,
                message=f"{dates_table} does not exist.",
                impact=_MISSING_TABLE_IMPACT,
            )
        )
    else:
        tables.append(dates_table)

    if not raw.events_exists or not raw.event_dates_exists:
        status = aggregate_status(f.severity for f in findings)
        check = SourceReconciliationCheckResult(
            name="corporate_action_event_linkage",
            status=status,
            tables=tuple(tables),
            checked_row_count=None,
            mismatch_count=None,
            summary={},
        )
        return check, tuple(findings)

    if not raw.events_schema_sufficient:
        findings.append(
            SourceReconciliationFinding(
                severity="FAIL",
                code="CORPORATE_ACTION_EVENTS_SCHEMA_INSUFFICIENT",
                table=events_table,
                field=None,
                message=(
                    f"{events_table} is missing required column(s): "
                    f"{', '.join(raw.events_missing_columns)}."
                ),
                impact="Linkage reconciliation cannot be performed until the schema is repaired.",
                row_count=raw.events_row_count,
            )
        )

    if not raw.event_dates_schema_sufficient:
        findings.append(
            SourceReconciliationFinding(
                severity="FAIL",
                code="CORPORATE_ACTION_EVENT_DATES_SCHEMA_INSUFFICIENT",
                table=dates_table,
                field=None,
                message=(
                    f"{dates_table} is missing required column(s): "
                    f"{', '.join(raw.event_dates_missing_columns)}."
                ),
                impact="Linkage reconciliation cannot be performed until the schema is repaired.",
                row_count=raw.event_dates_row_count,
            )
        )

    if not raw.events_schema_sufficient or not raw.event_dates_schema_sufficient:
        status = aggregate_status(f.severity for f in findings)
        check = SourceReconciliationCheckResult(
            name="corporate_action_event_linkage",
            status=status,
            tables=tuple(tables),
            checked_row_count=raw.event_dates_row_count,
            mismatch_count=None,
            summary={},
        )
        return check, tuple(findings)

    if raw.events_row_count == 0:
        findings.append(_empty_table_finding(events_table))
    if raw.event_dates_row_count == 0:
        findings.append(_empty_table_finding(dates_table))

    if raw.orphan_date_rows_count:
        findings.append(
            SourceReconciliationFinding(
                severity="FAIL",
                code="CORPORATE_ACTION_DATE_ORPHAN",
                table=dates_table,
                field=None,
                message=(
                    f"{raw.orphan_date_rows_count} corporate_action_event_dates row(s) "
                    "have no matching corporate_action_events row by (source, "
                    "event_type, source_event_id, ticker)."
                ),
                impact="Date row cannot be interpreted without its parent event.",
                sample_rows=raw.orphan_date_rows_samples,
                mismatch_count=raw.orphan_date_rows_count,
            )
        )

    if raw.events_without_dates_count:
        findings.append(
            SourceReconciliationFinding(
                severity="WARN",
                code="CORPORATE_ACTION_EVENT_WITHOUT_DATES",
                table=events_table,
                field=None,
                message=(
                    f"{raw.events_without_dates_count} corporate_action_events row(s) "
                    "have no corresponding corporate_action_event_dates rows."
                ),
                impact="Event has no known date roles (e.g. cum/ex/payment) recorded.",
                sample_rows=raw.events_without_dates_samples,
                mismatch_count=raw.events_without_dates_count,
            )
        )

    if raw.null_event_date_count:
        findings.append(
            SourceReconciliationFinding(
                severity="FAIL",
                code="CORPORATE_ACTION_MISSING_EVENT_DATE",
                table=dates_table,
                field="event_date",
                message=(
                    f"{raw.null_event_date_count} corporate_action_event_dates row(s) "
                    "have null event_date."
                ),
                impact="Date row cannot be used for temporal reasoning without event_date.",
                sample_rows=raw.null_event_date_samples,
                mismatch_count=raw.null_event_date_count,
            )
        )

    if raw.null_date_role_count:
        findings.append(
            SourceReconciliationFinding(
                severity="WARN",
                code="CORPORATE_ACTION_MISSING_DATE_ROLE",
                table=dates_table,
                field="date_role",
                message=(
                    f"{raw.null_date_role_count} corporate_action_event_dates row(s) "
                    "have null date_role."
                ),
                impact="Unclear which role (cum/ex/payment/etc.) this date represents.",
                mismatch_count=raw.null_date_role_count,
            )
        )

    status = aggregate_status(f.severity for f in findings)
    check = SourceReconciliationCheckResult(
        name="corporate_action_event_linkage",
        status=status,
        tables=tuple(tables),
        checked_row_count=raw.event_dates_row_count,
        mismatch_count=(
            raw.orphan_date_rows_count
            + raw.events_without_dates_count
            + raw.null_event_date_count
            + raw.null_date_role_count
        ),
        summary={
            "events_row_count": raw.events_row_count,
            "event_dates_row_count": raw.event_dates_row_count,
            "orphan_date_rows_count": raw.orphan_date_rows_count,
            "events_without_dates_count": raw.events_without_dates_count,
        },
    )
    return check, tuple(findings)


def evaluate_ticker_notation_cache(
    raw: RawTickerNotationObservation,
) -> tuple[SourceReconciliationCheckResult, tuple[SourceReconciliationFinding, ...]]:
    table = "ticker_notation_cache"
    if not raw.exists:
        return _missing_enrichment_table_result("ticker_notation_cache_limitation", table)

    if not raw.schema_sufficient:
        return _schema_insufficient_result(
            "ticker_notation_cache_limitation",
            table,
            "TICKER_NOTATION_SCHEMA_INSUFFICIENT",
            raw.row_count,
            raw.missing_columns,
        )

    findings: list[SourceReconciliationFinding] = []

    if raw.row_count == 0:
        findings.append(_empty_table_finding(table))

    findings.append(
        SourceReconciliationFinding(
            severity="INFO",
            code="TICKER_NOTATION_CURRENT_CACHE_LIMITATION",
            table=table,
            field=None,
            message="ticker_notation_cache is a CURRENT_CACHE snapshot, not historical PIT.",
            impact=(
                "ticker_notation_cache has no DB-enforced historical uniqueness; do "
                "not use it for point-in-time historical replay."
            ),
        )
    )

    if raw.missing_provenance_count:
        findings.append(
            SourceReconciliationFinding(
                severity="WARN",
                code="TICKER_NOTATION_MISSING_PROVENANCE",
                table=table,
                field=None,
                message=(
                    f"{raw.missing_provenance_count} ticker_notation_cache row(s) have "
                    "null source or fetched_date."
                ),
                impact="Provenance is incomplete for affected rows.",
                sample_rows=raw.missing_provenance_samples,
                row_count=raw.row_count,
                mismatch_count=raw.missing_provenance_count,
            )
        )

    status = aggregate_status(f.severity for f in findings)
    check = SourceReconciliationCheckResult(
        name="ticker_notation_cache_limitation",
        status=status,
        tables=(table,),
        checked_row_count=raw.row_count,
        mismatch_count=raw.missing_provenance_count,
        summary={"missing_provenance_count": raw.missing_provenance_count},
    )
    return check, tuple(findings)


def evaluate_stock_meta(
    raw: RawStockMetaObservation,
) -> tuple[SourceReconciliationCheckResult, tuple[SourceReconciliationFinding, ...]]:
    table = "stock_meta"
    if not raw.exists:
        return _missing_enrichment_table_result("stock_meta_provenance", table)

    if not raw.schema_sufficient:
        return _schema_insufficient_result(
            "stock_meta_provenance",
            table,
            "STOCK_META_SCHEMA_INSUFFICIENT",
            raw.row_count,
            raw.missing_columns,
        )

    findings: list[SourceReconciliationFinding] = []

    if raw.row_count == 0:
        findings.append(_empty_table_finding(table))

    if raw.missing_identity_count:
        findings.append(
            SourceReconciliationFinding(
                severity="FAIL",
                code="STOCK_META_MISSING_IDENTITY",
                table=table,
                field=None,
                message=(
                    f"{raw.missing_identity_count} stock_meta row(s) have null "
                    "ticker, source, or fetched_at."
                ),
                impact="Row cannot be trusted as a valid provenance-identifiable record.",
                sample_rows=raw.missing_identity_samples,
                row_count=raw.row_count,
                mismatch_count=raw.missing_identity_count,
            )
        )

    if raw.duplicate_identity_count:
        findings.append(
            SourceReconciliationFinding(
                severity="WARN",
                code="STOCK_META_DUPLICATE_IDENTITY",
                table=table,
                field=None,
                message=(
                    f"{raw.duplicate_identity_count} duplicate (ticker, fetched_at) "
                    "row(s) found in stock_meta."
                ),
                impact="PIT lookup becomes ambiguous for affected ticker/timestamp pairs.",
                sample_rows=raw.duplicate_identity_samples,
                row_count=raw.row_count,
                mismatch_count=raw.duplicate_identity_count,
            )
        )

    if raw.both_sector_industry_null_count:
        findings.append(
            SourceReconciliationFinding(
                severity="WARN",
                code="STOCK_META_MISSING_CLASSIFICATION",
                table=table,
                field=None,
                message=(
                    f"{raw.both_sector_industry_null_count} stock_meta row(s) have "
                    "both sector and industry null."
                ),
                impact="Classification is entirely unavailable for affected rows.",
                sample_rows=raw.both_sector_industry_null_samples,
                row_count=raw.row_count,
                mismatch_count=raw.both_sector_industry_null_count,
            )
        )

    status = aggregate_status(f.severity for f in findings)
    check = SourceReconciliationCheckResult(
        name="stock_meta_provenance",
        status=status,
        tables=(table,),
        checked_row_count=raw.row_count,
        mismatch_count=raw.missing_identity_count + raw.duplicate_identity_count,
        summary={
            "missing_identity_count": raw.missing_identity_count,
            "duplicate_identity_count": raw.duplicate_identity_count,
            "both_sector_industry_null_count": raw.both_sector_industry_null_count,
        },
    )
    return check, tuple(findings)
