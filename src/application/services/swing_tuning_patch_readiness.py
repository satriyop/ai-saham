"""Sample and attribution readiness validation policy for swing tuning patches.

Layer: Application
"""

from __future__ import annotations

# Phase I target-state readiness gates. Diagnostic-ready findings are
# report-only; patch validation requires the stricter patch-eligible floor from
# docs/signal_refactor.md.
_DIAGNOSTIC_MIN_OOS_TRADE_COUNT: int = 10
_PATCH_MIN_IS_TRADE_COUNT: int = 60
_PATCH_MIN_OOS_TRADE_COUNT: int = 30
_PATCH_MIN_OOS_PROFIT_FACTOR: float = 1.15
_PATCH_MIN_OOS_AVERAGE_RETURN_PCT: float = 0.0
_PATCH_MAX_OOS_DRAWDOWN_REGRESSION: float = 0.0
_MAX_SINGLE_REGIME_OOS_PROFIT_SHARE: float = 0.70
_MIN_POSITIVE_OOS_REGIME_COUNT: int = 2
_MIN_OOS_TRADES_PER_COUNTED_REGIME: int = 5


def _validate_sample_readiness(source_review: object) -> tuple[str, ...]:
    """Return issue strings when sample quality is insufficient for apply.

    All issues are prefixed with 'sample_not_ready:' so callers can detect
    the category with a single substring check.

    The validator is closed-by-default: missing required fields are rejected,
    not skipped. Phase I separates diagnostic-ready report output from
    patch-eligible config mutation. This validator only accepts patch-eligible
    source reviews.
    """
    prefix = "sample_not_ready:"
    issues: list[str] = []
    if not isinstance(source_review, dict):
        return ()  # structural error already reported by walk_forward check

    readiness_state = source_review.get("readiness_state")
    if readiness_state not in {"PATCH_ELIGIBLE", "patch_eligible"}:
        issues.append(
            f"{prefix} readiness_state must be PATCH_ELIGIBLE for config patch "
            f"validation; got {readiness_state!r}. Diagnostic-ready output is report-only."
        )

    # IS sample quality — source summary must still be coherent, but the
    # authoritative threshold is the canonical Phase I trade count below.
    sample = source_review.get("sample")
    if not isinstance(sample, dict):
        issues.append(f"{prefix} source_review.sample must be a dict")
    else:
        status = sample.get("status")
        if status not in {"TRADE_READY", "MIXED_READY"}:
            issues.append(
                f"{prefix} sample.status must be TRADE_READY or MIXED_READY, "
                f"got {status!r}; need patch-eligible IS/OOS evidence"
            )

    backtest = source_review.get("backtest_summary")
    if not isinstance(backtest, dict):
        issues.append(f"{prefix} source_review.backtest_summary must be a dict")
    else:
        try:
            is_trades = int(backtest.get("trade_count"))  # type: ignore[arg-type]
            if is_trades < _PATCH_MIN_IS_TRADE_COUNT:
                issues.append(
                    f"{prefix} IS completed_trade_count={is_trades} < {_PATCH_MIN_IS_TRADE_COUNT}"
                )
        except (TypeError, ValueError):
            issues.append(f"{prefix} backtest_summary.trade_count is missing or non-integer")

    # OOS quality — diagnostic-ready is report-only; config patches require the
    # stricter canonical patch-eligible OOS sample and performance floors.
    oos = source_review.get("oos_backtest_summary")
    if isinstance(oos, dict):
        oos_trades: int | None = None
        try:
            oos_trades = int(oos.get("trade_count"))  # type: ignore[arg-type]
            if oos_trades < _DIAGNOSTIC_MIN_OOS_TRADE_COUNT:
                issues.append(
                    f"{prefix} OOS trade_count={oos_trades} "
                    f"< diagnostic-ready minimum {_DIAGNOSTIC_MIN_OOS_TRADE_COUNT}"
                )
            elif oos_trades < _PATCH_MIN_OOS_TRADE_COUNT:
                issues.append(
                    f"{prefix} OOS trade_count={oos_trades} "
                    f"< patch-eligible minimum {_PATCH_MIN_OOS_TRADE_COUNT}; "
                    "diagnostic-ready output is report-only"
                )
        except (TypeError, ValueError):
            issues.append(f"{prefix} oos_backtest_summary.trade_count is missing or non-integer")

        if oos_trades is not None and oos_trades >= _DIAGNOSTIC_MIN_OOS_TRADE_COUNT:
            profit_factor = _float_field(oos, "profit_factor")
            if profit_factor is None:
                issues.append(f"{prefix} OOS profit_factor must be numeric")
            elif profit_factor < _PATCH_MIN_OOS_PROFIT_FACTOR:
                issues.append(
                    f"{prefix} OOS profit_factor={profit_factor} "
                    f"< floor {_PATCH_MIN_OOS_PROFIT_FACTOR}"
                )

            average_return = _first_float_field(
                oos,
                ("average_return_pct", "avg_return_pct"),
            )
            if average_return is None:
                issues.append(f"{prefix} OOS average_return_pct must be numeric")
            elif average_return < _PATCH_MIN_OOS_AVERAGE_RETURN_PCT:
                issues.append(
                    f"{prefix} OOS average_return_pct={average_return} "
                    f"< floor {_PATCH_MIN_OOS_AVERAGE_RETURN_PCT}"
                )

            drawdown_regression = _first_float_field(
                oos,
                ("drawdown_regression_pct", "max_drawdown_regression"),
            )
            if drawdown_regression is None:
                issues.append(f"{prefix} OOS drawdown_regression_pct must be numeric")
            elif drawdown_regression > _PATCH_MAX_OOS_DRAWDOWN_REGRESSION:
                issues.append(
                    f"{prefix} OOS drawdown_regression_pct={drawdown_regression} "
                    f"> max {_PATCH_MAX_OOS_DRAWDOWN_REGRESSION}"
                )
    else:
        issues.append(f"{prefix} source_review.oos_backtest_summary must be a dict")

    issues.extend(_validate_attribution_readiness(source_review, prefix=prefix))

    return tuple(issues)


def _float_field(payload: dict, field: str) -> float | None:
    try:
        return float(payload.get(field))
    except (TypeError, ValueError):
        return None


def _first_float_field(payload: dict, fields: tuple[str, ...]) -> float | None:
    for field in fields:
        value = _float_field(payload, field)
        if value is not None:
            return value
    return None


def _validate_attribution_readiness(
    source_review: dict,
    *,
    prefix: str,
) -> tuple[str, ...]:
    issues: list[str] = []
    attribution = source_review.get("attribution")
    if not isinstance(attribution, dict):
        return (f"{prefix} source_review.attribution must be a dict",)

    for group in ("market_regime", "coverage_bucket", "conviction_bucket"):
        buckets = _attribution_buckets(attribution.get(group))
        if not buckets:
            issues.append(f"{prefix} attribution.{group} must include buckets")

    if source_review.get("single_regime_scoped") is True:
        return tuple(issues)

    regime_buckets = _attribution_buckets(attribution.get("market_regime"))
    positive_profit_rows = [
        row
        for row in regime_buckets
        if _first_float_field(row, ("oos_profit", "total_pnl", "profit")) is not None
        and (_first_float_field(row, ("oos_profit", "total_pnl", "profit")) or 0.0) > 0.0
    ]
    positive_profit = sum(
        _first_float_field(row, ("oos_profit", "total_pnl", "profit")) or 0.0
        for row in positive_profit_rows
    )
    if positive_profit > 0.0:
        max_share = max(
            (
                (_first_float_field(row, ("oos_profit", "total_pnl", "profit")) or 0.0)
                / positive_profit
            )
            for row in positive_profit_rows
        )
        if max_share > _MAX_SINGLE_REGIME_OOS_PROFIT_SHARE:
            issues.append(
                f"{prefix} single-regime OOS profit share={max_share:.4f} "
                f"> {_MAX_SINGLE_REGIME_OOS_PROFIT_SHARE}"
            )

    counted_positive_regimes = 0
    for row in regime_buckets:
        profit = _first_float_field(row, ("oos_profit", "total_pnl", "profit"))
        trade_count = _first_float_field(row, ("oos_trade_count", "trade_count"))
        if (
            profit is not None
            and profit > 0.0
            and trade_count is not None
            and trade_count >= _MIN_OOS_TRADES_PER_COUNTED_REGIME
        ):
            counted_positive_regimes += 1
    if counted_positive_regimes < _MIN_POSITIVE_OOS_REGIME_COUNT:
        issues.append(
            f"{prefix} positive OOS regime count={counted_positive_regimes} "
            f"< {_MIN_POSITIVE_OOS_REGIME_COUNT}"
        )

    return tuple(issues)


def _attribution_buckets(value: object) -> tuple[dict, ...]:
    if isinstance(value, dict):
        buckets = value.get("buckets")
        if isinstance(buckets, list):
            return tuple(row for row in buckets if isinstance(row, dict))
        if all(isinstance(row, dict) for row in value.values()):
            return tuple(value.values())
    if isinstance(value, list):
        return tuple(row for row in value if isinstance(row, dict))
    return ()
