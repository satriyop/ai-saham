"""Tests for the accumulation-audit CLI workflow factory."""

from pathlib import Path

from src.adapters.cli import analyze_accum_workflow_factory as factory
from src.application.dto.accumulation_audit import AccumulationAuditPolicy
from src.application.use_case.run_accumulation_audit_workflow_use_case import (
    RunAccumulationAuditWorkflowUseCase,
)


class _FakeAuditConfig:
    policy = AccumulationAuditPolicy()
    setups = {"foreign-bounce": {"window": 10}}


class _FakeScreenerConfig:
    derived_features = object()
    accum_score_policy = None


class _FakeAuditUseCase:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def test_factory_returns_workflow_use_case(monkeypatch):
    monkeypatch.setattr(
        factory, "load_accumulation_audit_config", lambda: _FakeAuditConfig()
    )
    monkeypatch.setattr(
        factory, "load_accumulation_screener_config", lambda: _FakeScreenerConfig()
    )
    monkeypatch.setattr(factory, "SQLiteBrokerRepository", lambda db_path: object())
    monkeypatch.setattr(factory, "SQLiteMarketRepository", lambda db_path: object())
    monkeypatch.setattr(factory, "create_indicator_registry", lambda: object())
    monkeypatch.setattr(factory, "RulesYamlLoader", lambda: object())
    monkeypatch.setattr(factory, "AccumulationAuditUseCase", _FakeAuditUseCase)

    workflow = factory.create_run_accumulation_audit_workflow(db_path=Path("test.db"))

    assert isinstance(workflow, RunAccumulationAuditWorkflowUseCase)


def test_factory_wires_audit_use_case_with_infrastructure_dependencies(monkeypatch):
    captured = {}

    def _fake_audit_use_case(**kwargs):
        captured.update(kwargs)
        return _FakeAuditUseCase(**kwargs)

    monkeypatch.setattr(
        factory, "load_accumulation_audit_config", lambda: _FakeAuditConfig()
    )
    monkeypatch.setattr(
        factory, "load_accumulation_screener_config", lambda: _FakeScreenerConfig()
    )
    broker_repo = object()
    market_repo = object()
    registry = object()
    rules_loader = object()
    monkeypatch.setattr(factory, "SQLiteBrokerRepository", lambda db_path: broker_repo)
    monkeypatch.setattr(factory, "SQLiteMarketRepository", lambda db_path: market_repo)
    monkeypatch.setattr(factory, "create_indicator_registry", lambda: registry)
    monkeypatch.setattr(factory, "RulesYamlLoader", lambda: rules_loader)
    monkeypatch.setattr(factory, "AccumulationAuditUseCase", _fake_audit_use_case)

    factory.create_run_accumulation_audit_workflow(db_path=Path("test.db"))

    assert captured["broker_repository"] is broker_repo
    assert captured["market_repository"] is market_repo
    assert captured["indicator_registry"] is registry
    assert captured["rules_loader"] is rules_loader
    assert captured["derived_feature_policy"] is _FakeScreenerConfig.derived_features


def test_factory_module_imports_infrastructure():
    import inspect

    source = inspect.getsource(factory)
    assert "src.infrastructure" in source


def test_no_config_loading_remains_in_cli_command_module():
    import inspect

    from src.adapters.cli import analyze_accum_commands

    source = inspect.getsource(analyze_accum_commands)
    assert "load_accumulation_audit_config" not in source
    assert "load_accumulation_screener_config" not in source
