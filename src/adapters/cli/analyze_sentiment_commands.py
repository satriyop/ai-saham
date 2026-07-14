"""
CLI implementation functions for saham analyze sentiment commands.
Public command registration lives in lifecycle routers:
  saham analyze sentiment
  saham analyze audit
Layer: Adapter
"""

from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.analyze_sentiment_display import (
    display_sentiment_audit,
    display_sentiment_full,
)
from src.adapters.cli.analyze_sentiment_workflow_factory import (
    create_audit_sentiment_use_case,
    create_fetch_sentiment_use_case,
)
from src.application.use_case.audit_sentiment_use_case import AuditSentimentRequest
from src.application.use_case.fetch_sentiment_use_case import FetchSentimentRequest
from src.infrastructure.config.app_config import load_app_config


def sentiment(
    ticker: Annotated[str, typer.Argument(help="Stock ticker symbol (e.g., BBCA)")],
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Days of news to fetch", min=1, max=30),
    ] = 3,
    max_headlines: Annotated[
        int,
        typer.Option("--max", help="Maximum headlines to analyze", min=1, max=50),
    ] = 20,
    no_ai: Annotated[
        bool,
        typer.Option("--no-ai", help="Disable AI and use offline keyword classification"),
    ] = False,
    provider: Annotated[
        Optional[str],
        typer.Option(
            "--provider",
            help="AI provider for classification (deepseek/claude/openai/gemini/ollama)",
        ),
    ] = None,
    model: Annotated[
        Optional[str],
        typer.Option("--model", "-m", help="Model name for AI provider"),
    ] = None,
    news_provider_name: Annotated[
        str,
        typer.Option(
            "--news-provider",
            help="News source: composite (default), google, kontan, cnbc, mock",
        ),
    ] = "composite",
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="Path to SQLite database"),
    ] = None,
) -> None:
    """
    Fetch and analyze news sentiment for an IDX stock.
    """
    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)
    typer.echo(f"Fetching news sentiment for {ticker.upper()}...")

    try:
        use_case = create_fetch_sentiment_use_case(
            db_path=resolved_db,
            news_provider_name=news_provider_name,
            use_ai=not no_ai,
            provider=provider,
            model=model,
        )

        request = FetchSentimentRequest(
            ticker=ticker,
            max_headlines=max_headlines,
            days=days,
        )
        response = use_case.execute(request)

        # Display header
        typer.echo(f"\nTicker: {response.ticker}")
        fetched_date = (
            response.snapshot.fetched_at.date() if response.snapshot.fetched_at else "N/A"
        )
        typer.echo(f"Date: {fetched_date}")
        typer.echo(f"Headlines Analyzed: {response.snapshot.total_count}")

        # Display sentiment
        display_sentiment_full(
            snapshot=response.snapshot,
            provider=response.provider,
            classifier=response.classifier,
            warning=response.warning,
        )

        typer.echo("\nDISCLAIMER: Sentiment analysis only, not trading advice.")

    except Exception as e:
        error_msg = str(e).lower()
        if "connection" in error_msg or "network" in error_msg or "timeout" in error_msg:
            typer.echo("Warning: Could not fetch news (network issue).", err=True)
            typer.echo("Tip: Check your internet connection and try again.", err=True)
        else:
            typer.echo(f"Failed to analyze sentiment: {e}", err=True)
        raise typer.Exit(1)


def sentiment_audit(
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="Path to SQLite database"),
    ] = None,
) -> None:
    """
    Audit past sentiment accuracy against actual price moves.

    Finds logged sentiment predictions and checks their outcomes
    after 1, 3, and 5 trading days.
    """
    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)
    typer.echo("Auditing past sentiment predictions...")

    try:
        use_case = create_audit_sentiment_use_case(db_path=resolved_db)
        response = use_case.execute(AuditSentimentRequest())
        display_sentiment_audit(response)

    except Exception as e:
        typer.echo(f"Failed to audit sentiment: {e}", err=True)
        raise typer.Exit(1)
