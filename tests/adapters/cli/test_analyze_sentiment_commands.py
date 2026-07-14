"""Tests for the `saham analyze sentiment` / `saham analyze audit` CLI split."""

from datetime import datetime
from pathlib import Path

from typer.testing import CliRunner

from src.adapters.cli import (
    analyze_sentiment_commands,
    analyze_sentiment_workflow_factory,
)
from src.adapters.cli.analyze_commands import analyze_app
from src.application.use_case.audit_sentiment_use_case import AuditSentimentResponse
from src.application.use_case.fetch_sentiment_use_case import FetchSentimentResponse
from src.domain.value_objects.sentiment import Sentiment, SentimentSnapshot

runner = CliRunner()


def _snapshot() -> SentimentSnapshot:
    return SentimentSnapshot(
        ticker="BBCA",
        headlines=(),
        positive_count=2,
        neutral_count=1,
        negative_count=0,
        overall_sentiment=Sentiment.POSITIVE,
        fetched_at=datetime(2026, 7, 10),
    )


class FakeFetchUseCase:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class FakeAuditUseCase:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _private_display_helper_names() -> list[str]:
    # Built dynamically so this test file itself does not trip the
    # repo-wide grep for these forbidden literal tokens.
    prefix = "_display_sentiment_"
    return [prefix + "full", prefix + "brief"]


def test_command_module_has_no_display_or_infra_imports():
    source = Path(analyze_sentiment_commands.__file__).read_text()
    forbidden = [
        "Console",
        "Panel",
        "Table",
        "Text",
        "SentimentFactory",
        "SQLiteSentimentRepository",
        "SQLiteMarketRepository",
        "create_group_mapping_service",
        *_private_display_helper_names(),
    ]
    for token in forbidden:
        assert token not in source, f"{token} should not appear in analyze_sentiment_commands.py"


def test_no_private_display_helper_remains_in_cli_modules():
    cli_dir = Path(__file__).resolve().parents[3] / "src" / "adapters" / "cli"
    for py_file in cli_dir.glob("*.py"):
        source = py_file.read_text()
        for token in _private_display_helper_names():
            assert token not in source, f"{token} should not appear in {py_file}"


def test_fetch_factory_wires_expected_dependencies(monkeypatch):
    calls = {}

    class FakeNewsProvider:
        pass

    class FakeClassifier:
        pass

    def _fake_create_news_provider(name):
        calls["news_provider_name"] = name
        return FakeNewsProvider()

    def _fake_create_classifier(use_ai, provider, model):
        calls["use_ai"] = use_ai
        calls["provider"] = provider
        calls["model"] = model
        return FakeClassifier()

    monkeypatch.setattr(
        analyze_sentiment_workflow_factory.SentimentFactory,
        "create_news_provider",
        _fake_create_news_provider,
    )
    monkeypatch.setattr(
        analyze_sentiment_workflow_factory.SentimentFactory,
        "create_classifier",
        _fake_create_classifier,
    )
    monkeypatch.setattr(
        analyze_sentiment_workflow_factory,
        "create_group_mapping_service",
        lambda: object(),
    )

    captured_repo_db_path = {}

    class FakeSentimentRepo:
        def __init__(self, db_path):
            captured_repo_db_path["db_path"] = db_path

    monkeypatch.setattr(
        analyze_sentiment_workflow_factory, "SQLiteSentimentRepository", FakeSentimentRepo
    )

    db_path = Path("/tmp/test.db")
    use_case = analyze_sentiment_workflow_factory.create_fetch_sentiment_use_case(
        db_path=db_path,
        news_provider_name="mock",
        use_ai=False,
        provider="deepseek",
        model="foo-model",
    )

    assert calls["news_provider_name"] == "mock"
    assert calls["use_ai"] is False
    assert calls["provider"] == "deepseek"
    assert calls["model"] == "foo-model"
    assert captured_repo_db_path["db_path"] == db_path
    assert isinstance(use_case._news_provider, FakeNewsProvider)
    assert isinstance(use_case._classifier, FakeClassifier)


def test_audit_factory_wires_both_repositories_with_same_db_path(monkeypatch):
    seen_db_paths = []

    class FakeSentimentRepo:
        def __init__(self, db_path):
            seen_db_paths.append(("sentiment", db_path))

    class FakeMarketRepo:
        def __init__(self, db_path):
            seen_db_paths.append(("market", db_path))

    monkeypatch.setattr(
        analyze_sentiment_workflow_factory, "SQLiteSentimentRepository", FakeSentimentRepo
    )
    monkeypatch.setattr(
        analyze_sentiment_workflow_factory, "SQLiteMarketRepository", FakeMarketRepo
    )

    db_path = Path("/tmp/audit.db")
    analyze_sentiment_workflow_factory.create_audit_sentiment_use_case(db_path=db_path)

    assert seen_db_paths == [("sentiment", db_path), ("market", db_path)]


def test_sentiment_command_delegates_to_factory_and_prints_header(monkeypatch):
    response = FetchSentimentResponse(
        ticker="BBCA",
        snapshot=_snapshot(),
        provider="mock",
        classifier="keyword",
        success=True,
    )
    fake_use_case = FakeFetchUseCase(response)

    monkeypatch.setattr(
        analyze_sentiment_commands,
        "create_fetch_sentiment_use_case",
        lambda **kwargs: fake_use_case,
    )

    result = runner.invoke(
        analyze_app, ["sentiment", "BBCA", "--news-provider", "mock", "--no-ai"]
    )

    assert result.exit_code == 0
    assert "Fetching news sentiment for BBCA..." in result.stdout
    assert len(fake_use_case.requests) == 1
    request = fake_use_case.requests[0]
    assert request.ticker == "BBCA"
    assert request.max_headlines == 20
    assert request.days == 3


def test_audit_command_delegates_to_factory_and_prints_header(monkeypatch):
    response = AuditSentimentResponse(
        logs_audited=0,
        audits_saved=0,
        stats={"audited_logs": 0},
    )
    fake_use_case = FakeAuditUseCase(response)

    monkeypatch.setattr(
        analyze_sentiment_commands,
        "create_audit_sentiment_use_case",
        lambda **kwargs: fake_use_case,
    )

    result = runner.invoke(analyze_app, ["audit"])

    assert result.exit_code == 0
    assert "Auditing past sentiment predictions..." in result.stdout
    assert len(fake_use_case.requests) == 1
