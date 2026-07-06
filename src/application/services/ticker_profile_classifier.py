"""TickerProfileClassifier — application service (Phase F).

Computes deterministic per-ticker behavior diagnostics from candles, broker
flows, broker summaries, market-cap, and index membership. The primary profile
is a soft-exposure winner (`foreign_institutional`, `domestic_bandar`,
`retail_speculative`, or `unclassified` for sparse history); the market tier is
reported separately (`blue_chip`, `second_liner`, `third_liner`, `speculative`,
or `unknown`).

DIAGNOSTIC-ONLY: the resulting TickerProfileSnapshot is persisted and reported
for replay attribution and human inspection. It is NEVER fed into SignalEngine
scoring or DecisionPolicy.

Design invariants:
- The classifier NEVER fetches data. All inputs arrive on the request, except
  index membership which is resolved internally from config/universes.yaml at
  construction time (reverse index built once).
- The classifier NEVER raises. Every dimension computation degrades to a None
  score with an unavailable reason; an unhandled error degrades the whole
  snapshot to a minimal fallback with metadata["error"].
- evidence_status is always DIAGNOSTIC in this phase.

Layer: Application. Depends only on domain entities/VOs + stdlib + PyYAML.
No provider/repository/CLI imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from src.application.services.institutional_accumulation_evidence_builder import (
    DEFAULT_FOREIGN_BROKER_CODES,
)
from src.domain.entities.broker_flow import BrokerDailyFlow, BrokerSummary
from src.domain.entities.candle import Candle
from src.domain.value_objects.institutional_accumulation_evidence import EvidenceStatus
from src.domain.value_objects.ticker_profile_snapshot import TickerProfileSnapshot

# --------------------------------------------------------------------------- #
# Only these universe keys represent index membership. Sector and business-group
# universes (bank, energy, bumn20, ...) are intentionally excluded.
# --------------------------------------------------------------------------- #
_INDEX_UNIVERSE_KEYS: frozenset[str] = frozenset(
    {"lq45", "idx30", "idx80", "jii", "mbx"}
)

_DEFAULT_PROFILE_CONFIG_PATH = (
    Path(__file__).parent.parent.parent.parent / "config" / "ticker_profile.yaml"
)
_DEFAULT_UNIVERSES_PATH = (
    Path(__file__).parent.parent.parent.parent / "config" / "universes.yaml"
)


# --------------------------------------------------------------------------- #
# Request / config dataclasses
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class TickerProfileRequest:
    ticker: str
    snapshot_date: date
    candles: tuple[Candle, ...]
    broker_daily_flows: tuple[BrokerDailyFlow, ...]
    broker_summaries: tuple[BrokerSummary, ...]
    market_cap_idr: Decimal | None
    sector: str | None
    sub_sector: str | None


@dataclass(frozen=True)
class TickerProfileConfig:
    evidence_status: EvidenceStatus
    profile_window_days: int
    market_cap_large: int
    market_cap_mid: int
    market_cap_small: int
    index_membership_scores: dict[str, float]
    liquidity_high: float
    liquidity_low: float
    volatility_high: float
    volatility_low: float
    sparse_history_threshold: int
    conservative_fallback_confidence: float
    exposure_weights: dict[str, dict[str, float]] = field(default_factory=dict)

    def validate(self) -> None:
        for name, score in self.index_membership_scores.items():
            if not 0.0 <= float(score) <= 1.0:
                raise ValueError(
                    f"index_membership_score for {name} must be in [0,1]"
                )
        for profile, weights in self.exposure_weights.items():
            if not weights:
                continue
            total = 0.0
            for dim, weight in weights.items():
                weight_float = float(weight)
                if weight_float < 0.0:
                    raise ValueError(
                        f"exposure weight {profile}.{dim} must be non-negative"
                    )
                total += weight_float
            if abs(total - 1.0) > 0.0001:
                raise ValueError(
                    f"exposure weights for {profile} must sum to 1.0, got {total:.4f}"
                )

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "TickerProfileConfig":
        block = raw.get("ticker_profile", raw)
        caps = block.get("market_cap_thresholds_idr", {}) or {}
        liq = block.get("liquidity_thresholds", {}) or {}
        vol = block.get("volatility_thresholds", {}) or {}
        status = EvidenceStatus(block.get("evidence_status", "DIAGNOSTIC"))
        return cls(
            evidence_status=status,
            profile_window_days=int(block.get("profile_window_days", 30)),
            market_cap_large=int(caps.get("large", 10_000_000_000_000)),
            market_cap_mid=int(caps.get("mid", 1_000_000_000_000)),
            market_cap_small=int(caps.get("small", 200_000_000_000)),
            index_membership_scores={
                str(k): float(v)
                for k, v in (block.get("index_membership_scores") or {}).items()
            },
            liquidity_high=float(liq.get("high_daily_value_idr", 50_000_000_000)),
            liquidity_low=float(liq.get("low_daily_value_idr", 500_000_000)),
            volatility_high=float(vol.get("high_atr_pct", 0.050)),
            volatility_low=float(vol.get("low_atr_pct", 0.005)),
            sparse_history_threshold=int(block.get("sparse_history_threshold", 10)),
            conservative_fallback_confidence=float(
                block.get("conservative_fallback_confidence", 0.30)
            ),
            exposure_weights={
                str(profile): {
                    str(dim): float(weight)
                    for dim, weight in (dims or {}).items()
                }
                for profile, dims in (block.get("exposure_weights") or {}).items()
            },
        )


# --------------------------------------------------------------------------- #
# Small numeric helpers
# --------------------------------------------------------------------------- #
def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _saturating(value: float, low: float, high: float) -> float:
    """Saturating linear map: <=low -> 0.0, >=high -> 1.0, linear in between."""
    if high <= low:
        return 0.0
    if value >= high:
        return 1.0
    if value <= low:
        return 0.0
    return _clamp01((value - low) / (high - low))


def _compute_exposures(
    liquidity: float | None,
    broker_concentration: float | None,
    foreign_flow: float | None,
    volatility: float | None,
    index_membership: float | None,  # already 0.0 minimum, never None
    market_cap_bucket: str | None,
    weights: dict,
) -> tuple[float, float, float]:
    """Return a simplex (fi, db, rs) of soft behavioral exposures summing to 1.0.

    Missing optional dimensions degrade to a neutral 0.5. index_membership is
    already a float (0.0 minimum). Weights fall back to canonical defaults when
    absent from config, so an empty ``weights`` mapping is valid.
    """
    # neutral 0.5 for missing optional dims; index_membership is 0.0 minimum
    liq = liquidity if liquidity is not None else 0.5
    bc = broker_concentration if broker_concentration is not None else 0.5
    ff = foreign_flow if foreign_flow is not None else 0.5
    vol = volatility if volatility is not None else 0.5
    im = index_membership if index_membership is not None else 0.0

    # market cap scores
    mc_spec = {"large": 0.0, "mid": 0.2, "small": 0.7, "micro": 1.0}.get(
        market_cap_bucket or "", 0.5
    )

    w_fi = weights.get("foreign_institutional", {})
    fi_raw = (
        ff * w_fi.get("foreign_flow", 0.35)
        + im * w_fi.get("index_membership", 0.30)
        + liq * w_fi.get("liquidity", 0.20)
        + (1.0 - bc) * w_fi.get("broker_concentration_inverse", 0.15)
    )

    w_db = weights.get("domestic_bandar", {})
    db_raw = (
        bc * w_db.get("broker_concentration", 0.45)
        + (1.0 - ff) * w_db.get("foreign_flow_inverse", 0.35)
        + liq * w_db.get("liquidity", 0.20)
    )

    w_rs = weights.get("retail_speculative", {})
    rs_raw = (
        vol * w_rs.get("volatility", 0.40)
        + (1.0 - liq) * w_rs.get("liquidity_inverse", 0.35)
        + mc_spec * w_rs.get("market_cap_speculative", 0.25)
    )

    total = fi_raw + db_raw + rs_raw
    if total == 0:
        return 1 / 3, 1 / 3, 1 / 3
    return fi_raw / total, db_raw / total, rs_raw / total


class TickerProfileClassifier:
    """Builds a diagnostic TickerProfileSnapshot from per-ticker market data."""

    def __init__(
        self,
        config: TickerProfileConfig,
        ticker_universe_index: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        self._config = config
        self._config.validate()
        self._universe_index = ticker_universe_index or {}

    # ---------------------------------------------------------------- config
    @classmethod
    def from_yaml(
        cls,
        profile_path: str | Path | None = None,
        universes_path: str | Path | None = None,
    ) -> "TickerProfileClassifier":
        profile = (
            Path(profile_path) if profile_path is not None
            else _DEFAULT_PROFILE_CONFIG_PATH
        )
        universes = (
            Path(universes_path) if universes_path is not None
            else _DEFAULT_UNIVERSES_PATH
        )
        with open(profile, "r") as handle:
            raw = yaml.safe_load(handle) or {}
        config = TickerProfileConfig.from_mapping(raw)
        index = cls._build_universe_index(universes)
        return cls(config, ticker_universe_index=index)

    @staticmethod
    def _build_universe_index(
        universes_path: Path,
    ) -> dict[str, tuple[str, ...]]:
        reverse: dict[str, list[str]] = {}
        if not universes_path.exists():
            return {}
        with open(universes_path, "r") as handle:
            data = yaml.safe_load(handle) or {}
        for key, block in data.items():
            if key not in _INDEX_UNIVERSE_KEYS:
                continue
            if not isinstance(block, dict):
                continue
            for ticker in block.get("tickers") or []:
                code = str(ticker).upper()
                bucket = reverse.setdefault(code, [])
                if key not in bucket:
                    bucket.append(key)
        return {code: tuple(keys) for code, keys in reverse.items()}

    # ------------------------------------------------------------ public API
    def classify(self, request: TickerProfileRequest) -> TickerProfileSnapshot:
        try:
            return self._classify(request)
        except Exception as exc:  # pragma: no cover - defensive last resort
            return self._minimal_fallback(request, error=str(exc))

    # -------------------------------------------------------------- classify
    def _classify(self, request: TickerProfileRequest) -> TickerProfileSnapshot:
        ticker = request.ticker.upper().strip()
        candles_sorted = sorted(request.candles, key=lambda c: c.date)
        window = self._config.profile_window_days
        candle_window = candles_sorted[-window:]

        unavailable: list[str] = []

        liquidity_score = self._safe(
            lambda: self._liquidity(candle_window), "liquidity", unavailable
        )
        broker_concentration_score = self._safe(
            lambda: self._broker_concentration(request.broker_daily_flows, window),
            "broker_concentration",
            unavailable,
        )
        foreign_flow_score = self._safe(
            lambda: self._foreign_flow(request.broker_summaries, window),
            "foreign_flow",
            unavailable,
        )
        volatility_score = self._safe(
            lambda: self._volatility(candle_window), "volatility", unavailable
        )

        # Index membership is always resolvable (0.0 when in no index). Even on
        # error we fall back to 0.0 so the dimension is never None.
        memberships: tuple[str, ...] = ()
        try:
            memberships = self._universe_index.get(ticker, ())
            index_membership_score: float | None = self._index_membership(
                memberships
            )
        except Exception as exc:  # noqa: BLE001 - never let membership kill build
            index_membership_score = 0.0
            unavailable.append(f"index_membership_failed:{exc}")

        market_cap_bucket = self._market_cap_bucket(request.market_cap_idr)

        # ----- coverage: 5 slots; index membership always counts.
        slots = [
            liquidity_score is not None,
            broker_concentration_score is not None,
            foreign_flow_score is not None,
            volatility_score is not None,
            index_membership_score is not None,
        ]
        coverage_score = round(sum(1 for s in slots if s) / len(slots), 4)

        # ----- soft behavioral exposures (simplex over the three profiles)
        fi_exp, db_exp, rs_exp = _compute_exposures(
            liquidity=liquidity_score,
            broker_concentration=broker_concentration_score,
            foreign_flow=foreign_flow_score,
            volatility=volatility_score,
            index_membership=index_membership_score,
            market_cap_bucket=market_cap_bucket,
            weights=self._config.exposure_weights,
        )
        exposures = {
            "foreign_institutional": fi_exp,
            "domestic_bandar": db_exp,
            "retail_speculative": rs_exp,
        }
        primary_profile = max(exposures, key=lambda k: exposures[k])

        # ----- market tier + confidence (deterministic, priority order)
        sparse = len(candles_sorted) < self._config.sparse_history_threshold
        if sparse:
            market_tier = "unknown"
            primary_profile = "unclassified"
            fi_exp = 0.0
            db_exp = 0.5
            rs_exp = 0.5
            profile_confidence = self._config.conservative_fallback_confidence
            unavailable.append("sparse_history")
        else:
            market_tier = self._profile_label(
                index_membership_score,
                market_cap_bucket,
                liquidity_score,
                volatility_score,
            )
            # confidence = margin between primary and second-best exposure
            ranked = sorted((fi_exp, db_exp, rs_exp), reverse=True)
            profile_confidence = round(ranked[0] - ranked[1], 4)

        metadata: dict[str, Any] = {"diagnostic_only": True}

        return TickerProfileSnapshot(
            ticker=ticker,
            snapshot_date=request.snapshot_date,
            epoch=request.snapshot_date.strftime("%Y-%m"),
            primary_profile=primary_profile,
            profile_confidence=_clamp01(profile_confidence),
            liquidity_score=liquidity_score,
            broker_concentration_score=broker_concentration_score,
            foreign_flow_score=foreign_flow_score,
            volatility_score=volatility_score,
            index_membership_score=index_membership_score,
            market_cap_bucket=market_cap_bucket,
            sector=request.sector,
            sub_sector=request.sub_sector,
            index_memberships=tuple(memberships),
            coverage_score=coverage_score,
            evidence_status=self._config.evidence_status,
            reasons=(),
            unavailable_reasons=tuple(unavailable),
            market_tier=market_tier,
            foreign_institutional_exposure=round(fi_exp, 4),
            domestic_bandar_exposure=round(db_exp, 4),
            retail_speculative_exposure=round(rs_exp, 4),
            metadata=metadata,
        )

    # =================================================================== #
    # Dimension computations
    # =================================================================== #
    def _liquidity(self, candles: list[Candle]) -> float | None:
        values: list[float] = []
        for candle in candles:
            volume = float(candle.volume)
            if volume == 0:
                continue
            values.append(float(candle.high) * volume)
        if not values:
            raise _Unavailable("no_valid_candles")
        mean_value = _mean(values)
        return _saturating(
            mean_value, self._config.liquidity_low, self._config.liquidity_high
        )

    def _broker_concentration(
        self, flows: tuple[BrokerDailyFlow, ...], window: int
    ) -> float | None:
        recent = self._flows_in_window(flows, window)
        by_broker: dict[str, float] = {}
        for flow in recent:
            code = flow.broker_code.upper()
            if code in DEFAULT_FOREIGN_BROKER_CODES:
                continue
            by_broker[code] = by_broker.get(code, 0.0) + float(flow.buy_value)
        total_local_buy = sum(by_broker.values())
        if total_local_buy <= 0:
            raise _Unavailable("zero_local_buy_value")
        hhi = sum((v / total_local_buy) ** 2 for v in by_broker.values())
        return _clamp01(hhi)

    def _foreign_flow(
        self, summaries: tuple[BrokerSummary, ...], window: int
    ) -> float | None:
        ordered = sorted(summaries, key=lambda s: s.date)[-window:]
        ratios: list[float] = []
        for summary in ordered:
            total = float(summary.total_value)
            if total == 0:
                continue
            ratio = (
                float(summary.foreign_buy_value)
                + float(summary.foreign_sell_value)
            ) / total
            ratios.append(ratio)
        if not ratios:
            raise _Unavailable("no_valid_sessions")
        return _clamp01(_mean(ratios))

    def _volatility(self, candles: list[Candle]) -> float | None:
        # True ATR: TR = max(high-low, |high-prev_close|, |low-prev_close|),
        # normalized by prev_close. Needs at least two consecutive candles.
        candles_sorted = sorted(candles, key=lambda c: c.date)
        if len(candles_sorted) < 2:
            raise _Unavailable("insufficient_candles_for_atr")
        true_ranges: list[float] = []
        for i in range(1, len(candles_sorted)):
            prev_close = float(candles_sorted[i - 1].close)
            if prev_close == 0:
                continue
            high = float(candles_sorted[i].high)
            low = float(candles_sorted[i].low)
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            true_ranges.append(tr / prev_close)
        if not true_ranges:
            raise _Unavailable("no_valid_candles")
        mean_tr = _mean(true_ranges)
        return _saturating(
            mean_tr, self._config.volatility_low, self._config.volatility_high
        )

    def _index_membership(self, memberships: tuple[str, ...]) -> float:
        if not memberships:
            return 0.0
        scores = self._config.index_membership_scores
        return max(scores.get(name, 0.0) for name in memberships)

    def _market_cap_bucket(self, market_cap_idr: Any) -> str | None:
        if market_cap_idr is None:
            return None
        cap = float(market_cap_idr)
        if cap >= self._config.market_cap_large:
            return "large"
        if cap >= self._config.market_cap_mid:
            return "mid"
        if cap >= self._config.market_cap_small:
            return "small"
        return "micro"

    # =================================================================== #
    # Profile label (deterministic priority order)
    # =================================================================== #
    @staticmethod
    def _profile_label(
        index_membership_score: float | None,
        market_cap_bucket: str | None,
        liquidity_score: float | None,
        volatility_score: float | None,
    ) -> str:
        if (
            index_membership_score is not None
            and index_membership_score >= 0.95
            and market_cap_bucket == "large"
        ):
            return "blue_chip"
        if (
            index_membership_score is not None and index_membership_score >= 0.75
        ) or market_cap_bucket == "mid":
            return "second_liner"
        if (
            liquidity_score is not None
            and liquidity_score < 0.2
            and volatility_score is not None
            and volatility_score > 0.7
        ):
            return "speculative"
        if market_cap_bucket in ("small", "micro") or index_membership_score == 0.0:
            return "third_liner"
        return "unknown"

    # =================================================================== #
    # Helpers
    # =================================================================== #
    @staticmethod
    def _flows_in_window(
        flows: tuple[BrokerDailyFlow, ...], window: int
    ) -> list[BrokerDailyFlow]:
        if not flows:
            return []
        dates = sorted({flow.date for flow in flows})[-window:]
        keep = set(dates)
        return [flow for flow in flows if flow.date in keep]

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

    def _minimal_fallback(
        self, request: TickerProfileRequest, *, error: str
    ) -> TickerProfileSnapshot:
        ticker = (getattr(request, "ticker", "") or "UNKNOWN")
        ticker = str(ticker).upper().strip() or "UNKNOWN"
        snap_date = getattr(request, "snapshot_date", None) or date.today()
        return TickerProfileSnapshot(
            ticker=ticker,
            snapshot_date=snap_date,
            epoch=snap_date.strftime("%Y-%m"),
            primary_profile="unknown",
            profile_confidence=0.0,
            liquidity_score=None,
            broker_concentration_score=None,
            foreign_flow_score=None,
            volatility_score=None,
            index_membership_score=None,
            market_cap_bucket=None,
            sector=getattr(request, "sector", None),
            sub_sector=getattr(request, "sub_sector", None),
            index_memberships=(),
            coverage_score=0.0,
            evidence_status=self._config.evidence_status,
            reasons=(),
            unavailable_reasons=("classify_failed",),
            market_tier=None,
            foreign_institutional_exposure=None,
            domestic_bandar_exposure=None,
            retail_speculative_exposure=None,
            metadata={"diagnostic_only": True, "error": error},
        )


class _Unavailable(Exception):
    """Signals a dimension could not be computed (expected, not an error)."""
