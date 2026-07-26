"""
Factory for the `saham analyze risk` and `saham analyze compare` workflows.

Layer: Adapter

This module owns CLI/infrastructure wiring so analyze_risk_commands.py and
analyze_compare_commands.py can stay focused on flag parsing, request
construction, execution, and rendering.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from src.adapters.composition.risk_engine_helper import create_configured_risk_engine
from src.application.use_case.explain_risk_use_case import ExplainRiskUseCase
from src.application.use_case.run_risk_analysis_workflow_use_case import (
    RunRiskAnalysisWorkflowUseCase,
)
from src.application.use_case.run_risk_compare_use_case import RunRiskCompareUseCase
from src.infrastructure.ai import ExplainerFactory
from src.infrastructure.config.rules_yaml_loader import RulesYamlLoader
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository
from src.infrastructure.sentiment import SentimentFactory


def _fetch_sentiment_snapshot(ticker: str, provider_name: str, no_ai: bool) -> Any:
    """Fetch a sentiment snapshot using the configured news provider/classifier."""
    from src.application.use_case.fetch_sentiment_use_case import (
        FetchSentimentRequest,
        FetchSentimentUseCase,
    )

    news_provider = SentimentFactory.create_news_provider(provider_name)
    classifier = SentimentFactory.create_classifier(use_ai=not no_ai)
    response = FetchSentimentUseCase(
        news_provider=news_provider,
        classifier=classifier,
    ).execute(FetchSentimentRequest(ticker=ticker))
    return response.snapshot


def create_run_risk_analysis_workflow(db_path: Path) -> RunRiskAnalysisWorkflowUseCase:
    """Build the risk analysis workflow use case with CLI infrastructure."""
    engine = create_configured_risk_engine(
        db_path, with_enrichment=True, rules_loader=RulesYamlLoader()
    )
    return RunRiskAnalysisWorkflowUseCase(
        risk_engine=engine,
        sentiment_fetcher=_fetch_sentiment_snapshot,
    )


def create_run_risk_compare_workflow(db_path: Path) -> RunRiskCompareUseCase:
    """Build the risk compare workflow use case with CLI infrastructure."""
    engine = create_configured_risk_engine(
        db_path, with_enrichment=True, rules_loader=RulesYamlLoader()
    )
    repository = SQLiteMarketRepository(db_path=db_path)
    return RunRiskCompareUseCase(risk_engine=engine, market_repository=repository)


def create_explain_risk_use_case(
    provider: Optional[str] = None, model: Optional[str] = None
) -> ExplainRiskUseCase:
    """Build the AI explanation use case for the risk command's --explain flag."""
    explainer = ExplainerFactory.create(provider=provider, model=model)
    return ExplainRiskUseCase(explainer=explainer)
