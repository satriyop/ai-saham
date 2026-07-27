"""Thin CLI adapters for database-owned swing policy learning."""

from __future__ import annotations

import getpass
import json
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Any, Optional, Sequence

import typer

from src.adapters.cli.backtest_portfolio_runner import (
    _run_swing_backtest,
    load_swing_backtest_runner_config,
)
from src.adapters.composition.stock_analysis_workflow_dependencies import (
    create_stock_analysis_workflow_dependencies,
)
from src.application.services.universe_loader import (
    UniverseNotFoundError,
    resolve_tickers,
)
from src.application.use_case.swing_policy_learning_use_case import (
    ApplySwingPolicyRequest,
    ApplySwingPolicyUseCase,
    ConservativeSwingExitProposalGenerator,
    ResolveSwingLearningDatasetRequest,
    ResolveSwingLearningDatasetUseCase,
    RunSwingPolicyReviewRequest,
    RunSwingPolicyReviewUseCase,
    SwingLearningRow,
    SwingPolicyEvaluator,
    SwingPolicyMetrics,
    swing_policy_metrics_from_backtest,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.learning_artifacts import (
    AssessmentPurpose,
    LearningContractError,
    ValidationStatus,
    artifact_digest,
)
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.swing_policy_config_gateway import (
    YamlSwingPolicyConfigGateway,
)
from src.infrastructure.config.universe_config_loader import YamlUniverseConfigLoader
from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
    SQLiteLearningArtifactRepository,
)


class _BacktestPolicyEvaluator(SwingPolicyEvaluator):
    def __init__(
        self,
        *,
        tickers: list[str],
        setup: str,
        capital: int,
        risk_pct: float,
        max_positions: int,
        max_hold: int,
        cost_bps: float,
        with_regime: bool,
        benchmark: str,
        db_path: Path,
        dependencies: Any,
    ) -> None:
        self._tickers = tickers
        self._setup = setup
        self._capital = capital
        self._risk_pct = risk_pct
        self._max_positions = max_positions
        self._max_hold = max_hold
        self._cost_bps = cost_bps
        self._with_regime = with_regime
        self._benchmark = benchmark
        self._db_path = db_path
        self._dependencies = dependencies

    def evaluate(
        self,
        rows: Sequence[SwingLearningRow],
        policy: dict[str, Any],
    ) -> SwingPolicyMetrics:
        if not rows:
            raise LearningContractError("swing evaluator received an empty population")
        sessions = [str(row.payload["session"]) for row in rows]
        take_profit = float(
            policy["config/swing_backtest.yaml:swing_backtest.execution.take_profit_pct"]
        )
        stop_loss = float(
            policy["config/swing_backtest.yaml:swing_backtest.execution.stop_loss_pct"]
        )
        response = _run_swing_backtest(
            tickers=self._tickers,
            universe=None,
            setup=self._setup,
            start=min(sessions),
            end=max(sessions),
            capital=self._capital,
            risk_pct=self._risk_pct,
            max_positions=self._max_positions,
            take_profit=take_profit,
            stop_loss=stop_loss,
            max_hold=self._max_hold,
            cost_bps=self._cost_bps,
            with_regime=self._with_regime,
            allow_regimes=None,
            benchmark=self._benchmark,
            db_path=self._db_path,
            announce=False,
            dependencies=self._dependencies,
        )
        return swing_policy_metrics_from_backtest(
            response,
            population_fingerprint=artifact_digest({"row_ids": [row.row_id for row in rows]}),
        )


def _echo(payload: dict[str, Any], fmt: str) -> None:
    if fmt == "json":
        typer.echo(json.dumps(payload, indent=2, default=str))
    else:
        for key, value in payload.items():
            typer.echo(f"{key}: {value}")


def swing_tune(
    tickers: Annotated[Optional[list[str]], typer.Argument(help="Explicit ticker symbols")] = None,
    universe: Annotated[Optional[str], typer.Option("--universe", "-u")] = None,
    setup: Annotated[str, typer.Option("--setup")] = "foreign-bounce",
    start: Annotated[Optional[str], typer.Option("--start")] = None,
    end: Annotated[Optional[str], typer.Option("--end")] = None,
    is_ratio: Annotated[float, typer.Option("--is-ratio", help="Chronological IS share")] = 0.7,
    with_regime: Annotated[bool, typer.Option("--with-regime")] = True,
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
    fmt: Annotated[str, typer.Option("--format")] = "table",
) -> None:
    """Run IS proposal generation and identical-population paired OOS validation."""

    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)
    start_date = date.fromisoformat(start or cfg.backtest.start_date)
    end_date = date.fromisoformat(end) if end else date.today()
    dependencies = create_stock_analysis_workflow_dependencies(resolved_db)
    try:
        resolved_tickers = resolve_tickers(
            universe=universe,
            explicit=list(tickers or ()),
            db_path=resolved_db,
            loader=YamlUniverseConfigLoader(),
            repository=dependencies.broker_repository,
        )
    except (UniverseNotFoundError, FileNotFoundError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    if not resolved_tickers:
        raise typer.BadParameter("provide tickers or --universe")

    gateway = YamlSwingPolicyConfigGateway(Path("."))
    baseline = gateway.read_snapshot()
    compatibility_id = artifact_digest(
        {
            "config_hash": baseline.config_hash,
            "setup": setup,
            "tickers": sorted(resolved_tickers),
        }
    )
    dataset = ResolveSwingLearningDatasetUseCase(dependencies.market_repository).execute(
        ResolveSwingLearningDatasetRequest(
            tickers=tuple(resolved_tickers),
            start_date=start_date,
            end_date=end_date,
            compatibility_id=compatibility_id,
            benchmark=cfg.analysis.benchmark,
        )
    )
    runner = load_swing_backtest_runner_config().backtest_config
    repository = SQLiteLearningArtifactRepository(resolved_db)
    result = RunSwingPolicyReviewUseCase(
        evaluator=_BacktestPolicyEvaluator(
            tickers=list(resolved_tickers),
            setup=setup,
            capital=runner.capital,
            risk_pct=runner.risk_pct,
            max_positions=runner.max_positions,
            max_hold=runner.max_hold_days,
            cost_bps=runner.cost_bps,
            with_regime=with_regime,
            benchmark=cfg.analysis.benchmark,
            db_path=resolved_db,
            dependencies=dependencies,
        ),
        proposal_generator=ConservativeSwingExitProposalGenerator(
            float(baseline.values[ConservativeSwingExitProposalGenerator.TARGET])
        ),
        evaluations=repository,
        proposals=repository,
        validations=repository,
    ).execute(
        RunSwingPolicyReviewRequest(
            dataset=dataset,
            baseline_policy=baseline,
            is_ratio=is_ratio,
            evaluated_at=datetime.now(IDX_TIMEZONE),
        )
    )
    _echo(
        {
            "artifact_type": "paired_swing_policy_review",
            "proposal_id": result.proposal.proposal_id,
            "changes": result.proposal.changes,
            "validation_id": result.validation.validation_id,
            "validation_status": result.validation.status.value,
            "issues": list(result.validation.issues),
            "readiness": result.proposed_oos_evaluation.readiness.value,
        },
        fmt,
    )


def swing_review(
    proposal_id: Annotated[Optional[str], typer.Argument()] = None,
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
    fmt: Annotated[str, typer.Option("--format")] = "table",
) -> None:
    """Review immutable proposal and paired-validation records."""

    cfg = load_app_config()
    repository = SQLiteLearningArtifactRepository(db_path or Path(cfg.storage.db_path))
    proposals = (
        [repository.get_proposal(proposal_id)] if proposal_id else list(repository.list_proposals())
    )
    proposals = [proposal for proposal in proposals if proposal is not None]
    _echo(
        {
            "artifact_type": "swing_policy_proposal_catalog",
            "proposals": [
                {
                    "proposal_id": proposal.proposal_id,
                    "changes": proposal.changes,
                    "validation_status": (
                        validation.status.value
                        if (
                            validation := repository.get_validation_for_proposal(
                                proposal.proposal_id
                            )
                        )
                        else None
                    ),
                }
                for proposal in proposals
            ],
        },
        fmt,
    )


def swing_validate(
    proposal_id: Annotated[str, typer.Argument()],
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
    fmt: Annotated[str, typer.Option("--format")] = "table",
) -> None:
    """Inspect the persisted paired OOS validation for a proposal."""

    cfg = load_app_config()
    repository = SQLiteLearningArtifactRepository(db_path or Path(cfg.storage.db_path))
    validation = repository.get_validation_for_proposal(proposal_id)
    if validation is None:
        typer.echo("Validation not found for proposal.", err=True)
        raise typer.Exit(1)
    _echo(
        {
            "artifact_type": "paired_swing_policy_validation",
            "proposal_id": proposal_id,
            "validation_id": validation.validation_id,
            "status": validation.status.value,
            "population_fingerprint": validation.population_fingerprint,
            "paired_deltas": validation.paired_deltas,
            "issues": list(validation.issues),
        },
        fmt,
    )
    if validation.status is ValidationStatus.FAIL:
        raise typer.Exit(1)


def swing_apply(
    proposal_id: Annotated[str, typer.Argument()],
    yes: Annotated[bool, typer.Option("--yes")] = False,
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
    fmt: Annotated[str, typer.Option("--format")] = "table",
) -> None:
    """Apply one passing proposal to clean YAML and audit reread verification."""

    cfg = load_app_config()
    repository = SQLiteLearningArtifactRepository(db_path or Path(cfg.storage.db_path))
    try:
        application = ApplySwingPolicyUseCase(
            proposals=repository,
            validations=repository,
            applications=repository,
            config_gateway=YamlSwingPolicyConfigGateway(Path(".")),
        ).execute(
            ApplySwingPolicyRequest(
                proposal_id=proposal_id,
                confirmed=yes,
                confirmation_identity=f"cli:{getpass.getuser()}",
                applied_at=datetime.now(IDX_TIMEZONE),
            )
        )
    except LearningContractError as exc:
        typer.echo(f"Apply blocked: {exc}", err=True)
        raise typer.Exit(1)
    _echo(
        {
            "artifact_type": "yaml_policy_application",
            "application_id": application.application_id,
            "proposal_id": proposal_id,
            "previous_config_hash": application.previous_config_hash,
            "applied_config_hash": application.applied_config_hash,
            "reread_verified": application.reread_verified,
        },
        fmt,
    )


def swing_status(
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
    fmt: Annotated[str, typer.Option("--format")] = "table",
) -> None:
    """Show database-owned swing evaluation and policy lifecycle counts."""

    cfg = load_app_config()
    repository = SQLiteLearningArtifactRepository(db_path or Path(cfg.storage.db_path))
    _echo(
        {
            "artifact_type": "swing_policy_status",
            "evaluation_count": len(
                repository.list_evaluations(AssessmentPurpose.SWING_TRADE_SETUP)
            ),
            "proposal_count": len(repository.list_proposals()),
            "validation_count": len(repository.list_validations()),
            "application_count": len(repository.list_applications()),
        },
        fmt,
    )
