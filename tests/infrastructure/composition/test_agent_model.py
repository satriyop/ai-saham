import pytest

from src.application.dto.agent_tools import AgentToolName
from src.application.use_case.orchestrate_agent_turn_use_case import AgentTurnOrchestrator
from src.infrastructure.composition import agent_model
from src.infrastructure.composition.agent_model import build_agent_composition
from src.infrastructure.config.app_config import AiConfig
from src.infrastructure.config.local_env import read_local_env_value

pytestmark = pytest.mark.agent


def test_disabled_composition_does_not_construct_provider(monkeypatch) -> None:
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    result = build_agent_composition(AiConfig(enabled=False, provider="deepseek"))
    assert result.provider_available is False
    assert result.use_case.provider_available is False
    assert result.tools_requested is False
    assert result.tools_enabled is False
    assert result.registered_tools == ()


def test_tools_require_both_ai_and_tool_flags(monkeypatch) -> None:
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(agent_model, "read_local_env_value", lambda name: None)

    disabled = build_agent_composition(
        AiConfig(enabled=False, provider="deepseek", tools_enabled=True)
    )
    zero_tool = build_agent_composition(
        AiConfig(enabled=True, provider="deepseek", tools_enabled=False)
    )
    enabled = build_agent_composition(
        AiConfig(enabled=True, provider="deepseek", tools_enabled=True)
    )

    assert disabled.tools_requested is False
    assert zero_tool.tools_requested is False
    assert enabled.tools_requested is True
    assert disabled.tools_enabled is False
    assert zero_tool.tools_enabled is False
    assert enabled.tools_enabled is False


def test_tools_register_only_visible_result_when_fully_enabled(monkeypatch) -> None:
    sentinel_model = object()
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(agent_model, "DeepSeekAgentModel", lambda key: sentinel_model)

    result = build_agent_composition(
        AiConfig(enabled=True, provider="deepseek", tools_enabled=True)
    )

    assert result.provider_available is True
    assert result.tools_requested is True
    assert result.tools_enabled is True
    assert isinstance(result.use_case, AgentTurnOrchestrator)
    assert result.registered_tools == (AgentToolName.GET_VISIBLE_COCKPIT_RESULT,)


def test_existing_db_registers_visible_and_ticker_dashboard_tools(
    monkeypatch,
    tmp_path,
) -> None:
    db_path = tmp_path / "dashboard.db"
    db_path.touch()
    sentinel_model = object()
    sentinel_dashboard = object()
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(agent_model, "DeepSeekAgentModel", lambda key: sentinel_model)
    monkeypatch.setattr(
        agent_model,
        "build_read_only_ticker_dashboard_use_case",
        lambda path: sentinel_dashboard,
    )

    result = build_agent_composition(
        AiConfig(enabled=True, provider="deepseek", tools_enabled=True),
        db_path=db_path,
    )

    assert result.registered_tools == (
        AgentToolName.GET_VISIBLE_COCKPIT_RESULT,
        AgentToolName.GET_TICKER_DASHBOARD,
    )


def test_missing_db_keeps_visible_tool_and_does_not_create_file(
    monkeypatch,
    tmp_path,
) -> None:
    db_path = tmp_path / "missing" / "dashboard.db"
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(agent_model, "DeepSeekAgentModel", lambda key: object())

    result = build_agent_composition(
        AiConfig(enabled=True, provider="deepseek", tools_enabled=True),
        db_path=db_path,
    )

    assert result.registered_tools == (AgentToolName.GET_VISIBLE_COCKPIT_RESULT,)
    assert not db_path.exists()


def test_enabled_missing_key_is_fail_soft(monkeypatch) -> None:
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(agent_model, "read_local_env_value", lambda name: None)
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


def test_local_env_reader_supports_export_quotes_and_last_value(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "# local only\nexport DEEPSEEK_API_KEY='first'\nOTHER=value\nDEEPSEEK_API_KEY=\"second\"\n",
        encoding="utf-8",
    )

    assert read_local_env_value("DEEPSEEK_API_KEY", path=env_path) == "second"
    assert read_local_env_value("MISSING", path=env_path) is None


def test_composition_uses_local_env_when_process_key_is_absent(monkeypatch) -> None:
    sentinel_model = object()
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(agent_model, "read_local_env_value", lambda name: "local-key")
    monkeypatch.setattr(agent_model, "DeepSeekAgentModel", lambda key: sentinel_model)

    result = build_agent_composition(AiConfig(enabled=True, provider="deepseek"))

    assert result.provider_available is True
    assert result.use_case.provider_available is True


def test_process_key_takes_precedence_over_local_env(monkeypatch) -> None:
    seen: list[str] = []
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "process-key")
    monkeypatch.setattr(agent_model, "read_local_env_value", lambda name: "local-key")
    monkeypatch.setattr(
        agent_model,
        "DeepSeekAgentModel",
        lambda key: seen.append(key) or object(),
    )

    build_agent_composition(AiConfig(enabled=True, provider="deepseek"))

    assert seen == ["process-key"]
