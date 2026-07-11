"""
PreOpenScreenConfig — screening parameters loaded from config YAML.

Layer: Application
"""

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class PreOpenScreenConfig:
    """Screening parameters, loaded from config YAML or overridden by CLI flags."""

    iev_min: int = 100_000
    capital: Decimal = Decimal("3000000")
    tick_above: int = 1
    stop_loss_pct: Decimal = Decimal("0.20")
    sma_period: int = 20
    rsi_period: int = 14
    history_days: int = 365
    atr_period: int = 14
    atr_multiplier: Decimal = Decimal("1.0")
    max_stop_pct: Decimal = Decimal("0.07")
    use_atr_stop: bool = True
    max_gap_pct: Decimal = Decimal("0.03")
    suggested_limit_pct: Decimal = Decimal("0.005")
    rsi_overbought_threshold: Decimal = Decimal("75")
    top_n: int | None = None
    fast_mode: bool = False
    iep_min: int | None = None
    use_atr_range: bool = True
    atr_range_cap_min: Decimal = Decimal("0.01")
    atr_range_cap_max: Decimal = Decimal("0.05")
    broker_backing_window_days: int = 7
    broker_backing_threshold: float = 50.0
    fvwap_period: int = 20
    exclude_suffix_pattern: str = r"-(W|R|L)$"
    min_history_days: int = 20
    iev_intensity_enabled: bool = True
    iev_intensity_unusual_threshold: float = 5.0
    iev_intensity_auto_downgrade: bool = False
    min_bid_pressure_preopen: float = 0.0
    tick_friction_gate: bool = True
    min_target_ticks: int = 3
    min_stop_ticks: int = 2
    tighten_in_regimes: list[str] = field(default_factory=lambda: ["VOLATILE", "RISK_OFF"])
    gap_pct_tightening_factor: float = 0.5
    require_backed_in_weak: bool = True
    regime_gate_enabled: bool = True

    @classmethod
    def from_yaml(cls, data: dict) -> "PreOpenScreenConfig":
        """Parse from pre-open screener config YAML. All new keys have safe defaults."""
        screener = data.get("screener", {})
        entry = data.get("entry", {})
        risk = data.get("risk", {})
        analysis = data.get("analysis", {})
        regime_gate = data.get("regime_gate") or {}

        top_n_raw = screener.get("top_n", None)

        return cls(
            iev_min=int(screener.get("iev_min", 100_000)),
            capital=Decimal(str(entry.get("capital", 3_000_000))),
            tick_above=int(entry.get("tick_above", 1)),
            stop_loss_pct=Decimal(str(risk.get("stop_loss_pct", 0.20))),
            sma_period=int(analysis.get("sma_period", 20)),
            rsi_period=int(analysis.get("rsi_period", 14)),
            history_days=int(analysis.get("days", 365)),
            atr_period=int(analysis.get("atr_period", 14)),
            atr_multiplier=Decimal(str(risk.get("atr_multiplier", 1.0))),
            max_stop_pct=Decimal(str(risk.get("max_stop_pct", 0.07))),
            use_atr_stop=bool(risk.get("use_atr_stop", True)),
            max_gap_pct=Decimal(str(entry.get("max_gap_pct", 0.03))),
            suggested_limit_pct=Decimal(str(entry.get("suggested_limit_pct", 0.005))),
            rsi_overbought_threshold=Decimal(str(analysis.get("rsi_overbought_threshold", 75))),
            top_n=int(top_n_raw) if top_n_raw is not None else None,
            fast_mode=bool(screener.get("fast_mode", False)),
            iep_min=int(screener["iep_min"]) if screener.get("iep_min") is not None else None,
            use_atr_range=bool(analysis.get("use_atr_range", True)),
            atr_range_cap_min=Decimal(str(analysis.get("atr_range_cap_min", 0.01))),
            atr_range_cap_max=Decimal(str(analysis.get("atr_range_cap_max", 0.05))),
            broker_backing_window_days=int(analysis.get("broker_backing_window_days", 7)),
            broker_backing_threshold=float(analysis.get("broker_backing_threshold", 50.0)),
            fvwap_period=int(analysis.get("fvwap_period", 20)),
            exclude_suffix_pattern=str(
                data.get("filters", {}).get("exclude_suffix_pattern", r"-(W|R|L)$")
            ),
            min_history_days=int(data.get("filters", {}).get("min_history_days", 20)),
            iev_intensity_enabled=bool(analysis.get("iev_intensity_enabled", True)),
            iev_intensity_unusual_threshold=float(
                analysis.get("iev_intensity_unusual_threshold", 5.0)
            ),
            iev_intensity_auto_downgrade=bool(analysis.get("iev_intensity_auto_downgrade", False)),
            min_bid_pressure_preopen=float(screener.get("min_bid_pressure_preopen", 0.0)),
            tick_friction_gate=bool(risk.get("tick_friction_gate", True)),
            min_target_ticks=int(risk.get("min_target_ticks", 3)),
            min_stop_ticks=int(risk.get("min_stop_ticks", 2)),
            tighten_in_regimes=list(
                regime_gate.get("tighten_in_regimes", ["VOLATILE", "RISK_OFF"])
            ),
            gap_pct_tightening_factor=float(regime_gate.get("gap_pct_tightening_factor", 0.5)),
            require_backed_in_weak=bool(regime_gate.get("require_backed_in_weak", True)),
            regime_gate_enabled=bool(regime_gate.get("regime_gate_enabled", True)),
        )
