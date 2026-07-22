"""
CSV writer for `saham analyze accum-audit` raw audit records.

Layer: Adapter
"""

import csv
from pathlib import Path

from src.application.use_case.accumulation_audit_use_case import AccumulationAuditResponse

_FALLBACK_FIELDNAMES = [
    "signal_date", "ticker", "foreign_flow_score", "signal_score",
    "signal_authority_coverage", "streak", "net_buy_ratio",
    "total_net_value", "flow_pct", "vwap_disc_pct", "rsi", "bb_pctile",
    "trend", "broker_quality", "current_price", "return_5d_pct", "return_10d_pct",
    "return_20d_pct", "max_upside_pct", "max_drawdown_pct",
]


def write_accumulation_audit_csv(
    response: AccumulationAuditResponse,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [r.to_dict() for r in response.records]
    fieldnames = list(rows[0].keys()) if rows else _FALLBACK_FIELDNAMES
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
