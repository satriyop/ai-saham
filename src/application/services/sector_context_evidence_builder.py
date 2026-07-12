"""SectorContextEvidenceBuilder — application service (Phase H).

Computes local-universe sector context diagnostics: sector-relative return,
sector breadth, and ticker-vs-sector relative strength.

Design invariants:
- The builder NEVER fetches data. All inputs arrive on the request.
- The sector reverse index (universe_group -> tickers) is supplied at
  construction time by infrastructure, which owns parsing universes.yaml.
- The builder NEVER raises. Every metric computation degrades to None with an
  unavailable reason; an unhandled error degrades the whole snapshot with
  metadata["error"].
- evidence_status is always DIAGNOSTIC in Phase H.

Layer: Application. Depends only on domain entities/VOs + stdlib.
No provider/repository/CLI imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from src.domain.entities.candle import Candle
from src.domain.value_objects.institutional_accumulation_evidence import EvidenceStatus
from src.domain.value_objects.sector_context_evidence import SectorContextEvidence

# --------------------------------------------------------------------------- #
# Config dataclass
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class SectorContextConfig:
    evidence_status: EvidenceStatus
    min_peer_count: int
    max_peer_count: int
    lookback_sessions: int
    min_valid_sessions_per_peer: int
    bullish_sector_vs_ihsg_min: float
    bullish_breadth_min: float
    bearish_sector_vs_ihsg_max: float
    bearish_breadth_max: float

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "SectorContextConfig":
        thresholds = raw.get("sector_regime_thresholds", {}) or {}
        bullish = thresholds.get("bullish", {}) or {}
        bearish = thresholds.get("bearish", {}) or {}
        return cls(
            evidence_status=EvidenceStatus(
                raw.get("evidence_status", EvidenceStatus.DIAGNOSTIC.value)
            ),
            min_peer_count=int(raw.get("min_peer_count", 3)),
            max_peer_count=int(raw.get("max_peer_count", 20)),
            lookback_sessions=int(raw.get("lookback_sessions", 20)),
            min_valid_sessions_per_peer=int(raw.get("min_valid_sessions_per_peer", 15)),
            bullish_sector_vs_ihsg_min=float(bullish.get("sector_vs_ihsg_min", 0.01)),
            bullish_breadth_min=float(bullish.get("breadth_min", 0.55)),
            bearish_sector_vs_ihsg_max=float(bearish.get("sector_vs_ihsg_max", -0.01)),
            bearish_breadth_max=float(bearish.get("breadth_max", 0.45)),
        )


# --------------------------------------------------------------------------- #
# Request dataclass
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class SectorContextRequest:
    ticker: str
    snapshot_date: date
    sector: str | None                         # from ticker metadata (StockMeta / TickerNotation)
    ticker_candles: tuple[Candle, ...]         # candles for the target ticker
    peer_candles: dict[str, list[Candle]]      # {peer_ticker: [Candle, ...]}; may be empty
    ihsg_20d_return: float | None              # IHSG 20-session return; None when unavailable


# --------------------------------------------------------------------------- #
# Builder
# --------------------------------------------------------------------------- #

class SectorContextEvidenceBuilder:
    """Build SectorContextEvidence from local candle data.

    The sector reverse index (universe_group → tickers) is supplied at
    construction time by an infrastructure loader. The workflow calls
    `peers_for_group` to retrieve peer tickers before fetching their candles
    and submitting a SectorContextRequest.
    """

    def __init__(
        self,
        config: SectorContextConfig,
        sector_universe_index: dict[str, tuple[str, ...]],
    ) -> None:
        self._config = config
        # {universe_group_name: (ticker, ...)} for non-index groups only
        self._sector_index = sector_universe_index

    # --------------------------------------------------------- public helpers

    def sector_group_for_ticker(self, ticker: str) -> str | None:
        """Return the universe group name that contains this ticker, or None."""
        upper = ticker.upper()
        for group, tickers in self._sector_index.items():
            if upper in tickers:
                return group
        return None

    def peers_for_ticker(self, ticker: str) -> tuple[str, ...]:
        """Return same-sector peer tickers (excluding the ticker itself), capped."""
        upper = ticker.upper()
        group = self.sector_group_for_ticker(upper)
        if group is None:
            return ()
        peers = tuple(t for t in self._sector_index[group] if t != upper)
        return peers[: self._config.max_peer_count]

    # --------------------------------------------------------- main build

    def build(self, request: SectorContextRequest) -> SectorContextEvidence:
        try:
            return self._build(request)
        except Exception as exc:
            return SectorContextEvidence(
                sector=request.sector,
                peer_count=0,
                peer_tickers=(),
                sector_20d_return=None,
                sector_vs_ihsg_20d=None,
                sector_breadth=None,
                ticker_vs_sector_rs=None,
                sector_regime="UNKNOWN",
                coverage_score=0.0,
                evidence_status=EvidenceStatus.DIAGNOSTIC,
                reasons=(),
                unavailable_reasons=(f"builder_error:{exc}",),
                metadata={"error": str(exc)},
            )

    def _build(self, request: SectorContextRequest) -> SectorContextEvidence:
        cfg = self._config
        unavailable: list[str] = []
        reasons: list[str] = []
        lookback = cfg.lookback_sessions

        # Compute ticker 20d return.
        ticker_20d_return = _compute_return(
            request.ticker_candles, lookback, cfg.min_valid_sessions_per_peer
        )
        if ticker_20d_return is None:
            unavailable.append("ticker_return:insufficient_candles")

        # Compute peer returns.
        peer_returns: list[float] = []
        valid_peers: list[str] = []
        for peer, candles in request.peer_candles.items():
            ret = _compute_return(candles, lookback, cfg.min_valid_sessions_per_peer)
            if ret is not None:
                peer_returns.append(ret)
                valid_peers.append(peer)

        peer_count = len(valid_peers)
        coverage_score = _coverage(peer_count, cfg.min_peer_count)

        if peer_count == 0:
            unavailable.append("sector_peers:no_valid_candles")
            return SectorContextEvidence(
                sector=request.sector,
                peer_count=0,
                peer_tickers=(),
                sector_20d_return=None,
                sector_vs_ihsg_20d=None,
                sector_breadth=None,
                ticker_vs_sector_rs=None,
                sector_regime="UNKNOWN",
                coverage_score=0.0,
                evidence_status=EvidenceStatus.DIAGNOSTIC,
                reasons=(),
                unavailable_reasons=tuple(unavailable),
            )

        # Equal-weight sector 20d return.
        sector_20d_return = sum(peer_returns) / len(peer_returns)
        reasons.append(
            f"sector_20d_return computed from {peer_count} peers"
        )

        # Sector breadth: fraction of peers with positive 20d return.
        sector_breadth = (
            sum(1 for r in peer_returns if r > 0.0) / len(peer_returns)
        )

        # Sector vs IHSG.
        sector_vs_ihsg_20d: float | None = None
        if request.ihsg_20d_return is not None:
            sector_vs_ihsg_20d = sector_20d_return - request.ihsg_20d_return
        else:
            unavailable.append("sector_vs_ihsg:ihsg_return_unavailable")

        # Ticker vs sector RS.
        ticker_vs_sector_rs: float | None = None
        if ticker_20d_return is not None:
            ticker_vs_sector_rs = ticker_20d_return - sector_20d_return

        # Sector regime classification.
        sector_regime = _classify_regime(
            sector_vs_ihsg_20d=sector_vs_ihsg_20d,
            sector_breadth=sector_breadth,
            bullish_sector_vs_ihsg_min=cfg.bullish_sector_vs_ihsg_min,
            bullish_breadth_min=cfg.bullish_breadth_min,
            bearish_sector_vs_ihsg_max=cfg.bearish_sector_vs_ihsg_max,
            bearish_breadth_max=cfg.bearish_breadth_max,
        )
        reasons.append(f"sector_regime:{sector_regime}")

        metadata: dict[str, Any] = {
            "peer_returns": {p: round(r, 6) for p, r in zip(valid_peers, peer_returns)},
            "ticker_20d_return": (
                round(ticker_20d_return, 6) if ticker_20d_return is not None else None
            ),
        }

        return SectorContextEvidence(
            sector=request.sector,
            peer_count=peer_count,
            peer_tickers=tuple(valid_peers),
            sector_20d_return=sector_20d_return,
            sector_vs_ihsg_20d=sector_vs_ihsg_20d,
            sector_breadth=sector_breadth,
            ticker_vs_sector_rs=ticker_vs_sector_rs,
            sector_regime=sector_regime,
            coverage_score=coverage_score,
            evidence_status=EvidenceStatus.DIAGNOSTIC,
            reasons=tuple(reasons),
            unavailable_reasons=tuple(unavailable),
            metadata=metadata,
        )


# --------------------------------------------------------------------------- #
# Private helpers
# --------------------------------------------------------------------------- #

def _compute_return(
    candles: tuple[Candle, ...] | list[Candle],
    lookback: int,
    min_valid: int,
) -> float | None:
    """Compute simple price return over the last `lookback` sessions.

    Returns None when fewer than `min_valid` candles are available or when
    the reference close is zero.
    """
    sorted_c = sorted(candles, key=lambda c: c.date)
    window = sorted_c[-lookback:] if len(sorted_c) >= lookback else sorted_c
    valid = [c for c in window if c.close and float(c.close) > 0]
    if len(valid) < min_valid:
        return None
    # Use the oldest and newest close in the valid window.
    ref = float(valid[0].close)
    if ref == 0.0:
        return None
    return (float(valid[-1].close) - ref) / ref


def _coverage(peer_count: int, min_peer_count: int) -> float:
    """Coverage score: peer_count / min_peer_count, capped at 1.0."""
    if min_peer_count <= 0:
        return 1.0 if peer_count > 0 else 0.0
    return min(1.0, peer_count / min_peer_count)


def _classify_regime(
    *,
    sector_vs_ihsg_20d: float | None,
    sector_breadth: float | None,
    bullish_sector_vs_ihsg_min: float,
    bullish_breadth_min: float,
    bearish_sector_vs_ihsg_max: float,
    bearish_breadth_max: float,
) -> str:
    """Classify sector regime from sector_vs_ihsg and breadth.

    Both criteria must be satisfied for BULLISH or BEARISH.
    UNKNOWN when sector_vs_ihsg_20d is unavailable.
    """
    if sector_breadth is None:
        return "UNKNOWN"
    if sector_vs_ihsg_20d is None:
        # Classify from breadth alone when IHSG return is unavailable.
        if sector_breadth >= bullish_breadth_min:
            return "NEUTRAL"    # bullish breadth but no IHSG context = NEUTRAL
        if sector_breadth <= bearish_breadth_max:
            return "NEUTRAL"    # bearish breadth but no IHSG context = NEUTRAL
        return "NEUTRAL"
    if (
        sector_vs_ihsg_20d >= bullish_sector_vs_ihsg_min
        and sector_breadth >= bullish_breadth_min
    ):
        return "BULLISH"
    if (
        sector_vs_ihsg_20d <= bearish_sector_vs_ihsg_max
        and sector_breadth <= bearish_breadth_max
    ):
        return "BEARISH"
    return "NEUTRAL"
