"""
Display helpers for saham view market-context output.

Layer: Adapter
"""

from __future__ import annotations

import json

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.domain.value_objects.market_context import MarketContext, MarketRegime

_CONSOLE = Console()

# Display-compatible label map: MCE regime → legacy-style label for callers
# that previously showed BULLISH/SIDEWAYS/RISK_OFF labels.
REGIME_DISPLAY_LABEL: dict[str, str] = {
    "RISK_ON": "BULLISH",
    "NEUTRAL": "SIDEWAYS",
    "RISK_OFF": "RISK_OFF",
    "VOLATILE": "VOLATILE",
}

_REGIME_STYLE = {
    MarketRegime.RISK_ON: ("bold green", "RISK_ON"),
    MarketRegime.NEUTRAL: ("bold yellow", "NEUTRAL"),
    MarketRegime.RISK_OFF: ("bold red", "RISK_OFF"),
    MarketRegime.VOLATILE: ("bold magenta", "VOLATILE"),
}

_LABEL_STYLE = {
    "FAVORABLE": "green",
    "NEUTRAL": "yellow",
    "STRESSED": "red",
    "UNAVAILABLE": "dim",
    "DISABLED": "dim",
}

_SCORE_BAR_WIDTH = 10


def display_market_context(context: MarketContext, verbose: bool = False) -> None:
    """Render MarketContext to terminal."""
    _CONSOLE.print()

    regime_style, regime_text = _REGIME_STYLE.get(
        context.regime, ("bold white", context.regime.value)
    )

    # ── Header ───────────────────────────────────────────────────────────────
    header = Text()
    header.append(f"Market Context — {context.as_of_date}   ", style="bold")
    header.append(regime_text, style=regime_style)
    header.append(f"  (conviction: {context.conviction:.2f})", style="dim")

    # ── Factor table ─────────────────────────────────────────────────────────
    table = Table(
        show_header=True, header_style="bold cyan", box=None, pad_edge=False, padding=(0, 1)
    )
    table.add_column("Factor", style="bold", width=14)
    table.add_column("Score", justify="right", width=6)
    table.add_column("Weight", justify="right", width=7)
    table.add_column("Label", width=12)
    table.add_column("Detail")

    for factor in context.factors:
        if not factor.enabled:
            if verbose:
                table.add_row(
                    factor.name,
                    "—",
                    f"{factor.weight:.2f}",
                    _styled_label("DISABLED"),
                    Text("disabled in config", style="dim"),
                )
            continue

        score_str = f"{factor.score:.2f}" if factor.score is not None else "—"
        score_bar = _score_bar(factor.score) if factor.score is not None else ""

        if verbose:
            detail = Text()
            detail.append(score_bar + " ", style="dim")
            detail.append(factor.rationale)
        else:
            detail = Text(factor.rationale[:70])

        table.add_row(
            factor.name,
            score_str,
            f"{factor.weight:.2f}",
            _styled_label(factor.label),
            detail,
        )

    # ── Footer ───────────────────────────────────────────────────────────────
    footer = Text()
    mult = context.signal_multiplier
    tighten = "ON" if context.gate_tightening else "off"

    if mult < 1.0:
        footer.append(f"signal_multiplier: {mult:.2f}", style="bold red")
        footer.append("  (ENTER signals will be downgraded to WATCH)", style="dim red")
    else:
        footer.append(f"signal_multiplier: {mult:.2f}", style="green")

    footer.append("   gate_tightening: ", style="")
    if context.gate_tightening:
        footer.append(tighten, style="bold red")
    else:
        footer.append(tighten, style="dim")

    # ── A2: Regime quality metadata ───────────────────────────────────────────
    regime_quality_parts: list[Text] = []
    regime_confidence = getattr(context, "regime_confidence", None)
    regime_stability = getattr(context, "regime_stability", None)
    days_in_regime = getattr(context, "days_in_regime", None)
    transition_warning = getattr(context, "transition_warning", None)

    if regime_confidence is not None or regime_stability is not None:
        rq = Text()
        if regime_confidence is not None:
            conf_style = (
                "green"
                if regime_confidence >= 0.65
                else "yellow"
                if regime_confidence >= 0.35
                else "bold red"
            )
            rq.append("regime_confidence: ", style="dim")
            rq.append(f"{regime_confidence:.2f}", style=conf_style)
        if regime_stability is not None:
            stab_style = (
                "green"
                if regime_stability == "STABLE"
                else "yellow"
                if regime_stability == "UNKNOWN"
                else "bold red"
            )
            rq.append("   stability: ", style="dim")
            rq.append(regime_stability, style=stab_style)
        if days_in_regime is not None:
            rq.append(f"   days_in_regime: {days_in_regime}", style="dim")
        regime_quality_parts.append(rq)

    if transition_warning:
        regime_quality_parts.append(Text(f"⚠ {transition_warning}", style="yellow"))

    # ── Warnings ──────────────────────────────────────────────────────────────
    warnings = []
    if context.staleness_warning:
        warnings.append(Text(f"⚠ {context.staleness_warning}", style="yellow"))
    if context.coverage_warning:
        warnings.append(Text(f"⚠ {context.coverage_warning}", style="yellow"))

    from rich.console import Group as RGroup
    from rich.rule import Rule

    parts = [header, Rule(style="dim"), table, Rule(style="dim"), footer]
    for rq in regime_quality_parts:
        parts.append(rq)
    for w in warnings:
        parts.append(w)

    panel = Panel(RGroup(*parts), border_style=regime_style.replace("bold ", ""))
    _CONSOLE.print(panel)
    _CONSOLE.print()


def display_market_context_json(context: MarketContext) -> None:
    print(json.dumps(context.to_dict(), indent=2))


def _score_bar(score: float) -> str:
    filled = round(score * _SCORE_BAR_WIDTH)
    return "█" * filled + "░" * (_SCORE_BAR_WIDTH - filled)


def _styled_label(label: str) -> Text:
    style = _LABEL_STYLE.get(label, "")
    return Text(label, style=style)


# ── Shared helpers for callers migrated from MarketRegimeUseCase ──────────────


def context_factor_value(context: MarketContext, name: str) -> float | None:
    """Return the raw .value of a named ContextFactor, or None if not found/unavailable."""
    for f in context.factors:
        if f.name == name:
            return f.value
    return None


def context_warnings(context: MarketContext) -> list[str]:
    """Collect staleness and coverage warnings from a MarketContext."""
    return [w for w in (context.staleness_warning, context.coverage_warning) if w]


def context_conviction_score(context: MarketContext) -> int:
    """Map conviction (0.0–1.0) to a 0–7 integer for display parity with old regime score."""
    return round(context.conviction * 7)


def context_regime_style(context: MarketContext) -> str:
    """Return Rich colour style for the regime conviction level."""
    if context.conviction >= 0.65:
        return "green"
    if context.conviction >= 0.35:
        return "yellow"
    return "red"
