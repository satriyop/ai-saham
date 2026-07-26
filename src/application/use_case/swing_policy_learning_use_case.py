"""Typed IS proposal, paired OOS validation, and guarded YAML application."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Mapping, Protocol, Sequence

from src.domain.ports.learning_artifact_repositories import (
    LearningEvaluationRepository,
    LearningPolicyApplicationRepository,
    LearningPolicyProposalRepository,
    LearningPolicyValidationRepository,
)
from src.domain.value_objects.learning_artifacts import (
    AssessmentPurpose,
    EvaluationMethod,
    EvaluationReadiness,
    LearningContractError,
    LearningEvaluation,
    LearningPolicyApplication,
    LearningPolicyProposal,
    LearningPolicyValidation,
    OutcomeBasis,
    ValidationStatus,
    artifact_digest,
)


@dataclass(frozen=True)
class SwingPolicySnapshot:
    config_hash: str
    values: Mapping[str, Any]


@dataclass(frozen=True)
class SwingLearningRow:
    row_id: str
    observed_at: datetime
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class SwingLearningDataset:
    compatibility_id: str
    dataset_fingerprint: str
    rows: tuple[SwingLearningRow, ...]


@dataclass(frozen=True)
class SwingPolicyMetrics:
    population_fingerprint: str
    net_return: float
    profit_factor: float
    average_return: float
    max_drawdown: float
    trade_count: int
    regime_stability: float
    authority_coverage: float
    setup_readiness: float

    def to_dict(self) -> dict[str, float | int]:
        return {
            "net_return": self.net_return,
            "profit_factor": self.profit_factor,
            "average_return": self.average_return,
            "max_drawdown": self.max_drawdown,
            "trade_count": self.trade_count,
            "regime_stability": self.regime_stability,
            "authority_coverage": self.authority_coverage,
            "setup_readiness": self.setup_readiness,
        }


class SwingPolicyEvaluator(Protocol):
    def evaluate(
        self,
        rows: Sequence[SwingLearningRow],
        policy: Mapping[str, Any],
    ) -> SwingPolicyMetrics: ...


class SwingProposalGenerator(Protocol):
    def generate(self, is_evaluation: LearningEvaluation) -> Mapping[str, Any]: ...


class ConservativeSwingExitProposalGenerator:
    """Propose one bounded execution TP change from IS performance only."""

    TARGET = (
        "config/swing_backtest.yaml:"
        "swing_backtest.execution.take_profit_pct"
    )

    def __init__(self, current_value: float, *, step: float = 0.5) -> None:
        if current_value <= 0 or step <= 0:
            raise LearningContractError("swing exit proposal values must be positive")
        self._current = float(current_value)
        self._step = float(step)

    def generate(self, is_evaluation: LearningEvaluation) -> Mapping[str, Any]:
        metrics = is_evaluation.metrics
        profit_factor = float(metrics.get("profit_factor") or 0.0)
        average_return = float(metrics.get("average_return") or 0.0)
        if profit_factor >= 1.0 and average_return > 0.0:
            proposed = self._current + self._step
        else:
            proposed = max(self._step, self._current - self._step)
        return {self.TARGET: round(proposed, 4)}


def swing_policy_metrics_from_backtest(
    response: Any,
    *,
    population_fingerprint: str,
) -> SwingPolicyMetrics:
    """Map the canonical backtest DTO into all paired validation dimensions."""

    candidates = tuple(response.candidate_observations)
    authority_coverage = (
        sum(candidate.signal_score is not None for candidate in candidates)
        / len(candidates)
        if candidates
        else 0.0
    )
    setup_readiness = (
        sum(candidate.setup_match in {"MATCH", "PARTIAL"} for candidate in candidates)
        / len(candidates)
        if candidates
        else 0.0
    )
    regime_stats = tuple(response.regime_stats)
    regime_stability = (
        sum(
            stat.avg_return_pct is not None and stat.avg_return_pct >= 0.0
            for stat in regime_stats
        )
        / len(regime_stats)
        if regime_stats
        else 0.0
    )
    return SwingPolicyMetrics(
        population_fingerprint=population_fingerprint,
        net_return=float(response.total_return_pct),
        profit_factor=float(response.profit_factor or 0.0),
        average_return=float(response.avg_trade_return_pct or 0.0),
        max_drawdown=float(response.max_drawdown_pct),
        trade_count=int(response.trade_count),
        regime_stability=regime_stability,
        authority_coverage=authority_coverage,
        setup_readiness=setup_readiness,
    )


class SwingPolicyConfigGateway(Protocol):
    def read_snapshot(self) -> SwingPolicySnapshot: ...

    def target_files_clean(self, changes: Mapping[str, Any]) -> bool: ...

    def apply_changes(self, changes: Mapping[str, Any]) -> None: ...


class SwingDatasetMarketRepository(Protocol):
    def get_candles(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> Sequence[Any]: ...


@dataclass(frozen=True)
class ResolveSwingLearningDatasetRequest:
    tickers: tuple[str, ...]
    start_date: date
    end_date: date
    compatibility_id: str
    benchmark: str = "IHSG"


class ResolveSwingLearningDatasetUseCase:
    """Freeze chronological session identities before any policy evaluation."""

    def __init__(self, market_data: SwingDatasetMarketRepository) -> None:
        self._market_data = market_data

    def execute(
        self, request: ResolveSwingLearningDatasetRequest
    ) -> SwingLearningDataset:
        if not request.tickers:
            raise LearningContractError("swing learning dataset requires tickers")
        candles = self._market_data.get_candles(
            request.benchmark,
            start_date=request.start_date,
            end_date=request.end_date,
        )
        sessions = sorted(
            {
                candle.date
                for candle in candles
                if request.start_date <= candle.date <= request.end_date
            }
        )
        if len(sessions) < 2:
            raise LearningContractError(
                "swing learning dataset requires at least two sessions"
            )
        tickers = tuple(sorted({ticker.upper() for ticker in request.tickers}))
        rows = tuple(
            SwingLearningRow(
                row_id=artifact_digest(
                    {
                        "session": session.isoformat(),
                        "tickers": tickers,
                        "benchmark": request.benchmark.upper(),
                    }
                ),
                observed_at=datetime.combine(
                    session,
                    datetime.min.time(),
                    tzinfo=timezone.utc,
                ),
                payload={
                    "session": session.isoformat(),
                    "tickers": tickers,
                    "benchmark": request.benchmark.upper(),
                },
            )
            for session in sessions
        )
        fingerprint = artifact_digest(
            {
                "row_ids": [row.row_id for row in rows],
                "compatibility_id": request.compatibility_id,
            }
        )
        return SwingLearningDataset(
            compatibility_id=request.compatibility_id,
            dataset_fingerprint=fingerprint,
            rows=rows,
        )


@dataclass(frozen=True)
class RunSwingPolicyReviewRequest:
    dataset: SwingLearningDataset
    baseline_policy: SwingPolicySnapshot
    is_ratio: float
    evaluated_at: datetime


@dataclass(frozen=True)
class RunSwingPolicyReviewResult:
    is_evaluation: LearningEvaluation
    proposal: LearningPolicyProposal
    baseline_oos_evaluation: LearningEvaluation
    proposed_oos_evaluation: LearningEvaluation
    validation: LearningPolicyValidation


def _population_fingerprint(rows: Sequence[SwingLearningRow]) -> str:
    return artifact_digest({"row_ids": [row.row_id for row in rows]})


class RunSwingPolicyReviewUseCase:
    """Run the staged review while keeping OOS absent from proposal generation."""

    def __init__(
        self,
        *,
        evaluator: SwingPolicyEvaluator,
        proposal_generator: SwingProposalGenerator,
        evaluations: LearningEvaluationRepository,
        proposals: LearningPolicyProposalRepository,
        validations: LearningPolicyValidationRepository,
    ) -> None:
        self._evaluator = evaluator
        self._proposal_generator = proposal_generator
        self._evaluations = evaluations
        self._proposals = proposals
        self._validations = validations

    def execute(
        self, request: RunSwingPolicyReviewRequest
    ) -> RunSwingPolicyReviewResult:
        if not 0.0 < request.is_ratio < 1.0:
            raise LearningContractError("is_ratio must be between zero and one")
        rows = tuple(sorted(request.dataset.rows, key=lambda row: (row.observed_at, row.row_id)))
        split_index = int(len(rows) * request.is_ratio)
        if split_index < 1 or split_index >= len(rows):
            raise LearningContractError("chronological split requires non-empty IS and OOS")
        is_rows = rows[:split_index]
        oos_rows = rows[split_index:]
        is_population = _population_fingerprint(is_rows)
        oos_population = _population_fingerprint(oos_rows)

        is_metrics = self._evaluator.evaluate(is_rows, request.baseline_policy.values)
        self._require_population(is_metrics, is_population, "IS baseline")
        is_evaluation = self._evaluation(
            request=request,
            metrics=is_metrics,
            population_rows=is_rows,
            population_role="IS_BASELINE",
            readiness=EvaluationReadiness.OOS_DIAGNOSTIC_READY,
        )
        self._evaluations.add_evaluation(is_evaluation)

        # This is the sole proposal-generator call. Its type accepts only the
        # frozen IS evaluation, so OOS rows/results cannot cross the boundary.
        changes = dict(self._proposal_generator.generate(is_evaluation))
        proposal = LearningPolicyProposal.create(
            source_evaluation_id=is_evaluation.evaluation_id,
            current_config_hash=request.baseline_policy.config_hash,
            changes=changes,
            rationale={
                "source": "IS_ATTRIBUTION_ONLY",
                "dataset_fingerprint": request.dataset.dataset_fingerprint,
                "is_population_fingerprint": is_population,
                "oos_population_fingerprint": oos_population,
            },
            created_at=request.evaluated_at,
        )
        self._proposals.add_proposal(proposal)

        baseline_oos_metrics = self._evaluator.evaluate(
            oos_rows, request.baseline_policy.values
        )
        proposed_policy = {**request.baseline_policy.values, **proposal.changes}
        proposed_oos_metrics = self._evaluator.evaluate(oos_rows, proposed_policy)
        self._require_population(baseline_oos_metrics, oos_population, "OOS baseline")
        self._require_population(proposed_oos_metrics, oos_population, "OOS proposed")

        paired_deltas = self._paired_deltas(
            baseline_oos_metrics, proposed_oos_metrics
        )
        issues = self._validation_issues(
            baseline_oos_metrics, proposed_oos_metrics
        )
        status = ValidationStatus.PASS if not issues else ValidationStatus.FAIL
        proposed_readiness = (
            EvaluationReadiness.POLICY_REVIEW_ELIGIBLE
            if status is ValidationStatus.PASS
            else EvaluationReadiness.OOS_DIAGNOSTIC_READY
        )
        baseline_oos_evaluation = self._evaluation(
            request=request,
            metrics=baseline_oos_metrics,
            population_rows=oos_rows,
            population_role="OOS_BASELINE",
            readiness=EvaluationReadiness.OOS_DIAGNOSTIC_READY,
        )
        proposed_oos_evaluation = self._evaluation(
            request=request,
            metrics=proposed_oos_metrics,
            population_rows=oos_rows,
            population_role=f"OOS_PROPOSED:{proposal.proposal_id}",
            readiness=proposed_readiness,
        )
        self._evaluations.add_evaluation(baseline_oos_evaluation)
        self._evaluations.add_evaluation(proposed_oos_evaluation)
        validation = LearningPolicyValidation.create(
            proposal_id=proposal.proposal_id,
            baseline_evaluation_id=baseline_oos_evaluation.evaluation_id,
            proposed_evaluation_id=proposed_oos_evaluation.evaluation_id,
            population_fingerprint=oos_population,
            paired_deltas=paired_deltas,
            issues=tuple(issues),
            status=status,
            validated_at=request.evaluated_at,
        )
        self._validations.add_validation(validation)
        return RunSwingPolicyReviewResult(
            is_evaluation=is_evaluation,
            proposal=proposal,
            baseline_oos_evaluation=baseline_oos_evaluation,
            proposed_oos_evaluation=proposed_oos_evaluation,
            validation=validation,
        )

    @staticmethod
    def _require_population(
        metrics: SwingPolicyMetrics, expected: str, label: str
    ) -> None:
        if metrics.population_fingerprint != expected:
            raise LearningContractError(
                f"{label} evaluator changed the immutable population"
            )

    @staticmethod
    def _evaluation(
        *,
        request: RunSwingPolicyReviewRequest,
        metrics: SwingPolicyMetrics,
        population_rows: Sequence[SwingLearningRow],
        population_role: str,
        readiness: EvaluationReadiness,
    ) -> LearningEvaluation:
        return LearningEvaluation.create(
            purpose=AssessmentPurpose.SWING_TRADE_SETUP,
            method=EvaluationMethod.PORTFOLIO_WALK_FORWARD,
            compatibility_id=request.dataset.compatibility_id,
            dataset_fingerprint=request.dataset.dataset_fingerprint,
            split_contract=f"chronological_is_ratio:{request.is_ratio:.6f}:{population_role}",
            population={
                "role": population_role,
                "row_ids": [row.row_id for row in population_rows],
                "population_fingerprint": metrics.population_fingerprint,
            },
            exclusions={},
            metrics=metrics.to_dict(),
            outcome_basis=OutcomeBasis.SIMULATED_NET_EXECUTION,
            readiness=readiness,
            evaluated_at=request.evaluated_at,
        )

    @staticmethod
    def _paired_deltas(
        baseline: SwingPolicyMetrics, proposed: SwingPolicyMetrics
    ) -> dict[str, float | int]:
        return {
            "net_return": proposed.net_return - baseline.net_return,
            "profit_factor": proposed.profit_factor - baseline.profit_factor,
            "average_return": proposed.average_return - baseline.average_return,
            "drawdown_regression": proposed.max_drawdown - baseline.max_drawdown,
            "trade_count": proposed.trade_count - baseline.trade_count,
            "regime_stability": proposed.regime_stability - baseline.regime_stability,
            "authority_coverage": (
                proposed.authority_coverage - baseline.authority_coverage
            ),
            "setup_readiness": proposed.setup_readiness - baseline.setup_readiness,
        }

    @staticmethod
    def _validation_issues(
        baseline: SwingPolicyMetrics, proposed: SwingPolicyMetrics
    ) -> list[str]:
        issues: list[str] = []
        if proposed.net_return <= baseline.net_return:
            issues.append("net_return_not_improved")
        if proposed.profit_factor < baseline.profit_factor:
            issues.append("profit_factor_regressed")
        if proposed.average_return < baseline.average_return:
            issues.append("average_return_regressed")
        if proposed.max_drawdown > baseline.max_drawdown:
            issues.append("drawdown_regressed")
        if proposed.trade_count < max(1, baseline.trade_count):
            issues.append("trade_count_regressed")
        if proposed.regime_stability < baseline.regime_stability:
            issues.append("regime_stability_regressed")
        if proposed.authority_coverage < baseline.authority_coverage:
            issues.append("authority_coverage_regressed")
        if proposed.setup_readiness < baseline.setup_readiness:
            issues.append("setup_readiness_regressed")
        return issues


@dataclass(frozen=True)
class ApplySwingPolicyRequest:
    proposal_id: str
    confirmed: bool
    confirmation_identity: str
    applied_at: datetime


class ApplySwingPolicyUseCase:
    """Apply one passing, unused, hash-current proposal and persist verification."""

    def __init__(
        self,
        *,
        proposals: LearningPolicyProposalRepository,
        validations: LearningPolicyValidationRepository,
        applications: LearningPolicyApplicationRepository,
        config_gateway: SwingPolicyConfigGateway,
    ) -> None:
        self._proposals = proposals
        self._validations = validations
        self._applications = applications
        self._config = config_gateway

    def execute(self, request: ApplySwingPolicyRequest) -> LearningPolicyApplication:
        if not request.confirmed:
            raise LearningContractError("policy application requires explicit --yes")
        proposal = self._proposals.get_proposal(request.proposal_id)
        if proposal is None:
            raise LearningContractError("policy proposal not found")
        validation = self._validations.get_validation_for_proposal(request.proposal_id)
        if validation is None or validation.status is not ValidationStatus.PASS:
            raise LearningContractError("policy application requires passing validation")
        if self._applications.get_application_for_proposal(request.proposal_id) is not None:
            raise LearningContractError("policy proposal has already been applied")
        before = self._config.read_snapshot()
        if before.config_hash != proposal.current_config_hash:
            raise LearningContractError("production config hash is stale")
        if not self._config.target_files_clean(proposal.changes):
            raise LearningContractError("target YAML files have uncommitted changes")
        self._config.apply_changes(proposal.changes)
        after = self._config.read_snapshot()
        expected_values = {**before.values, **proposal.changes}
        if after.values != expected_values:
            raise LearningContractError("YAML reread verification mismatch")
        if after.config_hash == before.config_hash:
            raise LearningContractError("applied config hash did not change")
        application = LearningPolicyApplication.create(
            proposal_id=proposal.proposal_id,
            validation_id=validation.validation_id,
            previous_config_hash=before.config_hash,
            applied_config_hash=after.config_hash,
            exact_changes=proposal.changes,
            confirmation_identity=request.confirmation_identity,
            applied_at=request.applied_at,
            reread_verified=True,
        )
        self._applications.add_application(application)
        return application
