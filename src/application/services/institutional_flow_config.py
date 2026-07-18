"""Config and DTOs for institutional accumulation analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_FOREIGN_BROKER_CODES: frozenset[str] = frozenset(
    {
        "AK", "BK", "ZP", "KZ", "YU", "RX", "HD", "CP", "DR",  # tier-1 foreign
        "DB", "ML", "CS", "AI", "GW", "BW", "KI", "DP", "YB",  # broader foreign
    }
)

# Component weights mirror config/institutional_accumulation.yaml. Pure
# application defaults used when no explicit config is supplied (no YAML
# read); an explicit config mapping always overrides these.
DEFAULT_FOREIGN_TRACK_WEIGHTS: dict[str, float] = {
    "foreign_participation": 0.25,
    "foreign_concentration_cr4_cr8": 0.20,
    "cnfb_price_divergence": 0.35,
    "foreign_vwap_distance": 0.20,
}
DEFAULT_DOMESTIC_TRACK_WEIGHTS: dict[str, float] = {
    "broker_consistency": 0.25,
    "broker_reversal": 0.15,
    "accumulation_session_ratio": 0.20,
    "domestic_buy_vwap_distance": 0.15,
    "broker_hhi_divergence": 0.15,
    "bandar_broad_or_accumulation_score": 0.10,
}
DEFAULT_TRACK_WEIGHTS: dict[str, float] = {
    "foreign_institutional_track": 0.45,
    "domestic_bandar_track": 0.40,
    "counterparty_transfer": 0.15,
}


def _parse_foreign_broker_codes(block: dict) -> frozenset[str]:
    raw = (block.get("broker_classification") or {}).get("foreign_broker_codes")
    if raw is None:
        return DEFAULT_FOREIGN_BROKER_CODES
    return frozenset(c.upper().strip() for c in raw)


_EVIDENCE_AUTHORITY_CONFIG_ERROR = (
    "institutional_accumulation.evidence_status is not configurable; "
    "evidence authority is owned by the validated central authority registry"
)


@dataclass(frozen=True)
class InstitutionalAccumulationConfig:
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
        if "evidence_status" in raw:
            raise ValueError(_EVIDENCE_AUTHORITY_CONFIG_ERROR)
        block = raw.get("institutional_accumulation", raw)
        if "evidence_status" in block:
            raise ValueError(_EVIDENCE_AUTHORITY_CONFIG_ERROR)
        windows = block.get("windows", {})
        return cls(
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
                    block.get("foreign_institutional_track_components")
                    or DEFAULT_FOREIGN_TRACK_WEIGHTS
                ).items()
            },
            domestic_track_weights={
                str(k): float(v)
                for k, v in (
                    block.get("domestic_bandar_track_components")
                    or DEFAULT_DOMESTIC_TRACK_WEIGHTS
                ).items()
            },
            track_weights={
                str(k): float(v)
                for k, v in (block.get("track_weights") or DEFAULT_TRACK_WEIGHTS).items()
            },
            foreign_broker_codes=_parse_foreign_broker_codes(block),
        )

