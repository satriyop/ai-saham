"""
Display rendering for the `saham analyze risk` command.

Layer: Adapter

Renders facts already computed by the risk workflow use case and the AI
explanation use case. Does not construct repositories, use cases, engines,
or providers.
"""

from __future__ import annotations

from typing import Any

import typer

from src.domain.ports.ai_explainer import ExplainerAuthError


def render_risk_assessment_table(response: Any) -> None:
    """Render the "Risk Assessment" table for a completed AssessRiskResponse."""
    assessment = response.assessment
    snapshot = assessment.indicators

    typer.echo(f"\n{'=' * 50}")
    typer.echo(f" Risk Assessment  ·  {response.ticker}")
    typer.echo(f"{'=' * 50}\n")
    typer.echo(f"Data Date: {assessment.snapshot_date}")

    typer.echo("\nIndicators")
    typer.echo(f"{'─' * 30}")
    typer.echo(f"  SMA({response.sma_period}):  {snapshot.sma:>12,.2f}")
    typer.echo(f"  EMA({response.ema_period}):  {snapshot.ema:>12,.2f}")
    typer.echo(f"  RSI({response.rsi_period}):  {snapshot.rsi:>12.2f}")

    typer.echo("\nRisk Result")
    typer.echo(f"{'─' * 30}")
    typer.echo(f"  Status:     {assessment.risk_level_name}")
    typer.echo(f"  Gate:       {assessment.gate_triggered or '-'}")

    typer.echo("\nTriggered Rules")
    typer.echo(f"{'─' * 30}")
    for reason in assessment.rationale_list:
        typer.echo(f"  · {reason}")


def render_risk_trend(trend_response: Any, trend_days: int) -> None:
    """Render the "Risk Trend" panel for a completed AssessRiskTrendResponse."""
    typer.echo(f"\n{'─' * 50}")
    typer.echo(f"Risk Trend (last {trend_days} days)")
    typer.echo(f"{'─' * 50}")
    typer.echo(f"{'Date':<12} {'Risk Level':<12} {'Conf':>6}")
    typer.echo("─" * 32)
    for hist_date, hist_level, hist_conf in trend_response.history:
        typer.echo(f"{hist_date!s:<12} {hist_level:<12} {hist_conf:>4}/100")
    typer.echo("─" * 32)
    marker = {"IMPROVING": "↑", "DETERIORATING": "↓", "STABLE": "→"}.get(
        trend_response.direction, ""
    )
    typer.echo(
        f"Trend: {marker} {trend_response.direction}"
        f"  ({trend_response.days_in_current}d at current level)"
    )


def render_ai_explanation_header() -> None:
    """Render the "AI EXPLANATION" section header."""
    typer.echo(f"\n{'─' * 50}")
    typer.echo("AI EXPLANATION")
    typer.echo(f"{'─' * 50}")


def render_ai_explanation(explain_response: Any) -> None:
    """Render a completed ExplainRiskResponse."""
    if explain_response.success:
        typer.echo(f"\n{explain_response.explanation}")
        typer.echo(f"\n[Provider: {explain_response.provider}]")
    else:
        typer.echo(
            f"\n[error] AI explanation unavailable: {explain_response.error_message}",
            err=True,
        )


def render_ai_explanation_error(error: Exception) -> None:
    """Render an error raised while constructing/running the AI explainer."""
    typer.echo(f"\n[error] AI explanation unavailable: {error}", err=True)
    if isinstance(error, ExplainerAuthError):
        typer.echo("        Tip:   Set the appropriate API key environment variable.", err=True)
