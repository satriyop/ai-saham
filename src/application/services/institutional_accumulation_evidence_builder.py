"""InstitutionalAccumulationEvidenceBuilder — application service (Phase E).

Computes two-track institutional flow evidence (foreign institutional + domestic
bandar) plus a counterparty-transfer dimension from IDX broker data.

DIAGNOSTIC-ONLY: the resulting InstitutionalAccumulationEvidence is persisted and
reported for replay attribution and human inspection. It is NEVER fed into
SignalEngine scoring or DecisionPolicy.

Design invariants:
- The builder NEVER fetches data. All inputs arrive on the request.
- The builder NEVER raises. Every sub-computation degrades to a None score with
  an unavailable reason; an unhandled error degrades the whole evidence to
  coverage=0 / conviction=0 with metadata["error"].
- evidence_status is always DIAGNOSTIC in this phase.

Layer: Application. Depends only on domain entities/VOs + stdlib + PyYAML.
No provider/repository/CLI imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from src.application.services.institutional_flow_broker_metrics import (
    _Unavailable,
    foreign_flows,
    is_foreign_broker,
    local_flows,
)
from src.application.services.institutional_flow_config import (
    DEFAULT_FOREIGN_BROKER_CODES,
    InstitutionalAccumulationConfig,
)
from src.application.services.institutional_flow_counterparty import (
    build_counterparty_transfer,
)
from src.application.services.institutional_flow_domestic_track import build_domestic_track
from src.application.services.institutional_flow_foreign_track import build_foreign_track
from src.application.services.institutional_flow_math import _clamp01
from src.domain.entities.broker_flow import (
    BrokerDailyFlow,
    BrokerSummary,
    ForeignFlowPoint,
)
from src.domain.entities.candle import Candle
from src.domain.value_objects.bandar_detector_snapshot import BandarDetectorSnapshot
from src.domain.value_objects.institutional_accumulation_evidence import (
    DomesticBandarTrack,
    ForeignInstitutionalTrack,
    InstitutionalAccumulationEvidence,
)

__all__ = [
    "InstitutionalAccumulationEvidenceRequest",
    "InstitutionalAccumulationEvidenceBuilder",
    "InstitutionalAccumulationConfig",
    "DEFAULT_FOREIGN_BROKER_CODES",
]


@dataclass(frozen=True)
class InstitutionalAccumulationEvidenceRequest:
    ticker: str
    snapshot_date: date
    broker_daily_flows: tuple[BrokerDailyFlow, ...]
    foreign_flow_points: tuple[ForeignFlowPoint, ...]
    broker_summaries: tuple[BrokerSummary, ...]
    bandar_snapshot: BandarDetectorSnapshot | None
    candles: tuple[Candle, ...]


class InstitutionalAccumulationEvidenceBuilder:
    """Builds diagnostic InstitutionalAccumulationEvidence from broker data."""

    def __init__(
        self,
        config: InstitutionalAccumulationConfig | None = None,
        *,
        foreign_broker_codes: frozenset[str] | None = None,
    ) -> None:
        self._config = (
            config if config is not None else InstitutionalAccumulationConfig.from_mapping({})
        )
        self._config.validate()
        self._foreign_codes = (
            foreign_broker_codes
            if foreign_broker_codes is not None
            else self._config.foreign_broker_codes
        )

    def build(
        self, request: InstitutionalAccumulationEvidenceRequest
    ) -> InstitutionalAccumulationEvidence:
        try:
            return self._build(request)
        except Exception as exc:  # pragma: no cover
            return self._minimal_unavailable(request, error=str(exc))

    def _build(
        self, request: InstitutionalAccumulationEvidenceRequest
    ) -> InstitutionalAccumulationEvidence:
        ticker = request.ticker.upper().strip()
        candles = sorted(request.candles, key=lambda c: c.date)
        current_price = float(candles[-1].close) if candles else None

        metadata: dict[str, Any] = {"diagnostic_only": True}

        # Separately trace unavailable reasons for each track to avoid leakage
        foreign_unavailable: list[str] = []
        domestic_unavailable: list[str] = []

        def safe_foreign(func, name):
            return self._safe(func, name, foreign_unavailable)

        def safe_pair_foreign(func, name):
            return self._safe_pair(func, name, foreign_unavailable)

        def safe_domestic(func, name):
            return self._safe(func, name, domestic_unavailable)

        foreign_track = build_foreign_track(
            request=request,
            config=self._config,
            foreign_codes=self._foreign_codes,
            candles=candles,
            metadata=metadata,
            safe=safe_foreign,
            safe_pair=safe_pair_foreign,
            mean_available=self._mean_available,
            unavailable=foreign_unavailable,
        )

        domestic_track = build_domestic_track(
            request=request,
            config=self._config,
            foreign_codes=self._foreign_codes,
            current_price=current_price,
            safe=safe_domestic,
            mean_available=self._mean_available,
            unavailable=domestic_unavailable,
        )

        counterparty = build_counterparty_transfer(
            request=request,
            config=self._config,
            foreign_codes=self._foreign_codes,
        )

        # ----- top-level coverage / conviction (renormalised weighted average)
        weights = self._config.track_weights
        included: list[tuple[float, float, float]] = [
            (
                foreign_track.coverage_score,
                foreign_track.conviction_score,
                weights.get("foreign_institutional_track", 0.45),
            ),
            (
                domestic_track.coverage_score,
                domestic_track.conviction_score,
                weights.get("domestic_bandar_track", 0.40),
            ),
        ]
        counterparty_available = (
            counterparty is not None
            and counterparty.transfer_asymmetry_score is not None
        )
        if counterparty_available:
            included.append(
                (
                    counterparty.coverage_score,
                    counterparty.conviction_score,
                    weights.get("counterparty_transfer", 0.15),
                )
            )

        total_w = sum(w for _, _, w in included)
        if total_w > 0:
            coverage = round(sum(cov * w for cov, _, w in included) / total_w, 4)
            conviction = round(sum(con * w for _, con, w in included) / total_w, 4)
        else:
            coverage = 0.0
            conviction = 0.0

        reasons: tuple[str, ...] = ()
        unavailable: tuple[str, ...] = tuple(
            r for r in ("counterparty_unavailable",) if not counterparty_available
        )

        return InstitutionalAccumulationEvidence(
            ticker=ticker,
            snapshot_date=request.snapshot_date,
            foreign_institutional_track=foreign_track,
            domestic_bandar_track=domestic_track,
            counterparty_transfer=counterparty,
            coverage_score=_clamp01(coverage),
            conviction_score=_clamp01(conviction),
            evidence_status=self._config.evidence_status,
            reasons=reasons,
            unavailable_reasons=unavailable,
            metadata=metadata,
        )

    @staticmethod
    def _mean_available(values: list[float | None]) -> float | None:
        present = [v for v in values if v is not None]
        return _clamp01(sum(present) / len(present)) if present else None

    @staticmethod
    def _safe(func, name: str, unavailable: list[str]):
        try:
            return func()
        except _Unavailable as exc:
            unavailable.append(f"{name}_unavailable:{exc}")
            return None
        except Exception as exc:  # noqa: BLE001 - degrade any failure
            unavailable.append(f"{name}_failed:{exc}")
            return None

    @staticmethod
    def _safe_pair(func, name: str, unavailable: list[str]):
        try:
            return func()
        except _Unavailable as exc:
            unavailable.append(f"{name}_unavailable:{exc}")
            return None, None
        except Exception as exc:  # noqa: BLE001 - degrade any failure
            unavailable.append(f"{name}_failed:{exc}")
            return None, None

    def _minimal_unavailable(
        self,
        request: InstitutionalAccumulationEvidenceRequest,
        *,
        error: str,
    ) -> InstitutionalAccumulationEvidence:
        status = self._config.evidence_status
        empty_foreign = ForeignInstitutionalTrack(
            foreign_participation_score=None,
            foreign_cr4_score=None,
            foreign_cr8_score=None,
            cnfb_divergence_score=None,
            foreign_vwap_distance_score=None,
            coverage_score=0.0,
            conviction_score=0.0,
            evidence_status=status,
            reasons=(),
            unavailable_reasons=("build_failed",),
        )
        empty_domestic = DomesticBandarTrack(
            broker_consistency_score=None,
            broker_reversal_score=None,
            accumulation_session_ratio=None,
            domestic_buy_vwap_distance_score=None,
            broker_hhi_divergence_score=None,
            bandar_broad_score_normalized=None,
            bandar_accumulation_score_normalized=None,
            coverage_score=0.0,
            conviction_score=0.0,
            evidence_status=status,
            reasons=(),
            unavailable_reasons=("build_failed",),
        )
        return InstitutionalAccumulationEvidence(
            ticker=(request.ticker or "UNKNOWN").upper().strip() or "UNKNOWN",
            snapshot_date=request.snapshot_date,
            foreign_institutional_track=empty_foreign,
            domestic_bandar_track=empty_domestic,
            counterparty_transfer=None,
            coverage_score=0.0,
            conviction_score=0.0,
            evidence_status=status,
            reasons=(),
            unavailable_reasons=("build_failed",),
            metadata={"diagnostic_only": True, "error": error},
        )

    def _is_foreign(self, broker_code: str) -> bool:
        return is_foreign_broker(broker_code, self._foreign_codes)

    def _foreign_flows(self, flows: list[BrokerDailyFlow]) -> list[BrokerDailyFlow]:
        return foreign_flows(flows, self._foreign_codes)

    def _local_flows(self, flows: list[BrokerDailyFlow]) -> list[BrokerDailyFlow]:
        return local_flows(flows, self._foreign_codes)

