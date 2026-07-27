"""
Shared pure formatting helpers for policy accum CLI display.

No Rich panel/table orchestration. No application tuning builder imports.
All functions keep underscore prefix (private) unless imported by tests.

Layer: Adapter
"""

from __future__ import annotations


def _fmt_pct(value: float | None, signed: bool = False) -> str:
    if value is None:
        return "N/A"
    return f"{value:+.2f}%" if signed else f"{value:.1f}%"


def _quality_status_text(status: str) -> str:
    color = {
        "INSUFFICIENT_SAMPLE": "red",
        "CANDIDATE_ONLY": "yellow",
        "TRADE_READY": "green",
        "MIXED_READY": "green",
    }.get(status, "white")
    return f"[{color}]{status}[/]"


def _stat_count(stat) -> int:
    return getattr(stat, "trade_count", getattr(stat, "observation_count", 0))


def _stat_avg_return(stat) -> float | None:
    return getattr(
        stat,
        "avg_return_pct",
        getattr(stat, "avg_forward_return_pct", None),
    )


def _stat_profit_factor(stat) -> float | None:
    return getattr(stat, "profit_factor", None)


def _fmt_config_value(value: object | None) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, (dict, list, tuple)):
        return type(value).__name__
    return str(value)


def _fmt_target_path(item) -> str:
    parsed = getattr(item, "parsed_target_path", None)
    if parsed is None:
        return item.target_path
    file_name = parsed.file_path.rsplit("/", maxsplit=1)[-1]
    leaf = parsed.document_path.rsplit(".", maxsplit=1)[-1]
    return f"{file_name}:{leaf}"


def _fmt_evidence_dimensions(item) -> str:
    dimensions = getattr(item, "evidence_dimensions", ()) or (
        item.evidence_dimension,
    )
    return ",".join(dimensions)


def _fmt_count_map(counts: object) -> str:
    if not isinstance(counts, dict) or not counts:
        return "N/A"
    return ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))


def _fmt_evidence_snapshot(snapshot) -> str:
    if snapshot is None:
        return "N/A"
    spread = (
        "N/A"
        if snapshot.return_spread_pct is None
        else f"{snapshot.return_spread_pct:+.2f}%"
    )
    return (
        f"n={snapshot.sample_count}, spread={spread}, "
        f"strength={snapshot.evidence_strength}, priority={snapshot.priority}"
    )


def _fmt_target_classification(classification) -> str:
    return (
        f"{classification.target_family}/"
        f"{classification.target_kind}/"
        f"{classification.target_parameter}"
    )
