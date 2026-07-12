"""
CLI implementation functions for swing tuning commands.

Layer: Adapter
"""

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.trade_swing_backtest_runner import _run_swing_backtest
from src.adapters.cli.trade_swing_display import display_swing_backtest
from src.application.services.swing_tuning_contracts import (
    build_tuning_config_diff_draft,
    build_tuning_proposal_draft,
    build_tuning_readiness_plan,
)
from src.application.services.swing_tuning_review_journal import (
    SwingTuningReviewJournal,
)
from src.application.use_case.swing_backtest_use_case import (
    FOREIGN_BOUNCE_SETUP as BACKTEST_FOREIGN_BOUNCE_SETUP,
)
from src.application.use_case.swing_backtest_use_case import (
    SwingBacktestResponse,
)
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.config.swing_backtest_config import (
    load_swing_backtest_config as _load_swing_backtest_config,
)
from src.infrastructure.config.swing_config import load_swing_config as _load_swing_config
from src.infrastructure.config.swing_tuning_document_loader import (
    swing_tuning_document_loader,
)
from src.infrastructure.persistence.swing_tuning_review_jsonl_writer import (
    SwingTuningReviewJsonlWriter,
)

_SC = _load_swing_config()
_BT = _load_swing_backtest_config()

DEFAULT_SWING_TUNING_REVIEW_JOURNAL_PATH = Path(
    APP_CFG.storage.swing_tuning_review_journal
)


def _swing_tuning_payload(response: SwingBacktestResponse) -> dict:
    plan = build_tuning_readiness_plan(response.attribution_summary)
    proposal = build_tuning_proposal_draft(response.attribution_summary)
    active_setups = frozenset({response.setup}) if response.setup else None
    config_diff = build_tuning_config_diff_draft(
        response.attribution_summary,
        document_loader=swing_tuning_document_loader(),
        active_setups=active_setups,
    )
    return {
        "schema_version": 1,
        "artifact_type": "swing_tuning_review",
        "intent": "deterministic_backtest_attribution_to_config_review_no_apply",
        "setup": response.setup,
        "start_date": response.start_date.isoformat(),
        "end_date": response.end_date.isoformat(),
        "sample": response.attribution_summary.sample_quality.to_dict(),
        "backtest_summary": {
            "initial_capital": str(response.initial_capital),
            "final_equity": str(response.final_equity),
            "total_return_pct": response.total_return_pct,
            "max_drawdown_pct": response.max_drawdown_pct,
            "trade_count": response.trade_count,
            "win_rate_pct": response.win_rate_pct,
            "avg_trade_return_pct": response.avg_trade_return_pct,
            "profit_factor": response.profit_factor,
            "candidate_observation_count": len(response.candidate_observations),
        },
        "attribution_summary": response.attribution_summary.to_dict(),
        "tuning_plan": plan.to_dict(),
        "tuning_proposal": proposal.to_dict(),
        "tuning_config_diff": config_diff.to_dict(),
        "apply": {
            "supported": False,
            "reason": "This command is review-only. Edit YAML manually after human review.",
        },
    }


def _swing_tuning_patch_payload(review_payload: dict) -> dict:
    tuning_config_diff = review_payload.get("tuning_config_diff") or {}
    diff_items = tuning_config_diff.get("diff_items") or []
    patch_items = [
        {
            "target_path": item.get("target_path"),
            "parsed_target_path": item.get("parsed_target_path"),
            "current_value": item.get("current_value"),
            "proposed_value": item.get("proposed_value"),
            "rationale": item.get("rationale"),
            "confidence": item.get("confidence"),
            "status": item.get("status"),
            "value_selection_policy": item.get("value_selection_policy"),
            "target_classification": item.get("target_classification"),
            "evidence_snapshot": item.get("evidence_snapshot"),
            "evidence_dimensions": item.get("evidence_dimensions"),
        }
        for item in diff_items
        if item.get("proposed_value") is not None
    ]
    return {
        "schema_version": 1,
        "artifact_type": "swing_tuning_patch_review",
        "intent": "review_only_candidate_config_patch_no_apply",
        "source_review": {
            "setup": review_payload.get("setup"),
            "start_date": review_payload.get("start_date"),
            "end_date": review_payload.get("end_date"),
            "sample": review_payload.get("sample"),
            "backtest_summary": review_payload.get("backtest_summary"),
            "tuning_config_diff_status": tuning_config_diff.get("status"),
            "tuning_config_diff_summary": tuning_config_diff.get("summary"),
            "is_ratio": review_payload.get("is_ratio"),
            "is_end_date": review_payload.get("is_end_date"),
            "oos_start_date": review_payload.get("oos_start_date"),
            "full_end_date": review_payload.get("full_end_date"),
            "oos_backtest_summary": review_payload.get("oos_backtest_summary"),
            "walk_forward_enforced": review_payload.get("is_end_date") is not None,
        },
        "patch_items": patch_items,
        "item_count": len(patch_items),
        "apply": {
            "supported": False,
            "reason": "Patch export is review-only and must not mutate YAML.",
        },
    }


def _export_swing_tuning_patch(review_payload: dict, path: Path) -> dict:
    patch_payload = _swing_tuning_patch_payload(review_payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(patch_payload, indent=2, default=str) + "\n")
    return {
        "path": str(path),
        "item_count": patch_payload["item_count"],
        "artifact_type": patch_payload["artifact_type"],
    }


def swing_tune(
    tickers: Annotated[
        Optional[list[str]],
        typer.Argument(help="Explicit ticker symbols (e.g. BBCA BBRI)"),
    ] = None,
    universe: Annotated[
        Optional[str],
        typer.Option(
            "--universe",
            "-u",
            help="Universe name or 'cached' — see `saham fetch universe list`",
        ),
    ] = None,
    setup: Annotated[
        str,
        typer.Option("--setup", help="Swing setup to validate"),
    ] = BACKTEST_FOREIGN_BOUNCE_SETUP,
    start: Annotated[
        str,
        typer.Option("--start", help="Backtest start date, YYYY-MM-DD"),
    ] = APP_CFG.backtest.start_date,
    end: Annotated[
        Optional[str],
        typer.Option("--end", help="Backtest end date, YYYY-MM-DD (default: today)"),
    ] = None,
    capital: Annotated[
        int,
        typer.Option("--capital", "-c", help="Initial capital in IDR", min=1),
    ] = _BT.capital,
    risk_pct: Annotated[
        float,
        typer.Option("--risk-pct", help="% of capital risked per trade", min=0.01),
    ] = _BT.risk_pct,
    max_positions: Annotated[
        int,
        typer.Option("--max-positions", help="Maximum concurrent open positions", min=1),
    ] = _BT.max_positions,
    take_profit: Annotated[
        float,
        typer.Option("--take-profit", help="Take-profit percentage", min=0.01),
    ] = _BT.take_profit_pct,
    stop_loss: Annotated[
        float,
        typer.Option("--stop-loss", help="Stop-loss percentage", min=0.01),
    ] = _BT.stop_loss_pct,
    max_hold: Annotated[
        int,
        typer.Option("--max-hold", help="Maximum holding period in trading days", min=1),
    ] = _BT.max_hold_days,
    cost_bps: Annotated[
        float,
        typer.Option(
            "--cost-bps",
            help="One-way transaction cost in basis points (20 ~= 0.20%)",
            min=0,
        ),
    ] = _BT.cost_bps,
    with_regime: Annotated[
        bool,
        typer.Option("--with-regime", help="Group evidence by entry-date market regime"),
    ] = False,
    allow_regimes: Annotated[
        Optional[str],
        typer.Option(
            "--allow-regimes",
            help="Comma-separated entry regimes allowed to open trades",
        ),
    ] = None,
    benchmark: Annotated[
        str,
        typer.Option("--benchmark", help="Benchmark ticker for regime context"),
    ] = APP_CFG.analysis.benchmark,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = APP_CFG.analysis.format,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
    save: Annotated[
        bool,
        typer.Option(
            "--save",
            help="Append the tuning review artifact to the local JSONL journal",
        ),
    ] = False,
    journal: Annotated[
        Optional[Path],
        typer.Option("--journal", help="Override swing tuning review journal path"),
    ] = None,
    export_patch: Annotated[
        Optional[Path],
        typer.Option(
            "--export-patch",
            help="Write proposed config values to a review-only JSON patch artifact",
        ),
    ] = None,
    is_ratio: Annotated[
        Optional[float],
        typer.Option(
            "--is-ratio",
            help=(
                "In-sample ratio 0.0–1.0 (e.g. 0.70 = 70% IS / 30% OOS). "
                "Default: 1.0 (no split)."
            ),
        ),
    ] = None,
) -> None:
    """
    Build deterministic swing tuning review from walk-forward attribution.

    This is the first-class tuning-loop entry point for swing. It replays the
    deterministic workflow, summarizes attribution, and emits guarded config
    review artifacts. It never calls AI and never writes YAML.
    """
    if is_ratio is not None:
        if end is None:
            typer.echo(
                "Error: --is-ratio requires --end to define the full date range.",
                err=True,
            )
            raise typer.Exit(1)
        if not (0.0 < is_ratio < 1.0):
            typer.echo(
                f"Error: --is-ratio must be in range (0.0, 1.0) exclusive, got {is_ratio}",
                err=True,
            )
            raise typer.Exit(1)

    effective_end = end
    is_end_date: str | None = None
    oos_start_date: str | None = None
    if is_ratio is not None and start and end:
        start_dt = date.fromisoformat(start)
        end_dt = date.fromisoformat(end)
        if start_dt >= end_dt:
            typer.echo("Error: --start must be before --end.", err=True)
            raise typer.Exit(1)
        total_days = (end_dt - start_dt).days
        is_end_dt = start_dt + timedelta(days=int(total_days * is_ratio))
        oos_start_dt = is_end_dt + timedelta(days=1)
        if is_end_dt <= start_dt or oos_start_dt > end_dt:
            typer.echo(
                "Error: --is-ratio requires a date range large enough to produce "
                "non-empty IS and OOS windows.",
                err=True,
            )
            raise typer.Exit(1)
        effective_end = is_end_dt.isoformat()
        is_end_date = effective_end
        oos_start_date = oos_start_dt.isoformat()
        if output_format != "json":
            typer.echo(
                f"Walk-forward split: IS {start} -> {is_end_dt.isoformat()}  "
                f"OOS {oos_start_dt.isoformat()} -> {end}"
            )

    response = _run_swing_backtest(
        tickers=tickers,
        universe=universe,
        setup=setup,
        start=start,
        end=effective_end,
        capital=capital,
        risk_pct=risk_pct,
        max_positions=max_positions,
        take_profit=take_profit,
        stop_loss=stop_loss,
        max_hold=max_hold,
        cost_bps=cost_bps,
        with_regime=with_regime,
        allow_regimes=allow_regimes,
        benchmark=benchmark,
        db_path=db_path,
        announce=output_format != "json",
    )

    payload = _swing_tuning_payload(response)
    if is_ratio is not None:
        payload["is_ratio"] = round(is_ratio, 4)
        if is_end_date and oos_start_date and end:
            payload["is_end_date"] = is_end_date
            payload["oos_start_date"] = oos_start_date
            payload["full_end_date"] = end
            oos_response = _run_swing_backtest(
                tickers=tickers,
                universe=universe,
                setup=setup,
                start=oos_start_date,
                end=end,
                capital=capital,
                risk_pct=risk_pct,
                max_positions=max_positions,
                take_profit=take_profit,
                stop_loss=stop_loss,
                max_hold=max_hold,
                cost_bps=cost_bps,
                with_regime=with_regime,
                allow_regimes=allow_regimes,
                benchmark=benchmark,
                db_path=db_path,
                announce=False,
            )
            payload["oos_backtest_summary"] = {
                "trade_count": oos_response.trade_count,
                "total_return_pct": oos_response.total_return_pct,
                "win_rate_pct": oos_response.win_rate_pct,
                "max_drawdown_pct": oos_response.max_drawdown_pct,
                "avg_trade_return_pct": oos_response.avg_trade_return_pct,
                "profit_factor": oos_response.profit_factor,
            }
    if save:
        journal_path = journal or DEFAULT_SWING_TUNING_REVIEW_JOURNAL_PATH
        save_result = SwingTuningReviewJournal(
            SwingTuningReviewJsonlWriter(journal_path)
        ).append_review(payload)
        payload["persistence"] = {
            **save_result.to_dict(),
            "path": str(journal_path),
        }
    if export_patch is not None:
        payload["patch_export"] = _export_swing_tuning_patch(
            payload,
            export_patch,
        )

    if output_format == "json":
        typer.echo(json.dumps(payload, indent=2, default=str))
        return

    display_swing_backtest(
        response,
        show_trades=0,
        show_attribution=True,
        show_tuning_plan=True,
        show_tuning_proposal=True,
        show_tuning_diff=True,
    )
    if save:
        persistence = payload["persistence"]
        typer.echo(
            f"Saved swing tuning review -> {persistence['path']} "
            f"(records={persistence['record_count']})"
        )
    if export_patch is not None:
        patch_export = payload["patch_export"]
        typer.echo(
            f"Exported swing tuning patch -> {patch_export['path']} "
            f"(items={patch_export['item_count']})"
        )
