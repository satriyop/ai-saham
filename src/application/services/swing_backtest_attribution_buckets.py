from __future__ import annotations

from typing import Any, Iterable

from src.application.dto.swing_backtest_attribution import AttributionBucketPolicy


def trade_attribution_buckets(
    trade: Any,
    bucket_policy: AttributionBucketPolicy,
) -> tuple[tuple[str, str], ...]:
    buckets: list[tuple[str, str]] = []
    _add(buckets, "trade_setup_action", getattr(trade, "trade_setup_action", None))
    _add(buckets, "risk_status", getattr(trade, "risk_status", None))
    _add(buckets, "risk_gate", getattr(trade, "risk_gate", None))
    _add(buckets, "signal_strength", getattr(trade, "signal_strength", None))
    _add(
        buckets,
        "signal_score_bucket",
        _score_bucket(getattr(trade, "signal_score", None), bucket_policy),
    )
    _add(buckets, "regime", getattr(trade, "regime", None))
    _add_setup_gate_buckets(buckets, getattr(trade, "setup_gates", ()))
    _add_signal_factor_buckets(
        buckets,
        getattr(trade, "signal_breakdown", ()),
        bucket_policy,
    )
    return tuple(buckets)


def candidate_attribution_buckets(
    observation: Any,
    bucket_policy: AttributionBucketPolicy,
) -> tuple[tuple[str, str], ...]:
    buckets: list[tuple[str, str]] = []
    _add(buckets, "candidate_setup_match", getattr(observation, "setup_match", None))
    _add(buckets, "candidate_signal_strength", getattr(observation, "signal_strength", None))
    _add(
        buckets,
        "candidate_signal_score_bucket",
        _score_bucket(getattr(observation, "signal_score", None), bucket_policy),
    )
    _add(buckets, "candidate_risk_status", getattr(observation, "risk_status", None))
    _add(buckets, "candidate_risk_gate", getattr(observation, "risk_gate", None))
    _add(buckets, "candidate_trade_setup_action", getattr(observation, "trade_setup_action", None))
    _add(buckets, "candidate_regime", getattr(observation, "regime", None))
    _add_setup_gate_buckets(buckets, getattr(observation, "setup_gates", ()))
    _add_signal_factor_buckets(
        buckets,
        getattr(observation, "signal_breakdown", ()),
        bucket_policy,
        dimension="candidate_signal_factor_bucket",
    )
    return tuple(buckets)


def _add(buckets: list[tuple[str, str]], dimension: str, bucket: object | None) -> None:
    if bucket is None:
        return
    bucket_text = str(bucket)
    if bucket_text:
        buckets.append((dimension, bucket_text))


def _add_setup_gate_buckets(
    buckets: list[tuple[str, str]],
    setup_gates: Iterable[Any],
) -> None:
    for gate in setup_gates:
        label = getattr(gate, "label", None)
        if not label:
            continue
        status = "PASS" if getattr(gate, "passed", False) else "FAIL"
        buckets.append(("setup_gate", f"{label}:{status}"))


def _add_signal_factor_buckets(
    buckets: list[tuple[str, str]],
    signal_breakdown: Iterable[tuple[str, float]],
    bucket_policy: AttributionBucketPolicy,
    dimension: str = "signal_factor_bucket",
) -> None:
    for name, value in signal_breakdown:
        buckets.append((
            dimension,
            f"{name}:{_score_bucket(value, bucket_policy)}",
        ))


def _score_bucket(
    value: int | float | None,
    bucket_policy: AttributionBucketPolicy,
) -> str | None:
    if value is None:
        return None
    high = _format_threshold(bucket_policy.high_min_score)
    mid = _format_threshold(bucket_policy.mid_min_score)
    high_floor = _format_threshold(bucket_policy.high_min_score - 1)
    if value >= bucket_policy.high_min_score:
        return f"HIGH_{high}_PLUS"
    if value >= bucket_policy.mid_min_score:
        return f"MID_{mid}_{high_floor}"
    return f"LOW_BELOW_{mid}"


def _format_threshold(value: float) -> str:
    return str(int(value)) if value == int(value) else str(value).replace(".", "_")
