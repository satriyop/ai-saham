"""
CLI command for `saham analyze risk` — rule-based risk assessment.

Layer: Adapter
"""

import json as _json
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli import analyze_risk_display as display
from src.adapters.cli.analyze_risk_workflow_factory import (
    create_explain_risk_use_case,
    create_run_risk_analysis_workflow,
)
from src.application.rules.exceptions import (
    RulesFileError,
    RulesSchemaError,
    RulesValidationError,
)
from src.application.use_case.explain_risk_use_case import ExplainRiskRequest
from src.application.use_case.run_risk_analysis_workflow_use_case import (
    RunRiskAnalysisWorkflowRequest,
)
from src.infrastructure.config.app_config import load_app_config

__all__ = ["risk"]


def _no_data_error(ticker: str) -> None:
    typer.echo(f"[error] No cached data for {ticker.upper()}.", err=True)
    typer.echo(f"        Fix:   saham fetch market {ticker.upper()} --days 365", err=True)


def risk(
    ticker: Annotated[str, typer.Argument(help="Stock ticker symbol (e.g., BBCA)")],
    rules_file: Annotated[
        Optional[Path], typer.Option("--rules-file", "-r", help="Path to custom YAML rules file")
    ] = None,
    sma_period: Annotated[int, typer.Option("--sma", help="SMA period", min=1)] = 20,
    ema_period: Annotated[int, typer.Option("--ema", help="EMA period", min=1)] = 20,
    rsi_period: Annotated[int, typer.Option("--rsi", help="RSI period", min=1)] = 14,
    db_path: Annotated[Optional[Path], typer.Option("--db", help="Path to SQLite database")] = None,
    explain: Annotated[
        Optional[bool], typer.Option("--explain", "-e", help="Generate AI explanation")
    ] = None,
    provider: Annotated[
        Optional[str],
        typer.Option("--provider", help="AI provider (deepseek/claude/openai/gemini/ollama/mock)"),
    ] = None,
    model: Annotated[
        Optional[str], typer.Option("--model", "-m", help="Model name for AI provider")
    ] = None,
    with_sentiment: Annotated[
        bool, typer.Option("--with-sentiment", "-s", help="Include news sentiment context")
    ] = False,
    news_provider_name: Annotated[
        str,
        typer.Option("--news-provider", help="News source: composite, google, kontan, cnbc, mock"),
    ] = "composite",
    no_ai: Annotated[
        bool,
        typer.Option("--no-ai", help="Disable AI sentiment classifier (uses keyword fallback)"),
    ] = False,
    trend: Annotated[
        int, typer.Option("--trend", help="Show risk trend over last N days (0=off)", min=0)
    ] = 0,
    fmt: Annotated[
        Optional[str], typer.Option("--format", help="Output format: table or json")
    ] = None,
) -> None:
    """
    Assess risk for an IDX stock using deterministic risk gates.

    Risk status:
      OPEN      No configured gate fired
      BLOCKED   A configured gate fired

    Examples:
        saham analyze risk BBCA
        saham analyze risk BBCA --rules-file config/my_rules.yaml
        saham analyze risk BBCA --explain
        saham analyze risk BBCA --with-sentiment
    """
    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)
    explain = cfg.ai.enabled if explain is None else explain
    fmt = fmt or cfg.analysis.format

    if fmt != "json":
        typer.echo(f"Assessing risk for {ticker.upper()}...")

    try:
        workflow = create_run_risk_analysis_workflow(resolved_db)
        request = RunRiskAnalysisWorkflowRequest(
            ticker=ticker,
            sma_period=sma_period,
            ema_period=ema_period,
            rsi_period=rsi_period,
            rules_file=rules_file,
            include_sentiment=with_sentiment,
            sentiment_provider_name=news_provider_name,
            no_ai_sentiment=no_ai,
            trend_days=trend if fmt != "json" else 0,
        )
        result = workflow.execute(request)

        for warning in result.warnings:
            typer.echo(warning, err=True)

        if fmt == "json":
            typer.echo(_json.dumps(result.to_json_dict(), indent=2))
            return

        display.render_risk_assessment_table(result.response)

        if explain:
            display.render_ai_explanation_header()
            try:
                explain_use_case = create_explain_risk_use_case(provider=provider, model=model)
                explain_response = explain_use_case.execute(
                    ExplainRiskRequest(
                        ticker=ticker.upper(),
                        assessment=result.response.assessment,
                        snapshot=result.response.assessment.indicators,
                    )
                )
                display.render_ai_explanation(explain_response)
            except Exception as e:
                display.render_ai_explanation_error(e)

        if result.response.coverage_warning:
            typer.echo(f"\n[warning] {result.response.coverage_warning}", err=True)

        if result.trend_response is not None:
            display.render_risk_trend(result.trend_response, trend)

        if with_sentiment and result.sentiment_snapshot:
            from src.adapters.cli.analyze_sentiment_display import display_sentiment_brief

            display_sentiment_brief(snapshot=result.sentiment_snapshot)

        typer.echo("\nDISCLAIMER: Analysis only, not trading advice.")

    except RulesFileError as e:
        typer.echo(f"[error] {e}", err=True)
        raise typer.Exit(1)
    except RulesSchemaError as e:
        typer.echo(f"[error] Rules file schema error: {e}", err=True)
        raise typer.Exit(1)
    except RulesValidationError as e:
        typer.echo(f"[error] Invalid rules: {e}", err=True)
        raise typer.Exit(1)
    except ValueError as e:
        typer.echo(f"[error] {e}", err=True)
        raise typer.Exit(1)
    except FileNotFoundError:
        typer.echo(f"[error] Database not found at {resolved_db}.", err=True)
        typer.echo(f"        Fix:   saham fetch market {ticker.upper()} --days 365", err=True)
        raise typer.Exit(1)
    except Exception as e:
        msg = str(e).lower()
        if "no such table" in msg or "no data" in msg:
            _no_data_error(ticker)
        else:
            typer.echo(f"[error] Failed to assess risk: {e}", err=True)
        raise typer.Exit(1)
