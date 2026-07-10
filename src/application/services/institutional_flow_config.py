"""Config and DTOs for institutional accumulation analysis."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from src.domain.value_objects.institutional_accumulation_evidence import EvidenceStatus

DEFAULT_FOREIGN_BROKER_CODES: frozenset[str] = frozenset(
    {
        "AK", "BK", "ZP", "KZ", "YU", "RX", "HD", "CP", "DR",  # tier-1 foreign
        "DB", "ML", "CS", "AI", "GW", "BW", "KI", "DP", "YB",  # broader foreign
    }
)

_DEFAULT_CONFIG_PATH = (
    Path(__file__).parent.parent.parent.parent
    / "config"
    / "institutional_accumulation.yaml"
)


def _parse_foreign_broker_codes(block: dict) -> frozenset[str]:
    raw = (block.get("broker_classification") or {}).get("foreign_broker_codes")
    if raw is None:
        return DEFAULT_FOREIGN_BROKER_CODES
    return frozenset(c.upper().strip() for c in raw)


@dataclass(frozen=True)
class InstitutionalAccumulationConfig:
    evidence_status: EvidenceStatus
    cnfb_bullish_windows: tuple[int, ...]
    cnfb_bearish_windows: tuple[int, ...]
    foreign_vwap_days: int
    domestic_vwap_days: int
    broker_consistency_days: tuple[int, ...]
    counterparty_window_days: int
    min_sessions: dict[str, int]
    foreign_track_weights: dict[str, float]
    domestic_track_weights: dict[str, float]
    track_weights: dict[str, float]
    foreign_broker_codes: frozenset[str] = DEFAULT_FOREIGN_BROKER_CODES

    def validate(self) -> None:
        """Raise ValueError if any weight group does not sum to 1.00."""
        groups = {
            "foreign_institutional_track_components": self.foreign_track_weights,
            "domestic_bandar_track_components": self.domestic_track_weights,
            "track_weights": self.track_weights,
        }
        for name, weights in groups.items():
            total = round(sum(float(v) for v in weights.values()), 6)
            if abs(total - 1.0) > 1e-6:
                raise ValueError(
                    f"{name} weights must sum to 1.00, got {total}"
                )

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "InstitutionalAccumulationConfig":
        block = raw.get("institutional_accumulation", raw)
        windows = block.get("windows", {})
        status = EvidenceStatus(block.get("evidence_status", "DIAGNOSTIC"))
        return cls(
            evidence_status=status,
            cnfb_bullish_windows=tuple(
                int(w) for w in windows.get("cnfb_bullish_accumulation", [20, 30])
            ),
            cnfb_bearish_windows=tuple(
                int(w) for w in windows.get("cnfb_bearish_distribution", [3, 5, 7])
            ),
            foreign_vwap_days=int(windows.get("foreign_vwap_days", 20)),
            domestic_vwap_days=int(windows.get("domestic_vwap_days", 20)),
            broker_consistency_days=tuple(
                int(w) for w in windows.get("broker_consistency_days", [10, 20])
            ),
            counterparty_window_days=int(windows.get("counterparty_window_days", 5)),
            min_sessions={
                str(k): int(v) for k, v in (block.get("min_valid_sessions") or {}).items()
            },
            foreign_track_weights={
                str(k): float(v)
                for k, v in (
                    block.get("foreign_institutional_track_components") or {}
                ).items()
            },
            domestic_track_weights={
                str(k): float(v)
                for k, v in (block.get("domestic_bandar_track_components") or {}).items()
            },
            track_weights={
                str(k): float(v) for k, v in (block.get("track_weights") or {}).items()
            },
            foreign_broker_codes=_parse_foreign_broker_codes(block),
        )


def load_institutional_accumulation_config(
    path: str | Path | None = None
) -> InstitutionalAccumulationConfig:
    if path is None:
        if not _DEFAULT_CONFIG_PATH.exists():
            return InstitutionalAccumulationConfig.from_mapping({})
        config_path = _DEFAULT_CONFIG_PATH
    else:
        config_path = Path(path)

    with open(config_path, "r") as handle:
        raw = yaml.safe_load(handle) or {}
    return InstitutionalAccumulationConfig.from_mapping(raw)

