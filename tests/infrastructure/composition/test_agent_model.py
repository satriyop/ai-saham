import pytest

from src.infrastructure.composition.agent_model import build_agent_composition
from src.infrastructure.config.app_config import AiConfig

pytestmark = pytest.mark.agent


def test_disabled_composition_does_not_construct_provider(monkeypatch) -> None:
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    result = build_agent_composition(AiConfig(enabled=False, provider="deepseek"))
    assert result.provider_available is False
    assert result.use_case.provider_available is False


def test_enabled_missing_key_is_fail_soft(monkeypatch) -> None:
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    result = build_agent_composition(AiConfig(enabled=True, provider="deepseek"))
    assert result.provider_available is False
    assert result.configured_provider == "deepseek"


def test_environment_provider_overrides_config_without_fallback(monkeypatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "unused")
    result = build_agent_composition(AiConfig(enabled=True, provider="deepseek"))
    assert result.configured_provider == "openai"
    assert result.provider_available is False


def test_explicit_provider_overrides_environment(monkeypatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "openai")
    result = build_agent_composition(AiConfig(enabled=True, provider="deepseek"), provider="gemini")
    assert result.configured_provider == "gemini"
    assert result.provider_available is False
