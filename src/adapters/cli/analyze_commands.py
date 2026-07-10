"""
CLI commands for analysis and insights.

Commands (all under `saham analyze`):
  saham analyze risk TICKER       — rule-based risk assessment
  saham analyze compare TICKER…   — side-by-side multi-ticker comparison
  saham analyze sentiment TICKER  — news sentiment analysis
  saham analyze audit             — audit past sentiment accuracy
  saham analyze regime            — IHSG market regime context
  saham analyze chart             — terminal ASCII charts (sub-group)

Layer: Adapter
"""

from pathlib import Path
from typing import Annotated, Optional

import typer

from src.application.rules.exceptions import (
    RulesFileError,
    RulesSchemaError,
    RulesValidationError,
)
from src.application.services.bootstrap import create_risk_engine
from src.application.use_case.assess_risk_use_case import AssessRiskRequest
from src.domain.ports.ai_explainer import ExplainerAuthError
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_assessment import RiskAssessment
from src.infrastructure.ai import ExplainerFactory
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

analyze_app = typer.Typer(
    name="analyze",
    help="Analysis and insights — risk, sentiment, market regime, charts.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

# Register chart as a nested sub-group
from src.adapters.cli.analyze_chart_commands import chart_app

analyze_app.add_typer(chart_app, name="chart")

from src.infrastructure.config.app_config import APP_CFG

DEFAULT_DB_PATH = Path(APP_CFG.storage.db_path)


def _no_data_error(ticker: str) -> None:
    typer.echo(f"[error] No cached data for {ticker.upper()}.", err=True)
    typer.echo(f"        Fix:   saham fetch market {ticker.upper()} --days 365", err=True)


def _display_ai_explanation(
    ticker: str,
    assessment: "RiskAssessment",
    snapshot: "IndicatorSnapshot",
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> None:
    typer.echo(f"\n{'─' * 50}")
    typer.echo("AI EXPLANATION")
    typer.echo(f"{'─' * 50}")

    try:
        from src.application.use_case.explain_risk_use_case import (
            ExplainRiskRequest,
            ExplainRiskUseCase,
        )

        explainer = ExplainerFactory.create(provider=provider, model=model)
        explain_use_case = ExplainRiskUseCase(explainer=explainer)
        explain_response = explain_use_case.execute(
            ExplainRiskRequest(ticker=ticker, assessment=assessment, snapshot=snapshot)
        )
        if explain_response.success:
            typer.echo(f"\n{explain_response.explanation}")
            typer.echo(f"\n[Provider: {explain_response.provider}]")
        else:
            typer.echo(
                f"\n[error] AI explanation unavailable: {explain_response.error_message}", err=True
            )
    except ExplainerAuthError as e:
        typer.echo(f"\n[error] AI explanation unavailable: {e}", err=True)
        typer.echo("        Tip:   Set the appropriate API key environment variable.", err=True)
    except Exception as e:
        typer.echo(f"\n[error] AI explanation unavailable: {e}", err=True)


@analyze_app.command()
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
        bool, typer.Option("--explain", "-e", help="Generate AI explanation")
    ] = APP_CFG.ai.enabled,
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
        str, typer.Option("--format", help="Output format: table or json")
    ] = APP_CFG.analysis.format,
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
    resolved_db = db_path or DEFAULT_DB_PATH

    if fmt != "json":
        typer.echo(f"Assessing risk for {ticker.upper()}...")

    try:
        engine = create_risk_engine(resolved_db, with_enrichment=True)

        sentiment_snapshot = None
        if with_sentiment:
            try:
                from src.application.use_case.fetch_sentiment_use_case import (
                    FetchSentimentRequest,
                    FetchSentimentUseCase,
                )
                from src.infrastructure.sentiment import SentimentFactory

                news_provider = SentimentFactory.create_news_provider(news_provider_name)
                classifier = SentimentFactory.create_classifier(use_ai=not no_ai)
                sentiment_response = FetchSentimentUseCase(
                    news_provider=news_provider,
                    classifier=classifier,
                ).execute(FetchSentimentRequest(ticker=ticker))
                sentiment_snapshot = sentiment_response.snapshot
            except Exception as e:
                typer.echo(f"Warning: Could not fetch sentiment: {e}", err=True)

        request = AssessRiskRequest(
            ticker=ticker,
            sma_period=sma_period,
            ema_period=ema_period,
            rsi_period=rsi_period,
            rules_file=rules_file,
            sentiment=sentiment_snapshot,
        )

        response = engine.assess_request(request)
        assessment = response.assessment
        snapshot = assessment.indicators

        if fmt == "json":
            import json as _json

            typer.echo(
                _json.dumps(
                    {
                        "schema_version": 1,
                        "artifact_type": "risk_assessment",
                        "ticker": response.ticker,
                        "risk_status": assessment.risk_level_name,
                        "status": assessment.risk_level_name,
                        "verdict": assessment.risk_level_name,
                        "gate_triggered": assessment.gate_triggered,
                        "gate_confidence": assessment.gate_confidence,
                        "rationale": assessment.rationale_list,
                        "indicators": {
                            f"sma_{response.sma_period}": float(snapshot.sma),
                            f"ema_{response.ema_period}": float(snapshot.ema),
                            f"rsi_{response.rsi_period}": float(snapshot.rsi),
                        },
                    },
                    indent=2,
                )
            )
            return

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

        if explain:
            _display_ai_explanation(
                ticker=ticker.upper(),
                assessment=assessment,
                snapshot=snapshot,
                provider=provider,
                model=model,
            )

        if response.coverage_warning:
            typer.echo(f"\n[warning] {response.coverage_warning}", err=True)

        if trend > 0 and not rules_file:
            try:
                trend_resp = engine.assess_trend(request, days=trend)
                typer.echo(f"\n{'─' * 50}")
                typer.echo(f"Risk Trend (last {trend} days)")
                typer.echo(f"{'─' * 50}")
                typer.echo(f"{'Date':<12} {'Risk Level':<12} {'Conf':>6}")
                typer.echo("─" * 32)
                for hist_date, hist_level, hist_conf in trend_resp.history:
                    typer.echo(f"{hist_date!s:<12} {hist_level:<12} {hist_conf:>4}/100")
                typer.echo("─" * 32)
                marker = {"IMPROVING": "↑", "DETERIORATING": "↓", "STABLE": "→"}.get(
                    trend_resp.direction, ""
                )
                typer.echo(
                    f"Trend: {marker} {trend_resp.direction}  ({trend_resp.days_in_current}d at current level)"
                )
            except Exception as e:
                typer.echo(f"\nTrend unavailable: {e}", err=True)

        if with_sentiment and sentiment_snapshot:
            from src.adapters.cli.analyze_sentiment_commands import _display_sentiment_brief

            _display_sentiment_brief(snapshot=sentiment_snapshot)

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


@analyze_app.command()
def compare(
    tickers: Annotated[
        list[str], typer.Argument(help="Two or more tickers to compare (e.g., BBCA BBRI BMRI)")
    ],
    sma_period: Annotated[int, typer.Option("--sma", help="SMA period", min=1)] = 20,
    rsi_period: Annotated[int, typer.Option("--rsi", help="RSI period", min=1)] = 14,
    days: Annotated[int, typer.Option("--days", "-d", help="Days of history", min=30)] = 365,
    db_path: Annotated[Optional[Path], typer.Option("--db", help="SQLite database path")] = None,
) -> None:
    """
    Side-by-side risk comparison for multiple IDX tickers.

    Requires cached data for each ticker (`saham fetch market TICKERS` first).

    Examples:
        saham analyze compare BBCA BBRI BMRI
    """
    if len(tickers) < 2:
        typer.echo("[error] Provide at least 2 tickers to compare.", err=True)
        raise typer.Exit(1)

    resolved_db = db_path or DEFAULT_DB_PATH
    repository = SQLiteMarketRepository(db_path=resolved_db)
    engine = create_risk_engine(resolved_db, with_enrichment=True)

    typer.echo(f"\n{'=' * 60}")
    typer.echo(" Risk Comparison")
    typer.echo(f"{'=' * 60}\n")
    typer.echo(
        f"{'TICKER':<8} {'CLOSE':>10} {'SMA({})'.format(sma_period):>10}"
        f" {'RSI({})'.format(rsi_period):>9} {'RISK':<12} {'CONF':>6}"
    )
    typer.echo("─" * 60)

    for t in tickers:
        try:
            req = AssessRiskRequest(
                ticker=t,
                sma_period=sma_period,
                ema_period=sma_period,
                rsi_period=rsi_period,
            )
            resp = engine.assess_request(req)
            assessment = resp.assessment
            snap = assessment.indicators
            candles = repository.get_candles(t.upper())
            close = f"{candles[-1].close:,.0f}" if candles else "—"
            typer.echo(
                f"{t.upper():<8} {close:>10} {float(snap.sma):>10,.0f}"
                f" {float(snap.rsi):>9.1f} {assessment.risk_level_name:<12} {assessment.confidence:>4}/100"
            )
        except Exception:
            typer.echo(f"{t.upper():<8} {'—':>10} {'—':>10} {'—':>9} {'NO DATA':<12} {'—':>6}")

    typer.echo("─" * 60)
    typer.echo("\nDISCLAIMER: Analysis only, not trading advice.")


# Register sentiment and audit from analyze_sentiment_commands (no logic duplication)
from src.adapters.cli.analyze_accum_commands import accumulation_audit as _accumulation_audit_fn
from src.adapters.cli.analyze_regime_commands import regime as _regime_fn
from src.adapters.cli.analyze_sentiment_commands import sentiment as _sentiment_fn
from src.adapters.cli.analyze_sentiment_commands import sentiment_audit as _sentiment_audit_fn
from src.adapters.cli.analyze_signal_commands import signal_audit as _signal_audit_fn
from src.adapters.cli.analyze_signal_commands import (
    signal_backfill_observations as _signal_backfill_observations_fn,
)
from src.adapters.cli.analyze_signal_commands import signal_labels as _signal_labels_fn
from src.adapters.cli.analyze_signal_commands import signal_readiness as _signal_readiness_fn
from src.adapters.cli.analyze_signal_commands import signal_replay as _signal_replay_fn
from src.adapters.cli.analyze_swing_commands import swing as _swing_fn
from src.adapters.cli.analyze_swing_compare_commands import swing_compare as _swing_compare_fn

analyze_app.command("sentiment")(_sentiment_fn)
analyze_app.command("audit")(_sentiment_audit_fn)
analyze_app.command("regime")(_regime_fn)
analyze_app.command("swing")(_swing_fn)
analyze_app.command("accum-audit")(_accumulation_audit_fn)
analyze_app.command("swing-compare")(_swing_compare_fn)
analyze_app.command("signal-audit")(_signal_audit_fn)
analyze_app.command("signal-backfill-observations")(_signal_backfill_observations_fn)
analyze_app.command("signal-labels")(_signal_labels_fn)
analyze_app.command("signal-readiness")(_signal_readiness_fn)
analyze_app.command("signal-replay")(_signal_replay_fn)
