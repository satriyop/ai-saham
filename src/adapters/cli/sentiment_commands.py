"""
CLI commands for news sentiment analysis and impact auditing.

Commands:
  saham sentiment TICKER — Fetch and analyze news sentiment
  saham sentiment audit  — Audit past sentiment accuracy vs price moves

Layer: Adapter (CLI)
"""

from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.application.services.group_mapping import GroupMappingService
from src.application.use_case.audit_sentiment import AuditSentimentRequest, AuditSentimentUseCase
from src.application.use_case.fetch_sentiment import FetchSentimentRequest, FetchSentimentUseCase
from src.domain.ports.sentiment_repository import SentimentLog
from src.domain.value_objects.sentiment import CatalystType, Sentiment, SentimentSnapshot
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository
from src.infrastructure.persistence.sentiment_repository import SQLiteSentimentRepository
from src.infrastructure.sentiment import SentimentFactory

DEFAULT_DB_PATH = Path("data.db")


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
            "--provider", help="AI provider for classification (deepseek/claude/openai/gemini/ollama)"
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
    resolved_db = db_path or DEFAULT_DB_PATH
    typer.echo(f"Fetching news sentiment for {ticker.upper()}...")

    try:
        # Wire up dependencies
        news_provider = SentimentFactory.create_news_provider(news_provider_name)
        classifier = SentimentFactory.create_classifier(
            use_ai=not no_ai,
            provider=provider,
            model=model,
        )
        group_service = GroupMappingService()
        sentiment_repo = SQLiteSentimentRepository(db_path=resolved_db)

        use_case = FetchSentimentUseCase(
            news_provider=news_provider,
            classifier=classifier,
            group_service=group_service,
            sentiment_repo=sentiment_repo
        )

        # Execute use case
        request = FetchSentimentRequest(
            ticker=ticker,
            max_headlines=max_headlines,
            days=days,
        )
        response = use_case.execute(request)

        # Display header
        typer.echo(f"\nTicker: {response.ticker}")
        typer.echo(f"Date: {response.snapshot.fetch_date}")
        typer.echo(f"Headlines Analyzed: {response.snapshot.total_count}")

        # Display sentiment
        _display_sentiment_full(
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
    resolved_db = db_path or DEFAULT_DB_PATH
    typer.echo("Auditing past sentiment predictions...")

    try:
        sentiment_repo = SQLiteSentimentRepository(db_path=resolved_db)
        market_repo = SQLiteMarketRepository(db_path=resolved_db)

        use_case = AuditSentimentUseCase(
            sentiment_repo=sentiment_repo,
            market_repo=market_repo
        )

        response = use_case.execute(AuditSentimentRequest())

        typer.echo(f"Logs audited:   {response.logs_audited}")
        typer.echo(f"Audits saved:   {response.audits_saved}")

        stats = response.stats
        if stats["audited_logs"] > 0:
            typer.echo("\n" + "=" * 50)
            typer.echo("SENTIMENT ACCURACY REPORT (5-Day Horizon)")
            typer.echo("=" * 50)

            typer.echo(f"\nTotal Audited: {stats['audited_logs']}")

            typer.echo("\nBy Sentiment:")
            for sent, s_stats in stats["by_sentiment"].items():
                win_rate = (s_stats["wins"] / s_stats["total"]) * 100
                typer.echo(f"  {sent.upper():<10}: {win_rate:>5.1f}%  ({s_stats['wins']}/{s_stats['total']})")

            typer.echo("\nBy Catalyst:")
            for cat, c_stats in stats["by_catalyst"].items():
                win_rate = (c_stats["wins"] / c_stats["total"]) * 100
                typer.echo(f"  {cat.upper():<15}: {win_rate:>5.1f}%  ({c_stats['wins']}/{c_stats['total']})")

            typer.echo("=" * 50)
        else:
            typer.echo("\nNo audited data available yet. Audits require logs at least 1-5 days old.")

    except Exception as e:
        typer.echo(f"Failed to audit sentiment: {e}", err=True)
        raise typer.Exit(1)


def _display_sentiment_full(
    snapshot: SentimentSnapshot,
    provider: str,
    classifier: str,
    warning: str | None = None,
) -> None:
    """Display full sentiment snapshot output with catalysts."""
    if warning:
        typer.echo(f"\nWarning: {warning}")
        return

    # Sentiment symbol map
    sentiment_symbols = {
        Sentiment.POSITIVE: "+",
        Sentiment.NEUTRAL: "=",
        Sentiment.NEGATIVE: "-",
    }

    # Overall sentiment display
    typer.echo(f"\n{'-' * 39}")
    typer.echo("SENTIMENT SNAPSHOT")
    typer.echo(f"{'-' * 39}")

    # Get the count for the winning sentiment
    sentiment_counts = {
        Sentiment.POSITIVE: snapshot.positive_count,
        Sentiment.NEUTRAL: snapshot.neutral_count,
        Sentiment.NEGATIVE: snapshot.negative_count,
    }
    winning_count = sentiment_counts[snapshot.overall_sentiment]

    typer.echo(f"\nOverall: {snapshot.overall_sentiment.value.upper()}")
    typer.echo(
        f"Confidence: {winning_count}/{snapshot.total_count} headlines ({snapshot.confidence_pct}%)"
    )

    # Catalyst Summary
    cat_counts = {}
    for h in snapshot.headlines:
        cat_counts[h.catalyst] = cat_counts.get(h.catalyst, 0) + 1

    if cat_counts:
        top_catalyst = max(cat_counts, key=cat_counts.get)
        typer.echo(f"Primary Catalyst: {top_catalyst.name}")

    typer.echo("\nBreakdown:")
    total = snapshot.total_count or 1
    pos_pct = int(snapshot.positive_count / total * 100)
    neu_pct = int(snapshot.neutral_count / total * 100)
    neg_pct = int(snapshot.negative_count / total * 100)
    typer.echo(f"  Positive:  {snapshot.positive_count} ({pos_pct}%)")
    typer.echo(f"  Neutral:   {snapshot.neutral_count} ({neu_pct}%)")
    typer.echo(f"  Negative:  {snapshot.negative_count} ({neg_pct}%)")

    # Show recent headlines (max 8)
    if snapshot.headlines:
        typer.echo("\nRecent Headlines:")
        for headline in snapshot.headlines[:8]:
            symbol = sentiment_symbols.get(headline.sentiment, "?")
            title = headline.title[:65]
            suffix = "..." if len(headline.title) > 65 else ""
            cat_label = f"[{headline.catalyst.name[:4]}]"
            typer.echo(f"  [{symbol}] {cat_label:<6} {title}{suffix}")

    typer.echo(f"\n[Provider: {provider} | Classifier: {classifier}]")


def _display_sentiment_brief(
    snapshot: SentimentSnapshot,
    warning: str | None = None,
) -> None:
    """Display brief sentiment output for --with-sentiment flag.

    Args:
        snapshot: The sentiment snapshot to display
        warning: Optional warning message
    """
    typer.echo(f"\n{'-' * 39}")
    typer.echo("NEWS SENTIMENT")
    typer.echo(f"{'-' * 39}")

    if warning:
        typer.echo(f"\nWarning: {warning}")
        typer.echo("\nNote: Sentiment is contextual information only.")
        typer.echo("      It does NOT affect the risk assessment above.")
        return

    typer.echo(
        f"\nOverall: {snapshot.overall_sentiment.value.upper()} "
        f"({snapshot.confidence_pct}% confidence)"
    )

    # Catalyst if available
    cat_counts = {}
    for h in snapshot.headlines:
        cat_counts[h.catalyst] = cat_counts.get(h.catalyst, 0) + 1
    if cat_counts:
        top_catalyst = max(cat_counts, key=cat_counts.get)
        typer.echo(f"Catalyst: {top_catalyst.name}")

    typer.echo(f"Breakdown: +{snapshot.positive_count} / ={snapshot.neutral_count} / -{snapshot.negative_count}")
