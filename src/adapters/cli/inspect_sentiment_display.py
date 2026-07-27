"""
Rich rendering for `saham inspect sentiment` and `saham audit sentiment`.

Layer: Adapter
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.domain.value_objects.sentiment import Sentiment, SentimentSnapshot


def display_sentiment_full(
    snapshot: SentimentSnapshot,
    provider: str,
    classifier: str,
    warning: str | None = None,
) -> None:
    """Display full sentiment snapshot output with catalysts."""
    console = Console()
    if warning:
        console.print(f"\n[yellow]Warning:[/yellow] {warning}")
        return

    # Sentiment symbol map
    sentiment_symbols = {
        Sentiment.POSITIVE: "▲",
        Sentiment.NEUTRAL: "■",
        Sentiment.NEGATIVE: "▼",
    }
    sentiment_colors = {
        Sentiment.POSITIVE: "green",
        Sentiment.NEUTRAL: "yellow",
        Sentiment.NEGATIVE: "red",
    }

    # Get the count for the winning sentiment
    sentiment_counts = {
        Sentiment.POSITIVE: snapshot.positive_count,
        Sentiment.NEUTRAL: snapshot.neutral_count,
        Sentiment.NEGATIVE: snapshot.negative_count,
    }
    winning_count = sentiment_counts[snapshot.overall_sentiment]
    overall_color = sentiment_colors.get(snapshot.overall_sentiment, "white")

    # Catalyst Summary
    cat_counts = {}
    for h in snapshot.headlines:
        cat_counts[h.catalyst] = cat_counts.get(h.catalyst, 0) + 1
    top_catalyst_name = max(cat_counts, key=cat_counts.get).name if cat_counts else "-"

    console.print("")
    summary_text = Text()
    summary_text.append("Overall: ", style="bold")
    summary_text.append(snapshot.overall_sentiment.value.upper(), style=f"bold {overall_color}")
    summary_text.append(
        f" | Confidence: {winning_count}/{snapshot.total_count} ({snapshot.confidence_pct}%)"
    )
    summary_text.append(f" | Primary Catalyst: {top_catalyst_name}")

    panel = Panel(
        summary_text,
        title="[bold]SENTIMENT SNAPSHOT[/bold]",
        border_style=overall_color,
        expand=False,
    )
    console.print(panel)

    console.print("\n[bold]Sentiment Breakdown[/bold]")
    total = snapshot.total_count or 1
    pos_pct = int(snapshot.positive_count / total * 100)
    neu_pct = int(snapshot.neutral_count / total * 100)
    neg_pct = int(snapshot.negative_count / total * 100)

    # Let's show breakdown as a table
    breakdown_table = Table(show_header=True, header_style="bold magenta")
    breakdown_table.add_column("Sentiment", style="cyan")
    breakdown_table.add_column("Count", justify="right")
    breakdown_table.add_column("Percentage", justify="right")
    breakdown_table.add_column("Ratio Bar", style="dim white")

    # Construct simple ASCII/Unicode progress bars
    def _make_bar(pct: int, color: str) -> str:
        blocks = int(pct / 10)
        return f"[{color}]" + "█" * blocks + "░" * (10 - blocks) + "[/" + color + "]"

    breakdown_table.add_row(
        "Positive", str(snapshot.positive_count), f"{pos_pct}%", _make_bar(pos_pct, "green")
    )
    breakdown_table.add_row(
        "Neutral", str(snapshot.neutral_count), f"{neu_pct}%", _make_bar(neu_pct, "yellow")
    )
    breakdown_table.add_row(
        "Negative", str(snapshot.negative_count), f"{neg_pct}%", _make_bar(neg_pct, "red")
    )
    console.print(breakdown_table)

    # Show recent headlines (max 8)
    if snapshot.headlines:
        console.print("\n[bold]Recent Headlines[/bold]")
        headlines_table = Table(show_header=True, header_style="bold magenta")
        headlines_table.add_column("Dir", justify="center")
        headlines_table.add_column("Catalyst", style="yellow")
        headlines_table.add_column("Headline Title", style="white")

        for headline in snapshot.headlines[:8]:
            symbol = sentiment_symbols.get(headline.sentiment, "?")
            color = sentiment_colors.get(headline.sentiment, "white")
            cat_label = headline.catalyst.name
            headlines_table.add_row(
                f"[{color}]{symbol}[/{color}]",
                cat_label,
                headline.title,
            )
        console.print(headlines_table)

    console.print(f"\n[dim][Provider: {provider} | Classifier: {classifier}][/dim]")


def display_sentiment_brief(
    snapshot: SentimentSnapshot,
    warning: str | None = None,
) -> None:
    """Display brief sentiment output for --with-sentiment flag.

    Args:
        snapshot: The sentiment snapshot to display
        warning: Optional warning message
    """
    console = Console()
    console.print("")

    if warning:
        summary_text = Text()
        summary_text.append(f"Warning: {warning}\n\n", style="bold yellow")
        summary_text.append("Note: Sentiment is contextual information only.\n")
        summary_text.append("      It does NOT affect the risk assessment above.")
        panel = Panel(
            summary_text,
            title="[bold yellow]NEWS SENTIMENT[/bold yellow]",
            border_style="yellow",
            expand=False,
        )
        console.print(panel)
        return

    sentiment_colors = {
        Sentiment.POSITIVE: "green",
        Sentiment.NEUTRAL: "yellow",
        Sentiment.NEGATIVE: "red",
    }
    overall_color = sentiment_colors.get(snapshot.overall_sentiment, "white")

    # Catalyst if available
    cat_counts = {}
    for h in snapshot.headlines:
        cat_counts[h.catalyst] = cat_counts.get(h.catalyst, 0) + 1
    top_catalyst_name = max(cat_counts, key=cat_counts.get).name if cat_counts else "-"

    summary_text = Text()
    summary_text.append("Overall: ", style="bold")
    summary_text.append(snapshot.overall_sentiment.value.upper(), style=f"bold {overall_color}")
    summary_text.append(f" ({snapshot.confidence_pct}% confidence)\n")
    summary_text.append(f"Catalyst: {top_catalyst_name}\n")
    summary_text.append(
        f"Breakdown: [green]+{snapshot.positive_count}[/green]"
        f" / [yellow]={snapshot.neutral_count}[/yellow]"
        f" / [red]-{snapshot.negative_count}[/red]"
    )

    panel = Panel(
        summary_text,
        title="[bold]NEWS SENTIMENT[/bold]",
        border_style=overall_color,
        expand=False,
    )
    console.print(panel)


def display_sentiment_audit(response) -> None:
    """Display the sentiment audit accuracy report."""
    console = Console()
    console.print(f"Logs audited:   {response.logs_audited}")
    console.print(f"Audits saved:   {response.audits_saved}")

    stats = response.stats
    if stats["audited_logs"] > 0:
        console.print("")
        summary_text = Text()
        summary_text.append("Total Audited: ", style="bold")
        summary_text.append(str(stats["audited_logs"]), style="bold cyan")

        panel = Panel(
            summary_text,
            title="[bold]SENTIMENT ACCURACY REPORT (5-Day Horizon)[/bold]",
            border_style="cyan",
            expand=False,
        )
        console.print(panel)
        console.print("")

        console.print("[bold]Accuracy By Sentiment[/bold]")
        sent_table = Table(show_header=True, header_style="bold magenta")
        sent_table.add_column("Sentiment", style="cyan")
        sent_table.add_column("Win Rate", justify="right")
        sent_table.add_column("Wins/Total", justify="right")

        for sent, s_stats in stats["by_sentiment"].items():
            win_rate = (s_stats["wins"] / s_stats["total"]) * 100
            color = "green" if win_rate >= 50 else "yellow"
            sent_table.add_row(
                sent.upper(),
                f"[{color}]{win_rate:.1f}%[/{color}]",
                f"{s_stats['wins']}/{s_stats['total']}",
            )
        console.print(sent_table)
        console.print("")

        console.print("[bold]Accuracy By Catalyst[/bold]")
        cat_table = Table(show_header=True, header_style="bold magenta")
        cat_table.add_column("Catalyst", style="cyan")
        cat_table.add_column("Win Rate", justify="right")
        cat_table.add_column("Wins/Total", justify="right")

        for cat, c_stats in stats["by_catalyst"].items():
            win_rate = (c_stats["wins"] / c_stats["total"]) * 100
            color = "green" if win_rate >= 50 else "yellow"
            cat_table.add_row(
                cat.upper(),
                f"[{color}]{win_rate:.1f}%[/{color}]",
                f"{c_stats['wins']}/{c_stats['total']}",
            )
        console.print(cat_table)
    else:
        console.print("\nNo audited data available yet. Audits require logs at least 1-5 days old.")
