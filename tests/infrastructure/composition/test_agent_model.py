import pytest

from src.application.dto.agent_tools import AgentToolName
from src.application.services.agent_market_regime_tool import MarketRegimeTool
from src.application.use_case.orchestrate_agent_turn_use_case import AgentTurnOrchestrator
from src.application.use_case.session_aware_agent_turn_use_case import (
    SessionAwareAgentTurnUseCase,
)
from src.infrastructure.composition import agent_model
from src.infrastructure.composition.agent_model import build_agent_composition
from src.infrastructure.config.app_config import AiConfig
from src.infrastructure.config.local_env import read_local_env_value

pytestmark = pytest.mark.agent


class _EmptyMarketContextRepo:
    def get(self, as_of_date, *, semantic_compatibility_id=None):
        return None

    def get_recent(self, limit=30, *, semantic_compatibility_id=None):
        return []


def _market_regime_tool_stub(_path):
    return MarketRegimeTool(_EmptyMarketContextRepo(), cohort_id="sha256:test-cohort")


def test_disabled_composition_does_not_construct_provider(monkeypatch) -> None:
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    result = build_agent_composition(AiConfig(enabled=False, provider="deepseek"))
    assert result.provider_available is False
    assert result.use_case.provider_available is False
    assert result.tools_requested is False
    assert result.tools_enabled is False
    assert result.tools_multi_round is False
    assert result.session_requested is False
    assert result.session_enabled is False
    assert result.registered_tools == ()


def test_tools_multi_round_defaults_false_and_requires_tools(monkeypatch) -> None:
    sentinel = object()
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(agent_model, "DeepSeekAgentModel", lambda key: sentinel)

    l1 = build_agent_composition(
        AiConfig(enabled=True, provider="deepseek", tools_enabled=True, tools_multi_round=False)
    )
    l3 = build_agent_composition(
        AiConfig(enabled=True, provider="deepseek", tools_enabled=True, tools_multi_round=True)
    )
    multi_without_tools = build_agent_composition(
        AiConfig(enabled=True, provider="deepseek", tools_enabled=False, tools_multi_round=True)
    )

    assert l1.tools_multi_round is False
    assert isinstance(l1.use_case, AgentTurnOrchestrator)
    assert l1.use_case._policy.multi_round is False
    assert l1.use_case._policy.max_provider_calls == 2

    assert l3.tools_multi_round is True
    assert isinstance(l3.use_case, AgentTurnOrchestrator)
    assert l3.use_case._policy.multi_round is True
    assert l3.use_case._policy.max_provider_calls == 3
    assert l3.use_case._policy.max_tool_calls == 4

    assert multi_without_tools.tools_multi_round is False


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


def test_existing_db_registers_visible_ticker_dashboard_and_broker_desk_tools(
    monkeypatch,
    tmp_path,
) -> None:
    db_path = tmp_path / "dashboard.db"
    db_path.touch()
    sentinel_model = object()
    sentinel_dashboard = object()
    sentinel_desk = object()
    sentinel_flow = type(
        "FlowDeps",
        (),
        {"top_brokers": object(), "bandar_source": object()},
    )()
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(agent_model, "DeepSeekAgentModel", lambda key: sentinel_model)
    monkeypatch.setattr(
        agent_model,
        "build_read_only_ticker_dashboard_use_case",
        lambda path: sentinel_dashboard,
    )
    monkeypatch.setattr(
        agent_model,
        "build_read_only_broker_desk_use_cases",
        lambda path: sentinel_desk,
    )
    monkeypatch.setattr(
        agent_model,
        "build_read_only_ticker_broker_flow_deps",
        lambda path: sentinel_flow,
    )
    monkeypatch.setattr(
        agent_model,
        "build_read_only_ticker_foreign_history_use_case",
        lambda path: object(),
    )
    monkeypatch.setattr(
        agent_model,
        "build_read_only_ticker_desk_flow_history_service",
        lambda path: object(),
    )
    monkeypatch.setattr(
        agent_model,
        "build_read_only_ticker_ownership_source",
        lambda path: object(),
    )
    monkeypatch.setattr(
        agent_model,
        "build_read_only_ticker_ownership_history_use_case",
        lambda path: object(),
    )
    monkeypatch.setattr(
        agent_model,
        "build_read_only_preopen_iev_source",
        lambda path: object(),
    )
    monkeypatch.setattr(
        agent_model,
        "build_read_only_ticker_corp_action_source",
        lambda path: object(),
    )
    monkeypatch.setattr(
        agent_model,
        "build_read_only_ticker_sector_context_use_case",
        lambda path: object(),
    )
    monkeypatch.setattr(
        agent_model,
        "build_read_only_ticker_fundamentals_trend_use_case",
        lambda path: object(),
    )
    monkeypatch.setattr(
        agent_model,
        "build_read_only_ticker_insider_source",
        lambda path: object(),
    )
    monkeypatch.setattr(
        agent_model,
        "build_read_only_market_regime_tool",
        _market_regime_tool_stub,
    )
    monkeypatch.setattr(
        agent_model,
        "build_read_only_ticker_research_brief_use_case",
        lambda path, judge_ticker=None: object(),
    )

    result = build_agent_composition(
        AiConfig(enabled=True, provider="deepseek", tools_enabled=True),
        db_path=db_path,
    )

    assert result.registered_tools == (
        AgentToolName.GET_VISIBLE_COCKPIT_RESULT,
        AgentToolName.GET_TICKER_DASHBOARD,
        AgentToolName.GET_BROKER_DESK,
        AgentToolName.GET_TICKER_BROKER_FLOW,
        AgentToolName.GET_TICKER_FOREIGN_FLOW,
        AgentToolName.GET_TICKER_DESK_FLOW_HISTORY,
        AgentToolName.GET_TICKER_OWNERSHIP,
        AgentToolName.GET_TICKER_OWNERSHIP_HISTORY,
        AgentToolName.GET_PREOPEN_IEV,
        AgentToolName.GET_TICKER_CORPORATE_ACTIONS,
        AgentToolName.GET_TICKER_SECTOR_CONTEXT,
        AgentToolName.GET_TICKER_INSIDER_ACTIVITY,
        AgentToolName.GET_TICKER_FUNDAMENTALS_TREND,
        AgentToolName.GET_MARKET_REGIME,
        AgentToolName.GET_TICKER_RESEARCH_BRIEF,
    )


def test_approved_judge_factory_registers_accumulation_tool(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "dashboard.db"
    db_path.touch()

    def sentinel_judge(ticker):
        return ticker

    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(agent_model, "DeepSeekAgentModel", lambda key: object())
    monkeypatch.setattr(
        agent_model,
        "build_read_only_ticker_dashboard_use_case",
        lambda path: object(),
    )
    monkeypatch.setattr(
        agent_model,
        "build_read_only_broker_desk_use_cases",
        lambda path: object(),
    )
    monkeypatch.setattr(
        agent_model,
        "build_read_only_ticker_broker_flow_deps",
        lambda path: type(
            "FlowDeps",
            (),
            {"top_brokers": object(), "bandar_source": object()},
        )(),
    )
    monkeypatch.setattr(
        agent_model,
        "build_read_only_ticker_foreign_history_use_case",
        lambda path: object(),
    )
    monkeypatch.setattr(
        agent_model,
        "build_read_only_ticker_desk_flow_history_service",
        lambda path: object(),
    )
    monkeypatch.setattr(
        agent_model,
        "build_read_only_ticker_ownership_source",
        lambda path: object(),
    )
    monkeypatch.setattr(
        agent_model,
        "build_read_only_ticker_ownership_history_use_case",
        lambda path: object(),
    )
    monkeypatch.setattr(
        agent_model,
        "build_read_only_preopen_iev_source",
        lambda path: object(),
    )
    monkeypatch.setattr(
        agent_model,
        "build_read_only_ticker_corp_action_source",
        lambda path: object(),
    )
    monkeypatch.setattr(
        agent_model,
        "build_read_only_ticker_sector_context_use_case",
        lambda path: object(),
    )
    monkeypatch.setattr(
        agent_model,
        "build_read_only_ticker_fundamentals_trend_use_case",
        lambda path: object(),
    )
    monkeypatch.setattr(
        agent_model,
        "build_read_only_ticker_insider_source",
        lambda path: object(),
    )
    monkeypatch.setattr(
        agent_model,
        "build_read_only_market_regime_tool",
        _market_regime_tool_stub,
    )
    monkeypatch.setattr(
        agent_model,
        "build_read_only_ticker_research_brief_use_case",
        lambda path, judge_ticker=None: object(),
    )

    result = build_agent_composition(
        AiConfig(enabled=True, provider="deepseek", tools_enabled=True),
        db_path=db_path,
        accumulation_judge_factory=lambda: sentinel_judge,
    )

    assert result.registered_tools == (
        AgentToolName.GET_VISIBLE_COCKPIT_RESULT,
        AgentToolName.GET_TICKER_DASHBOARD,
        AgentToolName.GET_BROKER_DESK,
        AgentToolName.GET_TICKER_BROKER_FLOW,
        AgentToolName.GET_TICKER_FOREIGN_FLOW,
        AgentToolName.GET_TICKER_DESK_FLOW_HISTORY,
        AgentToolName.GET_TICKER_OWNERSHIP,
        AgentToolName.GET_TICKER_OWNERSHIP_HISTORY,
        AgentToolName.GET_PREOPEN_IEV,
        AgentToolName.GET_TICKER_CORPORATE_ACTIONS,
        AgentToolName.GET_TICKER_SECTOR_CONTEXT,
        AgentToolName.GET_TICKER_INSIDER_ACTIVITY,
        AgentToolName.GET_TICKER_FUNDAMENTALS_TREND,
        AgentToolName.GET_MARKET_REGIME,
        AgentToolName.GET_TICKER_RESEARCH_BRIEF,
        AgentToolName.JUDGE_ACCUMULATION_TICKER,
    )


def test_judge_factory_is_lazy_and_fail_soft(monkeypatch) -> None:
    calls = []

    def broken_factory():
        calls.append(True)
        raise OSError("read-only composition unavailable")

    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    disabled = build_agent_composition(
        AiConfig(enabled=False, provider="deepseek", tools_enabled=True),
        accumulation_judge_factory=broken_factory,
    )
    assert disabled.registered_tools == ()
    assert calls == []

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(agent_model, "DeepSeekAgentModel", lambda key: object())
    enabled = build_agent_composition(
        AiConfig(enabled=True, provider="deepseek", tools_enabled=True),
        accumulation_judge_factory=broken_factory,
    )
    assert enabled.registered_tools == (AgentToolName.GET_VISIBLE_COCKPIT_RESULT,)
    assert calls == [True]


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


def test_session_enabled_wraps_use_case_when_certified(monkeypatch) -> None:
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(agent_model, "DeepSeekAgentModel", lambda key: object())

    disabled = build_agent_composition(
        AiConfig(enabled=True, provider="deepseek", session_enabled=False)
    )
    enabled = build_agent_composition(
        AiConfig(enabled=True, provider="deepseek", session_enabled=True)
    )

    assert disabled.session_requested is False
    assert disabled.session_enabled is False
    assert not isinstance(disabled.use_case, SessionAwareAgentTurnUseCase)
    assert enabled.session_requested is True
    assert enabled.session_enabled is True
    assert isinstance(enabled.use_case, SessionAwareAgentTurnUseCase)


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
