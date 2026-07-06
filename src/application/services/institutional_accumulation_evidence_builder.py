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
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from src.domain.entities.broker_flow import (
    BrokerDailyFlow,
    BrokerSummary,
    ForeignFlowPoint,
)
from src.domain.entities.candle import Candle
from src.domain.value_objects.bandar_detector_snapshot import BandarDetectorSnapshot
from src.domain.value_objects.institutional_accumulation_evidence import (
    CounterpartyTransferEvidence,
    DomesticBandarTrack,
    EvidenceStatus,
    ForeignInstitutionalTrack,
    InstitutionalAccumulationEvidence,
)

# --------------------------------------------------------------------------- #
# Broker classification
#
# BrokerDailyFlow has no broker_type field, so foreign vs local is derived from
# the broker code. This mirrors TIER1_FOREIGN_BROKERS used by the accumulation
# screener, broadened with the common foreign custody/prime-brokerage desks.
# The set is overridable on the constructor for deterministic tuning in tests.
# --------------------------------------------------------------------------- #
DEFAULT_FOREIGN_BROKER_CODES: frozenset[str] = frozenset(
    {
        "AK", "BK", "ZP", "KZ", "YU", "RX", "HD", "CP", "DR",  # tier-1 foreign
        "DB", "ML", "CS", "AI", "GW", "BW", "KI", "DP", "YB",  # broader foreign
    }
)

# VWAP saturation band: within NEAR → full score, beyond FAR → zero score.
_VWAP_NEAR = 0.02
_VWAP_FAR = 0.20

_DEFAULT_CONFIG_PATH = (
    Path(__file__).parent.parent.parent.parent
    / "config"
    / "institutional_accumulation.yaml"
)


# --------------------------------------------------------------------------- #
# Request / config dataclasses
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class InstitutionalAccumulationEvidenceRequest:
    ticker: str
    snapshot_date: date
    broker_daily_flows: tuple[BrokerDailyFlow, ...]
    foreign_flow_points: tuple[ForeignFlowPoint, ...]
    broker_summaries: tuple[BrokerSummary, ...]
    bandar_snapshot: BandarDetectorSnapshot | None
    candles: tuple[Candle, ...]


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
        )


# --------------------------------------------------------------------------- #
# Small numeric helpers
# --------------------------------------------------------------------------- #
def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _slope(values: list[float]) -> float:
    """Ordinary least-squares slope of ``values`` against index 0..n-1."""
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(values) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    num = sum((xs[i] - mean_x) * (values[i] - mean_y) for i in range(n))
    return num / denom


def _group_by_date(
    flows: list[BrokerDailyFlow],
) -> dict[date, list[BrokerDailyFlow]]:
    grouped: dict[date, list[BrokerDailyFlow]] = {}
    for flow in flows:
        grouped.setdefault(flow.date, []).append(flow)
    return grouped


def _vwap_distance_score(current_price: float, vwap: float) -> float | None:
    """Saturating score: 1.0 within NEAR of VWAP, 0.0 once FAR above VWAP."""
    if vwap <= 0:
        return None
    distance = (current_price - vwap) / vwap
    if distance <= _VWAP_NEAR:
        return 1.0
    if distance >= _VWAP_FAR:
        return 0.0
    return _clamp01(1.0 - (distance - _VWAP_NEAR) / (_VWAP_FAR - _VWAP_NEAR))


class InstitutionalAccumulationEvidenceBuilder:
    """Builds diagnostic InstitutionalAccumulationEvidence from broker data."""

    def __init__(
        self,
        config: InstitutionalAccumulationConfig | None = None,
        *,
        foreign_broker_codes: frozenset[str] | None = None,
    ) -> None:
        self._config = config if config is not None else self._load_default_config()
        self._config.validate()
        self._foreign_codes = (
            foreign_broker_codes
            if foreign_broker_codes is not None
            else DEFAULT_FOREIGN_BROKER_CODES
        )

    # ---------------------------------------------------------------- config
    @classmethod
    def from_yaml(
        cls, path: str | Path | None = None
    ) -> "InstitutionalAccumulationEvidenceBuilder":
        config_path = Path(path) if path is not None else _DEFAULT_CONFIG_PATH
        with open(config_path, "r") as handle:
            raw = yaml.safe_load(handle) or {}
        return cls(InstitutionalAccumulationConfig.from_mapping(raw))

    @staticmethod
    def _load_default_config() -> InstitutionalAccumulationConfig:
        if _DEFAULT_CONFIG_PATH.exists():
            with open(_DEFAULT_CONFIG_PATH, "r") as handle:
                raw = yaml.safe_load(handle) or {}
            return InstitutionalAccumulationConfig.from_mapping(raw)
        # Fallback mirrors config/institutional_accumulation.yaml defaults.
        return InstitutionalAccumulationConfig.from_mapping({})

    # ------------------------------------------------------------ public API
    def build(
        self, request: InstitutionalAccumulationEvidenceRequest
    ) -> InstitutionalAccumulationEvidence:
        try:
            return self._build(request)
        except Exception as exc:  # pragma: no cover - defensive last resort
            return self._minimal_unavailable(
                request, error=str(exc)
            )

    # --------------------------------------------------------------- builder
    def _build(
        self, request: InstitutionalAccumulationEvidenceRequest
    ) -> InstitutionalAccumulationEvidence:
        ticker = request.ticker.upper().strip()
        candles = sorted(request.candles, key=lambda c: c.date)
        current_price = float(candles[-1].close) if candles else None

        metadata: dict[str, Any] = {"diagnostic_only": True}

        foreign_track = self._build_foreign_track(request, candles, metadata)
        domestic_track = self._build_domestic_track(request, current_price, metadata)
        counterparty = self._build_counterparty(request)

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

    # ---------------------------------------------------------- foreign track
    def _build_foreign_track(
        self,
        request: InstitutionalAccumulationEvidenceRequest,
        candles: list[Candle],
        metadata: dict[str, Any],
    ) -> ForeignInstitutionalTrack:
        flows = list(request.broker_daily_flows)
        unavailable: list[str] = []

        participation = self._safe(
            lambda: self._foreign_participation(request.broker_summaries),
            "foreign_participation",
            unavailable,
        )
        cr4, cr8 = self._safe_pair(
            lambda: self._foreign_concentration(flows),
            "foreign_concentration",
            unavailable,
        )
        cnfb_score = self._safe(
            lambda: self._cnfb_bullish(
                request.foreign_flow_points, candles, metadata
            ),
            "cnfb_divergence",
            unavailable,
        )
        # Fast-distribution windows are diagnostic-only fingerprint data.
        self._safe(
            lambda: self._cnfb_bearish(
                request.foreign_flow_points, candles, metadata
            ),
            "cnfb_distribution",
            unavailable,
        )
        vwap_dist = self._safe(
            lambda: self._foreign_vwap_distance(flows, candles),
            "foreign_vwap_distance",
            unavailable,
        )

        # ----- coverage: 4 slots (participation, cr4|cr8, cnfb, vwap)
        slots = [
            participation is not None,
            (cr4 is not None or cr8 is not None),
            cnfb_score is not None,
            vwap_dist is not None,
        ]
        coverage = round(sum(1 for s in slots if s) / len(slots), 4)

        # ----- conviction: renormalized weighted sum over AVAILABLE components
        # Missing components lower coverage (above). Conviction reflects signal
        # strength of what IS available — renormalize so available weights sum to 1.0.
        w = self._config.foreign_track_weights
        concentration_score = self._mean_available([cr4, cr8])
        available: list[tuple[float, float]] = []  # (score, weight)
        if participation is not None:
            available.append((participation, w.get("foreign_participation", 0.0)))
        if concentration_score is not None:
            available.append(
                (concentration_score, w.get("foreign_concentration_cr4_cr8", 0.0))
            )
        if cnfb_score is not None:
            available.append((cnfb_score, w.get("cnfb_price_divergence", 0.0)))
        if vwap_dist is not None:
            available.append((vwap_dist, w.get("foreign_vwap_distance", 0.0)))
        total_w = sum(wt for _, wt in available)
        conviction = (
            sum(s * wt for s, wt in available) / total_w if total_w > 0 else 0.0
        )

        return ForeignInstitutionalTrack(
            foreign_participation_score=participation,
            foreign_cr4_score=cr4,
            foreign_cr8_score=cr8,
            cnfb_divergence_score=cnfb_score,
            foreign_vwap_distance_score=vwap_dist,
            coverage_score=_clamp01(coverage),
            conviction_score=_clamp01(round(conviction, 4)),
            evidence_status=self._config.evidence_status,
            reasons=(),
            unavailable_reasons=tuple(unavailable),
        )

    # --------------------------------------------------------- domestic track
    def _build_domestic_track(
        self,
        request: InstitutionalAccumulationEvidenceRequest,
        current_price: float | None,
        metadata: dict[str, Any],
    ) -> DomesticBandarTrack:
        flows = list(request.broker_daily_flows)
        unavailable: list[str] = []

        consistency = self._safe(
            lambda: self._broker_consistency(flows),
            "broker_consistency",
            unavailable,
        )
        reversal = self._safe(
            lambda: self._broker_reversal(flows),
            "broker_reversal",
            unavailable,
        )
        session_ratio = self._safe(
            lambda: self._accumulation_session_ratio(flows),
            "accumulation_session_ratio",
            unavailable,
        )
        vwap_dist = self._safe(
            lambda: self._domestic_vwap_distance(flows, current_price),
            "domestic_buy_vwap_distance",
            unavailable,
        )
        hhi_div = self._safe(
            lambda: self._broker_hhi_divergence(flows),
            "broker_hhi_divergence",
            unavailable,
        )
        broad_norm, accum_norm = self._bandar_normalise(
            request.bandar_snapshot, unavailable
        )

        # ----- coverage: 6 slots (bandar broad|accumulation collapse to 1)
        slots = [
            consistency is not None,
            reversal is not None,
            session_ratio is not None,
            vwap_dist is not None,
            hhi_div is not None,
            (broad_norm is not None or accum_norm is not None),
        ]
        coverage = round(sum(1 for s in slots if s) / len(slots), 4)

        # ----- conviction: renormalized weighted sum over AVAILABLE components
        w = self._config.domestic_track_weights
        bandar_score = self._mean_available([broad_norm, accum_norm])
        available: list[tuple[float, float]] = []
        if consistency is not None:
            available.append((consistency, w.get("broker_consistency", 0.0)))
        if reversal is not None:
            available.append((reversal, w.get("broker_reversal", 0.0)))
        if session_ratio is not None:
            available.append(
                (session_ratio, w.get("accumulation_session_ratio", 0.0))
            )
        if vwap_dist is not None:
            available.append((vwap_dist, w.get("domestic_buy_vwap_distance", 0.0)))
        if hhi_div is not None:
            available.append((hhi_div, w.get("broker_hhi_divergence", 0.0)))
        if bandar_score is not None:
            available.append(
                (bandar_score, w.get("bandar_broad_or_accumulation_score", 0.0))
            )
        total_w = sum(wt for _, wt in available)
        conviction = (
            sum(s * wt for s, wt in available) / total_w if total_w > 0 else 0.0
        )

        return DomesticBandarTrack(
            broker_consistency_score=consistency,
            broker_reversal_score=reversal,
            accumulation_session_ratio=session_ratio,
            domestic_buy_vwap_distance_score=vwap_dist,
            broker_hhi_divergence_score=hhi_div,
            bandar_broad_score_normalized=broad_norm,
            bandar_accumulation_score_normalized=accum_norm,
            coverage_score=_clamp01(coverage),
            conviction_score=_clamp01(round(conviction, 4)),
            evidence_status=self._config.evidence_status,
            reasons=(),
            unavailable_reasons=tuple(unavailable),
        )

    # ------------------------------------------------------- counterparty leg
    def _build_counterparty(
        self, request: InstitutionalAccumulationEvidenceRequest
    ) -> CounterpartyTransferEvidence | None:
        flows = list(request.broker_daily_flows)
        if not flows:
            return None
        try:
            return self._counterparty_hhi(flows)
        except Exception as exc:
            return CounterpartyTransferEvidence(
                transfer_asymmetry_score=None,
                buy_side_hhi=None,
                sell_side_hhi=None,
                coverage_score=0.0,
                conviction_score=0.0,
                evidence_status=self._config.evidence_status,
                unavailable_reasons=(f"counterparty_failed:{exc}",),
            )

    # =================================================================== #
    # Metric computations
    # =================================================================== #
    def _foreign_participation(
        self, summaries: tuple[BrokerSummary, ...]
    ) -> float | None:
        if not summaries:
            raise _Unavailable("no_broker_summaries")
        latest = max(summaries, key=lambda s: s.date)
        total = latest.total_value
        if total == Decimal("0"):
            raise _Unavailable("zero_total_value")
        ratio = float((latest.foreign_buy_value + latest.foreign_sell_value) / total)
        return _clamp01(ratio)

    def _foreign_concentration(
        self, flows: list[BrokerDailyFlow]
    ) -> tuple[float | None, float | None]:
        foreign = self._foreign_flows(flows)
        if not foreign:
            raise _Unavailable("no_foreign_flows")
        by_date = _group_by_date(foreign)
        recent = sorted(by_date)[-5:] or sorted(by_date)[-1:]
        cr4s: list[float] = []
        cr8s: list[float] = []
        for d in recent:
            session = by_date[d]
            total = sum(float(f.buy_value) for f in session)
            if total <= 0:
                continue
            buys = sorted((float(f.buy_value) for f in session), reverse=True)
            cr4s.append(_clamp01(sum(buys[:4]) / total))
            cr8s.append(_clamp01(sum(buys[:8]) / total))
        if not cr4s:
            raise _Unavailable("zero_foreign_buy_value")
        return _clamp01(_mean(cr4s)), _clamp01(_mean(cr8s))

    def _cnfb_bullish(
        self,
        points: tuple[ForeignFlowPoint, ...],
        candles: list[Candle],
        metadata: dict[str, Any],
    ) -> float | None:
        scores: list[float] = []
        per_window: dict[str, float] = {}
        for window in self._config.cnfb_bullish_windows:
            threshold = self._config.min_sessions.get(f"cnfb_{window}d", window)
            score = self._cnfb_divergence(
                points, candles, window, threshold, bearish=False
            )
            if score is not None:
                scores.append(score)
                per_window[f"cnfb_{window}d"] = round(score, 4)
        if per_window:
            metadata["cnfb_bullish_scores"] = per_window
        if not scores:
            raise _Unavailable("insufficient_cnfb_sessions")
        return _clamp01(_mean(scores))

    def _cnfb_bearish(
        self,
        points: tuple[ForeignFlowPoint, ...],
        candles: list[Candle],
        metadata: dict[str, Any],
    ) -> float | None:
        per_window: dict[str, float] = {}
        for window in self._config.cnfb_bearish_windows:
            threshold = self._config.min_sessions.get(f"cnfb_{window}d", 2)
            score = self._cnfb_divergence(
                points, candles, window, threshold, bearish=True
            )
            if score is not None:
                per_window[f"cnfb_{window}d"] = round(score, 4)
        if "cnfb_3d" in per_window:
            metadata["cnfb_distribution_3d"] = per_window["cnfb_3d"]
        if per_window:
            metadata["cnfb_bearish_scores"] = per_window
        if not per_window:
            raise _Unavailable("insufficient_fast_cnfb_sessions")
        # Diagnostic fingerprint only; not part of a track score slot.
        return per_window.get("cnfb_3d")

    def _cnfb_divergence(
        self,
        points: tuple[ForeignFlowPoint, ...],
        candles: list[Candle],
        window: int,
        threshold: int,
        *,
        bearish: bool,
    ) -> float | None:
        ordered = sorted(points, key=lambda p: p.date)[-window:]
        if len(ordered) < threshold:
            return None
        close_by_date = {c.date: float(c.close) for c in candles}
        cnfb: list[float] = []
        prices: list[float] = []
        running = 0.0
        for point in ordered:
            running += float(point.net_val)
            if point.date not in close_by_date:
                continue
            cnfb.append(running)
            prices.append(close_by_date[point.date])
        if len(cnfb) < threshold or len(prices) < 2:
            return None
        cnfb_slope = _slope(cnfb)
        price_slope = _slope(prices)
        if bearish:
            return self._bearish_score(cnfb_slope, price_slope)
        return self._bullish_score(cnfb_slope, price_slope)

    @staticmethod
    def _bullish_score(cnfb_slope: float, price_slope: float) -> float:
        if cnfb_slope > 0 and price_slope <= 0:
            return 1.0
        if cnfb_slope > 0 and price_slope > 0:
            return 0.5
        if cnfb_slope < 0 and price_slope < 0:
            return 0.2
        if cnfb_slope < 0 and price_slope >= 0:
            return 0.0
        return 0.2

    @staticmethod
    def _bearish_score(cnfb_slope: float, price_slope: float) -> float:
        if cnfb_slope < 0 and price_slope >= 0:
            return 1.0
        if cnfb_slope > 0 and price_slope <= 0:
            return 0.0
        if cnfb_slope != 0:
            return 0.5
        return 0.5

    def _foreign_vwap_distance(
        self, flows: list[BrokerDailyFlow], candles: list[Candle]
    ) -> float | None:
        foreign = self._foreign_flows(flows)
        threshold = self._config.min_sessions.get("vwap_20d", 10)
        return self._vwap_distance(
            foreign, candles, self._config.foreign_vwap_days, threshold
        )

    def _domestic_vwap_distance(
        self, flows: list[BrokerDailyFlow], current_price: float | None
    ) -> float | None:
        local = self._local_flows(flows)
        threshold = self._config.min_sessions.get("vwap_20d", 10)
        return self._vwap_distance_from_price(
            local, current_price, self._config.domestic_vwap_days, threshold
        )

    def _vwap_distance(
        self,
        flows: list[BrokerDailyFlow],
        candles: list[Candle],
        window: int,
        threshold: int,
    ) -> float | None:
        current_price = float(candles[-1].close) if candles else None
        return self._vwap_distance_from_price(
            flows, current_price, window, threshold
        )

    def _vwap_distance_from_price(
        self,
        flows: list[BrokerDailyFlow],
        current_price: float | None,
        window: int,
        threshold: int,
    ) -> float | None:
        if current_price is None:
            raise _Unavailable("no_current_price")
        by_date = _group_by_date(flows)
        recent = sorted(by_date)[-window:]
        total_value = 0.0
        total_shares = 0.0
        valid_sessions = 0
        for d in recent:
            session_value = 0.0
            session_shares = 0.0
            counted = False
            for flow in by_date[d]:
                buy_value = float(flow.buy_value)
                avg_price = float(flow.avg_buy_price)
                if buy_value <= 0 or avg_price <= 0:
                    continue
                session_value += buy_value
                session_shares += buy_value / avg_price
                counted = True
            if counted:
                total_value += session_value
                total_shares += session_shares
                valid_sessions += 1
        if valid_sessions < threshold or total_shares <= 0:
            raise _Unavailable("insufficient_vwap_sessions")
        vwap = total_value / total_shares
        score = _vwap_distance_score(current_price, vwap)
        if score is None:
            raise _Unavailable("invalid_vwap")
        return score

    def _broker_consistency(self, flows: list[BrokerDailyFlow]) -> float | None:
        local = self._local_flows(flows)
        if not local:
            raise _Unavailable("no_local_flows")
        window = max(self._config.broker_consistency_days)
        by_date = _group_by_date(local)
        recent = sorted(by_date)[-window:]
        threshold = self._config.min_sessions.get("broker_consistency", 8)
        if len(recent) < threshold:
            raise _Unavailable("insufficient_consistency_sessions")
        top3 = self._top_brokers_by_net(local, recent, count=3)
        if not top3:
            raise _Unavailable("no_top_brokers")
        aligned = 0
        for d in recent:
            net_by_broker = self._net_by_broker(by_date[d])
            if all(net_by_broker.get(code, 0.0) > 0 for code in top3):
                aligned += 1
        return _clamp01(aligned / len(recent))

    def _broker_reversal(self, flows: list[BrokerDailyFlow]) -> float | None:
        local = self._local_flows(flows)
        if not local:
            raise _Unavailable("no_local_flows")
        window = min(self._config.broker_consistency_days)
        by_date = _group_by_date(local)
        recent = sorted(by_date)[-window:]
        if len(recent) < 5:
            raise _Unavailable("insufficient_reversal_sessions")
        half = len(recent) // 2
        early_dates = set(recent[:half])
        late_dates = set(recent[half:])
        top10 = self._top_brokers_by_volume(local, recent, count=10)
        if not top10:
            raise _Unavailable("no_top_brokers")
        early_net: dict[str, float] = {}
        late_net: dict[str, float] = {}
        for d in recent:
            for flow in by_date[d]:
                code = flow.broker_code.upper()
                if code not in top10:
                    continue
                if d in early_dates:
                    early_net[code] = early_net.get(code, 0.0) + float(flow.net_value)
                elif d in late_dates:
                    late_net[code] = late_net.get(code, 0.0) + float(flow.net_value)
        flipped = sum(
            1
            for code in top10
            if early_net.get(code, 0.0) < 0 and late_net.get(code, 0.0) > 0
        )
        return _clamp01(flipped / len(top10))

    def _accumulation_session_ratio(
        self, flows: list[BrokerDailyFlow]
    ) -> float | None:
        local = self._local_flows(flows)
        if not local:
            raise _Unavailable("no_local_flows")
        window = max(self._config.broker_consistency_days)
        by_date = _group_by_date(local)
        recent = sorted(by_date)[-window:]
        if not recent:
            raise _Unavailable("no_sessions")
        top3 = self._top_brokers_by_net(local, recent, count=3)
        if not top3:
            raise _Unavailable("no_top_brokers")
        buying_sessions = 0
        for d in recent:
            net_by_broker = self._net_by_broker(by_date[d])
            collective = sum(net_by_broker.get(code, 0.0) for code in top3)
            if collective > 0:
                buying_sessions += 1
        return _clamp01(buying_sessions / len(recent))

    def _broker_hhi_divergence(self, flows: list[BrokerDailyFlow]) -> float | None:
        by_date = _group_by_date(flows)
        recent = sorted(by_date)[-5:]
        if len(recent) < 3:
            raise _Unavailable("insufficient_hhi_sessions")
        buy_hhi: list[float] = []
        sell_hhi: list[float] = []
        for d in recent:
            session = by_date[d]
            total_buy = sum(float(f.buy_value) for f in session)
            total_sell = sum(float(f.sell_value) for f in session)
            if total_buy > 0:
                buy_hhi.append(
                    sum((float(f.buy_value) / total_buy) ** 2 for f in session)
                )
            if total_sell > 0:
                sell_hhi.append(
                    sum((float(f.sell_value) / total_sell) ** 2 for f in session)
                )
        if len(buy_hhi) < 3 or len(sell_hhi) < 3:
            raise _Unavailable("insufficient_hhi_sides")
        buy_slope = _slope(buy_hhi)
        sell_slope = _slope(sell_hhi)
        if buy_slope > 0 and sell_slope <= 0:
            return 1.0
        if buy_slope > 0 and sell_slope > 0:
            return 0.5
        return 0.0

    def _bandar_normalise(
        self,
        snapshot: BandarDetectorSnapshot | None,
        unavailable: list[str],
    ) -> tuple[float | None, float | None]:
        if snapshot is None:
            unavailable.append("bandar_snapshot_unavailable")
            return None, None
        try:
            broad = _clamp01((float(snapshot.broad_score) + 12.0) / 24.0)
            accum = _clamp01((float(snapshot.accumulation_score) + 6.0) / 12.0)
            return broad, accum
        except Exception as exc:
            unavailable.append(f"bandar_normalise_failed:{exc}")
            return None, None

    def _counterparty_hhi(
        self, flows: list[BrokerDailyFlow]
    ) -> CounterpartyTransferEvidence:
        by_date = _group_by_date(flows)
        recent = sorted(by_date)[-self._config.counterparty_window_days:]
        net_buy: dict[str, float] = {}
        net_sell: dict[str, float] = {}
        for d in recent:
            for flow in by_date[d]:
                code = flow.broker_code.upper()
                net = float(flow.net_value)
                net_buy[code] = net_buy.get(code, 0.0) + max(net, 0.0)
                net_sell[code] = net_sell.get(code, 0.0) + abs(min(net, 0.0))
        total_net_buy = sum(net_buy.values())
        total_net_sell = sum(net_sell.values())
        if total_net_buy <= 0 or total_net_sell <= 0:
            return CounterpartyTransferEvidence(
                transfer_asymmetry_score=None,
                buy_side_hhi=None,
                sell_side_hhi=None,
                coverage_score=0.0,
                conviction_score=0.0,
                evidence_status=self._config.evidence_status,
                unavailable_reasons=("zero_net_buy_or_sell",),
            )
        buy_hhi = sum((v / total_net_buy) ** 2 for v in net_buy.values())
        sell_hhi = sum((v / total_net_sell) ** 2 for v in net_sell.values())
        raw_asymmetry = buy_hhi - sell_hhi
        transfer = _clamp01((raw_asymmetry + 1.0) / 2.0)
        return CounterpartyTransferEvidence(
            transfer_asymmetry_score=round(transfer, 4),
            buy_side_hhi=round(buy_hhi, 6),
            sell_side_hhi=round(sell_hhi, 6),
            coverage_score=1.0,
            conviction_score=round(transfer, 4),
            evidence_status=self._config.evidence_status,
            unavailable_reasons=(),
        )

    # =================================================================== #
    # Broker helpers
    # =================================================================== #
    def _is_foreign(self, broker_code: str) -> bool:
        return broker_code.upper() in self._foreign_codes

    def _foreign_flows(
        self, flows: list[BrokerDailyFlow]
    ) -> list[BrokerDailyFlow]:
        return [f for f in flows if self._is_foreign(f.broker_code)]

    def _local_flows(self, flows: list[BrokerDailyFlow]) -> list[BrokerDailyFlow]:
        return [f for f in flows if not self._is_foreign(f.broker_code)]

    @staticmethod
    def _net_by_broker(session: list[BrokerDailyFlow]) -> dict[str, float]:
        result: dict[str, float] = {}
        for flow in session:
            code = flow.broker_code.upper()
            result[code] = result.get(code, 0.0) + float(flow.net_value)
        return result

    @staticmethod
    def _top_brokers_by_net(
        flows: list[BrokerDailyFlow],
        dates: list[date],
        *,
        count: int,
    ) -> list[str]:
        date_set = set(dates)
        totals: dict[str, float] = {}
        for flow in flows:
            if flow.date not in date_set:
                continue
            code = flow.broker_code.upper()
            totals[code] = totals.get(code, 0.0) + float(flow.net_value)
        ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
        return [code for code, _ in ranked[:count]]

    @staticmethod
    def _top_brokers_by_volume(
        flows: list[BrokerDailyFlow],
        dates: list[date],
        *,
        count: int,
    ) -> set[str]:
        date_set = set(dates)
        totals: dict[str, float] = {}
        for flow in flows:
            if flow.date not in date_set:
                continue
            code = flow.broker_code.upper()
            volume = float(flow.buy_value) + float(flow.sell_value)
            totals[code] = totals.get(code, 0.0) + volume
        ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
        return {code for code, _ in ranked[:count]}

    @staticmethod
    def _mean_available(values: list[float | None]) -> float | None:
        present = [v for v in values if v is not None]
        if not present:
            return None
        return _clamp01(sum(present) / len(present))

    # =================================================================== #
    # Graceful-degradation wrappers
    # =================================================================== #
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


class _Unavailable(Exception):
    """Signals a metric could not be computed (expected, not an error)."""
