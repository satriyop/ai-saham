"""
CompositeSignalScore — immutable value object combining 6 enrichment signals into a 0–100 score.

Aggregates:
  - Bandar detector (institutional operator accumulation/distribution)
  - Foreign flow accumulation quality (normalized from AccumulationCandidate.score)
  - Piotroski F-Score (fundamental quality gate)
  - Seasonality (current-month historical edge)
  - Analyst consensus (buy% + price target upside)
  - Forward EPS valuation (forward P/E attractiveness)

Weights:
  bandar        20% — Stockbit institutional signal
  foreign_flow  20% — consistency × streak × VWAP × BCI
  piotroski     20% — fundamental health (0–9 F-score)
  seasonality   15% — monthly historical win rate + direction
  analyst       15% — buy% + target upside
  forward_eps   10% — forward P/E valuation attractiveness

Layer: Domain
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompositeSignalScore:
    """Weighted composite signal (0–100) across 6 enrichment dimensions.

    Each component is independently normalized to 0–100.
    Missing data defaults to 50 (neutral) so partial data still produces useful scores.
    """

    ticker: str

    # Component scores — each normalized 0–100
    bandar: float         # Institutional operator accumulation intensity
    foreign_flow: float   # Foreign flow quality (from existing accumulation score)
    piotroski: float      # Piotroski F-Score fundamental quality
    seasonality: float    # Current-month seasonal edge (win rate × direction)
    analyst: float        # Analyst buy% + target upside
    forward_eps: float    # Forward P/E valuation attractiveness

    # Component availability flags (False = defaulted to neutral 50)
    has_bandar: bool
    has_piotroski: bool
    has_seasonality: bool
    has_analyst: bool
    has_forward_eps: bool

    # Final weighted composite (0–100)
    total: float

    # Weights used (sum to 1.0)
    BANDAR_W: float = 0.20
    FOREIGN_W: float = 0.20
    PIOTROSKI_W: float = 0.20
    SEASONALITY_W: float = 0.15
    ANALYST_W: float = 0.15
    FORWARD_EPS_W: float = 0.10

    @property
    def is_high_conviction(self) -> bool:
        """True when ≥4 of 6 components score above 60 (broad agreement)."""
        return sum(
            1 for s in [self.bandar, self.foreign_flow, self.piotroski,
                        self.seasonality, self.analyst, self.forward_eps]
            if s >= 60.0
        ) >= 4

    @property
    def label(self) -> str:
        sign = "★" if self.is_high_conviction else "·"
        return f"{self.total:.0f}{sign}"

    def breakdown_label(self) -> str:
        """Compact per-component breakdown for detail lines."""
        return (
            f"[ban={self.bandar:.0f} ff={self.foreign_flow:.0f}"
            f" pio={self.piotroski:.0f} sea={self.seasonality:.0f}"
            f" ana={self.analyst:.0f} fwd={self.forward_eps:.0f}]"
        )

    def to_dict(self) -> dict:
        return {
            "total": round(self.total, 1),
            "bandar": round(self.bandar, 1),
            "foreign_flow": round(self.foreign_flow, 1),
            "piotroski": round(self.piotroski, 1),
            "seasonality": round(self.seasonality, 1),
            "analyst": round(self.analyst, 1),
            "forward_eps": round(self.forward_eps, 1),
            "is_high_conviction": self.is_high_conviction,
            "has_bandar": self.has_bandar,
            "has_piotroski": self.has_piotroski,
            "has_seasonality": self.has_seasonality,
            "has_analyst": self.has_analyst,
            "has_forward_eps": self.has_forward_eps,
        }
